"use client";

import * as React from "react";
import { ImageUp, X } from "lucide-react";
import { cn } from "@/lib/utils";

const MAX_BYTES = 10 * 1024 * 1024;

export function ImageDrop({
  file,
  onFile,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
}) {
  const [dragging, setDragging] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const previewUrl = React.useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  React.useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const accept = (f: File | undefined) => {
    setError(null);
    if (!f) return;
    if (!f.type.startsWith("image/")) return setError("That's not an image file.");
    if (f.size > MAX_BYTES) return setError("Image is larger than 10 MB.");
    onFile(f);
  };

  if (file && previewUrl) {
    return (
      <div className="relative overflow-hidden rounded-[--radius-md] border border-border">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={previewUrl} alt="Answer preview" className="max-h-72 w-full object-contain bg-muted" />
        <button
          onClick={() => onFile(null)}
          className="absolute right-2 top-2 flex size-8 items-center justify-center rounded-full bg-background/90 text-foreground shadow hover:bg-background"
          aria-label="Remove image"
        >
          <X className="size-4" />
        </button>
        <p className="truncate border-t border-border bg-card px-3 py-2 text-xs text-muted-foreground">
          {file.name} · {(file.size / 1024).toFixed(0)} KB
        </p>
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          accept(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-2 rounded-[--radius-md] border border-dashed px-6 py-10 text-center transition-colors",
          dragging ? "border-primary bg-accent" : "border-border hover:border-primary/40 hover:bg-muted/50",
        )}
      >
        <ImageUp className="size-7 text-muted-foreground" />
        <span className="text-sm font-medium">Drop an answer sheet, or click to upload</span>
        <span className="text-xs text-muted-foreground">PNG / JPG, up to 10 MB · scanned or photographed</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => accept(e.target.files?.[0])}
      />
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
    </div>
  );
}
