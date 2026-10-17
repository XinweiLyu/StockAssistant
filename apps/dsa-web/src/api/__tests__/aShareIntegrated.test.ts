import { expect,it,vi } from 'vitest';
import { aShareMarketApi } from '../aShareMarket';
const {get,post}=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../index',()=>({default:{get,post}}));
it('uses read-only GET and explicit POST with abort and force controls',async()=>{
  get.mockResolvedValue({data:{code:'000807',status:'missing'}});
  post.mockResolvedValue({data:{accepted:true,status:'running'}});
  const signal=new AbortController().signal;
  await aShareMarketApi.integrated('000807',signal);
  expect(get).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/000807/integrated-research',{params:undefined,signal});
  await aShareMarketApi.prepareResearch('000807',20,signal);
  expect(post).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/000807/research-data',undefined,{params:{peer_offset:20},signal});
  await aShareMarketApi.generateIntegrated('000807',true,signal);
  expect(post).toHaveBeenLastCalledWith('/api/v1/a-share/market/stocks/000807/integrated-research',undefined,{params:{force:true},signal});
});
