import { useCallback, useEffect, useRef, useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { QuantOutlook } from '../../types/aShareMarket';

// Reject incomplete responses rather than manufacturing empty evidence or losing the whole detail view.
const completeResponse=(result:QuantOutlook)=>result&&['pending','ready','partial','insufficient','failed'].includes(result.status)
  &&Array.isArray(result.forecasts)&&result.forecasts.every(item=>item&&Array.isArray(item.points)&&item.validation)
  &&Array.isArray(result.trends)&&Array.isArray(result.events)&&result.events.every(item=>item&&item.impact)
  &&Array.isArray(result.limitations)&&result.weekly&&result.environment&&result.archive&&result.plan
  &&Array.isArray(result.plan.conditions)&&Array.isArray(result.plan.invalidation)&&Array.isArray(result.plan.reasons);

export function useQuantOutlook(code:string,minRewardRisk:number) {
  const [revision,setRevision]=useState(0);
  const key=[code,minRewardRisk].join('|'),sequence=useRef(0),refreshRequest=useRef<string|undefined>(undefined);
  const latest=useRef<{key:string;result:QuantOutlook}|undefined>(undefined);
  const [saved,setSaved]=useState<{key:string;revision:number;result?:QuantOutlook;error?:string}>({key:'',revision:0});
  useEffect(()=>{
    const controller=new AbortController(),seq=++sequence.current;
    const refresh=refreshRequest.current===key;
    refreshRequest.current=undefined;
    let timer:ReturnType<typeof setTimeout>|undefined,busy=false;
    const schedule=(delay:number)=>{if(timer)clearTimeout(timer);timer=setTimeout(()=>void load(),delay);};
    const load=async(forceRefresh=false)=>{
      if(busy||controller.signal.aborted)return;
      if(document.visibilityState==='hidden'){schedule(60000);return;}
      busy=true;
      try {
        const result=await aShareMarketApi.outlook(code,minRewardRisk,controller.signal,forceRefresh);
        if(controller.signal.aborted||seq!==sequence.current)return;
        if(!result||!completeResponse(result))throw new Error('数值研究数据结构不完整，请重试');
        if(result.code!==code)throw new Error('数值研究返回的证券代码不匹配，请重试');
        latest.current={key,result};
        setSaved({key,revision,result});
        schedule(result.status==='pending'?4000:result.status==='partial'?30000:300000);
      } catch(error) {
        if(!controller.signal.aborted&&seq===sequence.current){
          const prior=latest.current?.key===key?latest.current.result:undefined;
          setSaved({key,revision,result:prior,error:error instanceof Error?error.message:'数值研究资料未取得'});
          schedule(prior?.status==='pending'?4000:prior?.status==='partial'?30000:300000);
        }
      } finally {busy=false;}
    };
    const onFocus=()=>{if(document.visibilityState!=='hidden')void load();};
    if(code)void load(refresh);
    window.addEventListener('focus',onFocus);
    document.addEventListener('visibilitychange',onFocus);
    return ()=>{controller.abort();if(timer)clearTimeout(timer);window.removeEventListener('focus',onFocus);document.removeEventListener('visibilitychange',onFocus);};
  },[code,minRewardRisk,key,revision]);
  const current=saved.key===key?saved:undefined;
  const retry=useCallback(()=>{refreshRequest.current=key;setRevision(value=>value+1);},[key]);
  const reload=useCallback(()=>{refreshRequest.current=undefined;setRevision(value=>value+1);},[]);
  return {result:current?.result,error:current?.error,loading:!!code&&(!current||current.revision!==revision),retry,reload};
}
