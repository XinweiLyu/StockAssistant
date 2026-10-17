import { useCallback,useEffect,useRef,useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { Adjust,HistoryPage } from '../../types/aShareMarket';
export function useMarketHistory(code:string,start:string,end:string,adjust:Adjust){
  const key=[code,start,end,adjust].join('|'),sequence=useRef(0),refreshRequest=useRef<string|undefined>(undefined);
  const latest=useRef<{key:string;history:HistoryPage}|undefined>(undefined);
  const [revision,setRevision]=useState(0),[saved,setSaved]=useState<{key:string;history?:HistoryPage;error?:string}>({key:''});
  useEffect(()=>{
    const controller=new AbortController(),seq=++sequence.current,refresh=refreshRequest.current===key;
    refreshRequest.current=undefined;
    let timer:ReturnType<typeof setTimeout>|undefined;
    const load=async(forceRefresh=false)=>{try{
      const history=await aShareMarketApi.history(code,start,end,adjust,controller.signal,forceRefresh);
      if(controller.signal.aborted||seq!==sequence.current)return;
      if(history.code!==code||history.adjust!==adjust)throw new Error('历史资料证券或价格口径不匹配');
      latest.current={key,history};
      setSaved({key,history});if(history.state==='pending')timer=setTimeout(()=>void load(),4000);
    }catch(e){if(!controller.signal.aborted&&seq===sequence.current)setSaved({key,history:latest.current?.key===key?latest.current.history:undefined,error:e instanceof Error?e.message:'历史资料未取得'});}};
    if(code)void load(refresh);
    return ()=>{controller.abort();if(timer)clearTimeout(timer);};
  },[code,start,end,adjust,key,revision]);
  const retry=useCallback(()=>{refreshRequest.current=key;setRevision(value=>value+1);},[key]);
  const reload=useCallback(()=>{refreshRequest.current=undefined;setRevision(value=>value+1);},[]);
  return {history:saved.key===key?saved.history:undefined,error:saved.key===key?saved.error:undefined,retry,reload};
}
