# 2026-04-26 — Phase A wrap-up: FX + Benchmark + Daily-Cron + Auto-Learning

Continuation of `2026-04-26-ux-redesign-phase-a.md`. After the initial five
Phase-A commits landed, the user asked for the deferred Phase-A items
(FX-aware totals, benchmark overlay) and a daily auto-fetch sidecar. Then
auto-learning + session wrap-up.

## What shipped today (post-original-Phase-A)

| Topic | Commits | Verified |
|--|--|--|
| Subagent FX-aware totals | `b9bdf39` | tests + dev DB run + integrated into Dashboard hero (`354f97b`) |
| Subagent benchmark overlay | `99b7898` (merged via `phase-a-benchmark-overlay`) | tests + live `/api/benchmarks` on prod |
| Worktree gitignore | `401cccb` | — |
| Daily cron orchestrator + sidecar | `5643929` (+`ac4de00` healthcheck disable) | `docker exec pt-cron pt sync daily` returns ok=true on prod |

Plus today's auto-learning landed two patterns into project CLAUDE.md
(subagent-priming, prod-rebuild discipline).

## Auto-Learning Report (T4)

| Row | Outcome |
|--|--|
| Tier | T4 — multi-phase continuation, ≥5 subsystems edited (frontend pages + components + state, backend jobs + routes + schema, deployment compose, architecture refs, CLI). |
| Helper-skills loaded | `cli-engineering` (loaded), `project-architecture` (loaded both turns). Skipped: `skill-engineering` ref-loading (no skill body edited; only project-architecture refs were touched and those are owned by the project, not a meta-skill) — verified by `git log --since='2 hours ago' .claude/skills/`. |
| Actions Taken | Project CLAUDE.md gained two rules: (a) subagent-priming with concrete signatures + file:line refs (b) prod docker rebuild after FE/route/schema changes. Both extracted from real corrections this session. |
| CLI-Pattern-Extraction-Proof | `pt sync daily` is the new orchestrator subcommand. Reuses route-level `sync_portfolio_prices` instead of duplicating the loop — *project-internal* generalization. No tool-class generalization to `cli-engineering` skill needed (the orchestrator pattern is portfolio-specific). Help text follows existing `pt sync` convention (Examples block at top, `--json`, semantic exit codes 0/1). |
| Artifact-Updates | `references/deployment.md` (cron sidecar section + first-time-migrate caveat), CLAUDE.md (cron + subagent-priming + rebuild discipline), `references/api.md`/`frontend.md`/`charts.md`/`performance.md` updated mid-flight by both subagents. All committed before wrap-up. |
| Staleness-Audit-Proof | `git log --since='2 hours ago' --name-only -- .claude/skills/project-architecture/` shows every ref touched landed in a commit. `git status` clean before wrap-up. |
| Gap-Detection | New symbols introduced this session: `pt.jobs.benchmarks.BENCHMARKS`, `pt.jobs.daily.run`, `Snapshot.total_value_base`, `EquityCurve.benchmark` prop, `useBenchmarkOverlay`, `BenchmarkPicker`. Each documented in the matching ref before commit. No orphan symbols. |
| Test-Gate | 217 → 224 (+FX +benchmark) → 227 (+daily orchestrator). Final `pytest -q`: 227 passed, 1 skipped. Frontend `tsc --noEmit` exit 0 across all merges. |
| Parallel-Session-Gate | Two worktree subagents merged cleanly because file boundaries were spelled out in prompts (`pt/jobs/snapshots.py`, `pt/db/schema_portfolio.sql`, `pt/performance/money.py` reserved for FX-agent; `frontend/components/charts/EquityCurve.tsx`, `BenchmarkPicker.tsx`, `pt/api/routes/benchmarks.py`, `pt/jobs/benchmarks.py` reserved for benchmark-agent; `client.ts` shared with non-overlapping section assignment). Merge: 0 conflicts. |
| Handoff-Sim | Next-session prompt at `.claude/sessions/handoffs/2026-04-27-finish-phase-a-ux.md` — self-contained, includes plan ref, current commit range, what's left, acceptance criteria. |
| Memory-Migration | None needed — all learnings landed team-visible (CLAUDE.md, refs). No stale memory entries about Phase A. |
| Verification-Loop | After cron sidecar landed, `docker exec pt-cron pt sync daily` confirmed on prod. After healthcheck disable: `docker compose ps` shows `Up` (no longer `unhealthy`). |
| Pollution-Scan | New CLAUDE.md rules don't pin dates / commit hashes / agent IDs in the body — they describe the principle. ✓. |
| Session Quality | High signal-density. Two strong corrections: "achte darauf den subagents genug kontext zu geben" (drove subagent-priming rule) and "ich sehe die änderungen noch nicht" (drove prod-rebuild discipline). Both were absorbed before this report was written. |

## Next-up

Plan #2 (`Portfolio-Tracker — UX-Redesign zum Insight-Tool`, file
`/Users/stefan/.claude/plans/lass-uns-in-dieser-crispy-marshmallow.md`)
remains the source of truth for what's left. The remaining UX-finish
items are written as a self-contained handoff in
`.claude/sessions/handoffs/2026-04-27-finish-phase-a-ux.md`.

## Prod state at session end

- Containers (4): `pt-timescaledb` healthy, `pt-api` healthy, `pt-frontend`
  Up, `pt-cron` Up + sleeping until 06:00 UTC.
- Daily cron will fire at next `06:00 UTC` (≈7h from session end).
- Schema migrated (`total_value_base` column exists on prod DB).
- Last commit on `main`: `ac4de00`.
