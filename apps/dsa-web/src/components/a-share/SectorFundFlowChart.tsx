import {useState} from 'react';
import type {FlowCategory,FlowPoint} from '../../types/aShareSectorFlow';
import {FLOW_NAMES,flowMoney,chartRows,flowSegments} from './sectorFundFlowData';
const COLORS={main:'#16c4e5',super:'#aa8dff',large:'#ffc16f',medium:'#f07b9c',small:'#61cca6',cumulative:'#e5da91'};
export default function SectorFundFlowChart({points,period,categories,showPrice,cumulative}:{points:FlowPoint[];period:number;categories:FlowCategory[];showPrice:boolean;cumulative:boolean}){
 const rows=chartRows(points,period),[selected,setSelected]=useState<number|undefined>();
 const W=1000,H=310,L=75,R=925,T=28,B=252;
 const keys:(FlowCategory|'cumulative')[]=[...categories,...(period&&cumulative?['cumulative' as const]:[])];
 const amounts=keys.flatMap(k=>flowSegments(rows,k,period).flatMap(p=>p.map(n=>n.value)));
 const max=Math.max(1,...amounts.map(Math.abs)),priceMax=Math.max(.01,...rows.map(r=>Math.abs(r.change||0)));
 const x=(i:number)=>L+(R-L)*(rows.length>1?i/(rows.length-1):.5),y=(n:number)=>T+(B-T)*(1-n/max)/2,py=(n:number)=>T+(B-T)*(1-n/priceMax)/2;
 const focus=rows[Math.min(selected??rows.length-1,rows.length-1)];
 return <div className="am-flow-chart"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={period?'每日净流入及累计趋势（亿元）':'盘中累计资金采样曲线（亿元）'}>
  {[-1,-.5,0,.5,1].map(t=><g key={t}><line x1={L} x2={R} y1={y(max*t)} y2={y(max*t)} stroke="currentColor" opacity={t===0?.45:.12}/><text x={L-10} y={y(max*t)+4} textAnchor="end">{(max*t/1e8).toFixed(2)}</text>{showPrice&&<text x={R+8} y={y(max*t)+4}>{(priceMax*t*100).toFixed(1)}%</text>}</g>)}
  <text x={L} y={15}>资金 · 亿元</text>{showPrice&&<text x={R} y={15} textAnchor="end">源公布涨跌幅 · 右轴</text>}
  {!!period&&categories.includes('main')&&rows.map(r=>r.values.main==null?null:<rect key={r.index} x={x(r.index)-Math.min(10,300/rows.length)} y={Math.min(y(0),y(r.values.main))} width={Math.min(20,600/rows.length)} height={Math.max(1,Math.abs(y(r.values.main)-y(0)))} fill={r.values.main>=0?'#e45c65':'#38b990'} opacity={.5}/>)}
  {keys.map(k=>flowSegments(rows,k,period).map((part,i)=><g key={k+i}><polyline points={part.map(p=>`${x(p.index)},${y(p.value)}`).join(' ')} stroke={COLORS[k]} strokeWidth={k==='main'?2.5:1.8} strokeDasharray={k==='cumulative'?'7 5':undefined} fill="none"/>{part.length===1&&<circle cx={x(part[0].index)} cy={y(part[0].value)} r={3} fill={COLORS[k]}/>}</g>))}
  {showPrice&&flowSegments(rows,'change',period).map((part,i)=><polyline key={i} points={part.map(p=>`${x(p.index)},${py(p.value)}`).join(' ')} stroke="#b2b6c5" strokeDasharray="3 5" fill="none"/>)}
  {focus&&<line x1={x(focus.index)} x2={x(focus.index)} y1={T} y2={B} stroke="currentColor" opacity={.3} strokeDasharray="4 4"/>}
  {rows.filter((_,i)=>i===0||i===rows.length-1||rows.length>8&&i===Math.floor(rows.length/2)).map(r=><text key={r.index} x={x(r.index)} y={B+25} textAnchor="middle">{r.label}</text>)}
  {rows.map(r=><rect key={r.index} x={x(r.index)-(R-L)/Math.max(2,rows.length)/2} y={T} width={(R-L)/Math.max(1,rows.length)} height={B-T} fill="transparent" onMouseEnter={()=>setSelected(r.index)}><title>{r.label} 主力 {flowMoney(r.values.main)}</title></rect>)}
 </svg>{!!rows.length&&<><label className="am-flow-scrubber">查看时间 <input type="range" aria-label="资金图表查看时间" min={0} max={Math.max(0,rows.length-1)} value={focus?.index||0} onChange={e=>setSelected(Number(e.target.value))}/></label><div className="am-flow-legend"><strong>{focus?.label}</strong>{focus&&categories.map(k=><span key={k} style={{color:COLORS[k]}}>{FLOW_NAMES[k]} {flowMoney(focus.values[k])}</span>)}{focus&&period&&cumulative?<span style={{color:COLORS.cumulative}}>区间累计 {flowMoney(focus.cumulative)}</span>:null}{showPrice&&<span>涨跌 {focus?.change==null?'未知':(focus.change*100).toFixed(2)+'%'}</span>}</div></>}</div>;
}
