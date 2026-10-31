# Value Investing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有A股详情中实现跨行业、6个月到3年持有视角的价值研究，以可追溯财报、适配估值、错误定价假说及安全边际帮助判断。

**Architecture:** 复用研究资料和持久任务，增加独立价值事实/快照、确定性估值器和可选一次AI草案调用。通过版本化假设、同行资格与风险门槛输出价值报告，在原个股工作区展示，不改变短期模型。

**Tech Stack:** Python / Pydantic / FastAPI / SQLAlchemy journal / React / TypeScript / Vitest；不新增运行依赖。

**Spec:** `docs/superpowers/specs/2026-10-30-value-investing-design.md`

## Global Constraints

- 持有期为6、12、24、36个自然月；显式估值预测期5年，续存价值必须单列。
- 免费优先，不自动升级数据权限；无AI也能录入假设和确定性计算。
- 普通页面读取不启动网络抓取或模型调用；一次价值研究最多一次模型请求，失败不自动重试。
- 现有短期六角色与5/20/60交易日预测保持兼容，价值估值不受其历史波动上下界裁剪。
- 金额用人民币元、股数用股、比率用小数；NaN/Infinity/布尔数值一律拒绝。
- 同业正式样本至少5家才发布分位；初次最多准备20个候选公司的资料，offset上限500。
- DCF/DDM折现率与终值增长至少差1个百分点；不同方法基准值差异超过主方法值30%触发争议复核。
- 安全边际分母为已确认主方法保守价值；未设置用户要求的折价时不生成条件安全价。
- 保留现有全部功能、报价/K线优先布局和配置/数据；不提交或推送，除非用户另行明确授权。
- 新增中文模块文档及扁平CHANGELOG条目；不添加README推广、联系合作或产品预览。

## Review Focus

1. 财报累计/单季、合并/归母、利息分类或元/万元混淆：有来源合同才连接；矛盾/缺失阻止依赖它的估值（Task 1、2）。
2. 增发/回购、少数权益、非经营现金与股息造成重复计算：固定资本适用门槛与桥接必须检查，未分配FCF不能消失（Task 3、4）。
3. 银行、亏损科技、周期高点被套用通用PE/现金流：使用经济模型适配，缺方法则研究而非数值低估（Task 2、3）。
4. 配置/股票/假设版本切换或后台崩溃：旧结果留作历史，禁止串股、覆盖新版或重复付费（Task 5、6、7）。
5. AI引用未送达证据、事件重复传导、价格已提前反映被当成超预期：限定证据ID与驱动变更，保留反方与零样本（Task 4、6）。

---

## 执行约定

推荐本会话直接执行，便于保持财务口径、API和前端一致；设计检查及最终独立审查使用新审阅者。仓库禁止未经确认提交，所以各任务结束以测试和差异审阅作为检查点，省略技能示例中的自动commit。首先在当前可写仓库执行，不另建重复运行环境；需隔离时先按worktree技能检查附件。

以下命令中的 `python` 指已配置运行环境的解释器，工作目录为本仓库。实施时检查可用路径，不把机器路径写进产品配置。计划步骤尚未执行。

### Task 1: 严格价值事实与独立版本协议

**Files:** Create `src/schemas/a_share_value.py`, `data_provider/a_share_value_facts.py`; Modify `data_provider/a_share_fundamentals.py`; Test `tests/test_a_share_value_facts.py`。

**Interfaces:**
- `ValueFact`：`fact_id,code,metric,value,unit,currency,report_period,period_start,period_end,period_basis,scope,attribution,source,raw_field,published_at,revised_at,observed_at,available_at,vintage_quality,content_hash,conflicts`；严格schema，值有限。
- 枚举 `period_basis=instant|ytd|quarter|annual`、`scope=consolidated|parent|unknown`、`attribution=all_claims|parent_common|minority|unknown`；不明口径可留作研究，不能自动进入估值。
- `normalize_value_statements(code:str, rows:list[dict], source:str, observed_at:str)->list[ValueFact]`；逐来源字段合同。
- `ResearchSources.financials()` 保留 `facts/status/errors/limitations`，追加 `value_facts`；同一原响应分派两种适配器，不新增重复抓取。
- `ValueSnapshot / ValueAssumptions / ValueReport`，版本 `value-research-v1`。Snapshot含资料和资格绑定；Assumptions含 `revision,snapshot_id,confirmed,primary_method,cases,margin_required,peer_confirmations,driver_changes,holding_cases`；Report分离 `valuation_state,valuation_cases,comparison,quality,theses,risks,missing,holding_cases,stale_reasons`。

