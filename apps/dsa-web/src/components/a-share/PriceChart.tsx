import { useMemo, useState } from 'react';
import type { MarketBar, IndicatorSelection, ChartPriceLevel, ChartForecast, ChartEvent, ChartLiveBar, ChartIntegratedForecast } from '../../types/aShareMarket';
import { computeIndicators } from './priceChartData';
const COLORS=['#e3ac57','#a8c9fa','#b996ec','#70bcb7','#d5b27b','#92a8bc'];
const MA_KEYS=['MA5','MA10','MA20','MA60','MA120','MA250'] as const;
const SCENARIOS={bear:{label:'偏弱',color:'#70bcb7'},base:{label:'基准',color:'#b996ec'},bull:{label:'偏强',color:'#e77986'}};
export default function PriceChart({items,warmup,chartType,indicators,levels,highlight,onHighlight,forecast,events=[],live,integrated}:{items:MarketBar[];warmup?:MarketBar[];chartType:'candle'|'line';indicators:IndicatorSelection;levels:ChartPriceLevel[];highlight?:string;onHighlight?:(id:string)=>void;forecast?:ChartForecast;events?:ChartEvent[];live?:ChartLiveBar;integrated?:ChartIntegratedForecast}){
  const data=useMemo(()=>computeIndicators(items,warmup),[items,warmup]);
  const [count,setCount]=useState(120),[offset,setOffset]=useState(0),[hover,setHover]=useState<number|null>(null),[includeFar,setIncludeFar]=useState(false);
  if(!items.length)return <div className="as-empty">暂无有效历史价格。补齐数据后显示真实开、高、低、收。</div>;
  const end=Math.max(1,items.length-Math.min(offset,items.length-1)),start=Math.max(0,end-count),visible=items.slice(start,end);
  const provisional=live&&end===items.length&&live.bar.date>(items.at(-1)?.date||'')?live:undefined;
  const displayLength=visible.length+(provisional?1:0);
  const hoverIndex=Math.max(0,Math.min(hover??displayLength-1,displayLength-1));
  const indicatorIndex=start+Math.min(hoverIndex,visible.length-1);
  const fan=forecast&&end===items.length&&visible.at(-1)?.date===forecast.anchor_date?forecast:undefined;
  const scenario=integrated&&end===items.length&&visible.at(-1)?.date===integrated.anchor_date?integrated:undefined;
  const active=levels.filter(l=>l.active&&(!l.anchor_date||visible.some(b=>b.date===l.anchor_date)));
  const candleMin=Math.min(...visible.map(b=>b.low)),candleMax=Math.max(...visible.map(b=>b.high));
  const far=active.some(l=>l.low<candleMin||l.low>candleMax||(l.high!=null&&(l.high<candleMin||l.high>candleMax)));
  const priceValues=visible.flatMap(b=>[b.high,b.low]).concat(active.flatMap(l=>[l.low,l.high??l.low]).filter(v=>includeFar||(v>=candleMin&&v<=candleMax)));
  MA_KEYS.forEach(key=>{if(indicators[key])priceValues.push(...data[key].slice(start,end).filter((v):v is number=>v!=null));});
  if(provisional)priceValues.push(provisional.bar.high,provisional.bar.low);
  if(fan)priceValues.push(fan.anchor_price,...fan.points.flatMap(point=>[point.low,point.high]));
  if(scenario)priceValues.push(scenario.anchor_price,...scenario.points.flatMap(point=>[point.low,point.high]),...(scenario.scenarios||[]).flatMap(s=>s.points.flatMap(p=>[p.low,p.high])));
  if(indicators.BOLL)priceValues.push(...data.BOLL.upper.slice(start,end).concat(data.BOLL.lower.slice(start,end)).filter((v):v is number=>v!=null));
  const finite=priceValues.filter(Number.isFinite),min=Math.min(...finite),max=Math.max(...finite),pad=Math.max((max-min)*.08,.1);
  const x=(i:number)=>58+(i+.5)*760/displayLength,y=(v:number)=>18+(max+pad-v)/(max-min+2*pad)*252;
  const layerY=(v:number)=>Math.max(20,Math.min(268,y(v)));
  const reportLabelY=new Map<string,number>();
  const reportLevels=active.filter(level=>level.source==='report').sort((a,b)=>layerY(a.low)-layerY(b.low));
  let lastLabelY=16;
  reportLevels.forEach(level=>{lastLabelY=Math.max(layerY(level.low),lastLabelY+14);reportLabelY.set(level.id,lastLabelY);});
  if(lastLabelY>266)reportLevels.forEach(level=>reportLabelY.set(level.id,(reportLabelY.get(level.id)??0)-(lastLabelY-266)));
  const current=provisional&&hoverIndex===visible.length?provisional.bar:visible[Math.min(hoverIndex,visible.length-1)],body=Math.max(1,Math.min(9,760/displayLength*.65));
  const path=(values:(number|null)[],scale:(v:number)=>number)=>{let d='',gap=true;values.slice(start,end).forEach((v,i)=>{if(v==null||!Number.isFinite(v)){gap=true;return;}d+=`${gap?'M':'L'}${x(i)},${scale(v)} `;gap=false;});return d;};
  const panels=(['volume','MACD','RSI','ATR20'] as const).filter(k=>indicators[k]);
  const height=308+panels.length*95;
  const futureHorizon=Math.max(1,fan?.horizon_sessions||0,scenario?.horizon_sessions||0,...active.map(l=>l.horizon||0));
  const futureX=(sessions:number)=>sessions===0?x(visible.length-1):840+sessions/futureHorizon*130;
  const fanPoints=fan?[{sessions:0,date:fan.anchor_date,low:fan.anchor_price,median:fan.anchor_price,high:fan.anchor_price},...fan.points]:[];
  const fanPath=(kind:'low'|'median'|'high')=>fanPoints.map((point,i)=>`${i?'L':'M'}${futureX(point.sessions)},${y(point[kind])}`).join(' ');
  const fanArea=fanPoints.map(point=>`${futureX(point.sessions)},${y(point.high)}`).concat([...fanPoints].reverse().map(point=>`${futureX(point.sessions)},${y(point.low)}`)).join(' ');
  const scenarioPoints=scenario?[{sessions:0,low:scenario.anchor_price,median:scenario.anchor_price,high:scenario.anchor_price},...scenario.points]:[];
  const scenarioX=futureX;
  const scenarioPath=(kind:'low'|'median'|'high')=>scenarioPoints.map((p,i)=>`${i?'L':'M'}${scenarioX(p.sessions)},${y(p[kind])}`).join(' ');
  const scenarioArea=scenarioPoints.map(p=>`${scenarioX(p.sessions)},${y(p.high)}`).concat([...scenarioPoints].reverse().map(p=>`${scenarioX(p.sessions)},${y(p.low)}`)).join(' ');
  const scenarioLayers=(scenario?.scenarios||[]).map(series=>{
    const points=[{sessions:0,low:scenario!.anchor_price,median:scenario!.anchor_price,high:scenario!.anchor_price},...series.points];
    return {...series,style:SCENARIOS[series.scenario],path:points.map((p,i)=>`${i?'L':'M'}${futureX(p.sessions)},${y(p.median)}`).join(' '),
      area:points.map(p=>`${futureX(p.sessions)},${y(p.high)}`).concat([...points].reverse().map(p=>`${futureX(p.sessions)},${y(p.low)}`)).join(' ')};
  });
  const scenarioSessions=[...new Set(scenarioLayers.flatMap(s=>s.points.map(p=>p.sessions)))].sort((a,b)=>a-b);
  return <div className="am-chart">
    <div className="am-ohlc" aria-live="polite">{current.date}{provisional&&hoverIndex===visible.length?' · 未完成':''} · 开 {current.open.toFixed(2)} · 高 {current.high.toFixed(2)} · 低 {current.low.toFixed(2)} · 收 {current.close.toFixed(2)} · 量 {current.volume==null?'未知':current.volume.toLocaleString()} 股</div>
    {scenarioLayers.length>0&&<div className="am-scenario-legend" role="group" aria-label="综合情景图例">{scenarioLayers.map(s=><span key={s.scenario} style={{color:s.style.color}}>{s.style.label}情景 · 区间中点连线</span>)}<small>指向节点查看该期限区间与成立条件</small></div>}
    <svg viewBox={`0 0 1000 ${height}`} role="img" aria-label="历史价格与指标" tabIndex={0} onKeyDown={e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();setHover(v=>Math.max(0,Math.min(displayLength-1,(v??displayLength-1)+(e.key==='ArrowRight'?1:-1))));}}}>
      {[0,1,2,3,4].map(i=>{const value=min-pad+(max-min+pad*2)*i/4;return <g key={i}><line x1={58} x2={984} y1={y(value)} y2={y(value)} stroke="currentColor" opacity=".1"/><text x={4} y={y(value)+4} fontSize={11} fill="currentColor">{value.toFixed(2)}</text></g>;})}
      <line x1={830} x2={830} y1={16} y2={276} stroke="currentColor" strokeDasharray="3 4" opacity=".3"/><text x={846} y={13} fontSize={10} fill="currentColor">未来情景 · 非历史价格</text>
      {fan&&<g data-outlook-code={fan.code} data-outlook-horizon={fan.horizon_sessions} aria-label={`${fan.horizon_sessions}交易日数值预测扇形`}>
        <title>数值预测区间 · {fan.horizon_sessions}交易日 · 连接线为显示插值</title>
        <polygon points={fanArea} fill="#7eb7ef" opacity=".16"/>
        <path d={fanPath('low')} fill="none" stroke="#7eb7ef" strokeDasharray="3 4"/>
        <path d={fanPath('high')} fill="none" stroke="#7eb7ef" strokeDasharray="3 4"/>
        <path d={fanPath('median')} fill="none" stroke="#7eb7ef" strokeWidth={1.8} strokeDasharray="6 3"/>
        {fan.points.map(point=><g key={point.sessions}><circle cx={futureX(point.sessions)} cy={y(point.median)} r={2.5} fill="#7eb7ef"><title>+{point.sessions}交易日 · {point.date||'未来日历未知'} · 中位 ¥{point.median.toFixed(2)} · 区间 ¥{point.low.toFixed(2)} — ¥{point.high.toFixed(2)}</title></circle></g>)}
        <text x={840} y={280} fontSize={9} fill="#7eb7ef">+{fan.horizon_sessions}交易日</text>
      </g>}
      {scenario&&<g data-integrated-code={scenario.code} aria-label={`${scenario.horizon_sessions}交易日综合研究情景`}>
        <title>综合研究估计，尚未校准；连接线仅用于显示情景</title>
        {scenarioLayers.length>0?<>{scenarioLayers.map(series=><g key={series.scenario} data-integrated-scenario={series.scenario} aria-label={`${series.style.label}情景节点`}>
          <polygon points={series.area} fill={series.style.color} opacity=".08"/>
          <path data-scenario-center={series.scenario} d={series.path} fill="none" stroke={series.style.color} strokeWidth={1.8} strokeDasharray="5 3"/>
          {series.points.map(point=><g key={point.sessions} data-sessions={point.sessions}>
            <title>+{point.sessions}交易日 · {series.style.label} · 图表口径区间 ¥{point.low.toFixed(2)} — ¥{point.high.toFixed(2)} · 区间中点 ¥{point.median.toFixed(2)} · 成立：{point.conditions.join('；')} · 来源 {point.sources.join('、')}</title>
            <line x1={futureX(point.sessions)} x2={futureX(point.sessions)} y1={y(point.low)} y2={y(point.high)} stroke={series.style.color} opacity=".5"/>
            <circle cx={futureX(point.sessions)} cy={y(point.median)} r={3} fill={series.style.color}/>
          </g>)}
        </g>)}{scenarioSessions.map(sessions=><text key={sessions} x={futureX(sessions)} y={267} fontSize={8} textAnchor="middle" fill="currentColor">+{sessions}日</text>)}</>:<>
          <polygon points={scenarioArea} fill="#f19dba" opacity=".12"/>
          <path d={scenarioPath('low')} fill="none" stroke="#f19dba" strokeDasharray="3 4"/>
          <path d={scenarioPath('high')} fill="none" stroke="#f19dba" strokeDasharray="3 4"/>
          <path d={scenarioPath('median')} fill="none" stroke="#f19dba" strokeWidth={1.8} strokeDasharray="6 3"/>
          <text x={840} y={267} fontSize={9} fill="#f19dba">综合 +{scenario.horizon_sessions}交易日 · 未校准</text>
        </>}
      </g>}
      {chartType==='line'?<path d={path(items.map(b=>b.close),y)} fill="none" stroke="#a8c9fa" strokeWidth={1.5}/>:visible.map((b,i)=>{const color=b.close>=b.open?'#e45c65':'#38b990';return <g key={b.date} aria-label={`${b.date} 开${b.open} 高${b.high} 低${b.low} 收${b.close}`}><line x1={x(i)} x2={x(i)} y1={y(b.high)} y2={y(b.low)} stroke={color}/><rect x={x(i)-body/2} y={Math.min(y(b.open),y(b.close))} width={body} height={Math.max(1,Math.abs(y(b.open)-y(b.close)))} fill={color}/></g>;})}
      {MA_KEYS.map((key,i)=>indicators[key]&&<g key={key}><path d={path(data[key],y)} fill="none" stroke={COLORS[i]} strokeWidth={1.3}/><text x={60+i*125} y={294} fontSize={10} fill={COLORS[i]}>{key} {data[key][indicatorIndex]?.toFixed(2)??'不足窗口'}</text></g>)}
      {indicators.BOLL&&Object.values(data.BOLL).map((values,i)=><path key={i} d={path(values,y)} fill="none" stroke="#be92d7" strokeDasharray="4 3"/>)}
      {visible.map((b,i)=><rect key={b.date} x={x(i)-380/displayLength} width={760/displayLength} y={18} height={height-30} fill="transparent" onMouseMove={()=>setHover(i)}/>)}
      {visible.map((bar,i)=>{const dayEvents=events.filter(event=>event.date===bar.date);return dayEvents.length?<g key={`events-${bar.date}`} data-quant-event={dayEvents.map(event=>event.id).join(' ')} aria-label={`${bar.date} · ${dayEvents.length}条事件观察`}><title>{dayEvents.map(event=>`${event.title} · ${event.verified?'已核实':'待核实'}`).join('；')} · 事件观察不证明因果</title><circle cx={x(i)} cy={278} r={4} fill="#7eb7ef"/><text x={x(i)+7} y={281} fontSize={9} fill="#7eb7ef">{dayEvents.length}</text></g>:null;})}
      {provisional&&<g data-live-date={provisional.bar.date} data-live-code={provisional.code} aria-label={`${provisional.bar.date} 未完成 开${provisional.bar.open} 高${provisional.bar.high} 低${provisional.bar.low} 收${provisional.bar.close}`} onMouseMove={()=>setHover(visible.length)}>
        <title>未完成行情 · 获取 {provisional.fetched_at||'时间未知'} · 不进入均线与预测计算</title>
        <line x1={x(visible.length)} x2={x(visible.length)} y1={y(provisional.bar.high)} y2={y(provisional.bar.low)} stroke="#7eb7ef" strokeDasharray="3 2"/>
        <rect x={x(visible.length)-body/2} y={Math.min(y(provisional.bar.open),y(provisional.bar.close))} width={body} height={Math.max(1,Math.abs(y(provisional.bar.open)-y(provisional.bar.close)))} fill="none" stroke="#7eb7ef" strokeWidth={1.4} strokeDasharray="3 2"/>
        <text x={Math.min(775,x(visible.length)-15)} y={Math.max(30,y(provisional.bar.high)-6)} fill="#7eb7ef" fontSize={10}>未完成</text>
        <rect x={x(visible.length)-380/displayLength} width={760/displayLength} y={18} height={height-30} fill="transparent"/>
      </g>}
      {active.map(l=>{const future=l.horizon!=null,cx=future?futureX(l.horizon!):58,color=l.source==='value'?'#c7d68c':l.source==='integrated'?'#f19dba':l.source==='ai'?'#c8a6f1':l.source==='report'?'#64c8c2':l.source==='quant'?'#7eb7ef':'#efbc68';return <g key={l.id} data-level-id={l.id} onClick={()=>onHighlight?.(l.id)} style={{cursor:'pointer'}}><title>{l.label}{l.source==='report'?' · 首页历史报告参考价':''} · ¥{l.low.toFixed(2)}</title>{l.high!=null&&<rect x={cx} y={layerY(l.high)} width={future?15:760} height={Math.max(2,layerY(l.low)-layerY(l.high))} fill={color} opacity={highlight===l.id?.3:.12}/>}<line x1={cx} x2={future?cx+15:818} y1={layerY(l.low)} y2={layerY(l.low)} stroke={color} strokeWidth={highlight===l.id?2.5:1} strokeDasharray={l.source==='rule'?undefined:'5 3'}/>{l.source==='report'&&<path d={`M818,${layerY(l.low)} L835,${reportLabelY.get(l.id)??layerY(l.low)}`} fill="none" stroke={color} opacity=".6"/>}<text x={l.source==='report'?840:future?cx-8:60} y={l.source==='report'?reportLabelY.get(l.id):layerY(l.high??l.low)-4} fontSize={10} fill={color}>{l.label} ¥{l.low.toFixed(2)}{!includeFar&&(l.low<min||l.low>max)?' · 超出图轴':''}</text></g>;})}
      {panels.map((key,p)=>{const top=316+p*95,vals=key==='volume'?items.map(b=>b.volume??null):data[key],vs=(key==='MACD'?vals.concat(data.DIF,data.DEA):vals).slice(key==='MACD'?0:start,key==='MACD'?undefined:end).filter((v):v is number=>v!=null),lo=key==='RSI'?0:Math.min(0,...vs),hi=key==='RSI'?100:Math.max(1,...vs),scale=(v:number)=>top+70-(v-lo)/(hi-lo||1)*60;return <g key={key}><text x={4} y={top+10} fontSize={10} fill="currentColor">{key==='volume'?'成交量':key}</text><text x={4} y={top+35} fontSize={9} fill="currentColor">{hi.toFixed(1)}</text><line x1={58} x2={818} y1={scale(0)} y2={scale(0)} stroke="currentColor" opacity=".15"/>{key==='volume'||key==='MACD'?vals.slice(start,end).map((v,i)=>v!=null&&<rect key={i} x={x(i)-body/2} y={Math.min(scale(v),scale(0))} height={Math.max(1,Math.abs(scale(v)-scale(0)))} width={body} fill={key==='volume'?(visible[i].close>=visible[i].open?'#e45c65':'#38b990'):v>=0?'#e45c65':'#38b990'}/>):<path d={path(vals,scale)} stroke="#a8c9fa" fill="none"/>}{key==='MACD'&&<><path d={path(data.DIF,scale)} fill="none" stroke="#e3ac57"/><path d={path(data.DEA,scale)} fill="none" stroke="#a8c9fa"/></>}<text x={850} y={top+35} fill="currentColor" fontSize={11}>{vals[indicatorIndex]?.toFixed(2)??'资料不足'}</text></g>;})}
      <line x1={x(hoverIndex)} x2={x(hoverIndex)} y1={18} y2={height-15} stroke="currentColor" opacity=".3" strokeDasharray="3 4"/>

      <text x={58} y={height-2} fontSize={10} fill="currentColor">{visible[0].date}</text><text x={735} y={height-2} fontSize={10} fill="currentColor">{visible.at(-1)?.date}</text>
    </svg>
    {provisional&&<p className="as-footnote am-live-note">{provisional.bar.date} · 未完成行情 · 获取 {provisional.fetched_at||'时间未知'}。空心虚线蜡烛单独显示，不进入均线、指标或预测；扇形仍以最后完整交易日为锚点。</p>}
    {fan&&<p className="as-footnote">蓝色扇形为数值预测区间，价格轴包含该区间；连接线仅为显示插值，各节点独立预测。{fan.target_date?`终点 ${fan.target_date}`:'未来日历未知，仅按交易日序号展示。'}</p>}
    {forecast&&!fan&&<p className="as-footnote">当前窗口不含数值研究锚点，切回最近期间查看扇形。</p>}
    {scenario&&<><p className="as-footnote">综合情景为综合研究估计，尚未校准；各色节点采用同次研究已发布的分期限区间，点为区间中点，阴影为区间连接示意；连接线不代表逐日预测，也不代表这些条件一定依次发生。</p>
      {scenario.missing_nodes&&scenario.missing_nodes.length>0&&<p className="as-footnote">缺失节点：{scenario.missing_nodes.map(n=>`${n.sessions}日${SCENARIOS[n.scenario].label}`).join('、')}；不补值，不将已结束的情景延长到缺失期限。</p>}</>}
    {reportLevels.length>0&&<p className="as-footnote">青色虚线是首页历史报告参考价，按当前图表口径映射；原始建议价见上方报告，不随行情自动重算。</p>}
    {far&&<label className="am-checkbox"><input aria-label="包含远端价位" type="checkbox" checked={includeFar} onChange={e=>setIncludeFar(e.target.checked)}/>包含远端价位（扩大价格轴）</label>}
    <div className="am-zoom"><label>可见交易日数量<input aria-label="可见交易日数量" type="range" min={1} max={items.length} value={Math.min(count,items.length)} onChange={e=>setCount(Number(e.target.value))}/></label><label>向前查看<input aria-label="历史窗口位置" type="range" min={0} max={Math.max(0,items.length-1)} value={Math.min(offset,items.length-1)} onChange={e=>setOffset(Number(e.target.value))}/></label></div>
    {levels.some(l=>l.active&&l.anchor_date&&!visible.some(b=>b.date===l.anchor_date))&&<p className="as-footnote">当前窗口不含研究锚点，切回最近期间查看价位叠加。</p>}
  </div>;
}
