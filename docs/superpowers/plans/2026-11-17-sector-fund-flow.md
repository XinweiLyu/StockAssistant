# Sector Fund Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement inline, with a single fresh final review. No implementation subagents. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add auditable A-share sector flow charts and dynamic trends to the existing workspace without losing prior functionality.
**Architecture:** Typed flow contracts and strict normalization; additive SQLite repository; service reusing the existing market task worker and bounded provider; shared UI panel/hooks; closed-day cached evidence injected into existing expert research.
**Tech Stack:** Existing FastAPI/Pydantic/SQLAlchemy/SQLite, React/TypeScript/Recharts, requests/CapabilityProvider. No new package or paid subscription.
**Spec:** docs/superpowers/specs/2026-11-17-sector-fund-flow-design.md
**Approval:** User explicitly requested implementation of the preceding proposal on 2026-11-17. Preserve current worktree and no Git commits/pushes.

## Global Constraints

- CN Eastmoney industry/concept by canonical BK code only; HK/US unsupported explicitly.
- Currency CNY; raw amounts yuan, UI hundred-million yuan; missing null, no synthetic flows.
- Daily net vs intraday cumulative are distinct. Five-minute samples are not additive; source time may be unknown.
- Profile/source/task publication guards; no paid model/source calls on reads or refresh.
- Preserve original stock chart placement, filters, watchlists, members and all multi-market code.
- Freeze only observed-before-cutoff closed-day flow evidence; no look-ahead from later revisions.

## Review Focus

1. Duplicate timestamps, later source revisions, missing sessions and day resets must not create inflated cumulative flow (Tasks1/2).
2. Mode/config switches or source failures during fetch must not replace another profile's cache or erase prior good data (Task2).
3. Same named boards, concept overlaps and member changes must not conflate identities or imply sums are market totals (Tasks1/2/3).
4. Rapid sector/market switches, hidden tabs and repeat manual clicks must not display old results or multiply fetches (Task3).
5. Cached source observations obtained after a research cutoff must never become earlier known funds evidence; refresh must not invoke models (Task4).

## Task 1: Contracts, normalization and persistence

Files: create src/schemas/a_share_sector_flow.py, data_provider/a_share_sector_flow.py, src/repositories/a_share_sector_flow_repository.py; tests/test_a_share_sector_flow_data.py, tests/test_a_share_sector_flow_repository.py.
Interfaces: normalize_rank(rows,kind,observed_at), normalize_history(rows,sector,observed_at), normalize_members(rows,sector,observed_at); SectorFlowRepository.save_daily/profile+sector+date, save_observations/profile+sector+session+bucket, read_daily/read_observations.
- [x] RED: zero vs missing, yuan/percent mapping, invalid/future dates, code/type mismatch; repeated snapshot bucket, raw dates independent of source time, retained history revisions/as-of reads.
- [x] Implement typed observations and bounded direct adapters matching installed AKShare field semantics; preserve classification and provenance.
- [x] GREEN: python -m pytest -q tests/test_a_share_sector_flow_data.py tests/test_a_share_sector_flow_repository.py (all pass).

## Task 2: Queue, service and API

Files: create src/services/a_share_sector_flow_service.py; modify data_provider/a_share.py allowlist/worker dispatch, src/services/a_share_market_service.py service init/task dispatch, api/v1/endpoints/a_share_market.py routes; tests/test_a_share_sector_flow_service.py, tests/test_a_share_sector_flow_api.py.
Interfaces: SectorFlowService.get(sector_id,period=0,refresh=False), rankings(kind,refresh=False), members flow map; fetches are existing durable tasks sector_flow_rank/sector_flow_history/sector_flow_members; API GET sectors/fund-flow-rankings and GET/POST sectors/{id}/fund-flow; stock industry summary uses same endpoint.
- [x] RED: shared5min rank task; exact sector history; complete trading-day windows vs null gaps; zero values; no repeated-sum snapshots; lunch/holiday schedules; cached error and actual fetched time; immutable task profile/source publication; invalid periods; unsupported board types.
- [x] Implement queueing and snapshot persistence. Auto-refresh only from visible clients; provider fetch bounded. No clearing successful cache on failure; failed tasks retry only through existing bounded policy/manual action.
- [x] GREEN: run new service/API and existing market jobs/service/API suites.

## Task 3: Same-page visualization and member linkage

Files: create apps/dsa-web/src/types/aShareSectorFlow.ts, components/a-share/useSectorFundFlow.ts, SectorFundFlowPanel.tsx, SectorFundFlowChart.tsx; modify api/aShareMarket.ts, SectorDetail.tsx, SectorBrowser.tsx, SectorHeatmap.tsx, StockDetail.tsx, pages/ASharePage.css. Tests beside components.
Interfaces: typed get/refresh/rank methods; hook keyed by qualified sector+period,5min visible polling/cancel; panel periods0/5/20/60 and category toggles, price right axis, nonstacked flows, source state; optional compact panel for stock industry.
- [x] RED: view selector, toggles/null gaps, cumulative vs daily copy, stale responses ignored, polling stops hidden/unmount, manual refresh never generates AI, rankings/member navigation preserved, HK/US unsupported.
- [x] Implement panel above sector member table, flow columns, ranking metrics and collapsed stock-industry summary without moving stock K-line.
- [x] GREEN: impacted tests and original sector/workspace tests; scoped ESLint, full frontend tests/build.

## Task 4: Evidence, real-source/runtime acceptance and delivery

Files: modify src/services/a_share_integrated_service.py and integrated prompts only to deliver cached market evidence, docs/CHANGELOG.md; create docs/sector-fund-flow.md, tests/test_a_share_sector_flow_research.py and opt-in source smoke coverage.
Interfaces: SectorFlowService.research_fact(stock_code,industry,cutoff,anchor_date) returns one bounded sourced market fact or None, read-only; flow fact IDs include board/type/content/version.
- [x] RED: observed-after-cutoff exclusion, unverified intraday excluded, only same-industry cached evidence, source reuse/citation and zero generation from reads.
- [x] Implement cached evidence injection, no model call or stochastic forecast modifications. Update usage/data semantics and source limitations docs.
- [x] Run complete affected backend and full offline gate; record actual source probe availability without credentials, take final independent read-only review, fix Important findings with RED→GREEN once.
- [x] Back up runtime/code/build; deploy only verified files, preserve config/databases; verify original and new routes/browser charts, keep screenshots outside Git. Record rollback and any source failure honestly.
- [x] Pause automatic continuation after actual completion; leave code uncommitted/unpushed.
