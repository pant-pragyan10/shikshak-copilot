/**
 * The single typed API client. Every call to the FastAPI backend goes through here —
 * never hardcode URLs in components. Base URL is env-driven so prod points at the
 * hosted backend.
 */
import type {
  ApiErrorBody,
  BatchGradeRequest,
  BatchGradeResponse,
  CareerGuidance,
  CareerRequest,
  ChatRequest,
  ChatResponse,
  GradeRequest,
  GradedResult,
  LessonPlan,
  LessonPlanRequest,
  ProfileUpsert,
  TeacherProfile,
  WorkloadEntry,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

/** A backend error mapped from the `{error: {type, message}}` envelope. */
export class ApiError extends Error {
  type: string;
  status: number;
  constructor(message: string, type: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.type = type;
    this.status = status;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let type = "http_error";
  let message = `Request failed (${res.status}).`;
  try {
    const body = (await res.json()) as Partial<ApiErrorBody>;
    if (body.error) {
      type = body.error.type ?? type;
      message = body.error.message ?? message;
    }
  } catch {
    /* non-JSON error body — keep defaults */
  }
  return new ApiError(message, type, res.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: string;
  version: string;
  env: string;
  providers: Record<string, Record<string, boolean>>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  chat: (body: ChatRequest) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(body) }),

  grade: (body: GradeRequest) =>
    request<GradedResult>("/grade", { method: "POST", body: JSON.stringify(body) }),

  gradeBatch: (body: BatchGradeRequest) =>
    request<BatchGradeResponse>("/grade/batch", { method: "POST", body: JSON.stringify(body) }),

  gradeImage: async (params: {
    file: File;
    question: string;
    rubricJson?: string;
    teacherId?: string;
  }): Promise<GradedResult> => {
    const form = new FormData();
    form.append("file", params.file);
    form.append("question", params.question);
    if (params.rubricJson) form.append("rubric_json", params.rubricJson);
    if (params.teacherId) form.append("teacher_id", params.teacherId);
    const res = await fetch(`${API_BASE}/grade/image`, { method: "POST", body: form });
    if (!res.ok) throw await toApiError(res);
    return (await res.json()) as GradedResult;
  },

  lessonPlan: (body: LessonPlanRequest) =>
    request<LessonPlan>("/lesson-plan", { method: "POST", body: JSON.stringify(body) }),

  career: (body: CareerRequest) =>
    request<CareerGuidance>("/career", { method: "POST", body: JSON.stringify(body) }),

  getProfile: (teacherId: string) =>
    request<TeacherProfile>(`/profile/${encodeURIComponent(teacherId)}`),

  putProfile: (teacherId: string, body: ProfileUpsert) =>
    request<TeacherProfile>(`/profile/${encodeURIComponent(teacherId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  addWorkload: (teacherId: string, entry: WorkloadEntry) =>
    request<TeacherProfile>(`/profile/${encodeURIComponent(teacherId)}/workload`, {
      method: "POST",
      body: JSON.stringify(entry),
    }),
};
