# TTS_Providers.py
# Description: This file contains the functions to allow for usage of different TTS providers.
#
# Imports
import json
import logging
import os
import tempfile
import time
import uuid
#
# External Imports
#import edge_tts
import requests
from openai import api_key
from pydub import AudioSegment
from pydub.playback import play
#
# Local Imports
from App_Function_Libraries.Utils.Utils import load_and_log_configs, loaded_config_data
#
#######################################################################################################################
#
# Functions:

def play_mp3(file_path):
    """Play an MP3 file using the pydub library."""
    try:
        from pydub.utils import which
        logging.debug(f"Debug: ffmpeg path: {which('ffmpeg')}")
        logging.debug(f"Debug: ffplay path: {which('ffplay')}")

        absolute_path = os.path.abspath(file_path)
        audio = AudioSegment.from_mp3(absolute_path)
        logging.debug("Debug: File loaded successfully")
        play(audio)
    except Exception as e:
        logging.debug(f"Debug: Exception type: {type(e)}")
        logging.debug(f"Debug: Exception args: {e.args}")
        logging.error(f"Error playing the audio file: {e}")


def play_audio_file(file_path):
    """Play an audio file using the pydub library."""
    try:
        absolute_path = os.path.abspath(file_path)
        audio = AudioSegment.from_file(absolute_path)
        play(audio)
    except Exception as e:
        logging.error(f"Error playing the audio file: {e}")


def generate_audio(api_key, text, provider, voice=None, model=None, voice2=None, output_file=None, response_format=None, streaming=False):
    """Generate audio using the specified TTS provider."""
    logging.info(f"Starting generate_audio function")

    # Get default provider if none specified
    if not provider:
        provider = loaded_config_data['tts_settings'].get('default_tts_provider', 'openai')
        logging.info(f"No provider specified, using default: {provider}")

    # Set default output file if none specified
    if not output_file:
        # FIXME - use a temp file
        output_file = "speech.mp3"
        logging.info(f"No output file specified, using default: {output_file}")

    logging.info(f"Generating audio using {provider} TTS provider")

    if provider == "openai":
        logging.info("Using OpenAI TTS provider")
        if api_key is None:
            logging.info("No API key provided, attempting to use config file")
            api_key = loaded_config_data['openai_api']['api_key']
        return generate_audio_openai(
            api_key=api_key,
            input_text=text,
            voice=voice,
            model=model,
            response_format=response_format,
            output_file=output_file,
            streaming=streaming
        )

    elif provider == "elevenlabs":
        logging.info("Using ElevenLabs TTS provider")
        if api_key is None:
            logging.info("No API key provided, attempting to use config file")
            api_key = loaded_config_data['elevenlabs_api']['api_key']
        return generate_audio_elevenlabs(
            input_text=text,
            voice=voice,
            model=model,
            api_key=api_key
        )

    elif provider == "alltalk":
        logging.info("Using AllTalk TTS provider")
        return generate_audio_alltalk(
            input_text=text,
            voice=voice,
            model=model
        )

    elif provider == "google":
        pass

    elif provider == "gpt-soviTTS":
        pass

    elif provider == "piper":
        logging.info("Using Piper TTS provider")
        return generate_audio_piper(
            input_text=text,
            model=model,
            output_file=output_file,
        )

    else:
        error_msg = f"Invalid TTS provider: {provider}"
        logging.error(error_msg)
        raise ValueError(error_msg)


def speak_last_response(chatbot):
    """Handle speaking the last chat response."""
    logging.debug("Starting speak_last_response")
    try:
        # If there's no chat history, return
        if not chatbot or len(chatbot) == 0:
            logging.debug("No messages in chatbot history")
            return "No messages to speak"

        # Log the chatbot content for debugging
        logging.debug(f"Chatbot history: {chatbot}")

        # Get the last message from the assistant
        last_message = chatbot[-1][1]
        logging.debug(f"Last message to speak: {last_message}")

        # Generate audio using your preferred TTS provider
        audio_file = generate_audio(
            text=last_message,
            provider="openai",  # or get from config
            output_file="last_response.mp3"  # specify output file
        )

        logging.debug(f"Generated audio file: {audio_file}")

        # Play the audio
        if audio_file and os.path.exists(audio_file):
            play_mp3(audio_file)
            return "Speaking response..."
        else:
            logging.error("Failed to generate audio file")
            return "Failed to generate audio"

    except Exception as e:
        logging.error(f"Error in speak_last_response: {str(e)}")
        return f"Error speaking response: {str(e)}"


