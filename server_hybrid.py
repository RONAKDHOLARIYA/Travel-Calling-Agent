import os
import asyncio
import base64
import json
import logging
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

# --- IMPORTS ---
from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    ServerEventType,
    ServerVad,
    Modality,
    InputAudioFormat,
    RequestSession,
)
from elevenlabs.client import AsyncElevenLabs

from dotenv import load_dotenv

load_dotenv()
# --- CONFIGURATION ---
AZURE_KEY = os.environ.get("AZURE_VOICELIVE_API_KEY")
AZURE_ENDPOINT = os.environ.get("AZURE_VOICELIVE_ENDPOINT")
AZURE_MODEL = os.environ.get("VOICELIVE_MODEL","gpt-4o-realtime-preview")

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY")
# Your Voice ID
ELEVEN_VOICE_ID = os.environ.get("ELEVEN_VOICE_ID","TRnaQb7q41oL7sV0w6Bu")

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LalBhaiAgent")

# Initialize Client
client_eleven = AsyncElevenLabs(api_key=ELEVEN_KEY)

# --- PERSONA ---
INSTRUCTIONS = """
Objective
---------
You are a voice agent named 'Leela Ben,' who acts as a friendly, empathetic, and knowledgeable travel agent specializing in global travel. Your goal is to simulate a natural, human-like conversational approach, maintaining a relaxed spoken style at all times.

Personality and Tone
--------------------
* Leela Ben should have a warm, approachable, and professional tone.
* IMPORTANT: Speak at a fast, energetic pace.
* Warm, enthusiastic, and approachable.
* She should sound enthusiastic about travel, curious, and empathetic to the user's context.
* Use casual, non-robotic language. Avoid repetitive phrases or mechanical responses.
* Include 'Human-like behaviors' such as occasional fillers (e.g., 'Hmm,' 'Let me think on that,' 'Oh, that is interesting') to simulate a natural thought process.

Language & Localization
-----------------------
* Multilingual Mastery: You must be able to communicate fluently in English, Hindi, and Gujarati.
* Adaptability: Tailor your responses according to the user's preferred language. If the user switches to Hindi or Gujarati, respond naturally in that language.
* Voice Safety: Do not use any emojis, annotations, parenthetically, or action lines (e.g., no *laughs* or [pause]). Only respond with words to be spoken.
* Normalization: Write out and normalize all text. For example, '200 INR' should be 'two dollars and thirty-five cents,' and '100 km/h' should be 'one hundred kilometers per hour.'

Constraints
-----------
* Keep responses brief, under five sentences.
* Use only standard alphabet characters and basic punctuation.

User Personalization
--------------------
Ask for basic details early: 'Where are you traveling from?', 'Budget?', 'Type of experience?'. Based on this, provide personalized suggestions.
"""


@app.websocket("/call")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Web client connected")

    # Shared State
    state = {"interrupted": False, "text_buffer": "", "tts_queue": asyncio.Queue()}

    async with connect(
        endpoint=AZURE_ENDPOINT,
        credential=AzureKeyCredential(AZURE_KEY),
        model=AZURE_MODEL,
    ) as azure_connection:

        # 1. Configure Session
        await setup_session(azure_connection)

        # 2. Start Background Tasks
        receive_task = asyncio.create_task(
            handle_azure_output(azure_connection, websocket, state)
        )
        tts_worker_task = asyncio.create_task(process_tts_queue(websocket, state))

        try:
            while True:
                # 3. Receive Mic Audio from Browser
                data = await websocket.receive_bytes()
                audio_base64 = base64.b64encode(data).decode("utf-8")
                await azure_connection.input_audio_buffer.append(audio=audio_base64)

        except WebSocketDisconnect:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            receive_task.cancel()
            tts_worker_task.cancel()


async def setup_session(connection):
    """Configures Azure: Listen to Audio, Respond with Text Only."""
    session_config = RequestSession(
        modalities=[Modality.TEXT, Modality.AUDIO],
        instructions=INSTRUCTIONS,
        input_audio_format=InputAudioFormat.PCM16,
        # Threshold 0.6 balances sensitivity vs echo
        turn_detection=ServerVad(
            threshold=0.6, prefix_padding_ms=300, silence_duration_ms=500
        ),
    )
    await connection.session.update(session=session_config)


async def handle_azure_output(connection, websocket: WebSocket, state):
    """Reads Azure events and fills the TTS Queue."""
    try:
        async for event in connection:

            # --- INTERRUPTION LOGIC ---
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                logger.info("User speaking... Interrupting!")
                state["interrupted"] = True
                state["text_buffer"] = ""

                # Clear the TTS Queue instantly
                while not state["tts_queue"].empty():
                    try:
                        state["tts_queue"].get_nowait()
                        state["tts_queue"].task_done()
                    except asyncio.QueueEmpty:
                        break

                await websocket.send_text(json.dumps({"type": "interrupt"}))

            # --- TEXT GENERATION LOGIC ---
            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                state["interrupted"] = False
                delta = event.delta
                state["text_buffer"] += delta

                # Send text for UI bubble
                await websocket.send_text(
                    json.dumps({"type": "agent_transcript_delta", "text": delta})
                )

                # Detect complete sentences to stream audio faster
                if re.search(r"[.!?।]\s*$", state["text_buffer"]):
                    sentence = state["text_buffer"].strip()
                    state["text_buffer"] = ""
                    if sentence:
                        await state["tts_queue"].put(sentence)

            elif event.type == ServerEventType.RESPONSE_DONE:
                if state["text_buffer"].strip():
                    await state["tts_queue"].put(state["text_buffer"])
                    state["text_buffer"] = ""
                await websocket.send_text(json.dumps({"type": "agent_response_done"}))

    except Exception as e:
        logger.error(f"Error in Azure Event Loop: {e}")


async def process_tts_queue(websocket, state):
    """Worker: Picks one sentence at a time -> ElevenLabs -> Browser."""
    while True:
        text = await state["tts_queue"].get()

        if state["interrupted"]:
            state["tts_queue"].task_done()
            continue

        try:
            # ✅ FINAL FORMAT: PCM 24000 (High Quality, Low Latency)
            # No 'await' on the convert() call because it's a generator in this version
            audio_stream = client_eleven.text_to_speech.convert(
                text=text,
                voice_id=ELEVEN_VOICE_ID,
                model_id="eleven_multilingual_v2",
                output_format="pcm_24000",
            )

            async for chunk in audio_stream:
                if state["interrupted"]:
                    break
                await websocket.send_bytes(chunk)

        except Exception as e:
            logger.error(f"ElevenLabs Worker Error: {e}")
        finally:
            state["tts_queue"].task_done()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
