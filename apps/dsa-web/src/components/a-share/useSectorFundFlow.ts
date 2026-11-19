import {useEffect,useRef,useState} from 'react';
import {aShareMarketApi} from '../../api/aShareMarket';
import type {SectorFundFlow} from '../../types/aShareSectorFlow';
export function useSectorFundFlow(id:string,period:number,enabled=true){
 const [saved,setSaved]=useState<{key:string;value?:SectorFundFlow;error?:string;loading:boolean}>({key:'',loading:true});
 const [manual,setManual]=useState(0);const forceNext=useRef(false);
 const key=id+':'+period;
 useEffect(()=>{
  if(!enabled)return;
  const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;let busy=false;let force=forceNext.current;forceNext.current=false;let last=0;
  const load=async()=>{
   if(busy||controller.signal.aborted||document.visibilityState==='hidden')return;
   busy=true;last=Date.now();if(timer)clearTimeout(timer);
   setSaved(prev=>({...((prev.key===key?prev:undefined)||{key}),loading:true}));
   let delay=300000;
   try{
    const value=await (force?aShareMarketApi.refreshFundFlow(id,period,controller.signal):aShareMarketApi.fundFlow(id,period,controller.signal));force=false;
    if(controller.signal.aborted)return;
    if(value.sector?.sector_id!==id||!Array.isArray(value.points)||!Array.isArray(value.task_ids)||!Array.isArray(value.member_flows)||!value.health)throw new Error('资金数据结构或板块身份不匹配，保留已有缓存');
    setSaved({key,value,loading:false});
    if(value.poll_pending??(value.task_ids.length&&!Object.values(value.health).some(h=>h.status==='failed')))delay=5000;
   }catch(e){if(!controller.signal.aborted)setSaved(prev=>({...((prev.key===key?prev:undefined)||{key}),loading:false,error:e instanceof Error?e.message:'资金数据暂未取得'}));delay=30000;}
   finally{busy=false;if(!controller.signal.aborted)timer=setTimeout(()=>void load(),delay);}
  };
  const visible=()=>{if(document.visibilityState==='visible'&&Date.now()-last>=5000)void load();};
  document.addEventListener('visibilitychange',visible);void load();
  return()=>{controller.abort();if(timer)clearTimeout(timer);document.removeEventListener('visibilitychange',visible);};
 },[id,period,key,enabled,manual]);
 return {value:enabled&&saved.key===key?saved.value:undefined,error:saved.key===key?saved.error:undefined,loading:enabled&&(saved.key!==key||saved.loading),refresh:()=>{forceNext.current=true;setManual(n=>n+1);}};
}
