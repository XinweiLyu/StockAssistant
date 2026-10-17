import { useEffect,useRef,useState } from 'react';
import type { Sector } from '../../types/aShareMarket';
import { aShareMarketApi } from '../../api/aShareMarket';
import SectorHeatmap from './SectorHeatmap';
export default function SectorBrowser({onSelectSector,selectedSectorId}:{onSelectSector:(s:Sector)=>void;selectedSectorId?:string}){
  const [kind,setKind]=useState<'industry'|'concept'>('industry'),[period,setPeriod]=useState(0),[view,setView]=useState('heat'),[q,setQ]=useState(''),[page,setPage]=useState(1);
  const [result,setResult]=useState<{key:string;items:Sector[];classification:string;error?:string;checkedAt?:number}>({key:'',items:[],classification:''});
  const lastChecked=useRef(0);
  const key=kind+':'+period;
  useEffect(()=>{
    lastChecked.current=Date.now();
    const controller=new AbortController();
    let busy=false;
    const load=async()=>{
      if(busy)return;
      busy=true;
      try{
        const response=await aShareMarketApi.sectors({kind,period},controller.signal);
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
  },[kind,period,key]);
  const all=result.key===key?result.items.filter(s=>!q||s.name.includes(q)||s.code.includes(q)):[],items=all.slice((page-1)*24,page*24),extent=Math.max(.01,...items.map(s=>Math.abs(s.change??0)));
  return <section className="am-sector-browser" aria-label="板块行情"><div className="as-section-heading"><div><h2>行业与概念板块</h2><p>源公布指数 · 各分类独立比较 · 概念成员可能重叠</p></div><div className="am-toolbar"><select aria-label="板块类型" value={kind} onChange={e=>{setKind(e.target.value as 'industry'|'concept');setPage(1);setQ('');}}><option value="industry">行业</option><option value="concept">概念</option></select><select aria-label="板块区间" value={period} onChange={e=>{setPeriod(Number(e.target.value));setPage(1);}}><option value={0}>源公布快照</option><option value={5}>5交易日</option><option value={20}>20交易日</option><option value={60}>60交易日</option></select><select aria-label="板块展示" value={view} onChange={e=>setView(e.target.value)}><option value="heat">热力图</option><option value="rank">排行 / 正负条形图</option></select><input aria-label="搜索板块" placeholder="搜索板块" value={q} onChange={e=>{setQ(e.target.value);setPage(1);}}/></div></div>
    <p className="as-footnote">{result.key===key?result.classification:'加载中'} · {period?`截止 ${items[0]?.history_as_of||'待补齐'}`:`来源时间 ${items[0]?.source_time||'未知，快照不视作已核实今日涨跌'}`} · 获取 {items[0]?.fetched_at||'—'} · 页面每 5 分钟自动检查{result.key===key&&result.checkedAt?`（最近 ${new Date(result.checkedAt).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'})}）`:''}</p>
    {result.key===key&&result.error&&<p role="alert">{result.error}；已有板块仍显示上次成功获取的缓存。</p>}
    {view==='heat'?<SectorHeatmap items={items} onSelect={onSelectSector} selectedSectorId={selectedSectorId}/>:<div className="am-sector-ranking">{items.map((s,i)=><button key={s.sector_id} aria-pressed={s.sector_id===selectedSectorId} onClick={()=>onSelectSector(s)}><span>{(page-1)*24+i+1}. {s.name}</span><div className="am-diverging"><i className="am-zero"/>{s.change!=null&&<i style={{left:s.change>=0?'50%':`${50-Math.abs(s.change)/extent*50}%`,width:`${Math.abs(s.change)/extent*50}%`,background:s.change>=0?'#e45c65':'#38b990'}}/>}</div><strong>{s.change==null?'资料不足':`${(s.change*100).toFixed(2)}%`}</strong></button>)}</div>}
    {!all.length&&<p className="as-footnote">板块资料尚未就绪。数据源失败时会保留未知，不填造涨跌。</p>}<div className="am-pagination"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil(all.length/24))} · {all.length} 个板块</span><button disabled={page*24>=all.length} onClick={()=>setPage(p=>p+1)}>下一页</button></div>
  </section>;
}
