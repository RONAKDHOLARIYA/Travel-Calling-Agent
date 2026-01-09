let socket;
let audioContext;
let processor;
let inputSource;
let selectedVoiceId = null,
  mediaRecorder,
  audioChunks = [],
  recordedBlob = null;
// Audio Queue Management
let nextStartTime = 0;
let audioQueue = []; // Tracks all active audio nodes
let ignoreAudio = false; // Flag to discard stale packets

let currentAgentBubble = null;

const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusMsg = document.getElementById("status-msg");
const visWrapper = document.getElementById("vis-wrapper");
const chatContainer = document.getElementById("chat-container");
const SAMPLE_RATE = 24000;
const HOST = "localhost:8000";
window.onload = async () => {
  await fetchAndRenderVoices();
};

async function fetchAndRenderVoices() {
  const grid = document.getElementById("avatarGrid");
  try {
    const res = await fetch(`https://${HOST}/voices`);
    const data = await res.json();

    grid.innerHTML = ""; // Clear loader

    if (data.voices.length === 0) {
      grid.innerHTML =
        "<p style='color:#888; width:100%;'>No voices found. Go to Clone tab!</p>";
      return;
    }

    // Colors to cycle through
    const styles = ["cyan", "pink", "purple"];
    const emojis = ["👨‍🚀", "👩‍🚀", "🤖", "👽", "🦸"];

    data.voices.forEach((v, index) => {
      const style = styles[index % styles.length];
      const emoji = emojis[index % emojis.length];

      // Create HTML for Avatar
      const div = document.createElement("div");
      div.className = `voice-option ${style}`;
      div.onclick = () => selectVoice(v.id, v.name, div);
      div.innerHTML = `<span class="emoji">${emoji}</span><span class="label">${v.name}</span>`;

      grid.appendChild(div);

      // Auto-select first one
      if (index === 0 && !selectedVoiceId) selectVoice(v.id, v.name, div);
    });
  } catch (e) {
    console.error(e);
    grid.innerHTML = "API Error";
  }
}

function selectVoice(id, name, el) {
  selectedVoiceId = id;

  // UI Updates
  document
    .querySelectorAll(".voice-option")
    .forEach((d) => d.classList.remove("selected"));
  el.classList.add("selected");

  // Update Main Button
  document.getElementById("currentVoiceName").innerText = name;
  document.getElementById("currentAvatar").innerText =
    el.querySelector(".emoji").innerText;

  // Close modal after short delay for effect
  // setTimeout(closeModal, 300);
}

function openModal() {
  const m = document.getElementById("voiceModal");
  m.style.display = "flex";
  setTimeout(() => m.classList.add("open"), 10);
}
function closeModal() {
  const m = document.getElementById("voiceModal");
  m.classList.remove("open");
  setTimeout(() => (m.style.display = "none"), 300);
}

startBtn.onclick = async () => {
  statusMsg.innerText = "Connecting to Lal Bhai...";
  try {
    socket = new WebSocket(`wss://${HOST}/call?voice_id=${selectedVoiceId}`);
    socket.binaryType = "arraybuffer";

    socket.onopen = async () => {
      statusMsg.innerText = "Listening...";
      startBtn.style.display = "none";
      stopBtn.style.display = "block";
      await startAudioCapture();
    };

    socket.onmessage = async (event) => {
      if (typeof event.data === "string") {
        const msg = JSON.parse(event.data);
        handleServerEvent(msg);
      } else {
        // Handle Audio Packet
        playPCMChunk(event.data);
      }
    };

    socket.onclose = () => resetUI();
  } catch (err) {
    console.error(err);
    statusMsg.innerText = "Connection Failed";
  }
};

stopBtn.onclick = () => {
  if (socket) socket.close();
  if (audioContext) audioContext.close();
  resetUI();
};

function resetUI() {
  statusMsg.innerText = "Session Ended";
  startBtn.style.display = "block";
  stopBtn.style.display = "none";
  visWrapper.classList.remove("speaking");
  stopAllAudio(); // Ensure silence
}

// --- CORE LOGIC: STOP EVERYTHING ---
function stopAllAudio() {
  console.log("🛑 STOPPING ALL AUDIO");

  // 1. Stop all queued source nodes
  audioQueue.forEach((source) => {
    try {
      source.stop();
    } catch (e) {}
  });
  audioQueue = []; // Clear the list

  // 2. Reset the timeline so next audio plays IMMEDIATELY
  if (audioContext) {
    nextStartTime = audioContext.currentTime;
  }

  // 3. Ignore incoming packets for a short moment (prevents network lag from playing old audio)
  ignoreAudio = true;
  setTimeout(() => {
    ignoreAudio = false;
  }, 500); // 500ms safety window
}

