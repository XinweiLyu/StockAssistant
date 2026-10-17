import { useEffect,useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { HistoryPage,Sector,SectorMembersPage } from '../../types/aShareMarket';
import PriceChart from './PriceChart';
import SectorComparisonChart from './SectorComparisonChart';

const money=(value:number|null|undefined)=>value==null||!Number.isFinite(value)?'—':value.toFixed(2);
export default function SectorDetail({sector,onSelectStock,onClose,stockCode}:{sector:Sector;onSelectStock:(code:string)=>void;onClose:()=>void;stockCode?:string}){
  const [page,setPage]=useState(1),[q,setQ]=useState(''),[sort,setSort]=useState('change'),[retry,setRetry]=useState(0);
  const [saved,setSaved]=useState<{key:string;members?:SectorMembersPage;error?:string}>({key:''});
  const [comparisonOpen,setComparisonOpen]=useState(false);
  const [comparison,setComparison]=useState<{key:string;history?:HistoryPage;benchmark?:HistoryPage;stock?:HistoryPage;error?:string}>({key:''});
  const key=JSON.stringify([sector.sector_id,page,q,sort]);
  useEffect(()=>{
    const controller=new AbortController();
    let timer:ReturnType<typeof setTimeout>|undefined;
    const load=async()=>{
      try{
        const members=await aShareMarketApi.members(sector.sector_id,{page,page_size:20,q,sort,direction:sort==='code'||sort==='name'?'asc':'desc'},controller.signal);
        if(controller.signal.aborted)return;
        setSaved({key,members});
        timer=setTimeout(()=>void load(),members.membership.state==='pending'?5000:5*60*1000);
      }catch(error){
        if(!controller.signal.aborted)setSaved(previous=>({...(previous.key===key?previous:{key}),error:error instanceof Error?error.message:'板块成员未取得'}));
      }
    };
    void load();
    return ()=>{controller.abort();if(timer)clearTimeout(timer);};
  },[sector.sector_id,page,q,sort,key,retry]);

  // Comparison history is optional and must not block a usable member list.
  const comparisonKey=sector.sector_id+':'+stockCode;
  useEffect(()=>{
    if(!comparisonOpen)return;
    const controller=new AbortController();
    let timer:ReturnType<typeof setTimeout>|undefined;
    const end=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date());
    const start=new Date(Date.parse(end)-365*86400000).toISOString().slice(0,10);
    const load=async()=>{
      const [history,benchmark,stock]=await Promise.allSettled([
        aShareMarketApi.sectorHistory(sector.sector_id,start,end,controller.signal),
        aShareMarketApi.benchmarkHistory(start,end,controller.signal),
        stockCode?aShareMarketApi.history(stockCode,start,end,'qfq',controller.signal):Promise.resolve(undefined),
      ]);
      if(controller.signal.aborted)return;
      const value={key:comparisonKey,history:history.status==='fulfilled'?history.value:undefined,benchmark:benchmark.status==='fulfilled'?benchmark.value:undefined,stock:stock.status==='fulfilled'?stock.value:undefined,
        error:[history,benchmark,stock].some(item=>item.status==='rejected')?'部分对比历史未取得；已取得的资料仍可查看。':undefined};
      setComparison(value);
      if([value.history,value.benchmark,value.stock].some(item=>item?.state==='pending'))timer=setTimeout(()=>void load(),5000);
    };
    void load();
    return ()=>{controller.abort();if(timer)clearTimeout(timer);};
  },[sector.sector_id,stockCode,comparisonKey,comparisonOpen]);
  const value=saved.key===key?saved:undefined,plots=comparison.key===comparisonKey?comparison:undefined;
  const membershipVersion=value?.members?.membership.version??sector.membership_version;
  const breadth=membershipVersion&&membershipVersion===sector.membership_version?sector.member_breadth:undefined;
  const pending=!value?.members||value.members.membership.state==='pending';
  const total=value?.members?.total||0,pages=Math.max(1,Math.ceil(total/20));
  return <section className="am-sector-detail" aria-label="板块详情">
    <div className="as-section-heading"><div><h2>{sector.name} · {sector.kind==='industry'?'行业':'概念'}</h2><p>{sector.classification} · {sector.source}<br/>板块获取 {sector.fetched_at}</p></div><button className="am-button" onClick={onClose}>关闭板块详情</button></div>
    <div className="am-sector-summary"><strong className={sector.change==null?'':sector.change>=0?'am-up':'am-down'}>{sector.change==null?'涨跌资料不足':`${sector.change>0?'+':''}${(sector.change*100).toFixed(2)}%`}</strong><span>源公布快照 · 点击下方股票查看 K 线</span></div>
    <p className="as-footnote">已获取成员 {!pending?(value?.members?.membership.codes.length??total):'待补齐'} 家 · 本地报价覆盖 {breadth?breadth.total-breadth.unknown:'未知'} 家 · 上涨 {breadth?.up??'未知'} / 下跌 {breadth?.down??'未知'} / 平盘 {breadth?.flat??'未知'} / 报价未知 {breadth?.unknown??'未知'}<br/>成员版本 {membershipVersion||'待补齐'}；报价覆盖计数不等于源公布指数涨跌。</p>
    <div className="am-toolbar am-member-toolbar"><input aria-label="搜索板块成分股" placeholder="代码或股票名称" value={q} onChange={event=>{setQ(event.target.value);setPage(1);}}/><select aria-label="成分股排序" value={sort} onChange={event=>{setSort(event.target.value);setPage(1);}}><option value="change">涨跌幅</option><option value="amount">成交额</option><option value="code">代码</option><option value="name">名称</option></select></div>
    {pending&&!value?.error&&<p className="as-footnote" role="status">正在获取板块成分股，完成后自动展示…</p>}
    {value?.error&&<p role="alert">{value.error}；保留已取得的成员资料。<button className="am-button" onClick={()=>setRetry(v=>v+1)}>重试成分股</button></p>}
    <div className="as-table-wrap am-member-table"><table className="as-table" aria-label="板块成分股"><thead><tr><th>股票 / 代码</th><th>最新价</th><th>涨跌幅</th></tr></thead><tbody>{value?.members?.items?.map(stock=><tr key={stock.code}><td><button className="as-stock" aria-label={`查看${stock.name} ${stock.code}`} onClick={()=>onSelectStock(stock.code)}>{stock.name}<span>{stock.code}</span></button></td><td>{money(stock.quote?.price)}</td><td className={stock.quote?.change==null?'':stock.quote.change>=0?'am-up':'am-down'}>{stock.quote?.change==null?'—':`${stock.quote.change>0?'+':''}${(stock.quote.change*100).toFixed(2)}%`}</td></tr>)}</tbody></table></div>
    {!pending&&!total&&!value?.error&&<p className="as-footnote">当前条件没有已获取的成分股，可更换搜索条件；未填造股票或行情。</p>}
    <div className="am-pagination"><button disabled={page<=1} onClick={()=>setPage(p=>p-1)}>上一页成分股</button><span>{page} / {pages} · {total} 只</span><button disabled={pending||page*20>=total} onClick={()=>setPage(p=>p+1)}>下一页成分股</button></div>
    <p className="as-footnote">成员报价可能来自不同时间的缓存；进入个股后可手动刷新最新行情。</p>
    <details onToggle={event=>setComparisonOpen(event.currentTarget.open)}><summary>板块历史与沪深300 / 所选股票对比</summary>{comparisonOpen&&<>
      {plots?.error&&<p role="alert">{plots.error}</p>}<p className="as-footnote">源公布指数 · 实际截止 {plots?.history?.actual_end||'待取得'} · {plots?.history?.state||'查询中'}</p>
      <PriceChart items={plots?.history?.items||[]} chartType="line" indicators={{MA20:true}} levels={[]}/><SectorComparisonChart sector={plots?.history?.items||[]} benchmark={plots?.benchmark?.items||[]} stock={plots?.stock?.items}/>
    </>}</details>
  </section>;
}
