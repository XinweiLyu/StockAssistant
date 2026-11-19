# Multi-market Trading Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing assistant to Hong Kong and US equities, including search, charts, event-aware research and auditable value investing.

**Architecture:** Add a market-qualified workspace facade, delegating CN to the current assistant and offshore fetching to existing providers. Generalize shared research/value contracts and inject market context rather than duplicating valuation or prediction algorithms. Keep all legacy CN endpoints and persisted records compatible.

**Tech Stack:** Existing Python/FastAPI/Pydantic/SQLite, React/TypeScript/Vitest, yfinance/AKShare, exchange-calendars and configured search/LLM services; SEC public JSON APIs.

**Spec:** `docs/superpowers/specs/2026-11-11-multi-market-assistant-design.md`

**Status:** Approved by the user on 2026-11-16; implementation and live data/browser checks completed in this chat. Real model acceptance failed and is explicitly recorded in docs/multi-market-acceptance-2026-11-16.md. No commit, push or new paid data subscription is implied.

## Global Constraints

- Markets: `cn/hk/us`; canonical IDs include market; old CN code and CNY defaults remain readable.
- Quote checks: 300 seconds on visible selected market; reads/refresh never call LLMs.
- Trading scenarios: 5/20/60 sessions; value scenarios: 6/12/24/36 months.
- Preserve source/observed/publication dates, native financial currency, adjustment semantics and missing values.
- Separate formal value, reference sensitivity, model proposal and user-confirmed assumptions.
- No new mandatory paid subscription; no hardcoded secrets/model/port/contact identity.
- No commit/tag/push without current explicit authorization. Do not edit `sources/` or runtime configuration.

## Review Focus

1. Same issuer or similar bare codes across markets must not collide in cache, evidence, task, watchlist or chart state (Tasks 1, 2, 7).
2. US DST, holidays, half-days and overnight quotes must not create false completed candles or future sessions (Tasks 2, 4, 7).
3. Native financial currency, share class/ADR ratio, diluted shares and corporate actions must not produce a silently wrong per-security value (Tasks 3, 6).
4. Missing directory members, references, original filings, historical vintages or provider failures must remain explicit rather than becoming fabricated complete research (Tasks 2–6).
5. Rapid market switches, stale research and simultaneous refresh/generation must not show another security's results or generate model fees from reads (Tasks 4, 5, 7, 8).

## Task 1: Market-qualified identity and compatible contracts

**Files:**
- Create `src/schemas/market_workspace.py`, `src/services/market_workspace_symbols.py`.
- Modify `src/schemas/a_share_value.py`, `src/schemas/a_share_integrated.py`, `src/schemas/a_share_market.py` only where shared contracts require compatible fields.
- Include monetary identity/currency treatment in MonitorRule, ForecastObservation, SupplementFact, ValueReport and holding/reference outputs; new offshore records require explicit market and currency while old CN records remain readable.
- Test `tests/test_market_workspace_symbols.py`, `tests/test_market_workspace_contracts.py`.

**Interfaces:** `resolve_instrument(market: str, symbol: str) -> InstrumentIdentity`; identity has `instrument_id`, `market`, `symbol`, `source_symbol`, timezone and explicit verification metadata. Resolution normalizes syntax; catalog/provider confirmation establishes verification.

- [ ] Write RED tests for `hk00700/00700/0700.HK -> hk:00700`, CN 000807, US AAPL, class-share aliases, market-conflicting input and invalid input.
- [ ] Write RED compatibility tests: old ValueFact/ValueSnapshot/ValueAssumptions records parse as CN/CNY; monetary unit/currency mismatch is rejected; new market IDs are distinct.
- [ ] Write RED tests that offshore facts/monitoring/supplement/report inputs without explicit market/currency are rejected; legacy A-share endpoints still reject offshore identifiers. Namespace journal/supplement revisions, evidence IDs and task lookup, not just cache keys.
- [ ] Run `python -m pytest -q tests/test_market_workspace_symbols.py tests/test_market_workspace_contracts.py`; confirm failures describe missing behavior.
- [ ] Implement identity and currency/price-basis metadata, preserving existing symbols at provider boundaries and never mapping unknown to CN.
- [ ] Run new tests plus `tests/test_a_share_market_contracts.py`, `tests/test_a_share_value_api.py`, `tests/test_a_share_integrated_api.py`; all pass.

## Task 2: Catalog, history, quote and calendar-aware source adapters

