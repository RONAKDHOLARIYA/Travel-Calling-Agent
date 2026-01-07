🎙️ Azure GPT-4o Realtime Voice Agent (POC)
===========================================

> A low-latency, multilingual voice-to-voice web assistant powered by Azure OpenAI's GPT-4o Realtime API.

📖 About The Project
--------------------

This Proof of Concept (POC) demonstrates a **next-generation Voice AI Agent** that runs entirely in the browser. Unlike traditional pipelines (Speech-to-Text → LLM → Text-to-Speech), this project uses **Azure's GPT-4o Realtime API** to process audio streams end-to-end. This results in ultra-low latency conversations that feel natural and human-like.

The current persona, **"Leela Ben"**, acts as a multilingual travel agent capable of switching seamlessly between **English, Hindi, and Gujarati**.

### ✨ Key Features

-   **⚡ Ultra-Low Latency:** Uses WebSocket streaming to bypass traditional transcoding delays.

-   **🗣️ Multilingual Support:** Automatically detects and speaks in **English, Hindi, and Gujarati** using Azure's polyglot neural voices.

-   **🛑 Interruptibility (Barge-in):** Users can interrupt the agent mid-sentence, and the AI instantly stops speaking and listens (Full Duplex).

-   **🌊 Reactive UI:** A modern, futuristic web interface with a real-time audio visualizer (orb) and live chat transcripts.

-   **🧠 Context Aware:** Maintains conversation history and adapts to user speed and tone.

🏗️ Architecture
----------------

Code snippet

```
graph TD;
    Browser[User Browser (Mic/Speaker)] <-->|WebSocket (Raw PCM)| Python[FastAPI Bridge];
    Python <-->|Azure SDk| Azure[Azure GPT-4o Realtime API];
    Azure -->|Audio Stream| Python;
    Azure -->|Transcripts| Python;
    Python -->|JSON Events| Browser;
```

1.  **Frontend (Vanilla JS):** Captures microphone input (downsampled to 24kHz), plays raw PCM audio, and visualizes state.

2.  **Backend (FastAPI):** Acts as a secure relay bridge. It manages the WebSocket connection and authenticates with Azure.

3.  **AI Core (Azure):** Handles VAD (Voice Activity Detection), STT, LLM logic, and TTS in a single "Realtime" session.

🚀 Getting Started
------------------

### Prerequisites

-   Python 3.10+

-   An Azure OpenAI Resource with `gpt-4o-realtime-preview` model deployed.

-   **API Key** and **Endpoint** for the resource.

### Installation

1.  **Clone the repo**

    Bash

    ```
    git clone https://github.com/RONAKDHOLARIYA/Travel-Calling-Agent.git
    cd Travel-Calling-Agent
    ```

2.  **Install Dependencies**

    Bash

    ```
    pip install -r requirements.txt
    ```

3.  Set Environment Variables

    Create a .env file or export them in your terminal:

    Bash

    ```
    export AZURE_VOICELIVE_API_KEY="your_key_here"
    export AZURE_VOICELIVE_ENDPOINT="wss://<your-region>.api.cognitive.microsoft.com"
    export VOICELIVE_MODEL="gpt-4o-realtime-preview"
    export VOICELIVE_VOICE="en-US-ShimmerTurboMultilingualNeural"
    ```

### Running the App

1.  **Start the Server**

    Bash

    ```
    python server.py
    ```

2.  Access the Interface

    Open your browser and navigate to:

    http://localhost:8000

📂 Project Structure
--------------------

-   `server.py`: Main FastAPI backend. Handles WebSocket bridging and Azure session configuration (System prompts, Voice ID).

-   `index.html`: The frontend client. Handles AudioContext, PCM conversion, queue management, and UI animations.

🧩 Customization
----------------

-   **Change Persona:** Edit the `INSTRUCTIONS` variable in `server.py` to change the agent's behavior (e.g., to a Doctor, Support Agent, or Teacher).

-   **Change Voice:** Update the `VOICE` variable in `server.py`. Recommended IDs:

    -   `en-US-BrianMultilingualNeural` (Fast/Casual)

    -   `en-US-AndrewMultilingualNeural` (Balanced)

    -   `en-US-AvaMultilingualNeural` (Female/Sharp)

🤝 Contributing
---------------

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

* * * * *

*Built with ❤️ using Azure OpenAI & FastAPI.*