- [ ] Step 1: 编写参数化失败测试：现金0保留、None不补0、单位转换一次；拒绝NaN/Inf/布尔；错误证券不入事实；日期可用性=max(观察/公布/修订)，未来资料排除；原有financial事实结果不变。
- [ ] Step 2: `python -m pytest tests/test_a_share_value_facts.py -q`，确认新接口缺失导致失败。
- [ ] Step 3: 定义严格schema与按接口的指标/单位/期间合同，实施双适配；从官方实现与真实匿名字段结构构造夹具，覆盖免费报表及Tushare版本。
- [ ] Step 4: 运行该测试及 `tests/test_a_share_research_sources.py`，结果PASS；单独审查每个含糊字段是否仅保留而没有估值资格。

### Task 2: 财务连接、正常化与同行

**Files:** Create `src/services/a_share_value_financials.py`, `src/services/a_share_value_peers.py`; Test `tests/test_a_share_value_financials.py`, `tests/test_a_share_value_peers.py`。

**Interfaces:**
- `build_financial_view(facts:list[ValueFact],cutoff:str)->dict`：年度序列最多10年、最新期、严格TTM、冲突和覆盖；输出每个派生值的 `fact_ids/formula/period/scope/unit`。
- `select_economic_model(industry:dict|None,business_evidence:list[dict],override:dict|None)->dict`：模型枚举 `operating|cyclical|growth|early_stage|bank|life_insurance|nonlife_insurance|securities|asset_management|leasing|utility|asset_holding|unresolved`；返回依据与允许/禁用方法，映射版本固定 `eastmoney-industry`。
- `build_peer_comparison(target:dict,candidates:list[dict],confirmations:list[dict])->dict`：候选与正式同行分离；每指标独立可比样本、排除理由、N/中位/Q1/Q3/分位。

- [ ] Step 1: 失败测试固定TTM：年度120、本期前三季100、上年前三季80→140；缺上年同期→missing；资产时点不相加；单季与累计冲突→blocked；合并CFO/归母利润不能标严格现金转化率。
- [ ] Step 2: 同行失败测试：同概念异行业、同行亏损、负净资产、期间不齐、只有行业没有主营依据均不入相应正式样本；4家不给分位，5家值10/12/14/16/18、target14→N5/中位14/分位0.6。
- [ ] Step 3: 实现带来源的连接、规模调整正常化视图与经济模型映射；周期不足5年完整年报则“周期覆盖不足”，不把短均值叫完整周期。已知结构变化分段，未知不假定稳定。遍历实际行业目录每项得到明确映射或unresolved；券商/资管/租赁各有清单，基金/REIT不估作普通A股。
- [ ] Step 4: `python -m pytest tests/test_a_share_value_financials.py tests/test_a_share_value_peers.py -q`，全部PASS。确认排序不能把未确认同行悄悄纳入。

### Task 3: 五种估值器、敏感性与安全边际

**Files:** Create `src/services/a_share_value_valuation.py`; Test `tests/test_a_share_value_valuation.py`。

**Interfaces:**
- `project_operating_case(case:dict,financial_view:dict)->dict`：使用R0/NWC0及5年营收增长、EBIT率、折旧/营收、capex/营收、NWC/营收、税率生成逐年FCFF，另有稳定期第6年完整输入计算terminal FCF；FCFE另需税后利息、净借款与普通股归属调节。缺项不填0，直接FCF数列不可跳过经营桥接。
- `evaluate_method(method:str,case:dict,financial_view:dict,eligibility:dict)->dict`：输出value_total/value_per_share、现金流明细、terminal_share、桥接、缺口/理由；严格执行设计公式。FCFE非经营资产必须选择included_in_flows或separate，二者不可混用。
- `evaluate_value(assumptions:ValueAssumptions,snapshot:ValueSnapshot)->ValueReport`：主方法三情景、交叉争议、敏感性与状态。
- `compare_price(conservative_value:float|None,quote:dict,margin_required:float|None,eligibility:dict)->dict`：无模型、无外部抓取。

