import { useCallback,useEffect,useMemo,useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { Candidate, RoleResearch, Journal, Evidence } from '../../types/aShare';
import type { Adjust,MarketStock,PriceScenarioResult,IndicatorSelection,ChartPriceLevel } from '../../types/aShareMarket';
import { useMarketHistory } from './useMarketHistory';
import { mapPrice,priceFamily,chartForecast,isConditionalPlan,provisionalPriceBar,integratedChartLayer } from './priceChartData';
import PriceChart from './PriceChart';
import PriceScenarioPanel from './PriceScenarioPanel';
import SavedAnalysisPanel from './SavedAnalysisPanel';
import {strategyPrice,useSavedAnalysis} from './savedAnalysis';
import IndicatorControls from './IndicatorControls';
import QuantOutlookPanel from './QuantOutlookPanel';
import { useQuantOutlook } from './useQuantOutlook';
import { useLivePrice } from './useLivePrice';
import { useIntegratedResearch } from './useIntegratedResearch';
import IntegratedResearchPanel from './IntegratedResearchPanel';
import ResearchWorkspaceToolbar from './ResearchWorkspaceToolbar';
import { integratedResearchStatus } from './integratedResearchStatus';
const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const since=(days:number)=>new Date(Date.parse(today())-days*86400000).toISOString().slice(0,10);
const safeUrl=(url?:string)=>{try{const u=new URL(url||'');return ['http:','https:'].includes(u.protocol)?u.href:undefined;}catch{return undefined;}};
export default function StockDetail({code,candidate,onWatchlist,research,events=[],onPriceRefresh}:{code:string;candidate?:Candidate;onWatchlist:(code:string)=>void;onResearch:(code:string)=>void;research?:RoleResearch;events?:Journal<Evidence>[];disabled?:boolean;remainingCalls?:number;onPriceRefresh?:(code:string)=>void}){
  const [adjust,setAdjust]=useState<Adjust>('qfq'),[chartType,setChartType]=useState<'candle'|'line'>('candle');
  const [start,setStart]=useState(()=>since(365)),[end,setEnd]=useState(today),[highlight,setHighlight]=useState(''),[showAI,setShowAI]=useState(true),[showRule,setShowRule]=useState(true),[showReport,setShowReport]=useState(true);
  const savedAnalysis=useSavedAnalysis(code);
  const [horizon,setHorizon]=useState(20),[minRewardRisk,setMinRewardRisk]=useState(2),[showFan,setShowFan]=useState(true),[showQuantPlan,setShowQuantPlan]=useState(true);
  const outlook=useQuantOutlook(code,minRewardRisk);
  const integrated=useIntegratedResearch(code);
  const [integratedHorizon,setIntegratedHorizon]=useState(20),[showIntegrated,setShowIntegrated]=useState(true);
  const integratedOutcome=integratedResearchStatus(integrated.result?.report,integratedHorizon);
  const [indicators,setIndicators]=useState<IndicatorSelection>(()=>{try{return JSON.parse(localStorage.getItem('a-share-indicators')||'null')||{MA20:true,MA60:true,volume:true};}catch{return {MA20:true,MA60:true,volume:true};}});
  const [saved,setSaved]=useState<{code:string;stock?:MarketStock;result?:PriceScenarioResult;error?:string}>({code:''});
  const {history,error,retry,reload}=useMarketHistory(code,start,end,adjust);
  const {history:raw,reload:reloadRaw}=useMarketHistory(code,start,end,'raw');
  const [stockReload,setStockReload]=useState({code:'',revision:0});
  const reloadOutlook=outlook.reload,reloadIntegrated=integrated.reload;
  const onLiveReady=useCallback(()=>{reload();reloadRaw();reloadOutlook();reloadIntegrated();onPriceRefresh?.(code);setStockReload(previous=>({code,revision:previous.revision+1}));},[code,reload,reloadRaw,reloadOutlook,reloadIntegrated,onPriceRefresh]);
  const live=useLivePrice(code,onLiveReady);
  useEffect(()=>{
    if(stockReload.code!==code)return;
    const controller=new AbortController();
    void aShareMarketApi.stock(code,controller.signal).then(stock=>{
      if(controller.signal.aborted)return;
      if(stock.code!==code)throw new Error('最新证券资料代码不匹配');
      setSaved(previous=>previous.code===code?{...previous,stock,error:undefined}:{code,stock});
    }).catch(error=>{if(!controller.signal.aborted)setSaved(previous=>previous.code===code?{...previous,error:error instanceof Error?error.message:'最新证券资料未取得'}:{code,error:'最新证券资料未取得'});});
    return ()=>controller.abort();
  },[code,stockReload]);
  useEffect(()=>{
    const c=new AbortController();let busy=false;
    const load=async()=>{if(busy)return;busy=true;try{const [stock,result]=await Promise.all([aShareMarketApi.stock(code,c.signal),aShareMarketApi.scenarios(code,c.signal)]);if(!c.signal.aborted)setSaved({code,stock,result});}catch(e){if(!c.signal.aborted)setSaved({code,error:e instanceof Error?e.message:'资料未取得'});}finally{busy=false;}};
    void load();const t=setInterval(()=>void load(),10000);return ()=>{c.abort();clearInterval(t);};
  },[code]);
  const numericalFan=useMemo(()=>chartForecast(outlook.result,raw,history,adjust,code,horizon),[outlook.result,raw,history,adjust,code,horizon]);
  const integratedLayer=useMemo(()=>integratedChartLayer(integrated.result,raw,history,adjust,code,integratedHorizon),[integrated.result,raw,history,adjust,code,integratedHorizon]);
  const stock=saved.code===code?saved.stock:undefined,result=saved.code===code?saved.result:undefined;
  const liveQuote=live.result?.quote,stockTime=Date.parse(stock?.quote?.fetched_at||'');
  const quote=liveQuote&&(!stock?.quote||!Number.isFinite(stockTime)||Date.parse(liveQuote.fetched_at)>=stockTime)?liveQuote:stock?.quote;
  const liveBar=useMemo(()=>provisionalPriceBar(live.result,history,adjust,end,code),[live.result,history,adjust,end,code]);
  const levels=useMemo(()=>{
    const output:ChartPriceLevel[]=[],ctx=result?.context;
    const r=raw?.items.at(-1),q=history?.items.at(-1);
    const paired=r&&q&&r.date===q.date&&priceFamily(raw?.source)===priceFamily(history?.source);
    const convert=(price:number)=>mapPrice(price,paired?r.close:null,paired?q.close:null,adjust);
    const add=(id:string,source:'ai'|'rule'|'report'|'quant',label:string,low:number|undefined|null,high?:number|null,horizon?:number)=>{if(low==null)return;const l=convert(low),h=high==null?null:convert(high);if(l==null||(high!=null&&h==null))return;output.push({id,source,kind:id,label,low:l,high:h,active:source==='ai'?showAI:source==='report'?showReport:source==='quant'?showQuantPlan:showRule,anchor_date:source==='ai'?ctx?.anchor_date:source==='quant'?outlook.result?.as_of:source==='rule'?history?.actual_end||undefined:undefined,horizon});};
    if(showRule&&candidate){add('rule-entry','rule','规则突破',candidate.high);add('rule-plan','rule','规则计划',candidate.plan?.entry);add('rule-stop','rule','规则止损',candidate.plan?.stop);}
    if(showReport&&savedAnalysis.status==='ready'&&savedAnalysis.report){const p=savedAnalysis.report.strategy;add('report-ideal','report','首页·理想买入',strategyPrice(p?.idealBuy));add('report-secondary','report','首页·二次买入',strategyPrice(p?.secondaryBuy));add('report-stop','report','首页·止损点',strategyPrice(p?.stopLoss));add('report-profit','report','首页·止盈目标',strategyPrice(p?.takeProfit));}
    const matches=ctx?.code===code&&ctx.anchor_date===history?.actual_end&&(adjust==='raw'||ctx.adjustment_basis===history?.adjustment_basis)&&ctx.reference_price===r?.close;
    if(matches&&result?.status!=='stale'&&showAI){const t=result?.trade_levels;if(t){add('ai-entry','ai','AI买入区间',t.entry_low,t.entry_high);add('ai-sell','ai','AI卖出区间',t.sell_low,t.sell_high);add('ai-stop','ai','AI止损',t.stop_reference);}result?.forecasts?.forEach(f=>add(`ai-${f.horizon_sessions}-${f.scenario}`,'ai',`${f.horizon_sessions}日${{bear:'谨慎',base:'中性',bull:'积极'}[f.scenario]}`,f.low,f.high,f.horizon_sessions));}
    const plan=outlook.result?.plan;
    if(numericalFan&&plan&&isConditionalPlan(plan,minRewardRisk)){add('quant-entry','quant','数值买入观察',plan.entry_low,plan.entry_high);add('quant-stop','quant','数值止损参考',plan.stop);add('quant-target','quant','数值目标观察',plan.target_low,plan.target_high);}
    return output;
  },[result,raw,history,adjust,showAI,showRule,showReport,savedAnalysis,candidate,code,numericalFan,outlook.result,minRewardRisk,showQuantPlan]);
  const reasons=[...(candidate?.check?.reasons||[]),...(candidate?.plan?.reasons||[])];
  const chartLevels=useMemo(()=>levels.concat(showIntegrated?integratedLayer?.levels||[]:[]),[levels,showIntegrated,integratedLayer]);
  const related=events.filter(e=>[e.payload.code,e.payload.related_code,e.payload.verification?.code].includes(code)||(!e.payload.code&&!e.payload.related_code));
  return <section role="region" aria-label="股票研究详情" className="am-stock-detail"><header className="am-stock-header"><div><p className="as-eyebrow">{code} · {stock?.demo?'虚构样本':stock?.identity_verified?'证券身份已核实':'证券身份待核实'}</p><h2>{stock?.name||candidate?.name||code}</h2><p className="as-muted">{stock?.industries?.map(s=>s.name).join('、')||'行业待补齐'} · {stock?.concepts?.map(s=>s.name).join('、')||'概念待补齐'}</p></div><div><strong className="am-quote">{quote?.price==null?'—':`¥${quote.price.toFixed(2)}`}</strong><p className="as-footnote">{live.state==='ready'&&live.result?.provisional===false?'收盘快照':'行情快照'} · {quote?.source_time||'行情源时间未知'}<br/>行情日 {quote?.trade_date||'未知'} · 获取 {quote?.fetched_at||'—'}</p><button className="am-button" onClick={()=>onWatchlist(code)}>加入 / 移出自选</button><button className="am-button am-live-button" disabled={live.loading} onClick={live.refresh}>刷新最新行情</button><p className="as-footnote am-live-status" role="status">{live.state==='pending'?'正在刷新最新行情…':live.loading?'正在读取最新行情缓存…':live.state==='failed'?'刷新失败，保留已获行情':live.result?.message||'尚无最新行情缓存'}<br/>最近获取 {live.result?.fetched_at||quote?.fetched_at||'未知'}</p>{live.error&&<p className="am-live-error" role="alert">{live.error}</p>}</div></header>
    <ResearchWorkspaceToolbar result={integrated.result} error={integrated.error} message={integrated.message} busy={integrated.busy} loading={integrated.loading} horizon={integratedHorizon} onHorizon={setIntegratedHorizon} onPrepare={()=>void integrated.prepare()} onGenerate={force=>void integrated.generate(force)} overlayMatched={!!(integratedLayer?.forecast||integratedLayer?.levels.length)}/>
    <section className="am-chart-panel" aria-label="K线与指标"><div className="am-toolbar"><label>图形<select aria-label="图形" value={chartType} onChange={e=>setChartType(e.target.value as 'candle'|'line')}><option value="candle">蜡烛图</option><option value="line">收盘线</option></select></label><label>价格口径<select aria-label="价格口径" value={adjust} onChange={e=>setAdjust(e.target.value as Adjust)}><option value="qfq">前复权</option><option value="raw">不复权</option></select></label><label>查看期间<select aria-label="查看期间" defaultValue="365" onChange={e=>{if(e.target.value!=='custom'){setStart(since(Number(e.target.value)));setEnd(today());}}}>{[[30,'1个月'],[90,'3个月'],[180,'6个月'],[365,'1年'],[1095,'3年'],['custom','自定义']].map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label><label>起始<input aria-label="起始日期" type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>截止<input aria-label="截止日期" type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label><button className="am-button" onClick={retry}>重试 / 更新历史</button></div>
      <IndicatorControls value={indicators} onChange={v=>{setIndicators(v);try{localStorage.setItem('a-share-indicators',JSON.stringify(v));}catch{/* private browsing */}}}/><div className="am-layer-controls"><label><input type="checkbox" checked={showRule} onChange={e=>setShowRule(e.target.checked)}/>规则价位</label><label><input type="checkbox" checked={showReport} onChange={e=>setShowReport(e.target.checked)}/>首页历史策略线（虚线）</label><label><input type="checkbox" checked={showAI} onChange={e=>setShowAI(e.target.checked)}/>AI价位与预测区间</label><label><input type="checkbox" checked={showQuantPlan} onChange={e=>setShowQuantPlan(e.target.checked)}/>数值观察价位</label></div>
      <div className="am-layer-controls"><label><input type="checkbox" checked={showIntegrated} onChange={e=>setShowIntegrated(e.target.checked)}/>综合情景与策略线（未校准）</label></div>
      {(error||(saved.code===code&&saved.error))&&<p role="alert">{error||saved.error}</p>}
      {!history&&<p className="as-footnote">正在查询历史缓存…</p>}
      {!integrated.busy&&!['preparing','running'].includes(integrated.result?.status||'')&&integratedOutcome.missingReason&&<p className="am-integrated-warning" role="status">综合情景未绘制：{integratedOutcome.missingReason}</p>}
      {history&&<><p className="as-footnote">{history.source||'来源待确认'} · {adjust==='qfq'?'前复权':'不复权'} · {history.state==='pending'?'补齐中':history.state==='partial'?'部分覆盖':history.state==='failed'?'获取失败':'缓存历史'} · 实际 {history.actual_start||'—'} 至 {history.actual_end||'—'}<br/>获取 {history.fetched_at||'—'} · 基准 {history.adjustment_basis||'—'}</p><PriceChart items={history.items||[]} warmup={history.warmup_items} chartType={chartType} indicators={indicators} levels={chartLevels} highlight={highlight} onHighlight={setHighlight} forecast={showFan?numericalFan:undefined} events={numericalFan?outlook.result?.events:undefined} live={liveBar} integrated={showIntegrated?integratedLayer?.forecast:undefined}/>{live.result?.state==='ready'&&live.result.provisional&&!liveBar&&<p className="as-footnote">临时行情的日期、来源或复权基准与当前期间不匹配，未叠加到图表。</p>}{history.limitations?.map(s=><p className="as-footnote" key={s}>{s}</p>)}</>}
    </section>
    <IntegratedResearchPanel controls={false} result={integrated.result} error={integrated.error} message={integrated.message} busy={integrated.busy} horizon={integratedHorizon} onHorizon={setIntegratedHorizon} onPrepare={offset=>void integrated.prepare(offset)} onGenerate={force=>void integrated.generate(force)} onHighlight={setHighlight} overlayMatched={!!(integratedLayer?.forecast||integratedLayer?.levels.length)}/>
    <div className="am-detail-grid am-detail-grid-unified"><div className="am-detail-main"><SavedAnalysisPanel code={code} state={savedAnalysis}/><QuantOutlookPanel result={outlook.result} error={outlook.error} loading={outlook.loading} horizon={horizon} minRewardRisk={minRewardRisk} onHorizon={setHorizon} onMinRewardRisk={setMinRewardRisk} onRetry={outlook.retry} showFan={showFan} onShowFan={setShowFan} overlayMatched={!!numericalFan}/>
      {candidate&&<div className="am-rule-plan"><h3>原规则计划 · {candidate.strategy}</h3><p>本次计划参考价：{candidate.plan?.entry??'资料不足'} · 计划股数：{candidate.plan?.quantity??'账户资料不足'} · 止损参考：{candidate.plan?.stop??'资料不足'} · 有效日：{candidate.valid_date||'待补充'}</p><p>得分 {candidate.score} · 20日 {(candidate.r20*100).toFixed(2)}% · 60日 {(candidate.r60*100).toFixed(2)}% · 波幅 {candidate.atr?.toFixed(2)} · 状态 {candidate.check?.status||'observe'}</p></div>}
      <details className="am-evidence"><summary>历史研究观点与共享证据</summary>{research?.roles.map(r=><article className="as-role" key={r.role}><h3>{{bull_researcher:'支持观点',bear_researcher:'反对观点',research_manager:'情景与分歧',news_analyst:'事件研究',fundamentals_analyst:'基本面研究'}[r.role]||r.role} · {r.status}</h3>{r.claims.map((c,i)=><p key={i}>{c.text} [{c.sources.join(', ')}]</p>)}{r.message&&<p>{r.message}</p>}</article>)}{!research&&<p className="as-footnote">暂无旧版研究记录。新研究统一从K线旁“生成综合研究与价位”开始。</p>}{research?.evidence.map(e=><p className="as-footnote" key={e.id}>{e.id} · {e.source} {safeUrl(e.url)&&<a href={safeUrl(e.url)} target="_blank" rel="noreferrer">原文 ↗</a>}<br/>{e.content?.slice(0,500)}</p>)}{research?.limitations.map(s=><p className="as-footnote" key={s}>{s}</p>)}</details>
      <details className="am-evidence"><summary>相关新闻与公告 · {related.length} 条</summary>{related.slice(0,20).map(e=><article key={e.id}><h3>{safeUrl(e.payload.url)?<a href={safeUrl(e.payload.url)} target="_blank" rel="noreferrer">{e.payload.title} ↗</a>:e.payload.title}</h3><p>{e.payload.content?.slice(0,300)}</p><p className="as-footnote">{e.payload.source} · 首次获取 {e.payload.first_seen} · {e.payload.verification?'已有人工核实':'待核实'} · {e.payload.coverage}</p></article>)}{!related.length&&<p className="as-footnote">已获取资料没有相关记录，不代表没有风险；人工核实仍在原资讯页。</p>}</details>
    <details className="am-evidence"><summary>历史AI价位与情景（旧版5/10/20日）</summary><PriceScenarioPanel result={result} onHighlight={setHighlight} riskReasons={reasons}/></details></div></div>
  </section>;
}
