import { useEffect, useRef, useState } from "react";
import { getJwt } from "../lib/api";
import { haptic, notifyHaptic } from "../lib/telegram";

const REALTIME_WS =
  import.meta.env.VITE_REALTIME_WS_URL || "wss://realtime.entrenadorax.com/ws/realtime";

type Estado = "idle" | "conectando" | "en_llamada" | "terminada" | "error" | "sin_cuota";

export function Llamar() {
  const [estado, setEstado] = useState<Estado>("idle");
  const [transcript, setTranscript] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [segundosRestantes, setSegundosRestantes] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    return () => terminar();
  }, []);

  async function iniciar() {
    haptic("medium");
    setError(null);
    setEstado("conectando");
    setTranscript([]);
    const jwt = getJwt();
    if (!jwt) {
      setError("Sesion expirada. Cierra y vuelve a abrir desde Telegram.");
      setEstado("error");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRef.current = stream;
      audioCtxRef.current = new AudioContext({ sampleRate: 24000 });

      const ws = new WebSocket(`${REALTIME_WS}?token=${encodeURIComponent(jwt)}`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        setEstado("en_llamada");
        notifyHaptic("success");
        const ctx = audioCtxRef.current!;
        const source = ctx.createMediaStreamSource(stream);
        const processor = ctx.createScriptProcessor(4096, 1, 1);
        source.connect(processor);
        processor.connect(ctx.destination);
        processor.onaudioprocess = (e) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          const input = e.inputBuffer.getChannelData(0);
          const pcm16 = floatToPCM16(input);
          ws.send(pcm16.buffer);
        };
      };

      ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === "transcript") {
              setTranscript((t) => [...t, `${msg.role}: ${msg.text}`]);
            } else if (msg.type === "cuota") {
              setSegundosRestantes(msg.segundos_restantes);
              if (msg.segundos_restantes <= 0) {
                setEstado("sin_cuota");
                terminar();
              }
            } else if (msg.type === "error") {
              setError(msg.message || "Error de servidor");
              setEstado("error");
            }
          } catch {}
        } else {
          await reproducirAudio(event.data as ArrayBuffer);
        }
      };

      ws.onerror = (e) => {
        console.error("WS error", e);
        setError("Conexion fallida");
        setEstado("error");
      };
      ws.onclose = () => {
        if (estado === "en_llamada") setEstado("terminada");
      };
    } catch (e: any) {
      console.error(e);
      setError(e?.message || "No pude acceder al microfono");
      setEstado("error");
      notifyHaptic("error");
    }
  }

  function terminar() {
    try {
      wsRef.current?.close();
    } catch {}
    wsRef.current = null;
    try {
      mediaRef.current?.getTracks().forEach((t) => t.stop());
    } catch {}
    mediaRef.current = null;
    try {
      audioCtxRef.current?.close();
    } catch {}
    audioCtxRef.current = null;
  }

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Llamar al coach</h1>
      <p className="text-sm text-slate-500">
        Conversa con el coach IA en tiempo real. Disponible desde plan Starter (trial 5 min).
      </p>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {estado === "idle" && (
        <button className="btn-primary w-full" onClick={iniciar}>
          Iniciar llamada
        </button>
      )}
      {estado === "conectando" && <p>Conectando...</p>}
      {estado === "en_llamada" && (
        <>
          <button className="btn-secondary w-full" onClick={terminar}>
            Terminar llamada
          </button>
          {segundosRestantes !== null && (
            <p className="text-xs text-slate-500">
              Quedan ~{Math.floor(segundosRestantes / 60)}:{String(segundosRestantes % 60).padStart(2, "0")}
            </p>
          )}
        </>
      )}
      {estado === "sin_cuota" && (
        <p className="text-amber-600">Se acabaron tus minutos. Mejora tu plan para mas.</p>
      )}
      {estado === "terminada" && (
        <button className="btn-primary w-full" onClick={iniciar}>
          Volver a llamar
        </button>
      )}

      {transcript.length > 0 && (
        <div className="card max-h-60 overflow-y-auto">
          <h3 className="text-sm font-semibold">Transcripcion</h3>
          {transcript.map((l, i) => (
            <p key={i} className="text-xs">{l}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function floatToPCM16(float32: Float32Array): Int16Array {
  const pcm = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}

async function reproducirAudio(buffer: ArrayBuffer) {
  try {
    const ctx = new AudioContext({ sampleRate: 24000 });
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
