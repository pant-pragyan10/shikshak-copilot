"use client";

import * as React from "react";

/**
 * The "current teacher" identity. There's no auth (out of scope) — we persist a
 * teacher_id in localStorage so every tool (grade, wellbeing, profile) acts on the
 * same teacher across the app. Defaults to the demo teacher so the app works OOTB.
 */
const DEFAULT_TEACHER_ID = "demo-teacher";
const STORAGE_KEY = "tc.teacher_id";

interface TeacherContextValue {
  teacherId: string;
  setTeacherId: (id: string) => void;
}

const TeacherContext = React.createContext<TeacherContextValue | null>(null);

export function TeacherProvider({ children }: { children: React.ReactNode }) {
  const [teacherId, setTeacherIdState] = React.useState(DEFAULT_TEACHER_ID);

  React.useEffect(() => {
    // Sync from an external store (localStorage) on mount — this is exactly the kind
    // of external-system sync effects are for, so the set-state rule is safe here.
    const stored = window.localStorage.getItem(STORAGE_KEY);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored) setTeacherIdState(stored);
  }, []);

  const setTeacherId = React.useCallback((id: string) => {
    const clean = id.trim() || DEFAULT_TEACHER_ID;
    setTeacherIdState(clean);
    window.localStorage.setItem(STORAGE_KEY, clean);
  }, []);

  return (
    <TeacherContext.Provider value={{ teacherId, setTeacherId }}>
      {children}
    </TeacherContext.Provider>
  );
}

export function useTeacher(): TeacherContextValue {
  const ctx = React.useContext(TeacherContext);
  if (!ctx) throw new Error("useTeacher must be used within TeacherProvider");
  return ctx;
}
