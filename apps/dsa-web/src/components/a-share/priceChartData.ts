import type { MarketBar, Adjust, QuantOutlook, HistoryPage, ChartForecast, LivePriceResult, ChartLiveBar, IntegratedResearchResult, ChartIntegratedForecast, ChartPriceLevel } from '../../types/aShareMarket';
export function movingAverage(values:number[],window:number):(number|null)[]{
  let sum=0; return values.map((v,i)=>{sum+=v;if(i>=window)sum-=values[i-window];return i>=window-1?sum/window:null;});
}
function ema(values:(number|null)[],window:number):(number|null)[]{
  let prev:number|null=null;const seed:number[]=[];
  return values.map(v=>{if(v==null)return null;if(prev==null){seed.push(v);if(seed.length<window)return null;prev=seed.reduce((a,b)=>a+b,0)/window;}else prev=v*2/(window+1)+prev*(1-2/(window+1));return prev;});
}
function indicatorSeries(items:MarketBar[]){
  const close=items.map(b=>b.close),ma=movingAverage(close,20),e12=ema(close,12),e26=ema(close,26);
  const DIF=close.map((_,i)=>e12[i]==null||e26[i]==null?null:e12[i]!-e26[i]!),DEA=ema(DIF,9),MACD=DIF.map((v,i)=>v==null||DEA[i]==null?null:2*(v-DEA[i]!));
  const sd=close.map((_,i)=>ma[i]==null?null:Math.sqrt(close.slice(i-19,i+1).reduce((s,v)=>s+(v-ma[i]!)**2,0)/20));
  let gain=0,loss=0,atr=0;
  const RSI:(number|null)[]=[],ATR20:(number|null)[]=[];
  items.forEach((b,i)=>{
    const tr=i?Math.max(b.high-b.low,Math.abs(b.high-items[i-1].close),Math.abs(b.low-items[i-1].close)):b.high-b.low;
    atr=i<20?atr+tr:(atr*19+tr)/20;
    if(i===19)atr/=20;
    ATR20.push(i>=19?atr:null);
    if(i){const delta=b.close-items[i-1].close;if(i<=14){gain+=Math.max(delta,0)/14;loss+=Math.max(-delta,0)/14;}else{gain=(gain*13+Math.max(delta,0))/14;loss=(loss*13+Math.max(-delta,0))/14;}}
    RSI.push(i<14?null:!gain&&!loss?50:!loss?100:100-100/(1+gain/loss));
  });
  return {MA5:movingAverage(close,5),MA10:movingAverage(close,10),MA20:ma,MA60:movingAverage(close,60),MA120:movingAverage(close,120),MA250:movingAverage(close,250),BOLL:{upper:ma.map((v,i)=>v==null?null:v+2*sd[i]!),middle:ma,lower:ma.map((v,i)=>v==null?null:v-2*sd[i]!)},DIF,DEA,MACD,RSI,ATR20};
}
export function computeIndicators(items:MarketBar[],warmup:MarketBar[]=[]){
  const prior=warmup.filter(b=>items.length&&b.date<items[0].date).slice(-249);
  const data=indicatorSeries([...prior,...items]),trim=(values:(number|null)[])=>values.slice(prior.length);
  return {MA5:trim(data.MA5),MA10:trim(data.MA10),MA20:trim(data.MA20),MA60:trim(data.MA60),MA120:trim(data.MA120),MA250:trim(data.MA250),
    BOLL:{upper:trim(data.BOLL.upper),middle:trim(data.BOLL.middle),lower:trim(data.BOLL.lower)},DIF:trim(data.DIF),DEA:trim(data.DEA),MACD:trim(data.MACD),RSI:trim(data.RSI),ATR20:trim(data.ATR20)};
}
export function mapPrice(price:number,raw:number|null|undefined,qfq:number|null|undefined,adjust:Adjust){
  if(!Number.isFinite(price)||price<=0)return null;
  if(adjust==='raw')return price;
  return raw!=null&&qfq!=null&&raw>0&&qfq>0&&Number.isFinite(raw)&&Number.isFinite(qfq)?price*qfq/raw:null;
}
export function normalizedComparison(series:{name:string;items:MarketBar[]}[]){
  if(!series.length)return [];
  const common=series[0].items.map(b=>b.date).filter(d=>series.every(s=>s.items.some(b=>b.date===d))).sort();
  if(!common.length)return [];
  const maps=series.map(s=>new Map(s.items.map(b=>[b.date,b.close])));
  if(maps.some(m=>!m.get(common[0])))return [];
  return common.map(date=>({date,...Object.fromEntries(series.map((s,i)=>[s.name,maps[i].get(date)!/maps[i].get(common[0])!*100]))}));
}

export function priceFamily(source:string|null|undefined){return source?.startsWith('tushare')?'tushare':source;}

