import {useEffect,useState} from 'react';
import type {Sector} from '../../types/aShareMarket';
import type {FlowCategory,SectorFundFlow} from '../../types/aShareSectorFlow';
import {useSectorFundFlow} from './useSectorFundFlow';
import {useMarketPresentation} from './MarketContext';
import SectorFundFlowChart from './SectorFundFlowChart';
import {FLOW_NAMES,flowMoney} from './sectorFundFlowData';
export default function SectorFundFlowPanel({sector,onData}:{sector:Sector;onData?:(value:SectorFundFlow|undefined)=>void}){
 const {market}=useMarketPresentation();const enabled=market==='cn'&&/^em:(industry|concept):BK\d{4}$/.test(sector.sector_id);
 const [period,setPeriod]=useState(0),[categories,setCategories]=useState<FlowCategory[]>(['main']),[price,setPrice]=useState(true),[cumulative,setCumulative]=useState(true);
 const state=useSectorFundFlow(sector.sector_id,period,enabled),v=state.value;
 useEffect(()=>{onData?.(state.value);},[state.value,onData]);
 if(!enabled)return <p className="as-footnote">暂不支持港美股板块资金流或此分类的数据源；成交额不会作为资金净流入替代值。</p>;
 const errors=Object.entries(v?.health||{}).filter(([,h])=>h.status==='failed');
 return <section className="am-flow-panel" aria-label="板块资金流动态趋势"><div className="as-section-heading"><div><p className="as-eyebrow">{sector.name} · 资金动态</p><h3>{period?'每日净流入与累计趋势':'盘中累计资金采样'}</h3></div><div className="am-toolbar"><select aria-label="资金流期间" value={period} onChange={e=>setPeriod(Number(e.target.value))}><option value={0}>今日盘中采样</option><option value={5}>近5交易日</option><option value={20}>近20交易日</option><option value={60}>近60交易日</option></select><button className="am-button" disabled={state.loading} onClick={state.refresh}>刷新资金数据</button></div></div>
 <div className="am-flow-toggles">{(Object.keys(FLOW_NAMES) as FlowCategory[]).map(k=><label key={k}><input type="checkbox" checked={categories.includes(k)} onChange={e=>setCategories(c=>e.target.checked?[...c,k]:c.filter(n=>n!==k))}/>{FLOW_NAMES[k]}</label>)}<label><input type="checkbox" checked={price} onChange={e=>setPrice(e.target.checked)}/>板块涨跌（右轴）</label>{period>0&&<label><input type="checkbox" checked={cumulative} onChange={e=>setCumulative(e.target.checked)}/>主力区间累计</label>}</div>
 {v&&period>0&&<div className="am-flow-stats"><span>主力区间净额 <strong>{flowMoney(v.summary.main_net)}</strong></span><span>净流入天数 <strong>{v.summary.positive_days??'未知'}</strong></span><span>完整日覆盖 <strong>{v.summary.covered}/{period}</strong> · 截止 {v.anchor_date||'未知'}</span></div>}
 {v&&<div className="am-flow-legend"><span>近5日主力 {flowMoney(v.summary.net_5d)}</span><span>近20日主力 {flowMoney(v.summary.net_20d)}</span><span>连续净流入 {v.summary.consecutive_positive??'未知'} 天</span><span>近3日−前3日净额 {flowMoney(v.summary.acceleration_3d)}</span></div>}
 <p className="as-footnote" role="status">{state.loading?'正在读取资金数据…':(v?.poll_pending??(v?.task_ids.length&&!errors.length))?'后台获取资金资料中，完成后自动更新…':errors.length?'部分资金来源暂不可用，保留已有缓存':period?'完整日资金缓存':'盘中采样缓存'} · 每5分钟检查，隐藏页面暂停检查{v&&!v.active?' · 当前非连续交易时段':''}</p>
 {state.error&&<p role="alert">{state.error}</p>}{errors.map(([k,h])=><p className="as-footnote" key={k}>{({rank:'排行/采样',history:'日历史',members:'成分股资金'}[k]||k)}：{h.error} · 检查 {h.checked_at||'未知'}</p>)}
 {v?.points.some(p=>Object.values(p.values).some(n=>n!=null))?<SectorFundFlowChart points={v.points} period={period} categories={categories} showPrice={price} cumulative={cumulative}/>:<div className="am-flow-empty">{period?'尚无该期间完整日资金资料；后台获取后自动展示。':'尚无盘中采样；交易时段打开后每5分钟采集，不补造历史分钟曲线。'}</div>}
 <p className="as-footnote">来源 {v?.source||'eastmoney/sector-flow'} · 单位人民币亿元 · 获取 {v?.observed_at||'尚未取得'}<br/>{period?'日期来自日资金源；只采用已完成交易日。':'来源未提供交易日期和时间；采样时间不代表数据属于今天。午休与采样缺口断线。'}{v&&!v.calendar_available&&' 交易日历不可用，暂停区间统计。'}<br/>主力包含超大单与大单，图中各线独立展示，不能重复相加；不是机构持仓或买卖信号。</p>
 </section>;
}
