# policy-voice-bot
A conversational voice AI assistant built for the insurance domain. Supports multilingual speech, real-time translation, and GPT-based responses.
The Policy Voice Bot is a real-time conversational AI assistant built for the insurance domain. It allows users to speak naturally in multiple Indian languages, processes their voice inputs using Whisper (STT), generates smart responses using GPT (OpenAI/Ollama), and then speaks the answers aloud using gTTS or OpenAI TTS.

It provides human-like, multilingual support, aiming to make insurance policy information and services more accessible and user-friendly via voice interaction.
Tech Stack Used:
Frontend: HTML, CSS, JavaScript
Backend: Python, Flask
AI Models:
Whisper for speech-to-text (STT)
Ollama / OpenAI GPT for natural language response
gTTS / OpenAI TTS for text-to-speech
Other Tools: orjson, uuid, session memory, ChromaDB (for vector storage)
Voice Languages: Telugu, Hindi, Gujarati, Punjabi (more supported)
Real-time voice interaction
Multilingual support
Context-aware responses
Natural-sounding TTS voice output
Call memory using transcription and vector memory
Animated video bot interface
