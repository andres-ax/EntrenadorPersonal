// Cliente de llamada por voz para /app/llamar (mini app Telegram).
// Portado a vanilla JS desde frontend/miniapp/src/pages/Llamar.tsx.
//
// El JWT del usuario viaja por query string al WebSocket (es la unica forma:
// las cookies HttpOnly NO se envian en upgrade WS handshakes en todos los
// navegadores). El servidor lo valida en src/realtime/server.py.

(function () {
  "use strict";

  const REALTIME_WS_DEFAULT =
    "wss://" + location.host + "/ws/realtime";

  // -------- helpers DOM --------
  const $ = (id) => document.getElementById(id);
  const log = (msg) => {
    const el = $("call-log");
    if (el) {
      const p = document.createElement("p");
      p.className = "text-xs";
      p.textContent = msg;
      el.appendChild(p);
      el.scrollTop = el.scrollHeight;
    }
  };
  const setEstado = (estado) => {
    $("call-state").textContent = estado;
    document.body.dataset.callState = estado;
  };
  const setError = (msg) => {
    const el = $("call-error");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("hidden", !msg);
  };

  // -------- Telegram WebApp helpers --------
  const tg = window.Telegram && window.Telegram.WebApp;
  const haptic = (style) => {
    try {
      tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(style);
    } catch (_) {}
  };
  const notifyHaptic = (type) => {
    try {
      tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(type);
    } catch (_) {}
  };

  // -------- conversion PCM16 <-> Float32 --------
  function floatToPCM16(f32) {
    const pcm = new Int16Array(f32.length);
    for (let i = 0; i < f32.length; i++) {
      const s = Math.max(-1, Math.min(1, f32[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return pcm;
  }

  async function reproducirAudio(buffer) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      const pcm = new Int16Array(buffer);
      const f32 = new Float32Array(pcm.length);
      for (let i = 0; i < pcm.length; i++) f32[i] = pcm[i] / 0x8000;
      const audioBuf = ctx.createBuffer(1, f32.length, 24000);
      audioBuf.copyToChannel(f32, 0);
      const source = ctx.createBufferSource();
      source.buffer = audioBuf;
      source.connect(ctx.destination);
      source.start();
    } catch (e) {
      console.error("Error reproduciendo audio", e);
    }
  }

  // -------- estado global --------
  let ws = null;
  let media = null;
  let audioCtx = null;

  function terminar() {
    try {
      ws && ws.close();
    } catch (_) {}
    ws = null;
    try {
      media && media.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    media = null;
    try {
      audioCtx && audioCtx.close();
    } catch (_) {}
    audioCtx = null;
    setEstado("idle");
  }

  async function iniciar() {
    haptic("medium");
    setError(null);
    setEstado("conectando");
    $("call-log").innerHTML = "";

    // El JWT lo expone el server inyectandolo en el HTML como
    // <meta name="user-jwt" content="..."> (ver llamar.html).
    const meta = document.querySelector('meta[name="user-jwt"]');
    const jwt = meta ? meta.content : "";
    if (!jwt) {
      setError("Sesion expirada. Cerra y volve a abrir el mini app desde Telegram.");
      setEstado("error");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      media = stream;
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });

      const wsBase = (document.querySelector('meta[name="realtime-ws"]') || {}).content || REALTIME_WS_DEFAULT;
      ws = new WebSocket(wsBase + "?token=" + encodeURIComponent(jwt));
      ws.binaryType = "arraybuffer";

      ws.onopen = function () {
        setEstado("en_llamada");
        notifyHaptic("success");
        const source = audioCtx.createMediaStreamSource(stream);
        // ScriptProcessorNode esta deprecated pero funciona en Telegram WebView.
        // Para upgrade a AudioWorkletNode, ver MDN AudioWorklet.
        const processor = audioCtx.createScriptProcessor(4096, 1, 1);
        source.connect(processor);
        processor.connect(audioCtx.destination);
        processor.onaudioprocess = function (e) {
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          const input = e.inputBuffer.getChannelData(0);
          const pcm16 = floatToPCM16(input);
          ws.send(pcm16.buffer);
        };
      };

      ws.onmessage = async function (event) {
        if (typeof event.data === "string") {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "transcript") {
              log(msg.role + ": " + msg.text);
            } else if (msg.type === "cuota") {
              const restantes = msg.segundos_restantes || 0;
              const m = Math.floor(restantes / 60);
              const s = String(restantes % 60).padStart(2, "0");
              $("call-quota").textContent = "Quedan " + m + ":" + s;
              if (restantes <= 0) {
                setEstado("sin_cuota");
                terminar();
              }
            } else if (msg.type === "error") {
              setError(msg.message || "Error del servidor");
              setEstado("error");
            }
          } catch (_) {}
        } else {
          await reproducirAudio(event.data);
        }
      };

      ws.onerror = function (err) {
        console.error("WS error", err);
        setError("Conexion fallida");
        setEstado("error");
      };
      ws.onclose = function () {
        if (document.body.dataset.callState === "en_llamada") {
          setEstado("terminada");
        }
      };
    } catch (e) {
      console.error(e);
      setError((e && e.message) || "No pude acceder al microfono");
      setEstado("error");
      notifyHaptic("error");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (tg) {
      try { tg.ready(); tg.expand(); } catch (_) {}
    }
    $("btn-iniciar").addEventListener("click", iniciar);
    $("btn-terminar").addEventListener("click", terminar);
    $("btn-volver").addEventListener("click", iniciar);
    window.addEventListener("beforeunload", terminar);
  });
})();