- [ ] Step 1: 手算测试：营收100、growth0、EBIT率20%、税25%、DA5、capex10、NWC不变→每年FCFF10；零利息/借款/少数现金分配均有明示依据时FCFE10。ke10%、g0%、5年、10股→股权100、每股10；FCFF同样EV100、独立非经营资产20、债30、其他索取5、少数5→普通股80/10=8；缺少桥接不能把该项填0。
- [ ] Step 2: RIM B0=100、ke10%、E每年10、分红10、omega0→价值100；DDM每年1、ke10%、g0→每股10；NAV资产150−债40−税费10→100，再按10股→10。
- [ ] Step 3: 门槛失败测试：g>=r、差不足1个百分点、非正股数、未来现金融资/回购的资本桥接未知、银行走FCFF、亏损科技PE、非正价值、安全边际参数越界；均精确给字段原因，不静默夹紧。FCFE非经营资产漏计/重复计、只填FCF或提高增长却缺投资输入均不可绕过。第5年FCF10而稳定期第6年20、g0、r10%时续存价值200，不得误算100。
- [ ] Step 4: 实现纯计算器与确定性验证，保留完整明细。压力测试将经营现金流、资本开支、r/g与无额外收益稀释作为显式冲击，不自动赋概率。
- [ ] Step 5: 价格60、保守值80→MOS0.25、潜在涨幅1/3；要求MOS0.30→条件价56。草案/重大风险/错误股本/过期报价禁止条件价；主方法100、交叉140→disputed；保留原值不平均。
- [ ] Step 6: `python -m pytest tests/test_a_share_value_valuation.py -q`，PASS；人工复算上述样例。

### Task 4: 事件经营传导与6–36月兑现情景

**Files:** Create `src/services/a_share_value_drivers.py`, `src/services/a_share_value_holding.py`; Test `tests/test_a_share_value_drivers.py`, `tests/test_a_share_value_holding.py`。

**Interfaces:**
- `apply_driver_changes(snapshot:ValueSnapshot,assumptions:ValueAssumptions)->dict`：只应用被引用的字段级变更，返回before/after/delta/传导依据；不改变原始事实。
- `cashflow_schedule(case:dict,start_date:str)->list[dict]`：默认估值日起逐年周年末，明确分红日替代；所有日期按ACT/365.25折现，V0与Vh共享，不能暗改月末均摊。
- `evaluate_holding(case:dict,valuation:dict,start_date:str,months:int)->dict`：只接受6/12/24/36，自然月末日期规则，返回终点剩余价值、兑现因子、股息、毛/净回报、费用口径或缺口。
- 引用已有event_family、历史可比案例和市场上下文，保留0样本、样本偏差及非历史成员说明。

- [ ] Step 1: 事件重复、基准已经纳入、无单位、引用不存在、未来事件、新闻同比冒充超预期的测试均不能产生数值增量；有正式成本变化可改变相应现金流且保留反事实。
- [ ] Step 2: DDM按同一日期排程手算，V0=已付现金流现值+终点剩余价值现值的拆分恒等成立；明确分红日改变时两端同时重算，终点前已付股息不能仍在剩余价值中；k=P/V，初始P60/V80→k0.75，无纠偏时Vh100→Ph75，充分纠偏k1→Ph100。未填k不补线性收敛。2026-10-30加6个月→2027-04-30；月底/闰年遵循自然月合法最后一天。
- [ ] Step 3: FCF缺分配/留存现金勾稽时仍给V0但不提供终点价格；股息再相加两次的反例应失败；NAV缺未来资产/债务滚动同样不足；税费未填只给毛收益。
- [ ] Step 4: 实现事件变更白名单和幂等、V0/Vh共享日期排程、各模型终点适用门槛及自然日年化。
- [ ] Step 5: `python -m pytest tests/test_a_share_value_drivers.py tests/test_a_share_value_holding.py -q`，PASS。

### Task 5: 快照、假设版本、资料与缓存服务/API

**Files:** Create `src/services/a_share_value_service.py`, `api/v1/endpoints/a_share_value.py`; Modify `src/services/a_share_service.py`, `src/services/a_share_integrated_service.py`, `api/v1/endpoints/a_share_market.py`; Test `tests/test_a_share_value_service.py`, `tests/test_a_share_value_api.py`。

**Interfaces:**
- `ValueResearchService(assistant)`；`.get(code)`, `.prepare(code,peer_offset=0,refresh=False)`, `.save_assumptions(code,request)`, `.supplement(code,request)`, `.evaluate(code,request)`, `.generate(code,request)`, `.handle_task(task)`。
- 六个API路径/body/409/422行为严格遵循设计；`a_share_market.py` 只include新router，不在大文件堆业务。supplement限50条、每条引用2000字、HTTP/HTTPS，保存user_attested并创建新snapshot，不能覆盖原事实。
- Assistant拥有 `.value`；共享资料handler在短期freeze失败前先保存完整价值资料；已有research_data结果追加value_facts，不删除旧facts/events。
- journal kind `value_snapshot/value_assumptions/value_report/value_review/value_attempt`；key `profile:code`，snapshot按hash留存；乐观并发锁复用settings锁。

