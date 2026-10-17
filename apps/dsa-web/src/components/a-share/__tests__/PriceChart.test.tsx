import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { movingAverage, computeIndicators, chartForecast, isConditionalPlan, provisionalPriceBar } from '../priceChartData';
import PriceChart from '../PriceChart';
import { outlookFixture, outlookHistory } from './outlookFixture';
import { liveFixture } from './liveFixture';
const bars = Array.from({length:65},(_,i)=>({date:`2026-10-${i}`,open:10+i,high:12+i,low:9+i,close:11+i,volume:100}));
describe('price chart',()=>{
  it('has warmup gaps and known Wilder values',()=>{
    expect(movingAverage([10,11,12],2)).toEqual([null,10.5,11.5]);
    const v=computeIndicators(bars);
    expect(v.MA20[19]).toBe(20.5); expect(v.RSI[14]).toBe(100); expect(v.ATR20[20]).toBe(3);
    expect(v.MACD[24]).toBeNull(); expect(v.DIF[25]).toBeCloseTo(7); expect(v.DEA[33]).toBeCloseTo(7);
    expect(v.BOLL.upper[19]).toBeCloseTo(32.03256,4);
    const flat=computeIndicators(bars.map(b=>({...b,open:10,high:10,low:10,close:10})));
    expect(flat.RSI[14]).toBe(50);
  });
  it('draws real open close candles and shared hover with bounded zoom',()=>{
    render(<PriceChart items={bars.slice(0,2)} chartType="candle" indicators={{MA20:true,volume:true}} levels={[]} />);
    expect(screen.getByLabelText(/2026-10-0 开10 高12 低9 收11/)).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('img',{name:'历史价格与指标'}),{key:'ArrowRight'});
    expect(screen.getByText(/开 11/)).toBeInTheDocument();
    expect(screen.getByLabelText('可见交易日数量')).toBeInTheDocument();
  });
});
it('remote forecast prices keep the candle scale until explicitly included',()=>{
  render(<PriceChart items={bars.slice(0,2)} chartType="candle" indicators={{}} levels={[{id:'ai-future',source:'ai',kind:'forecast',label:'远端情景',low:500,high:510,active:true,horizon:20}]}/>);
  const control=screen.getByLabelText('包含远端价位');expect(control).not.toBeChecked();fireEvent.click(control);expect(control).toBeChecked();
});
it('separates nearby historical strategy labels on the chart',()=>{
  const levels=[25.6,25.8,26.3,26.6].map((value,i)=>({id:`report-${i}`,source:'report' as const,kind:'historical',label:`历史价位${i}`,low:value,active:true}));
  const {container}=render(<PriceChart items={[{date:'2026-10-09',open:26,high:30,low:20,close:26}]} chartType="candle" indicators={{}} levels={levels}/>);
  const positions=levels.map(l=>Number(container.querySelector(`[data-level-id="${l.id}"] text`)?.getAttribute('y'))).sort((a,b)=>a-b);
  expect(positions.every(Number.isFinite)).toBe(true);
  expect(positions.slice(1).every((y,i)=>y-positions[i]>=14)).toBe(true);
  expect(container.querySelector('[data-level-id="report-0"] text')).toHaveAttribute('x','840');
  expect(screen.getByText(/青色虚线是首页历史报告参考价/)).toBeInTheDocument();
});

it('long moving averages have full warmup and use all historical sessions',()=>{
  const longBars=Array.from({length:260},(_,i)=>({...bars[0],date:String(i),close:i+1}));
  const values=computeIndicators(longBars);
  expect(values.MA120?.[118]).toBeNull();
  expect(values.MA120?.[119]).toBe(60.5);
  expect(values.MA250?.[248]).toBeNull();
  expect(values.MA250?.[249]).toBe(125.5);
});

it('uses prior calculation bars for long indicators without showing them as candles',()=>{
  const all=Array.from({length:251},(_,i)=>({date:new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10),open:i+1,high:i+1,low:i+1,close:i+1}));
  const prior=all.slice(0,249),selected=all.slice(249);
  expect(computeIndicators(selected,prior).MA250).toEqual([125.5,126.5]);
  const {container}=render(<PriceChart items={selected} warmup={prior} chartType="candle" indicators={{MA250:true}} levels={[]}/>);
  expect(screen.getByText('MA250 126.50')).toBeInTheDocument();
  expect(container.querySelectorAll('g[aria-label*=" 开"]')).toHaveLength(2);
  expect(screen.getByLabelText('可见交易日数量')).toHaveAttribute('max','2');
  expect(computeIndicators(selected,[...prior,selected[0]]).MA250).toEqual([125.5,126.5]);
});

