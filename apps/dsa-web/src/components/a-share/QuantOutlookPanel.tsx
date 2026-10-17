import type { QuantOutlook } from '../../types/aShareMarket';
import { isConditionalPlan } from './priceChartData';

const money=(value:number|null|undefined)=>value==null||!Number.isFinite(value)?'资料不足':`¥${value.toFixed(2)}`;
const percent=(value:number|null|undefined)=>value==null||!Number.isFinite(value)?'资料不足':`${(value*100).toFixed(1)}%`;
const samples=(value:number|null|undefined)=>value!=null&&Number.isInteger(value)&&value>=0?`${value} 个`:'资料不足';
const state={up:'向上',down:'向下',range:'震荡',unknown:'未知',insufficient:'资料不足'};
const safeUrl=(value:string|null)=>{try{const url=new URL(value||'');return ['http:','https:'].includes(url.protocol)?url.href:undefined;}catch{return undefined;}};

export default function QuantOutlookPanel({result,error,loading,horizon,minRewardRisk,onHorizon,onMinRewardRisk,onRetry,showFan,onShowFan,overlayMatched}:{
  result?:QuantOutlook;error?:string;loading:boolean;horizon:number;minRewardRisk:number;onHorizon:(value:number)=>void;onMinRewardRisk:(value:number)=>void;onRetry:()=>void;showFan:boolean;onShowFan:(value:boolean)=>void;overlayMatched:boolean;
}) {
  const forecast=result?.forecasts.find(item=>item.horizon_sessions===horizon),plan=result?.plan;
  const available=result&&['ready','partial'].includes(result.status);
  const conditional=available&&plan&&isConditionalPlan(plan,minRewardRisk);
  return <section className="am-quant" aria-label="多周期数值研究">
    <div className="am-quant-heading"><div><h3>多周期数值研究</h3><p className="as-footnote">本地统计基线 · 读取与切换不调用模型</p></div><button className="am-button" onClick={onRetry}>更新数值研究</button></div>
    <div className="am-toolbar"><label>预测期限<select aria-label="预测期限" value={horizon} onChange={e=>onHorizon(Number(e.target.value))}>{[5,20,60].map(value=><option value={value} key={value}>{value} 交易日</option>)}</select></label><label>最低盈亏比<select aria-label="最低盈亏比" value={minRewardRisk} onChange={e=>onMinRewardRisk(Number(e.target.value))}>{[1,1.5,2,2.5,3,4,5].map(value=><option value={value} key={value}>{value}:1</option>)}</select></label><label className="am-quant-toggle"><input type="checkbox" checked={showFan} onChange={e=>onShowFan(e.target.checked)}/>数值预测扇形</label></div>
    {loading&&<p className="as-footnote" role="status">正在查询数值研究…</p>}
    {error&&<p role="alert">{error}{result?' · 保留同一股票与门槛最近成功的缓存，来源与生成时间见证据。':''}</p>}
    {result&&<>
      <p className="am-status">{{pending:'历史补齐中 · 尚无可用预测',ready:'统计基线已就绪',partial:'部分资料可用 · 缺口见证据',insufficient:'历史样本不足 · 继续观察',failed:'数据获取失败 · 请重试'}[result.status]}{result.demo?' · 虚构样本':''}</p>
      <div className="am-quant-trends">{result.trends.map(trend=><div key={trend.period}><span>{trend.period}日趋势 · {state[trend.state]}</span><strong>MA{trend.period} {money(trend.ma)}</strong><small>距均线 {percent(trend.distance)} · 斜率 {percent(trend.slope)}</small></div>)}</div>
      <p className="as-footnote">最近完整周 {result.weekly.as_of||'资料不足'} · {state[result.weekly.state]} · MA10周 {money(result.weekly.ma10)} · MA30周 {money(result.weekly.ma30)}</p>
      <p className="as-footnote">市场 {state[result.environment.market_state]} · 相对基准20 / 60日 {percent(result.environment.relative20)} / {percent(result.environment.relative60)} · 相对行业 {percent(result.environment.sector_relative20)} / {percent(result.environment.sector_relative60)}</p>
      {available&&forecast?<>
        <div className="am-quant-range"><span>{horizon}交易日 · 不复权参考区间</span><strong>{money(forecast.low)} — {money(forecast.high)}</strong><span>中位 {money(forecast.median)} · {forecast.target_date||'未来日历未知，按交易日序号展示'}</span></div>
        <p className="as-footnote">名义覆盖 {percent(forecast.nominal_coverage)}，不等于已校准准确率。{forecast.calibration_state==='insufficient'?'区间校准样本不足。':'区间来自历史残差。'}</p>
        <p className="as-footnote">滚动验证 · 价格误差样本 {samples(forecast.validation.samples)} · 区间覆盖样本 {samples(forecast.validation.coverage_samples)} · {forecast.validation.state==='measured'?`实测覆盖 ${percent(forecast.validation.coverage)} · 平均绝对误差 ${money(forecast.validation.mean_absolute_error)} · 不变价格基线 ${money(forecast.validation.baseline_mean_absolute_error)}`:'滚动验证资料不足，尚无实测误差与覆盖率。'}价格误差验证不代表组合盈利。</p>
        {showFan&&!overlayMatched&&<p className="as-footnote">预测与当前图表的股票、来源、锚点或复权基准不匹配，扇形暂不叠加。</p>}
      </>:<p className="as-footnote">该期限尚无有效数值区间，待历史与验证样本补齐。</p>}
      {plan&&<div className="am-quant-plan"><h3>{conditional?'条件式观察计划':'仅观察 · 条件未齐备'} · {plan.horizon_sessions}交易日</h3>{conditional&&<p>观察买入 {money(plan.entry_low)} — {money(plan.entry_high)} · 止损参考 {money(plan.stop)} · 目标 {money(plan.target_low)} — {money(plan.target_high)} · 盈亏比 {plan.reward_risk?.toFixed(2)??'资料不足'}:1</p>}<p className="as-footnote">门槛 {plan.min_reward_risk}:1 · 有效至 {plan.valid_until||'未来日历未知'}<br/>成立：{plan.conditions.join('；')||'资料不足'}<br/>失效：{plan.invalidation.join('；')||'资料不足'}</p>{plan.reasons.map(reason=><p className="as-footnote" key={reason}>{reason}</p>)}</div>}
      <details className="am-evidence"><summary>来源与时间证据 · 事件观察 {result.events.length} 条</summary><p className="as-footnote">{result.source||'来源未知'} · 不复权 · 锚点 {result.as_of||'未知'} · 参考 {money(result.reference_price)} · 历史 {result.history_sessions} 个交易日<br/>生成 {result.generated_at||'未知'} · 版本 {result.version} · 复权基准 {result.adjustment_basis||'未知'}<br/>原始 / 前复权锚点 {money(result.raw_anchor)} / {money(result.qfq_anchor)} · 数据标识 {result.data_hash||'未知'}</p>
        <p className="as-footnote">{forecast?`方法 ${forecast.method} · 训练样本 ${forecast.sample_size} · 验证方法 ${forecast.validation.method}`:'预测方法尚未取得'}<br/>归档 {result.archive.snapshots} 条 · 已成熟 {result.archive.matured} 条 · 实测覆盖 {percent(result.archive.coverage)} · 平均绝对误差 {money(result.archive.mean_absolute_error)}</p>
        {result.events.map(event=><article key={event.id}><h3>{safeUrl(event.url)?<a href={safeUrl(event.url)} target="_blank" rel="noreferrer">{event.title} ↗</a>:event.title}</h3><p className="as-footnote">{event.kind} · {event.verified?'已核实':'待核实'} · 事件日 {event.date||'未知'}<br/>发布时间 {event.published_at||'未知'} · 首次获取 {event.first_seen||'未知'}</p><p className="as-footnote">{event.impact.state==='observed'?`观察样本 ${event.impact.samples} · ${event.impact.horizon_sessions}交易日超额收益中位 ${percent(event.impact.median_excess)} · 区间 ${percent(event.impact.low)} — ${percent(event.impact.high)}`:'事件影响资料不足'} · {event.impact.reason}</p></article>)}
        <p className="as-footnote">事件观察不证明因果关系。{!result.events.length?'未取得相关事件，不代表不存在风险。':''}</p>{result.limitations.map(limit=><p className="as-footnote" key={limit}>{limit}</p>)}
      </details>
    </>}
  </section>;
}