def test_generate_audio():
    """Test the generate_audio function with a real API request."""
    api_key = None
    text = "The quick brown fox jumped over the lazy dog."
    provider = ["openai", "elevenlabs", "alltalk"]
    voice = "alloy"
    model = None
    response_format = "mp3"
    output_file = "speech.mp3"

    # Call the function
    for provider in provider:
        result = generate_audio(api_key, text, provider, voice, model, output_file, response_format)

        # Assertions
        assert os.path.exists(result), f"The file {result} should exist."
        assert result.endswith(".mp3"), f"The file {result} should be an MP3 file."

        print(f"Attempting to play file: {result} from provider: {provider}")
        if os.path.exists(result):
            play_mp3(result)  # Single play call
    print("Test successful")


#######################################################
#
# OpenAI TTS Provider Functions

# https://github.com/leokwsw/OpenAI-TTS-Gradio/blob/main/app.py
def generate_audio_openai(api_key, input_text, voice, model, response_format="mp3", output_file="speech.mp3", streaming=False):
    """
    Generate audio using OpenAI's Text-to-Speech API.

    Args:
        api_key (str): OpenAI API key.
        input_text (str): Text input for speech synthesis.
        voice (str): Voice to use for the synthesis.
        model (str): Model to use for the synthesis (e.g., "tts-1").
        response_format (str): Format of the response audio file (default is "mp3").
        output_file (str): Name of the output file to save the audio.

    Returns:
        str: Path to the saved audio file if successful.

    Raises:
        ValueError: If required inputs are missing or invalid.
        RuntimeError: If the API request fails.
    """
    logging.info("Generating audio using OpenAI API.")
    # Validate inputs

    # API key validation
    try:
        if api_key == None:
            logging.info("OpenAI: API key not provided as parameter")
            logging.info("OpenAI: Attempting to use API key from config file")
            api_key = loaded_config_data['openai_api']['api_key']
            logging.debug(f"OpenAI: Using API Key: {api_key[:5]}...{api_key[-5:]}")
    except Exception as e:
        logging.error(f"OpenAI: Error loading API Key: {str(e)}")
        return f"OpenAI: Error loading API Key: {str(e)}"

    # Input data handling
    try:
        if not input_text:
            raise ValueError("Text input is required.")
        logging.debug(f"OpenAI: Raw input data type: {type(input_text)}")
        logging.debug(f"OpenAI: Raw input data (first 500 chars): {str(input_text)[:500]}...")
    except Exception as e:
        logging.error(f"OpenAI: Error loading input text: {str(e)}")
        return f"OpenAI: Error loading input text: {str(e)}"

    # Voice selection handling
    try:
        if not voice:
            logging.info("OpenAI: Speaker Voice not provided as parameter")
            logging.info("OpenAI: Attempting to use Speaker Voice from config file")
            voice = loaded_config_data['tts_settings']['default_openai_tts_voice']

        if not voice:
            raise ValueError("Voice is required. Default voice not found in config file and no voice selection was passed.")
    except Exception as e:
        logging.error(f"OpenAI: Error loading Speaker Voice: {str(e)}")
        return f"OpenAI: Error loading Speaker Voice: {str(e)}"

    # Model selection handling
    try:
        if not model:
            logging.info("OpenAI: Model not provided as parameter")
            logging.info("OpenAI: Attempting to use Model from config file")
            model = loaded_config_data['tts_settings']['default_openai_tts_model']

        if not model:
            raise ValueError("Model is required. Default model not found in config and no model selection was passed.")
    except Exception as e:
        logging.error(f"OpenAI: Error Selecting Model: {str(e)}")
        return f"OpenAI: Error Selecting Model: {str(e)}"

    # API endpoint
    endpoint = "https://api.openai.com/v1/audio/speech"

    # Headers for the API request
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Payload for the API request
    payload = {
        "model": model,
        "input": input_text,
        "voice": voice,
    }

    if streaming == True:
        try:
            # Make the request to the API
            response = requests.post(endpoint, headers=headers, json=payload, stream=True)
            response.raise_for_status()  # Raise an error for HTTP status codes >= 400

            # Save the audio response to a file
            with open(output_file, "wb") as f:
                f.write(response.content)

            print(f"Audio successfully generated and saved to {output_file}.")
            return output_file

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to generate audio: {str(e)}") from e
    else:
        try:
            # Make the request to the API
            response = requests.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()  # Raise an error for HTTP status codes >= 400

            # Save the audio response to a file
            with open(output_file, "wb") as f:
                f.write(response.content)

            print(f"Audio successfully generated and saved to {output_file}.")
            return output_file

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to generate audio: {str(e)}") from e


