import { useState } from 'react';
import type { IntegratedResearchResult } from '../../types/aShareMarket';
import { integratedResearchStatus } from './integratedResearchStatus';

const money=(n:number|null|undefined)=>n!=null&&Number.isFinite(n)?`¥${n.toFixed(2)}`:'依据不足';
const percent=(n:unknown)=>typeof n==='number'&&Number.isFinite(n)?`${(n*100).toFixed(2)}%`:'未取得';
const safe=(url:unknown)=>{try{const u=new URL(String(url));return ['https:','http:'].includes(u.protocol)?u.href:undefined;}catch{return undefined;}};
const names:Record<string,string>={financial:'财报与业绩',valuation:'估值',disclosures:'公司公告',news:'新闻与政策',technical:'技术与完整日线',industry:'行业归属',liquidity:'成交额与流动性',chips:'筹码',ready:'已取得',partial:'部分取得',mixed_types:'不同报表口径，分开核对',missing:'缺失',failed:'失败',ok:'已完成',skipped:'资料不足，已跳过',trend_pullback:'趋势回踩',range_reversion:'区间回归',event_followthrough:'事件跟踪',observe:'观察',conditional:'条件成立后观察'};
const fieldNames:Record<string,string>={revenue:'营业收入',net_profit:'归母净利润',deducted_profit:'扣非净利润',operating_cashflow:'经营现金流',cash_profit_ratio:'现金含量',cashflow_per_share:'每股经营现金流',assets:'总资产',liabilities:'总负债',revenue_yoy:'营收同比',profit_yoy:'利润同比',roe:'ROE',gross_margin:'毛利率',debt_ratio:'负债率',eps:'每股收益',bps:'每股净资产',pe_ttm:'市盈率TTM',pb:'市净率',pe_percentile:'历史PE分位',trade_date:'估值日期'};

const lifecycleNames:Record<string,string>={tracking:'持续核查',superseded:'后续披露已取代',needs_text:'待补原文',needs_review:'待核查解除进展',background:'历史背景',withdrawn:'已撤回',unanchored:'尚无有效价格锚点'};
const dimensionNames:Record<string,string>={market_state:'市场状态',pre20:'当前阶段涨幅',event_pre20:'事件前涨幅',realized_since_event:'事件后已实现涨幅',intensity:'事件强度',industry_id:'历史行业',valuation_percentile:'估值分位'};

function caseOutcome(event:Record<string,unknown>,horizon:number):Record<string,unknown> {
  const outcomes=event.outcomes;
  if(!outcomes||typeof outcomes!=='object')return {};
  const row=(outcomes as Record<string,unknown>)[String(horizon)];
  return row&&typeof row==='object'?row as Record<string,unknown>:{};
}

