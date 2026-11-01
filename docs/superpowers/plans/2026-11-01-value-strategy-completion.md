# Value Strategy Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 补齐已确认审查范围的价值研究闭环，优先修复计算问题，保留原有功能和真实数据限制。
**Architecture:** 复用价值快照/事实/估值/假设/事件与journal，增量增加可审计经济底稿、预期试算和复核。程序计算及核验，AI解释并提出有来源的未确认假设，GET不抓取或收费。
**Tech Stack:** existing Python/FastAPI/Pydantic/pytest and React/TypeScript/Vitest.
**Spec:** docs/superpowers/specs/2026-11-01-value-strategy-completion-design.md

## Global Constraints
- 按用户已确认审查范围和此前本会话直接实现方式执行；当前feat/value-investing保留七个未提交文件，不reset/stash/切分支。
- 不自动commit/tag/push，不改密钥或购买数据；sources只读。
- 同一股票/快照/假设/模型的缓存、引用和费用护栏保持；历史保留，规则版本升级明确过期。
- 新增字段为兼容可选项，缺失不填0；不把参考值升级正式安全价。

## Review Focus
- 同期现金流变化可能为一次释放而非永久年金：Task1反例。
- 有库存成本但无库存数量以及资本变动时不误用发行股数：Task1反例。
- 新股/周期/金融/负利润及年度断点不套稳定制造业推断：Task2/3适配测试。
- 无效报价、不可解/多解及异步换股不产生隐含预期或串数据：Task4/6测试。
- 假说证据过期、未到期及当期修订数据不能冒充历史预测验证：Task5/6测试。

### Task 1: Valuation mathematics
**Files:** valuation.py, holding.py, schema version, test_a_share_value_valuation.py, test_a_share_value_holding.py.
**Interfaces:** evaluate_method adds recurring terminal vs one-time adjustment diagnostics; issued_shares distinct from outside shares. evaluate_value binds cutoff.
- [x] Write and run failing tests: flat revenue100/FCFF10/NWC10→0/r.1 yields per-share10.56447393; treasury2/issued10/equity100 yields12.5 or explicit missing count; first dividend6months gives consistentV0/Vh.
- [x] Implement corrected math, common capital denominator and date binding, conservative unknown protection; correct DDM stress description.
- [x] Run value math/holding/review regressions and ledger evidence.

### Task 2: Source facts, financial quality and peers
**Files:** data_provider/a_share_value_facts.py; value_financials.py; new value_economics.py; value_service.py peer row; tests value_facts/economics/peers.
**Interfaces:** build_economic_analysis(view, model) returns metrics with value/unit/period/fact_ids/formula/limitations, flags and method needs. Peer rows consume matching metrics.
- [x] RED tests for total vs parent profit/CFO, missing inputs, average-equity ROE, operating margin/CFO-capex yield, financial sector exclusion, debt/receivables/inventory/profit-quality flags.
- [x] Add only verified raw field mappings, derive normalized metrics and explicit proxies, expose missing/gating reasons, keep source dates.
- [x] GREEN tests and actual saved Eastmoney raw payload replay; no new paid sources.

### Task 3: Company drivers and evidence-aware research
**Files:** new value_strategy.py; value_research.py; value_service.py; schemas; tests strategy/research/service.
**Interfaces:** build_value_strategy(snapshot, assumptions=None, report=None, portfolio=None) returns evidence-gaps, economics, company-driver histories/ranges, method suitability, economic checks. Append VALUE_STRATEGY evidence to bounded AI payload and output snapshot/GET strategy.
- [x] RED: three gap kinds; sourced annual histories and growth/margin/cash/capex anchored ranges; discontinuities/negative profits/insufficient periods; terminal dependence and growth/reinvestment diagnostics.
- [x] Implement company-specific research bottom-up inputs, targeted report windows for cost/segment/workingcapital/debt/governance; refine prompt to allow labeled future assumptions without inventing current facts. Keep formal risk gates.
- [x] GREEN and inspect real Dongpeng payload contains actual bottom-up evidence within48KB; retain sent/omitted tracking.

### Task 4: Reverse valuation and event paths
**Files:** new value_expectations.py; value_drivers.py; value_valuation.py; tests expectations/drivers.
**Interfaces:** reverse_value(case, view, price, price_basis) returns state, parameter, solution, bracket, held assumptions, evidence/limitations. apply_driver_changes handles method-specific fields and temporal type with backwards-compatible default decay.
- [x] RED: simple known price solution, no valid scenario, unreachable/nonmonotonic, unverified quote labeled input; DDM/RIM/NAV field changes with old-value/unit/source checks, no duplicate family, structural vs one-off duration.
- [x] Implement bounded deterministic solve and method-specific events, keep counterfactual reports; no historical price-return addition.
- [x] GREEN mathematical and event regression tests.

### Task 5: Holding review and forward evidence
**Files:** new value_monitoring.py; schemas assumption monitor_rules; value_service.py; tests monitoring/service/API.
**Interfaces:** build_monitoring(snapshot, assumptions, report, portfolio=None) returns due reviews, rule results, thesis/valuation/portfolio signals, forecast comparisons with matched actuals. Reuse assumption revisions and reports, no new database tables.
- [x] RED: due/unknown/breached/reviewed, same company/units/date, not-yet-mature observations, source-missing, long-term thesis vs short-term stop context.
- [x] Implement bounded explicit monitoring conditions, quarter checkpoints, valuation/portfolio conflict explanations and matured business forecast checks. Do not auto-submit orders or auto-charge.
- [x] GREEN compatibility/API and persisted assumption roundtrip tests.

### Task 6: Same-page UI and delivery
**Files:** types/aShareValue.ts; new ValueStrategyPanel.tsx; ValueInvestingPanel.tsx; ValueAssumptionEditor.tsx; tests; docs/a-share-value-investing.md; flat CHANGELOG.
**Interfaces:** Optional strategy payload on value GET; monitor_rules in existing save; quality, company drivers, method needs, price-implied inputs, event effect and review results displayed under existing value section.
- [x] RED UI tests: actual data/unknown states, reference labeling, monitor editing, no extra AI call, stock switch and stale compatibility, original comparison cards preserved.
- [x] Implement integrated UI and docs; full backend not-network tests, full frontend tests, scopedlint/build.
- [x] Fresh independent code review, TDD fixes; backup runtime, deploy without secrets/DBschema changes; actualAPI+browser evidence, one explicitly announced model integration if needed. Record partial failures honestly.

No task commits without a new explicit request. Complete ledger/validation artifacts instead. Financial forecasts need forward validation over time; do not claim proven investment performance.