it('maps a raw forecast only through matching anchored history, without inventing calendar dates',()=>{
  const data=outlookFixture(),raw=outlookHistory('raw'),qfq=outlookHistory('qfq');
  const mapped=chartForecast(data,raw,qfq,'qfq','600000',20);
  expect(mapped?.anchor_price).toBe(20);
  expect(mapped?.points).toEqual([{sessions:20,date:null,low:16,median:21.6,high:28}]);
  expect(chartForecast(data,raw,raw,'raw','600000',20)?.points[0].median).toBe(27);
  expect(chartForecast(data,raw,qfq,'qfq','600000',5)?.points[0].median).toBeCloseTo(20.4);
  expect(chartForecast({...data,status:'partial'},raw,qfq,'qfq','600000',20)).toBeDefined();
  expect(chartForecast({...data,status:'failed'},raw,qfq,'qfq','600000',20)).toBeUndefined();
  const invalid=outlookFixture();invalid.forecasts[1].points[0].low=Infinity;
  expect(chartForecast(invalid,raw,qfq,'qfq','600000',20)).toBeUndefined();
  expect(chartForecast(data,raw,{...qfq,items:[{...qfq.items[0],date:'2026-10-08'}]},'qfq','600000',20)).toBeUndefined();
});
it('requires real ordered plan prices and conservative target risk before showing conditional levels',()=>{
  const plan=outlookFixture().plan;
  expect(isConditionalPlan(plan,2)).toBe(true);
  expect(isConditionalPlan({...plan,status:'observe'},2)).toBe(false);
  expect(isConditionalPlan({...plan,target_low:26,reward_risk:4},2)).toBe(false);
  expect(isConditionalPlan({...plan,stop:null},2)).toBe(false);
  expect(isConditionalPlan(plan,3)).toBe(false);
});

it('rejects same-date raw refreshes when the displayed close differs from the forecast raw anchor',()=>{
  const data=outlookFixture(),raw=outlookHistory('raw');
  data.raw_anchor=12;data.reference_price=12;
  raw.items=[{date:'2026-10-09',open:12,high:13,low:11,close:12}];
  expect(chartForecast(data,raw,raw,'raw','600000',20)?.anchor_price).toBe(12);
  const displayed={...raw,items:[{...raw.items[0],open:13,high:14,low:12,close:13}]};
  expect(chartForecast(data,raw,displayed,'raw','600000',20)).toBeUndefined();
});

it('accepts only new dated live bars in the selected period with matching source and basis',()=>{
  const live=liveFixture(),history=outlookHistory('qfq');
  expect(provisionalPriceBar(live,history,'qfq','2026-10-14','600000')?.bar.close).toBe(22);
  expect(provisionalPriceBar({...live,source:'other'},history,'qfq','2026-10-14','600000')).toBeUndefined();
  expect(provisionalPriceBar({...live,adjustment_basis:'older'},history,'qfq','2026-10-14','600000')).toBeUndefined();
  expect(provisionalPriceBar(live,history,'qfq','2026-10-09','600000')).toBeUndefined();
  expect(provisionalPriceBar({...live,code:'600001'},history,'qfq','2026-10-14','600000')).toBeUndefined();
  expect(provisionalPriceBar({...live,bars:{...live.bars,qfq:{...live.bars.qfq!,date:'unknown'}}},history,'qfq','2026-10-14','600000')).toBeUndefined();
  expect(provisionalPriceBar({...live,bars:{...live.bars,qfq:{...live.bars.qfq!,date:'2026-10-09'}}},history,'qfq','2026-10-14','600000')).toBeUndefined();
  expect(provisionalPriceBar({...live,provisional:false},history,'qfq','2026-10-14','600000')).toBeUndefined();
});
it('draws a hollow unfinished candle without admitting it to MA or forecast anchor calculations',()=>{
  const history=Array.from({length:5},(_,i)=>({date:`2026-10-${String(i+5).padStart(2,'0')}`,open:10+i,high:10+i,low:10+i,close:10+i}));
  const live={code:'600000',bar:{date:'2026-10-14',open:90,high:110,low:80,close:100},fetched_at:'2026-10-14T14:01:00+08:00'};
  const forecast={code:'600000',anchor_date:'2026-10-09',anchor_price:14,horizon_sessions:20,target_date:null,nominal_coverage:.8,points:[{sessions:20,date:null,low:12,median:14,high:16}]};
  const {container}=render(<PriceChart items={history} chartType="candle" indicators={{MA5:true}} levels={[]} forecast={forecast} live={live}/>);
  expect(screen.getByText('MA5 12.00')).toBeInTheDocument();
  expect(container.querySelector('[data-live-date="2026-10-14"] rect')).toHaveAttribute('fill','none');
  expect(container.querySelector('[data-live-date="2026-10-14"] rect')).toHaveAttribute('stroke-dasharray','3 2');
  expect(container.querySelector('[data-outlook-code]')).toBeInTheDocument();
  expect(screen.getAllByText(/未完成/).length).toBeGreaterThan(0);
  expect(screen.getByLabelText('可见交易日数量')).toHaveAttribute('max','5');
  fireEvent.keyDown(screen.getByRole('img',{name:'历史价格与指标'}),{key:'ArrowLeft'});
  expect(container.querySelector('.am-ohlc')).toHaveTextContent('2026-10-09');
  expect(container.querySelector('[data-outlook-code] path')?.getAttribute('d')).toMatch(/^M628,/);
});

it('withholds live overlays until the exact raw or adjusted history publication is displayed',()=>{
  const live=liveFixture();
  for(const adjust of ['raw','qfq'] as const){
    const history=outlookHistory(adjust);
    expect(provisionalPriceBar(live,history,adjust,'2026-10-14','600000')).toBeDefined();
    expect(provisionalPriceBar({...live,history_updated:false},history,adjust,'2026-10-14','600000')).toBeUndefined();
    expect(provisionalPriceBar({...live,history_binding:undefined},history,adjust,'2026-10-14','600000')).toBeUndefined();
    expect(provisionalPriceBar(live,{...history,fetched_at:'2026-10-14T08:00:00+08:00'},adjust,'2026-10-14','600000')).toBeUndefined();
    expect(provisionalPriceBar(live,{...history,items:[{...history.items[0],close:10}]},adjust,'2026-10-14','600000')).toBeUndefined();
  }
});
