"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { User } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ToolShell } from "@/components/layout/tool-shell";
import { ProfileEditor } from "@/components/profile/profile-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { useTeacher } from "@/lib/teacher";

export default function ProfilePage() {
  const { teacherId, setTeacherId } = useTeacher();
  const [idInput, setIdInput] = React.useState(teacherId);

  const query = useQuery({
    queryKey: ["profile", teacherId],
    queryFn: () => api.getProfile(teacherId),
    retry: false,
  });

  const aside = (
    <div className="space-y-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Teacher identity
      </p>
      <p className="text-sm text-muted-foreground">
        No login here — everything is keyed to this id. Switch it to act as another teacher.
      </p>
      <div className="flex gap-2">
        <Input value={idInput} onChange={(e) => setIdInput(e.target.value)} />
        <Button variant="outline" onClick={() => setTeacherId(idInput)}>
          Switch
        </Button>
      </div>
    </div>
  );

  return (
    <ToolShell aside={aside} asideTitle="Account">
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8">
        <PageHeader
          icon={User}
          title="Profile"
          description="Your teaching context powers the other tools — subjects feed grading and career, workload feeds wellbeing."
        />
        {query.isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Loading profile…
          </div>
        ) : (
          // Remount (fresh form state) whenever the teacher id changes.
          <ProfileEditor key={teacherId} teacherId={teacherId} initial={query.data ?? null} />
        )}
      </div>
    </ToolShell>
  );
}
