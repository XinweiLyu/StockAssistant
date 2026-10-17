# StockAssistant 仓库快照与新机配置

本仓库首次上传于2026-10-17，采用当前源码快照建立独立的 main 分支，不携带本机配置及运行资料，也不导入不完整的上游 Git 历史。

## 来源

- 基础框架：daily_stock_analysis，来源 https://github.com/ZhuLinsen/daily_stock_analysis ，参考提交 `ce364e457aab288863a5707e7b3df79786ad07f2`。根目录保留原 MIT 许可证。
- TradingAgents-CN 适配的代码范围和 Apache-2.0 许可见 `THIRD_PARTY_NOTICES.md` 和 `src/agent/cn_research/LICENSE`。
- 本项目的A股助手改造代码、测试、相关设计及专题文档包含在本次快照中。

## 新机器运行

需要 Python 3.11或以上，以及符合 `apps/dsa-web/package.json` 的 Node/npm 版本。

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

在 `.env` 中填写自己的模型/搜索/可选数据源凭据，或在启动后的设置页配置。不要提交实际密钥。高级 LiteLLM 路由示例若需使用，可将 `litellm_config.example.yaml` 复制成 `litellm_config.yaml`，在 `.env` 中配置其引用的环境变量，并将 `LITELLM_CONFIG=litellm_config.yaml`。路由示例沿用现有参数；使用成本和可用性取决于服务商，不代表新账号已有额度。

启动后打开 http://127.0.0.1:8000/assistant 。来源权限、数据缺失、运行约束及端口配置见 `docs/a-share-assistant.md`。

## 上传范围

包含源码、测试、锁文件、部署脚本、公开静态素材、许可证和使用文档。排除 `.env`、实际 `litellm_config.yaml`、数据库与账户记录、研究/分析缓存、日志、截图验收材料、虚拟环境、node_modules 和构建输出。源码中的演示数据及测试夹具属于程序的一部分，保留。

完整中长期事件影响路径仍是升级设计，Qlib尚未接入；不要把设计文档视为已上线功能。此快照用于版本保存，不表示全部上游测试均已通过。

## 首次上传前检查

- 全部712个Python源码文件通过语法解析检查。
- A股相关后端测试377项通过。
- 前端125个测试文件通过，1447项测试通过、2项跳过；前端构建通过。
- 真实配置中的凭据未出现在候选上传文件中；配置模板仅引用环境变量。
- 现有前端静态检查仍有1个错误和1个警告：`LiveChipSnapshot.tsx` 的effect内同步状态更新，以及 `StockScreeningPage.tsx` 的effect依赖提示。本次源码保存未修改这些功能代码。
- 未重新运行全部上游后端测试，也未执行付费模型或实时数据端到端测试；不能据本次检查声称全项目所有检查均通过。