export function integratedChartLayer(state:IntegratedResearchResult|undefined,raw:HistoryPage|undefined,history:HistoryPage|undefined,adjust:Adjust,code:string,horizon:number):{forecast?:ChartIntegratedForecast;levels:ChartPriceLevel[]}|undefined {
  const report=state?.report,binding=report?.history_binding;
  if(!report||!binding||state?.status==='stale'||report.stale||!['complete','partial'].includes(report.status)||!raw||!history)return;
  if(!state.bundle||state.bundle.data_hash!==report.data_hash)return;
  if([state?.code,report.code,raw.code,history.code].some(c=>c!==code)||raw.adjust!=='raw'||history.adjust!==adjust)return;
  if(!['ready','partial'].includes(raw.state)||!['ready','partial'].includes(history.state))return;
  const r=raw.items.at(-1),q=history.items.at(-1);
  const same=(a:number,b:number)=>Number.isFinite(a)&&Number.isFinite(b)&&a>0&&Math.abs(a-b)<=Math.max(1,Math.abs(b))*1e-8;
  if(!r||!q||r.date!==binding.anchor_date||q.date!==binding.anchor_date||report.anchor_date!==binding.anchor_date||!same(binding.raw_anchor,r.close)||!same(report.reference_price,r.close))return;
  if(!binding.raw_fetched_at||binding.raw_fetched_at!==raw.fetched_at||priceFamily(binding.source)!==priceFamily(raw.source)||priceFamily(binding.source)!==priceFamily(history.source))return;
  if(adjust==='qfq'&&(!binding.qfq_fetched_at||binding.qfq_fetched_at!==history.fetched_at||binding.adjustment_basis!==history.adjustment_basis||!same(binding.qfq_anchor,q.close)))return;
  if(adjust==='raw'&&(!same(q.close,r.close)||history.fetched_at!==binding.raw_fetched_at))return;
  const convert=(p:number)=>mapPrice(p,binding.raw_anchor,binding.qfq_anchor,adjust);
  const published=report.forecasts.filter(f=>[5,20,60].includes(f.horizon_sessions)&&f.horizon_sessions<=horizon&&[f.low,f.high].every(v=>Number.isFinite(v)&&v>0)&&f.low<=f.high);
  const forecasts=published.filter(f=>f.horizon_sessions===horizon);
  let forecast:ChartIntegratedForecast|undefined;
  if(forecasts.length){
    const low=Math.min(...forecasts.map(f=>f.low)),high=Math.max(...forecasts.map(f=>f.high)),base=forecasts.find(f=>f.scenario==='base');
    const median=base?(base.low+base.high)/2:(low+high)/2;
    forecast={code,anchor_date:binding.anchor_date,anchor_price:q.close,horizon_sessions:horizon,target_date:null,
      points:[{sessions:horizon,date:null,low:convert(low)!,median:convert(median)!,high:convert(high)!}],
      scenarios:(['bear','base','bull'] as const).map(kind=>({scenario:kind,points:published.filter(f=>f.scenario===kind)
        .sort((a,b)=>a.horizon_sessions-b.horizon_sessions).map(f=>({sessions:f.horizon_sessions,date:null,
          low:convert(f.low)!,median:convert(f.low+(f.high-f.low)/2)!,high:convert(f.high)!,conditions:f.conditions,sources:f.sources}))})).filter(s=>s.points.length>0),
      missing_nodes:[5,20,60].filter(h=>h<=horizon).flatMap(sessions=>(['bear','base','bull'] as const)
        .filter(kind=>!published.some(f=>f.horizon_sessions===sessions&&f.scenario===kind)).map(scenario=>({sessions,scenario})))};
  }
  const levels:ChartPriceLevel[]=[],plan=report.plans.find(p=>p.horizon_sessions===horizon);
  const add=(id:string,label:string,low:number|null|undefined,high?:number|null)=>{
    if(low==null)return;const l=convert(low),h=high==null?null:convert(high);
    if(l==null||(high!=null&&h==null))return;
    levels.push({id:'integrated-'+id,source:'integrated',kind:id,label,low:l,high:h,active:true,anchor_date:binding.anchor_date});
  };
  if(plan){add('entry','综合·理想观察',plan.entry_low,plan.entry_high);add('second','综合·二次观察',plan.second_entry?.low,plan.second_entry?.high);add('stop','综合·止损参考',plan.stop_reference);plan.targets.forEach((t,i)=>add('target'+i,'综合·目标'+(i+1),t));}
  return {forecast,levels};
}

