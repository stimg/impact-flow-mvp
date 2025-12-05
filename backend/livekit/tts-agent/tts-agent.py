import asyncio
import os

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.plugins import elevenlabs
from livekit.agents.tts import SynthesizedAudio

load_dotenv()


TTS_TOPIC = "assistant-tts"  # data topic the agent will listen on


async def entrypoint(ctx: agents.JobContext):
    """
    Standalone TTS agent:
    - Joins the room
    - Publishes one audio track ("assistant-tts")
    - Listens for data messages with topic=TTS_TOPIC
    - Speaks the received text using ElevenLabs via LiveKit plugin
    """

    # Connect to the room (no need for auto_subscribe here)
    await ctx.connect()
    print("[TTS-Agent] connected to room:", ctx.room.name)

    # --- ElevenLabs TTS setup -------------------------------------------------
    # ELEVEN_API_KEY must be set in env (see livekit-plugins-elevenlabs docs)
    # You can optionally configure voice/model via env vars.
    eleven_voice_id = os.getenv("ELEVEN_VOICE_ID")  # optional, None -> default
    eleven_model = os.getenv("ELEVEN_TTS_MODEL", "eleven_flash_v2_5")
    eleven_language = os.getenv("ELEVEN_TTS_LANG", "de")  # match your STT "de"

    tts = elevenlabs.TTS(
        voice_id=eleven_voice_id if eleven_voice_id else elevenlabs.DEFAULT_VOICE.id,
        model=eleven_model,
        language=eleven_language,
        streaming_latency=0,        # start with lowest latency; tune if choppy
        enable_ssml_parsing=False,  # keep it simple for now
        sync_alignment=False,       # no need for word timings yet
    )

    # We’ll stream audio frames from TTS into this AudioSource
    # ElevenLabs defaults to 24kHz mono PCM for streaming, which matches this.
    sample_rate = 24000
    num_channels = 1

    source = rtc.AudioSource(
        sample_rate=sample_rate,
        num_channels=num_channels,
    )
    track = rtc.LocalAudioTrack.create_audio_track("assistant-tts", source)

    await ctx.room.local_participant.publish_track(track)
    print("[TTS-Agent] published audio track: assistant-tts")

    # --- Message queue + playback loop ----------------------------------------

    # Queue for incoming text messages (to avoid overlapping playback)
    play_queue: asyncio.Queue[str] = asyncio.Queue()

    @ctx.room.on("data_received")
    def _on_data_received(data: bytes, participant: rtc.RemoteParticipant, topic: str):
        if topic != TTS_TOPIC:
            return

        try:
            text = data.decode("utf-8").strip()
        except Exception as e:
            print(f"[TTS-Agent] failed to decode data message: {e}")
            return

        if not text:
            return

        print(f"[TTS-Agent] queued text from {participant.identity}: {text!r}")
        play_queue.put_nowait(text)

    async def playback_loop():
        print("[TTS-Agent] playback loop started; waiting for text…")
        while True:
            text = await play_queue.get()
            try:
                print(f"[TTS-Agent] speaking: {text!r}")
                await speak_text(tts, source, text)
            except Exception as e:
                print(f"[TTS-Agent] error during synthesis: {e}")
            finally:
                play_queue.task_done()

    # Start playback loop in background
    asyncio.create_task(playback_loop())

    # Clean up nicely when job is shutting down
    async def _shutdown():
        print("[TTS-Agent] shutting down…")
        try:
            await tts.aclose()
        except Exception as e:
            print(f"[TTS-Agent] error closing TTS: {e}")

    ctx.add_shutdown_callback(_shutdown)

    # Block until LiveKit tells this job to shut down
    await ctx.run_until_shutdown()


async def speak_text(
        tts: elevenlabs.TTS,
        source: rtc.AudioSource,
        text: str,
) -> None:
    """
    Stream TTS audio into the LiveKit AudioSource.
    Uses ElevenLabs plugin streaming API for low latency.
    """
    stream = tts.stream()

    async def _pull_and_play():
        async for ev in stream:  # ev: SynthesizedAudio
            if not isinstance(ev, SynthesizedAudio):
                continue
            # ev.frame is an rtc.AudioFrame; push it into the source
            await source.capture_frame(ev.frame)

    pull_task = asyncio.create_task(_pull_and_play())

    try:
        # Push the text for this utterance
        stream.push_text(text)
        stream.end_input()  # signal no more text for this utterance

        await pull_task
    finally:
        await stream.aclose()


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))