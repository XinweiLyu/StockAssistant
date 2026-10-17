# Multi-cycle outlook implementation

Approved intent: implement the strategy research delivered on 2026-10-14. Preserve existing reports, assistant rules, AI scenarios, settings, filters and charts. Work on the existing `feature/a-share-assistant` checkout; do not commit, push, reset or overwrite unrelated work. The user has requested execution of the reviewed research; execute continuously.

## Scope

Deliver long-cycle/finished-week indicators, a local statistical price baseline with chronological validation, risk-filtered observation levels, immutable forecast snapshots and event observations in the same chart. Existing 120-day rules remain unchanged and versioned. Numerical forecasts do not call the LLM. Price-model evaluation is not portfolio profitability; event observations do not establish causality. Reuse current dependencies and resumable data jobs; Qlib is optional, not a required migration.

## Shared contract

Engine: `src/services/a_share_outlook.py`

```python
def build_outlook(bars, calendar, as_of, *, benchmark=(), sector=(), events=(), min_reward_risk=2.0) -> dict:
    # Input rows: date/open/high/low/close/adjusted_close/volume/amount.
    # Returns numerical fields below in actual-price units rebased to the last close.
    ...
```

API: `GET /api/v1/a-share/market/stocks/{code}/outlook?min_reward_risk=2&refresh=false`. Ratio finite and within1–5. Reads cache, queues selected-stock history when necessary, never calls LLM.

```typescript
interface QuantOutlook {
  code:string; status:'pending'|'ready'|'partial'|'insufficient'|'failed';
  version:string; as_of:string; generated_at:string; history_sessions:number;
  reference_price:number|null; price_basis:'raw'; source:string|null;
  adjustment_basis:string|null; raw_anchor:number|null; qfq_anchor:number|null;
  data_hash:string; demo:boolean;
  trends:{period:number;ma:number|null;distance:number|null;slope:number|null;state:'up'|'down'|'range'|'insufficient'}[];
  weekly:{as_of:string|null;ma10:number|null;ma30:number|null;state:'up'|'down'|'range'|'insufficient'};
  environment:{market_state:'up'|'down'|'range'|'unknown';relative20:number|null;relative60:number|null;sector_relative20:number|null;sector_relative60:number|null};
  forecasts:{horizon_sessions:number;target_date:string|null;low:number;median:number;high:number;sample_size:number;method:string;nominal_coverage:number;calibration_state:'historical'|'insufficient';validation:{state:'measured'|'insufficient';samples:number;coverage:number|null;mean_absolute_error:number|null;baseline_mean_absolute_error:number|null;method:string};points:{sessions:number;date:string|null;low:number;median:number;high:number}[]}[];
  plan:{status:'observe'|'conditional';horizon_sessions:number;entry_low:number|null;entry_high:number|null;stop:number|null;target_low:number|null;target_high:number|null;reward_risk:number|null;min_reward_risk:number;valid_until:string|null;conditions:string[];invalidation:string[];reasons:string[]};
  events:{id:string;title:string;url:string|null;date:string|null;published_at:string|null;first_seen:string|null;kind:string;verified:boolean;impact:{state:'observed'|'insufficient';samples:number;horizon_sessions:number;median_excess:number|null;low:number|null;high:number|null;reason:string}}[];
  archive:{snapshots:number;matured:number;coverage:number|null;mean_absolute_error:number|null};
  limitations:string[];
}
```

Unknowns are null/insufficient. Low/median/high positive finite. Forecast horizons5/20/60 trading sessions; intermediate points are separately forecast, connecting lines are display interpolation. Unknown future calendar dates stay null. Overlay requires matching stock/source/anchor/price basis. Nominal interval coverage is not measured accuracy. Preserve legacy fields.

## Task 1: numerical engine and event observations

Own only the new engine/helper modules and `tests/test_a_share_outlook.py`. First write and run failing tests for future-bar exclusion, MA250 warmup, incomplete-week exclusion, duplicate/calendar-gap/nonfinite input, forward-label chronology, ordered positive intervals, chronological non-overlapping validation, no training accuracy mislabeled as validation, and low reward/risk rejection without inflating targets.

```python
assert build_outlook(history, calendar, cutoff) == build_outlook(history + future_rows, calendar, cutoff)
```

Implement multi-cycle indicators, a deterministic small regularized baseline, residual intervals and rolling-origin validation with horizon purging and training-only preprocessing. Compare against unchanged-price baseline. Event taxonomy retains source/time; deduplicate revisions, use first-available timestamp, matured outcomes and aligned benchmark for observational excess returns. Unknown or immature evidence stays insufficient. No news-trained model claim. Conditional plan requires trend/baseline/reward-risk conditions. Run `.venv/bin/python -m pytest tests/test_a_share_outlook.py -q`, RED then GREEN.

## Task 2: service/API/archive

Root owns `src/services/a_share_service.py`, optional adapter `src/services/a_share_outlook_service.py`, API endpoint and integration tests. Test actual SQLite fixtures: non-candidate access does not create candidates; demo does not queue real sources; source mismatch queues consistent repair; repeat GET does not duplicate immutable daily snapshots; new data creates new identity; material verified risk blocks plan; archive evaluation excludes pre-issuance/missing/not-mature endpoints; existing AI scenarios remain compatible.

Use full cached completed history. Request up to five calendar years for selected stock and benchmark/known sector through existing jobs; preserve longer ranges. This matches the existing public history API's five-year limit and is sufficient for the initial MA250/rolling baseline; longer already cached history is still consumed. Stable cache identity covers mode/code/date/data/version/ratio and event verification. Append changed snapshots to existing journal. Add long-cycle facts to AI price evidence without removing old fields or adding model calls on read. Existing v1 rule scoring stays unchanged. Run focused integration plus existing price/market/research tests.

## Task 3: frontend

Own A-share market types/API, chart data/controls/chart, StockDetail, new QuantOutlookPanel/hook and related tests/CSS only. First run failing tests for MA120/250 warmup/values, default20 and switches5/60, ratio-request changes, fan overlay basis matching, missing calendar, abort/switch/loading/error handling, event links, and preserved legacy reports/scenarios.

```tsx
expect(screen.getByLabelText('预测期限')).toHaveValue('20');
```

Add indicators and completed-week summary. Fetch outlook independently from LLM scenarios; no model cost on toggles. Integrate horizon/ratio controls, validation/risk/evidence cards and future fan with matching price mapping. Preserve candles, zoom, keyboard/hover, legacy dashed lines and sector comparison; only display new fan when latest history includes its anchor. Use HTTP(S) links only. Tests, lint and build must pass for changed files; full frontend suite/build required.

## Task 4: integration/docs/review

Update assistant docs, strategy review and flat Unreleased changelog. Explain method, date/price basis, gaps, costs, validation and rollback; do not claim measured improvements that do not exist. Backend compile/offline tests; frontend full suite/lint/build; real local API and browser after build/restart. Save screenshot outside repository. Fresh review focuses on leakage, adjusted price, caching/races, event revisions, metadata gaps and legacy compatibility. Fix important findings with RED→GREEN.

## Operational constraints and progress

Do not purchase data, place trades, change accounts, commit or push. Original application files are preserved because the running app depends on pre-existing uncommitted work. Progress lives in the task mirror's `outputs/a-share-implementation-progress.md`; retain it because there are no commits to serve as the record. User approval of the preceding research and direct implementation request supplies task authorization.