def test_generate_audio_openai():
    try:
        logging.info("OpenAI: Attempting to use API key from config file")
        api_key = loaded_config_data['openai_api']['api_key']

        if not api_key:
            logging.error("OpenAI: API key not found or is empty")
            return "OpenAI: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"OpenAI: Using API Key: {api_key[:5]}...{api_key[-5:]}")
    except Exception as e:
        logging.error(f"OpenAI: Error loading API Key: {str(e)}")
        return f"OpenAI: Error loading API Key: {str(e)}"

    input_text = "The quick brown fox jumped over the lazy dog."

    voice = "alloy"

    model = "tts-1"

    try:
        output_file = generate_audio_openai(api_key, input_text, voice, model)
        print(f"Generated audio file: {output_file}")
        play_mp3(output_file)
    except Exception as e:
        print(f"Error: {e}")

#
# End of OpenAI TTS Provider Functions
#######################################################


#######################################################
#
# MS Azure TTS Provider Functions
#
#https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-azure-speech/README.md

#
# End of MS Edge TTS Provider Functions
#######################################################


#######################################################
#
# ElvenLabs TTS Provider Functions
# FIXME - all of this

# https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/tools/llama-index-tools-elevenlabs/README.md
#https://elevenlabs.io/docs/api-reference/text-to-speech
def generate_audio_elevenlabs(input_text, voice, model=None, api_key=None):
    """Generate audio using ElevenLabs API."""
    logging.info("Generating audio using ElevenLabs API.")
    CHUNK_SIZE = 1024
    # API key validation
    elevenlabs_api_key = api_key
    try:
        if not elevenlabs_api_key:
            logging.info("ElevenLabs: API key not provided as parameter")
            logging.info("ElevenLabs: Attempting to use API key from config file")
            elevenlabs_api_key = loaded_config_data['elevenlabs_api']['api_key']

        if not elevenlabs_api_key:
            logging.error("ElevenLabs: API key not found or is empty")
            return "ElevenLabs: API Key Not Provided/Found in Config file or is empty"

        logging.debug(f"ElevenLabs: Using API Key: {elevenlabs_api_key[:5]}...{elevenlabs_api_key[-5:]}")
    except Exception as e:
        logging.error(f"ElevenLabs: Error loading API Key: {str(e)}")
        return f"ElevenLabs: Error loading API Key: {str(e)}"

    # Input data handling
    try:
        if not input_text:
            raise ValueError("Text input is required.")
        logging.debug(f"ElevenLabs: Raw input data type: {type(input_text)}")
        logging.debug(f"ElevenLabs: Raw input data (first 500 chars): {str(input_text)[:500]}...")
    except Exception as e:
        logging.error(f"ElevenLabs: Error loading input text: {str(e)}")
        return f"ElevenLabs: Error loading input text: {str(e)}"

    # Handle Voice ID
    try:
        if not voice:
            logging.info("ElevenLabs: Speaker ID(Voice) not provided as parameter")
            logging.info("ElevenLabs: Attempting to use Speaker ID(Voice) from config file")
            voice = loaded_config_data['tts_settings']['default_eleven_tts_voice']

        if not voice:
            raise ValueError("Voice is required. Default voice not found in config file and no voice selection was passed.")
    except Exception as e:
        logging.error(f"ElevenLabs: Error loading Speaker ID(Voice): {str(e)}")
        return f"ElevenLabs: Error loading Speaker ID(Voice): {str(e)}"

    # Handle Model ID/Selection
    try:
        if not model:
            logging.info("ElevenLabs: Model not provided as parameter")
            logging.info("ElevenLabs: Attempting to use Model from config file")
            model = loaded_config_data['tts_settings']['default_eleven_tts_model']

        if not model:
            raise ValueError("Model is required. Default model not found in config file and no model selection was passed.")
    except Exception as e:
        logging.error(f"ElevenLabs: Error Selecting Model: {str(e)}")
        return f"ElevenLabs: Error Selecting Model: {str(e)}"

    # FIXME - add SSML tags
    # Set the parameters for the TTS conversion
    try:
        # Stability
        stability_str = loaded_config_data['tts_settings'].get('default_eleven_tts_voice_stability', '0.0')
        default_eleven_tts_voice_stability = float(stability_str) if stability_str else 0.0

        # Similarity Boost
        similarity_boost_str = loaded_config_data['tts_settings'].get('default_eleven_tts_voice_similiarity_boost', '1.0')
        default_eleven_tts_voice_similiarity_boost = float(similarity_boost_str) if similarity_boost_str else 1.0

        # Style
        style_str = loaded_config_data['tts_settings'].get('default_eleven_tts_voice_style', '0.0')
        default_eleven_tts_voice_style = float(style_str) if style_str else 0.0

        # Use Speaker Boost
        use_speaker_boost_str = loaded_config_data['tts_settings'].get('default_eleven_tts_voice_use_speaker_boost', 'True')
        default_eleven_tts_voice_use_speaker_boost = use_speaker_boost_str.lower() == 'true' if use_speaker_boost_str else True

        # Output Format
        default_eleven_tts_output_format = loaded_config_data['tts_settings'].get('default_eleven_tts_output_format', 'mp3_44100_192')
    except Exception as e:
        logging.error(f"ElevenLabs: Error loading voice settings: {str(e)}")
        return f"ElevenLabs: Error loading voice settings: {str(e)}"

    # Make the API request
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream?output_format={default_eleven_tts_output_format}"

    # Set up headers for the API request, including the API key for authentication
    headers = {
        "Accept": "application/json",
        "xi-api-key": elevenlabs_api_key
    }

    # Set up the data payload for the API request, including the text and voice settings
    data = {
        "text": input_text,
        "model_id": model,
        "output_format": default_eleven_tts_output_format,
        "voice_settings": {
            "stability": default_eleven_tts_voice_stability,
            "similarity_boost": default_eleven_tts_voice_similiarity_boost,
            "style": default_eleven_tts_voice_style,
            "use_speaker_boost": default_eleven_tts_voice_use_speaker_boost
        }
    }

    try:
        # Make the POST request to the TTS API with headers and data, enabling streaming response
        with requests.post(tts_url, headers=headers, json=data, stream=True) as response:
            # Check if the request was successful
            if response.ok:
                # Create temp file but don't use context manager
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    tmp_file.write(chunk)
                tmp_file.flush()
                tmp_file.close()  # Explicitly close the file handle
                temp_file_path = tmp_file.name
                print(f"Audio stream saved successfully to {temp_file_path}.")
                return temp_file_path
            else:
                logging.error(f"API request failed: {response.status_code} - {response.text}")
                return f"API request failed: {response.status_code} - {response.text}"
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to generate audio: {str(e)}") from e


