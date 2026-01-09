import os
import asyncio
import base64
import json
import logging
import re
import shutil
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from io import BytesIO
# --- IMPORTS ---
from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    ServerEventType,
    ServerVad,
    Modality,
    InputAudioFormat,
    RequestSession
)
from elevenlabs.client import AsyncElevenLabs 

from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
# Load from environment variables
AZURE_KEY = os.environ.get("AZURE_VOICELIVE_API_KEY")
AZURE_ENDPOINT = os.environ.get("AZURE_VOICELIVE_ENDPOINT")
# Default to 'mini' for cost savings
AZURE_MODEL = os.environ.get("AZURE_VOICELIVE_MODEL", "gpt-4o-mini-realtime-preview")
ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY")

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceAgent")

client_eleven = AsyncElevenLabs(api_key=ELEVEN_KEY)

# --- 1. API: GET CLONED VOICES ---
@app.get("/voices")
async def get_voices():
    """Fetches ONLY CLONED voices from your ElevenLabs account."""
    try:
        response = await client_eleven.voices.get_all()
        # Filter for 'cloned' category to hide premade/default voices
        cloned_voices = [
            {"id": v.voice_id, "name": v.name, "category": v.category} 
            for v in response.voices 
            if v.category == 'cloned' 
        ]
        return {"voices": cloned_voices}
    except Exception as e:
        logger.error(f"Error fetching voices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 2. API: CLONE VOICE (FILE UPLOAD ONLY) ---
@app.post("/clone")
async def clone_voice(name: str = Form(...), files: List[UploadFile] = File(...)):
    """
    Creates a new voice using the official 'ivc.create' method.
    We fix the 'Corrupted' error by explicitly naming the BytesIO objects.
    """
    try:
        # 1. Check if voice exists (Optimization)
        response = await client_eleven.voices.get_all()
        existing_voice = next((v for v in response.voices if v.name == name), None)

        if existing_voice:
            logger.info(f"Voice '{name}' already exists. Using it.")
            return {
                "status": "exists", 
                "voice_id": existing_voice.voice_id, 
                "name": existing_voice.name,
                "message": "Voice already exists! Selected it."
            }

        # 2. Prepare Files for Official API
        logger.info(f"Cloning voice '{name}' using ivc.create...")
        
        voice_files = []
        
        for file in files:
            # Read the file content into memory
            content = await file.read()
            
            # Create a BytesIO object (Standard Python in-memory file)
            io_obj = BytesIO(content)
            
            # 🔴 CRITICAL FIX: The API needs to know this is an .mp3/.wav
            # Without this line, you get "400 Bad Request: File corrupted"
            io_obj.name = file.filename 
            
            voice_files.append(io_obj)

        # 3. Call Official SDK Method
        # Matches your example: client.voices.ivc.create(...)
        voice = await client_eleven.voices.ivc.create(
            name=name,
            description="Cloned via Hybrid Agent",
            files=voice_files
        )
        
        return {
            "status": "success", 
            "voice_id": voice.voice_id, 
            "name": name,
            "message": "Successfully created new voice!"
        }

    except Exception as e:
        logger.error(f"Cloning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
# --- 3. WEBSOCKET AGENT ---
INSTRUCTIONS = """
Objective
---------
You are a voice agent named 'Priti,' who acts as a friendly, empathetic, and knowledgeable travel agent specializing in global travel. Your goal is to simulate a natural, human-like conversational approach, maintaining a relaxed spoken style at all times.

Personality and Tone
--------------------
* Priti should have a warm, approachable, and professional tone.
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
async def websocket_endpoint(websocket: WebSocket, voice_id: str = "TRnaQb7q41oL7sV0w6Bu"):
    """
    Accepts 'voice_id' as a query parameter.
    Example: ws://localhost:8000/call?voice_id=XYZ
    """
    await websocket.accept()
    logger.info(f"Client connected. Using Voice ID: {voice_id}")

    state = {
        "interrupted": False,
        "text_buffer": "",
        "tts_queue": asyncio.Queue(),
        "voice_id": voice_id 
    }

    async with connect(
        endpoint=AZURE_ENDPOINT,
        credential=AzureKeyCredential(AZURE_KEY),
        model=AZURE_MODEL
    ) as azure_connection:
        
        await setup_session(azure_connection)
        
        receive_task = asyncio.create_task(handle_azure_output(azure_connection, websocket, state))
        tts_worker_task = asyncio.create_task(process_tts_queue(websocket, state))

        try:
            while True:
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
    session_config = RequestSession(
        modalities=[Modality.TEXT, Modality.AUDIO], 
        instructions=INSTRUCTIONS,
        input_audio_format=InputAudioFormat.PCM16,
        turn_detection=ServerVad(threshold=0.6, prefix_padding_ms=300, silence_duration_ms=500),
    )
    await connection.session.update(session=session_config)

async def handle_azure_output(connection, websocket: WebSocket, state):
    try:
        async for event in connection:
            if event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                state["interrupted"] = True
                state["text_buffer"] = "" 
                while not state["tts_queue"].empty():
                    try:
                        state["tts_queue"].get_nowait()
                        state["tts_queue"].task_done()
                    except asyncio.QueueEmpty:
                        break
                await websocket.send_text(json.dumps({"type": "interrupt"}))

            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                state["interrupted"] = False
                state["text_buffer"] += event.delta
                await websocket.send_text(json.dumps({"type": "agent_transcript_delta", "text": event.delta}))

                if re.search(r'[.!?।]\s*$', state["text_buffer"]):
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
    while True:
        text = await state["tts_queue"].get()
        if state["interrupted"]:
            state["tts_queue"].task_done()
            continue

        try:
            # ✅ RAW PCM 24000
            audio_stream = client_eleven.text_to_speech.convert(
                text=text,
                voice_id=state["voice_id"], # Dynamic Voice
                model_id="eleven_multilingual_v2", 
                output_format="pcm_24000" 
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