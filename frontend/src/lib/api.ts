/**
 * Typed client for the Order Supervisor FastAPI backend.
 * Types mirror backend/app/api/schemas.py and backend/app/domain.py.
 */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };

export type RunStatus =
  | "starting"
  | "awake"
  | "sleeping"
  | "paused"
  | "completing"
  | "completed"
  | "terminated"
  | "failed";

export const TERMINAL_STATUSES: readonly RunStatus[] = ["completed", "terminated", "failed"];

export type TimelineKind =
  | "event"
  | "classification"
  | "wake"
  | "agent"
  | "tool"
  | "sleep"
  | "instruction"
  | "control"
  | "memory"
  | "system";

export const TIMELINE_KINDS: readonly TimelineKind[] = [
  "event",
  "classification",
  "wake",
  "agent",
  "tool",
  "sleep",
  "instruction",
  "control",
  "memory",
  "system",
];

export type WakeAggressiveness = "low" | "balanced" | "high";

export interface ToolSpec {
  name: string;
  description: string;
  parameters: JsonObject;
}

export interface Meta {
  action_tools: ToolSpec[];
  control_tools: ToolSpec[];
  event_types: string[];
  wake_aggressiveness: WakeAggressiveness[];
}

export interface Supervisor {
  id: string;
  name: string;
  base_instruction: string;
  tools: string[];
  default_wake_minutes: number;
  max_sleep_minutes: number;
  wake_aggressiveness: WakeAggressiveness;
  model: string | null;
  is_template: boolean;
  created_at: string;
}

export interface SupervisorCreate {
  name: string;
  base_instruction: string;
  tools: string[];
  default_wake_minutes: number;
  max_sleep_minutes: number;
  wake_aggressiveness: WakeAggressiveness;
  model: string | null;
}

export interface WakeGuidance {
  wake_on?: string[];
  ignore?: string[];
  note?: string;
}

export interface FinalReport {
  summary: string;
  outcome: string;
  key_actions: string[];
  learnings: string[];
  recommendations: string[];
}

export interface Run {
  id: string;
  order_id: string;
  supervisor_id: string;
  supervisor_name: string;
  workflow_id: string;
  status: RunStatus;
  order_status: string;
  order_context: JsonObject;
  memory_summary: string;
  next_wake_at: string | null;
  wake_guidance: WakeGuidance;
  instructions: string[];
  turn_count: number;
  pending_events: number;
  final_report: FinalReport | null;
  close_reason: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface TimelineEntry {
  id: number;
  at: string;
  kind: TimelineKind;
  title: string;
  detail: JsonObject;
  important: boolean;
}

export interface ToolExecution {
  tool: string;
  args: JsonObject;
  result: JsonObject;
  created_at: string;
}

export interface RunDetail extends Run {
  timeline: TimelineEntry[];
  tool_executions: ToolExecution[];
}

export interface RunCreate {
  supervisor_id: string;
  order_id: string;
  order_context: JsonObject;
  instructions: string[];
}

export interface Accepted {
  ok: boolean;
  message: string;
}

/** Error raised for non-2xx responses, with FastAPI's `detail` flattened into readable messages. */
export class ApiError extends Error {
  readonly status: number;
  readonly messages: string[];

  constructor(status: number, messages: string[]) {
    super(messages.join(" · ") || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.messages = messages;
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

function detailToMessages(detail: unknown): string[] {
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) {
    return detail.map((issue: ValidationIssue) => {
      const field = (issue.loc ?? []).filter((part) => part !== "body").join(".");
      const msg = (issue.msg ?? "Invalid value").replace(/^Value error, /, "");
      return field ? `${field}: ${msg}` : msg;
    });
  }
  return [];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, [`Cannot reach the API at ${API_URL}. Is the backend running?`]);
  }
  if (!response.ok) {
    let messages: string[] = [];
    try {
      const body: { detail?: unknown } = await response.json();
      messages = detailToMessages(body.detail);
    } catch {
      // Non-JSON error body; fall back to the status text.
    }
    throw new ApiError(response.status, messages.length ? messages : [response.statusText || `HTTP ${response.status}`]);
  }
  return (await response.json()) as T;
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string }>("/health"),
  meta: () => request<Meta>("/api/meta"),

  listSupervisors: () => request<Supervisor[]>("/api/supervisors"),
  getSupervisor: (id: string) => request<Supervisor>(`/api/supervisors/${encodeURIComponent(id)}`),
  createSupervisor: (body: SupervisorCreate) => post<Supervisor>("/api/supervisors", body),

  listRuns: (active?: boolean) => request<Run[]>(`/api/runs${active === undefined ? "" : `?active=${active}`}`),
  getRun: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  startRun: (body: RunCreate) => post<Run>("/api/runs", body),

  sendEvent: (runId: string, type: string, payload: JsonObject) =>
    post<Accepted>(`/api/runs/${encodeURIComponent(runId)}/events`, { type, payload, source: "ui" }),
  addInstruction: (runId: string, text: string, wakeAgent: boolean) =>
    post<Accepted>(`/api/runs/${encodeURIComponent(runId)}/instructions`, { text, wake_agent: wakeAgent }),
  interrupt: (runId: string, note: string) => post<Accepted>(`/api/runs/${encodeURIComponent(runId)}/interrupt`, { note }),
  pause: (runId: string) => post<Accepted>(`/api/runs/${encodeURIComponent(runId)}/pause`),
  resume: (runId: string) => post<Accepted>(`/api/runs/${encodeURIComponent(runId)}/resume`),
  terminate: (runId: string, reason: string) =>
    post<Accepted>(`/api/runs/${encodeURIComponent(runId)}/terminate`, { reason }),
};

export function isTerminal(status: RunStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
