import { useCallback,useEffect,useRef,useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { IntegratedResearchResult } from '../../types/aShareMarket';

export function useIntegratedResearch(code:string) {
  const [revision,setRevision]=useState(0),sequence=useRef(0);
  const pendingActions=useRef(new Map<string,symbol>()),acceptedWork=useRef(new Set<string>()),visibleCode=useRef(code);
  visibleCode.current=code;
  const latest=useRef<{code:string;result:IntegratedResearchResult}|undefined>(undefined);
  const [saved,setSaved]=useState<{code:string;result?:IntegratedResearchResult;error?:string;message?:string;busy?:boolean}>({code:''});
  useEffect(()=>{
    const controller=new AbortController(),seq=++sequence.current;
    let timer:ReturnType<typeof setTimeout>|undefined,busy=false;
    const load=async()=>{
      if(busy||controller.signal.aborted)return;
      busy=true;
      try {
        const result=await aShareMarketApi.integrated(code,controller.signal);
        if(controller.signal.aborted||seq!==sequence.current)return;
        if(!result||result.code!==code||typeof result.status!=='string')throw new Error('综合研究返回的证券或状态不匹配');
        latest.current={code,result};
        if(!pendingActions.current.has(code)){
          if(['preparing','running'].includes(result.status))acceptedWork.current.add(code);
          else acceptedWork.current.delete(code);
        }
        setSaved(previous=>({code,result,message:previous.code===code?previous.message:undefined,busy:pendingActions.current.has(code)||acceptedWork.current.has(code)}));
        timer=setTimeout(()=>void load(),['preparing','running'].includes(result.status)?4000:300000);
      } catch(error) {
        if(!controller.signal.aborted&&seq===sequence.current){
          setSaved(previous=>({code,result:latest.current?.code===code?latest.current.result:undefined,error:error instanceof Error?error.message:'综合研究未取得',message:previous.code===code?previous.message:undefined,busy:pendingActions.current.has(code)||acceptedWork.current.has(code)}));
          timer=setTimeout(()=>void load(),30000);
        }
      } finally {busy=false;}
    };
    if(code)void load();
    const focus=()=>{if(document.visibilityState!=='hidden'){if(timer)clearTimeout(timer);void load();}};
    window.addEventListener('focus',focus);
    return ()=>{controller.abort();if(timer)clearTimeout(timer);window.removeEventListener('focus',focus);};
  },[code,revision]);
  const reload=useCallback(()=>setRevision(v=>v+1),[]);
  const action=useCallback(async(kind:'prepare'|'generate',option:number|boolean)=>{
    if(!code||pendingActions.current.has(code)||acceptedWork.current.has(code))return;
    const token=Symbol(code);
    pendingActions.current.set(code,token);
    // A read started before this mutation cannot acknowledge its completion.
    ++sequence.current;
    setSaved(previous=>previous.code===code?{...previous,busy:true,error:undefined}:{code,busy:true});
    try {
      const response=kind==='prepare'?await aShareMarketApi.prepareResearch(code,Number(option)):await aShareMarketApi.generateIntegrated(code,Boolean(option));
      if(['running','preparing'].includes(response.status))acceptedWork.current.add(code);
      if(visibleCode.current===code)setSaved(previous=>({...previous,code,busy:acceptedWork.current.has(code),message:response.message}));
    } catch(error) {
      if(visibleCode.current===code)setSaved(previous=>({...previous,code,busy:acceptedWork.current.has(code),error:error instanceof Error?error.message:'操作未完成'}));
    } finally {
      if(pendingActions.current.get(code)===token)pendingActions.current.delete(code);
      if(visibleCode.current===code)reload();
    }
  },[code,reload]);
  const prepare=useCallback((peerOffset=0)=>action('prepare',peerOffset),[action]);
  const generate=useCallback((force=false)=>action('generate',force),[action]);
  const current=saved.code===code?saved:undefined;
  return {result:current?.result,error:current?.error,message:current?.message,busy:current?.busy||false,loading:!current,reload,prepare,generate};
}
