let recognition;
let currentBotAudio = null; // To keep track of the currently playing bot audio
let isBotSpeaking = false;  // Flag to indicate if the bot's audio is currently playing
let finalTranscript = ''; // To accumulate the final transcript
let recognitionTimeoutId; // To store the timeout for restarting recognition

window.onload = () => {
    const startBtn = document.getElementById("start-btn");

    startBtn.addEventListener("click", () => {
        startBtn.disabled = true; // Disable the button after the first click
        updateStatus("🎤 Listening...");
        startVoiceRecognition();
    });
};

function startVoiceRecognition() {
    // Clear any existing timeout for restarting recognition
    if (recognitionTimeoutId) {
        clearTimeout(recognitionTimeoutId);
        recognitionTimeoutId = null;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("Speech Recognition is not supported in this browser.");
        return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    // recognition.continuous = true; // Use with caution, can lead to very long recordings if not managed
    // recognition.speechRecognitionTimeout = 5000; // Example: 5 seconds of silence before ending

    recognition.onstart = () => {
        updateStatus("🎤 Listening...");
        switchAvatarVideo("/static/blinking.mp4", true); // Ensure blinking animation while listening
        finalTranscript = ''; // Reset transcript for new utterance
        // Also clear any previous timeout when a new recognition starts
        if (recognitionTimeoutId) {
            clearTimeout(recognitionTimeoutId);
            recognitionTimeoutId = null;
        }
    };

    recognition.onresult = (event) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }
        updateStatus(`🎤 Listening: ${finalTranscript + interimTranscript}`);
    };

    recognition.onend = () => {
        updateStatus("🟡 Idle...");
        if (finalTranscript.trim() !== '') {
            displayUserMessage(finalTranscript.trim());
            sendToBot(finalTranscript.trim());
        } else {
            console.log("No final transcript captured. Waiting to restart recognition.");
            // Only restart if bot isn't about to speak and after a delay
            if (!isBotSpeaking) {
                displayError("No voice detected. Please speak."); // Display the statement
                recognitionTimeoutId = setTimeout(() => {
                    startVoiceRecognition();
                }, 15000); // Wait for 15 seconds before restarting
            }
        }
    };

    recognition.onerror = (event) => {
        console.error("🎙️ Speech recognition error:", event.error);
        if (event.error === 'no-speech') {
            updateStatus("🟡 Idle (no speech)");
            displayError("No voice detected. Please speak."); // Display the statement
            if (!isBotSpeaking) {
                recognitionTimeoutId = setTimeout(() => {
                    startVoiceRecognition();
                }, 15000); // Wait for 15 seconds before restarting
            }
        } else if (event.error === 'network') {
            displayError("Network error during speech recognition. Check your connection.");
            if (!isBotSpeaking) {
                recognitionTimeoutId = setTimeout(() => {
                    startVoiceRecognition();
                }, 15000); // Wait for 15 seconds before restarting
            }
        } else if (event.error === 'not-allowed') {
            displayError("Microphone access denied. Please allow microphone in browser settings.");
            document.getElementById("start-btn").disabled = false;
            // Do not automatically restart if permission is denied
        } else if (event.error === 'aborted') {
            // This error often means recognition was stopped externally (e.g., by another start call)
            console.warn("Speech recognition aborted, likely due to quick restart or resource conflict.");
            // We usually don't need to display a user-facing error for 'aborted'
            if (!isBotSpeaking) {
                recognitionTimeoutId = setTimeout(() => {
                    startVoiceRecognition();
                }, 500); // Shorter delay for aborted to retry quickly
            }
        }
        else {
            displayError("Mic error: " + event.error);
            if (!isBotSpeaking) {
                recognitionTimeoutId = setTimeout(() => {
                    startVoiceRecognition();
                }, 15000); // Wait for 15 seconds before restarting
            }
        }
    };

    recognition.start();
    console.log("Speech recognition started.");
}