def test_generate_audio_elevenlabs_real_request():
    """Test the function with a real API request."""
    api_key = None
    input_text = "This is a test text for generating audio."
    voice = None
    model = "eleven_turbo_v2"

    # Call the function
    result = generate_audio_elevenlabs(input_text=input_text, voice=voice, model=model, api_key=api_key)

    # Assertions
    assert os.path.exists(result), f"The file {result} should exist."
    assert result.endswith(".mp3"), f"The file {result} should be an MP3 file."

    print(f"Attempting to play file: {result}")
    if os.path.exists(result):
        play_mp3(result)  # Single play call


def test_generate_audio_elevenlabs_invalid_api_key():
    """Test the function with an invalid API key."""
    # Use an invalid API key
    api_key = "invalid_api_key"
    input_text = "This is a test text for generating audio."
    voice = "your_voice_id"  # Replace with a valid voice ID from ElevenLabs

    # Call the function
    result = generate_audio_elevenlabs(input_text=input_text, voice=voice, api_key=api_key)

    # Assertions
    assert "API request failed" in result, "The function should return an error message for an invalid API key."

def test_generate_audio_elevenlabs_missing_input_text():
    """Test the function with missing input text."""
    # Use a valid API key but no input text
    api_key = "your_actual_api_key"
    input_text = ""
    voice = "your_voice_id"  # Replace with a valid voice ID from ElevenLabs

    # Call the function
    result = generate_audio_elevenlabs(input_text=input_text, voice=voice, api_key=api_key)

    # Assertions
    assert "Error loading input text" in result, "The function should return an error message for missing input text."

