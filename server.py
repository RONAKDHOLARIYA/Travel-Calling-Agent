import os
import asyncio
import base64
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# Azure VoiceLive Imports
from azure.core.credentials import AzureKeyCredential
from azure.ai.voicelive.aio import connect
from azure.ai.voicelive.models import (
    ServerEventType,
    ServerVad,
    AzureStandardVoice,
    Modality,
    InputAudioFormat,
    OutputAudioFormat,
    RequestSession
)
from dotenv import load_dotenv

load_dotenv()
# Configuration
API_KEY = os.environ.get("AZURE_VOICELIVE_API_KEY", "YOUR_API_KEY")
ENDPOINT = os.environ.get("AZURE_VOICELIVE_ENDPOINT", "YOUR_ENDPOINT")
MODEL = os.environ.get("VOICELIVE_MODEL", "gpt-4o-realtime-preview")
VOICE =os.environ.get("VOICELIVE_VOICE", "en-US-ShimmerTurboMultilingualNeural") # Changed to an Indian English voice for better fit
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
* Normalization: Write out and normalize all text. For example, '$2.35' should be 'two dollars and thirty-five cents,' and '100 km/h' should be 'one hundred kilometers per hour.'

Constraints
-----------
* Keep responses brief, under five sentences.
* Use only standard alphabet characters and basic punctuation.

User Personalization
--------------------
Ask for basic details early: 'Where are you traveling from?', 'Budget?', 'Type of experience?'. Based on this, provide personalized suggestions.
"""

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LalBhaiAgent")



@app.websocket("/call")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Web client connected")

    async with connect(
        endpoint=ENDPOINT,
        credential=AzureKeyCredential(API_KEY),
        model=MODEL
    ) as azure_connection:
        
        await setup_session(azure_connection)
        
        # Concurrent tasks for stream handling
        receive_task = asyncio.create_task(handle_azure_events(azure_connection, websocket))
        
        try:
            while True:
                # Receive PCM from browser
                data = await websocket.receive_bytes()
                audio_base64 = base64.b64encode(data).decode("utf-8")
                await azure_connection.input_audio_buffer.append(audio=audio_base64)
                
        except WebSocketDisconnect:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            receive_task.cancel()

async def setup_session(connection):
    """Configures the Session with Leela Ben Persona"""
    session_config = RequestSession(
        modalities=[Modality.TEXT, Modality.AUDIO],
        instructions=INSTRUCTIONS, # <--- INJECTED HERE
        voice=AzureStandardVoice(name=VOICE, type="azure-standard", rate="1.1"),
        input_audio_format=InputAudioFormat.PCM16,
        output_audio_format=OutputAudioFormat.PCM16,
        turn_detection=ServerVad(threshold=0.5, prefix_padding_ms=300, silence_duration_ms=500),
    )
    await connection.session.update(session=session_config)
    logger.info("Leela Ben Persona Configured")

async def handle_azure_events(connection, websocket: WebSocket):
    try:
        async for event in connection:
            if event.type == ServerEventType.RESPONSE_AUDIO_DELTA:
                await websocket.send_bytes(event.delta)
            
            elif event.type == ServerEventType.CONVERSATION_ITEM_INPUT_AUDIO_TRANSCRIPTION_COMPLETED:
                await websocket.send_text(json.dumps({
                    "type": "user_transcript",
                    "text": event.transcript
                }))

            elif event.type == ServerEventType.RESPONSE_AUDIO_TRANSCRIPT_DELTA:
                await websocket.send_text(json.dumps({
                    "type": "agent_transcript_delta",
                    "text": event.delta
                }))

            elif event.type == ServerEventType.RESPONSE_DONE:
                await websocket.send_text(json.dumps({
                    "type": "agent_response_done"
                }))

            elif event.type == ServerEventType.INPUT_AUDIO_BUFFER_SPEECH_STARTED:
                await websocket.send_text(json.dumps({"type": "interrupt"}))
                
            elif event.type == ServerEventType.ERROR:
                logger.error(f"Azure Error: {event.error.message}")
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in event loop: {e}")

@app.get("/")
async def get():
    with open("index.html", "r") as f:
        return HTMLResponse(f.read())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)