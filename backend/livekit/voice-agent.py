import asyncio
import re
import os
import numpy as np

from dotenv import load_dotenv
from livekit.agents.tts import SynthesizedAudio

from livekit import agents, rtc
from livekit.agents.stt import SpeechEventType, SpeechEvent
from typing import AsyncIterable
from livekit.plugins import deepgram, elevenlabs

load_dotenv()

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    print("[Voice Agent] connected to room:", ctx.room.name)

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
    eleven_model = os.getenv("ELEVEN_TTS_MODEL", "eleven_turbo_v2_5")
    eleven_language = os.getenv("ELEVEN_TTS_LANG", "de")  # match your STT "de"

    tts = elevenlabs.TTS(
        voice_id=eleven_voice_id,
        model=eleven_model,
        language=eleven_language,
        streaming_latency=0,        # start with lowest latency; tune if choppy
        enable_ssml_parsing=False,  # keep it simple for now
        sync_alignment=False,       # no need for word timings yet
    )

    # Create audio source and publish TTS track
    # Use the TTS native sample rate - let LiveKit handle conversion
    tts_audio_source = rtc.AudioSource(tts.sample_rate, tts.num_channels)
    tts_track = rtc.LocalAudioTrack.create_audio_track("tts_audio", tts_audio_source)

    # Use SOURCE_UNKNOWN to prevent LiveKit from applying audio processing
    # that might attenuate the signal (AGC, noise suppression, etc.)
    tts_options = rtc.TrackPublishOptions(
        source=rtc.TrackSource.SOURCE_UNKNOWN,
    )

    await ctx.room.local_participant.publish_track(tts_track, tts_options)
    print(f"[TTS Agent] TTS audio track published at {tts.sample_rate}Hz with SOURCE_UNKNOWN")

    play_queue: asyncio.Queue[str] = asyncio.Queue()

    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        if data.topic == "chat_text":
            text_chunk = data.data.decode('utf-8')
            print(f"[TTS-Agent] queued text for TTS: {text_chunk}")
            play_queue.put_nowait(text_chunk)

    async def process_tts_chunk(text: str, audio_source: rtc.AudioSource):
        """
        Process text chunk through ElevenLabs TTS and stream audio to LiveKit
        Implements duplex mode for minimal latency
        """
        try:
            audio_stream = tts.stream()

            for audio_chunk in audio_stream:
                if isinstance(audio_chunk, bytes):
                    # Create audio frame from the chunk
                    # PCM 16-bit samples
                    samples_per_channel = len(audio_chunk) // 2  # 16-bit = 2 bytes per sample

                    if samples_per_channel > 0:
                        audio_frame = rtc.AudioFrame.create(
                            tts.sample_rate,
                            tts.num_channels,
                            samples_per_channel
                        )

                        # Copy audio data to frame using numpy for efficient memory manipulation
                        frame_array = np.frombuffer(audio_frame.data, dtype=np.int16)
                        chunk_array = np.frombuffer(audio_chunk, dtype=np.int16)
                        np.copyto(frame_array[:len(chunk_array)], chunk_array)

                        # Send frame to LiveKit immediately (minimal latency)
                        await audio_source.capture_frame(audio_frame)

            print(f"[TTS Agent] Audio chunk processed and streamed: {text[:50]}...")

        except Exception as e:
            print(f"[TTS Agent] Error processing TTS chunk: {e}")

    async def synthesize_and_stream(text: str, audio_source):
        try:
            audio_stream = tts.synthesize(text)
            async for audio_chunk in audio_stream:
                await audio_source.capture_frame(audio_chunk.frame)

        except Exception as e:
            print(f"[TTS Agent] Error during synthesis: {e}")

    chunk_counter = 0

    async def speak_text(text: str) -> None:
        """
        Send TTS audio via data channel in 0.5-second chunks for smooth playback.
        """
        nonlocal chunk_counter
        stream = tts.stream()
        import base64, json

        async def _pull_and_play():
            nonlocal chunk_counter
            buffer_chunks = []
            buffer_size = 0
            chunk_size = 11025  # 0.5 seconds at 22050Hz
            sample_rate = None
            num_channels = None

            stream.push_text(text)
            stream.end_input()

            async for audio_chunk in stream:
                if not isinstance(audio_chunk, SynthesizedAudio):
                    continue

                frame = audio_chunk.frame
                sample_rate = frame.sample_rate
                num_channels = frame.num_channels

                frame_data = bytes(frame.data)
                samples = np.frombuffer(frame_data, dtype=np.int16)
                buffer_chunks.append(samples)
                buffer_size += len(samples)

                # Send when we have 0.5 seconds of audio
                if buffer_size >= chunk_size:
                    combined = np.concatenate(buffer_chunks)
                    max_amp = np.max(np.abs(combined)) if len(combined) > 0 else 0
                    print(f"[TTS-Agent] Sending chunk #{chunk_counter}: {len(combined)} samples, amplitude: {max_amp}")

                    payload = json.dumps({
                        "audio": base64.b64encode(combined.tobytes()).decode('utf-8'),
                        "sample_rate": sample_rate,
                        "num_channels": num_channels,
                        "chunk_id": chunk_counter
                    }).encode('utf-8')

                    await ctx.room.local_participant.publish_data(payload, reliable=True, topic="tts_audio")

                    chunk_counter += 1
                    buffer_chunks = []
                    buffer_size = 0

            # Send remaining
            if buffer_chunks:
                combined = np.concatenate(buffer_chunks)
                max_amp = np.max(np.abs(combined)) if len(combined) > 0 else 0
                print(f"[TTS-Agent] Sending final chunk #{chunk_counter}: {len(combined)} samples, amplitude: {max_amp}")

                payload = json.dumps({
                    "audio": base64.b64encode(combined.tobytes()).decode('utf-8'),
                    "sample_rate": sample_rate,
                    "num_channels": num_channels,
                    "chunk_id": chunk_counter,
                    "final": True
                }).encode('utf-8')

                await ctx.room.local_participant.publish_data(payload, reliable=True, topic="tts_audio")
                chunk_counter += 1

            await stream.aclose()

        await _pull_and_play()

    async def playback_loop() -> None:
        print("[TTS-Agent] playback loop started; waiting for text…")
        while True:
            text = await play_queue.get()
            try:
                print(f"[TTS-Agent] speaking: {text!r}")
                await speak_text(text)
            except Exception as e:
                print(f"[TTS-Agent] error during synthesis: {e}")
            finally:
                play_queue.task_done()

    asyncio.create_task(playback_loop())

    # 5) Shutdown handling -------------------------------------------------------
    shutdown_event = asyncio.Event()

    # async def _on_shutdown(reason: str) -> None:
    #     print("[Voice-Agent] shutting down… reason:", reason)
    #     try:
    #         await tts.aclose()
    #     except Exception as e:
    #         print(f"[Voice-Agent] error closing TTS: {e}")
    #     try:
    #         await tts_audio_source.aclose()
    #     except Exception as e:
    #         print(f"[Voice-Agent] error closing audio source: {e}")
    #     shutdown_event.set()
    #
    # ctx.add_shutdown_callback(_on_shutdown)

    # 6) Block until job is told to shut down
    await shutdown_event.wait()



if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