# End of ElvenLabs TTS Provider Functions
#######################################################


#######################################################
#
# Google Gemini TTS Provider Functions

# https://github.com/google-gemini/cookbook/blob/main/quickstarts/Audio.ipynb
# Fuck google. lets wait for their docs to not be complete fucking shit.

#
# End of Google Gemini TTS Provider Functions
#######################################################


############################################################ LOCAL #####################################################


#######################################################
#
# AllTalk TTS Provider Functions
# https://github.com/erew123/alltalk_tts
# https://github.com/erew123/alltalk_tts/wiki/API-%E2%80%90-OpenAI-V1-Speech-Compatible-Endpoint

def generate_audio_alltalk(input_text, voice=None, model=None, response_format=None, speed=None):
    """Generate audio using AllTalk API.

    Args:
        input_text (str): Text to convert to speech (max 4096 chars)
        voice (str, optional): Voice ID ('alloy', 'echo', 'fable', 'nova', 'onyx', 'shimmer')
        model (str, optional): Model ID (placeholder)
        response_format (str, optional): Audio format (defaults to 'wav')
        speed (float, optional): Speech speed (0.25 to 4.0, defaults to 1.0)

    Returns:
        str: Path to the generated audio file
    """

    # Input validation
    try:
        if not input_text:
            raise ValueError("Text input is required.")
        logging.debug(f"AllTalk: Raw input data type: {type(input_text)}")
        logging.debug(f"AllTalk: Raw input data (first 500 chars): {str(input_text)[:500]}...")
    except Exception as e:
        logging.error(f"AllTalk: Error loading input text: {str(e)}")
        return f"AllTalk: Error loading input text: {str(e)}"
    try:
        if input_text > 4096:
            raise ValueError("Text input must be less than 4096 characters.")
    except Exception as e:
        logging.error(f"AllTalk: Error loading input text(more than 4096 characters): {str(e)}")
        return f"AllTalk: Error loading input text(more than 4096 characters): {str(e)}"

    # Handle Voice
    try:
        if not voice:
            logging.info("AllTalk: Voice not provided as parameter")
            logging.info("AllTalk: Attempting to use voice from config file")
            voice = loaded_config_data['alltalk_api']['voice']

        if not voice:
            raise ValueError("Voice is required. Default voice not found in config file and no voice selection was passed.")
    except Exception as e:
        logging.error(f"AllTalk: Error loading voice: {str(e)}")
        return f"AllTalk: Error loading voice: {str(e)}"

    # Handle Response Format
    try:
        if not response_format:
            logging.info("AllTalk: Format not provided as parameter")
            logging.info("AllTalk: Attempting to use format from config file")
            response_format = loaded_config_data['alltalk_api']['default_alltalk_tts_output_format']

        if not response_format:
            logging.debug("AllTalk: No response format provided. Defaulting to 'wav'")
            response_format = "wav"
    except Exception as e:
        logging.error(f"AllTalk: Error setting format: {str(e)}")
        return f"AllTalk: Error setting format: {str(e)}"

    # Handle Speed
    try:
        if not speed:
            logging.info("AllTalk: Speed not provided as parameter")
            logging.info("AllTalk: Attempting to use speed from config file")
            speed = loaded_config_data['alltalk_api']['default_alltalk_tts_speed']

        if not speed:
            logging.debug("AllTalk: No speed provided. Defaulting to '1.0'")
            speed = 1.0

        speed = float(speed)
        if not 0.25 <= speed <= 4.0:
            raise ValueError("Speed must be between 0.25 and 4.0")
    except Exception as e:
        logging.error(f"AllTalk: Error setting speed: {str(e)}")
        return f"AllTalk: Error setting speed: {str(e)}"

    # API URL
    try:
        alltalk_api_url = loaded_config_data['alltalk_api']['api_ip']
        if not alltalk_api_url:
            raise ValueError("API URL not found in config")
    except Exception as e:
        logging.error(f"AllTalk: Error loading API URL: {str(e)}")
        return f"AllTalk: Error loading API URL: {str(e)}"

    # Prepare request
    payload = {
        "model": model,
        "input": input_text,
        "voice": voice,
        "response_format": response_format,
        "speed": speed
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        # Make the API request without streaming
        response = requests.post(alltalk_api_url, json=payload, headers=headers)

        if response.ok:
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False,
                                           suffix=f".{response_format}") as tmp_file:
                # Write the entire response content at once
                tmp_file.write(response.content)
                tmp_file.flush()
                temp_file_path = tmp_file.name

            print(f"Audio stream saved successfully to {temp_file_path}.")
            return temp_file_path
        else:
            error_msg = f"API request failed: {response.status_code} - {response.text}"
            logging.error(error_msg)
            return error_msg

    except requests.exceptions.RequestException as e:
        error_msg = f"Failed to generate audio: {str(e)}"
        logging.error(error_msg)
        return error_msg


