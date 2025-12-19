import asyncio
import json
import re
import os
import numpy as np

from dotenv import load_dotenv

from livekit.agents.stt import SpeechEventType, SpeechEvent
from typing import AsyncIterable
from livekit.plugins import deepgram, elevenlabs

from livekit import agents, rtc
from livekit.agents.tts import SynthesizedAudio

load_dotenv()

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    print("[Agent] connected to room:", ctx.room.name)
    shutdown_event = asyncio.Event()

    @ctx.room.on("disconnected")
    def on_disconnected():
        print("[Agent] Room disconnected, triggering shutdown")
        shutdown_event.set()

    #############################################
    #   STT agent                               #
    #############################################

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.RemoteTrack):
        print(f"[STT Agent] Subscribed to audio track.")
        asyncio.create_task(process_track(track))


    async def process_track(track: rtc.RemoteTrack):
        """Process incoming audio track for STT"""
        stt = deepgram.STT(model="nova-3", language="de", endpointing_ms=500)
        stt_stream = stt.stream()
        audio_stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=16000,
            num_channels=1
        )

        async with asyncio.TaskGroup() as tg:
            # Create task for processing STT stream
            stt_task = tg.create_task(process_stt_stream(stt_stream))

            # Process audio stream
            async for audio_event in audio_stream:
                stt_stream.push_frame(audio_event.frame)

            # Indicates the end of the audio stream
            stt_stream.end_input()

            # Wait for STT processing to complete
            await stt_task


    async def process_stt_stream(stream: AsyncIterable[SpeechEvent]):
        """Process STT stream and publish transcripts"""
        try:
            async for event in stream:
                if event.type == SpeechEventType.FINAL_TRANSCRIPT:
                    alternatives = event.alternatives
                    if alternatives and len(alternatives) > 0:
                        text = alternatives[0].text
                    else:
                        continue
                    print(f"Prompt:  {text}")

                    if re.search(r"^(nachricht )?(senden|wenn denn|wenden)\W?$", text, re.I):
                        print("Send prompt detected.")
                        await ctx.room.local_participant.publish_data(
                            "send",
                            topic="system"
                        )
                    elif re.search(r"^(nachricht )?l([öa])schen\W?$", text, re.I):
                        print("Delete prompt detected.")
                        await ctx.room.local_participant.publish_data(
                            "delete",
                            topic="system"
                        )
                    else:
                        await ctx.room.local_participant.publish_data(
                            text.encode('utf-8'),
                            topic="transcript"
                        )
        finally:
            await stream.aclose()
            # ctx.shutdown() # Don't shutdown, keep running for TTS


    #############################################
    #   TTS agent                               #
    #############################################

    # Initialize TTS
    eleven_voice_id = os.getenv("ELEVEN_VOICE_ID")
    eleven_model = os.getenv("ELEVEN_TTS_MODEL", "eleven_flash_v2_5")
    eleven_language = os.getenv("ELEVEN_TTS_LANG", "de")

    tts = elevenlabs.TTS(
        voice_id=eleven_voice_id,
        model=eleven_model,
        language=eleven_language,
        streaming_latency=0,
        enable_ssml_parsing=True,
        sync_alignment=False,
    )

    # text_stream: AsyncIterable[str] = ... # you need to provide a stream of text
    audio_source = rtc.AudioSource(tts.sample_rate, tts.num_channels)
    tts_track = rtc.LocalAudioTrack.create_audio_track("agent-audio", audio_source)
    await ctx.room.local_participant.publish_track(tts_track)
    await ctx.room.local_participant.publish_data(
        payload=json.dumps({
            "track_id": tts_track.sid,
            "identity": ctx.room.local_participant.identity,
        }).encode('utf-8'),
        reliable=True,
        topic="agent_info"
    )
    print(f"[TTS Agent] TTS audio track published, name: {tts_track.name}, sid: {tts_track.sid}, participant: {ctx.room.local_participant.identity}")

    # Queue for sequential TTS stream processing
    tts_queue: asyncio.Queue[AsyncIterable[SynthesizedAudio] | None] = asyncio.Queue()
    current_stream_task: asyncio.Task | None = None
    queue_worker_task: asyncio.Task | None = None

    async def process_audio_stream(audio_stream: AsyncIterable[SynthesizedAudio]):
        """Process a single audio stream and capture frames to audio source."""
        total_duration = 0.0
        first_frame = True

        async for a in audio_stream:
            # Send TTS begin signal on the first frame
            if first_frame:
                asyncio.create_task(ctx.room.local_participant.publish_data(
                    payload=b'',
                    reliable=True,
                    topic="tts_start"
                ))
                first_frame = False
                print("[TTS Agent] Sent tts_start signal.")

            # DEBUG: Check if audio frame has actual audio data
            # frame_data = a.frame.data.tobytes()
            # audio_array = np.frombuffer(frame_data, dtype=np.int16)
            # audio_min = audio_array.min()
            # audio_max = audio_array.max()
            # audio_avg_abs = np.abs(audio_array).mean()

            # duration_ms = (len(audio_array) / a.frame.num_channels) / (a.frame.sample_rate / 1000.0)
            # total_duration += duration_ms

            # print(f"[TTS Agent] audio frame sent: {a.frame}, duration={duration_ms:.2f}ms, total={total_duration/1000.0:.2f}s, min={audio_min}, max={audio_max}, avg_abs={audio_avg_abs:.2f}")

            await audio_source.capture_frame(a.frame)

        if tts_queue.empty():
            # Send tts_complete only when all queued streams have been processed
            await ctx.room.local_participant.publish_data(
                payload=b'',
                reliable=True,
                topic="tts_complete"
            )

            print("[TTS Agent] All streams processed, sending tts_complete signal")

    async def tts_queue_worker():
        """Worker that processes TTS streams from the queue sequentially."""
        nonlocal current_stream_task

        while True:
            try:
                # Wait for the next audio stream from the queue
                audio_stream = await tts_queue.get()

                # None is the sentinel value to stop the worker
                if audio_stream is None:
                    print("[TTS Agent] Queue worker received shutdown signal")
                    break

                # Process the audio stream
                try:
                    current_stream_task = asyncio.current_task()
                    await process_audio_stream(audio_stream)
                except asyncio.CancelledError:
                    print("[TTS Agent] Current stream processing cancelled")
                    raise
                finally:
                    current_stream_task = None
                    tts_queue.task_done()

            except asyncio.CancelledError:
                print("[TTS Agent] Queue worker cancelled")
                break
            except Exception as e:
                print(f"[TTS Agent] Error processing audio stream: {e}")
                tts_queue.task_done()

    # Start the queue worker
    queue_worker_task = asyncio.create_task(tts_queue_worker())

    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        if data.topic == "chat_text":
            # Send complete sentences to TTS via queue
            sentence = data.data.decode('utf-8')
            sentence = f"<s>{sentence}</s>"
            chunked_stream = tts.synthesize(sentence)
            tts_queue.put_nowait(chunked_stream)
            # print(f"[TTS-Agent] Queued: {sentence}")

        elif data.topic == "chat_text_end":
            sentence = data.data.decode('utf-8')
            if sentence:
                sentence = f"<s>{sentence}</s>"
                chunked_stream = tts.synthesize(sentence)
                tts_queue.put_nowait(chunked_stream)
                # print(f"[TTS-Agent] Queued (end): {sentence}")

            # print(f"[TTS-Agent] end of message")

        elif data.topic == "stop_response":
            asyncio.create_task(handle_stop_signal())


    async def handle_stop_signal():
        nonlocal queue_worker_task, current_stream_task
        print("[TTS-Agent] Received stop_response signal")

        # Clear all pending items from the queue
        cleared_count = 0
        while not tts_queue.empty():
            try:
                tts_queue.get_nowait()
                tts_queue.task_done()
                cleared_count += 1
            except asyncio.QueueEmpty:
                break

        if cleared_count > 0:
            print(f"[TTS-Agent] Cleared {cleared_count} pending streams from queue")

        # Cancel the queue worker to interrupt current playback
        if queue_worker_task and not queue_worker_task.done():
            queue_worker_task.cancel()
            try:
                await queue_worker_task
            except asyncio.CancelledError:
                pass

        # Restart the queue worker for new input
        queue_worker_task = asyncio.create_task(tts_queue_worker())
        print("[TTS-Agent] Queue worker restarted for new input")
    

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
