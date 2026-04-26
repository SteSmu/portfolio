# Handoff: Phase-A UX-Redesign abschließen

**Plan**: `/Users/stefan/.claude/plans/lass-uns-in-dieser-crispy-marshmallow.md`
(cortex plan #2, status `approved`).

**Repo**: `/Users/stefan/projects/private/prod/portfolio` — commit-Range
der bisherigen Phase A: `5d5d76e..ac4de00`. 227 Tests grün, prod-Stack
auf `:5174` läuft 4-Container, dev-Stack via `.claude/launch.json` →
preview_start "frontend-dev" auf `:5175`.

---

## Vor Implementation lesen (Pflicht)

```bash
ls .claude/skills/project-architecture/references/
# frontend.md, charts.md, api.md sind die wichtigsten — alle aktuell
# (diese Session hat sie zuletzt am 2026-04-26 gepflegt).
cortex search "phase a" --limit 5         # Vorwissen aus Session #3 + #4
```

Project-CLAUDE.md hat zwei neue Regeln seit der letzten Session:
- Subagent-Priming mit konkreten Signaturen
- Prod-Docker-Rebuild nach FE/Schema-Changes

Beides relevant für diese Session — wenn du parallel arbeitest oder am
Ende verifizieren willst.

---

## Was zum Abschluss noch offen ist

Phase-A-Plan-Sektion → konkrete TODO. Reihenfolge ist eine sinnvolle
Default-Order; jeder Punkt ist independent committable.

### 1. AssetDetail · News-Marker auf der Preis-Chart

Plan-Sektion "AssetDetail" listet das als optional. Jetzt umsetzen:

- `frontend/src/components/charts/AssetPriceChart.tsx` lädt die News-
  Items via `api.listNews(symbol, assetType, 50)` direkt im Wrapper
  (oder als optionaler `news` prop von der Page).
- Pro News-Item ein kleiner Marker via `createSeriesMarkers(...)` —
  shape: `circle`, position: `inBar`, size klein, color `var(--cat-3)`.
- Hover-Tooltip = News-`title`; Click öffnet die news-URL im neuen Tab.
- Sentiment >0 grün, <0 rot, neutral grau.
- Toggle "Show news" in der Period-Selector-Zeile (default off, weil
  bei vielen News-Items das Chart sonst zugepflastert wird).

Verweis: `references/charts.md` — lightweight-charts v5 Marker-Pattern
ist dort dokumentiert. **Nicht** auf v4-Docs zurückfallen.

### 2. Allocation-over-time (Stacked-Area)

Plan erwähnt es als zukünftige Allocation-Variante. Daten existieren
bereits: jeder `Snapshot.metadata.by_asset_type` hat den Breakdown.

- Neuer Tab in `Allocation.tsx` neben Sunburst/Donut: `'over-time'`.
- `AllocationOverTime.tsx` (neu in `components/charts/`): ECharts-
  `stacked-area`, x = snapshot.date, y = value pro asset_type.
  Eine Series pro asset_type, gestapelt, Farbpalette `--cat-1..8`.
- Pulle Snapshots via `api.listSnapshots(activeId, {from})` — gleicher
  Hook wie auf der Performance-Page.

### 3. Mobile-Pass (375px DevTools)

Risiko-Kandidaten:
- Holdings-Table → Heatmap-Toggle: Treemap rendert auf 375px klein,
  Tile-Labels werden truncated. Prüfen ob Click-to-Drill-In noch funktioniert.
- Performance-Equity-+-Drawdown-Stack: legend-Position auf mobil.
- AssetDetail: lightweight-charts wird sehr eng — `overflow-x-auto`
  am Card-Container hilft nicht (Chart füllt 100% Width). Prüfen ob
  der Period-Selector unter dem Title bricht.
- Header-Nav bricht bei 375px aktuell auf 2 Reihen — checken ob das
  hübsch genug ist oder ob ein Burger-Menu nötig wäre.

Tooling: `preview_resize` mit `preset: 'mobile'`, dann jede Page
durchklicken. Screenshot pro Page als Beweis.

### 4. Skeleton-Loaders überall einheitlich

Heute heterogen — manche Pages haben nur "loading…", manche einen
`.skeleton`-div. Pattern festziehen:
- Hero-KPI: `<div className="skeleton h-7 w-32 mt-2" />`
- Card-Body: `<div className="skeleton h-32" />`
- Chart-Frame: `<div className="skeleton h-72" />` (oder die Chart-
  Wrapper-Höhe matchen — z.B. h-96 für AssetDetail).
- Table: `<div className="skeleton h-40" />` als Single-Block reicht.

`Holdings.tsx` und `Transactions.tsx` haben das schon. AssetDetail,
Performance, Allocation prüfen.

### 5. BenchmarkPicker UX-Polish

Aktuell zeigt der Chart einfach nur die Hauptlinien wenn das Benchmark
keine Candles hat. Besser:

- Wenn `useBenchmarkOverlay` `series.length === 0` zurückgibt, render
  einen Toast/Banner über dem Chart: "No candles synced for SPY yet —
  click 'Sync benchmark' to backfill." mit Button → `api.syncBenchmark(symbol, 365)`.
- "Sync" als kleiner Button im BenchmarkPicker selbst (Icon-only OK).
- Auf Erfolg: TanStack-Query invalidate auf `['candles', symbol, ...]`
  damit der `useBenchmarkOverlay` neu fetched.

### 6. (Optional, falls Zeit) Year-in-Review

Parqet-Wrapped-Style Storyboard-Page `/year/2026`:
- max return month, max DD week, best mover, realized total,
  dividends paid (wenn welche da sind).
- Alles aus Snapshots + Tx-Log computebar — keine neuen API-Routen
  nötig wenn `listSnapshots` + `realized` + `listTransactions` reichen.
- Eine einzige scrollbare Page, große Zahlen pro Sektion, sparkline-
  background.
- Plan-Sektion erwähnt das als Differenzator-Bonus.

---

## Akzeptanz

- [ ] Cortex Plan #2 als `done` markieren (`cortex plan done 2`).
- [ ] 230+ Tests grün (jeder Item committet bringt 1-3 Tests dazu).
- [ ] Prod (`docker compose -f docker-compose.prod.yml up -d --build`)
      zeigt alle 6 Items live auf `:5174`.
- [ ] Mobile-Pass dokumentiert in der Session-Log mit Screenshots.
- [ ] Architecture-Refs (`frontend.md`, `charts.md`) updates für News-
      Marker + Allocation-Over-Time + Skeleton-Konvention.
- [ ] `gw acp` pro Item, Commit-Subjects beginnen mit
      `Phase A finish: <topic>` damit der commit-log lesbar bleibt.
- [ ] Auto-learning am Ende auf user-Anweisung — **nicht** selbst starten.

---

## Tooling Cheatsheet

```bash
# Dev-Stack laufen lassen (oder per preview_start im harness)
cd frontend && npx vite --host 127.0.0.1 --port 5175    # Dev-FE
PT_DB_PORT=5434 .venv/bin/uvicorn pt.api.app:app --port 8430 --reload  # Dev-API

# Tests
PT_DB_PORT=5434 .venv/bin/python -m pytest tests/ -q
cd frontend && npx tsc --noEmit

# Prod re-build
docker compose -f docker-compose.prod.yml up -d --build
docker exec pt-cron pt sync daily             # manuell tagessync feuern
docker logs pt-cron --since 1m                # cron-output

# Architecture
cortex search "<query>"
ci skill project-architecture --ref frontend  # liest ref direkt
```

## Prompt für die nächste Session (copy-paste)

> Wir schließen das Phase-A-UX-Redesign ab. Plan-Datei:
> `/Users/stefan/.claude/plans/lass-uns-in-dieser-crispy-marshmallow.md`
> (cortex plan #2). Handoff:
> `.claude/sessions/handoffs/2026-04-27-finish-phase-a-ux.md` — sechs
> Items, je independent committable. Bitte bestehenden Plan-Stand lesen
> (`cortex plan show 2`), Architecture-Refs konsultieren bevor du
> implementierst, und in dieser Reihenfolge arbeiten: News-Marker auf
> AssetDetail-Chart → Allocation-Over-Time → Mobile-Pass → Skeleton-
> Konsistenz → BenchmarkPicker-UX → (optional) Year-in-Review. Akzeptanz
> in der Handoff-Datei. Subagents nur für genuinely-independent Items
> nutzen, dann mit konkreten Signaturen primen.
