import type {FlowCategory,FlowPoint} from '../../types/aShareSectorFlow';
export const FLOW_NAMES={main:'主力',super:'超大单',large:'大单',medium:'中单',small:'小单'};
export const flowMoney=(n:number|null|undefined)=>n==null?'资料不足':`${n>0?'+':''}${(n/1e8).toFixed(2)}亿`;
export function chartRows(points:FlowPoint[],period:number){
 let total:number|null=0;
 return points.map((p,index)=>{const n=p.values.main;if(n==null)total=null;else if(total!==null)total+=n;
  return {...p,index,label:period?(p.source_date||''):p.observed_at?new Date(p.observed_at).toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit'}):'未知',cumulative:period?total:null};});
}
export type Row=ReturnType<typeof chartRows>[number];
export function flowSegments(rows:Row[],key:FlowCategory|'cumulative'|'change',period:number){
 const parts:{index:number;value:number}[][]=[];let part:{index:number;value:number}[]=[];let previous:Row|undefined;
 for(const r of rows){const n=key==='change'?r.change:key==='cumulative'?r.cumulative:r.values[key];
  const gap=!period&&previous?.observed_at&&r.observed_at&&Date.parse(r.observed_at)-Date.parse(previous.observed_at)>8*60000;
  if(n==null||gap){if(part.length)parts.push(part);part=[];}
  if(n!=null)part.push({index:r.index,value:n});previous=r;
 }if(part.length)parts.push(part);return parts;
}