export default function IntegratedResearchPanel({result,error,message,busy=false,horizon,onHorizon,onPrepare,onGenerate,onHighlight,overlayMatched,controls=true}: {
  result?:IntegratedResearchResult;error?:string;message?:string;busy?:boolean;horizon:number;onHorizon:(h:number)=>void;
  onPrepare:(offset?:number)=>void;onGenerate:(force:boolean)=>void;onHighlight?:(id:string)=>void;overlayMatched?:boolean;controls?:boolean;
}) {
  const outcome=integratedResearchStatus(result?.report,horizon);
  const report=result?.report,bundle=result?.bundle,working=busy||result?.status==='preparing'||result?.status==='running';
  const [peerBatch,setPeerBatch]=useState({code:result?.code,offset:20});
  const [eventId,setEventId]=useState('');
  const peerOffset=Math.max(peerBatch.code===result?.code?peerBatch.offset:20,result?.peer_progress?.next_offset||20);
  const plan=report?.plans?.find(p=>p.horizon_sessions===horizon),forecasts=report?.forecasts?.filter(f=>f.horizon_sessions===horizon)||[];
  const match=bundle?.cases?.cohorts?.find(c=>c.target_event?.id===eventId)||bundle?.cases;
  const stats=match?.horizons?.[String(horizon)];
  const stale=result?.status==='stale'||report?.stale;
  const cases=[...(match?.cases||[]),...(match?.reference_cases||[])].slice(0,20);
  const diagnostics=bundle?.cases?.diagnostics;
  const validation=result?.validation,measured=validation?.horizons[String(horizon)],comparison=validation?.comparison.horizons[String(horizon)];
  return <section role="region" aria-label="综合预测与策略" className="am-integrated">
    <header className="as-section-heading"><div><p className="as-eyebrow">多维资料 · 多专家复核</p><h2>综合预测与策略</h2><p className="as-footnote">研究估计，尚未校准 · 价位均为人民币不复权参考</p></div>{controls?<label>综合研究期限<select aria-label="综合研究期限" value={horizon} onChange={e=>onHorizon(Number(e.target.value))}>{[5,20,60].map(h=><option value={h} key={h}>{h}交易日</option>)}</select></label>:<span>{horizon}交易日 · 研究详情</span>}</header>
    {controls&&<div className="am-toolbar"><button className="am-button" disabled={working} onClick={()=>onPrepare()}>更新研究资料</button><button className="am-primary" disabled={working} onClick={()=>onGenerate(false)}>生成综合预测</button>{report&&<button className="am-button" disabled={working} onClick={()=>onGenerate(true)}>重新生成（按用量计费）</button>}</div>}
    <p className="as-footnote">资料准备不调用AI；完整研究最多6类专家，按实际调用计费。手动生成不限每日次数，看图和切换期限不调用模型。</p>
    {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    {controls&&working&&<p role="status">{result?.progress?.message||'正在后台准备研究资料…'} {result?.progress?`${result.progress.completed} / ${result.progress.expected}`:''}</p>}
    {!!result?.peer_progress?.total&&<p className="as-footnote">同业资料任务：完成 {result.peer_progress.complete} / {result.peer_progress.total} · 排队 {result.peer_progress.pending} · 进行中 {result.peer_progress.running} · 失败 {result.peer_progress.failed}。可以先研究已有资料，任务完成不等于已满足严格案例门槛。</p>}
    {result?.task?.error&&<p role="alert">{result.task.error}</p>}
    {result?.status==='waiting_history'&&<p role="status">{result.message}；请先更新行情，资料已经保存，无需重复抓取。</p>}
    {report?.error&&<p role="alert">综合研究未完成：{report.error}。可重试，已有资料保留。</p>}
    {report?.rejections?.map((r,i)=><p className="am-integrated-warning" key={i}>{r.horizon||''}日{r.kind==='plan'?'策略':'情景'}未发布：{r.reason}</p>)}
    {stale&&<p className="am-integrated-warning">{result?.stale_reasons?.length?result.stale_reasons.join('；'):'资料或价格已变化'}，当前为历史研究；更新资料并重新生成后再查看叠加。</p>}
    {!bundle&&!working&&<p className="as-footnote">尚无综合研究资料，请先更新研究资料，再生成综合预测。</p>}
    {bundle&&<p className="as-footnote">当前资料截止 {bundle.cutoff} · 当前价格锚点 {bundle.anchor_date} {money(bundle.reference_price)}</p>}
    {diagnostics&&<div className="am-evidence" aria-label="事件跟踪概况"><p>公告 {diagnostics.announcements} 条 · 已核对原文 {diagnostics.verified_texts} 份 · 持续跟踪 {diagnostics.tracking_events} 项 · 可量化匹配 {diagnostics.quantified_targets} 项</p><p className="as-footnote">事件按类型和证据状态继续核查，不再统一在20日后失效。核查周期不是实际影响期限，跟踪不表示仍有上涨空间；超预期与衰减未经估计时保持未知。</p>{!!diagnostics.unquantified_tracking&&<p className="as-footnote">{diagnostics.unquantified_tracking} 项跟踪事件仍缺原文或可核对强度，仅作定性研究及风险核查。</p>}{!!diagnostics.omitted_targets&&<p>本次另有 {diagnostics.omitted_targets} 项量化候选未进入比较，未合并其数值影响。</p>}</div>}
    {bundle?.cases.status==='no_target'&&<p role="status">{bundle.cases.message}</p>}
    {report&&<p className="as-footnote">研究生成 {report.generated_at} · 研究价格锚点 {report.anchor_date} {money(report.reference_price)} · 本次专家调用 {report.calls} 次{!overlayMatched&&<> · 当前图表未匹配研究锚点或没有有效价位</>}</p>}
    {report&&<><div className="am-integrated-grid">{forecasts.map(f=><article key={f.scenario} className="am-integrated-card"><span>{({bear:'偏弱',base:'基准',bull:'偏强'} as const)[f.scenario]}情景 · {horizon}日</span><strong>{money(f.low)} – {money(f.high)}</strong><p>{f.conditions.join('；')}</p><p className="as-footnote">{f.derivation}<br/>依据 {f.basis_ids.join('、')} · 来源 {f.sources.join('、')}</p></article>)}</div>
      {!forecasts.length&&<p className="as-footnote">{outcome.missingReason||'该期限尚无通过校验的综合预测价位；价格基线仍可单独查看。'}</p>}
      {!plan&&<p className="as-footnote">{horizon}日尚无综合交易策略；买入、二次买入、止损与盈利目标暂未提供。</p>}
      {plan&&<article className="am-integrated-plan"><h3>{names[plan.strategy_kind]||plan.strategy_kind} · {names[plan.status]}</h3><div className="am-integrated-grid">
        <button className="am-level" onClick={()=>onHighlight?.('integrated-entry')}><span>理想买入观察区间</span><strong>{money(plan.entry_low)} – {money(plan.entry_high)}</strong></button>
        <button className="am-level" onClick={()=>onHighlight?.('integrated-second')}><span>二次买入观察区间</span><strong>{plan.second_entry?`${money(plan.second_entry.low)} – ${money(plan.second_entry.high)}`:'依据不足'}</strong></button>
        <button className="am-level" onClick={()=>onHighlight?.('integrated-stop')}><span>止损参考</span><strong>{money(plan.stop_reference)}</strong></button>
      </div><p>分段盈利目标：{plan.targets.length?plan.targets.map(money).join(' / '):'依据不足'} · 潜在收益/风险 {plan.reward_risk?.toFixed(2)||'未核实'}{plan.net_reward_risk!=null&&<> · 示例成本后 {plan.net_reward_risk.toFixed(2)}（实际成本未验证）</>}</p>
      <p>成立：{plan.conditions.join('；')}<br/>失效：{plan.invalidation.join('；')}<br/>有效至 {plan.valid_until}</p>{plan.second_entry&&<p>二次观察条件：{plan.second_entry.conditions.join('；')} · 失效：{plan.second_entry.invalidation.join('；')}</p>}
      {plan.rejection_reasons.map(r=><p className="am-integrated-warning" key={r}>{r}</p>)}</article>}
      <details><summary>专家结论与分歧 · {report.roles?.length||0} 类角色</summary>{report.roles?.map(r=><article className="am-evidence" key={r.role}><h3>{r.label} · {names[r.status]||r.status}</h3>{r.claims.map((c,i)=><p key={i}>{c.text}<small> [{c.sources.join('、')}]</small></p>)}{r.message&&<p>{r.message}</p>}{report.role_evidence?.[r.role]&&<p className="as-footnote">实际收到 {report.role_evidence[r.role].sent_ids.length} 项资料 · 因预算未发送 {report.role_evidence[r.role].omitted_ids.length} 项</p>}</article>)}</details>
    </>}
    {bundle&&<><details><summary>资料覆盖与来源</summary><div className="am-integrated-grid">{bundle.coverage.map(c=><article key={c.category}><strong>{names[c.category]||c.category}</strong><p>{names[c.status]||c.status} · {c.count} 条{c.texts!=null?` · ${c.texts} 份原文`:''}</p>{c.pending!=null&&<p>待补正文 {c.pending} 份 · 本轮尝试 {c.attempted||0} 份 · 暂缓重试 {c.retry_wait||0} 份</p>}<small>{c.sources?.join('、')||c.source}</small></article>)}</div>
      {bundle.coverage.some(c=>c.category==='disclosures'&&(c.pending||0)>0)&&<div><button className="am-button" disabled={working} onClick={()=>onPrepare()}>补齐下一批公告正文</button><p className="as-footnote">复用已保存正文，每轮最多新增6份；失败文件暂缓一小时重试，优先补齐跟踪事件，兼顾历史资料。不调用AI模型。</p></div>}
      {bundle.missing.map(s=><p className="am-integrated-warning" key={s}>{s}</p>)}
      {bundle.context.financial_coverage&&<details><summary>最新报告期财务字段 · {bundle.context.financial_coverage.report_period||'未知'}</summary>{Object.entries(bundle.context.financial_coverage.fields).map(([field,value])=><p key={field}>{fieldNames[field]||field}：{names[value.status]||value.status}{value.reason?` · ${value.reason}`:` · ${value.value??value.values?.join(' / ')??''}`}<small> {value.fact_ids.join('、')}</small>{value.status==='mixed_types'&&value.observations?.map(o=><small key={o.fact_id}> · 类型{o.report_type||'未知'}：{o.value.toLocaleString()}（{o.source}）</small>)}</p>)}</details>}
      {bundle.facts.filter(f=>f.category==='news').map(f=><article className="am-evidence" key={'news-'+f.fact_id}><h4><a href={safe(f.url)} target="_blank" rel="noreferrer">{String(f.values.title||'相关新闻')} ↗</a></h4><p className="as-footnote">{f.source} · {f.published_at} · {f.fact_id} · 搜索摘要</p><p>{String(f.values.content||'').slice(0,800)}</p></article>)}
      {bundle.facts.slice(0,16).map(f=><article className="am-evidence" key={f.fact_id}><h4>{names[f.category]||f.category} · {f.report_period||String(f.values.trade_date||'')} {safe(f.url)&&<a href={safe(f.url)} target="_blank" rel="noreferrer">来源 ↗</a>}</h4><p className="as-footnote">{f.source} · 可用时间 {f.available_at||'未知'} · {f.fact_id}</p><p>{Object.entries(f.values).filter(([k,v])=>fieldNames[k]&&v!=null).slice(0,10).map(([k,v])=>`${fieldNames[k]}：${typeof v==='number'&&['roe','gross_margin','debt_ratio','profit_yoy','revenue_yoy','pe_percentile'].includes(k)?percent(v):typeof v==='number'?v.toLocaleString():String(v)}`).join('；')}</p></article>)}
      {[...bundle.events].sort((a,b)=>Number(!!b.tracking_active)-Number(!!a.tracking_active)||Number(b.text_status==='ready')-Number(a.text_status==='ready')).slice(0,24).map(e=><article className="am-evidence" key={e.id}><h4>{safe(e.url)?<a href={safe(e.url)} target="_blank" rel="noreferrer">{e.title} ↗</a>:e.title}</h4><p className="as-footnote">{e.published_at} · {e.text_status==='ready'?'原文已取得':'正文未取得'} · {e.id}</p>{e.lifecycle_state&&<p>{lifecycleNames[e.lifecycle_state]||e.lifecycle_state} · {e.age_sessions!=null?`已过${e.age_sessions}个交易日`:'阶段未知'} · 类型核查周期 {e.review_sessions} 日<br/>{e.review_reason}</p>}<p>{e.text?.slice(0,500)}</p></article>)}
      {report&&<details><summary>专家实际使用的来源清单 · {report.evidence?.length||0} 项</summary>{report.evidence?.map(e=><p key={e.id}><strong>{e.id}</strong> · {names[e.category]||e.category} · {e.source||'派生依据'} {safe(e.url)&&<a href={safe(e.url)} target="_blank" rel="noreferrer">核对来源 ↗</a>}</p>)}</details>}
    </details><details><summary>可比历史事件 · {horizon}交易日</summary>{!!bundle.cases.cohorts?.length&&<label>当前比较事件<select aria-label="当前比较事件" value={match?.target_event?.id||''} onChange={e=>setEventId(e.target.value)}>{bundle.cases.cohorts.map(c=><option key={c.target_event?.id} value={c.target_event?.id}>{c.target_event?.published_at?.slice(0,10)} · {c.target_event?.title} · 已过{c.elapsed_sessions}日</option>)}</select></label>}{match?.target_event&&<p>从事件后的第{match.elapsed_sessions}个交易日继续观察未来{horizon}日；各事件独立比较，不叠加重复收益。</p>}{stats&&<><p>{stats.sample_size} 个事件 · {stats.companies} 家公司</p><p>{stats.numerical_eligible?'达到样本门槛，历史分布仍不是未来概率':match?.status==='no_target'?'未启动历史比较':'样本不足，未发布历史事件数值预测'} · {stats.reason}</p><p>个股中位收益 {percent(stats.median_return)} · 市场超额 {percent(stats.median_market_excess)} · 行业超额 {percent(stats.median_industry_excess)}</p>{stats.concentration_warning&&<p className="as-footnote">样本集中于少数年份，代表性有限。</p>}</>}
      {!!match?.missing_dimensions?.length&&<p>缺少匹配维度：{match.missing_dimensions.map(k=>dimensionNames[k]||k).join('、')}</p>}
      <div className="am-integrated-case-table"><table><thead><tr><th>事件</th><th>发生时间</th><th>市场</th><th>事件前20日</th><th>当前阶段20日</th><th>强度</th><th>期内收益</th><th>市场超额</th><th>行业超额</th></tr></thead><tbody>{cases.map((e,i)=>{const outcome=caseOutcome(e,horizon);return <tr key={String(e.id||i)}><td>{safe(e.url)?<a href={safe(e.url)} target="_blank" rel="noreferrer">{String(e.title||e.code)}</a>:String(e.title||e.code)}</td><td>{String(e.published_at||'未知').slice(0,10)}</td><td>{String(e.market_state||'未知')}</td><td>{percent(e.event_pre20)}</td><td>{percent(e.pre20)}</td><td>{percent(e.intensity)}</td><td>{percent(outcome.stock_return)}</td><td>{percent(outcome.market_excess)}</td><td>{percent(outcome.industry_excess)}</td></tr>;})}</tbody></table></div>
      {!cases.length&&<p className="as-footnote">尚无满足可比条件的案例，不能用今日行业分类补造过去的同行关系。</p>}
      {Object.keys(match?.excluded||{}).length>0&&<p className="as-footnote">筛除记录：{Object.entries(match?.excluded||{}).map(([reason,count])=>`${({self:'当前事件或同一版本族',future:'未来记录',unverified_publication:'未核对原文',event_kind:'事件类型不同',earnings_stage:'业绩披露阶段不同',superseded_at_stage:'对齐阶段已有后续业绩',intensity_unit:'强度口径不同',direction:'方向不同或未知',unverified_industry:'历史行业未核实',industry:'行业不同',duplicate_family:'重复或更正事件'} as Record<string,string>)[reason]||reason} ${count}`).join('；')}</p>}
      <button className="am-button" disabled={working||peerOffset>500} onClick={()=>{onPrepare(peerOffset);setPeerBatch({code:result?.code,offset:peerOffset+20});}}>补充下一批同业资料</button><span className="as-footnote"> 每批最多20家公司 · 下一批起点 {peerOffset}</span>
      {bundle.cases.limitations?.map(s=><p className="as-footnote" key={s}>{s}</p>)}</details></>}
    {validation&&<details><summary>预测实绩与同条件对照</summary>
      {measured?.matured?<><p>{horizon}日成熟预测 {measured.matured} 条 · 独立窗口 {measured.non_overlapping_samples} 条</p><p>平均绝对误差 {money(measured.mean_absolute_error)} · 方向符合 {percent(measured.direction_accuracy)} · 观察到的情景覆盖 {percent(measured.observed_scenario_coverage)} · 平均不利变动 {percent(measured.mean_adverse)}</p></>:<p>尚无成熟的{horizon}日预测，不能据此宣称准确率提升。</p>}
      {comparison&&<p>相同样本 {comparison.samples} 条 · 不变价误差 {money(comparison.unchanged_price_mae)} · 价格模型误差 {money(comparison.price_model_mae)} · 综合情景误差 {money(comparison.integrated_mae)}</p>}
      <p className="am-integrated-warning">综合策略收益尚未验证；未生成财务单项、事件单项的实验结果时，不展示增量收益。</p>{validation.limitations.map(s=><p className="as-footnote" key={s}>{s}</p>)}
    </details>}
    {report?.limitations?.map(s=><p className="as-footnote" key={s}>{s}</p>)}
  </section>;
}
