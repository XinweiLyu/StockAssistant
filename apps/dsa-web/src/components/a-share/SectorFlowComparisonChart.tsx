import type {FlowCategory,FlowComparisonSeries} from '../../types/aShareSectorFlow';
import {COMPARISON_COLORS,comparisonSegments,comparisonValue,minuteLabel,type ComparisonMetric,type ComparisonRow} from './sectorFlowComparisonData';
export default function SectorFlowComparisonChart({rows,series,category,metric,selectedIndex,onSelectIndex}:{rows:ComparisonRow[];series:FlowComparisonSeries[];category:FlowCategory;metric:ComparisonMetric;selectedIndex:number;onSelectIndex:(n:number)=>void}){
 const L=80,R=920,T=28,B=270,W=1000,H=320;
 const extent=Math.max(metric==='amount'?1:.001,...rows.flatMap(r=>series.map(s=>Math.abs(comparisonValue(r.cells[s.sector.sector_id],category,metric)||0))));
 const x=(m:number)=>L+(m-570)/330*(R-L),y=(n:number)=>T+(1-n/extent)*(B-T)/2;
 const row=rows[selectedIndex];
 return <div className="am-compare-chart"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="多板块今日资金采样对比图" onMouseMove={event=>{const bounds=event.currentTarget.getBoundingClientRect();if(!bounds.width)return;const target=570+((event.clientX-bounds.left)/bounds.width*W-L)/(R-L)*330;let chosen=0;rows.forEach((r,i)=>{if(Math.abs(r.minute-target)<Math.abs(rows[chosen].minute-target))chosen=i;});onSelectIndex(chosen);}}>
 <rect x={x(690)} y={T} width={x(780)-x(690)} height={B-T} fill="currentColor" opacity={.035}/><text x={(x(690)+x(780))/2} y={T+20} textAnchor="middle">午休</text>
 {[-1,-.5,0,.5,1].map(t=><g key={t}><line x1={L} x2={R} y1={y(extent*t)} y2={y(extent*t)} stroke="currentColor" opacity={t===0?.45:.12}/><text x={L-12} y={y(extent*t)+5} textAnchor="end">{(extent*t*(metric==='amount'?1e-8:100)).toFixed(2)}</text></g>)}
 <text x={L} y={17}>{metric==='amount'?'累计净额 · 亿元':'净占比 · %'}</text><text x={R} y={17} textAnchor="end">今日观测 · 5分钟采样窗</text>
 {series.map((s,i)=>comparisonSegments(rows,s.sector.sector_id,category,metric).map((part,k)=><g key={s.sector.sector_id+':'+k}><polyline points={part.map(p=>`${x(p.minute)},${y(p.value)}`).join(' ')} fill="none" stroke={COMPARISON_COLORS[i%8]} strokeWidth={2.5}/>{part.map(p=><circle key={p.minute} cx={x(p.minute)} cy={y(p.value)} r={part.length===1?4:2} fill={COMPARISON_COLORS[i%8]}><title>{s.sector.name} {minuteLabel(p.minute)} {metric==='amount'?(p.value/1e8).toFixed(2)+'亿':(p.value*100).toFixed(2)+'%'}</title></circle>)}</g>))}
 {row&&<line x1={x(row.minute)} x2={x(row.minute)} y1={T} y2={B} stroke="currentColor" opacity={.5} strokeDasharray="4 4"/>}
 {[570,630,690,780,840,900].map(m=><text key={m} x={x(m)} y={B+28} textAnchor="middle">{minuteLabel(m)}</text>)}
 </svg><label className="am-flow-scrubber">查看采样窗口 {row?.label}<input aria-label="多板块资金时间光标" type="range" min={0} max={rows.length-1} value={selectedIndex} onChange={e=>onSelectIndex(Number(e.target.value))}/></label></div>;
}