**Files:**
- Create `data_provider/market_workspace.py`, `src/services/market_workspace_service.py`.
- Modify `src/repositories/a_share_market_repository.py` only to add namespaced entries if existing persistence supports them without changing CN semantics.
- Reuse `src/data/stock_index_loader.py`, existing Yfinance/AkShare providers, `src/core/trading_calendar.py`.
- Test `tests/test_market_workspace_provider.py`, `tests/test_market_workspace_service.py`.

**Interfaces:** `MarketWorkspaceService.catalog(market, query)`, `.stock(market, symbol)`, `.history(market, symbol, start, end, basis)`, `.refresh(market, symbol)`, `.capabilities(market)` return qualified identities and per-block states. New code must not call StockService's zero-price placeholder path.

- [ ] Add failing tests for catalog coverage and stale fallback; partial industry membership; quote 0/null rejection; HK aliases; preserved US class-share mapping.
- [ ] Add failing tests for US DST/half-day, HK holiday and market-local completed session; raw/adjusted pairing; provider 429/timeout; Stooq marked daily fallback.
- [ ] Run new tests to RED, then implement bounded provider calls, qualified persistence, per-source request coalescing and cancellation-safe queries.
- [ ] Add explicit unadjusted Yahoo acquisition with `auto_adjust=False`, Adj Close/actions and common acquisition/version metadata; do not relabel the existing auto-adjusted history as raw. Calendar certification uses fail-closed session APIs. Identity/classification coverage remains explicit even if the old index marks all entries active.
- [ ] Run new tests plus existing provider/calendar/market-service regressions. Ensure failures preserve cached data with its actual age and explicit error.

## Task 3: Offshore financial facts, disclosures and auditable currency/capital binding

**Files:**
- Create `data_provider/sec_filings.py`, `data_provider/offshore_research.py`, `src/services/market_workspace_financials.py`.
- Extract an auditable FX adapter from `src/services/portfolio_service.py::_fetch_fx_rate_from_yfinance` without changing portfolio behavior; return actual quote date/source/pair/direction, not only a float.
- Reuse/extend `data_provider/yfinance_fundamental_adapter.py`, `src/services/a_share_value_financials.py` and `src/services/a_share_value_capital.py`.
- Modify `.env.example` and `src/config.py` only for the genuinely new SEC access identifier, using existing config registration paths.
- Test `tests/test_sec_filings.py`, `tests/test_offshore_research.py`, `tests/test_market_workspace_financials.py`.

**Interfaces:** `OffshoreResearchSources.fetch(identity, cutoff) -> dict` returns raw facts, source/available dates, source currency, documents and capabilities. `bind_listing_value(identity, financial_view, fx, capital) -> dict` returns conversion evidence or exact blocking reasons; never synthesizes ADR ratios or debt.

- [ ] RED tests: SEC CIK mapping; US-GAAP/IFRS facts; same-period amendments; availability dates; custom/unmapped tags; access identity missing; 429/timeout.
- [ ] Support only the spec's initial standard-tag metrics/units and filing families; preserve duplicate-context conflicts and amendment provenance. Unknown custom-tag semantics stay unmapped.
- [ ] RED tests: fiscal years and 52/53 weeks; YTD vs individual quarters; semiannual HK statements; currency conflicts; negative capex normalization; current vs weighted shares; treasury stock and ADR missing ratio.
- [ ] RED tests: FX actual date no later than valuation date, maximum 7 calendar days old, finite positive rate, inverse provenance and no implicit CNY/CNH equivalence; old portfolio callers keep their float/None contract.
- [ ] RED tests: HKEXnews title-only evidence cannot become full text; unknown publication remains unknown; user supplement retains original currency/source and audit metadata.
- [ ] Implement SEC adapter behind bounded access, vendor fact normalization and native-currency/FX/capital bindings. Reuse existing disclosed fact validation and supplement workflow.
- [ ] Replace Dec-31 assumptions inside `src/services/a_share_value_financials.py` with fiscal-period interval normalization and constituent provenance; exercise AAPL/MSFT noncalendar fiscal years, HK semiannual filings and period changes.
- [ ] ADR/share-class bindings consume sourced official filing/IR/depositary evidence or audited manual supplement, including entitlement direction, effective date and corporate-action coverage through anchor. Test that observation date never overwrites share effective date. No silent FX triangulation.
- [ ] Run tests plus current value-facts/financials/capital/research regressions. Missing official coverage yields partial, not ready.

## Task 4: Market-specific event context and comparable-history analysis

