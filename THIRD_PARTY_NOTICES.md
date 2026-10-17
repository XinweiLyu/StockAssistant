# Third-Party Notices

This repository includes software derived from third-party projects. The
following notice applies to the files identified below.

## AlphaSift

- Project: AlphaSift
- Source: https://github.com/ZhuLinsen/alphasift
- Referenced revision: `9f522747caafd3c0b1ddb7e14d5cf44c8580b6cf`
- License: Apache License 2.0
- Included and modified files: `src/services/screening/**/*.py` and
  `src/services/screening/strategies/*.yaml`
- License copy: `src/services/screening/LICENSE`

The included code has been modified and integrated into
`daily_stock_analysis`. Per-file headers identify the source revision and
modification status.

## TradingAgents-CN research adaptation

- Source: https://github.com/hsliuping/TradingAgents-CN
- Revision: `51060a7682cf51810b4bc3a704829438d18cd8dc` (v3.0)
- Copyright 2024-2026 hsliuping & TradingAgents-CN Contributors
- Applicable license: Apache License 2.0 for `tradingagents/`
- Vendored utility: `src/agent/cn_research/compliance_prompting.py`, from
  `tradingagents/agents/utils/compliance_prompting.py`, with provenance header.
- Adapted role design/prompt excerpts: `src/services/a_share_research.py`, from
  `tradingagents/agents/researchers/bull_researcher.py`, `bear_researcher.py` and
  research-manager role constraints. Orchestration, budget, evidence contract and
  storage have been independently implemented for DSA.
- License copy: `src/agent/cn_research/LICENSE`.
- No code from upstream `app/`, `frontend/` or root `core/` is distributed here.

## daily_stock_analysis application foundation

- Source: https://github.com/ZhuLinsen/daily_stock_analysis
- Referenced revision: `ce364e457aab288863a5707e7b3df79786ad07f2`.
- License: MIT; original copyright and license are retained in `LICENSE`.
- StockAssistant adds and modifies the A-share assistant, market/data services,
  research workflow, charts, API, tests, configuration examples and documentation.
- This initial repository import is a source snapshot, rather than a full copy of
  the upstream Git history.
