import asyncio
import logging
import base64
import numpy as np

from livekit import rtc

log = logging.getLogger(__name__)

class LiveKitWebRTCHelper:
    def __init__(self, url: str, token: str, event_emitter):
        self.url = url
        self.token = token
        self.event_emitter = event_emitter
        self.room = rtc.Room()
        self.connected = False

    async def connect(self):
        try:
            log.info(f"Connecting to LiveKit room at {self.url}")

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
                asyncio.create_task(self.handle_audio_stream(track))

            await self.room.connect(self.url, self.token)
            self.connected = True
            self.tts_done_event = asyncio.Event()

            @self.room.on("data_received")
            def on_data_received(data: rtc.DataPacket):
                if data.topic == "tts_complete":
                    log.info("Received tts_complete signal from agent")
                    self.tts_done_event.set()

            log.info(f"Connected to LiveKit room: {self.room.name}")

        except Exception as e:
            log.error(f"Failed to connect to LiveKit: {e}")

    async def handle_audio_stream(self, track: rtc.Track):
        log.info("Starting audio stream handler")

        # IMPORTANT: match the TTS output format (ElevenLabs via LK: 22050 Hz, mono)
        sample_rate = 22050
        num_channels = 1

        # Create an AudioStream that yields rtc.AudioFrameEvent(frame=AudioFrame)
        audio_stream = rtc.AudioStream.from_track(
            track=track,
            sample_rate=sample_rate,
            num_channels=num_channels,
            frame_size_ms=100, # 100ms chunks to reduce overhead
        )

        total_duration = 0.0

        try:
            async for audio_event in audio_stream:
                frame = audio_event.frame  # rtc.AudioFrame
                pcm_arr = np.frombuffer(frame.data, dtype=np.int16)
                audio_array = pcm_arr # .tobytes()

                duration_ms = (len(audio_array) / num_channels) / (sample_rate / 1000.0)
                total_duration += duration_ms

                # audio_array = np.frombuffer(pcm_bytes, dtype=np.int16)
                log.info(
                    "Audio frame stats: samples=%d, duration=%.2fms, total=%.2fs, min=%d, max=%d, avg_abs=%.2f",
                    len(audio_array),
                    duration_ms,
                    total_duration / 1000.0,
                    audio_array.min(),
                    audio_array.max(),
                    np.abs(audio_array).mean(),
                )

                encoded_data = base64.b64encode(audio_array).decode("ascii")

                # Use create_task to avoid blocking the audio reader loop
                asyncio.create_task(self.event_emitter({
                    "type": "chat:audio",
                    "data": {
                        "audio": encoded_data,                 # raw int16 PCM, base64
                        "sample_rate": frame.sample_rate,      # should be 22050
                        "num_channels": frame.num_channels,    # should be 1
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
                await audio_stream.aclose()
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

    async def wait_for_tts_completion(self, timeout: float = 30.0):
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
