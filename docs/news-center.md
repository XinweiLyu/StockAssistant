# 热点资讯

侧栏“热点资讯”或 `/news` 独立浏览。市场热点显示当前所选市场及全球背景的NewsNow聚合资讯；新闻快讯显示全部已采集来源；我的自选只查询当前市场前100只自选、且来源明确关联了该股票的资讯。标题提及某公司、热度上升或市场级新闻不会被自动归属成个股证据。

可按A股/港股/美股、来源、关键词和最近采集1/3/7/30天筛选，每页20条。采集范围指系统读取时间，不保证发布时间也处于该窗口。发布时间未知明确标注；带偏移的时间按北京时间显示。已有无偏移记录无法区分转换后的UTC与上游未声明时区，因此统一标“时区未标注”，不推断UTC；采集时间保留原服务时钟语义。全球背景会另行标注，不冒充特定市场公告。

页面可见时每5分钟检查并尝试刷新已启用来源，采集中每2秒读取进度。隐藏或离开停止页面请求；已接受的后台采集继续完成。同一应用实例只保留一个刷新任务，服务端执行300秒冷却，重复点击复用状态/缓存，不产生并行批次。多进程部署各有独立刷新状态；当前本地启动为单应用进程。读取失败保留同一筛选下已加载的资讯，切换筛选不显示之前市场的结果。

首次打开没有来源时，展开“来源状态与管理”，点击“添加内置免费来源”，或启用已有来源。添加使用原有RSS/Atom/NewsNow模板；已存在而被关闭的来源不会被添加操作重新启用，可逐一勾选。明确关闭的来源用既有状态字段记录，自动分析的默认源初始化及在途采集都不会撤销这个选择；未被用户关闭的初始默认源保持旧自动初始化行为。可查看各来源上次成功时间、失败状态及脱敏错误。公开源可能限流、失效或不提供发布时间；空列表不代表市场没有新闻。港股/美股不承诺交易所全部历史公告覆盖。这里不要求新密钥、不自动调用模型、不自动推送消息或下单。

带有明确股票关联的条目可点“查看股票”，通过与原助手一致的市场/证券规则进入原交易助手。A股仍处于演示模式时，显示请求的真实代码和切换数据模式提示，不代换成演示公司。原文仅允许不带用户名/密码的http或https链接。自动采集仍沿用现有URL、DNS及重定向防护。页面没有把搜索摘要变成公告原文或已验证事件。

## API与兼容

认证沿用现有应用。原 `/api/v1/intelligence/items` 参数继续可用，追加 `source_type`、`source_id`、`symbols`（最多100个，空集合返回空结果）、`include_global`；过滤在分页之前执行。自选证券前缀与常见港股代码形式在同市场内匹配，不跨市场归并。

- `GET /api/v1/intelligence/refresh`：刷新进度、处理数、失败数和冷却时间。
- `POST /api/v1/intelligence/refresh`：后台拉取已启用来源，不隐式启用来源。
- `PATCH /api/v1/intelligence/sources/{id}`，`{"enabled":true|false}`：只修改启用状态。

无新增数据库结构或依赖。回滚恢复部署前源码及前端构建，用原启动脚本启动，保留新闻、配置及研究数据库。

## 本地验收与网络排障（2026-11-24）

最终后端检查8857通过、769子测试通过，10个在线测试未包含在离线套件；前端1535通过、2跳过，生产构建通过，lint零错误、一个原有选股页依赖警告。本地健康、页面、资讯读取与刷新状态均返回200；独立浏览器验证导航、市场切换、自选视图和600519跳转，未发现页面运行错误。

首次来源初始化遇到 Fake-IP：四个公开资讯域名被解析为 198.18.0.0/15 保留地址，应用拒绝连接。恢复本机自动 DNS 后，保留系统代理并实测完成采集。8 个内置来源全部成功，首次入库 178 条，A 股热点、港股快讯和美股快讯接口均读取到了真实记录。这次采集在增强模式停用时验证。若再次出现 Fake-IP，先检查代理的 DNS 规则，确认资讯域名返回公网地址，再重新添加来源或刷新。

独立板块资金在线探测也出现不稳定：一次排行成功、历史接口失败，随后直接排行请求连接失败。资金页面保留原缓存与错误状态，不保证免费源持续在线。本次没有替换成伪造新闻或资金数据。

## English coverage note

The new Market News navigation reuses existing RSS/Atom/NewsNow sources with no automatic LLM calls. It offers market aggregation, all news and explicitly tagged watchlist news for CN/HK/US; global stories and unknown publication dates remain labeled. Visible pages check every five minutes, refresh jobs coalesce per app instance, and source failures retain cached items. This is not a complete exchange-disclosure feed or a validated trading signal. Existing research and assistant routes remain available.
