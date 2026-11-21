/**
 * TypeScript definitions matching contracts/*.schema.json verbatim.
 * Source of truth: SPEC.md and contracts/*.schema.json.
 */

export type EngineId = "B-GPU" | "B-Mac" | "A" | "replay";
export type LaneId = "target" | "raw" | "other";

export interface FaceBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface FaceConsent {
  given: boolean;
  by: string | null;
  time: string | null;
}

export interface Face {
  id: string;
  box: FaceBox;
  lips: [number, number][];
  mouth_open: number;
  color: string;
  consent: FaceConsent;
  is_target?: boolean;
  label?: string | null;
}

export interface Hop {
  session_id: string;
  seq: number;
  target_face_id: string | null;
  reset: boolean;
  pcm: string; // base64 int16 LE 16 kHz mono (8000 samples for 0.5 s)
  crops: string[]; // 12 or 13 base64 112x112 grayscale JPEGs
  t_capture: number; // Unix ms
  sample_rate?: 16000;
  hop_ms?: number;
  faces?: Face[];
  other_crops?: Record<string, string[]>;
  frame_jpeg?: string | null;
}

export interface HopResult {
  seq: number;
  pcm: string;
  gpu_ms: number;
  queue_ms: number;
  t_return: number;
  covers?: [number, number];
  samples?: number;
  t_capture?: number | null;
  sent_ms?: number | null;
  rtt_ms?: number;
  engine?: EngineId;
}

export interface CaptionSegment {
  t0: number;
  t1: number;
  lane: LaneId;
  face_id: string | null;
  text: string;
  confidence: number;
  engine: EngineId;
  segment_id?: string;
  is_final?: boolean;
  speaker_color?: string | null;
  translated_text?: string | null;
  latency_ms?: number;
  guarded?: boolean;
}

export interface SpeakingDecision {
  face_id: string;
  window_t0: number;
  window_t1: number;
  p_speaking: number;
  latency_ms: number;
  calibrated?: boolean;
  source?: "decision-1" | "mediapipe-uncalibrated";
}

export interface PipelineConfig {
  config_id: string;
  engine: EngineId;
  window_s: number;
  hop_s: number;
  decision_threshold: number;
  guard_ms: number;
  vocab: string[];
  translate_to: string | null;
  created_at?: string;
  parent_config_id?: string | null;
  notes?: string;
}

export interface RobotCommand {
  command_id: string;
  face_id: string;
  text: string;
  target_face_id: string | null;
  point: [number, number] | null; // [y, x] in 0..1000
  object_label: string | null;
  allowed?: boolean;
  hook_reason?: string | null;
  latency_ms?: number;
  time?: string;
}

export interface MemoryAnswer {
  question: string;
  answer: string;
  time: string | number | null;
  clip: string | null;
  confidence: number;
  source?: "argon" | "neon-transcript-only";
  latency_ms?: number;
  face_id?: string | null;
}

export interface AgentEvent {
  time: string;
  event_type: "tool_call" | "hook" | "eval" | "file_written" | "config_release" | "info";
  tool?: string;
  hook?: "gate_release" | "gate_privacy" | "gate_command" | "post_tool";
  decision?: "ALLOW" | "DENY";
  reason?: string;
  summary: string;
  metrics_before?: Record<string, number>;
  metrics_after?: Record<string, number>;
}

export interface LiveMetrics {
  engine: EngineId;
  engine_reason?: string;
  voice_delay_ms: number | null;
  caption_delay_ms: number | null;
  gpu_ms: number | null;
  rtt_ms: number | null;
  raw_leakage_pct: number | null;
  target_leakage_pct: number | null;
  leakage_source?: "csv" | "live";
  clips_count?: number;
  hop_ms?: number;
}

export interface WhereItBreaksRow {
  slice: string;
  condition: string;
  n: number;
  raw_leak_pct: number | null;
  target_leak_pct: number | null;
  target_wer_pct: number | null;
  delay_p50_ms: number | null;
}

export interface EndCardData {
  updated_at: string;
  set_c: {
    n_clips: number;
    b0_leak_pct: number | null;
    b0_wer_pct: number | null;
    engine_a_leak_pct: number | null;
    engine_a_wer_pct: number | null;
    engine_b_leak_pct: number | null;
    engine_b_wer_pct: number | null;
    beats_raw_gate_passed: boolean;
  };
  set_d: {
    n_windows: number;
    accuracy_at_0_9_pct: number | null;
    latency_p50_ms: number | null;
  };
  set_r: {
    n_pairs: number;
    point_correct: number;
    hook_denied_other: number;
  };
  delay: {
    voice_p50_ms: number | null;
    voice_p95_ms: number | null;
    caption_p50_ms: number | null;
    hops_logged: number;
  };
  where_it_breaks: WhereItBreaksRow[];
  repo_url: string;
}

// Client -> Backend WebSocket messages
export type ClientWsMessage =
  | { type: "hop"; payload: Hop }
  | { type: "set_target"; face_id: string | null; mode: "auto" | "pinned" }
  | { type: "set_consent"; face_id: string; consent: FaceConsent; label?: string | null }
  | { type: "ask_memory"; question: string }
  | { type: "request_summary" }
  | { type: "save_transcript"; conversation_id?: string }
  | { type: "robot_command"; face_id: string; text: string; frame_jpeg?: string | null }
  | { type: "replay_last_10s" };

// Backend -> Client WebSocket messages
export type ServerWsMessage =
  | { type: "hop_result"; payload: HopResult }
  | { type: "segment"; payload: CaptionSegment }
  | { type: "decision"; payload: SpeakingDecision }
  | { type: "engine_status"; engine: EngineId; reason?: string; hop_ms?: number }
  | { type: "metrics"; payload: LiveMetrics }
  | { type: "agent_event"; payload: AgentEvent }
  | { type: "memory_answer"; payload: MemoryAnswer }
  | { type: "robot_command"; payload: RobotCommand }
  | { type: "config"; payload: PipelineConfig }
  | { type: "end_card"; payload: EndCardData };
