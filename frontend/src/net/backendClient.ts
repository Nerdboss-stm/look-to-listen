/**
 * WebSocket + REST client connecting the browser to FastAPI backend (/ws/live).
 * Never queues stale hops: if the socket buffer backs up (> 256 KB), drops the hop.
 */

import type {
  ClientWsMessage,
  EndCardData,
  Hop,
  MemoryAnswer,
  RobotCommand,
  ServerWsMessage,
} from "../types/contracts";

export type ConnectionState = "disconnected" | "connecting" | "connected";

export interface BackendClientCallbacks {
  onStateChange: (state: ConnectionState) => void;
  onMessage: (msg: ServerWsMessage) => void;
}

const MAX_BUFFERED_BYTES = 256 * 1024;

export class BackendClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private stopped = false;
  private state: ConnectionState = "disconnected";
  private readonly callbacks: BackendClientCallbacks;
  private readonly wsUrl: string;
  private readonly apiBase: string;

  constructor(callbacks: BackendClientCallbacks, customBackendOrigin?: string) {
    this.callbacks = callbacks;
    const origin =
      customBackendOrigin ||
      new URLSearchParams(window.location.search).get("backend") ||
      window.location.origin;
    const url = new URL(origin);
    const wsProto = url.protocol === "https:" ? "wss:" : "ws:";
    this.wsUrl = `${wsProto}//${url.host}/ws/live`;
    this.apiBase = `${url.protocol}//${url.host}`;
  }

  connect(): void {
    this.stopped = false;
    this.openSocket();
  }

  private setState(next: ConnectionState): void {
    if (this.state !== next) {
      this.state = next;
      this.callbacks.onStateChange(next);
    }
  }

  private openSocket(): void {
    if (this.stopped) return;
    this.setState("connecting");
    try {
      const ws = new WebSocket(this.wsUrl);
      this.ws = ws;
      ws.onopen = () => {
        this.setState("connected");
      };
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(String(ev.data)) as ServerWsMessage;
          if (parsed && typeof parsed.type === "string") {
            this.callbacks.onMessage(parsed);
          }
        } catch {
          // Ignore malformed non-JSON messages
        }
      };
      ws.onclose = () => {
        this.ws = null;
        this.setState("disconnected");
        if (!this.stopped) {
          this.reconnectTimer = window.setTimeout(() => this.openSocket(), 1500);
        }
      };
      ws.onerror = () => {
        // onclose handles reconnect cleanly
      };
    } catch {
      this.setState("disconnected");
      if (!this.stopped) {
        this.reconnectTimer = window.setTimeout(() => this.openSocket(), 1500);
      }
    }
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * Sends a Hop if connected and socket buffer is not congested.
   * Returns false if dropped due to backpressure or disconnected state.
   */
  sendHop(hop: Hop): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    if (this.ws.bufferedAmount > MAX_BUFFERED_BYTES) {
      return false;
    }
    const msg: ClientWsMessage = { type: "hop", payload: hop };
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  send(msg: ClientWsMessage): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  async fetchEndCard(): Promise<EndCardData | null> {
    try {
      const res = await fetch(`${this.apiBase}/api/end_card`);
      if (!res.ok) return null;
      return (await res.json()) as EndCardData;
    } catch {
      return null;
    }
  }

  async fetchHealth(): Promise<{
    gpuName: string | null;
    gpuMsLast: number | null;
  } | null> {
    try {
      const res = await fetch(`${this.apiBase}/api/health`);
      if (!res.ok) return null;
      const data = (await res.json()) as {
        gpu_health?: { gpu?: string; gpu_ms_last20?: number[] };
      };
      const rawGpu = data?.gpu_health?.gpu ?? null;
      // Shorten e.g. "NVIDIA GeForce RTX 4090" -> "RTX 4090"
      const gpuName = rawGpu
        ? rawGpu.replace(/^NVIDIA\s+(GeForce\s+|Tesla\s+)?/i, "").trim()
        : null;
      const arr = data?.gpu_health?.gpu_ms_last20;
      const gpuMsLast =
        Array.isArray(arr) && arr.length > 0 ? arr[arr.length - 1] : null;
      return { gpuName, gpuMsLast };
    } catch {
      return null;
    }
  }

  async askMemoryRest(question: string): Promise<MemoryAnswer | null> {
    try {
      const res = await fetch(`${this.apiBase}/api/memory/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) return null;
      return (await res.json()) as MemoryAnswer;
    } catch {
      return null;
    }
  }

  async triggerRobotCommandRest(params: {
    face_id: string;
    text: string;
    target_face_id: string | null;
    frame_jpeg?: string | null;
  }): Promise<RobotCommand | null> {
    try {
      const res = await fetch(`${this.apiBase}/api/robot/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) return null;
      return (await res.json()) as RobotCommand;
    } catch {
      return null;
    }
  }

  async saveTranscriptRest(conversationId?: string): Promise<unknown> {
    try {
      const res = await fetch(`${this.apiBase}/api/agent/save_transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: conversationId ?? "live" }),
      });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    }
  }

  disconnect(): void {
    this.stopped = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setState("disconnected");
  }
}
