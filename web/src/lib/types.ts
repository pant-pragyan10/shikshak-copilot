/**
 * TypeScript mirror of the backend API contract.
 *
 * Source of truth: `src/teacher_copilot/api/schemas.py` and the agent domain models
 * (grading_models.py, lesson_plan_models.py, career_models.py, wellbeing.py,
 * profile.py). Keep these in sync with the FastAPI backend — do not invent fields.
 */

export type Intent = "grading" | "lesson_plan" | "wellbeing" | "career" | "general";
export type Board = "CBSE" | "ICSE" | "STATE";

// --- grading --------------------------------------------------------------------
export interface RubricCriterion {
  name: string;
  description: string;
  max_marks: number;
}
export interface Rubric {
  criteria: RubricCriterion[];
  subject?: string | null;
  grade_level?: string | null;
  question?: string | null;
}
export interface CriterionScore {
  criterion_name: string;
  awarded_marks: number;
  max_marks: number;
  justification: string;
}
export interface GradedResult {
  scores: CriterionScore[];
  total_awarded: number;
  total_max: number;
  percentage: number;
  strengths: string[];
  improvements: string[];
  overall_comment: string;
  status: "graded" | "needs_review";
  confidence: number;
  rubric?: Rubric | null;
  rubric_source: "teacher" | "auto";
  adjustments: string[];
  raw_output?: string | null;
}
export interface GradingError {
  message: string;
  error_type: string;
  student_identifier?: string | null;
}

// --- lesson plan ----------------------------------------------------------------
export type Grounding = "curriculum_grounded" | "partial" | "general_knowledge";
export interface LessonSegment {
  title: string;
  minutes: number;
  activities: string[];
  teacher_notes: string;
}
export interface Citation {
  source: string;
  snippet: string;
}
export interface LessonPlan {
  topic: string;
  subject?: string | null;
  grade?: string | null;
  board?: string | null;
  duration_minutes: number;
  objectives: string[];
  materials: string[];
  timeline: LessonSegment[];
  assessment_ideas: string[];
  homework: string[];
  differentiation: string[];
  citations: Citation[];
  grounding: Grounding;
  disclaimer?: string | null;
}
export interface LessonPlanRequest {
  topic: string;
  subject?: string | null;
  grade?: string | null;
  board?: string | null;
  duration_minutes: number;
  notes?: string | null;
}

// --- wellbeing ------------------------------------------------------------------
export type ToneFlag = "routine" | "elevated_workload" | "distress_handoff";
export interface WellbeingResource {
  name: string;
  contact: string;
  description: string;
  region: string;
}
export interface WellbeingReflection {
  observations: string[];
  patterns: string[];
  supportive_message: string;
  practical_suggestions: string[];
  resources: WellbeingResource[];
  disclaimer: string;
  tone_flag: ToneFlag;
}

// --- career ---------------------------------------------------------------------
export type CareerGrounding = "grounded" | "general";
export interface MatchedPath {
  title: string;
  why_it_fits: string;
  skills_to_build: string[];
  first_steps: string[];
  source?: string | null;
}
export interface CareerGuidance {
  matched_paths: MatchedPath[];
  honest_caveats: string[];
  grounding: CareerGrounding;
  disclaimer?: string | null;
}

// --- profile --------------------------------------------------------------------
export interface WorkloadEntry {
  entry_date: string; // ISO date
  papers_graded: number;
  classes_taken: number;
  self_reported_energy: number; // 1..5
}
export interface TeacherProfile {
  teacher_id: string;
  name: string;
  subjects: string[];
  grades_taught: string[];
  board: Board;
  years_experience: number;
  workload_log: WorkloadEntry[];
}
export interface ProfileUpsert {
  name: string;
  subjects: string[];
  grades_taught: string[];
  board: Board;
  years_experience: number;
  workload_log: WorkloadEntry[];
}

// --- api request/response -------------------------------------------------------
export interface ChatRequest {
  teacher_id: string;
  message: string;
  session_id?: string | null;
}
export interface ChatResponse {
  session_id: string;
  intent: Intent;
  active_agent?: string | null;
  message: string;
  agent_output?: AgentOutput | null;
}
export interface GradeRequest {
  question: string;
  answer_text: string;
  rubric?: Rubric | null;
  student_identifier?: string | null;
  teacher_id?: string | null;
}
export interface BatchGradeRequest {
  items: GradeRequest[];
  teacher_id?: string | null;
  max_concurrency: number;
}
export interface BatchGradeResponse {
  results: (GradedResult | GradingError)[];
}
export interface CareerRequest {
  interest: string;
  teacher_id?: string | null;
}

// --- structured agent_output (discriminated by `type`) --------------------------
export type AgentOutput =
  | ({ type: "grading" } & GradedResult)
  | ({ type: "lesson_plan" } & LessonPlan)
  | ({ type: "wellbeing" } & WellbeingReflection)
  | ({ type: "career" } & CareerGuidance)
  | { type: "general"; text: string; provider?: string }
  | { type: "error"; text: string }
  | { type: "not_implemented"; agent: string; phase: number; message: string }
  | { type: "needs_input"; status: string; message: string }
  | ({ type: string } & Record<string, unknown>);

// --- SSE event payloads ---------------------------------------------------------
export interface IntentEvent {
  intent: Intent;
}
export interface MessageEvent {
  text: string;
  active_agent: string | null;
}
export interface DoneEvent {
  session_id: string;
}
export interface ErrorEvent {
  message: string;
}

export interface ApiErrorBody {
  error: { type: string; message: string };
}
