### What you asked
A full track of function calls (with short descriptions) starting at `MessageInput.svelte:1480` — the point where the audio file is sent for transcription and the transcript is sent as a text prompt.

Below is the end‑to‑end flow for BOTH possible paths: (A) LiveKit streaming ASR and (B) the fallback file‑upload transcription. Your referenced `:1480` line sits in the click handler that toggles recording and chooses between these paths.

---

### The button click and branching point
- File: `src/lib/components/chat/MessageInput.svelte`
- Lines: 1469–1489
- What happens:
    - The mic button’s `on:click` handler checks `LIVEKIT_ENABLED`.
    - If `LIVEKIT_ENABLED` is true → it toggles LiveKit ASR (`startLivekitAsr`/`stopLivekitAsr`).
    - Else (fallback) → requests mic permission and sets `recording = true` at `1480`.

```svelte
on:click={async () => {
  if (LIVEKIT_ENABLED) {
    if (!lkConnected) { await startLivekitAsr(); } else { await stopLivekitAsr(); }
  } else {
    // fallback: simple mic permission + toggle recording UI
    ...
    if (stream) {
      recording = true;          // <- line 1480: this triggers VoiceRecording UI
      ...
    }
  }
}}
```

From here, the flow splits:

---

### A) LiveKit streaming ASR path (no file upload)
- File: `src/lib/components/chat/MessageInput.svelte`
- Function: `startLivekitAsr()`
- Lines: 74–105
- Short description:
    1. Gets mic via `navigator.mediaDevices.getUserMedia`.
    2. Creates a `livekit-client` `Room` and registers a transcription event listener.
    3. Fetches a LiveKit token via `getLivekitToken()` (client API) and connects to the room.
    4. Publishes the mic track to the room; sets `lkConnected = true` and `recording = true`.
    5. On transcription events, it appends recognized text directly into the chat input `prompt`.

```ts
async function startLivekitAsr() {
  const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  ...
  const room = new Room({ adaptiveStream: true, dynacast: true });
  room.on((RoomEvent as any).TranscriptionReceived ?? 'transcription-received', (evt: any) => {
    const segments = (evt?.segments ?? []);
    for (const seg of segments) {
      if (seg?.final && seg?.text) prompt = `${prompt}${seg.text} `;  // Append transcript to prompt
    }
  });
  const { url, token } = await getLivekitToken();                     // from `$lib/apis`
  await room.connect(url, token);
  await room.localParticipant.publishTrack(lkMicTrack);
  lkConnected = true;
  recording = true;
}
```

- How transcript becomes prompt:
    - Directly in the event handler above: `prompt = `${prompt}${seg.text} `` (line ~85).
    - There is no file sent to the backend in this path; LiveKit server produces transcription events.

- Stopping:
    - Function: `stopLivekitAsr()` (lines 107–116) disconnects room, stops mic track, and sets `recording = false`.

- Server endpoints involved here:
    - Not for the transcription itself. However, `getLivekitToken()` hits your backend to fetch a LiveKit access token. See: `src/lib/apis/index.ts` where `getLivekitToken` is defined and the backend that serves it (recent files show `backend/open_webui/routers/livekitapi.py`).

- Backend snippets to know:
    - File: `backend/open_webui/routers/livekitapi.py`
    - Endpoint: `POST /transcribe` (line ~50) and handler `transcribe_audio(...)` (line ~51). This router deals with LiveKit related requests/tokens.

---

### B) Fallback path — local recording with file upload to transcribe
This is the path that starts exactly at your referenced `MessageInput.svelte:1480` when `recording = true` is set.

1) Recording UI mounts and manages capture
- File: `src/lib/components/chat/MessageInput.svelte`
- Lines: 679–701
- Short description:
    - When `recording` is true, the component renders `<VoiceRecording ... />`.
    - It binds `recording` and provides `onConfirm` and `onCancel` handlers.

```svelte
{#if recording}
  <VoiceRecording
    bind:recording
    onCancel={...}
    onConfirm={async (data) => {
      const { text, filename } = data;
      prompt = `${prompt}${text} `;              // append transcript to prompt
      recording = false;
      if ($settings?.speechAutoSend ?? false) {
        dispatch('submit', prompt);             // optional auto-send
      }
    }}
  />
{/if}
```

2) VoiceRecording: capture audio, stop, and prepare blob/file
- File: `src/lib/components/chat/MessageInput/VoiceRecording.svelte`
- Key lines: 174–241 (start/stop flow) and 141–172 (`onStopHandler`)
- Short description:
    - Uses `MediaRecorder` to collect `audioChunks`.
    - On stop, creates a `Blob`, converts it to a `File` (`blobToFile`), and, if transcription is enabled, calls the client API `transcribeAudio`.

```ts
const onStopHandler = async (audioBlob, ext: string = 'wav') => {
  const file = blobToFile(audioBlob, `Recording-${dayjs().format('L LT')}.${ext}`);
  if (transcribe) {
    if ($config.audio.stt.engine === 'web' || ($settings?.audio?.stt?.engine ?? '') === 'web') {
      // web STT path: handled on-device; no upload
      return;
    }
    const res = await transcribeAudio(localStorage.token, file, $settings?.audio?.stt?.language)
      .catch((error) => { toast.error(`${error}`); return null; });
    if (res) {
      onConfirm(res);                              // returns { text, filename }
    }
  } else {
    onConfirm({ file, blob: audioBlob });
  }
};
```