function handleServerEvent(msg) {
  if (msg.type === "interrupt") {
    // INTERRUPTION DETECTED
    stopAllAudio();

    // UI Cleanup
    visWrapper.classList.remove("speaking");
    if (currentAgentBubble) {
      currentAgentBubble.innerText += " ...";
      currentAgentBubble.classList.remove("typing");
      currentAgentBubble = null;
    }
  } else if (msg.type === "user_transcript") {
    addMessage(msg.text, "user-msg");
  } else if (msg.type === "agent_transcript_delta") {
    // If we get new text, it means a NEW response has started
    // So we stop ignoring audio (if we were)
    ignoreAudio = false;

    if (!currentAgentBubble) {
      currentAgentBubble = addMessage("", "agent-msg typing");
    }
    currentAgentBubble.innerText += msg.text;
    scrollToBottom();
  } else if (msg.type === "agent_response_done") {
    if (currentAgentBubble) {
      currentAgentBubble.classList.remove("typing");
      currentAgentBubble = null;
    }
  }
}

function playPCMChunk(arrayBuffer) {
  if (!audioContext || ignoreAudio) return; // Drop packet if we are ignoring

  // Update UI
  visWrapper.classList.add("speaking");
  clearTimeout(window.speakTimeout);
  window.speakTimeout = setTimeout(
    () => visWrapper.classList.remove("speaking"),
    300
  );

  // Convert PCM
  const int16Array = new Int16Array(arrayBuffer);
  const float32Array = new Float32Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    float32Array[i] = int16Array[i] / 32768;
  }

  const buffer = audioContext.createBuffer(1, float32Array.length, SAMPLE_RATE);
  buffer.copyToChannel(float32Array, 0);

  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.destination);

  // Scheduling
  const currentTime = audioContext.currentTime;
  if (nextStartTime < currentTime) nextStartTime = currentTime;
  source.start(nextStartTime);
  nextStartTime += buffer.duration;

  // --- QUEUE MANAGEMENT ---
  // Add to queue
  audioQueue.push(source);

  // Remove from queue when done playing
  source.onended = () => {
    audioQueue = audioQueue.filter((s) => s !== source);
  };
}

function addMessage(text, className) {
  const div = document.createElement("div");
  div.className = `message ${className}`;
  div.innerText = text;
  chatContainer.appendChild(div);
  scrollToBottom();
  return div;
}

function scrollToBottom() {
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function startAudioCapture() {
  audioContext = new (window.AudioContext || window.webkitAudioContext)({
    sampleRate: SAMPLE_RATE,
  });
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      sampleRate: SAMPLE_RATE,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });
  inputSource = audioContext.createMediaStreamSource(stream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);
  inputSource.connect(processor);
  processor.connect(audioContext.destination);

  processor.onaudioprocess = (e) => {
    if (socket.readyState === WebSocket.OPEN) {
      const inputData = e.inputBuffer.getChannelData(0);
      socket.send(floatTo16BitPCM(inputData));
    }
  };
}

function floatTo16BitPCM(output) {
  const buffer = new ArrayBuffer(output.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < output.length; i++) {
    let s = Math.max(-1, Math.min(1, output[i]));
    s = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(i * 2, s, true);
  }
  return buffer;
}
async function startRec() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(audioChunks, { type: "audio/webm" });
      document.getElementById("recordBtn").innerText = "✅ Captured";
    };
    mediaRecorder.start();
    document.getElementById("recordBtn").innerText = "🔴 Recording...";
  } catch (e) {
    alert("Mic Error");
  }
}
function stopRec() {
  if (mediaRecorder) mediaRecorder.stop();
}

async function submitClone() {
  const name = document.getElementById("cloneName").value;
  const file = document.getElementById("cloneFile").files[0];
  const status = document.getElementById("cloneStatus");

  const formData = new FormData();
  formData.append("name", name);
  if (recordedBlob) formData.append("files", recordedBlob, "mic.webm");
  else if (file) formData.append("files", file);
  else return (status.innerText = "❌ No Audio");

  status.innerText = "⏳ Uploading...";
  try {
    const res = await fetch(`https://${HOST}/clone`, {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (data.status === "success" || data.status === "exists") {
      status.innerText = "✅ Done!";
      await fetchAndRenderVoices();
      switchView("call");
      // Auto select new voice logic would go here
    } else status.innerText = "❌ Error";
  } catch (e) {
    status.innerText = "❌ Network Error";
  }
}
function switchView(v) {
  document
    .querySelectorAll(".view")
    .forEach((e) => e.classList.remove("active"));
  document
    .querySelectorAll(".tab")
    .forEach((e) => e.classList.remove("active"));
  document.getElementById(`view-${v}`).classList.add("active");
  // Simple tab index logic
  const idx = v === "call" ? 0 : 1;
  document.querySelectorAll(".tab")[idx].classList.add("active");
}