def test_generate_audio_alltalk():
    model = "placeholder"
    input_text = "The quick brown fox jumped over the yellow lazy dog."
    voice = "alloy"
    response_format = "wav"
    speed = 1.0

    generate_audio_alltalk(model, input_text, voice, response_format, speed)

#
# End of AllTalk TTS Provider Functions
#######################################################


#######################################################
#
# Piper TTS Provider Functions
# https://github.com/rhasspy/piper
# https://github.com/erew123/alltalk_tts/wiki/API-%E2%80%90-OpenAI-V1-Speech-Compatible-Endpoint

def generate_audio_piper(input_text, voice=None, model=None, response_format=None, speed=None):
    """Generate audio using Piper TTS.

    Args:

    Returns:
        str: Path to the generated audio file
    """

    # Input validation
    pass

#
# End of Piper TTS Provider Functions
#######################################################


#######################################################
#
# Vevo TTS Provider Functions
#
# https://github.com/open-mmlab/Amphion
# https://huggingface.co/amphion/Vevo

def generate_audio_vevo(input_text, voice=None, model=None, response_format=None, speed=None):
    """Generate audio using Piper TTS.

    Args:

    Returns:
        str: Path to the generated audio file
    """

    # Input validation
    pass

#
# End of Vevo TTS Provider Functions
#######################################################


#######################################################
#
# gpt-soviTTS TTS Provider Functions
# https://github.com/RVC-Boss/GPT-SoVITS

#
# End of gpt-soviTTS TTS Provider Functions
#######################################################

#
# End of TTS_Providers.py
#######################################################################################################################
