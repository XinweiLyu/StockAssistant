import {renderHook,act} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {useLivePrice} from '../useLivePrice';
import {aShareMarketApi} from '../../../api/aShareMarket';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{live:vi.fn(),refreshPrice:vi.fn()}}));
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks();});
it('refreshes selected offshore quote every five minutes and stops after unmount',async()=>{
 vi.useFakeTimers();
 const result={code:'us:AAPL',state:'ready',bars:{raw:null,qfq:null},quote:null,provisional:false,history_updated:false};
 vi.mocked(aShareMarketApi.live).mockResolvedValue(result as never);vi.mocked(aShareMarketApi.refreshPrice).mockResolvedValue(result as never);
 const hook=renderHook(()=>useLivePrice('us:AAPL',()=>{}));
 await act(async()=>{await Promise.resolve();});
 expect(aShareMarketApi.refreshPrice).not.toHaveBeenCalled();
 await act(async()=>{await vi.advanceTimersByTimeAsync(300000);});
 expect(aShareMarketApi.refreshPrice).toHaveBeenCalledTimes(1);
 hook.unmount();
 await act(async()=>{await vi.advanceTimersByTimeAsync(300000);});
 expect(aShareMarketApi.refreshPrice).toHaveBeenCalledTimes(1);
});
