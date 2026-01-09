# Hybrid Voice Agent (Azure Realtime + ElevenLabs)

A high-fidelity, low-latency voice AI agent designed for multilingual conversations (English, Hindi, Gujarati). 

This project demonstrates a **Hybrid Architecture** that combines the reasoning speed of **Azure OpenAI Realtime API** with the superior voice quality of **ElevenLabs**, synchronized via a custom **24kHz Raw PCM** audio pipeline.

## 🚀 Key Features

* **Hybrid Intelligence:** Uses **Azure GPT-4o Realtime** for "Brain" (Logic & STT).
* **Premium Voice:** Uses **ElevenLabs Multilingual v2** for "Voice" (TTS).
* **True Duplex:** Supports **Barge-in** (Interruption)—the user can speak over the bot, and the bot stops immediately.
* **High-Fidelity Audio:** Runs on a custom **24kHz Raw PCM** pipeline (no MP3 compression) to ensure crystal-clear quality and perfect playback speed.
* **Cost Optimized:** Configured to support `gpt-4o-mini-realtime-preview` for 10x lower costs.
* **Smart Queueing:** Handles TTS concurrency limits automatically.

## 🛠️ Architecture

1.  **Browser (Frontend):** Captures Microphone at **24kHz** (Required by Azure) and plays received audio raw.
2.  **Server (Python/FastAPI):** * Forwards input audio to **Azure**.
    * Receives text tokens from Azure.
    * Buffers sentences and sends them to **ElevenLabs**.
3.  **ElevenLabs:** Streams **24kHz Raw PCM** audio bytes back to the browser.

## 📋 Prerequisites

* **Python 3.10+**
* **Azure OpenAI Account** (with Realtime API access)
* **ElevenLabs Account** (with API Key)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/RONAKDHOLARIYA/Travel-Calling-Agent.git
    cd Travel-Calling-Agent
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

Create a `.env` file in the root directory and add your keys. 

**Recommended for Low Cost:** Use the `mini` model.

```env
# --- AZURE CONFIGURATION ---
AZURE_VOICELIVE_API_KEY=your_azure_api_key_here
AZURE_VOICELIVE_ENDPOINT=https://your-resource-name.openai.azure.com

# Model: Use 'gpt-4o-realtime-preview' (High Intellect) or 'gpt-4o-mini-realtime-preview' (Low Cost)
AZURE_VOICELIVE_MODEL=gpt-4o-mini-realtime-preview

# --- ELEVENLABS CONFIGURATION ---
ELEVENLABS_API_KEY=your_elevenlabs_key_here