**Files:**
- Create `src/services/market_workspace_events.py`.
- Modify `src/services/a_share_event_cases.py`, `src/services/a_share_event_lifecycle.py`, `src/services/a_share_integrated_service.py` through optional explicit market context, leaving CN defaults intact.
- Test `tests/test_market_workspace_events.py` and existing event audit suites.

**Interfaces:** `event_market_context(identity, event, histories, cutoff) -> dict` supplies market session alignment and labeled benchmark/industry references to current case calculations. Case matching requires market-qualified samples unless explicitly marked external comparison.

- [ ] Write failing tests for release-after-close, US overnight timezone, no look-ahead from restatements, benchmark-only partial context and missing sector reference.
- [ ] Write failing tests showing cross-market samples do not silently join; same issuer's news is not counted repeatedly; prior rally and event age are calculated on local sessions.
- [ ] Implement provider-backed references and evidence lineage; pass context to existing lifecycle/case functions, keeping current eligibility and sample minimums.
- [ ] Bind explicit wide-market baselines `^GSPC` / `^HSI` through existing index fetches, label reference limitations and mark industry controls unavailable unless actual member/index coverage exists; never conflate a broad index with style/industry matching.
- [ ] Verify new tests and all `test_a_share_event*.py` / `test_a_share_audit*.py`; confirm no random forecast bends and no claimed calibrated probability.

## Task 5: Shared multi-expert prediction, task persistence and API facade

**Files:**
- Create `src/services/market_workspace_research.py`, `api/v1/endpoints/market_workspace.py`.
- Modify `api/v1/router.py`, `src/services/a_share_integrated_research.py`, `src/services/a_share_integrated_prediction.py`, `src/services/a_share_integrated_validation.py` to accept explicit market/price/currency/session context where currently hardcoded.
- Reuse MarketJobs, model usage journal, model budget and research progress helpers.
- Test `tests/test_market_workspace_research.py`, `tests/test_market_workspace_api.py`.

**Interfaces:** `/api/v1/market-workspace/{market}` exposes catalog, stock, history, refresh, sectors/members, research-data and integrated-research paths. CN calls existing services. Offshore POST produces a qualified durable task; GET reads cache/task without invoking model.

- [ ] RED API tests: authentication parity; invalid market/symbol; error states; disjoint task keys; model disabled/unconfigured; repeated POST de-duplication; GET and quote refresh make zero LLM calls.
- [ ] RED pipeline tests using only external-response substitution: evidence delivery -> role claims -> numerical validation -> report save -> subsequent GET/chart binding; missing evidence and bad citations cannot publish.
- [ ] Implement shared runner market prompt, preserve six existing roles, evidence budget/ledger and role progress; no unlimited automatic retries or guessed ETA.
- [ ] Run API/pipeline tests and current integrated/research/progress tests, including CN compatibility.

## Task 6: Full value workflow in each market

**Files:**
- Create `src/services/market_workspace_value.py`.
- Modify current value service/context/research/reference/strategy/economics/peers/holding/monitoring/valuation modules only for explicit identity, currency, source and capital dependencies.
- Extend market facade with value-research, assumptions, evaluation, supplement and peer-confirmation actions mirroring current contracts.
- Test `tests/test_market_workspace_value.py`, `tests/test_market_workspace_value_api.py`.

**Interfaces:** market-qualified value service uses existing ValueFact/ValueSnapshot/ValueAssumptions and `evaluate_value(assumptions, snapshot)` arithmetic, with explicit native/valuation/quote currency and listing capital bindings. Results retain formal/reference separation.

- [ ] RED fixtures for US operating company, HK CNY-reporting/HKD-quoted company, financial company, ADR, missing debt, stock compensation/dilution and unsupported security type.
- [ ] RED tests for absent/dated FX blocking safety price; ADR ratio blocking per-listed-security value; 6/12/24/36 holding results; peer comparability; manual supplement and native-currency units.
- [ ] RED tests at shared valuation entry: mismatched market-qualified identity, raw-price basis, FX direction/date/currency or listed-unit entitlement blocks every dependent comparison/return/overlay. Keep native enterprise value and null blocked quote outputs; stamp lineage on ValueReport, reference and holding outputs. Cash-flow currency must agree with discount-rate rationale.
- [ ] RED tests for rejected model assumptions retaining diagnostics; valid cited proposals produce three valuations only when constraints are complete; reference trials never get formal chart levels.
- [ ] Implement context injection and currency-safe output conversion, sharing existing valuation arithmetic, guards and old-record defaults.
- [ ] Replace blanket same-day capital requirements with effective share date plus auditable post-date action coverage. Missing coverage blocks publication with a specific supplement request, without backdating or inventing same-day share facts.
- [ ] Run all `tests/test_a_share_value*.py` and new cross-market value/API tests; fail closed for missing quantitative preconditions while preserving completed qualitative research.

