import asyncio
import logging
import base64
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
            def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
                log.info(f"Track subscribed: {track.kind} from {participant.identity}")
                if track.kind == rtc.TrackKind.KIND_AUDIO:
                    log.info(f"Starting audio stream handler for track {track.sid}")
                    asyncio.create_task(self.handle_audio_stream(track))

            await self.room.connect(self.url, self.token)
            self.connected = True
            log.info(f"Connected to LiveKit room: {self.room.name}")

        except Exception as e:
            log.error(f"Failed to connect to LiveKit: {e}")

    async def handle_audio_stream(self, track):
        log.info("Starting audio stream handler")
        try:
            # Use from_track() method - this is the correct API
            audio_stream = rtc.AudioStream.from_track(
                track=track,
                sample_rate=22050,  # Match the TTS output from voice-agent (ElevenLabs turbo_v2_5)
                num_channels=1
            )

            async for audio_event in audio_stream:
                frame = audio_event.frame

                # frame.data is memoryview of int16 samples
                data = bytes(frame.data)
                encoded_data = base64.b64encode(data).decode('utf-8')

                log.debug(f"Sending audio chunk: {len(data)} bytes, {frame.sample_rate}Hz, {frame.num_channels}ch")

                await self.event_emitter({
                    "type": "chat:audio",
                    "data": {
                        "audio": encoded_data,
                        "sample_rate": frame.sample_rate,
                        "num_channels": frame.num_channels
                    }
                })
        except Exception as e:
            log.error(f"Error handling audio stream: {e}")

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

    async def disconnect(self):
        if self.connected:
            await self.room.disconnect()
            self.connected = False
            log.info("Disconnected from LiveKit room")
