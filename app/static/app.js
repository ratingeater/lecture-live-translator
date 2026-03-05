const sourceTranscript = document.getElementById("sourceTranscript");
const translatedTranscript = document.getElementById("translatedTranscript");
const connectionStatus = document.getElementById("connectionStatus");
const runtimeHint = document.getElementById("runtimeHint");
const detectedLanguage = document.getElementById("detectedLanguage");
const targetLanguageBadge = document.getElementById("targetLanguageBadge");
const startButton = document.getElementById("startButton");
const stopButton = document.getElementById("stopButton");
const clearButton = document.getElementById("clearButton");
const offlineForm = document.getElementById("offlineForm");
const offlineResult = document.getElementById("offlineResult");

const projectIdInput = document.getElementById("projectId");
const speechLocationInput = document.getElementById("speechLocation");
const sourceModeInput = document.getElementById("sourceMode");
const sourceLanguageInput = document.getElementById("sourceLanguage");
const targetLanguageInput = document.getElementById("targetLanguage");
const translateInterimInput = document.getElementById("translateInterim");

let audioContext;
let mediaStream;
let processorNode;
let websocket;
let interimSourceNode = null;
let interimTranslationNode = null;

function syncSourceMode() {
  const autoMode = sourceModeInput.value === "auto";
  sourceLanguageInput.disabled = autoMode;
}

function addSegment(container, text, className = "") {
  const element = document.createElement("div");
  element.className = `segment ${className}`.trim();
  element.textContent = text;
  container.appendChild(element);
  container.scrollTop = container.scrollHeight;
  return element;
}

function clearInterimNodes() {
  if (interimSourceNode) {
    interimSourceNode.remove();
    interimSourceNode = null;
  }
  if (interimTranslationNode) {
    interimTranslationNode.remove();
    interimTranslationNode = null;
  }
}

function resetTranscripts() {
  sourceTranscript.textContent = "";
  translatedTranscript.textContent = "";
  clearInterimNodes();
}

function setStatus(text, hint, tone = "idle") {
  connectionStatus.textContent = text;
  runtimeHint.textContent = hint;
  const toneMap = {
    idle: ["#d8efe8", "#005f73"],
    live: ["#d9f7c8", "#1c6e2f"],
    warn: ["#ffe3c2", "#a14a11"],
    error: ["#ffd8d8", "#972222"],
  };
  const [bg, fg] = toneMap[tone] || toneMap.idle;
  connectionStatus.style.background = bg;
  connectionStatus.style.color = fg;
}

function floatTo16BitPCM(floatBuffer) {
  const int16 = new Int16Array(floatBuffer.length);
  for (let i = 0; i < floatBuffer.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, floatBuffer[i]));
    int16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return int16.buffer;
}

async function startListening() {
  if (!projectIdInput.value.trim()) {
    setStatus("缺少配置", "请先填写 GCP Project ID。", "warn");
    return;
  }

  targetLanguageBadge.textContent = targetLanguageInput.value;
  setStatus("连接中", "正在请求麦克风和建立 WebSocket...", "warn");

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      noiseSuppression: true,
      autoGainControl: false,
      echoCancellation: false,
    },
  });

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  websocket = new WebSocket(`${protocol}://${window.location.host}/ws/realtime`);
  websocket.binaryType = "arraybuffer";

  websocket.onopen = async () => {
    websocket.send(
      JSON.stringify({
        project_id: projectIdInput.value.trim(),
        speech_location: speechLocationInput.value,
        source_mode: sourceModeInput.value,
        source_language: sourceLanguageInput.value,
        auto_languages: ["ru-RU", "en-US", "ja-JP"],
        target_language: targetLanguageInput.value,
        sample_rate_hz: 16000,
        channel_count: 1,
        translate_interim: translateInterimInput.checked,
      }),
    );

    audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(mediaStream);
    processorNode = audioContext.createScriptProcessor(4096, 1, 1);
    source.connect(processorNode);
    processorNode.connect(audioContext.destination);
    processorNode.onaudioprocess = (event) => {
      if (!websocket || websocket.readyState !== WebSocket.OPEN) {
        return;
      }
      const samples = event.inputBuffer.getChannelData(0);
      websocket.send(floatTo16BitPCM(samples));
    };

    startButton.disabled = true;
    stopButton.disabled = false;
    setStatus("直播中", "实时转写已启动。讲话时请保持稳定音量。", "live");
  };

  websocket.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "status") {
      setStatus("已连接", payload.message || "服务已连接。", "live");
      return;
    }
    if (payload.type === "error") {
      setStatus("错误", payload.message || "发生错误。", "error");
      return;
    }
    if (payload.type !== "transcript") {
      return;
    }

    detectedLanguage.textContent = `语言: ${payload.language_code || "-"}`;
    if (payload.is_final) {
      clearInterimNodes();
      addSegment(sourceTranscript, payload.transcript || "");
      addSegment(translatedTranscript, payload.translation || "");
    } else {
      if (!interimSourceNode) {
        interimSourceNode = addSegment(sourceTranscript, "", "interim");
      }
      if (!interimTranslationNode) {
        interimTranslationNode = addSegment(translatedTranscript, "", "interim");
      }
      interimSourceNode.textContent = payload.transcript || "";
      interimTranslationNode.textContent = payload.translation || "";
      sourceTranscript.scrollTop = sourceTranscript.scrollHeight;
      translatedTranscript.scrollTop = translatedTranscript.scrollHeight;
    }
  };

  websocket.onclose = () => {
    stopListening(false);
    setStatus("已断开", "实时连接已结束。", "idle");
  };

  websocket.onerror = () => {
    setStatus("连接失败", "WebSocket 出错，请检查后端和 GCP 凭据。", "error");
  };
}

function stopListening(closeSocket = true) {
  if (processorNode) {
    processorNode.disconnect();
    processorNode.onaudioprocess = null;
    processorNode = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  if (closeSocket && websocket) {
    websocket.close();
  }
  websocket = null;
  startButton.disabled = false;
  stopButton.disabled = true;
}

startButton.addEventListener("click", async () => {
  try {
    await startListening();
  } catch (error) {
    console.error(error);
    stopListening();
    setStatus("启动失败", error.message || "无法启动麦克风。", "error");
  }
});

stopButton.addEventListener("click", () => {
  stopListening();
  setStatus("已停止", "实时监听已停止。", "idle");
});

clearButton.addEventListener("click", () => {
  resetTranscripts();
  detectedLanguage.textContent = "语言: -";
});

targetLanguageInput.addEventListener("change", () => {
  targetLanguageBadge.textContent = targetLanguageInput.value;
});

sourceModeInput.addEventListener("change", syncSourceMode);
syncSourceMode();

offlineForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fileInput = document.getElementById("offlineFile");
  if (!fileInput.files.length) {
    offlineResult.textContent = "请先选择音频或视频文件。";
    return;
  }
  if (!projectIdInput.value.trim()) {
    offlineResult.textContent = "请先填写 GCP Project ID。";
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("project_id", projectIdInput.value.trim());
  formData.append("speech_location", speechLocationInput.value);
  formData.append("source_mode", sourceModeInput.value);
  formData.append("source_language", sourceLanguageInput.value);
  formData.append("target_language", targetLanguageInput.value);

  offlineResult.textContent = "正在上传并提交批处理，请稍候...";
  try {
    const response = await fetch("/api/batch-transcribe", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "批处理失败");
    }
    offlineResult.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    offlineResult.textContent = error.message || "批处理失败。";
  }
});
