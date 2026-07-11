# Teacher Copilot — Web

The Next.js frontend for Teacher Copilot. It consumes the FastAPI backend (REST + SSE)
and renders the four agents' structured outputs as rich, interactive cards.

- **Next.js 16** (App Router) · **React 19** · **TypeScript** · **Tailwind v4**
- **TanStack Query** for data, a fetch-based **SSE reader** for streaming chat
- **framer-motion** for tasteful motion · **lucide-react** icons · **sonner** toasts
- Owned, shadcn-style UI kit (`src/components/ui`) · light/dark themes

Screens: **Chat** (orchestrator, streams + routes live), **Grade** (typed or scanned
answer + rubric builder), **Lesson Plan** (grounded + cited), **Wellbeing** (workload
chart + respectful check-in), **Career** (grounded guidance), **Profile**.

## Run locally

The backend must be running first (see the repo root README). Then:

```bash
cd web
npm install
cp .env.example .env.local        # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev                       # http://localhost:3000
```

Everything is keyed to a `teacher_id` (no auth) — the default is `demo-teacher`, which
matches the seeded demo profile. Switch it on the Profile page.

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the FastAPI backend | `http://localhost:8000` |

It's a `NEXT_PUBLIC_` var so it's inlined at build time — set it in Vercel before
deploying so the production build points at your hosted backend.

## Deploy to Vercel

1. Push this repo to GitHub.
2. On Vercel: **New Project** → import the repo → set the **Root Directory** to `web`
   (the frontend lives in a monorepo subfolder).
3. Framework preset **Next.js** is auto-detected. Add the environment variable
   `NEXT_PUBLIC_API_BASE_URL` = your deployed backend URL (e.g.
   `https://teacher-copilot-api.onrender.com`).
4. Deploy. Then add the resulting Vercel URL to the backend's `CORS_ORIGINS` env var
   and redeploy the backend, so the browser is allowed to call it.

## Contract

All API calls go through `src/lib/api.ts`; the TypeScript types in `src/lib/types.ts`
mirror the backend's `api/schemas.py` and agent domain models. If the backend contract
changes, update `types.ts` to match — it's the single source of truth on the client.
