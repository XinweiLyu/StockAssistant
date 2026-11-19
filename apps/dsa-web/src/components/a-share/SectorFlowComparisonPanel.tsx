import {useEffect,useRef,useState} from 'react';
import {aShareMarketApi} from '../../api/aShareMarket';
import type {Sector} from '../../types/aShareMarket';
import type {FlowCategory,SectorFlowComparison} from '../../types/aShareSectorFlow';
import {useMarketPresentation} from './MarketContext';
import {FLOW_NAMES} from './sectorFundFlowData';
import {COMPARISON_COLORS,comparisonRows,comparisonValue,comparisonFormat,type ComparisonMetric} from './sectorFlowComparisonData';
import SectorFlowComparisonChart from './SectorFlowComparisonChart';
type Kind='industry'|'concept';
const selectionKey=(k:Kind)=>'assistant-flow-comparison:'+k;
function readSelections(){const out:Partial<Record<Kind,string[]>>={};for(const k of ['industry','concept'] as const)try{const a=JSON.parse(localStorage.getItem(selectionKey(k))||'null');if(Array.isArray(a)&&a.every(s=>typeof s==='string'))out[k]=[...new Set(a)].slice(0,8);}catch{/* Ignore invalid local preferences. */}return out;}
export default function SectorFlowComparisonPanel({onSelectSector}:{onSelectSector:(s:Sector)=>void}){
 const {market}=useMarketPresentation();const enabled=market==='cn';
 const [kind,setKind]=useState<Kind>('industry'),[q,setQ]=useState(''),[category,setCategory]=useState<FlowCategory>('main'),[metric,setMetric]=useState<ComparisonMetric>('amount');
 const [selected,setSelected]=useState(readSelections),[catalog,setCatalog]=useState<{key:string;items:Sector[];error?:string}>({key:'',items:[]});
 const [saved,setSaved]=useState<{key:string;value?:SectorFlowComparison;error?:string;loading?:boolean}>({key:''});
 const [manual,setManual]=useState(0),[cursor,setCursor]=useState<number|undefined>();const nextForce=useRef(false);
 const boards=catalog.key===kind?catalog.items:[],valid=new Set(boards.map(b=>b.sector_id));
 const ids=(selected[kind]||[]).filter(i=>valid.has(i));const idKey=ids.join(','),key=market+':'+kind+':'+idKey;
 useEffect(()=>{
  if(!enabled)return;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let busy=false;
  const load=async()=>{if(busy||controller.signal.aborted||document.visibilityState==='hidden')return;busy=true;if(timer)clearTimeout(timer);let delay=300000;
   try{const v=await aShareMarketApi.sectors({kind,period:0},controller.signal);if(controller.signal.aborted)return;
    if(!Array.isArray(v.items))throw new Error('板块目录结构不完整');
    const items=v.items.filter(b=>b.kind===kind&&b.classification==='eastmoney-'+kind&&new RegExp('^em:'+kind+':BK\\d{4}$').test(b.sector_id));
    if(items.length){setCatalog({key:kind,items});setSelected(prev=>{const saved=prev[kind],available=new Set(items.map(b=>b.sector_id)),choice=saved!==undefined?saved.filter(i=>available.has(i)):items.slice(0,6).map(b=>b.sector_id);return saved?.join(',')===choice.join(',')?prev:{...prev,[kind]:choice};});}
    else{delay=v.items.length?300000:5000;setCatalog(prev=>prev.key===kind&&prev.items.length?{...prev,error:'目录正在补齐，保留已获取选项'}:{key:kind,items:[],error:v.items.length?'此目录暂无可用东财板块':'目录正在补齐，完成后自动显示'});}
   }catch(e){if(!controller.signal.aborted)setCatalog(prev=>({...((prev.key===kind?prev:undefined)||{key:kind,items:[]}),error:e instanceof Error?e.message:'板块目录未取得'}));delay=30000;}
   finally{busy=false;if(!controller.signal.aborted)timer=setTimeout(()=>void load(),delay);}};
  const visible=()=>{if(document.visibilityState==='visible')void load();};document.addEventListener('visibilitychange',visible);void load();
  return()=>{controller.abort();if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',visible);};
 },[enabled,kind]);
 useEffect(()=>{if(!enabled||selected[kind]===undefined)return;try{localStorage.setItem(selectionKey(kind),JSON.stringify(selected[kind]));}catch{/* Keep memory-only preferences when storage is unavailable. */}},[enabled,kind,selected]);

 useEffect(()=>{
  if(!enabled||!idKey)return;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let busy=false;let force=nextForce.current;nextForce.current=false;
  const load=async()=>{if(busy||controller.signal.aborted||document.visibilityState==='hidden')return;busy=true;if(timer)clearTimeout(timer);let delay=300000;
   setSaved(p=>({...((p.key===key?p:undefined)||{key}),loading:true}));
   try{const v=await aShareMarketApi.fundFlowComparison(kind,idKey.split(','),controller.signal,force);force=false;if(controller.signal.aborted)return;
    if(v.kind!==kind||!Array.isArray(v.series)||v.series.length!==idKey.split(',').length||new Set(v.series.map(s=>s.sector?.sector_id)).size!==v.series.length||v.series.some(s=>!idKey.split(',').includes(s.sector?.sector_id)||!Array.isArray(s.points)))throw new Error('板块资金身份或资料结构不匹配');
    setSaved({key,value:v,loading:false});if(v.poll_pending)delay=5000;
   }catch(e){if(!controller.signal.aborted)setSaved(p=>({...((p.key===key?p:undefined)||{key}),loading:false,error:e instanceof Error?e.message:'资金来源暂不可用'}));delay=30000;}
   finally{busy=false;if(!controller.signal.aborted)timer=setTimeout(()=>void load(),delay);}};
  const visible=()=>{if(document.visibilityState==='visible')void load();};document.addEventListener('visibilitychange',visible);timer=setTimeout(()=>void load(),200);
  return()=>{controller.abort();if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',visible);};
 },[enabled,kind,idKey,key,manual]);
 const value=saved.key===key?saved.value:undefined,error=saved.key===key?saved.error:undefined;
 const series=ids.flatMap(id=>value?.series.find(s=>s.sector.sector_id===id)||[]),rows=comparisonRows(series,value?.day||''),last=rows.reduce((prev,r,i)=>Object.keys(r.cells).length?i:prev,0),index=Math.min(cursor??last,rows.length-1),focus=rows[index];
 const anyPoints=rows.some(r=>ids.some(id=>comparisonValue(r.cells[id],category,metric)!==null)),anyObservations=rows.some(r=>Object.keys(r.cells).length>0);
 const changeSelection=(id:string,checked:boolean)=>{const next=checked?[...ids,id].slice(0,8):ids.filter(i=>i!==id);setSelected(p=>({...p,[kind]:next}));setCursor(undefined);};
 if(!enabled)return <p className="as-footnote">多板块资金曲线目前仅支持A股；港美股不使用成交额替代资金净额。</p>;
 return <section className="am-flow-comparison" aria-label="多板块资金动态总览"><div className="as-section-heading"><div><p className="as-eyebrow">资金去向 · 多板块同图对比</p><h2>今日资金流入变化</h2><p>每条线代表一个板块，共用时间轴和零基线；默认关注6个，最多同时8个。</p></div><div className="am-toolbar"><select aria-label="对比板块类型" value={kind} onChange={e=>{setKind(e.target.value as Kind);setQ('');setCursor(undefined);}}><option value="industry">行业</option><option value="concept">概念</option></select><select aria-label="对比资金类别" value={category} onChange={e=>setCategory(e.target.value as FlowCategory)}>{(Object.keys(FLOW_NAMES) as FlowCategory[]).map(k=><option key={k} value={k}>{FLOW_NAMES[k]}</option>)}</select><select aria-label="对比度量" value={metric} onChange={e=>setMetric(e.target.value as ComparisonMetric)}><option value="amount">累计净流入金额</option><option value="ratio">资金净占比</option></select><button className="am-button" disabled={!ids.length||saved.key===key&&saved.loading} onClick={()=>{nextForce.current=true;setManual(n=>n+1);}}>刷新对比资金</button></div></div>
 <div className="am-compare-layout"><aside className="am-compare-picker"><input aria-label="搜索对比板块" placeholder="搜索并勾选板块" value={q} onChange={e=>setQ(e.target.value)}/><p className="as-footnote">已选 {ids.length}/8 · 行业/概念分别选择</p><div className="am-compare-options">{boards.filter(b=>!q||b.name.includes(q)||b.code.includes(q)).map(b=><label key={b.sector_id}><input type="checkbox" aria-label={'对比'+b.name} checked={ids.includes(b.sector_id)} disabled={!ids.includes(b.sector_id)&&ids.length>=8} onChange={e=>changeSelection(b.sector_id,e.target.checked)}/>{b.name}</label>)}</div>{catalog.error&&<p className="as-footnote">{catalog.error}</p>}</aside><div className="am-compare-main"><div className="am-compare-legend">{ids.map((id,i)=><span key={id}><i style={{background:COMPARISON_COLORS[i]}}/>{boards.find(b=>b.sector_id===id)?.name}</span>)}</div>
 <p className="as-footnote am-compare-provenance" role="status">{value?.day||'今天'} · 今日采样，源交易日期未核实 · 可见页面每5分钟更新<br/>{!ids.length?'请先勾选要比较的板块':saved.key!==key||saved.loading?'正在查询资金采样…':value?.poll_pending?'后台获取中，完成后自动更新':value?.health.status==='failed'?'资金源暂不可用；保留已取得采样，缺失不补值':!value?.active?'当前非连续交易时段，暂停自动采样':'交易时段持续采样'}{error&&' · '+error}</p>
 {anyPoints?<SectorFlowComparisonChart rows={rows} series={series} category={category} metric={metric} selectedIndex={index} onSelectIndex={setCursor}/>:<div className="am-flow-empty">{anyObservations?'当前资金类别尚无可绘制值，可切换类别查看。':'今天尚无采样记录；交易时段每5分钟积累多个板块的观测。'}<br/>采集成功后，多条曲线会出现在这里；不使用昨日或日线数据替代。</div>}
 <div className="as-table-wrap"><table className="as-table" aria-label="板块资金同步对比"><thead><tr><th>板块</th><th>{focus?.label}采样窗</th><th>最近采样值</th><th>最近观测</th></tr></thead><tbody>{ids.map((id,i)=>{const s=series.find(s=>s.sector.sector_id===id),b=boards.find(b=>b.sector_id===id);return <tr key={id}><td><button className="as-stock" aria-label={'查看资金板块'+b?.name} onClick={()=>b&&onSelectSector(b)}><i className="am-compare-dot" style={{background:COMPARISON_COLORS[i]}}/>{b?.name}</button></td><td>{comparisonFormat(comparisonValue(focus?.cells[id],category,metric),metric)}</td><td>{comparisonFormat(comparisonValue(s?.latest,category,metric),metric)}</td><td>{s?.latest?.observed_at?new Date(s.latest.observed_at).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai'}):'未取得'}</td></tr>;})}</tbody></table></div>
 <p className="as-footnote">来源 {value?.source||'eastmoney/sector-flow'} · {metric==='amount'?'人民币亿元':'来源净占比'} · 图表只显示实际采样点，缺口与午休断线；光标窗口缺失不沿用上一条值。<br/>主力已包含超大单和大单；板块曲线独立对比，概念成员可能重叠，不汇总为全市场流入。</p>
 </div></div></section>;
}
