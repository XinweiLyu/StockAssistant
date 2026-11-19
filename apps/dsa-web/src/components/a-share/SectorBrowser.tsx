import {flowMoney} from './sectorFundFlowData';
import type {SectorFlowRank} from '../../types/aShareSectorFlow';
import {useMarketPresentation} from './MarketContext';
import { useEffect,useRef,useState } from 'react';
import type { Sector } from '../../types/aShareMarket';
import { aShareMarketApi } from '../../api/aShareMarket';
import SectorHeatmap from './SectorHeatmap';
export default function SectorBrowser({onSelectSector,selectedSectorId}:{onSelectSector:(s:Sector)=>void;selectedSectorId?:string}){
  const {market}=useMarketPresentation();
  const [kind,setKind]=useState<'industry'|'concept'>('industry'),[period,setPeriod]=useState(0),[view,setView]=useState('heat'),[q,setQ]=useState(''),[page,setPage]=useState(1);
  const [result,setResult]=useState<{key:string;items:Sector[];classification:string;error?:string;checkedAt?:number}>({key:'',items:[],classification:''});
  const [metric,setMetric]=useState('change');
  const [flow,setFlow]=useState<{key:string;value?:SectorFlowRank;error?:string}>({key:''});
  const flowKey=market+':'+kind;
  const lastChecked=useRef(0);
  useEffect(()=>{
    if(metric==='change'||market!=='cn')return;
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let busy=false;
    const load=async()=>{if(busy||controller.signal.aborted||document.visibilityState==='hidden')return;busy=true;let delay=300000;if(timer)clearTimeout(timer);try{const value=await aShareMarketApi.fundFlowRank(kind,controller.signal);if(!controller.signal.aborted)setFlow({key:flowKey,value});if(value.poll_pending??(value.task_id&&value.health.status!=='failed'))delay=5000;}catch(e){if(!controller.signal.aborted)setFlow(p=>({...((p.key===flowKey?p:undefined)||{key:flowKey}),error:e instanceof Error?e.message:'资金排行暂未取得'}));delay=30000;}finally{busy=false;if(!controller.signal.aborted)timer=setTimeout(()=>void load(),delay);}};
    const visible=()=>{if(document.visibilityState==='visible')void load();};document.addEventListener('visibilitychange',visible);void load();return()=>{controller.abort();if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',visible);};
  },[metric,market,kind,flowKey]);
  const key=market+':'+kind+':'+period;
  useEffect(()=>{
    lastChecked.current=Date.now();
    const controller=new AbortController();
    let busy=false;
    const load=async()=>{
      if(busy)return;
      busy=true;
      try{
        const response=await aShareMarketApi.sectors({kind,period,...(market!=='cn'?{market}:{})},controller.signal);
        if(!controller.signal.aborted){
          lastChecked.current=Date.now();
          setResult({key,items:response.items||[],classification:response.classification,checkedAt:lastChecked.current});
        }
      }catch(error){
        if(!controller.signal.aborted){
          lastChecked.current=Date.now();
          const message=error instanceof Error?error.message:'板块资料未取得';
          setResult(previous=>previous.key===key
            ? {...previous,error:message,checkedAt:lastChecked.current}
            : {key,items:[],classification:'',error:message,checkedAt:lastChecked.current});
        }
      }finally{busy=false;}
    };
    void load();
    const timer=setInterval(()=>{if(document.visibilityState==='visible')void load();},5*60*1000);
    const onVisible=()=>{if(document.visibilityState==='visible'&&Date.now()-lastChecked.current>=5*60*1000)void load();};
    document.addEventListener('visibilitychange',onVisible);
    return ()=>{controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',onVisible);};
  },[kind,period,key,market]);
  const flowRows=new Map((flow.key===flowKey?flow.value?.items||[]:[]).map(r=>[r.sector_id,r]));
  const effectiveMetric=market==='cn'?metric:'change';
  const metricValue=(s:Sector)=>effectiveMetric==='change'?s.change:effectiveMetric==='main_net'?flowRows.get(s.sector_id)?.values.main:flowRows.get(s.sector_id)?.ratios?.main;
  const formatValue=(n:number)=>effectiveMetric==='main_net'?flowMoney(n):`${(n*100).toFixed(2)}%`;
  const all=result.key===key?result.items.filter(s=>!q||s.name.includes(q)||s.code.includes(q)):[];
  if(effectiveMetric!=='change')all.sort((a,b)=>{const av=metricValue(a),bv=metricValue(b);return av==null?(bv==null?0:1):bv==null?-1:bv-av;});
  const items=all.slice((page-1)*24,page*24),extent=Math.max(.01,...items.map(s=>Math.abs(metricValue(s)??0)));
  return <section className="am-sector-browser" aria-label="板块行情"><div className="as-section-heading"><div><h2>行业与概念板块</h2><p>{market==='cn'?'源公布指数 · 各分类独立比较 · 概念成员可能重叠':'已核实公司所属行业 · 成员覆盖逐步增加 · 尚无独立行业指数涨跌'}</p></div><div className="am-toolbar"><select disabled={market!=='cn'} aria-label="板块类型" value={kind} onChange={e=>{setKind(e.target.value as 'industry'|'concept');setPage(1);setQ('');}}><option value="industry">行业</option><option value="concept">概念</option></select><select disabled={market!=='cn'||metric!=='change'} aria-label="板块区间" value={period} onChange={e=>{setPeriod(Number(e.target.value));setPage(1);}}><option value={0}>源公布快照</option><option value={5}>5交易日</option><option value={20}>20交易日</option><option value={60}>60交易日</option></select><select disabled={market!=='cn'} aria-label="板块排序指标" value={metric} onChange={e=>{setMetric(e.target.value);setPeriod(0);setPage(1);}}><option value="change">涨跌幅</option><option value="main_net">主力净流入</option><option value="main_ratio">主力净占比</option></select><select aria-label="板块展示" value={view} onChange={e=>setView(e.target.value)}><option value="heat">热力图</option><option value="rank">排行 / 正负条形图</option></select><input aria-label="搜索板块" placeholder="搜索板块" value={q} onChange={e=>{setQ(e.target.value);setPage(1);}}/></div></div>
    <p className="as-footnote">{result.key===key?result.classification:'加载中'} · {period?`截止 ${items[0]?.history_as_of||'待补齐'}`:`来源时间 ${items[0]?.source_time||'未知，快照不视作已核实今日涨跌'}`} · 获取 {items[0]?.fetched_at||'—'} · 页面每 5 分钟自动检查{result.key===key&&result.checkedAt?`（最近 ${new Date(result.checkedAt).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'})}）`:''}</p>
    {result.key===key&&result.error&&<p role="alert">{result.error}；已有板块仍显示上次成功获取的缓存。</p>}
    {effectiveMetric!=='change'&&<p className="as-footnote">资金累计快照 · 获取 {flow.key===flowKey?flow.value?.observed_at||'待获取':'待获取'} · 来源交易日期未知；概念重叠不能汇总为市场资金总额。{flow.key===flowKey&&(flow.error||flow.value?.health.error)}</p>}
    {view==='heat'?<SectorHeatmap items={items} onSelect={onSelectSector} selectedSectorId={selectedSectorId} getValue={metricValue} format={formatValue}/>:<div className="am-sector-ranking">{items.map((s,i)=><button key={s.sector_id} aria-pressed={s.sector_id===selectedSectorId} onClick={()=>onSelectSector(s)}><span>{(page-1)*24+i+1}. {s.name}</span><div className="am-diverging"><i className="am-zero"/>{metricValue(s)!=null&&<i style={{left:metricValue(s)!>=0?'50%':`${50-Math.abs(metricValue(s)!)/extent*50}%`,width:`${Math.abs(metricValue(s)!)/extent*50}%`,background:metricValue(s)!>=0?'#e45c65':'#38b990'}}/>}</div><strong>{metricValue(s)==null?(market==='cn'?'资料不足':'查看成员'):formatValue(metricValue(s)!)}</strong></button>)}</div>}
    {!all.length&&<p className="as-footnote">板块资料尚未就绪。数据源失败时会保留未知，不填造涨跌。</p>}<div className="am-pagination"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil(all.length/24))} · {all.length} 个板块</span><button disabled={page*24>=all.length} onClick={()=>setPage(p=>p+1)}>下一页</button></div>
  </section>;
}
