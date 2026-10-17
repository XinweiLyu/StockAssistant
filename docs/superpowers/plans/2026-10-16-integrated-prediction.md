# A股综合预测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有A股助手升级为具有来源、时间版本、可比历史事件、多专家复核、综合情景与条件策略的可运行研究流程，保留所有旧功能。

**Architecture:** 沿用CapabilityProvider、MarketJobs、追加式仓储日志、ResearchEngine和当前K线组件。用不可变ResearchBundle连接规范化财务/公告、纯函数案例匹配和专家研究；新接口及新图层采用追加契约。旧价格回归作为独立对照，未校准综合情景不复用其概率含义。

**Tech Stack:** 现有Python/FastAPI/Pydantic/SQLAlchemy/NumPy/AKShare/Tushare；React/TypeScript/Vitest；公告PDF仅新增pypdf用于有大小/页数/超时上限的文本提取，不引入Qlib运行依赖或新数据库。

**Spec:** `docs/superpowers/specs/2026-10-16-a-share-integrated-prediction-design.md`

**修订记录（2026-10-16）：** 用户选择“先调整计划”后，逐项核对原要求，明确补入新闻检索/事件抽取链路、按市场状态选择策略、预测对照与验证边界，并增加文末需求覆盖表。此记录只表示计划完善，不表示功能已经实现或用户已经批准修订后的执行。

## Global Constraints

- 先A股、优先免费来源、盘中行情约5分钟检查、手动模型调用不设次数上限、保留原有功能、不自动下单、不购买服务、不改用户密钥及模型部署、不执行提交或推送。
- 当时留存记录与事后补录资料分开；综合情景统一标“研究估计，尚未校准”。
- 初始回溯最多5个日历年，初始同业批次最多20家公司；相同事件/方向/行业案例至少10个不重叠事件、5家公司才输出数值案例参考。
- 同源raw/qfq和精确历史绑定继续有效，未匹配或过期研究不得叠加到当前图表。
- 新增只读结果接口和显式POST准备/生成操作；GET不触发收费模型。
- 不为完成测试清空数据库、覆盖.env、切分支、stash、reset、commit或push；现有未提交文件是当前应用的一部分。

## Review Focus

- 源只返回标题/最新修订财务时：能显示当前研究资料，但不能捏造事件强度或过去当时可用的财报版本。任务1、2测试固定此边界。
- 相同代码切换来源、同日复权刷新及旧任务迟到：旧研究保持可查，不能覆盖或叠加到新快照。任务3、5测试竞态和绑定。
- 同时出现两项利好、转载、更正及重叠收益窗口：按事件家族与期限去重，不把同一段行情当多项独立证据。任务2测试。
- 原文缺失、模型返回未知引用/异常数值/自行编造胜率或目标：拒收对应条目、保留其他结果及价格基线，不静默填默认价。任务1、4、5测试。
- 行情/财务已经变化但用户未重新研究：显示过期、资料变化和旧报告时间，不在GET或自动5分钟行情检查中付费重跑。任务3、5、6测试。

---

### Task 1: 规范财务/公告事实与来源

**Files:**
- Create: `src/schemas/a_share_integrated.py`
- Create: `data_provider/a_share_fundamentals.py`
- Create: `data_provider/a_share_disclosures.py`
- Modify: `data_provider/a_share.py`（能力白名单与财务/公告源选择）
- Modify: `requirements.txt`（`pypdf>=6.21.0,<7`，2026-10-16已在官方PyPI核实发布）
- Test: `tests/test_a_share_research_sources.py`

**Interfaces:**
- Consumes: `CapabilityProvider.call(name, params=None, tushare=False)`、`AssistantSettings`。
- Produces: `ResearchFact`、`ResearchBundle`、`normalize_financials(code, rows, source, observed_at) -> list[dict]`、`normalize_disclosures(code, rows, observed_at) -> list[dict]`。
- Produces: `ResearchSources(provider, settings).financials(code, observed_at) -> dict`、`.disclosures(code, start, end, observed_at) -> dict`、`fetch_disclosure_text(url, max_bytes=8388608, max_pages=80) -> dict`；返回显式`ready/partial/missing/failed/unauthorized`、来源、事实、缺失及覆盖范围。
- Produces: `ResearchSources.news(code, company_name, industries, cutoff) -> dict`，复用现有新闻/Tavily配置与客户端；按股票代码、经核对公司名及已知行业检索，再核对原文时间/实体；返回有来源的新闻/政策/外部观点及缺失状态，不把检索成功当作完整新闻覆盖。

- [x] **Step 1: 写财务时间/单位和原文边界反例。**

