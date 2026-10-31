import {expect,it} from 'vitest';
import {valueChartLevels} from '../valueChartData';
import type {ValueResearchResult} from '../../../types/aShareValue';
import {integratedHistory} from './integratedFixture';

it('hides draft/stale or mismatched capital and maps matched raw values to qfq',()=>{
 const history=integratedHistory('qfq'),raw=integratedHistory('raw');
 const result={code:history.code,status:'ready',snapshot:{code:history.code,cutoff:history.actual_end+'T15:00:00+08:00',snapshot_id:'s',binding:{shares:{value:10},quote:{trade_date:history.actual_end}}},assumptions:{revision:1,cases:[{shares:10}]},report:{snapshot_id:'s',assumptions_revision:1,valuation_state:'draft',comparison:{reference_value:80,conditional_price:56}}} as unknown as ValueResearchResult;
 expect(valueChartLevels(result,raw,history,'qfq',true).levels).toEqual([]);
 result.report!.valuation_state='conditional';
 result.quote={valid:true};
 expect(valueChartLevels(result,raw,history,'qfq',true).levels).toHaveLength(2);
 result.quote={valid:false};
 expect(valueChartLevels(result,raw,history,'qfq',true).levels).toEqual([]);
 result.quote={valid:true};
 result.assumptions!.cases[0].shares=20;
 expect(valueChartLevels(result,raw,history,'qfq',true).levels).toEqual([]);
});