## Task 7: Unified assistant UI and chart/research integration

**Files:**
- Create `apps/dsa-web/src/api/marketWorkspace.ts`, `apps/dsa-web/src/types/marketWorkspace.ts`, `apps/dsa-web/src/components/a-share/MarketSelector.tsx`.
- Modify existing ASharePage, InvestmentWorkspace, MarketStockBrowser, SectorBrowser/Detail, StockDetail, history/live/integrated/value hooks, priceChartData/valueChartData and value panels through a market data-client boundary.
- Update existing strings/styles and add tests beside affected components; preserve A-share API default behavior.

**Interfaces:** market data client supplies existing hooks with market-qualified request keys and market metadata. `MarketSelector` chooses cn/hk/us; selected instrument and persisted UI state are keyed by market. Chart drawing and panel structure remain shared.

- [ ] RED interaction tests: CN -> HK -> US -> CN state restore; delayed old request cannot overwrite new selection; aliases resolve to one watchlist row; catalog/industry click filters members.
- [ ] RED chart tests: correct quote currency and financial currency; raw/provider-adjusted labels; temporary vs completed bar; future session labels; stale market/FX/adjustment report rejected from overlay with explanation.
- [ ] RED research tests: one toolbar, chart directly below quote, full value/forecast panels, progress/resume/retry; no polling-triggered generation; unavailable blocks show actionable reasons.
- [ ] Implement market selector and client injection, replacing hardcoded ¥/Shanghai only where required. A-share rules remain available only in CN; all existing A-share controls remain reachable.
- [ ] Run impacted Vitest suites, scoped lint, TypeScript/build and existing A-share workspace/navigation/chart/value tests.

## Task 8: Real-source acceptance, runtime verification and delivery

**Files:**
- Add `docs/multi-market-assistant.md`; update `docs/market-support.md`, `docs/a-share-value-investing.md`, flat `docs/CHANGELOG.md` and new config examples if applicable.
- Add reproducible network-marked smoke checks under tests; one-time evidence/logs go outside Git.

**Interfaces:** acceptance report records source, instrument, timestamps, actual field coverage, model task/result status and limitation; model stub results and paid real-model results have distinct headings.

- [ ] Run deterministic full affected backend suites and complete frontend test/build. Verify old CN endpoints and no credentials in changed files/artifacts.
- [ ] Live-probe AAPL/MSFT and 00700/01810 catalog, identity, completed/raw/adjusted prices, financial facts and news; record actual availability/latency and access failures.
- [ ] Announce actual model-use scope; perform one real unified research/valuation attempt per new market, retaining its result even if partial; do not charge automatic repeated retries.
- [ ] Back up runtime files/hashes and update only affected code/build assets; preserve model/search configuration and databases. Verify server health and same-page browser behavior with all three markets.
- [ ] Record accurate passing/failing checks, coverage, remaining source gaps and rollback paths. Do not claim live success from offline fixtures. Keep branch uncommitted unless the user separately asks to submit/push.

## Self-review and execution notes

- All five requested capabilities are covered; event matching and full value workflow have their own deliverables, not placeholder UI.
- Data ownership flows Task 1 -> 2/3 -> 4 -> 5/6 -> 7 -> 8. API contracts must be finalized before the UI consumes them; value currency conversion cannot proceed from quote-only facts.
- Avoid parallel implementation on shared schemas/services; execute sequentially in this chat. Runtime is a separate directory and must be verified separately from source tests.
- Public-page access does not prove stable automated access. Official-source restrictions, unavailable ADR/FX fields and sparse history are explicit runtime states, not reasons to fabricate numbers.
- Existing known unrelated lint/test failures must be distinguished from regressions, with new scoped and affected suites passing before deployment.


## Delivery notes (2026-11-16)

Implemented capabilities and verified limits are recorded in [acceptance](../../multi-market-acceptance-2026-11-16.md). Provisional test filenames above were grouped into market_workspace symbols/service/financials/events/research/value/API/network tests. Queue namespace support lives in a repository facade; shared event modules were extended directly instead of creating a parallel market event engine. Keep the original task checklist as the reviewed implementation brief; the acceptance record states what actually ran and which source/model checks remain partial.
