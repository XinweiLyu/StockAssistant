# StockAssistant

A股交易研究助手，整合股票行情、歷史K線、產業與概念篩選、新聞公告及AI條件研究，方便在同一頁面查看分析依據與策略參考。

[简体中文](../README.md) · [English](README_EN.md)

## 目前功能

- 股票搜尋、產業與概念篩選、板塊漲跌展示及成分股查看。
- 歷史蠟燭圖、可選技術指標、手動行情更新，以及研究區間與策略參考線。
- 整理可取得的財報、估值、公告原文與新聞，產生附來源、條件及失效說明的5/20/60交易日研究情景。
- 顯示資料準備與模型研究進度、結果和缺失項，保留歷史報告。
- 保留問股、分析、選股、持倉、回測及設定入口。

系統提供研究參考，不自動下單。資料可用性取決於來源權限、介面狀態及歷史覆蓋；資料缺失會影響研究結果。

## 本機執行

需要Python 3.11或以上，以及符合[前端相依要求](../apps/dsa-web/package.json)的Node.js和npm。

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

首次執行前，在本機 `.env` 或應用程式設定頁配置模型服務；搜尋及付費資料來源按需配置。預設網址為 `http://127.0.0.1:8000/assistant`，監聽參數見[執行說明](a-share-assistant.md)。

儲存庫只提供設定範本。實際API金鑰、進階路由設定、帳戶與持倉資料庫、分析紀錄及日誌應保留在本機，不應提交至GitHub。進階模型路由可參考 `litellm_config.example.yaml`，其中金鑰透過環境變數引用。

## 研究邊界

目前包含價格模型基線、歷史案例研究基礎及多角色條件情景；它們不等於已驗證的獲利策略，也不代表已完成事件對未來每日價格的量化預測。

完整的中長期事件生命週期、預期差、價格已反映程度、影響持續與衰減、事件增量價格路徑仍待實作與驗證；Qlib尚未接入。見[事件影響路徑設計](superpowers/specs/2026-10-17-event-impact-pathway-design.md)。

## 文件

- [A股助手執行、設定與資料邊界](a-share-assistant.md)
- [綜合研究與歷史事件說明](a-share-integrated-research.md)
- [儲存庫設定與首次上傳檢查紀錄](stockassistant-repository.md)
- [變更紀錄](CHANGELOG.md)

## 來源與授權

本專案基於 [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) 改造，保留其[MIT授權](../LICENSE)。部分研究角色與約束適配自 [TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) 的Apache-2.0授權程式碼範圍。

具體來源、版本、修改範圍及授權副本見 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
