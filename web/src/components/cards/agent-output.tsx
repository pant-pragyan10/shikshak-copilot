"use client";

import { CareerCard } from "@/components/cards/career-card";
import { GradedResultCard } from "@/components/cards/graded-result-card";
import { LessonPlanCard } from "@/components/cards/lesson-plan-card";
import { WellbeingCard } from "@/components/cards/wellbeing-card";
import type {
  AgentOutput,
  CareerGuidance,
  GradedResult,
  LessonPlan,
  WellbeingReflection,
} from "@/lib/types";

/**
 * Render a structured agent_output payload as the matching rich card. Text-only
 * outputs (general / error / not_implemented / needs_input) render nothing here —
 * their text is already shown in the chat message bubble.
 */
export function AgentOutputCard({ output }: { output: AgentOutput }) {
  switch (output.type) {
    case "grading":
      return <GradedResultCard result={output as unknown as GradedResult} />;
    case "lesson_plan":
      return <LessonPlanCard plan={output as unknown as LessonPlan} />;
    case "wellbeing":
      return <WellbeingCard reflection={output as unknown as WellbeingReflection} />;
    case "career":
      return <CareerCard guidance={output as unknown as CareerGuidance} />;
    default:
      return null;
  }
}
