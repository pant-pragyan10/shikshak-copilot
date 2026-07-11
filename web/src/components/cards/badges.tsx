import { BookCheck, CircleHelp, Sparkles, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { INTENT_LABELS } from "@/lib/constants";
import type { CareerGrounding, Grounding, Intent } from "@/lib/types";

export function IntentBadge({ intent }: { intent: Intent }) {
  return (
    <Badge variant="primary">
      <Sparkles className="size-3" />
      {INTENT_LABELS[intent]}
    </Badge>
  );
}

export function GroundingBadge({ grounding }: { grounding: Grounding }) {
  if (grounding === "curriculum_grounded") {
    return (
      <Badge variant="success">
        <BookCheck className="size-3" />
        Curriculum-grounded
      </Badge>
    );
  }
  if (grounding === "partial") {
    return (
      <Badge variant="warning">
        <BookCheck className="size-3" />
        Partially grounded
      </Badge>
    );
  }
  return (
    <Badge variant="warning">
      <TriangleAlert className="size-3" />
      General knowledge — not syllabus-verified
    </Badge>
  );
}

export function CareerGroundingBadge({ grounding }: { grounding: CareerGrounding }) {
  return grounding === "grounded" ? (
    <Badge variant="success">
      <BookCheck className="size-3" />
      Grounded in curated paths
    </Badge>
  ) : (
    <Badge variant="warning">
      <CircleHelp className="size-3" />
      General guidance
    </Badge>
  );
}
