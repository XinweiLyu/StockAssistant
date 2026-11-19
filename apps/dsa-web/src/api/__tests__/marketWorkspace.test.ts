import {beforeEach,expect,it,vi} from 'vitest';
import {aShareMarketApi} from '../aShareMarket';
const {get,post}=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
vi.mock('../index',()=>({default:{get,post}}));
beforeEach(()=>{get.mockReset().mockResolvedValue({data:{}});post.mockReset().mockResolvedValue({data:{}});});
it('routes qualified securities and market catalogs without altering A-share URLs',async()=>{
 await aShareMarketApi.stock('us:AAPL');
 expect(get.mock.calls.at(-1)?.[0]).toBe('/api/v1/market-workspace/us/stocks/us%3AAAPL');
 await aShareMarketApi.generateIntegrated('hk:00700');
 expect(post.mock.calls.at(-1)?.[0]).toBe('/api/v1/market-workspace/hk/stocks/hk%3A00700/integrated-research');
 await aShareMarketApi.stocks({market:'us',q:'Apple'});
 expect(get.mock.calls.at(-1)).toEqual(['/api/v1/market-workspace/us/stocks',{params:{q:'Apple'},signal:undefined}]);
 await aShareMarketApi.stock('000807');
 expect(get.mock.calls.at(-1)?.[0]).toBe('/api/v1/a-share/market/stocks/000807');
});
