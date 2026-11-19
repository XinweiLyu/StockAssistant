# Sector Flow Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, one fresh read-only final reviewer. No implementation agents. Steps use checkbox syntax.

**Goal:** Correct the existing feature to compare multiple sectors' today-observed cumulative flow in one chart.
**Architecture:** Read existing per-board observation buckets through a bounded cached comparison endpoint, reuse shared rank queue, add a full-width comparison panel before existing sector grid. No new provider, paid source or model calls.
**Tech Stack:** Existing Python/FastAPI/SQLite and React/TypeScript/SVG.
**Spec:** docs/superpowers/specs/2026-11-17-sector-flow-comparison-design.md

## Global Constraints
- Preserve prior dirty code and old single-board features; no commit/push/merge or reset.
- CN Eastmoney exact identities, max8 matching-kind IDs; unknown source trade date explicit. Today observations only, no backfill/summing/forward-fill, missing data stays null.
- Read endpoint queues only shared free rank. Same5min bucket dedupe; profiles unchanged. No per-sector history fanout or LLM.
- Today source limitations/failures explicit, no fabricated real-source acceptance. Hidden tabs cancel polling.

## Review Focus
- Invalid/mixed-kind/duplicate IDs and oversized lists rejected before any fetch.
- Cross-day observations must never appear today; clock or no-quote values not fabricated.
- Shared hover table may not carry another timestamp's last-known value.
- Abort/races/kind changes cannot overwrite selected board identities.
- Disabled/hidden offshore views cannot issue CN requests.

## Task 1: Cached comparison API
Files: src/services/a_share_sector_flow_service.py, api/v1/endpoints/a_share_market.py, tests/test_a_share_sector_flow_comparison.py.
- [x] RED: max8/type/duplicates/missing board, source failure + cached points, today/profile isolation, shared rank dedupe, no history/AI queues.
- [x] Implement comparison(kind,ids,refresh=False), per-series actual observations and health/timing, static route before sector paths.
- [x] GREEN: new comparison and all flow tests + original market API/service suites.

## Task 2: Full-width comparison UI
Files: types/aShareSectorFlow.ts, api/aShareMarket.ts, new sectorFlowComparisonData.ts, SectorFlowComparisonChart.tsx, SectorFlowComparisonPanel.tsx; modify InvestmentWorkspace.tsx and ASharePage.css; component tests.
- [x] RED: point/line/missing/gap/time-grid semantics, toggles/search/selectmax8, category/metric, linked hover matrix, aborted responses/hidden/offshore states.
- [x] Implement full-width chart/selection/linked table, visible5min shared source polling, source/calendar/coverage limitations. Preserve old grid and navigation.
- [x] GREEN: related + full frontend tests/scopedlint/build.

## Task 3: Review and runtime delivery
- [x] Update feature guide/changelog; final independent review with task-only baseline and one regression fix pass.
- [x] Fresh related/full checks appropriate to isolated cached endpoint; back up runtime files/build/protected config hashes, deploy code and static, use original run-a-share.sh, real browser acceptance with actual missing source state (no fake points).
- [x] Retain working tree/ledger, no Git publish; explain current source limitation accurately. Prior completion automation remainspaused unless unfinished at quota boundary.
