from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import os
import base64
import uuid
import traceback
import sys
import io
import orjson  # Faster JSON
from openai import OpenAI, APIError, AuthenticationError, BadRequestError

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecretkey_change_me_in_production")


client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "ap key.."))


transcribed_recordings = {}

RECORDINGS_FOLDER = 'recordings'

def load_and_transcribe_recordings():
    """
    Scans the 'recordings' folder, transcribes audio files using OpenAI Whisper,
    and stores the transcriptions in the global transcribed_recordings dictionary.
    This function runs once on application startup.
    """
    print(f"Scanning '{RECORDINGS_FOLDER}' folder for audio recordings...")
    # Ensure the recordings folder exists
    if not os.path.exists(RECORDINGS_FOLDER):
        os.makedirs(RECORDINGS_FOLDER)
        print(f"Created '{RECORDINGS_FOLDER}' folder. Please place your call recordings here.")
        return

    supported_audio_extensions = ('.mp3', '.wav', '.m4a', '.flac', '.ogg')
    
    for filename in os.listdir(RECORDINGS_FOLDER):
        if filename.lower().endswith(supported_audio_extensions):
            filepath = os.path.join(RECORDINGS_FOLDER, filename)
            recording_id = os.path.splitext(filename)[0] # Use filename (without extension) as ID

            # Skip if already transcribed (useful for multiple restarts during development)
            if recording_id in transcribed_recordings:
                print(f"'{filename}' already transcribed. Skipping.")
                continue

            try:
                print(f"Transcribing '{filename}'...")
                with open(filepath, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model="whisper-1", # Using the Whisper ASR model
                        file=audio_file
                    )
                transcribed_text = transcription.text
                transcribed_recordings[recording_id] = transcribed_text
                print(f"Successfully transcribed '{filename}'. Stored with ID: '{recording_id}'.")
                print(f"Transcription preview: {transcribed_text[:100]}...") # Log a preview
            except AuthenticationError as e:
                print(f"Authentication Error during transcription of '{filename}': {e}")
                print("Please check your OPENAI_API_KEY environment variable.")
                break # Stop processing if authentication fails
            except APIError as e:
                print(f"OpenAI API Error during transcription of '{filename}': {e.response.json() if e.response else e}")
                print("Skipping this file due to API error.")
            except Exception as e:
                print(f"Error transcribing '{filename}': {str(e)}")
                traceback.print_exc() # Print full traceback for debugging
                print("Skipping this file due to an unexpected error.")
    print(f"Finished scanning and transcribing recordings. Total transcribed: {len(transcribed_recordings)}")


