import asyncio
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
    eleven_voice_id = os.getenv("ELEVEN_VOICE_ID")  # optional, None -> default
    eleven_model = os.getenv("ELEVEN_TTS_MODEL", "eleven_flash_v2_5")
    eleven_language = os.getenv("ELEVEN_TTS_LANG", "de")  # match your STT "de"

    tts = elevenlabs.TTS(
        voice_id=eleven_voice_id,
        model=eleven_model,
        language=eleven_language,
        streaming_latency=0,        # start with lowest latency; tune if choppy
        enable_ssml_parsing=False,  # keep it simple for now
        sync_alignment=False,       # no need for word timings yet
    )
    tts_stream = tts.stream()


    # text_stream: AsyncIterable[str] = ... # you need to provide a stream of text
    audio_source = rtc.AudioSource(tts.sample_rate, tts.num_channels)
    tts_track = rtc.LocalAudioTrack.create_audio_track("agent-audio", audio_source)
    pub = await ctx.room.local_participant.publish_track(tts_track)
    print(f"[TTS Agent] TTS audio track published, muted: {pub.muted}, name: {tts_track.name}, sid: {tts_track.sid}, participant: {ctx.room.local_participant.identity}")

    async def send_audio(audio_stream: AsyncIterable[SynthesizedAudio]):
        total_duration = 0.0
        async for a in audio_stream:
            # DEBUG: Check if audio frame has actual audio data
            frame_data = a.frame.data.tobytes()
            audio_array = np.frombuffer(frame_data, dtype=np.int16)
            audio_min = audio_array.min()
            audio_max = audio_array.max()
            audio_avg_abs = np.abs(audio_array).mean()

            duration_ms = (len(audio_array) / a.frame.num_channels) / (a.frame.sample_rate / 1000.0)
            total_duration += duration_ms

            print(f"[TTS Agent] audio frame sent: {a.frame}, duration={duration_ms:.2f}ms, total={total_duration/1000.0:.2f}s, min={audio_min}, max={audio_max}, avg_abs={audio_avg_abs:.2f}")

            await audio_source.capture_frame(a.frame)
        
        # Wait for audio to flush (prevent race condition where signal arrives before last audio frames)
        await asyncio.sleep(2.0)
        
        print(f"[TTS Agent] Audio stream finished. Sending tts_complete signal.")
        await ctx.room.local_participant.publish_data(
            payload=b'',
            reliable=True,
            topic="tts_complete"
        )

    asyncio.create_task(send_audio(tts_stream))

    # Text buffering for complete sentences
    text_buffer = ""

    def extract_complete_sentences(text):
        """
        Extract complete sentences from text.
        Returns: (list of complete sentences, remaining incomplete text)
        """

        # Common sentence delimiters
        sentence_endings = r'(\n|[.!?]+[\s\n]+|[.!?]+$)'

        # Split by sentence endings while keeping the delimiters
        parts = re.split(sentence_endings, text)

        sentence = ""
        current = ""

        for i, part in enumerate(parts):
            current += part
            # If this is a delimiter (odd indices after split) and not the last part
            if i % 2 == 1:
                sentence += current.strip()
                current = ""

        # Return complete sentences and any remaining incomplete text
        return sentence, current

    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        nonlocal text_buffer

        if data.topic == "chat_text":
            text_chunk = data.data.decode('utf-8')
            # print(f"[TTS-Agent] received text chunk: {text_chunk}")

            text_buffer += text_chunk
            sentence, remaining = extract_complete_sentences(text_buffer)

            # Send complete sentences to TTS
            if sentence:
                text_buffer = remaining
                tts_stream.push_text(sentence)

                print(f"[TTS-Agent] sending complete sentence: {sentence}")

            # Keep only the incomplete part in buffer
            text_buffer = remaining if remaining else ''

        elif data.topic == "chat_text_end":
            # Flush any remaining buffered text
            if text_buffer:
                remaining_text = text_buffer.strip()
                if remaining_text:
                    print(f"[TTS-Agent] flushing remaining text: {remaining_text}")
                    tts_stream.push_text(remaining_text)
                text_buffer = ""

            tts_stream.end_input()
            print(f"[TTS-Agent] end of message")

    shutdown_event = asyncio.Event()
    await shutdown_event.wait()



if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
