import type {ValueResearchResult} from '../../types/aShareValue';
import type {Adjust,HistoryPage,ChartPriceLevel} from '../../types/aShareMarket';
import {mapPrice,priceFamily} from './priceChartData';

export function valueChartLevels(result:ValueResearchResult|undefined,raw:HistoryPage|undefined,history:HistoryPage|undefined,adjust:Adjust,enabled:boolean):{levels:ChartPriceLevel[];reason:string}{
 const s=result?.snapshot,r=result?.report,a=result?.assumptions;
 const none=(reason:string)=>({levels:[],reason});
 if(!enabled)return none('');
 if(!s||!r||!a)return none('尚无价值报告');
 if(!result.quote?.valid)return none('当前不复权报价未核实，暂停价值价位叠加');
 if(result.status==='stale'||result.stale_reasons?.length||r.valuation_state!=='conditional'||r.snapshot_id!==s.snapshot_id||r.assumptions_revision!==a.revision)return none('草案、争议、资料或假设过期时不绘制当前价值线');
 if(!s.binding.shares?.value||!a.cases.every(c=>c.shares===s.binding.shares?.value))return none('股本基准未匹配');
 const last=raw?.items.at(-1),adjusted=history?.items.at(-1);
 if(!last||!adjusted||raw?.code!==s.code||history?.code!==s.code||last.date!==adjusted.date||last.date!==s.binding.quote?.trade_date||priceFamily(raw?.source)!==priceFamily(history?.source))return none('行情日、证券或价格转换来源未匹配估值基准');
 const levels:ChartPriceLevel[]=[];
 for(const [id,label,v] of [['value-conservative','保守价值参考',r.comparison.reference_value],['value-margin','条件安全价',r.comparison.conditional_price]] as const){
  if(v==null||!Number.isFinite(v)||v<=0)continue;
  const price=mapPrice(v,last.close,adjusted.close,adjust);
  if(price!=null)levels.push({id,source:'value',kind:id,low:price,label:`${label} · ${s.cutoff.slice(0,10)}`,active:true,anchor_date:s.cutoff.slice(0,10)});
 }
 return {levels,reason:levels.length?'':'暂无通过条件的价值参考'};
}
