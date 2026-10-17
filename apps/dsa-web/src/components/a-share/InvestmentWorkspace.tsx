import { useCallback,useEffect,useState } from 'react';
import type { AssistantBoard } from '../../types/aShare';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { Sector } from '../../types/aShareMarket';
import MarketStockBrowser from './MarketStockBrowser';
import MarketSyncStatus from './MarketSyncStatus';
import StockDetail from './StockDetail';
import SectorBrowser from './SectorBrowser';
import SectorDetail from './SectorDetail';
export default function InvestmentWorkspace({board,selectedCode,selectedStrategy,navigationRevision=0,onSelectStock,onWatchlist,onResearch}:{board:AssistantBoard;selectedCode:string;selectedStrategy?:string;navigationRevision?:number;onSelectStock:(code:string)=>void;onWatchlist:(code:string)=>void;onResearch:(code:string)=>void}){
  const [industry,setIndustry]=useState<Sector>(),[concept,setConcept]=useState<Sector>(),[sector,setSector]=useState<Sector>();
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
  useEffect(()=>{
    const controller=new AbortController();
    const latest={industry:[] as Sector[],concept:[] as Sector[]};
    let busy=false;
    const load=async()=>{
      if(busy)return;
      busy=true;
      try{
        const [industryResult,conceptResult,jobsResult]=await Promise.allSettled([
          aShareMarketApi.sectors({kind:'industry',period:0},controller.signal),
          aShareMarketApi.sectors({kind:'concept',period:0},controller.signal),
          aShareMarketApi.jobs(),
        ]);
        if(controller.signal.aborted)return;
        if(industryResult.status==='fulfilled')latest.industry=industryResult.value.items||[];
        if(conceptResult.status==='fulfilled')latest.concept=conceptResult.value.items||[];
        setGroups({...latest});
        const failed=industryResult.status==='rejected'||conceptResult.status==='rejected'||
          (jobsResult.status==='fulfilled'&&jobsResult.value.health?.['health:sector_catalog']?.status==='failed');
        setSectorStatus(latest.industry.length&&latest.concept.length?'ready':failed?'failed':'loading');
        if(latest.industry.length&&latest.concept.length)clearInterval(timer);
      }finally{busy=false;}
    };
    const timer=setInterval(()=>void load(),30000);
    void load();
    return ()=>{controller.abort();clearInterval(timer);};
  },[board.settings.mode]);
  const validSelection=board.settings.mode==='demo'?selectedCode.startsWith('DEMO'): /^\d{6}$/.test(selectedCode);
  const code=validSelection?selectedCode:board.report?.candidates[0]?.code||'';
  const candidate=board.report?.candidates.find(c=>c.code===code&&(!validSelection||!selectedStrategy||c.strategy===selectedStrategy)),research=board.research?.find(r=>r.payload.code===code)?.payload;
  const selectSector=(s:Sector)=>setSector(s);
  const clear=()=>{setIndustry(undefined);setConcept(undefined);setSector(undefined);};
  const openMember=(stockCode:string)=>{
    // Enter the selected board's universe, without a previous search, scope or
    // opposite-kind filter silently hiding its constituents.
    setIndustry(sector?.kind==='industry'?sector:undefined);
    setConcept(sector?.kind==='concept'?sector:undefined);
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
        <MarketStockBrowser key={browserRevision} reloadRevision={priceReload} selectedCode={code} onSelectStock={onSelectStock} industry={industry} concept={concept} industries={groups.industry} concepts={groups.concept} sectorStatus={sectorStatus} onSelectIndustry={s=>{setIndustry(s);setSector(s||concept);}} onSelectConcept={s=>{setConcept(s);setSector(s||industry);}} onClearSector={clear}/>
        <div className="am-main">
          {code?<StockDetail key={code} code={code} candidate={candidate} onWatchlist={onWatchlist} onResearch={onResearch} research={research} events={board.events} onPriceRefresh={refreshPriceList} disabled={!board.settings.research_enabled}/>:<div className="as-empty">从左侧搜索或选择股票，即可在此查看 K 线、指标、AI 价位和证据。</div>}
          <p className="as-footnote am-model-budget">手动模型调用：今日 {board.manual_model_usage??0} 次（不限次，按实际用量计费） · 自动研究上限：{board.model_usage??0} / {board.settings.daily_model_calls??0}</p>
        </div>
      </div>
    </div>
    <div id="am-sector-panel" role="tabpanel" aria-labelledby="am-sector-tab" hidden={view!=='sector'}>
      <div className="am-sector-workspace">
        <SectorBrowser onSelectSector={selectSector} selectedSectorId={sector?.sector_id}/>
        {sector?<SectorDetail key={sector.sector_id} sector={sector} stockCode={code||undefined} onSelectStock={openMember} onClose={()=>setSector(undefined)}/>:<section className="am-sector-placeholder" aria-label="板块成分股"><h2>查看板块成分股</h2><p>从左侧选择行业或概念，即可查看该板块的股票、报价和涨跌幅。</p><p className="as-footnote">点击成分股进入个股 K 线；板块历史与相对走势可按需展开。</p></section>}
      </div>
    </div>
    <details className="am-data-drawer"><summary>数据准备与后台任务</summary><MarketSyncStatus/></details>
  </div>;
}