- [ ] Step 1: GET只读测试将provider和模型设置为调用即失败，仍返回缓存/缺口；demo/live不互串；没有K线时value-data仍完成资料快照。
- [ ] Step 2: 版本测试：两窗口expected_revision冲突→409；旧snapshot提交→409；配置/risk/股本/同行变化后旧结果stale，不能出当前条件价；不存在股票404，非法输入422，响应无原始异常/凭据。人工来源完整且核对后可支持标记为人工依据的条件分析；与可信事实冲突仍blocked，不得借此改写身份/风险或伪造历史。
- [ ] Step 3: 实现缓存快照/资料准备与版本API；新的基础估值没有现有B/C基线依赖。最新报价的比较独立确定性刷新，不因每次价格变化重跑AI。
- [ ] Step 4: API测试覆盖六条路径、认证既有边界、手动无模型输入→保存→计算→GET报告；手工补充→新snapshot→旧假设失效；已有路由和响应仍兼容。
- [ ] Step 5: `python -m pytest tests/test_a_share_value_service.py tests/test_a_share_value_api.py tests/test_a_share_integrated_service.py -q`，PASS。

### Task 6: 一次可选AI调用与持久进度

**Files:** Create `src/services/a_share_value_research.py`; Modify `src/services/a_share_value_service.py`, `src/services/a_share_service.py`, `src/services/a_share_research_progress.py`, `src/repositories/a_share_market_repository.py`; Test `tests/test_a_share_value_research.py`, 扩充Task5测试。

**Interfaces:**
- `ValueResearchEngine(repo).run(snapshot:ValueSnapshot,settings,progress:Callable)->dict`，使用现有ResearchEngine模型网关/用量记录；不创建并行API Key配置。
- AI输出 `perspectives,theses,proposed_assumptions,driver_changes,counterevidence,missing`；全部引用实际送达ID，输入预算最多48KB，披露裁剪ID；只按严格schema解析，失败不补造数值。
- `value_research` 独立kind排除在普通市场队列之外，由value的MarketJobs消费；Assistant start/stop与profile切换同时管理。handler捕获模型失败并留存终态，不走MarketJobs自动重试；调用前持久写 `value_attempt`，恢复时已尝试但未完成则中断。新增 `MarketRepository.enqueue_value_research(profile,fingerprint,payload,force)->dict` 在事务中复用运行中任务并分配代次，依现有profile/key唯一约束去重；fingerprint含code/snapshot/model/假设revision，force也不能绕过运行中任务。

- [ ] Step 1: 伪造引用、网页注入指令、未发送ID、错误公司、缺资本桥接、仅增长没投资、无法证实超预期等输入不能成为正式假设；引擎算术覆盖AI提供的总价。
- [ ] Step 2: 一次调用测试：同任务重放/崩溃恢复/跨进程并发重复POST均不增加模型请求；运行中force仍复用，上一代终态后force新任务才允许再次请求。源配置改变后旧任务不能发布成最新报告；手动不受每日次数配额但仍记录用量。
- [ ] Step 3: 实现多视角结构化提示与草案、进度各阶段/耗时、model_attempt_started收据和单次调用；已有短期6角色不改。
- [ ] Step 4: `python -m pytest tests/test_a_share_value_research.py tests/test_a_share_value_service.py tests/test_a_share_research_progress.py -q`，PASS；检查完成/依据不足/失败/中断都有不同终态。

### Task 7: 同页价值报告、假设编辑与统一入口

**Files:** Create `apps/dsa-web/src/types/aShareValue.ts`, `apps/dsa-web/src/components/a-share/useValueResearch.ts`, `ValueInvestingPanel.tsx`, `ValueAssumptionEditor.tsx`, `valueChartData.ts`（后三个均在同一components/a-share目录）；Modify `apps/dsa-web/src/api/aShareMarket.ts`, `StockDetail.tsx`, `ResearchWorkspaceToolbar.tsx`, `priceChartData.ts`, `apps/dsa-web/src/types/aShareMarket.ts`, `apps/dsa-web/src/pages/ASharePage.css`；Test `apps/dsa-web/src/components/a-share/__tests__/ValueInvesting.test.tsx`, `ValueChartData.test.ts`, `apps/dsa-web/src/api/__tests__/aShareValue.test.ts`。

