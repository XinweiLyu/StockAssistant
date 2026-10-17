import { expect, it, vi } from 'vitest';
import { aShareMarketApi } from '../aShareMarket';
const {get}=vi.hoisted(()=>({get:vi.fn()}));
vi.mock('../index',()=>({default:{get}}));
it('reads local outlook with ratio and abort signal, then forwards ratio and refresh',async()=>{
  get.mockResolvedValue({data:{code:'600000',status:'pending'}});
  const controller=new AbortController();
  await aShareMarketApi.outlook('600000',2,controller.signal);
  expect(get).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/600000/outlook',{params:{min_reward_risk:2,refresh:false},signal:controller.signal});
  await aShareMarketApi.outlook('600000',3,controller.signal,true);
  expect(get).toHaveBeenLastCalledWith('/api/v1/a-share/market/stocks/600000/outlook',{params:{min_reward_risk:3,refresh:true},signal:controller.signal});
});