@app.route("/")
def home():
    """
    Renders the main HTML page for the chatbot.
    Initializes the conversation history for a new session.
    """
    session['conversation_history'] = [
        {"role": "system", "content": "You are a helpful insurance advisor. Speak in the language the user speaks and remember previous interactions."}
    ]
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    """
    Processes user input, generates a bot reply using OpenAI Chat Completions,
    and includes transcribed call recordings as context.
    """
    try:
        data = request.get_json(force=True)
        user_input = data.get("text")

        if not user_input:
            return jsonify({"error": "Missing input"}), 400

        print(f"User said: {user_input}")

        # Retrieve conversation history from session, or initialize it
        conversation_history = session.get('conversation_history', [])

        # Ensure the system message is always the first element and correctly formatted.
        if not conversation_history or conversation_history[0]["role"] != "system":
            conversation_history.insert(0, {"role": "system", "content": "You are a helpful insurance advisor. Speak in the language the user speaks and remember previous interactions."})

        # --- Bot Format: Including Transcribed Recordings as Context ---
        context_from_recordings = ""
        if transcribed_recordings:
            context_from_recordings = "\n\n--- Relevant Call Recording Transcripts (for context) ---\n"
            # Concatenate all stored transcriptions into the context.
            # WARNING: This approach can quickly hit token limits for long recordings or many recordings.
            # For a more robust solution with many recordings, consider implementing semantic search (RAG)
            # to retrieve and include only the most relevant snippets based on user input.
            for rec_id, transcript in transcribed_recordings.items():
                context_from_recordings += f"Recording ID: {rec_id}:\n{transcript}\n\n"
            context_from_recordings += "----------------------------------------------\n\n"

        # Update the system message with the dynamic context from recordings.
        # This effectively "trains" the bot for the current conversation by providing
        # it with the knowledge from the recordings.
        original_system_content = "You are a helpful insurance advisor. Speak in the language the user speaks and remember previous interactions."
        conversation_history[0]["content"] = (
            f"{original_system_content}"
            f"\n\n{context_from_recordings}"
            "When answering, refer to the provided call recording transcripts if relevant and integrate their information naturally."
            "Do not explicitly state 'According to the recordings' unless necessary."
        )
        # --- End Bot Format ---

        # Append the current user input to the conversation history
        conversation_history.append({"role": "user", "content": user_input})

        # Prepare messages for the OpenAI API call.
        # It's important to manage history to avoid exceeding token limits.
        # The system message is always included. We limit the number of
        # user/assistant turns.
        max_user_assistant_messages = 9 # Allows for 1 system message + 9 user/assistant pairs (total 10 messages)

        # Get only the recent user/assistant messages
        # Slicing from index 1 ensures we skip the system message
        user_assistant_messages_for_api = conversation_history[1:]
        if len(user_assistant_messages_for_api) > max_user_assistant_messages:
            user_assistant_messages_for_api = user_assistant_messages_for_api[-max_user_assistant_messages:]

        # Reconstruct the full message list for the OpenAI API call
        # The system message (which now includes the context) is always first.
        full_conversation_for_api = [conversation_history[0]] + user_assistant_messages_for_api

        # Make the API call to OpenAI's Chat Completions
        response_chat = client.chat.completions.create(
            model="gpt-3.5-turbo", # You might consider "gpt-4" or "gpt-4o" for better performance with large contexts
            messages=full_conversation_for_api
        )
        reply_original = response_chat.choices[0].message.content.strip()
        print(f"Bot reply: {reply_original}")

        # Append the assistant's reply to the full conversation history stored in the session
        # This history is used for subsequent turns to maintain context.
        conversation_history.append({"role": "assistant", "content": reply_original})
        session['conversation_history'] = conversation_history # Update the session

        return app.response_class(
            response=orjson.dumps({
                "reply": reply_original,
                "audio_id": str(uuid.uuid4())  # Unique ID for TTS fetch
            }),
            status=200,
            mimetype='application/json'
        )

    except AuthenticationError as e:
        print("Authentication Error:", e)
        return jsonify({"error": "Invalid OpenAI API key. Please check your OPENAI_API_KEY environment variable."}), 500
    except BadRequestError as e:
        print("Bad Request:", e)
        return jsonify({"error": f"Bad Request: {e.response.json() if e.response else e}"}), 400
    except APIError as e:
        print("OpenAI API Error:", e)
        return jsonify({"error": f"API Error: {e.response.json() if e.response else e}"}), 500
    except Exception as e:
        print("Internal Server Error:", str(e))
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/tts", methods=["POST"])
def tts():
    """
    Endpoint to convert text to speech using OpenAI TTS.
    """
    try:
        data = request.get_json(force=True)
        text = data.get("text")
        audio_id = data.get("audio_id", str(uuid.uuid4()))

        if not text:
            return jsonify({"error": "Missing text for TTS"}), 400

        voice_to_use = "nova" # You can choose other voices like 'alloy', 'shimmer', 'echo', 'fable', 'onyx'
        filepath = os.path.join(app.static_folder, f"{audio_id}.mp3")

        # Create the audio file using OpenAI's TTS model
        response_tts = client.audio.speech.create(
            model="tts-1", # Using the TTS model
            voice=voice_to_use,
            input=text
        )
        response_tts.stream_to_file(filepath) # Stream the audio response directly to a file

        # Read the generated audio file and encode it to base64
        with open(filepath, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')

        os.remove(filepath) # Clean up the temporary audio file after sending

        return app.response_class(
            response=orjson.dumps({
                "audio_base64": audio_base64
            }),
            status=200,
            mimetype='application/json'
        )

    except Exception as e:
        print("TTS Error:", str(e))
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Ensure the 'static' directory exists for temporary files and TTS output
    if not os.path.exists('static'):
        os.makedirs('static')
    
    # --- AUTOMATIC RECORDING TRANSCRIPTION ON STARTUP ---
    load_and_transcribe_recordings()
    # --- END AUTOMATIC RECORDING TRANSCRIPTION ---

    # Run the Flask application in debug mode (for development)
    app.run(debug=True, port=5000)