**Interfaces:**
- APIclient追加 `getValue`, `prepareValue`, `generateValue`, `saveValueAssumptions`, `supplementValue`, `evaluateValue`；统一code编码、signal传递。
- `useValueResearch(code:string)` 返回result/loading/busy/error及prepare/generate/save/evaluate动作；运行中3秒轮询，空闲30秒读取缓存，隐藏页面暂停、卸载取消。
- `ValueInvestingPanel({code,state,onRequestResearch})` 位于K线后；`ValueAssumptionEditor`负责受控表单/字段错误/未保存提示，不直接调用模型。
- 工具条新增受控 `scope:'trading'|'value'|'both'` 与value进度，默认trading；单生成按钮按选中范围启动；双方报告、进度、失败独立汇总，value-only不请求短期生成。
- `valueChartLevels(result,history,enabled)->{levels,reason}`；ChartPriceLevel.source追加`value`，使用现有价格变换验证并绑定股本/报告状态。默认关闭长期层。

- [ ] Step 1: 前端失败测试：已有K线顺序/短期按钮兼容；价值单选只发一次价值请求；both最多6+1；编辑保存/重算0次模型调用；有字段错误展示中文原因。
- [ ] Step 2: 切股A→B后A慢响应不能出现；旧假设revision不覆盖新数据；返回409提示重载而非自动force重试；缺数据展示具体字段/渠道，不是“未提供”。
- [ ] Step 3: 图层测试：草案/争议/过期/股本不匹配/价格基准不明都不绘价值线；合法raw/qfq换算才有线，标估值日与“价值参考”；原短期事件路径不变。
- [ ] Step 4: 实现组件与API类型、范围统一入口、表格/财务趋势/假设/压力/反证/6–36月情景；安全边际与潜在涨幅不同标签。小屏横向表格、语义区域/按钮及键盘焦点可访问。
- [ ] Step 5: 运行新前端测试及已有 `StockDetail/ResearchWorkspaceToolbar/InvestmentWorkspace/IntegratedResearch/PriceChart` 测试，全部PASS；运行改动文件eslint及前端build成功。

### Task 8: 文档、独立复核、真实联调与本地交付

**Files:** Create `docs/a-share-value-investing.md`; Modify `docs/CHANGELOG.md`；一次性截图、日志与回滚清单放系统临时目录，不入库。

- [ ] Step 1: 完成中文使用说明：数据来源、数学公式、各产业适用/缺口、安全边际分母、草案确认、固定资本限制、长期回报缺口、费用和版本；CHANGELOG加扁平新功能项。评估英文文档：当前无对应专题，保留README不改。
- [ ] Step 2: 跑完整 `python -m pytest tests/test_a_share*.py -q` 和前端受影响测试；前端build及改动文件lint，若全局lint存在已知无关错误如实记录。检视diff/secret扫描，不复制任何凭据。
- [ ] Step 3: 按requesting-code-review/verification技能完成独立审查；特别复核本计划5条Review Focus，修复后只补必要回归。
- [ ] Step 4: 在配置环境使用云铝股份和一家公司经营模式不同的A股进行真实取数；另检查银行专有字段覆盖。记录来源、时间、字段完整度、失败/降级。选其中一家触发一次真实价值AI调用，验证结构/用量/草案与免费确定性计算；失败不自动追加付费调用。
- [ ] Step 5: 对运行目录先核验变更基线并备份，按白名单部署代码/静态资源，保留.env、模型配置、数据及原功能。确认无研究运行后安全重启；检查health、API、当前页面、手机宽度及一次股票切换。
- [ ] Step 6: 最终交付区分“已实现/验证”“缺源或待人工假设”“未验证收益”；提供回滚目录，不宣称已经提交GitHub。

## 计划自审

设计各部分映射：数据/时点/权限→1、2、5；跨产业/同行→2、3；内在价值/安全边际/陷阱→3、6、7；事件与持有期→4；AI成本/进度/版本→5、6、7；同页/图层→7；真实联调/保留原功能/文档/部署→8。五类Review Focus均有明确反例。所有产品步骤等待设计和计划审阅后执行；当前仅完成文档与源码调研。

独立builder-check提出的8项实质问题已落实到设计和任务：经营预测最低输入、FCFE非经营资产、并发计费去重、非银行金融覆盖、人工补充版本、价格兑现因子、V0/Vh同一排程、稳定期第6年现金流。未增加需要用户另行决定的投资偏好，安全边际要求仍由实际使用者填写。

实现前基线：2026-10-30在当前提交运行 `tests/test_a_share*.py`，559 passed、4 warnings、25.32秒；日志留在系统临时目录。该结果只证明修改前回归基线，不代表本计划功能已实现或验证。
