import SectorFlowComparisonPanel from './SectorFlowComparisonPanel';
import type {ComponentProps} from 'react';
import MarketSelector from './MarketSelector';
import {MarketContext} from './MarketContext';
import {codeMarket,workspaceWatchlist,type WorkspaceMarket} from '../../api/marketWorkspace';
import { useCallback,useEffect,useRef,useState } from 'react';
import type { AssistantBoard } from '../../types/aShare';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { Sector } from '../../types/aShareMarket';
import MarketStockBrowser from './MarketStockBrowser';
import MarketSyncStatus from './MarketSyncStatus';
import StockDetail from './StockDetail';
import SectorBrowser from './SectorBrowser';
import SectorDetail from './SectorDetail';
function InvestmentWorkspaceContent({market='cn',board,selectedCode,selectedStrategy,navigationRevision=0,onSelectStock,onWatchlist,onResearch}:{market?:WorkspaceMarket;board:AssistantBoard;selectedCode:string;selectedStrategy?:string;navigationRevision?:number;onSelectStock:(code:string)=>void;onWatchlist:(code:string)=>void;onResearch:(code:string)=>void}){
  const restoreSector=(kind:string):Sector|undefined=>{try{const saved=JSON.parse(localStorage.getItem('assistant-sector-'+market+'-'+kind)||'null') as Sector|null;return saved&&saved.kind===kind?saved:undefined;}catch{return undefined;}};
  const [industry,setIndustry]=useState<Sector|undefined>(()=>restoreSector('industry')),[concept,setConcept]=useState<Sector|undefined>(()=>restoreSector('concept')),[sector,setSector]=useState<Sector>();
  useEffect(()=>{try{localStorage.setItem('assistant-sector-'+market+'-industry',JSON.stringify(industry||null));localStorage.setItem('assistant-sector-'+market+'-concept',JSON.stringify(concept||null));}catch{/* Storage is optional. */}},[market,industry,concept]);
  const selectionKey=selectedCode+':'+(selectedStrategy||'')+':'+navigationRevision;
  const [navigation,setNavigation]=useState<{selection:string;view:'stock'|'sector'}>({selection:selectionKey,view:'stock'});
  // Commit the new navigation identity, including repeated candidate clicks.
  // A -> B -> A must not revive A's old board view.
  if(navigation.selection!==selectionKey)setNavigation({selection:selectionKey,view:'stock'});
  const view=navigation.selection===selectionKey?navigation.view:'stock';
  const setView=(next:'stock'|'sector')=>setNavigation({selection:selectionKey,view:next});
  const [browserRevision,setBrowserRevision]=useState(0);
  const [priceReload,setPriceReload]=useState(0);
  const refreshPriceList=useCallback(()=>setPriceReload(value=>value+1),[]);
  const [groups,setGroups]=useState<{industry:Sector[];concept:Sector[]}>({industry:[],concept:[]});
  const [sectorStatus,setSectorStatus]=useState<'loading'|'failed'|'ready'>('loading');
  const refreshSectors=useRef<()=>void>(()=>{});
  useEffect(()=>{
    const controller=new AbortController();
    const latest={industry:[] as Sector[],concept:[] as Sector[]};
    let busy=false;
    let lastChecked=0;
    let timer:ReturnType<typeof setTimeout>|undefined;
    const load=async()=>{
      if(busy||controller.signal.aborted)return;
      if(timer)clearTimeout(timer);
      busy=true;
      try{
        const [industryResult,conceptResult,jobsResult]=await Promise.allSettled([
          aShareMarketApi.sectors({kind:'industry',period:0,...(market!=='cn'?{market}:{})},controller.signal),
          aShareMarketApi.sectors({kind:'concept',period:0,...(market!=='cn'?{market}:{})},controller.signal),
          aShareMarketApi.jobs(market==='cn'?undefined:market),
        ]);
        if(controller.signal.aborted)return;
        if(industryResult.status==='fulfilled'&&industryResult.value.items?.length)latest.industry=industryResult.value.items;
        if(conceptResult.status==='fulfilled'&&conceptResult.value.items?.length)latest.concept=conceptResult.value.items;
        setGroups({...latest});
        const failed=industryResult.status==='rejected'||conceptResult.status==='rejected'||
          (jobsResult.status==='fulfilled'&&jobsResult.value.health?.['health:sector_catalog']?.status==='failed');
        setSectorStatus((market!=='cn'||latest.industry.length&&latest.concept.length)?'ready':failed?'failed':'loading');
        lastChecked=Date.now();
      }finally{
        busy=false;
        if(!controller.signal.aborted)timer=setTimeout(()=>{
          if(document.visibilityState==='visible')void load();
        },latest.industry.length&&latest.concept.length?5*60*1000:30000);
      }
    };
    const onVisible=()=>{
      if(document.visibilityState==='visible'&&Date.now()-lastChecked>=30000)void load();
    };
    refreshSectors.current=()=>{void load();};
    document.addEventListener('visibilitychange',onVisible);
    void load();
    return ()=>{controller.abort();if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',onVisible);};
  },[board.settings.mode,market]);
  const validSelection=market!=='cn'?selectedCode.startsWith(market+':'):board.settings.mode==='demo'?selectedCode.startsWith('DEMO'): /^\d{6}$/.test(selectedCode);
  const code=validSelection?selectedCode:board.report?.candidates[0]?.code||'';
  const candidate=board.report?.candidates.find(c=>c.code===code&&(!validSelection||!selectedStrategy||c.strategy===selectedStrategy)),research=board.research?.find(r=>r.payload.code===code)?.payload;
  const selectSector=(s:Sector)=>setSector(s);
  const clear=()=>{setIndustry(undefined);setConcept(undefined);setSector(undefined);};
  const openMember=(stockCode:string)=>{
    // Enter the selected board's universe, without a previous search, scope or
    // opposite-kind filter silently hiding its constituents.
    setIndustry(sector?.kind==='industry'?sector:undefined);
    setConcept(sector?.kind==='concept'?sector:undefined);
    try{for(const key of ['q','scope','board','sort'])localStorage.removeItem('assistant-filter-'+market+'-'+key);}catch{/* Storage is optional. */}
    setBrowserRevision(value=>value+1);
    onSelectStock(stockCode);
    setView('stock');
  };
  return <div id="am-workspace" className="am-workspace">
    <div className="am-workspace-tabs" role="tablist" aria-label="行情工作区">
      <button id="am-stock-tab" role="tab" aria-selected={view==='stock'} aria-controls="am-stock-panel" onClick={()=>setView('stock')}>个股行情</button>
      <button id="am-sector-tab" role="tab" aria-selected={view==='sector'} aria-controls="am-sector-panel" onClick={()=>setView('sector')}>行业与概念</button>
    </div>
    <div id="am-stock-panel" role="tabpanel" aria-labelledby="am-stock-tab" hidden={view!=='stock'}>
      <div className="am-workspace-grid">
        <MarketStockBrowser key={browserRevision} reloadRevision={priceReload} watchlistSignature={[...board.settings.watchlist].sort().join('|')} selectedCode={code} onSelectStock={onSelectStock} industry={industry} concept={concept} industries={groups.industry} concepts={groups.concept} sectorStatus={sectorStatus} onRefreshSectors={()=>refreshSectors.current()} onSelectIndustry={s=>{setIndustry(s);setSector(s||concept);}} onSelectConcept={s=>{setConcept(s);setSector(s||industry);}} onClearSector={clear}/>
        <div className="am-main">
          {code?<StockDetail key={code} code={code} candidate={candidate} onWatchlist={onWatchlist} onResearch={onResearch} research={research} events={board.events} onPriceRefresh={refreshPriceList} disabled={!board.settings.research_enabled}/>:<div className="as-empty">从左侧搜索或选择股票，即可在此查看 K 线、指标、AI 价位和证据。</div>}
          <p className="as-footnote am-model-budget">手动模型调用：今日 {board.manual_model_usage??0} 次（不限次，按实际用量计费） · 自动研究上限：{board.model_usage??0} / {board.settings.daily_model_calls??0}</p>
        </div>
      </div>
    </div>
    <div id="am-sector-panel" role="tabpanel" aria-labelledby="am-sector-tab" hidden={view!=='sector'}>
      {view==='sector'&&<SectorFlowComparisonPanel onSelectSector={selectSector}/>}
      <div className="am-sector-workspace">
        <SectorBrowser onSelectSector={selectSector} selectedSectorId={sector?.sector_id}/>
        {sector?<SectorDetail key={sector.sector_id} sector={sector} stockCode={code||undefined} onSelectStock={openMember} onClose={()=>setSector(undefined)}/>:<section className="am-sector-placeholder" aria-label="板块成分股"><h2>查看板块成分股</h2><p>从左侧选择行业或概念，即可查看该板块的股票、报价和涨跌幅。</p><p className="as-footnote">点击成分股进入个股 K 线；板块历史与相对走势可按需展开。</p></section>}
      </div>
    </div>
    <details className="am-data-drawer"><summary>数据准备与后台任务</summary><MarketSyncStatus/></details>
  </div>;
}


type WorkspaceProps=ComponentProps<typeof InvestmentWorkspaceContent>&{onMarketChange?:(market:WorkspaceMarket)=>void};
export default function InvestmentWorkspace(props:WorkspaceProps){
 const [market,setMarket]=useState<WorkspaceMarket>(()=>{try{const saved=localStorage.getItem('assistant-market');return props.selectedCode?codeMarket(props.selectedCode):saved==='us'||saved==='hk'?saved:'cn';}catch{return 'cn';}});
 const [selections,setSelections]=useState<Partial<Record<WorkspaceMarket,string>>>(()=>{const saved:Partial<Record<WorkspaceMarket,string>>={};for(const key of ['cn','hk','us'] as const)try{saved[key]=localStorage.getItem('assistant-selection-'+key)||'';}catch{/* storage unavailable */}return saved;});
 const [watchlist,setWatchlist]=useState<string[]>([]),[watchRevision,setWatchRevision]=useState(0),[error,setError]=useState('');
 const [lastNavigation,setLastNavigation]=useState(props.navigationRevision);
 if(props.navigationRevision!==lastNavigation){setLastNavigation(props.navigationRevision);setMarket(codeMarket(props.selectedCode));}
 useEffect(()=>{
  let current=true;
  if(market!=='cn')void workspaceWatchlist.get(market).then(codes=>{if(current)setWatchlist(codes);}).catch(()=>{if(current)setError('自选列表未取得，请稍后重试');});
  return()=>{current=false;};
 },[market,watchRevision]);
 const selected=props.selectedCode&&codeMarket(props.selectedCode)===market?props.selectedCode:selections[market]||'';
 useEffect(()=>{if(selected){try{localStorage.setItem('assistant-selection-'+market,selected);}catch{/* storage unavailable */}}},[market,selected]);
 const changeMarket=(next:WorkspaceMarket)=>{
  let code=selections[next]||'';
  setSelections(previous=>({...previous,[market]:selected}));
  if(!code)try{code=localStorage.getItem('assistant-selection-'+next)||'';}catch{/* storage unavailable */}
  setMarket(next);props.onSelectStock(code);props.onMarketChange?.(next);setError('');
  try{localStorage.setItem('assistant-market',next);}catch{/* storage unavailable */}
 };
 const watch=(code:string)=>{
  if(market==='cn'){props.onWatchlist(code);return;}
  void workspaceWatchlist.change(market,code,watchlist.includes(code)).then(()=>setWatchRevision(v=>v+1)).catch(()=>setError('自选未保存，请重试'));
 };
 const board=market==='cn'?props.board:{...props.board,settings:{...props.board.settings,watchlist},report:null,research:[],events:[]};
 const currency=market==='us'?'USD':market==='hk'?'HKD':'CNY';
 return <MarketContext.Provider value={{market,currency,financialCurrency:currency}}>
  <MarketSelector market={market} onChange={changeMarket}/>
  {market!=='cn'&&<p className="as-footnote">{market==='us'?'美股 · 纽约交易时区':'港股 · 香港交易时区'} · 免费行情可能延迟 · 行业仅显示已核实覆盖范围 · 行情刷新不调用AI</p>}
  {error&&<p role="alert">{error}</p>}
  <InvestmentWorkspaceContent key={market} {...props} market={market} board={board} selectedCode={selected} onWatchlist={watch} onSelectStock={code=>{setSelections(previous=>({...previous,[market]:code}));props.onSelectStock(code);}}/>
 </MarketContext.Provider>;
}
