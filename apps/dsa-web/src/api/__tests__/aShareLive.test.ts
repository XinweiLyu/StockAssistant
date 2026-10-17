import { expect,it,vi } from 'vitest';
import { aShareMarketApi } from '../aShareMarket';
const {get,post}=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../index',()=>({default:{get,post}}));
it('explicitly posts a selected-stock refresh and reads its live cache with the abort signal',async()=>{
  get.mockResolvedValue({data:{code:'600000',state:'pending'}});post.mockResolvedValue({data:{code:'600000',state:'pending'}});
  const controller=new AbortController();
  await aShareMarketApi.live('600000',controller.signal);
  expect(get).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/600000/live',{params:undefined,signal:controller.signal});
  expect(post).not.toHaveBeenCalled();
  await aShareMarketApi.refreshPrice('600000',controller.signal);
  expect(post).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/600000/refresh',undefined,{signal:controller.signal});
});
