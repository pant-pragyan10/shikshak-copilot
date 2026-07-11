import {
  BookOpen,
  Compass,
  HeartPulse,
  MessagesSquare,
  PenLine,
  User,
  type LucideIcon,
} from "lucide-react";
import type { Board, Intent } from "./types";

export interface Mode {
  href: string;
  label: string;
  icon: LucideIcon;
  blurb: string;
}

/** Primary navigation — one entry per product capability. */
export const MODES: Mode[] = [
  { href: "/chat", label: "Chat", icon: MessagesSquare, blurb: "Ask anything — it routes automatically" },
  { href: "/grade", label: "Grade", icon: PenLine, blurb: "Grade typed or scanned answers" },
  { href: "/lesson-plan", label: "Lesson Plan", icon: BookOpen, blurb: "Curriculum-grounded plans" },
  { href: "/wellbeing", label: "Wellbeing", icon: HeartPulse, blurb: "Workload-aware check-ins" },
  { href: "/career", label: "Career", icon: Compass, blurb: "Grounded growth guidance" },
  { href: "/profile", label: "Profile", icon: User, blurb: "Your subjects & workload" },
];

export const BOARDS: Board[] = ["CBSE", "ICSE", "STATE"];

export const SUBJECTS = [
  "Science",
  "Mathematics",
  "English",
  "Hindi",
  "Social Studies",
  "Physics",
  "Chemistry",
  "Biology",
  "Computer Science",
];

export const INTENT_LABELS: Record<Intent, string> = {
  grading: "Grading",
  lesson_plan: "Lesson Plan",
  wellbeing: "Wellbeing",
  career: "Career",
  general: "General",
};
