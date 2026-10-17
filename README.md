# StockAssistant

A股交易研究助手，整合股票行情、历史K线、行业与概念筛选、新闻公告和AI条件研究，方便在同一页面查看分析依据与策略参考。

[English](docs/README_EN.md) · [繁體中文](docs/README_CHT.md)

## 当前功能

- **市场与板块**：股票搜索、行业和概念筛选、板块涨跌展示及成分股查看。
- **K线工作区**：历史蜡烛图、可选技术指标、手动行情刷新，以及研究区间与策略参考线。
- **综合研究**：整理可获取的财报、估值、公告原文与新闻，生成有来源、条件和失效说明的5/20/60交易日研究情景。
- **研究进度与历史**：显示资料准备、模型研究阶段、结果和缺失项，保留历史报告。
- **原有入口**：保留问股、分析、选股、持仓、回测及设置功能。

系统提供研究参考，不自动下单。可用资料取决于数据源权限、接口状态和历史覆盖；缺失资料会影响研究结果。

## 本地运行

需要 Python 3.11或以上，以及符合 [前端依赖要求](apps/dsa-web/package.json) 的Node.js和npm。

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

首次运行前，在本地 `.env` 或应用设置页配置模型服务；搜索和付费数据源按需配置。默认访问地址为 `http://127.0.0.1:8000/assistant`，监听参数见[运行说明](docs/a-share-assistant.md)。

仓库只提供配置模板。实际API密钥、高级路由配置、账户与持仓数据库、分析记录及日志保留在本地，不应提交到GitHub。高级模型路由可参考 `litellm_config.example.yaml`，其中密钥通过环境变量引用。

## 研究边界

当前包括价格模型基线、历史案例研究基础和多角色条件情景。它们不等于已验证的盈利策略，也不代表已完成事件对未来每日价格的量化预测。

完整的中长期事件生命周期、预期差、已计价程度、影响持续与衰减、事件增量价格路径仍待实现与验证；Qlib尚未接入。见[事件影响路径设计](docs/superpowers/specs/2026-10-17-event-impact-pathway-design.md)。

## 文档

- [A股助手运行、配置与数据边界](docs/a-share-assistant.md)
- [综合研究与历史事件说明](docs/a-share-integrated-research.md)
- [仓库配置与首次上传检查记录](docs/stockassistant-repository.md)
- [变更记录](docs/CHANGELOG.md)

## 来源与许可证

本项目基于 [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) 改造，保留其[MIT许可证](LICENSE)。部分研究角色与约束适配自 [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) 的Apache-2.0许可代码范围。

具体来源、版本、修改范围及许可证副本见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