3) Client API: upload the audio file for transcription
- File: `src/lib/apis/audio/index.ts`
- Function: `transcribeAudio(token, file, language?)`
- Lines: 67–98
- Short description:
    - Builds a `FormData` with the recorded file and optional `language`.
    - `POST` to `${AUDIO_API_BASE_URL}/transcriptions` with `Authorization: Bearer <token>`.
    - Returns the server JSON response.

```ts
export const transcribeAudio = async (token: string, file: File, language?: string) => {
  const data = new FormData();
  data.append('file', file);
  if (language) data.append('language', language);
  const res = await fetch(`${AUDIO_API_BASE_URL}/transcriptions`, {
    method: 'POST',
    headers: { Accept: 'application/json', authorization: `Bearer ${token}` },
    body: data
  })
  .then(async (res) => { if (!res.ok) throw await res.json(); return res.json(); });
  return res; // expected { text: string, filename: string }
};
```

4) Backend: accept upload, save to cache, run transcription, return text
- File: `backend/open_webui/routers/audio.py`
- Endpoint: `POST /transcriptions`
- Lines: 913–979 (handler `transcription`)
- Short description:
    - Validates MIME type, writes uploaded file into `CACHE_DIR/audio/transcriptions/<uuid>.<ext>`.
    - Calls `transcribe(request, file_path, metadata)` and returns its result with `filename`.

```py
@router.post("/transcriptions")
def transcription(request: Request, file: UploadFile = File(...), language: Optional[str] = Form(None), user=Depends(get_verified_user)):
  ...
  with open(file_path, "wb") as f: f.write(contents)
  metadata = {"language": language} if language else None
  result = transcribe(request, file_path, metadata)
  return { **result, "filename": os.path.basename(file_path) }
```

5) Backend: the `transcribe(...)` pipeline (split/compress + provider handler)
- File: `backend/open_webui/routers/audio.py`
- Function: `transcribe(request, file_path, metadata)`
- Lines: 798–848
- Short description:
    - Optionally converts/compresses audio, splits it if larger than configured size.
    - For each chunk, calls `transcription_handler(...)` (defined earlier in the same file; selects provider like Whisper/Azure based on configuration) and aggregates results.
    - Returns `{ "text": "...joined transcript..." }`.

```py
def transcribe(request: Request, file_path: str, metadata: Optional[dict] = None):
  if is_audio_conversion_required(file_path): file_path = convert_audio_to_mp3(file_path)
  try: file_path = compress_audio(file_path) except: ...
  chunk_paths = split_audio(file_path, MAX_FILE_SIZE)
  results = [transcription_handler(request, chunk, metadata) for chunk in chunk_paths]
  return { "text": " ".join([r["text"] for r in results]) }
```

6) Back to the client: append transcript to the prompt and optionally send
- File: `src/lib/components/chat/MessageInput.svelte`
- Lines: 688–700 in the `<VoiceRecording onConfirm={...} />` block
- Short description:
    - Receives `{ text, filename }` from the server response via `onConfirm(res)`.
    - Appends `text` to the chat `prompt` and stops recording.
    - If `$settings.speechAutoSend` is true, it dispatches `submit` with the new prompt.

```svelte
onConfirm={async (data) => {
  const { text, filename } = data;
  prompt = `${prompt}${text} `;   // <- transcript becomes prompt text here
  recording = false;
  if ($settings?.speechAutoSend ?? false) {
    dispatch('submit', prompt);
  }
}}
```

---

### Summary of the call graph from your anchor point (MessageInput.svelte:1480)
- `MessageInput.svelte:1480` sets `recording = true` (fallback path)
    - Renders `<VoiceRecording />` (MessageInput.svelte:679)
        - `VoiceRecording.svelte` captures mic → on stop → `onStopHandler`
            - If STT engine is not `web`: `transcribeAudio(token, file, language)` (client)
                - `src/lib/apis/audio/index.ts:transcribeAudio` → `POST` `${AUDIO_API_BASE_URL}/transcriptions`
                    - `backend/open_webui/routers/audio.py:/transcriptions` saves file → calls `transcribe(...)`
                        - `audio.py:transcribe(...)` split/compress → `transcription_handler(...)` per chunk (provider) → returns `{ text }`
                    - Response `{ text, filename }` back to client
            - `VoiceRecording.svelte` calls `onConfirm(res)` with the server response
        - `MessageInput.svelte:onConfirm` appends `data.text` to `prompt` and optionally submits

- If instead `LIVEKIT_ENABLED` was true at click time:
    - `startLivekitAsr()` connects to LiveKit and streams mic
    - Transcription events append text directly to `prompt` (no upload step)

---

### Related files you might also check
- `src/lib/components/chat/MessageInput/CallOverlay.svelte` — a similar pattern for call/voice mode uses `transcribeAudio` with recorded blobs.
- `backend/open_webui/routers/livekitapi.py` — endpoints involved in the LiveKit token/transcription configuration.

If you want, I can extract and list the exact provider selection code in `audio.py` (the `transcription_handler` and its branches like Whisper/Azure) to show the full server‑side path for your current config.