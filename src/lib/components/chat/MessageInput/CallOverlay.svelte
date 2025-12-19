<script lang="ts">
    import { config, models, settings, showCallOverlay, TTSWorker } from '$lib/stores';
    import { onMount, tick, getContext, onDestroy, createEventDispatcher } from 'svelte';

    const dispatch = createEventDispatcher();

    import { blobToFile } from '$lib/utils';
    import { generateEmoji } from '$lib/apis';
    import { synthesizeOpenAISpeech, transcribeAudio } from '$lib/apis/audio';

    import { toast } from 'svelte-sonner';

    import Tooltip from '$lib/components/common/Tooltip.svelte';
    import VideoInputMenu from './CallOverlay/VideoInputMenu.svelte';
    import { KokoroWorker } from '$lib/workers/KokoroWorker';
    import { ConnectionState } from 'livekit-client';

    const i18n = getContext('i18n');

    export let eventTarget: EventTarget;
    export let submitPrompt: Function;
    export let stopResponse: Function;
    export let files;
    export let chatId;
    export let modelId;

    export let lkConnectionState: ConnectionState | null = ConnectionState.Disconnected;
    export let lkMicLevel: number;

    let wakeLock = null;

    let model = null;

    let loading = false;
    let confirmed = false;
    let assistantSpeaking = false;

    let emoji = null;
    let camera = false;
    let cameraStream = null;

    let chatStreaming = false;
    let rmsLevel = 0;
    let hasStartedSpeaking = false;
    let mediaRecorder;
    let audioStream = null;
    let audioChunks = [];

    let videoInputDevices = [];
    let selectedVideoInputDeviceId = null;

    let userPrompt = '';
    let assistantResponse = '';
    let lkAutoSubmitTimeout = null;
    let lkThinking = false;
    // let lkAudioLevel = 0;

    // Sound wave animation for assistant speaking
    let waveHeights = Array(7).fill(25);
    let waveAnimationInterval = null;

    const LIVEKIT_ENABLED = $config.audio.stt.engine === 'livekit';
    const LIVEKIT_AUTO_SUBMIT_DELAY = 500;
    const AUDIO_BARS_COUNT = 12;
    const AUDIO_BARS = Array(AUDIO_BARS_COUNT)
        .fill(0)
        .map((_, i) => i); // Cache array

    // Reactive: Animate wave heights when assistant is speaking
    $: if (assistantSpeaking) {
        // Start animation
        if (!waveAnimationInterval) {
            waveAnimationInterval = setInterval(() => {
                waveHeights = waveHeights.map(() => Math.random() * 35 + 10); // Random height between 10-45px, avg ~27.5px
            }, 100); // Update every 100ms for smooth animation
        }
    } else {
        // Stop animation and reset to default heights
        if (waveAnimationInterval) {
            clearInterval(waveAnimationInterval);
            waveAnimationInterval = null;
        }
        waveHeights = Array(7).fill(25);
    }

    // Reactive: Start/stop visualizer based on LiveKit connection and state
    $: if (LIVEKIT_ENABLED) {
    }

    const getVideoInputDevices = async () => {
        const devices = await navigator.mediaDevices.enumerateDevices();
        videoInputDevices = devices.filter((device) => device.kind === 'videoinput');

        if (!!navigator.mediaDevices.getDisplayMedia) {
            videoInputDevices = [
                ...videoInputDevices,
                {
                    deviceId: 'screen',
                    label: 'Screen Share'
                }
            ];
        }

        console.log(videoInputDevices);
        if (selectedVideoInputDeviceId === null && videoInputDevices.length > 0) {
            selectedVideoInputDeviceId = videoInputDevices[0].deviceId;
        }
    };

    const startCamera = async () => {
        await getVideoInputDevices();

        if (cameraStream === null) {
            camera = true;
            await tick();
            try {
                await startVideoStream();
            } catch (err) {
                console.error('Error accessing webcam: ', err);
            }
        }
    };

    const startVideoStream = async () => {
        const video = document.getElementById('camera-feed');
        if (video) {
            if (selectedVideoInputDeviceId === 'screen') {
                cameraStream = await navigator.mediaDevices.getDisplayMedia({
                    video: {
                        cursor: 'always'
                    },
                    audio: false
                });
            } else {
                cameraStream = await navigator.mediaDevices.getUserMedia({
                    video: {
                        deviceId: selectedVideoInputDeviceId ? { exact: selectedVideoInputDeviceId } : undefined
                    }
                });
            }

            if (cameraStream) {
                await getVideoInputDevices();
                video.srcObject = cameraStream;
                await video.play();
            }
        }
    };

    const stopVideoStream = async () => {
        if (cameraStream) {
            const tracks = cameraStream.getTracks();
            tracks.forEach((track) => track.stop());
        }

        cameraStream = null;
    };

    const takeScreenshot = () => {
        const video = document.getElementById('camera-feed');
        const canvas = document.getElementById('camera-canvas');

        if (!canvas) {
            return;
        }

        const context = canvas.getContext('2d');

        // Make the canvas match the video dimensions
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        // Draw the image from the video onto the canvas
        context.drawImage(video, 0, 0, video.videoWidth, video.videoHeight);

        // Convert the canvas to a data base64 URL and console log it
        const dataURL = canvas.toDataURL('image/png');
        console.log(dataURL);

        return dataURL;
    };

    const stopCamera = async () => {
        await stopVideoStream();
        camera = false;
    };

    const MIN_DECIBELS = -55;

    const transcribeHandler = async (audioBlob) => {
        // Create a blob from the audio chunks

        await tick();
        const file = blobToFile(audioBlob, 'recording.wav');

        const res = await transcribeAudio(
            localStorage.token,
            file,
            $settings?.audio?.stt?.language
        ).catch((error) => {
            toast.error(`${error}`);
            return null;
        });

        if (res) {
            console.log(res.text);

            if (res.text !== '') {
                const _responses = await submitPrompt(res.text, { _raw: true });
                console.log(_responses);
            }
        }
    };

    const stopRecordingCallback = async (_continue = true) => {
        if ($showCallOverlay) {
            console.log('%c%s', 'color: red; font-size: 20px;', '🚨 stopRecordingCallback 🚨');

            // deep copy the audioChunks array
            const _audioChunks = audioChunks.slice(0);

            audioChunks = [];
            mediaRecorder = false;

            if (_continue) {
                startRecording();
            }

            if (confirmed) {
                loading = true;
                emoji = null;

                if (cameraStream) {
                    const imageUrl = takeScreenshot();

                    files = [
                        {
                            type: 'image',
                            url: imageUrl
                        }
                    ];
                }

                const audioBlob = new Blob(_audioChunks, { type: 'audio/wav' });
                await transcribeHandler(audioBlob);

                confirmed = false;
                loading = false;
            }
        } else {
            audioChunks = [];
            mediaRecorder = false;

            if (audioStream) {
                const tracks = audioStream.getTracks();
                tracks.forEach((track) => track.stop());
            }
            audioStream = null;
        }
    };

    const startRecording = async () => {
        if ($showCallOverlay) {
            if (!audioStream) {
                audioStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
            }
            mediaRecorder = new MediaRecorder(audioStream);

            mediaRecorder.onstart = () => {
                console.log('Recording started');
                audioChunks = [];
            };

            mediaRecorder.ondataavailable = (event) => {
                if (hasStartedSpeaking) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = (e) => {
                console.log('Recording stopped', audioStream, e);
                stopRecordingCallback();
            };

            analyseAudio(audioStream);
        }
    };

    const stopAudioStream = async () => {
        try {
            if (mediaRecorder) {
                mediaRecorder.stop();
            }
        } catch (error) {
            console.log('Error stopping audio stream:', error);
        }

        if (!audioStream) return;

        audioStream.getAudioTracks().forEach(function (track) {
            track.stop();
        });

        audioStream = null;
    };

    // Function to calculate the RMS level from time domain data
    const calculateRMS = (data: Uint8Array) => {
        let sumSquares = 0;
        for (let i = 0; i < data.length; i++) {
            const normalizedValue = (data[i] - 128) / 128; // Normalize the data
            sumSquares += normalizedValue * normalizedValue;
        }
        return Math.sqrt(sumSquares / data.length);
    };

    const analyseAudio = (stream) => {
        const audioContext = new AudioContext();
        const audioStreamSource = audioContext.createMediaStreamSource(stream);

        const analyser = audioContext.createAnalyser();
        analyser.minDecibels = MIN_DECIBELS;
        audioStreamSource.connect(analyser);

        const bufferLength = analyser.frequencyBinCount;

        const domainData = new Uint8Array(bufferLength);
        const timeDomainData = new Uint8Array(analyser.fftSize);

        let lastSoundTime = Date.now();
        hasStartedSpeaking = false;

        console.log('🔊 Sound detection started', lastSoundTime, hasStartedSpeaking);

        const detectSound = () => {
            const processFrame = () => {
                if (!mediaRecorder || !$showCallOverlay) {
                    return;
                }

                if (assistantSpeaking && !($settings?.voiceInterruption ?? false)) {
                    // Mute the audio if the assistant is speaking
                    analyser.maxDecibels = 0;
                    analyser.minDecibels = -1;
                } else {
                    analyser.minDecibels = MIN_DECIBELS;
                    analyser.maxDecibels = -30;
                }

                analyser.getByteTimeDomainData(timeDomainData);
                analyser.getByteFrequencyData(domainData);

                // Calculate RMS level from time domain data
                rmsLevel = calculateRMS(timeDomainData);

                // Check if initial speech/noise has started
                const hasSound = domainData.some((value) => value > 0);
                if (hasSound) {
                    // BIG RED TEXT
                    console.log('%c%s', 'color: red; font-size: 20px;', '🔊 Sound detected');
                    if (mediaRecorder && mediaRecorder.state !== 'recording') {
                        mediaRecorder.start();
                    }

                    if (!hasStartedSpeaking) {
                        hasStartedSpeaking = true;
                        stopAllAudio();
                    }

                    lastSoundTime = Date.now();
                }

                // Start silence detection only after initial speech/noise has been detected
                if (hasStartedSpeaking) {
                    if (Date.now() - lastSoundTime > 2000) {
                        confirmed = true;

                        if (mediaRecorder) {
                            console.log('%c%s', 'color: red; font-size: 20px;', '🔇 Silence detected');
                            mediaRecorder.stop();
                            return;
                        }
                    }
                }

                window.requestAnimationFrame(processFrame);
            };

            window.requestAnimationFrame(processFrame);
        };

        detectSound();
    };

    let finishedMessages = {};
    let currentMessageId = null;
    let currentUtterance = null;

    const speakSpeechSynthesisHandler = (content) => {
        if ($showCallOverlay) {
            return new Promise((resolve) => {
                let voices = [];
                const getVoicesLoop = setInterval(async () => {
                    voices = await speechSynthesis.getVoices();
                    if (voices.length > 0) {
                        clearInterval(getVoicesLoop);

                        const voice =
                            voices
                                ?.filter(
                                    (v) => v.voiceURI === ($settings?.audio?.tts?.voice ?? $config?.audio?.tts?.voice)
                                )
                                ?.at(0) ?? undefined;

                        currentUtterance = new SpeechSynthesisUtterance(content);
                        currentUtterance.rate = $settings.audio?.tts?.playbackRate ?? 1;

                        if (voice) {
                            currentUtterance.voice = voice;
                        }

                        speechSynthesis.speak(currentUtterance);
                        currentUtterance.onend = async (e) => {
                            await new Promise((r) => setTimeout(r, 200));
                            resolve(e);
                        };
                    }
                }, 100);
            });
        } else {
            return Promise.resolve();
        }
    };

    const playAudio = (audio) => {
        if ($showCallOverlay) {
            return new Promise((resolve) => {
                const audioElement = document.getElementById('audioElement') as HTMLAudioElement;

                if (audioElement) {
                    audioElement.src = audio.src;
                    audioElement.muted = true;
                    audioElement.playbackRate = $settings.audio?.tts?.playbackRate ?? 1;

                    audioElement
                        .play()
                        .then(() => {
                            audioElement.muted = false;
                        })
                        .catch((error) => {
                            console.error(error);
                        });

                    audioElement.onended = async (e) => {
                        await new Promise((r) => setTimeout(r, 100));
                        resolve(e);
                    };
                }
            });
        } else {
            return Promise.resolve();
        }
    };

    const stopAllAudio = async () => {
        assistantSpeaking = false;
        dispatch('stopAudioStream');

        if (chatStreaming) {
            stopResponse();
        }

        if (currentUtterance) {
            speechSynthesis.cancel();
            currentUtterance = null;
        }

        const audioElement = document.getElementById('audioElement');
        if (audioElement) {
            audioElement.muted = true;
            audioElement.pause();
            audioElement.currentTime = 0;
        }
    };

    let audioAbortController = new AbortController();

    // Audio cache map where key is the content and value is the Audio object.
    const audioCache = new Map();
    const emojiCache = new Map();

    const fetchAudio = async (content) => {
        if (!audioCache.has(content)) {
            try {
                // Set the emoji for the content if needed
                if ($settings?.showEmojiInCall ?? false) {
                    const emoji = await generateEmoji(localStorage.token, modelId, content, chatId);
                    if (emoji) {
                        emojiCache.set(content, emoji);
                    }
                }

                if ($settings.audio?.tts?.engine === 'browser-kokoro') {
                    const blob = await $TTSWorker
                        .generate({
                            text: content,
                            voice: $settings?.audio?.tts?.voice ?? $config?.audio?.tts?.voice
                        })
                        .catch((error) => {
                            console.error(error);
                            toast.error(`${error}`);
                        });

                    if (blob) {
                        audioCache.set(content, new Audio(blob));
                    }
                } else if ($config.audio.tts.engine !== '') {
                    const res = await synthesizeOpenAISpeech(
                        localStorage.token,
                        $settings?.audio?.tts?.defaultVoice === $config.audio.tts.voice
                            ? ($settings?.audio?.tts?.voice ?? $config?.audio?.tts?.voice)
                            : $config?.audio?.tts?.voice,
                        content
                    ).catch((error) => {
                        console.error(error);
                        return null;
                    });

                    if (res) {
                        const blob = await res.blob();
                        const blobUrl = URL.createObjectURL(blob);
                        audioCache.set(content, new Audio(blobUrl));
                    }
                } else {
                    audioCache.set(content, true);
                }
            } catch (error) {
                console.error('Error synthesizing speech:', error);
            }
        }

        return audioCache.get(content);
    };

    let messages = {};

    const monitorAndPlayAudio = async (id, signal) => {
        while (!signal.aborted) {
            if (messages[id] && messages[id].length > 0) {
                // Retrieve the next content string from the queue
                const content = messages[id].shift(); // Dequeues the content for playing

                if (audioCache.has(content)) {
                    // If content is available in the cache, play it

                    // Set the emoji for the content if available
                    if (($settings?.showEmojiInCall ?? false) && emojiCache.has(content)) {
                        emoji = emojiCache.get(content);
                    } else {
                        emoji = null;
                    }

                    if ($config.audio.tts.engine !== '') {
                        try {
                            console.log(
                                '%c%s',
                                'color: red; font-size: 20px;',
                                `Playing audio for content: ${content}`,
                                `Audio agent: ${$config.audio.tts.engine}`
                            );
                            assistantSpeaking = true;
                            lkThinking = false;

                            const audio = audioCache.get(content);
                            await playAudio(audio); // Here ensure that playAudio is indeed correct method to execute
                            console.log(`Played audio for content: ${content}`);
                            await new Promise((resolve) => setTimeout(resolve, 200)); // Wait before retrying to reduce tight loop
                        } catch (error) {
                            console.error('Error playing audio:', error);
                        }
                    } else {
                        await speakSpeechSynthesisHandler(content);
                    }
                } else {
                    // If not available in the cache, push it back to the queue and delay
                    messages[id].unshift(content); // Re-queue the content at the start
                    console.log(`Audio for "${content}" not yet available in the cache, re-queued...`);
                    await new Promise((resolve) => setTimeout(resolve, 200)); // Wait before retrying to reduce tight loop
                }
            } else if (finishedMessages[id] && messages[id] && messages[id].length === 0) {
                // If the message is finished and there are no more messages to process, break the loop
                assistantSpeaking = false;
                break;
            } else {
                // No messages to process, sleep for a bit
                await new Promise((resolve) => setTimeout(resolve, 200));
            }
        }
        console.log(`Audio monitoring and playing stopped for message ID ${id}`);
    };

    const chatStartHandler = async (e) => {
        const { id } = e.detail;

        chatStreaming = true;
        assistantResponse = '';

        if (currentMessageId !== id) {
            console.log(`Received chat start event for message ID ${id}`);

            currentMessageId = id;
            if (audioAbortController) {
                audioAbortController.abort();
            }
            audioAbortController = new AbortController();

            // assistantSpeaking = true;
            // Start monitoring and playing audio for the message ID
            monitorAndPlayAudio(id, audioAbortController.signal);
        }
    };

    const chatEventHandler = async (e) => {
        const { id, content } = e.detail;
        // "id" here is message id
        // if "id" is not the same as "currentMessageId" then do not process
        // "content" here is a sentence from the assistant,
        // there will be many sentences for the same "id"

        // Initialize currentMessageId if not set (first event) or if new message
        if (currentMessageId === null || currentMessageId !== id) {
            currentMessageId = id;
            assistantResponse = '';
        }

        try {
            if (messages[id] === undefined) {
                messages[id] = [content];
            } else {
                messages[id].push(content);
            }

            console.log(content);

            fetchAudio(content);
        } catch (error) {
            console.error('Failed to fetch or play audio:', error);
        }
    };

    const chatFinishHandler = async (e) => {
        const { id, content } = e.detail;
        // "content" here is the entire message from the assistant
        finishedMessages[id] = true;
        assistantResponse = content;

        chatStreaming = false;
    };

    const transcriptReadyHandler = async (e) => {
        // Ignore transcript if prompt already sent, but no answer from chat received.
        if (lkThinking) return;

        userPrompt = e.detail.text;

        console.log('[CallOverlay] 🎤 TRANSCRIPT READY:', userPrompt);

        // Interrupt assistant if it's currently speaking
        if (assistantSpeaking) {
            console.log('[CallOverlay] User started speaking - interrupting assistant');
            await stopAllAudio();
        }

        // Clear any existing auto-submit timeout
        if (lkAutoSubmitTimeout) {
            clearTimeout(lkAutoSubmitTimeout);
            lkAutoSubmitTimeout = null;
        }

        // Set new timeout for auto-submit after delay
        lkAutoSubmitTimeout = setTimeout(() => {
            console.log('[CallOverlay] 📤 Auto-submitting prompt');
            assistantResponse = '';
            submitPrompt(userPrompt);
            lkThinking = true;
        }, LIVEKIT_AUTO_SUBMIT_DELAY);
    };

    const ttsBeginHandler = () => {
        lkThinking = false;
        assistantSpeaking = true;
    }

    const ttsCompleteHandler = () => {
        // Set 1 sec timeout for buffered audio to finish
        setTimeout(() => (assistantSpeaking = false), 1000);
    }

    onMount(async () => {
        const setWakeLock = async () => {
            try {
                wakeLock = await navigator.wakeLock.request('screen');
            } catch (err) {
                // The Wake Lock request has failed - usually system related, such as battery.
                console.log(err);
            }

            if (wakeLock) {
                // Add a listener to release the wake lock when the page is unloaded
                wakeLock.addEventListener('release', () => {
                    // the wake lock has been released
                    console.log('Wake Lock released');
                });
            }
        };

        if ('wakeLock' in navigator) {
            await setWakeLock();

            document.addEventListener('visibilitychange', async () => {
                // Re-request the wake lock if the document becomes visible
                if (wakeLock !== null && document.visibilityState === 'visible') {
                    await setWakeLock();
                }
            });
        }

        model = $models.find((m) => m.id === modelId);

        if (LIVEKIT_ENABLED) {
            // Start LiveKit automatically when overlay opens
            console.log('[CallOverlay] Starting LiveKit ASR automatically');
            dispatch('startLivekit');

            // Listen for transcript ready events
            eventTarget.addEventListener('transcript:ready', transcriptReadyHandler);
            eventTarget.addEventListener('tts:start', ttsBeginHandler);
            eventTarget.addEventListener('tts:complete', ttsCompleteHandler);
        } else {
            await startRecording();
            // Use default audio processing when LiveKit is disabled
            eventTarget.addEventListener('chat:start', chatStartHandler);
            eventTarget.addEventListener('chat', chatEventHandler);
        }

        eventTarget.addEventListener('chat:finish', chatFinishHandler);

        return async () => {
            await stopAllAudio();
            await stopAudioStream();

            if (LIVEKIT_ENABLED) {
                eventTarget.removeEventListener('transcript:ready', transcriptReadyHandler);
                eventTarget.removeEventListener('tts:start', ttsBeginHandler);
                eventTarget.removeEventListener('tts:complete', ttsCompleteHandler);

                if (lkAutoSubmitTimeout) {
                    clearTimeout(lkAutoSubmitTimeout);
                    lkAutoSubmitTimeout = null;
                }

                dispatch('stopLivekit');
            } else {
                eventTarget.removeEventListener('chat:start', chatStartHandler);
            }

            eventTarget.removeEventListener('chat', chatEventHandler);
            eventTarget.removeEventListener('chat:finish', chatFinishHandler);

            audioAbortController.abort();
            await tick();

            await stopAllAudio();

            await stopRecordingCallback(false);
            await stopCamera();
        };
    });

    onDestroy(async () => {
        // Clean up wave animation interval
        if (waveAnimationInterval) {
            clearInterval(waveAnimationInterval);
            waveAnimationInterval = null;
        }

        await stopAllAudio();
        await stopRecordingCallback(false);
        await stopCamera();

        await stopAudioStream();

        if (LIVEKIT_ENABLED) {
            eventTarget.removeEventListener('transcript:ready', transcriptReadyHandler);
            eventTarget.removeEventListener('tts:start', ttsBeginHandler);
            eventTarget.removeEventListener('tts:complete', ttsCompleteHandler);

            if (lkAutoSubmitTimeout) {
                clearTimeout(lkAutoSubmitTimeout);
                lkAutoSubmitTimeout = null;
            }
            stopResponse();
            dispatch('stopLivekit');
        } else {
            eventTarget.removeEventListener('chat:start', chatStartHandler);
        }

        eventTarget.removeEventListener('chat', chatEventHandler);
        eventTarget.removeEventListener('chat:finish', chatFinishHandler);

        audioAbortController.abort();

        await tick();

        await stopAllAudio();
    });
</script>

{#if $showCallOverlay}
    <div class="max-w-lg w-full h-full max-h-[100dvh] flex flex-col justify-between p-3 md:p-6">
        <!-- Close button -->
        <div class="text-right">
            <button
                    class=" p-3 rounded-full"
                    on:click={async () => {
					await stopAudioStream();
					await stopVideoStream();

					console.log(audioStream);
					console.log(cameraStream);

					showCallOverlay.set(false);
					dispatch('close');
                    dispatch('stopLivekit')
				}}
                    type="button"
            >
                <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                        stroke-width="2"
                        stroke="currentColor"
                        fill="none"
                        class="w-5 h-5"
                >
                    <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>

        {#if camera}
            <button
                    type="button"
                    class="flex justify-center items-center w-full h-20 min-h-20"
                    on:click={() => {
					if (assistantSpeaking) {
						stopAllAudio();
					}
				}}
            >
                {#if emoji}
                    <div
                            class="  transition-all rounded-full"
                            style="font-size:{rmsLevel * 100 > 4
							? '4.5'
							: rmsLevel * 100 > 2
								? '4.25'
								: rmsLevel * 100 > 1
									? '3.75'
									: '3.5'}rem;width: 100%; text-align:center;"
                    >
                        {emoji}
                    </div>
                {:else if loading || assistantSpeaking}
                    <svg
                            class="size-12 text-gray-900 dark:text-gray-400"
                            viewBox="0 0 24 24"
                            fill="currentColor"
                            xmlns="http://www.w3.org/2000/svg"
                    ><style>
                        .spinner_qM83 {
                            animation: spinner_8HQG 1.05s infinite;
                        }
                        .spinner_oXPr {
                            animation-delay: 0.1s;
                        }
                        .spinner_ZTLf {
                            animation-delay: 0.2s;
                        }
                        @keyframes spinner_8HQG {
                            0%,
                            57.14% {
                                animation-timing-function: cubic-bezier(0.33, 0.66, 0.66, 1);
                                transform: translate(0);
                            }
                            28.57% {
                                animation-timing-function: cubic-bezier(0.33, 0, 0.66, 0.33);
                                transform: translateY(-6px);
                            }
                            100% {
                                transform: translate(0);
                            }
                        }
                    </style><circle class="spinner_qM83" cx="4" cy="12" r="3" /><circle
                            class="spinner_qM83 spinner_oXPr"
                            cx="12"
                            cy="12"
                            r="3"
                    /><circle class="spinner_qM83 spinner_ZTLf" cx="20" cy="12" r="3" /></svg
                    >
                {:else}
                    <div
                            class=" {rmsLevel * 100 > 4
							? ' size-[4.5rem]'
							: rmsLevel * 100 > 2
								? ' size-16'
								: rmsLevel * 100 > 1
									? 'size-14'
									: 'size-12'}  transition-all rounded-full {(model?.info?.meta
							?.profile_image_url ?? '/static/favicon.png') !== '/static/favicon.png'
							? ' bg-cover bg-center bg-no-repeat'
							: 'bg-teal-500 dark:bg-white'}  bg-teal-500 dark:bg-white"
                            style={(model?.info?.meta?.profile_image_url ?? '/static/favicon.png') !==
						'/static/favicon.png'
							? `background-image: url('${model?.info?.meta?.profile_image_url}');`
							: ''}
                    />
                {/if}
                <!-- navbar -->
            </button>
        {/if}

        <div class="flex justify-center items-center flex-1 min-h-0 w-full overflow-hidden">
            {#if !camera}
                <button
                        class="w-full h-full flex flex-col items-center justify-center outline-none"
                        type="button"
                        on:click={() => {
						if (assistantSpeaking) {
							stopAllAudio();
						}
					}}
                >
                    {#if LIVEKIT_ENABLED}
                        <div id="callOverlayMain" class="flex flex-col h-full w-full min-h-0 overflow-hidden">
                            <div class="flex-[1] flex items-center justify-center">
                                {#if lkThinking}
                                    <svg width="100%"
                                         height="100%"
                                         viewBox="0 0 284 284"
                                         xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
                                         xml:space="preserve" xmlns:serif="http://www.serif.com/"
                                         fill="currentColor"
                                         class="w-25 h-25 translate-y-[0.5px] text-gray-500 animate-breath"
                                    >
                                        <g transform="matrix(0.554687,0,0,0.554687,141.802774,142.01163)">
                                            <g transform="matrix(1,0,0,1,-256,-256)">
                                                <g transform="matrix(21.333333,0,0,21.333333,0,0)">
                                                    <path d="M3,22.5C3,23.328 2.328,24 1.5,24C0.672,24 0,23.328 0,22.5C0,21.672 0.672,21 1.5,21C2.328,21 3,21.672 3,22.5ZM6,17C4.895,17 4,17.895 4,19C4,20.105 4.895,21 6,21C7.105,21 8,20.105 8,19C8,17.895 7.105,17 6,17ZM15.845,15.58C16.544,15.859 17.267,16 18,16C21.309,16 24,13.309 24,10C24,7.267 22.177,4.931 19.584,4.228C18.646,1.71 16.228,0 13.5,0C11.621,0 9.848,0.819 8.62,2.223C8.096,2.076 7.553,2 7,2C3.691,2 1,4.691 1,8C1,11.242 3.585,13.892 6.802,13.997C7.864,15.842 9.834,17 12,17C13.426,17 14.767,16.501 15.845,15.58Z" style="fill-rule:nonzero;"/>
                                                </g>
                                            </g>
                                        </g>
                                        <path d="M177.833,161.489C177.833,161.489 157.563,159.53 140.518,159.53L106.89,159.53L106.89,153.425C108.342,153.318 110.486,153.166 113.311,152.958C116.136,152.75 118.088,152.434 119.169,152.018C121.161,151.236 122.522,150.206 123.248,148.923C123.974,147.64 124.34,146.014 124.34,144.027L124.34,80.383C124.34,78.61 123.991,77.04 123.288,75.684C122.584,74.328 121.217,73.231 119.169,72.398C117.874,71.875 115.967,71.34 113.434,70.794C110.902,70.248 108.724,69.866 106.896,69.657L106.896,63.552C106.896,63.552 122.809,62.832 126.062,63.552C130.097,64.447 132.888,66.011 134.345,73.332C134.525,73.22 132.201,77.986 131.183,80.771C134.216,76.033 136.692,71.014 150.316,66.827C156.612,64.891 171.046,63.558 171.046,63.558L171.046,67.71C169.414,67.868 160.94,69.854 158.886,70.969C156.939,72.027 155.206,73.281 154.497,74.716C153.788,76.151 153.439,77.783 153.439,79.612C153.439,79.612 153.501,105.981 153.439,108.064C153.298,112.644 154.806,111.952 154.806,111.952L155.183,115.086C155.183,115.086 153.214,115.311 153.439,126.763C153.472,128.479 153.439,143.178 153.439,143.178C153.439,145.057 153.776,146.678 154.542,147.995C159.499,156.531 163.956,151.827 178.778,158.416L177.838,161.5L177.833,161.489Z" style="fill:white;"/>
                                        <g transform="matrix(0.562726,0,0,0.562726,75.940028,25.601669)">
                                            <path d="M131.54,27.19C131.54,27.19 122.47,14.37 108.53,22.21C90,32.64 101.25,60.57 105.87,79.95C124.05,66.84 150.06,68.31 161.56,47.46C172.23,28.12 148.38,13.33 131.54,27.19Z" style="fill:white;fill-rule:nonzero;"/>
                                        </g>
                                        <g transform="matrix(0.562726,0,0,0.562726,75.940028,25.601669)">
                                            <path d="M142.07,156.4C155.82,147.12 152.6,133.99 165.29,122.97C179.38,110.73 191.13,108.31 226.57,111.02C206.92,119.57 209.54,127.58 194.06,141.42C175.37,158.14 158.61,158.57 142.86,156.59C154.26,151.83 175.34,113.18 223.51,111.65C170.12,111.64 154.7,152.28 142.61,156.54C142.24,156.46 142.05,156.4 142.05,156.4L142.07,156.4Z" style="fill:white;fill-rule:nonzero;"/>
                                        </g>
                                        <g transform="matrix(0.562726,0,0,0.562726,75.940028,25.601669)">
                                            <path d="M171.1,71.37C179.25,65.94 176.68,55.42 186.78,47.77C198.57,38.84 219.67,41.08 237.7,41.27C225.02,44.9 218.09,49.11 206.79,60.97C192.67,75.8 178.95,74.01 171.42,71.64C182.64,69.66 189.34,41.06 235.5,41.44C185.5,39.51 182.04,70.21 171.27,71.45C171.15,71.46 171.1,71.37 171.1,71.37Z" style="fill:white;fill-rule:nonzero;"/>
                                        </g>
                                        </svg>
                                {:else if assistantSpeaking}
                                    <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            viewBox="0 0 65 50"
                                            class="w-25 h-25"
                                    >
                                        {#each waveHeights as height, i}
                                            <rect
                                                    x={i * 8 + 10}
                                                    y={25 - height / 2}
                                                    width="3"
                                                    height={height}
                                                    fill="currentColor"
                                                    class="text-gray-500 transition-all duration-100"
                                            />
                                        {/each}
                                    </svg>
                                {:else if lkConnectionState == ConnectionState.Connecting}
                                    <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            viewBox="0 0 24 24"
                                            fill="currentColor"
                                            class="w-25 h-25 translate-y-[0.5px] text-amber-500"
                                    >
                                        <path
                                                d="m12.707,12.707l-2.293,2.293-1.414-1.414,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0l-2.293,2.293-1.879-1.879c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l.352.352-1.134,1.135c-1.77,1.769-1.982,4.515-.638,6.519l-2.58,2.58c-.391.391-.391,1.023,0,1.414.195.195.451.293.707.293s.512-.098.707-.293l2.58-2.58c.865.58,1.868.871,2.871.871,1.321,0,2.642-.503,3.647-1.509l1.135-1.134.352.352c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-1.879-1.879,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0ZM23.707.293c-.391-.391-1.023-.391-1.414,0l-2.58,2.58c-2.004-1.344-4.749-1.132-6.519.638l-1.135,1.135-.353-.353c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l8,8c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-.353-.353,1.135-1.135c1.77-1.769,1.982-4.515.638-6.519l2.58-2.58c.391-.391.391-1.023,0-1.414Z"
                                        />
                                    </svg>
                                {:else if lkConnectionState == ConnectionState.Connected}
                                    <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            viewBox="0 0 20 20"
                                            fill="currentColor"
                                            class="w-25 h-25 translate-y-[0.5px] text-teal-500"
                                    >
                                        <path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z"></path>
                                        <path
                                                d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z"
                                        ></path>
                                    </svg>
                                {:else if lkConnectionState == ConnectionState.Disconnected}
                                    <svg
                                            xmlns="http://www.w3.org/2000/svg"
                                            viewBox="0 0 24 24"
                                            fill="currentColor"
                                            class="w-25 h-25 translate-y-[0.5px] text-gray-500"
                                    >
                                        <path
                                                d="m12.707,12.707l-2.293,2.293-1.414-1.414,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0l-2.293,2.293-1.879-1.879c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l.352.352-1.134,1.135c-1.77,1.769-1.982,4.515-.638,6.519l-2.58,2.58c-.391.391-.391,1.023,0,1.414.195.195.451.293.707.293s.512-.098.707-.293l2.58-2.58c.865.58,1.868.871,2.871.871,1.321,0,2.642-.503,3.647-1.509l1.135-1.134.352.352c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-1.879-1.879,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0ZM23.707.293c-.391-.391-1.023-.391-1.414,0l-2.58,2.58c-2.004-1.344-4.749-1.132-6.519.638l-1.135,1.135-.353-.353c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l8,8c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-.353-.353,1.135-1.135c1.77-1.769,1.982-4.515.638-6.519l2.58-2.58c.391-.391.391-1.023,0-1.414Z"
                                        />
                                    </svg>
                                {/if}
                            </div>
                            <div id="callOverlayChatHistory" class="flex-[3] min-h-0 w-full text-left overflow-hidden flex flex-col">
                                {#if userPrompt}
                                    <div class="flex justify-end mb-3 shrink-0">
                                        <div class="bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-lg px-2 py-2 max-w-[85%] text-sm">
                                            {userPrompt}
                                        </div>
                                    </div>
                                {/if}
                                {#if assistantResponse}
                                    <div class="flex-1 min-h-0 overflow-y-auto touch-pan-y overscroll-contain mb-2">
                                        <div class="text-sm font-bold mb-2 py-1">
                                            {model.name}
                                        </div>
                                        <div class="markdown-prose-sm">
                                            {assistantResponse}
                                        </div>
                                    </div>
                                {/if}
                            </div>
                        </div>
                    {:else if emoji}
                        <div
                                class="  transition-all rounded-full"
                                style="font-size:{rmsLevel * 100 > 4
								? '13'
								: rmsLevel * 100 > 2
									? '12'
									: rmsLevel * 100 > 1
										? '11.5'
										: '11'}rem;width:100%;text-align:center;"
                        >
                            {emoji}
                        </div>
                    {:else if loading || assistantSpeaking}
                        <svg
                                class="size-44 text-gray-900 dark:text-gray-400"
                                viewBox="0 0 24 24"
                                fill="currentColor"
                                xmlns="http://www.w3.org/2000/svg"
                        ><style>
                            .spinner_qM83 {
                                animation: spinner_8HQG 1.05s infinite;
                            }
                            .spinner_oXPr {
                                animation-delay: 0.1s;
                            }
                            .spinner_ZTLf {
                                animation-delay: 0.2s;
                            }
                            @keyframes spinner_8HQG {
                                0%,
                                57.14% {
                                    animation-timing-function: cubic-bezier(0.33, 0.66, 0.66, 1);
                                    transform: translate(0);
                                }
                                28.57% {
                                    animation-timing-function: cubic-bezier(0.33, 0, 0.66, 0.33);
                                    transform: translateY(-6px);
                                }
                                100% {
                                    transform: translate(0);
                                }
                            }
                        </style><circle class="spinner_qM83" cx="4" cy="12" r="3" /><circle
                                class="spinner_qM83 spinner_oXPr"
                                cx="12"
                                cy="12"
                                r="3"
                        /><circle class="spinner_qM83 spinner_ZTLf" cx="20" cy="12" r="3" /></svg
                        >
                    {:else}
                        <div
                                class=" {rmsLevel * 100 > 4
								? ' size-52'
								: rmsLevel * 100 > 2
									? 'size-48'
									: rmsLevel * 100 > 1
										? 'size-44'
										: 'size-40'}  transition-all rounded-full {(model?.info?.meta
								?.profile_image_url ?? '/static/favicon.png') !== '/static/favicon.png'
								? ' bg-cover bg-center bg-no-repeat'
								: 'bg-teal-500'} "
                                style={(model?.info?.meta?.profile_image_url ?? '/static/favicon.png') !==
							'/static/favicon.png'
								? `background-image: url('${model?.info?.meta?.profile_image_url}');`
								: ''}
                        />
                    {/if}
                </button>
            {:else}
                <div class="relative flex video-container w-full max-h-full pt-2 pb-4 md:py-6 px-2 h-full">
                    <video
                            id="camera-feed"
                            autoplay
                            class="rounded-2xl h-full min-w-full object-cover object-center"
                            playsinline
                    />

                    <canvas id="camera-canvas" style="display:none;" />

                    <div class=" absolute top-4 md:top-8 left-4">
                        <button
                                type="button"
                                class="p-1.5 text-white cursor-pointer backdrop-blur-xl bg-black/10 rounded-full"
                                on:click={() => {
								stopCamera();
							}}
                        >
                            <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    viewBox="0 0 16 16"
                                    fill="currentColor"
                                    class="size-6"
                            >
                                <path
                                        d="M5.28 4.22a.75.75 0 0 0-1.06 1.06L6.94 8l-2.72 2.72a.75.75 0 1 0 1.06 1.06L8 9.06l2.72 2.72a.75.75 0 1 0 1.06-1.06L9.06 8l2.72-2.72a.75.75 0 0 0-1.06-1.06L8 6.94 5.28 4.22Z"
                                />
                            </svg>
                        </button>
                    </div>
                </div>
            {/if}
        </div>

        <div class="flex justify-between items-center pb-2 w-full shrink-0">
            {#if !LIVEKIT_ENABLED}
                <div>
                    {#if camera}
                        <VideoInputMenu
                                devices={videoInputDevices}
                                on:change={async (e) => {
								console.log(e.detail);
								selectedVideoInputDeviceId = e.detail;
								await stopVideoStream();
								await startVideoStream();
							}}
                        >
                            <button class=" p-3 rounded-full bg-gray-50 dark:bg-gray-900" type="button">
                                <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        viewBox="0 0 20 20"
                                        fill="currentColor"
                                        class="size-5"
                                >
                                    <path
                                            fill-rule="evenodd"
                                            d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z"
                                            clip-rule="evenodd"
                                    />
                                </svg>
                            </button>
                        </VideoInputMenu>
                    {:else}
                        <Tooltip content={$i18n.t('Camera')}>
                            <button
                                    class=" p-3 rounded-full bg-gray-50 dark:bg-gray-900"
                                    type="button"
                                    on:click={async () => {
									await navigator.mediaDevices.getUserMedia({ video: true });
									startCamera();
								}}
                            >
                                <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke-width="1.5"
                                        stroke="currentColor"
                                        class="size-5"
                                >
                                    <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            d="M6.827 6.175A2.31 2.31 0 0 1 5.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 0 0-1.134-.175 2.31 2.31 0 0 1-1.64-1.055l-.822-1.316a2.192 2.192 0 0 0-1.736-1.039 48.774 48.774 0 0 0-5.232 0 2.192 2.192 0 0 0-1.736 1.039l-.821 1.316Z"
                                    />
                                    <path
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                            d="M16.5 12.75a4.5 4.5 0 1 1-9 0 4.5 4.5 0 0 1 9 0ZM18.75 10.5h.008v.008h-.008V10.5Z"
                                    />
                                </svg>
                            </button>
                        </Tooltip>
                    {/if}
                </div>
            {/if}

            <div>
                <button
                        type="button"
                        on:click={() => {
						if (assistantSpeaking || lkThinking) {
							stopAllAudio();
						} else if (lkConnectionState === ConnectionState.Connected) {
							dispatch('stopLivekit');
						} else if (lkConnectionState === ConnectionState.Disconnected) {
							dispatch('startLivekit');
						}
					}}
                >
                    {#if LIVEKIT_ENABLED && lkConnectionState === ConnectionState.Connected && !assistantSpeaking && !lkThinking}
                        <!-- Audio Level Meter (horizontal) -->
                        <div class="flex items-center justify-center gap-0.5 px-2">
                            <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    viewBox="0 0 20 20"
                                    fill="currentColor"
                                    class="w-5 h-5 translate-y-[0.5px] text-rose-500 ml-3"
                            >
                                <path d="M7 4a3 3 0 016 0v6a3 3 0 11-6 0V4z"></path>
                                <path
                                        d="M5.5 9.643a.75.75 0 00-1.5 0V10c0 3.06 2.29 5.585 5.25 5.954V17.5h-1.5a.75.75 0 000 1.5h4.5a.75.75 0 000-1.5h-1.5v-1.546A6.001 6.001 0 0016 10v-.357a.75.75 0 00-1.5 0V10a4.5 4.5 0 01-9 0v-.357z"
                                ></path>
                            </svg> 
                            {#each AUDIO_BARS as index}
                                {@const isFilled = lkMicLevel * AUDIO_BARS_COUNT >= index + 1}
                                {@const isTeal = index < AUDIO_BARS_COUNT - AUDIO_BARS_COUNT / 4}
                                {@const isStandby = lkMicLevel === 0}
                                <div
                                        class="audio-bar"
                                        class:filled={isFilled}
                                        class:teal={isTeal}
                                        class:yellow={!isTeal}
                                        class:standby={isStandby}
                                        style={isStandby ? `animation-delay: ${index * 100}ms` : ''}
                                />
                            {/each}
                        </div>
                    {:else}
                        <div class="line-clamp-1 text-sm font-medium pl-3">
                            {#if LIVEKIT_ENABLED}
                                {#if lkConnectionState === ConnectionState.Disconnected}
                                    <div class="flex items-center gap-2 w-full">
                                        <svg
                                                xmlns="http://www.w3.org/2000/svg"
                                                viewBox="0 0 24 24"
                                                fill="currentColor"
                                                class="w-5 h-5 translate-y-[0.5px] text-rose-500"
                                        >
                                            <path
                                                    d="m12.707,12.707l-2.293,2.293-1.414-1.414,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0l-2.293,2.293-1.879-1.879c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l.352.352-1.134,1.135c-1.77,1.769-1.982,4.515-.638,6.519l-2.58,2.58c-.391.391-.391,1.023,0,1.414.195.195.451.293.707.293s.512-.098.707-.293l2.58-2.58c.865.58,1.868.871,2.871.871,1.321,0,2.642-.503,3.647-1.509l1.135-1.134.352.352c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-1.879-1.879,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0ZM23.707.293c-.391-.391-1.023-.391-1.414,0l-2.58,2.58c-2.004-1.344-4.749-1.132-6.519.638l-1.135,1.135-.353-.353c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l8,8c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-.353-.353,1.135-1.135c1.77-1.769,1.982-4.515.638-6.519l2.58-2.58c.391-.391.391-1.023,0-1.414Z"
                                            />
                                        </svg>
                                        {$i18n.t('Disconnected')}
                                    </div>
                                {:else if lkConnectionState === ConnectionState.Connecting}
                                    <div class="flex items-center gap-2 w-full">
                                        <svg
                                                xmlns="http://www.w3.org/2000/svg"
                                                viewBox="0 0 24 24"
                                                fill="currentColor"
                                                class="w-5 h-5 translate-y-[0.5px] text-amber-500"
                                        >
                                            <path
                                                    d="m12.707,12.707l-2.293,2.293-1.414-1.414,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0l-2.293,2.293-1.879-1.879c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l.352.352-1.134,1.135c-1.77,1.769-1.982,4.515-.638,6.519l-2.58,2.58c-.391.391-.391,1.023,0,1.414.195.195.451.293.707.293s.512-.098.707-.293l2.58-2.58c.865.58,1.868.871,2.871.871,1.321,0,2.642-.503,3.647-1.509l1.135-1.134.352.352c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-1.879-1.879,2.293-2.293c.391-.391.391-1.023,0-1.414s-1.023-.391-1.414,0ZM23.707.293c-.391-.391-1.023-.391-1.414,0l-2.58,2.58c-2.004-1.344-4.749-1.132-6.519.638l-1.135,1.135-.353-.353c-.391-.391-1.023-.391-1.414,0s-.391,1.023,0,1.414l8,8c.195.195.451.293.707.293s.512-.098.707-.293c.391-.391.391-1.023,0-1.414l-.353-.353,1.135-1.135c1.77-1.769,1.982-4.515.638-6.519l2.58-2.58c.391-.391.391-1.023,0-1.414Z"
                                            />
                                        </svg>
                                        {$i18n.t('Connecting...')}
                                    </div>
                                {:else if lkConnectionState === ConnectionState.Connected}
                                    {#if assistantSpeaking}
                                        <div class="flex items-center gap-2 w-full">
                                            <svg
                                                    xmlns="http://www.w3.org/2000/svg"
                                                    viewBox="0 0 24 24"
                                                    fill="currentColor"
                                                    class="w-5 h-5 text-rose-500"
                                            >
                                                <path
                                                        d="M12,0A12,12,0,1,0,24,12,12,12,0,0,0,12,0Zm4.707,15.293-1.414,1.414L12,13.414,8.707,16.707,7.293,15.293,10.586,12,7.293,8.707,8.707,7.293,12,10.586l3.293-3.293,1.414,1.414L13.414,12Z"
                                                />
                                            </svg>
                                            {$i18n.t('Tap to interrupt')}
                                        </div>
                                    {:else if lkThinking}
                                        <div class="flex items-center gap-2 w-full">
                                            <svg
                                                    xmlns="http://www.w3.org/2000/svg"
                                                    viewBox="0 0 24 24"
                                                    width="512"
                                                    height="512"
                                                    fill="currentColor"
                                                    class="w-5 h-5 translate-y-[0.5px] text-indigo-500"
                                            >
                                                <path
                                                        d="M3,22.5c0,.828-.672,1.5-1.5,1.5s-1.5-.672-1.5-1.5,.672-1.5,1.5-1.5,1.5,.672,1.5,1.5Zm3-5.5c-1.105,0-2,.895-2,2s.895,2,2,2,2-.895,2-2-.895-2-2-2Zm9.845-1.42c.699,.279,1.422,.42,2.155,.42,3.309,0,6-2.691,6-6,0-2.733-1.823-5.069-4.416-5.772-.938-2.518-3.356-4.228-6.084-4.228-1.879,0-3.652,.819-4.88,2.223-.524-.147-1.067-.223-1.62-.223C3.691,2,1,4.691,1,8c0,3.242,2.585,5.892,5.802,5.997,1.062,1.845,3.032,3.003,5.198,3.003,1.426,0,2.767-.499,3.845-1.42Z"
                                                />
                                            </svg>
                                            {$i18n.t('Thinking...')}
                                        </div>
                                    {/if}
                                {/if}
                            {:else if loading}
                                {$i18n.t('Thinking...')}
                            {:else if assistantSpeaking}
                                {$i18n.t('Tap to interrupt')}
                            {:else}
                                {$i18n.t('Listening...')}
                            {/if}
                        </div>
                    {/if}
                </button>
            </div>
        </div>
    </div>
{/if}

<style>
    /* Horizontal audio level meter bars */
    .audio-bar {
        width: 15px;
        height: 5px;
        border: darkorange solid 1px;
        background-color: orange;
        opacity: 0.2;
        transition:
                background-color 100ms ease-out,
                border-color 100ms ease-out;
    }

    .audio-bar.teal {
        border: seagreen solid 1px;
        background-color: lightseagreen;
        opacity: 0.2;
    }

    /* Filled state - bar is active */
    .audio-bar.teal.filled {
        background-color: lightseagreen;
        border-color: lightseagreen;
        opacity: 1;
    }

    .audio-bar.filled {
        background-color: orange;
        border-color: orange;
        opacity: 1;
    }

    /* Standby animation when no audio input */
    .audio-bar.standby {
        animation: standby-wave 1.5s ease-in-out infinite;
    }

    @keyframes standby-wave {
        0%,
        100% {
            opacity: 0.15;
        }
        50% {
            opacity: 0.5;
        }
    }

    /* Mobile responsiveness - narrower bars */
    @media (max-width: 640px) {
        .audio-bar {
            width: 20px;
            height: 5px;
        }
    }

    /* Tablet and up - slightly wider bars */
    @media (min-width: 768px) {
        .audio-bar {
            width: 15px;
            height: 5px;
        }
    }

    .animate-breath {
        animation: breath 2s infinite ease-in-out;
    }

    @keyframes breath {
        0% {
            transform: scale(0.95);
            opacity: 0.6;
        }
        50% {
            transform: scale(1.05);
            opacity: 1;
        }
        100% {
            transform: scale(0.95);
            opacity: 0.6;
        }
    }
</style>
