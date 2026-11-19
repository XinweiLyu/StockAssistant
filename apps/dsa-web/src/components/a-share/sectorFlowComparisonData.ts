import type {FlowCategory,FlowComparisonSeries,FlowPoint} from '../../types/aShareSectorFlow';
export type ComparisonMetric='amount'|'ratio';
export const COMPARISON_COLORS=['#00c8e8','#a78bfa','#f6b66c','#e8879b','#69cfaa','#66a6ef','#d8cf72','#b6baca'];
export interface ComparisonRow {minute:number;label:string;cells:Record<string,FlowPoint|undefined>}
export const minuteLabel=(n:number)=>`${Math.floor(n/60).toString().padStart(2,'0')}:${(n%60).toString().padStart(2,'0')}`;
export function comparisonRows(series:FlowComparisonSeries[],day:string):ComparisonRow[]{
 const rows:ComparisonRow[]=[];
 for(let m=570;m<=900;m+=5)if(m<=690||m>=780)rows.push({minute:m,label:minuteLabel(m),cells:{}});
 const grid=new Map(rows.map(r=>[r.minute,r]));
 for(const s of series)for(const p of s.points){
  if(!p.observed_at)continue;const stamp=Date.parse(p.observed_at);if(!Number.isFinite(stamp))continue;
  const local=new Date(stamp+8*3600000);if(local.toISOString().slice(0,10)!==day)continue;
  const minute=Math.floor((local.getUTCHours()*60+local.getUTCMinutes())/5)*5,row=grid.get(minute);if(!row)continue;
  const old=row.cells[s.sector.sector_id];if(!old?.observed_at||Date.parse(old.observed_at)<=stamp)row.cells[s.sector.sector_id]=p;
 }
 return rows;
}
export function comparisonValue(p:FlowPoint|undefined|null,category:FlowCategory,metric:ComparisonMetric){
 const value=metric==='amount'?p?.values[category]:p?.ratios?.[category];return value!=null&&Number.isFinite(value)?value:null;
}
export function comparisonSegments(rows:ComparisonRow[],id:string,category:FlowCategory,metric:ComparisonMetric){
 const out:{minute:number;value:number}[][]=[];let line:{minute:number;value:number}[]=[];let previous:number|undefined;let previousObserved:number|undefined;
 for(const r of rows){const point=r.cells[id],n=comparisonValue(point,category,metric),observed=point?.observed_at?Date.parse(point.observed_at):undefined;
  if(n==null||previous!=null&&r.minute-previous>8||observed!=null&&previousObserved!=null&&observed-previousObserved>8*60000){if(line.length)out.push(line);line=[];}
  if(n!=null)line.push({minute:r.minute,value:n});previous=r.minute;previousObserved=observed;
 }if(line.length)out.push(line);return out;
}
export const comparisonFormat=(n:number|null,metric:ComparisonMetric)=>n==null?'—':metric==='ratio'?`${(n*100).toFixed(2)}%`:`${n>0?'+':''}${(n/1e8).toFixed(2)}亿`;