// A forecast is raw-price evidence. Only a verified pair can map it onto this chart.
export function chartForecast(outlook:QuantOutlook|undefined,raw:HistoryPage|undefined,history:HistoryPage|undefined,adjust:Adjust,code:string,horizon:number):ChartForecast|undefined {
  if(!outlook||!raw||!history||!['ready','partial'].includes(outlook.status)||outlook.price_basis!=='raw')return;
  if([outlook.code,raw.code,history.code].some(value=>value!==code)||raw.adjust!=='raw'||history.adjust!==adjust)return;
  if([raw.state,history.state].some(state=>!['ready','partial'].includes(state)))return;
  const r=raw.items.at(-1),q=history.items.at(-1),source=priceFamily(outlook.source);
  if(!r||!q||!source||source!==priceFamily(raw.source)||source!==priceFamily(history.source)||r.date!==outlook.as_of||q.date!==outlook.as_of)return;
  const same=(a:number|null|undefined,b:number)=>a!=null&&Number.isFinite(a)&&a>0&&Math.abs(a-b)<=Math.max(1,Math.abs(b))*1e-8;
  if(!same(outlook.raw_anchor,r.close)||!same(outlook.reference_price,r.close))return;
  if(adjust==='raw'&&(!same(q.close,r.close)||!same(outlook.raw_anchor,q.close)||!same(outlook.reference_price,q.close)))return;
  if(adjust==='qfq'&&(!same(outlook.qfq_anchor,q.close)||!outlook.adjustment_basis||outlook.adjustment_basis!==history.adjustment_basis))return;
  const forecast=outlook.forecasts.find(f=>f.horizon_sessions===horizon);
  if(!forecast)return;
  const valid=(p:{low:number;median:number;high:number})=>[p.low,p.median,p.high].every(v=>Number.isFinite(v)&&v>0)&&p.low<=p.median&&p.median<=p.high;
  if(!valid(forecast)||forecast.points.some(p=>!valid(p)||!Number.isInteger(p.sessions)||p.sessions<1||p.sessions>horizon))return;
  const points=[...forecast.points].sort((a,b)=>a.sessions-b.sessions);
  if(points.some((p,i)=>i>0&&p.sessions===points[i-1].sessions))return;
  if(points.at(-1)?.sessions!==horizon)points.push({sessions:horizon,date:forecast.target_date,low:forecast.low,median:forecast.median,high:forecast.high});
  const mapped=points.map(p=>({...p,low:mapPrice(p.low,outlook.raw_anchor,outlook.qfq_anchor,adjust)!,median:mapPrice(p.median,outlook.raw_anchor,outlook.qfq_anchor,adjust)!,high:mapPrice(p.high,outlook.raw_anchor,outlook.qfq_anchor,adjust)!}));
  if(mapped.some(p=>!valid(p)))return;
  return {code,anchor_date:outlook.as_of,anchor_price:q.close,horizon_sessions:horizon,target_date:forecast.target_date,nominal_coverage:forecast.nominal_coverage,points:mapped};
}

export function isConditionalPlan(plan:QuantOutlook['plan'],threshold=plan.min_reward_risk):boolean {
  const prices=[plan.entry_low,plan.entry_high,plan.stop,plan.target_low,plan.target_high];
  if(plan.status!=='conditional'||prices.some(value=>value==null||!Number.isFinite(value)||value<=0))return false;
  const [entryLow,entryHigh,stop,targetLow,targetHigh]=prices as number[];
  return entryLow<=entryHigh&&stop<entryLow&&targetLow>entryHigh&&targetLow<=targetHigh&&plan.min_reward_risk===threshold&&plan.reward_risk!=null&&Number.isFinite(plan.reward_risk)&&plan.reward_risk>=threshold&&(targetLow-entryHigh)/(entryHigh-stop)>=threshold;
}

export function provisionalPriceBar(live:LivePriceResult|undefined,history:HistoryPage|undefined,adjust:Adjust,end:string,code:string):ChartLiveBar|undefined {
  if(!live||!history||live.code!==code||history.code!==code||history.adjust!==adjust||live.state!=='ready'||!live.provisional)return;
  const bar=live.bars[adjust],last=history.items.at(-1),binding=live.history_binding?.[adjust];
  // Await the matching GET publication; old same-key history stays visible
  // during reload and can have different adjustment factors on the same day.
  if(!live.history_updated||!binding||!binding.fetched_at||binding.fetched_at!==history.fetched_at||binding.source!==history.source||binding.adjustment_basis!==history.adjustment_basis)return;
  if(!last||binding.anchor_date!==last.date||!Number.isFinite(binding.anchor_close)||Math.abs(binding.anchor_close-last.close)>Math.max(1,Math.abs(last.close))*1e-8)return;
  const validDate=(date:string)=>/^\d{4}-\d{2}-\d{2}$/.test(date)&&Number.isFinite(Date.parse(date))&&new Date(date).toISOString().slice(0,10)===date;
  if(!bar||!last||!validDate(bar.date)||!validDate(last.date)||!validDate(end)||bar.date<=last.date||bar.date>end)return;
  const source=priceFamily(live.source);
  if(!source||source!==priceFamily(history.source)||!live.adjustment_basis||live.adjustment_basis!==history.adjustment_basis)return;
  if(!['ready','partial'].includes(history.state)||[bar.open,bar.high,bar.low,bar.close].some(value=>!Number.isFinite(value)||value<=0))return;
  if(bar.high<Math.max(bar.open,bar.close)||bar.low>Math.min(bar.open,bar.close)||bar.high<bar.low)return;
  return {code,bar,fetched_at:live.fetched_at||live.quote?.fetched_at||null};
}