function sendToBot(transcript) {
    updateStatus("🧠 Thinking...");
    if (recognitionTimeoutId) {
        clearTimeout(recognitionTimeoutId);
        recognitionTimeoutId = null;
    }

    fetch('/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: transcript })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.reply) {
            displayBotMessage(data.reply);

            // Now fetch TTS audio
            fetch('/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: data.reply, audio_id: data.audio_id })
            })
            .then(ttsResponse => {
                if (!ttsResponse.ok) {
                    return ttsResponse.json().then(errorData => {
                        throw new Error(errorData.error || `TTS error! status: ${ttsResponse.status}`);
                    });
                }
                return ttsResponse.json();
            })
            .then(ttsData => {
                if (ttsData.audio_base64) {
                    const audioData = "data:audio/mp3;base64," + ttsData.audio_base64;
                    const audio = new Audio(audioData);
                    currentBotAudio = audio;

                    isBotSpeaking = true;
                    switchAvatarVideo("/static/talking.mp4", true);

                    audio.play().catch(err => {
                        console.warn("🔇 Audio play error:", err);
                        isBotSpeaking = false;
                        switchAvatarVideo("/static/blinking.mp4", true);
                        startVoiceRecognition();
                    });

                    audio.onended = () => {
                        isBotSpeaking = false;
                        switchAvatarVideo("/static/blinking.mp4", true);
                        startVoiceRecognition();
                    };
                } else {
                    console.warn("No audio returned.");
                    displayError("Bot responded, but no audio available.");
                    startVoiceRecognition();
                }
            })
            .catch(ttsError => {
                console.error("TTS fetch error:", ttsError);
                displayError("TTS error: " + ttsError.message);
                startVoiceRecognition();
            });

        } else {
            displayError("No reply received from bot.");
            startVoiceRecognition();
        }
    })
    .catch(error => {
        console.error("Fetch error:", error);
        displayError("Communication error: " + error.message);
        startVoiceRecognition();
    });
}


function switchAvatarVideo(src, loop = true) {
    const video = document.getElementById("avatarVideo");
    const source = document.getElementById("videoSource");

    // Only proceed if the source needs to change
    if (source.src !== window.location.origin + src) {
        // Step 1: Fade out the current video
        // Remove fade-in first to ensure the transition happens cleanly
        video.classList.remove('fade-in'); 
        video.classList.add('fade-out');

        // Step 2: After the fade-out completes, change source and fade in
        // Use a timeout that matches your CSS transition duration (e.g., 300ms)
        setTimeout(() => {
            video.pause();
            source.src = src;
            video.loop = loop;
            video.load(); // Reloads the video with the new source

            // Attempt to play immediately after load
            video.play().then(() => {
                // Step 3: Fade in the new video once it starts playing
                video.classList.remove('fade-out');
                video.classList.add('fade-in'); // Ensure it becomes visible
            }).catch(err => {
                console.warn("Video play error after source change:", err);
                // If play fails, still try to make it visible
                video.classList.remove('fade-out');
                video.classList.add('fade-in');
            });
        }, 300); // This duration should match your CSS transition duration (0.3s)
    } else {
        // If the source is already correct, just ensure it's visible and playing
        video.classList.remove('fade-out');
        video.classList.add('fade-in');
        video.play().catch(err => console.warn("Video play error (already set):", err));
    }
}


function updateStatus(text) {
    document.getElementById("status").innerText = text;
}

function displayUserMessage(message) {
    const chatBox = document.getElementById("chat-output");
    const el = document.createElement("p");
    el.innerHTML = `<strong>🙋 You:</strong> ${message}`;
    chatBox.appendChild(el);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function displayBotMessage(message) {
    const chatBox = document.getElementById("chat-output");
    const el = document.createElement("p");
    el.innerHTML = `<strong>🤖 Bot:</strong> ${message}`;
    chatBox.appendChild(el);
    updateStatus("✅ Responded.");
    chatBox.scrollTop = chatBox.scrollHeight;
}

function displayError(message) {
    const chatBox = document.getElementById("chat-output");
    const el = document.createElement("p");
    el.innerHTML = `<span style='color:red;'>❌ ${message}</span>`;
    chatBox.appendChild(el);
    updateStatus("❌ Error.");
    chatBox.scrollTop = chatBox.scrollHeight;
}