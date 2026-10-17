import { useCallback,useEffect,useRef,useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { LivePriceResult } from '../../types/aShareMarket';

type LiveState={code:string;state:LivePriceResult['state'];result?:LivePriceResult;error?:string};
export function useLivePrice(code:string,onReady:(result:LivePriceResult)=>void) {
  const [revision,setRevision]=useState(0),[saved,setSaved]=useState<LiveState>();
  const sequence=useRef(0),refreshRequest=useRef<string|undefined>(undefined),latest=useRef<{code:string;result:LivePriceResult}|undefined>(undefined);
  const readyCallback=useRef(onReady);
  useEffect(()=>{readyCallback.current=onReady;},[onReady]);
  useEffect(()=>{
    const controller=new AbortController(),seq=++sequence.current,force=refreshRequest.current===code;
    refreshRequest.current=undefined;
    let timer:ReturnType<typeof setTimeout>|undefined,needsReload=force;
    const load=async(post=false)=>{
      try {
        const result=await (post?aShareMarketApi.refreshPrice(code,controller.signal):aShareMarketApi.live(code,controller.signal));
        if(controller.signal.aborted||seq!==sequence.current)return;
        if(!result||!['pending','ready','failed','unavailable'].includes(result.state)||!result.bars)throw new Error('最新行情缓存结构不完整，请重试');
        if(result.code!==code)throw new Error('最新行情证券代码不匹配，请重试');
        if(result.state==='ready')latest.current={code,result};
        const prior=latest.current?.code===code?latest.current.result:undefined;
        setSaved({code,state:result.state,result:result.state==='ready'?result:prior||result,error:result.state==='failed'?result.message||'最新行情获取失败':undefined});
        if(result.state==='pending'){needsReload=true;timer=setTimeout(()=>void load(),4000);}
        else if(result.state==='ready'&&needsReload){needsReload=false;readyCallback.current(result);}
      } catch(error) {
        if(!controller.signal.aborted&&seq===sequence.current)setSaved({code,state:'failed',result:latest.current?.code===code?latest.current.result:undefined,error:error instanceof Error?error.message:'最新行情未取得'});
      }
    };
    if(code)void load(force);
    return ()=>{controller.abort();if(timer)clearTimeout(timer);};
  },[code,revision]);
  const refresh=useCallback(()=>{
    refreshRequest.current=code;
    setSaved(previous=>({code,state:'pending',result:previous?.code===code?previous.result:undefined}));
    setRevision(value=>value+1);
  },[code]);
  const current=saved?.code===code?saved:undefined;
  return {result:current?.result,state:current?.state,error:current?.error,loading:!!code&&(!current||current.state==='pending'),refresh};
}
