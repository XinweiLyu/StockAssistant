import { useEffect,useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { MarketJobs } from '../../types/aShareMarket';
export default function MarketSyncStatus(){
  const [jobs,setJobs]=useState<MarketJobs>(),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{let live=true;const load=async()=>{try{const r=await aShareMarketApi.jobs();if(live)setJobs(r);}catch(e){if(live)setError(e instanceof Error?e.message:'任务状态未取得');}};void load();const t=setInterval(()=>void load(),10000);return ()=>{live=false;clearInterval(t);};},[]);
  const act=async(fn:()=>Promise<unknown>)=>{setBusy(true);try{await fn();setJobs(await aShareMarketApi.jobs());setError('');}catch(e){setError(e instanceof Error?e.message:'请求未完成');}finally{setBusy(false);}};
  const c=jobs?.coverage;
  return <div className="am-sync"><div><strong>全市场资料准备</strong><p>{c?`目录 ${c.catalog_total} · 有效 ${c.valid} · 已排除 ${c.excluded} · 身份待核实 ${c.unverified} · 失败 ${c.failed} · 待检查 ${c.pending}`:'查询覆盖情况…'}</p><p className="as-footnote">{c?.state==='complete'?'当前目录规则输入覆盖完整':c?.state==='complete_with_gaps'?'全目录检查结束但有缺失':c?.state==='not_started'?'尚未开始全目录研究':'逐步准备中'} · 截止 {c?.as_of||'待确认'} · {jobs?.paused?'批量研究已暂停':'后台队列运行中'}</p></div><div className="as-actions"><button className="am-button" disabled={busy} onClick={()=>void act(aShareMarketApi.warmup)}>准备全市场研究</button><button className="am-button" disabled={busy} onClick={()=>void act(jobs?.paused?aShareMarketApi.resume:aShareMarketApi.pause)}>{jobs?.paused?'继续批量准备':'暂停批量准备'}</button></div>{error&&<p role="alert">{error}</p>}{jobs?.tasks?.some(t=>t.state==='failed')&&<details><summary>查看近期失败任务</summary>{jobs.tasks.filter(t=>t.state==='failed').map(t=><p className="as-footnote" key={t.id}>{t.kind} · {t.error||'未取得数据'}</p>)}</details>}</div>;
}
