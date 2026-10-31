import {expect,it,vi} from 'vitest';
import {aShareMarketApi} from '../aShareMarket';
const {get,post,put}=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),put:vi.fn()}));
vi.mock('../index',()=>({default:{get,post,put}}));
it('keeps cache reads and explicit paid actions separate',async()=>{
 get.mockResolvedValue({data:{code:'000807',status:'missing'}});post.mockResolvedValue({data:{}});put.mockResolvedValue({data:{}});
 const signal=new AbortController().signal;
 await aShareMarketApi.getValue('000807',signal);
 expect(get).toHaveBeenCalledWith('/api/v1/a-share/market/stocks/000807/value-research',{params:undefined,signal});
 await aShareMarketApi.generateValue('000807','s1',false,signal);
 expect(post).toHaveBeenLastCalledWith('/api/v1/a-share/market/stocks/000807/value-research',{snapshot_id:'s1',force:false},{signal});
 await aShareMarketApi.evaluateValue('000807','s1',2,signal);
 expect(post).toHaveBeenLastCalledWith('/api/v1/a-share/market/stocks/000807/value-evaluate',{snapshot_id:'s1',assumptions_revision:2},{signal});
});
