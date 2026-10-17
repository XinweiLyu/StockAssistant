# StockAssistant

An A-share research assistant combining market data, historical candlesticks, industry and concept filters, disclosures, news and conditional AI research in one workspace.

[简体中文](../README.md) · [繁體中文](README_CHT.md)

## Current features

- Stock search, industry/concept filters, sector performance and constituent lists.
- Historical candlesticks, optional indicators, manual market refresh, research ranges and strategy reference lines.
- Available financial statements, valuation data, disclosure texts and news used for source-linked 5/20/60-session conditional research scenarios.
- Data preparation and research progress, missing-data explanations and saved reports.
- Existing chat, analysis, screening, portfolio, backtest and settings pages.

The application does not place orders. Data availability depends on provider permissions, service availability and historical coverage.

## Run locally

Use Python 3.11 or later and the Node.js/npm versions required by [package.json](../apps/dsa-web/package.json).

```sh
git clone https://github.com/XinweiLyu/StockAssistant.git
cd StockAssistant
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
cd apps/dsa-web
npm ci
npm run build
cd ../..
./scripts/run-a-share.sh
```

Configure your model service locally in `.env` or the settings page. Search and paid data providers are optional. The default assistant URL is `http://127.0.0.1:8000/assistant`; see the [run guide](a-share-assistant.md) for listener configuration.

Only configuration templates belong in this repository. Keep actual API credentials, advanced routing configuration, account/portfolio databases, analysis records and logs local. The optional `litellm_config.example.yaml` uses environment-variable references for credentials.

## Research limits

The project includes a price-model baseline, initial historical-case research and multi-role conditional scenarios. These are not validated profit strategies or a completed event-to-daily-price forecasting model.

The complete medium/long-term event lifecycle, expectation surprise, priced-in assessment, impact duration/decay and incremental event-price paths still require implementation and validation. Qlib is not integrated. See the [event-pathway design](superpowers/specs/2026-10-17-event-impact-pathway-design.md).

## Documentation

- [Assistant setup and data boundaries](a-share-assistant.md)
- [Integrated research](a-share-integrated-research.md)
- [Repository setup and initial upload checks](stockassistant-repository.md)
- [Changelog](CHANGELOG.md)

## Attribution and licenses

Based on [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis), retaining its [MIT license](../LICENSE). Selected research roles and constraints are adapted from the Apache-2.0-covered code of [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN).

See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for sources, revisions, modification scope and license copies.
