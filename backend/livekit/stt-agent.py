import asyncio
import re

from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents.stt import SpeechEventType, SpeechEvent
from typing import AsyncIterable
from livekit.plugins import (
    deepgram
)

load_dotenv()

async def entrypoint(ctx: agents.JobContext):
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    print("[Agent] connected to room:", ctx.room.name)

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.RemoteTrack):
        print(f"[Agent] Subscribed to audio track.")

        asyncio.create_task(process_track(track))

    async def process_track(track: rtc.RemoteTrack):
        stt = deepgram.STT(model="nova-3", language="de", endpointing_ms=250)
        stt_stream = stt.stream()
        audio_stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=16000,
            num_channels=1
        )
        await ctx.room.local_participant.publish_data(
            "connected",
            topic="system"
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
        try:
            async for event in stream:
                if event.type == SpeechEventType.FINAL_TRANSCRIPT:
                    text = event.alternatives[0].text
                    print(f"Prompt:  {text}")

                    if re.search(r"^(nachricht )?(senden|wenn denn|wenden)\W?$", text, re.I):
                        print("Send prompt detected.")
                        await ctx.room.local_participant.publish_data(
                            "send",
                            topic="system"   # optional topic
                        )
                    elif re.search(r"^(nachricht )?l([öa])schen\W?$", text, re.I):
                        print("Delete prompt detected.")
                        await ctx.room.local_participant.publish_data(
                            "delete",
                            topic="system"   # optional topic
                        )
                    else:
                        await ctx.room.local_participant.publish_data(
                            text.encode('utf-8'),
                            topic="transcript"   # optional topic
                        )
                # elif event.type == SpeechEventType.INTERIM_TRANSCRIPT:
                #     print(f"> {event.alternatives[0].text}")
                # elif event.type == SpeechEventType.START_OF_SPEECH:
                #     print("-start-")
                # elif event.type == SpeechEventType.END_OF_SPEECH:
                #     print("-stop-")
        finally:
            await stream.aclose()
            ctx.shutdown()

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))