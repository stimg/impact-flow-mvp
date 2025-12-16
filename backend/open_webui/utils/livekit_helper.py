import asyncio
import logging
import base64
import os
import numpy as np
from uuid import uuid4

from livekit import rtc
from livekit import api as livekit_api

log = logging.getLogger(__name__)

class LiveKitWebRTCHelper:
    def __init__(self, room_name: str, event_emitter):
        self.room_name = room_name
        self.event_emitter = event_emitter
        self.room = rtc.Room()
        self.connected = False
        self.audio_stream_task = None
        self.audio_stream = None

    async def connect(self):
        try:
            LIVEKIT_URL = os.getenv('LIVEKIT_URL')
            LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
            LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')

            if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
                log.error("LiveKit environment variables not configured")
                return

            identity = f"backend-{uuid4().hex[:8]}"
            token = livekit_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
                .with_identity(identity) \
                .with_name("Open WebUI Backend") \
                .with_grants(livekit_api.VideoGrants(
                    room_join=True,
                    room=self.room_name,
                )).to_jwt()

            log.info(f"Connecting to LiveKit room {self.room_name} at {LIVEKIT_URL}")

            # Set up track subscription handler BEFORE connecting
            @self.room.on("track_subscribed")
            def on_track_subscribed(
                    track: rtc.Track,
                    publication: rtc.TrackPublication,
                    participant: rtc.RemoteParticipant,
            ):
                log.info(
                    "Track subscribed: kind=%s sid=%s name=%s pub_name=%s muted=%s from identity=%s",
                    track.kind,
                    getattr(track, "sid", None),
                    getattr(track, "name", None),
                    getattr(publication, "name", None),
                    getattr(publication, "muted", None),
                    participant.identity,
                )

                if track.kind != rtc.TrackKind.KIND_AUDIO:
                    return

                if track.name != "agent-audio":
                    log.info("Ignoring non audio agent tracks")
                    return

                log.info("Starting audio stream handler for TTS track name: %s, sid: %s", track.name, track.sid)
                self.audio_stream_task = asyncio.create_task(self.handle_audio_stream(track))

            await self.room.connect(LIVEKIT_URL, token)
            self.connected = True
            self.tts_done_event = asyncio.Event()

            @self.room.on("data_received")
            def on_data_received(data: rtc.DataPacket):
                if data.topic == "tts_complete":
                    log.info("Received tts_complete signal from agent")
                    self.tts_done_event.set()
                elif data.topic == "stop_response":
                    log.info("Received stop_response signal from frontend")
                    asyncio.create_task(self.stop_audio_stream_processing())

            log.info(f"Connected to LiveKit room: {self.room.name}")

        except Exception as e:
            log.error(f"Failed to connect to LiveKit: {e}")

    async def handle_audio_stream(self, track: rtc.Track):
        log.info("Starting audio stream handler")

        # IMPORTANT: match the TTS output format (ElevenLabs via LK: 22050 Hz, mono)
        sample_rate = 22050

        self.audio_stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=sample_rate,
            frame_size_ms=50,
        )

        # total_duration = 0.0
        speech_started = False

        try:
            async for audio_event in self.audio_stream:
                frame = audio_event.frame
                audio_array = np.frombuffer(frame.data, dtype=np.int16)
                avg_abs = np.abs(audio_array).mean()

                # duration_ms = len(audio_array) / (sample_rate / 1000.0)
                # total_duration += duration_ms
                # log.info(
                #     "Audio frame stats: samples=%d, duration=%.2fms, total=%.2fs, min=%d, max=%d, avg_abs=%.2f",
                #     len(audio_array),
                #     duration_ms,
                #     total_duration / 1000.0,
                #     audio_array.min(),
                #     audio_array.max(),
                #     avg_abs,
                # )

                # Filter out initial silence only
                if not speech_started:
                    if avg_abs < 100:
                        continue
                    else:
                        speech_started = True
                        # log.info("Speech started (avg_abs=%.2f)", avg_abs)

                encoded_data = base64.b64encode(audio_array).decode("ascii")

                # Use create_task to avoid blocking the audio reader loop
                asyncio.create_task(self.event_emitter({
                    "type": "chat:audio",
                    "data": {
                        "audio": encoded_data,
                        "sample_rate": frame.sample_rate,
                        "num_channels": frame.num_channels,
                    },
                }))
        except asyncio.CancelledError:
            # room disconnect / shutdown – normal
            log.info("Audio stream handler cancelled")
        except Exception as e:
            log.error(f"Error handling audio stream: {e}", exc_info=True)
        finally:
            # ensure stream is closed and FFI resources cleaned up
            try:
                await self.audio_stream.aclose()
            except Exception:
                pass

    async def send_text(self, text: str):
        if not self.connected:
            log.warning("LiveKit not connected, cannot send text")
            return

        try:
            # Publish data to the room
            # Topic 'text' or similar is often used by agents
            payload = text.encode('utf-8')
            await self.room.local_participant.publish_data(
                payload,
                reliable=True,
                topic="chat_text"
            )
        except Exception as e:
            log.error(f"Failed to send text to LiveKit: {e}")

    async def end_of_input(self):
        if not self.connected:
            log.warning("LiveKit not connected.")
            return

        try:
            await self.room.local_participant.publish_data(
                payload=b'',
                reliable=True,
                topic="chat_text_end"
            )
        except Exception as e:
            log.error(f"Failed to send text to LiveKit: {e}")

    async def wait_for_tts_completion(self, timeout: float = 300.0):
        """Wait for the TTS agent to signal completion or timeout."""
        if not self.connected:
            return
            
        log.info(f"Waiting for TTS completion (timeout={timeout}s)...")
        try:
            await asyncio.wait_for(self.tts_done_event.wait(), timeout=timeout)
            log.info("TTS completion signal received.")
        except asyncio.TimeoutError:
            log.warning("Timed out waiting for TTS completion signal.")

    async def disconnect(self):
        if self.connected:
            await self.room.disconnect()
            self.connected = False
            log.info("Disconnected from LiveKit room")

    async def stop_audio_stream_processing(self):
        if self.audio_stream_task and not self.audio_stream_task.done():
            self.audio_stream_task.cancel()
            log.info("Cancelled audio stream task")
        
        if self.audio_stream:
            try:
                await self.audio_stream.aclose()
                log.info("Closed audio stream")
            except Exception as e:
                log.error(f"Failed to close audio stream: {e}")