```python
def test_latest_restatement_is_not_historical_vintage():
    row = {'SECUCODE': '000807.SZ', 'REPORT_DATE': '2025-12-31',
           'NOTICE_DATE': '2026-03-20', 'UPDATE_DATE': '2026-10-15',
           'TOTALOPERATEREVE': 100000000, 'PARENTNETPROFIT': 10000000}
    fact = normalize_financials('000807', [row], 'eastmoney', '2026-10-16T10:00:00+08:00')[0]
    assert fact['available_at'] >= '2026-10-16'
    assert fact['historical_eligible'] is False
    assert fact['report_period'] == '2025-12-31'

def test_title_alone_cannot_be_numeric_event_strength():
    event = normalize_disclosures('000807', [{'代码': '000807', '公告标题': '业绩预增公告',
        '公告时间': '2026-07-14', '公告链接': 'https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1'}],
        '2026-10-16T10:00:00+08:00')[0]
    assert event['intensity'] is None
    assert event['text_status'] == 'missing'
```

另外覆盖NaN/Infinity、负利润、金融类字段、累计/单季不混合、代码不符、空值不补零、source URL不合法、公告日期只有日、源权限不足及允许/禁止回退。

新闻专项反例：同名异股不关联、转载不算多项独立催化、只有抓取时间不冒充发布时间、未来日期不进入截止日前资料、仅有摘要不冒充全文、Tavily失败保留公告/财务。外部分析师/机构观点必须有真实作者或机构、日期和原文链接，标为“外部观点”；不能把系统AI角色冒充真实专家，也不能从研究报告摘要补造盈利预测。

- [x] **Step 2: 运行确认失败。** `.venv/bin/python -m pytest tests/test_a_share_research_sources.py -q` 应因新模块不存在失败。
- [x] **Step 3: 实现事实模型与源适配。** 原始数字和单位保留；金额统一人民币元、百分比统一数值比例并记录原单位；`NOTICE_DATE`与`REPORT_DATE`分开，最新修订表标`provider_latest`。Tushare单股分页检查重复/进度，免费失败不影响旧行情；仅对允许的财务/巨潮接口扩白名单。

```python
class ResearchFact(BaseModel):
    fact_id: str
    code: str
    category: str
    values: dict
    source: str
    published_at: str | None = None
    observed_at: str
    available_at: str
    report_period: str | None = None
    vintage_quality: str
    historical_eligible: bool = False
    url: str | None = None
```

