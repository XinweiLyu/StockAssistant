# Hotspot News Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add the approved news navigation and three-view browser using existing intelligence sources.

**Architecture:** Extend existing read filters and source enable APIs. A per-application refresh coordinator reuses existing fetch_source in a background task with shared status/cooldown. React consumes the existing authenticated client and market watchlists.

**Tech Stack:** FastAPI, SQLAlchemy, Python, React/TypeScript, existing CSS/components and Vitest.

**Spec:** `docs/superpowers/specs/2026-11-24-news-center-design.md` (approved concrete design in this conversation).

## Global Constraints

- No new credentials, model calls, dependencies or database migration.
- Keep existing reports, assistant, strategies and routes intact.
- Refresh interval300seconds; pause frontend polling when hidden/unmounted.
- Unknown published time stays unknown; fetched time is separate.
- Only explicit symbol association may enter the watchlist view or stock links.
- No commit/push unless separately requested; user already selected direct implementation in this conversation.

## Review Focus

- Source failure must not discard cached news or stop other enabled sources.
- Multiple page refreshes must coalesce; cooldown is enforced server-side.
- Old filter responses must not replace the current market/view.
- Empty watchlists must not accidentally query all stocks.
- Raw URLs and source errors must remain sanitized and authenticated.

### Task 1: News querying and background refresh

**Files:** `src/repositories/intelligence_repo.py`, `api/v1/endpoints/intelligence.py`, `api/v1/schemas/intelligence.py`; new `src/services/news_refresh_service.py`; `tests/test_intelligence_api.py`; new `tests/test_news_refresh_service.py`.

**Interfaces:** Existing items accepts optional `source_type`, `source_id`, `symbols` CSV; symbols filtering is symbol-scope only. Add `PATCH /sources/{id}` `{enabled:bool}`, `GET /refresh`, `POST /refresh`; coordinator exposes `start(background_tasks)` and `status()` with running/processed/total/results/error/cooldown timestamps.

- [x] Add filtering/empty-symbol/source-toggle tests and run to see failures.
- [x] Add coordinator merge/cooldown/failure tests and run to see failures.
- [x] Implement additive repository/API filters, source enable and coordinator using original fetch_source.
- [x] Run focused API/service tests and existing intelligence suites.

### Task 2: Browser, navigation and stock handoff

**Files:** New `apps/dsa-web/src/api/intelligence.ts`, `pages/NewsPage.tsx`, `components/news/useNewsFeed.ts`, `components/news/newsUtils.ts`; modify App, SidebarNav, ShellHeader, i18n, ASharePage; corresponding Vitest tests.

**Interfaces:** `/news` uses existing API client and `workspaceWatchlist.get(market)`. Handoff `/assistant?market=cn|hk|us&stock=<canonical>` validated by a shared helper; no analysis submission. UI reads snake_case intelligence payloads directly.

- [x] Add failing tests for navigation, three views, unknown time, safe links, empty watchlists, races and visibility pause.
- [x] Implement typed client and nonoverlapping visibility-aware hook.
- [x] Implement page using existing controls/styles, source management and pagination.
- [x] Add validated stock deep-link consumption preserving existing selections.
- [x] Run focused tests, full frontend suite, lint and production build.

### Task 3: Delivery

**Files:** `docs/news-center.md`, `docs/CHANGELOG.md`, English boundary note; no README preview.

- [x] Document real coverage, optional sources, timings, errors and rollback.
- [x] Run complete backend gate with final code; keep online-source failures separately reported.
- [x] Read-only final review, fix material issues, then deploy only tested files/build with backup and original startup script.
- [x] Verify real health, navigation and read-only news page; do not trigger model calls or expose credentials.

Real UI acceptance passed. Live acquisition passed after restoring public DNS resolution: all eight built-in sources succeeded and saved 178 items in the first run. See docs/news-center.md for the tested network conditions.
