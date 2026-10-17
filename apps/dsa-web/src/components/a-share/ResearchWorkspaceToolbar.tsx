import type { IntegratedResearchResult } from '../../types/aShareMarket';
import { integratedResearchStatus } from './integratedResearchStatus';
const roles=['市场与行业','业绩与估值','事件与历史案例','价格与流动性','风险复核','综合经理'];
const money=(value:number)=>`¥${value.toFixed(2)}`;
const duration=(value:number)=>{const seconds=Math.max(0,Math.floor(value));return `${Math.floor(seconds/60)}分${seconds%60}秒`;};
const statusName:Record<string,string>={pending:'待处理',running:'进行中',ok:'已完成',failed:'失败',skipped:'资料不足，跳过',insufficient:'已处理，依据不足',budget_exhausted:'自动预算不足'};
export default function ResearchWorkspaceToolbar({result,error,message,busy=false,loading=false,horizon,onHorizon,onPrepare,onGenerate,overlayMatched=false}: {
 result?:IntegratedResearchResult;error?:string;message?:string;busy?:boolean;loading?:boolean;horizon:number;
 onHorizon:(value:number)=>void;onPrepare:()=>void;onGenerate:(force:boolean)=>void;overlayMatched?:boolean;
}) {
 const report=result?.report,p=result?.progress;
 const outcome=integratedResearchStatus(report,horizon);
 const working=busy||result?.status==='preparing'||result?.status==='running';
 const stale=!!report&&(!!report.stale||result?.status==='stale'||report.data_hash!==result?.bundle?.data_hash);
 const completed=!!report&&!stale&&!working&&['complete','partial','failed'].includes(report.status);
 const percent=working?Math.min(95,p?.percent??Math.round((p?.completed||0)/(p?.expected||6)*100)):completed?100:0;
 const forecasts=report?.forecasts.filter(f=>f.horizon_sessions===horizon&&Number.isFinite(f.low)&&Number.isFinite(f.high)&&f.low>0&&f.low<=f.high)||[];
 const elapsed=p?.elapsed_seconds;
 const steps:{role:string;label:string;status:string;duration_seconds?:number|null}[]=p?.steps||roles.map((label,i)=>({role:String(i),label,status:completed?'ok':i<(p?.completed||0)?'ok':i===(p?.completed||0)&&result?.status==='running'?'running':'pending'}));
 return <section className="am-research-workspace" aria-label="统一研究与生成进度">
  <div className="am-research-actions"><div><strong>综合研究与价位</strong><p className="as-footnote">一次研究整合多方观点、未来区间和策略；最多6类角色，按实际模型用量计费。</p></div>
   <label>综合预测期限<select aria-label="综合研究期限" value={horizon} onChange={e=>onHorizon(Number(e.target.value))}>{[5,20,60].map(h=><option key={h} value={h}>{h}交易日</option>)}</select></label>
   <button className="am-primary" disabled={working||loading} onClick={()=>onGenerate(false)}>生成综合研究与价位</button>
   <details><summary>资料与重新生成</summary><button className="am-button" disabled={working} onClick={onPrepare}>更新研究资料</button>{report&&<button className="am-button" disabled={working} onClick={()=>onGenerate(true)}>重新生成（按用量计费）</button>}<p className="as-footnote">首次先准备资料；查看、切换期限不调用模型。重新生成会产生新的模型用量。</p></details>
  </div>
  {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  {loading&&!result&&<p role="status">正在读取已保存的研究与预测区间…</p>}
  {(working||completed)&&<div className="am-research-progress" aria-live="polite">
   <strong>{working?`${p?.current||p?.message||'准备研究'} · ${percent}%`:`${outcome.title}${outcome.hasPrices?' · 100%':''}`}</strong>
   {working&&<><progress aria-label="综合研究完成比例" aria-valuenow={percent} max={100} value={percent}/><p>已处理 {p?.completed||0} / {p?.expected||6} 类研究 · 已用时 {elapsed!=null?duration(elapsed):'本次开始时间尚未记录'}</p>
    <p>预计剩余：{p?.eta_seconds?`约${Math.max(1,Math.ceil(p.eta_seconds[0]/60))}–${Math.max(1,Math.ceil(p.eta_seconds[1]/60))}分钟（按${p.eta_samples||0}个已完成阶段耗时估算，可能延长）`:p?.estimate_overrun?'当前阶段已超过先前估算，剩余暂无法估算':p?.phase==='saving'?'正在保存结果':p?.phase==='validating'?'正在校验区间与策略':'暂无法估算；有实际阶段耗时后显示范围'}</p>
    <ol aria-label="研究阶段"><li>{result?.status==='preparing'?'进行中':'已取得'} · 研究资料</li>{steps.map(s=><li key={s.role}>{statusName[s.status]||s.status} · {s.label}{s.duration_seconds!=null?` · ${duration(s.duration_seconds)}`:''}</li>)}<li>{p?.phase==='validating'?'进行中':p?.phase==='saving'?'已完成':'待处理'} · 价位校验</li><li>{p?.phase==='saving'?'进行中':'待处理'} · 保存结果</li></ol>
    <small>百分比表示阶段完成比例，不能反映单个模型的内部推理进度；不要重复点击生成。</small></>}
   {completed&&outcome.priceFailed&&<p role="alert">{outcome.missingReason}</p>}
   {completed&&outcome.failedRoles.length>0&&<ul aria-label="失败研究环节">{outcome.failedRoles.map(r=><li key={r.role}>{r.label||r.role}：{r.message?.includes('CalledProcessError')?'模型请求失败；旧记录未保留服务商具体错误。':r.message||'模型请求失败，未取得该阶段结果。'}</li>)}</ul>}
   {completed&&report?.timing&&<p>本次研究用时 {duration(report.timing.elapsed_seconds)} · 模型调用 {report.calls} 次</p>}
  </div>}
  <div role="region" aria-label="未来情景预测区间" className="am-forecast-strip"><strong>未来{horizon}交易日情景区间 · 不复权参考 {stale?'· 历史研究，仅供对照':working&&report?'· 上次已保存情景，本次生成中':report?'· 研究估计，尚未校准':''}</strong>
   <div>{(['bear','base','bull'] as const).map(kind=>{const f=forecasts.find(f=>f.scenario===kind);return <article key={kind}><span>{{bear:'偏弱',base:'基准',bull:'偏强'}[kind]}</span><b>{f?`${money(f.low)} – ${money(f.high)}`:'未提供'}</b></article>;})}</div>
   {!working&&outcome.missingReason&&<p className="as-footnote">{outcome.missingReason}</p>}
   {report?.rejections?.filter(r=>r.kind==='forecast'&&r.horizon===horizon).map((r,i)=><p className="as-footnote" key={i}>本期限有区间未通过校验：{r.reason}。保留其余有效结果，不补造缺失区间。</p>)}
   {report&&!!forecasts.length&&!overlayMatched&&<p className="am-integrated-warning">{stale?'资料已更新，旧区间暂不叠加到当前K线；历史数值仍在此保留。新研究完成并匹配行情后恢复图层。':'图表的期间、价格来源或复权版本尚未匹配研究，区间暂不叠加；数值结果仍保留。'}</p>}
   {!report&&!loading&&<p className="as-footnote">尚无已保存的综合预测。准备资料并生成后，区间与策略会一同显示。</p>}
  </div>
 </section>;
}