原文提取只接受核验的巨潮HTTPS地址/公告ID，拒绝任意主机、私网、重定向到非允许域；请求限时、按块限制8MiB、PDF最多80页并用子进程整体超时。HTML/PDF类型不符、扫描件无文本、超限都返回具体缺口，不把链接页当公告正文。pypdf版本已在[官方PyPI](https://pypi.org/project/pypdf/6.21.0/)核实，实施时仅安装该声明范围，不加载远端代码。

财务字段验收清单固定为：营收、归母/扣非利润及变化、经营现金流、现金含量、ROE、毛利率、负债率、可得EPS/每股净资产与估值。每项必须显示数据或缺失理由。TTM、单季及估值推导须有完整同口径输入；缺历史股本或当时估值不拼凑历史PE。商品/政策新闻附业务敞口证据，无法确认企业受益还是受损时输出未知，不能机械套行业标签。

资金/筹码维度复用现有成交量、成交额、换手及已获筹码记录；仅在股票、日期、复权和来源可核对时送入对应角色。筹码须标明供应商结果或估算方法，不称为真实账户持仓；缺少可读记录则明确缺失。本任务不把付费逐笔/机构成交或全市场筹码覆盖当作现成能力。

- [x] **Step 4: 跑单元测试及只读在线接口验证。** 离线测试覆盖真实字段夹具和失败路径；在线对000807单股主指标、三表与限定时间公告核对来源/时间/规模，输出计数与状态，日志不含密钥。正文提取至少验证一份真实业绩公告；未解析不声称已有强度。
- [x] **Step 5: 自审本任务。** 检查Tushare档位不是授权事实、企业单位不混淆、数据不回写历史，记录测试结果；遵循AGENTS不提交。

### Task 2: 可比事件研究及有条件数值参考

**Files:**
- Create: `src/services/a_share_event_cases.py`
- Test: `tests/test_a_share_event_cases.py`
- Modify: `src/schemas/a_share_integrated.py`（事件/案例结果契约）

**Interfaces:**
- Consumes: Task1规范事件/事实；按代码的同源复权日线、基准/行业日线、交易日历和行业有效期事实。
- Produces: `event_context(event, histories, calendar, cutoff) -> dict`、`match_event_cases(target, cases, cutoff, horizons=(1,5,20,60)) -> dict`；每期限输出门槛、匹配层、缺失、样本/公司数、收益/超额/不利变动分布及可审阅案例。
- Produces: `case_price_references(matches, reference_price) -> list[dict]`；仅通过门槛的期限有人民币价格参考，明确`historical_distribution`、非未来概率。
- Produces: `extract_event_facts(document, numeric_facts, completion=None) -> dict`；优先直接核对原文数字，必要时在显式模型生成阶段使用AI抽取。输出类别、方向、强度值/分母/单位、公告前已知预期、新颖度、业务敞口及片段引用；缺原文/分母/可靠预期时对应值为null。

- [x] **Step 1: 写前视、重复和可比性反例。**

```python
def test_future_or_unmatured_case_is_excluded(case_factory):
    result = match_event_cases(case_factory(target=True),
        [case_factory(event_date='2026-10-15', outcome_end='2026-11-12')],
        cutoff='2026-10-16')
    assert result['horizons']['20']['sample_size'] == 0

def test_unverified_past_industry_cannot_count_as_matched(case_factory):
    case = case_factory(industry_quality='current_membership_only')
    result = match_event_cases(case_factory(target=True), [case], cutoff='2026-10-16')
    assert result['horizons']['5']['numerical_eligible'] is False
    assert result['excluded']['unverified_industry'] == 1
```

同组还测试同公告转载/修订、同股重叠窗口、不同期限成熟度、市场状态不同、事前涨幅差异、缺估值不当0、当时未知价格/财务、跨来源行业名称、停牌/跳空、分位数范围顺序及边界10事件/5公司。

抽取测试需覆盖“同比增长”和“超市场预期”的区别、订单金额缺营收分母、回购计划与已实施回购、事件更正/撤销、新事件与已经反映在公告前涨幅中的旧消息，以及同一窗口其他事件的混杂标记。模型抽取的事实必须逐项核对片段；有来源ID但片段不支持数字的记录不进入案例强度。

- [x] **Step 2: 跑测试确认失败。** `.venv/bin/python -m pytest tests/test_a_share_event_cases.py -q`。
- [x] **Step 3: 实现纯函数匹配。** 先硬过滤截止时间/成熟度/事件家族/行业有效时间，再分层应用市场趋势、事前20日收益与强度分档、可用估值档。档位只看截止日前候选，存入结果。保留被排除数量和低可比参考，不以扩大样本掩盖不匹配。

```python
stock_return = adjusted_end / adjusted_pre_event - 1
market_excess = stock_return - market_return
industry_excess = stock_return - industry_return
# 两个超额分别解释，不能相加修正价格回归。
reference_low = reference_price * (1 + matched_stock_return_quantile_10)
reference_mid = reference_price * (1 + matched_stock_return_quantile_50)
reference_high = reference_price * (1 + matched_stock_return_quantile_90)
```

另算首次可交易价格起算的结果，区分事件反应和可取得收益；无法取得成交约束时`execution_status='unverified'`，不称盈利回测。统计不调用LLM；提取事件强度需有原文片段并保留核对状态。

历史行业来源质量分层：供应商带有效期记录/当时保存快照可用于严格分类匹配；原公告经营描述可作业务相似参考，但不能假称东方财富当时行业成分；只有今日分类则显示历史分类未核实。免费来源无法补齐时保留缺口，不能以今日成员替代来凑够10事件/5公司。多事件同时出现时报告混杂和各自传导条件，不把同一股价变化分别全归因给每个事件。
- [x] **Step 4: 测试通过，增加源字段真实夹具。** 同一案例改变市场状态/公告前涨幅应改变匹配层与入选集；未来数据加入不能改变过去结果。
- [x] **Step 5: 自审并记录。** 不用合成测试样本充当产品案例；产品演示数据需demo标识，实际无样本显示不足；不提交。

### Task 3: 资料任务、不可变快照、API及缓存

**Files:**
- Create: `src/services/a_share_integrated_service.py`
- Modify: `src/services/a_share_service.py`（构造及门面方法）
- Modify: `src/services/a_share_market_service.py`（任务分发，不改变原handler语义）
- Modify: `src/repositories/a_share_repository.py`（精确键及分批历史检索）
- Modify: `api/v1/endpoints/a_share_market.py`
- Test: `tests/test_a_share_integrated_service.py`
- Test: `tests/test_a_share_integrated_api.py`

**Interfaces:**
- Consumes: Task1来源、Task2匹配、现有仓储/MarketJobs/AssistantSettings以及价格上下文。
- Produces: `IntegratedResearchService(assistant).get(code)`、`.prepare(code, peer_offset=0)`、`.generate(code, force=False)`、`.handle_task(task)`、`.validation(code)`、`.freeze(code, facts)`、`.bundle(data_hash)`。
- API: `GET /market/stocks/{code}/integrated-research`只读快照/状态；`POST /market/stocks/{code}/research-data?peer_offset=0`分批准备资料；`POST /market/stocks/{code}/integrated-research?force=false`显式生成；`GET /market/stocks/{code}/research-validation`读取成熟实绩。均沿用`/api/v1/a-share`与当前认证。
- HTTP成功返回任务状态、ID、资料截止/哈希、快照、缺失与耗用；未满足生成前提返回可操作的准备状态，不悄悄启动收费调用。

- [x] **Step 1: 用真实SQLite夹具写服务/API反例。**

```python
def test_get_does_not_fetch_or_call_model(service, provider, completion):
    result = service.get('000807')
    assert result['code'] == '000807'
    provider.assert_not_called()
    completion.assert_not_called()

def test_restatement_creates_new_bundle_not_overwriting_old(service, old_bundle, restated_facts):
    new_bundle = service.freeze('000807', restated_facts)
    assert new_bundle['data_hash'] != old_bundle['data_hash']
    assert service.bundle(old_bundle['data_hash']) == old_bundle
```

覆盖demo不联网、重复POST去重、任务失败可重试、暂停恢复、peer_offset范围、当前成员仅作抓取候选、20公司批次上限、源切换使缓存过期、未知股票404、未授权不能绕过、旧任务迟到不覆盖、新价格锚点无AI自动调用。
- [x] **Step 2: 跑失败。** `.venv/bin/python -m pytest tests/test_a_share_integrated_service.py tests/test_a_share_integrated_api.py -q`。
- [x] **Step 3: 实现资料队列与冻结流程。** 日志种类使用短版本化名称（不超当前kind列长度），如`research_fact`、`research_bundle`、`event_case`、`integrated_report`。状态指针和任务claim更新沿用现有原子约束；生成资料哈希使用完整相关来源/版本/核对状态及历史绑定，不能只hash价格。

```python
identity = sha256(canonical_json({
    'code': code, 'profile': source_signature(settings), 'cutoff': cutoff,
    'history_binding': binding, 'facts': facts, 'cases': matched_cases,
    'engine_version': ENGINE_VERSION,
}).encode()).hexdigest()
```

准备阶段只抓资料；历史同业任务按offset有界分批，不锁住行情工作线程。模型生成沿用后台线程或专用显式任务，不在请求线程长等。运行中切模式/改来源使任务失效，旧记录保留。当前股财务/公告与同业案例库分别展示进度，案例补录不可冒充已有全市场库。

冻结流程必须真正接入Task1的财务、三表、公告正文和相关新闻，并调用Task2形成事件/案例结果；不能只新增卡片或把旧新闻原样展示就算接入。资料清单记录“进入价格基线 / 进入综合情景 / 仅风险约束 / 缺失或未采用及原因”。当天只有日期的新闻、未核对实体和未来记录不进入事实输入；此前日期新闻以日末为保守界限，仅作实际观察时间之后的当前背景，保留日期精度，不作历史归因（最终审查裁定）；查询截止与价格最后完整日分别保存，避免盘中新闻被错误回填到前一天模型。
- [x] **Step 4: 测试通过并回归任务/仓储/旧API。** 运行新增测试加`test_a_share_market_jobs.py`、`test_a_share_storage.py`、`test_a_share_api.py`；确认只读GET/新POST身份错误码和旧端点一致。
- [x] **Step 5: 自审并记录。** 断点恢复、并发锁序和最后写入条件逐项核对，不提交。

### Task 4: 多专家与综合策略输出

**Files:**
- Modify: `src/services/a_share_research.py`（复用completion/计费，新增综合研究入口）
- Create: `src/services/a_share_integrated_prediction.py`
- Modify: `src/schemas/a_share_integrated.py`
- Modify: `src/services/a_share_integrated_service.py`（生成调度）
- Test: `tests/test_a_share_integrated_prediction.py`
- Modify/Test: `tests/test_a_share_research.py`

**Interfaces:**
- Consumes: 冻结ResearchBundle、价格基线及各期限案例参考；用户当前模型配置。
- Produces: `ResearchEngine.run_integrated(bundle, settings, day, manual=True) -> dict`；最多市场/行业、业绩/估值、事件/案例、价格/流动性、风险复核、综合经理6角色。
- Produces: `validate_integrated_prediction(value, bundle, sent_ids, min_reward_risk) -> dict`；5/20/60日情景与条件计划、拒收计数、缺失理由及未校准标识。
- Produces: `strategy_candidates(bundle, min_reward_risk) -> list[dict]`；根据已经完成的日线、MA120/250/已完成周线、市场/行业、事件及交易状态返回趋势回踩、区间回归、事件跟踪或观察候选，包含适用/排除理由，不以专家投票选择策略。

- [x] **Step 1: 写有意义的模型边界测试。**

```python
def test_fact_change_is_sent_to_relevant_expert(engine, bundle, changed_earnings, settings):
    engine.run_integrated(bundle, settings, '2026-10-16')
    before = engine.completion.call_args_list.copy()
    engine.run_integrated(changed_earnings, settings, '2026-10-16')
    after = engine.completion.call_args_list[len(before):]
    assert before != after
    assert 'PARENTNETPROFIT' in str(after)

def test_manager_cannot_publish_unreferenced_prices(bundle):
    result = validate_integrated_prediction({'forecasts': [{'horizon_sessions': 20,
        'scenario': 'base', 'low': 31., 'high': 35., 'sources': ['UNKNOWN']} ]},
        bundle, {'P1', 'F1'}, 2.)
    assert result['forecasts'] == []
    assert result['rejected'] > 0
```

覆盖未知引用、未发送事实、裁剪、缺财务/案例跳过角色、经理收到全部有效角色结论、任意胜率、NaN/反向价位/不足盈亏比、没有数值参考只观察、同模型投票非概率、单角色超时部分保留、手动越过自动预算且一次尝试一次记账、缓存重复不收费。

策略专项测试：长期下行时不得把短线反弹写成长线反转；区间策略遇已确认破位必须失效；事件证据撤销后事件策略降为观察；价位太密、可取得利润不足以覆盖成本/风险时不发布可操作计划。只改变新闻/财务的对照输入，应证明相关专家确实收到变化，且采纳/拒绝的理由进入最终报告；不要求每条利好必然上调目标价。
- [x] **Step 2: 跑失败。** `.venv/bin/python -m pytest tests/test_a_share_integrated_prediction.py tests/test_a_share_research.py -q`。
- [x] **Step 3: 实现角色资料路由和结构校验。** 在旧`run()`之外新增入口，复用配置参数和单次completion。不改旧5/10/20情景契约；综合结构单独支持5/20/60。按角色相关事实分发，固定事实ID，正文截断标记；部署模型声明上下文时据其预算，否则用有界保守输入预算，不按模型名猜容量。经理必须收到有效结论、反证及缺失，不能再仅保留90字节首条观点。

```python
context = {'bundle_id': bundle['data_hash'], 'cutoff': bundle['cutoff'],
    'evidence': relevant_facts, 'price_references': numeric_references,
    'prior_roles': accepted_roles, 'missing': bundle['missing']}
# 模型不得修改账户/股数，参考来源必须实际送入。
```

每条综合价位列`basis_ids`与数值推导说明；优先依据价格基线/合格案例范围/可验证估值约束。代码检查依据引用及数值关系，标明不能验证文字推导的经济正确性；未知依据不收。计划必须明确期限、条件与失效，二次买入是条件参考、不是自动加仓指令。风险复核在经理之前；失败角色显示状态，不能伪称全角色完成。

策略输出的固定字段包括：`strategy_kind`、`horizon_sessions`、`status`、`entry_low/high`、`second_entry`、`stop_reference`、`targets`、`conditions`、`invalidation`、`valid_until`、`reward_risk`、`basis_ids`、`rejection_reasons`；`second_entry`需含价位或区间、触发条件与失效条件，不能只写“择机加仓”。缺数值依据时字段为null且说明原因。先由代码生成符合条件的策略候选，专家研究事件/经营传导、反证与冲突，再由经理选择/否决并解释，最后再次规则校验。

完整调用分为“必要事件抽取”和“最多6个专家”两段，合计预先展示，分别记账。准备资料和只读GET不进行AI抽取。首版每次显式研究最多2次有界批量抽取，不能为20家同业暗中逐条运行模型；用尽仍未抽取的事件标为待结构化，不虚构成已研究。手动总调用次数继续不设每日上限；单次工作流有界与每日限额不同。
- [x] **Step 4: 测试通过，跑现有价格情景/规则测试。** 原规则的股数、持仓确认、风险过滤继续不受AI更改；新引擎状态/拒收与引用显示一致。
- [x] **Step 5: 自审并记录。** 专家角色≠独立确认，资料格式校验≠预测准确率，不提交。

### Task 5: 同页综合研究、图表图层与状态

**Files:**
- Modify: `apps/dsa-web/src/types/aShareMarket.ts`
- Modify: `apps/dsa-web/src/api/aShareMarket.ts`
- Create: `apps/dsa-web/src/components/a-share/useIntegratedResearch.ts`
- Create: `apps/dsa-web/src/components/a-share/IntegratedResearchPanel.tsx`
- Modify: `apps/dsa-web/src/components/a-share/StockDetail.tsx`
- Modify: `apps/dsa-web/src/components/a-share/PriceChart.tsx`
- Modify: `apps/dsa-web/src/components/a-share/priceChartData.ts`
- Modify: `apps/dsa-web/src/pages/ASharePage.css`
- Create/Test: `apps/dsa-web/src/components/a-share/__tests__/IntegratedResearch.test.tsx`
- Modify/Test: `apps/dsa-web/src/components/a-share/__tests__/PriceChart.test.tsx`
- Create/Test: `apps/dsa-web/src/api/__tests__/aShareIntegrated.test.ts`

**Interfaces:**
- Consumes: Task3接口与Task4结果；现有HistoryPage、图表levels与价格绑定。
- Produces: `useIntegratedResearch(code)`的`result/loading/error/prepare/generate/retry`；`IntegratedResearchPanel`显示覆盖、进度、专家、案例、期限策略与更新按钮；图表新增独立`integrated`图层参数，旧`forecast/levels`保留。

- [x] **Step 1: 写页面、请求和图层反例。**

```tsx
it('does not generate when opened or when horizon changes', async () => {
  render(<IntegratedResearchPanel {...readyProps} />);
  fireEvent.change(screen.getByLabelText('综合研究期限'), {target: {value: '60'}});
  expect(readyProps.onGenerate).not.toHaveBeenCalled();
});

it('does not map a stale adjustment generation', () => {
  expect(integratedChartLayer(report, raw, {...history, fetched_at: 'new'}, 'qfq', '000807', 20)).toBeUndefined();
});
```

另覆盖切股请求取消及迟到结果、2026-10-16资料到达使旧报告过期、资料不足按钮、部分角色失败、样本少不画假扇形、源链接仅HTTP(S)、轮询停止、买入/二次/止损/目标虚线、原价格基线和首页策略线不丢、K线仍在报价下方。
- [x] **Step 2: 跑新增测试确认失败。** 在Web目录执行 `npm run test -- --run src/components/a-share/__tests__/IntegratedResearch.test.tsx src/api/__tests__/aShareIntegrated.test.ts`。
- [x] **Step 3: 实现渐进显示。** 图下先综合结论及5/20/60期限，再覆盖/专家/案例详情。准备资料和生成模型两个动作分开，展示预计/实际调用；旧结果保留并显示截止日/过期。图例区分蓝色价格基线和综合情景，后者不写80%置信区间；绑定失配解释未叠加原因。

```ts
type IntegratedStatus = 'missing' | 'preparing' | 'ready' | 'running' | 'partial' | 'failed' | 'stale';
// GET读状态；只有显式按钮会POST。
```

全任务以服务schema为准对齐TS类型，数字格式对null处理，图中仅绘有限正价。不覆盖旧面板和开关，不将板块重新放到个股下方。

同页固定展示：5/20/60交易日期限、偏弱/基准/偏强情景、理想买入、二次买入、止损、分段盈利目标、成立/失效条件、采用策略与专家分歧。来源详情能核对市场/行业、业绩、新闻事件、资金/流动性、技术价格各维度到底是否取得及是否采用。未来图层只表示已生成期限节点之间的情景连接，不补造真实未来蜡烛或宣称逐日走势已知。当前临时行情仍单独显示，不进入完整日线统计。

兼容验收逐项保留：全部股票/规则候选/自选、搜索及行业/概念交集筛选、独立板块页与成分股跳转、历史期间与指标勾选、行情5分钟检查和手动刷新、首页历史策略同步及虚线、现有筹码/新闻展示、旧AI研究与价位、持仓/风控/原回测入口、已有模型配置及手动不限次数。图下出现综合面板不能把K线再次推到页面下部。
- [x] **Step 4: 定向测试/变更文件lint/构建。** 随后运行全Web测试，基线已有的全局lint问题单列，不能宣称全局全通过。
- [x] **Step 5: 真实浏览器验收并记录。** 免费资料准备、研究进度、云铝切另一只股票、图层/期限、行业页/成员导航和现有持仓/报告入口；截图存任务mirror的outputs，不入repo；不提交。

### Task 6: 前瞻归档、验证、文档与端到端跑通

**Files:**
- Create: `src/services/a_share_integrated_validation.py`
- Create/Test: `tests/test_a_share_integrated_validation.py`
- Modify: `src/services/a_share_integrated_service.py`
- Modify: `docs/a-share-assistant.md`
- Modify: `docs/a-share-strategy-review.md`
- Modify: `docs/CHANGELOG.md`（Unreleased扁平条目）
- Modify: `.env.example`（已有模型部署参数/研究输入预算说明，不写用户密钥）
- Create: `scripts/integrated-research-smoke.py`

**Interfaces:**
- Consumes: 不可变综合快照、同源完整日线、交易日历；生成日与价格绑定。
- Produces: `evaluate_integrated_snapshots(records, bars, calendar, cutoff) -> dict`；按5/20/60期限列成熟样本、价格误差、方向、情景覆盖及最大不利变动，前瞻归档与重建资料分别统计。
- Produces: `compare_forecast_snapshots(records, bars, calendar, cutoff) -> dict`；只在相同股票/发行时点/期限/价格版本且实际有对照结果的交集比较“不变价格 / 原价格模型 / 加财务 / 加事件 / 综合”。缺少实际变体记录时返回`unavailable`及原因，不以删除最终报告某段文字冒充消融实验。
- Produces: `scripts/integrated-research-smoke.py --code 000807 --base-url <url>`只读检查；`--prepare`显式准备；`--generate`显式跑一次模型研究并有界等待。工具读取当前配置，不输出密钥或改账户。

- [x] **Step 1: 写成熟度和盈利误称反例。**

```python
def test_not_matured_forecast_is_not_accuracy_sample(snapshot, bars, calendar):
    result = evaluate_integrated_snapshots([snapshot], bars, calendar, snapshot['anchor_date'])
    assert result['horizons']['20']['matured'] == 0
    assert result['horizons']['20']['mean_absolute_error'] is None
    assert result['portfolio_return'] is None
```

另外覆盖预测生成之后才成熟的终点、生成晚于历史截止的回填报告、口径不匹配、缺交易日、临时K线排除、非独立重叠预测单列、没有仓位/成交约束不能称策略回测、旧报告不因新预测被覆盖。

对照专项测试：两个模型覆盖股票不同不能直接比较总体准确率；同一测试窗口不能用于选权重；缺少财务/事件变体不能伪造增量结果；样本量、缺失率与时间划分随指标一起显示。本次默认比较已实际生成的“不变价格 / 原价格模型 / 综合情景”；单加财务、单加事件的分项在没有真实实验快照时显示未验证，接收真实快照后才可评价。一次完整研究不暗中重复四轮专家，也不以仅有记录比较器声称已做完所有模型消融。
- [x] **Step 2: 跑失败。** `.venv/bin/python -m pytest tests/test_a_share_integrated_validation.py -q`。
- [x] **Step 3: 实现按期限评价与文档。** 评价预测而非虚构组合收益；归档记录数据时点质量，未来变化只追加。文档说明哪些资料影响了综合情景、哪些仍没进蓝色回归、案例门槛、真实费用、缺失、重试、回退，以及Qlib未安装/未接入、本次只提供未来可复用的数据结构。已有原英文文档不改时交付说明原因：本次为本地A股扩展中文专题，未改变上游通用英语入口。

收益验证分两层：本次提供真实预测归档及同条件对照，不把价格命中率称为盈利率；已有回测入口保留。新的综合策略组合收益，只有在取得可成交价格/停牌/涨跌停状态、持有与T+1约束、有效日期的手续费/税费/滑点和历史股票范围后才可输出。当前不能取得这些资料时必须显示“综合策略收益尚未验证”，不能只用收盘价模拟后称已完成含成本回测。Qlib及新组合执行/回测引擎属于另行说明的后续范围。
- [x] **Step 4: 完整验证。** 编译改动Python；新增确定性测试；全部`tests/test_a_share_*.py`与相关筹码/上下文回归；Web全测试、lint、构建。完成后启动当前项目、读真实API、准备单股资料，最后执行一次显式完整模型研究（最多6角色尝试，不自动循环），确认引用、来源、状态、生成价位/无价位理由与图层绑定。若模型源报错则保存类型与状态、修复自身问题；外部账户无权限等限制如实报告，不能用mock称实测通过。
- [x] **Step 5: 新鲜审查和修复。** 检查本计划Review Focus全部路径，必要时使用requesting-code-review技能的独立审查，修复后只重跑受影响检查及必要集成。证据保存到mirror，逐项列实际完成/真实缺口，不能以“已接入”替代验证。

## 计划自审

设计覆盖：来源/新闻/时间/版本→任务1、3；事件抽取/案例匹配及收益→任务2；多专家/多策略/分期限价位→任务4；同页图表与旧功能→任务5；归档及真实对照验证/成本边界/联调→任务6。Qlib实际训练、完整一致预期和全市场历史行业库不在本次实施承诺内，资料不足显式显示，不能降级成假数据。

接口名和期限一致：旧接口5/10/20继续保留；综合接口5/20/60为独立追加。所有Task消费的Task间函数均在前述Interfaces中定义。完成时更新复选框与验收证据；本计划不执行任何git提交。

## 需求覆盖与本次边界

| 此前提出的需求 | 本次安排及验收位置 |
| --- | --- |
| 免费起步、以后切换数据档位，优先统一来源 | 任务1、3；东方财富行情/财务优先，巨潮原公告；Tushare逐能力核验，非按档位名称假定已授权 |
| 新闻、政策、业绩、现金流及估值共同判断 | 任务1获取并核对，任务3冻结，任务4实际发送给相应角色；缺失及未采用均可见 |
| 多专家、外部专家意见与反方复核 | 任务1外部观点具真实来源；任务4六角色共享资料、风险复核及综合经理，不冒充独立统计确认 |
| 更长周期综合判断与多策略 | 任务4沿用MA120/250和已完成周线，区分趋势、区间、事件及观察；按市场适用性选择 |
| 同类事件的行业、强度、市场、估值及前期涨幅 | 任务2分层匹配，1/5/20/60日收益、市场/行业超额及不利变动；历史条件未核实则不凑数 |
| 未来预测及理想/二次买入、止损、盈利目标 | 任务4输出5/20/60日情景和有条件价位；任务5同图虚线与详情，没依据留空 |
| 首页报告与交易助手融合，保留原有功能 | 任务5列出逐项回归；K线在报价后，板块独立，旧报告/自选/账户风控及回测入口保留 |
| 行情自动检查与手动更新 | 任务3、5保留既有5分钟检查及刷新按钮；临时K线不进入已完成日线训练 |
| 手动模型不限次数，费用透明 | 任务4分开显示抽取与专家调用，缓存不重付费；GET/切图/行情刷新不触发模型 |
| 验证是否优于纯技术预测、真实跑通 | 任务6存前瞻实绩和同条件对照；真实数据、一次完整模型及浏览器联调；不宣称已验证盈利 |
| Qlib优势及未来接入 | 设计第10节有说明，本次资料契约可复用；实际安装、训练、概率融合校准及组合回测为后续范围 |

以下不是“已补齐”的承诺：付费数据库的完整一致预期、全部宏观/商品时序、全市场跨年行业成分、任何股票都足量的历史事件、已训练的多因素数值融合模型、已经证明高收益的综合策略。当前每个缺口需显式展示；补齐这些资料/模型属于后续有验收证据的工作，不能用AI猜测代替。

## 执行方式与审阅

用户已于2026-10-16确认“先实现我们的计划之后再实现qlib”。按本计划推荐的方式，在当前会话由主实现者连续执行，完成后独立审查。Qlib不属于本轮，后续再接入；不再重复请求相同实施授权。

## 最终验收记录（2026-10-17）

任务1–6已实施，并经一次独立审查及重要问题反例修复。最终v4真实000807：六角色均完成、9情景、1个20日观察策略、0拒收；5/60日模型未提供交易策略，页面显式说明。432财务、2130估值、564公告/6正文、1条有公司标题的新闻摘要。同业40项任务完成（含重复准备批次，不等于40家不同公司）。当前事件/历史行业版本不足，严格事件数值仍不可用。

最终相关后端448通过，Web1432通过/2跳过，定向最后任务20通过，变更文件lint与构建通过。全仓此前8269通过/41失败；同组配置/API/进程测试隔离288项通过，仍不宣称全仓门禁全部通过。全局Web lint既有1错误/1警告单列。模型验收共四轮各6角色，24次实际调用、AI事件抽取0次，不再付费重复。

详细验收、缺口、失败清单和截图保存在ChatGPT项目mirror的outputs目录，原项目.superpowers实施台账保留。新闻旁栏误匹配、旧报告与新资料锚点混同、模型省略策略的静默展示已在实测中复现并修复。新综合预测未有成熟样本，未证明准确率或盈利提升。Qlib仍为下一阶段，不安装、不训练；未提交或推送。
