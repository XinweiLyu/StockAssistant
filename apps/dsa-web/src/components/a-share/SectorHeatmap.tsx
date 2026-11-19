import type { Sector } from '../../types/aShareMarket';
export default function SectorHeatmap({items,onSelect,selectedSectorId,getValue=(s:Sector)=>s.change,format=(v:number)=>`${v>0?'+':''}${(v*100).toFixed(2)}%`}:{items:Sector[];onSelect:(s:Sector)=>void;selectedSectorId?:string;getValue?:(s:Sector)=>number|null|undefined;format?:(n:number)=>string}){
  const extent=Math.max(.01,...items.map(s=>Math.abs(getValue(s)??0)));
  return <div className="am-heatmap">{items.map(s=>{const value=getValue(s),unknown=value==null,intensity=unknown?0:Math.abs(value!)/extent,color=unknown?'hsl(var(--muted))':value!>=0?`rgba(220,70,70,${.15+.6*intensity})`:`rgba(35,160,100,${.15+.6*intensity})`;return <button key={s.sector_id} aria-pressed={s.sector_id===selectedSectorId} onClick={()=>onSelect(s)} style={{background:color}} aria-label={`${s.name} ${unknown?'资料不足':format(value!)}`}><span>{s.name}</span><strong>{unknown?'资料不足':format(value!)}</strong></button>;})}</div>;
}
