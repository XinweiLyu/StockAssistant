import type { Sector } from '../../types/aShareMarket';
export default function SectorHeatmap({items,onSelect,selectedSectorId}:{items:Sector[];onSelect:(s:Sector)=>void;selectedSectorId?:string}){
  const extent=Math.max(.01,...items.map(s=>Math.abs(s.change??0)));
  return <div className="am-heatmap">{items.map(s=>{const unknown=s.change==null,intensity=unknown?0:Math.abs(s.change!)/extent,color=unknown?'hsl(var(--muted))':s.change!>=0?`rgba(220,70,70,${.15+.6*intensity})`:`rgba(35,160,100,${.15+.6*intensity})`;return <button key={s.sector_id} aria-pressed={s.sector_id===selectedSectorId} onClick={()=>onSelect(s)} style={{background:color}} aria-label={`${s.name} ${unknown?'资料不足':`${(s.change!*100).toFixed(2)}%`}`}><span>{s.name}</span><strong>{unknown?'资料不足':`${s.change!>0?'+':''}${(s.change!*100).toFixed(2)}%`}</strong></button>;})}</div>;
}
