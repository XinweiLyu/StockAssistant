# 上游稳定性更新吸收记录

2026-11-24 对照 `ZhuLinsen/daily_stock_analysis` 的 `45d9a0eee8e84ba9c7732f3ba1e7fd6a60ed0f63`。相对本项目最初采用的 `ce364e457aab288863a5707e7b3df79786ad07f2`，上游有97个提交。本次只吸收下列经过对照的修复，不代表同步了全部上游功能。

## 本次范围

| 上游提交 | 修复与适配 |
| --- | --- |
| `bd7b76799484` / #2587 | 共享重入锁串行保护 MiniRacer 初始化、eval/execute/call，避免并发进入V8；重复初始化不等待正在求值的运行锁，close和析构不额外加锁。保留可选依赖缺失时继续运行。 |
| `626eec11ff53` / #2602 | 定时分析已经回报结果、但工作进程未及时退出时，先清理进程，再保留真实成功/失败/跳过结果。没有结果或真正超时的任务仍报告失败。 |
| `2186f455fb83` / #2607 | 选股整数环境变量为空、空白或非法时使用默认值；保留原有最小值约束与后备配置。不改现有模型渠道配置。 |
| `15c7cdc0ca07` / #2479 | 工具结果和调用参数中的非有限浮点递归转为null，用严格JSON发送；补齐本项目真实工具执行中先转字符串的路径及脱敏输出，共用归一化逻辑，保留字符串和有限数值，不修改原始消息。 |
| `3acb2c5b585c` / #2557 | 没有真实历史平均置信度时保持中性，不再用固定0.6伪装历史统计来调整研究置信度。 |
| `76c59e8bd6c3` / #2501 | 基本面聚合复用已获取报价；明确传入None表示之前已失败/关闭，避免再次请求挤占财报及资金资料预算。独立调用仍可获取报价。保留本项目市场适配。 |
| `7b16d647ae7e` / #2528 | Tushare权限/积分不足按接口、网关及凭据摘要缓存6小时，立即尝试其他来源；不将单接口无权限等同整个供应商故障。频次限制和网络错误继续使用各自原有处理。选股路径同步区分权限失败及凭据变化。 |

本次不修改模型、密钥、付费数据配置、数据库结构或已保存研究，不新增自动模型调用。公开行情接口的可用性仍取决于上游服务及网络。

## 选择性更新与后续边界

没有引入上游赞助推广、官网、README预览、协作规则迁移、默认模型替换或发布流水线重构。单股超时隔离 #2572 改动涉及任务取消、外部进程和写入边界，不能只摘取超时数值；本次未引入，不宣称所有挂起问题已经解决。新增付费供应商不因本次更新自动启用。

本次核查时没有独立的热点资讯导航；用户随后确认新增集中入口，已按独立页面变更实现，见[热点资讯](news-center.md)。复用现有 `/api/v1/intelligence` 的已存新闻、来源模板、来源状态和采集接口，个股报告的新闻继续保留。来源未启用、采集失败或发布时间未知时，不能把空列表解释成市场没有新闻。

## 验证与回滚

定向测试：

```sh
python -m pytest -q tests/test_screening_config_env.py tests/test_llm_adapter_provider_trace.py tests/test_runtime_scheduler_service.py tests/test_multi_agent.py tests/test_fundamental_context.py tests/test_pipeline_index_targets.py tests/test_tushare_permission_circuit_breaker.py tests/test_mini_racer_guard.py
python -m pytest -q tests/test_agent_tool_serialization.py tests/test_agent_tool_surface.py tests/agent/test_tool_timeout.py
```

完整后端检查使用 `bash scripts/ci_gate.sh all`。MiniRacer真实并发测试在隔离子进程中运行，定时任务测试需要允许创建、检查及清理测试子进程。离线测试不验证付费Token的实际权限，不发起付费模型请求。

回滚恢复部署前涉及的源码，使用原有 `scripts/run-a-share.sh` 启动；保留 `.env`、模型路由配置、数据库及用户分析记录。新增保护均为进程内状态，重启后重新建立。

本专题仅提供中文操作记录；没有修改已有双语配置契约，无对应英文专题需要同步。
