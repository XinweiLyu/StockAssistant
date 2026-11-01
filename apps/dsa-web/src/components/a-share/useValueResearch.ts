import {useCallback,useEffect,useRef,useState} from 'react';
import {aShareMarketApi} from '../../api/aShareMarket';
import type {ValueAssumptions,ValueResearchResult,ValueSupplement} from '../../types/aShareValue';

function waitForData(signal:AbortSignal){
 return new Promise<void>((resolve,reject)=>{
  const abort=()=>{clearTimeout(timer);signal.removeEventListener('abort',abort);reject(new Error('已取消价值研究准备'));};
  const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},3000);
  signal.addEventListener('abort',abort,{once:true});
  if(signal.aborted)abort();
 });
}

export function useValueResearch(code:string){
 const [revision,setRevision]=useState(0),[saved,setSaved]=useState<{code:string;result?:ValueResearchResult;error?:string;actionError?:string;busy?:boolean}>({code:''});
 const active=useRef(code),sequence=useRef(0),controllers=useRef(new Set<AbortController>()),pending=useRef(new Set<string>());
 active.current=code;
 const reload=useCallback(()=>setRevision(v=>v+1),[]);
 useEffect(()=>{
  const controller=new AbortController(),seq=++sequence.current,controllerSet=controllers.current;controllerSet.add(controller);
  let timer:ReturnType<typeof setTimeout>|undefined,reading=false;
  const load=async()=>{
   if(controller.signal.aborted||reading||document.visibilityState==='hidden')return;
   reading=true;
   try{const result=await aShareMarketApi.getValue(code,controller.signal);
    if(controller.signal.aborted||seq!==sequence.current)return;
    if(result.code!==code)throw new Error('价值研究返回证券不匹配');
    setSaved(p=>({code,result,busy:pending.current.has(code),actionError:p.code===code?p.actionError:undefined}));
    timer=setTimeout(()=>void load(),['running','preparing'].includes(result.status)?3000:30000);
   }catch(error){if(!controller.signal.aborted&&seq===sequence.current){setSaved(p=>({code,result:p.code===code?p.result:undefined,actionError:p.code===code?p.actionError:undefined,error:error instanceof Error?error.message:'价值研究读取失败'}));timer=setTimeout(()=>void load(),30000);}}
   finally{reading=false;}
  };
  void load();
  const visibility=()=>{if(timer)clearTimeout(timer);if(document.visibilityState!=='hidden')void load();};
  document.addEventListener('visibilitychange',visibility);window.addEventListener('focus',visibility);
  return()=>{controller.abort();controllerSet.delete(controller);if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('focus',visibility);};
 },[code,revision]);
 useEffect(()=>{const all=controllers.current;return()=>{for(const c of all)c.abort();};},[code]);
 const action=useCallback(async(work:(signal:AbortSignal)=>Promise<unknown>)=>{
  if(pending.current.has(code))return;
  const c=new AbortController();controllers.current.add(c);pending.current.add(code);++sequence.current;
  setSaved(p=>({code,result:p.code===code?p.result:undefined,busy:true}));
  try{return await work(c.signal);}catch(error){if(active.current===code&&!c.signal.aborted)setSaved(p=>({...p,actionError:error instanceof Error?error.message:'操作失败，请核对资料与假设版本'}));throw error;}
  finally{controllers.current.delete(c);pending.current.delete(code);if(active.current===code)reload();}
 },[code,reload]);
 const result=saved.code===code?saved.result:undefined;
 const prepare=useCallback((offset=0)=>action(signal=>aShareMarketApi.prepareValue(code,offset,true,signal)),[action,code]);
 const generate=useCallback((force=false)=>action(signal=>{if(!result?.snapshot)throw new Error('请先更新价值研究资料');return aShareMarketApi.generateValue(code,result.snapshot.snapshot_id,force,signal);}),[action,code,result]);
 // Only an explicit generation click may continue preparation into a paid call.
 // Cache reads, manual data refreshes and returning to this stock never resume it.
 const research=useCallback((force=false)=>action(async signal=>{
  let latest=await aShareMarketApi.getValue(code,signal);
  const deadline=Date.now()+15*60*1000;
  const validate=()=>{if(signal.aborted||active.current!==code)throw new Error('已取消价值研究准备');if(latest.code!==code)throw new Error('价值研究返回证券不匹配');};
  const preparing=()=>latest.status==='preparing'||['pending','running'].includes(latest.data_task?.state||'')||!!(latest.peer_progress?.pending||latest.peer_progress?.running);
  const stale=()=>latest.status==='stale'||!!latest.stale_reasons?.length;
  validate();
  if(!preparing()&&(!latest.snapshot||stale()||!latest.snapshot.financial_view?.current_capital)){
   await aShareMarketApi.prepareValue(code,0,true,signal);
   latest=await aShareMarketApi.getValue(code,signal);validate();
  }
  while(preparing()){
   setSaved({code,result:latest,busy:true});
   if(Date.now()>deadline)throw new Error('资料准备超过15分钟，未调用AI；请查看后台任务后手动重试');
   await waitForData(signal);
   latest=await aShareMarketApi.getValue(code,signal);validate();
  }
  if(latest.data_task?.state==='failed')throw new Error(latest.data_task.error||'价值资料准备失败，尚未调用AI');
  if(!latest.snapshot||stale())throw new Error('价值资料仍不完整或已变化，尚未调用AI；请查看具体缺口');
  validate();setSaved({code,result:latest,busy:true});
  return aShareMarketApi.generateValue(code,latest.snapshot.snapshot_id,force,signal);
 }),[action,code]);
 const save=useCallback((a:ValueAssumptions,confirmed:boolean)=>action(async signal=>{
  const saved=await aShareMarketApi.saveValueAssumptions(code,a.snapshot_id,result?.assumptions?.revision||0,a,confirmed,signal);
  if((confirmed||a.monitor_rules?.length||a.forecast_observations?.length)&&a.cases.length&&!signal.aborted)return aShareMarketApi.evaluateValue(code,a.snapshot_id,saved.revision,signal);
  return saved;
 }),[action,code,result]);
 const supplement=useCallback((facts:ValueSupplement[])=>action(signal=>{if(!result?.snapshot)throw new Error('请先准备资料');return aShareMarketApi.supplementValue(code,result.snapshot.snapshot_id,facts,signal);}),[action,code,result]);
 return {result,error:saved.code===code?(saved.actionError||saved.error):undefined,loading:saved.code!==code,busy:!!(saved.code===code&&saved.busy)||['preparing','running'].includes(result?.status||''),reload,prepare,generate,research,save,supplement};
}
