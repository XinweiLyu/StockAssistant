import {render,screen} from '@testing-library/react';
import {expect,it} from 'vitest';
import PriceChart from '../PriceChart';
import {integratedChartLayer} from '../priceChartData';
import {integratedFixture,integratedHistory} from './integratedFixture';

function multiHorizon() {
 const s=integratedFixture(),f=s.report!.forecasts[0];
 s.report!.forecasts=[
  {...f,horizon_sessions:5,scenario:'bear',low:17,high:19},
  {...f,horizon_sessions:5,scenario:'bull',low:23,high:25},
  {...f,horizon_sessions:20,scenario:'bear',low:16,high:18},
  {...f,horizon_sessions:20,scenario:'base',low:20,high:24},
  {...f,horizon_sessions:20,scenario:'bull',low:25,high:29},
  {...f,horizon_sessions:60,scenario:'bear',low:19,high:21},
  {...f,horizon_sessions:60,scenario:'base',low:22,high:26},
 ];
 return s;
}

it('keeps all published earlier horizon nodes instead of reducing research to one terminal envelope',()=>{
 const h=integratedHistory(),f=integratedChartLayer(multiHorizon(),h,h,'raw','000807',60)!.forecast!;
 expect(f.scenarios?.find(s=>s.scenario==='bear')?.points.map(p=>[p.sessions,p.low,p.median,p.high])).toEqual([[5,17,18,19],[20,16,17,18],[60,19,20,21]]);
 expect(f.scenarios?.find(s=>s.scenario==='base')?.points.map(p=>p.sessions)).toEqual([20,60]);
 expect(f.scenarios?.find(s=>s.scenario==='bull')?.points.map(p=>p.sessions)).toEqual([5,20]);
});

it('limits nodes to the selected horizon and explicitly records missing scenarios without filling them',()=>{
 const h=integratedHistory(),f=integratedChartLayer(multiHorizon(),h,h,'raw','000807',20)!.forecast!;
 expect(f.scenarios?.flatMap(s=>s.points).every(p=>p.sessions<=20)).toBe(true);
 expect(f.missing_nodes).toEqual([{sessions:5,scenario:'base'}]);
 const short=integratedChartLayer(multiHorizon(),h,h,'raw','000807',5)!.forecast!;
 expect(short.scenarios?.map(s=>s.scenario)).toEqual(['bear','bull']);
});

it('draws the supplied scenario bends and interval nodes without manufacturing a missing future endpoint',()=>{
 const h=integratedHistory(),f=integratedChartLayer(multiHorizon(),h,h,'raw','000807',60)!.forecast!;
 const {container}=render(<PriceChart items={h.items} chartType="candle" indicators={{}} levels={[]} integrated={f}/>);
 expect(container.querySelectorAll('[data-integrated-scenario]')).toHaveLength(3);
 const bear=container.querySelector('[data-integrated-scenario="bear"]')!;
 expect(bear.querySelectorAll('[data-sessions]')).toHaveLength(3);
 const ys=[...bear.querySelector('[data-scenario-center]')!.getAttribute('d')!.matchAll(/[ML][\d.]+,([\d.]+)/g)].map(m=>Number(m[1]));
 expect(ys).toHaveLength(4);expect(ys[2]).toBeGreaterThan(ys[1]);expect(ys[3]).toBeLessThan(ys[2]);
 expect(container.querySelector('[data-integrated-scenario="base"] [data-sessions="5"]')).not.toBeInTheDocument();
 expect(container.querySelector('[data-integrated-scenario="bull"] [data-sessions="60"]')).not.toBeInTheDocument();
 expect(screen.getByText(/缺失节点.*5日基准.*60日偏强/)).toBeInTheDocument();
 expect(bear.querySelector('[data-sessions="5"] title')).toHaveTextContent('¥17.00');
});

it('maps every published scenario node to the same verified adjusted-price pair',()=>{
 const raw=integratedHistory(),qfq=integratedHistory('qfq');
 const f=integratedChartLayer(multiHorizon(),raw,qfq,'qfq','000807',60)!.forecast!;
 expect(f.scenarios?.find(s=>s.scenario==='bear')?.points[0].low).toBeCloseTo(13.6);
 expect(f.scenarios?.find(s=>s.scenario==='bear')?.points[2].high).toBeCloseTo(16.8);
 expect(integratedChartLayer(multiHorizon(),raw,{...qfq,fetched_at:'another-version'},'qfq','000807',60)).toBeUndefined();
});
