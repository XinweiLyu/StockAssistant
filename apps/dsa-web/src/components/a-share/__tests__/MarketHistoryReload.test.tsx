import { act,renderHook,waitFor } from '@testing-library/react';
import { beforeEach,expect,it,vi } from 'vitest';
import { useMarketHistory } from '../useMarketHistory';
import { useQuantOutlook } from '../useQuantOutlook';
import { aShareMarketApi } from '../../../api/aShareMarket';
import { outlookHistory,outlookFixture } from './outlookFixture';
vi.mock('../../../api/aShareMarket',()=>({aShareMarketApi:{getValue:vi.fn(async(code:string)=>({code,status:"missing"})),history:vi.fn(),outlook:vi.fn()}}));
beforeEach(()=>{vi.resetAllMocks();vi.mocked(aShareMarketApi.history).mockImplementation(async(code,_start,_end,adjust)=>outlookHistory(adjust,code));vi.mocked(aShareMarketApi.outlook).mockImplementation(async code=>outlookFixture(code));});
it('separates history read-only reload from explicit retry and never carries refresh to another key',async()=>{
  const {result,rerender}=renderHook(({code,adjust})=>useMarketHistory(code,'2026-01-01','2026-10-14',adjust),{initialProps:{code:'600000',adjust:'qfq' as 'raw'|'qfq'}});
  await waitFor(()=>expect(result.current.history?.code).toBe('600000'));
  act(()=>result.current.retry());
  await waitFor(()=>expect(aShareMarketApi.history).toHaveBeenLastCalledWith('600000','2026-01-01','2026-10-14','qfq',expect.any(AbortSignal),true));
  act(()=>result.current.reload());
  await waitFor(()=>expect(aShareMarketApi.history).toHaveBeenLastCalledWith('600000','2026-01-01','2026-10-14','qfq',expect.any(AbortSignal),false));
  act(()=>result.current.retry());
  await waitFor(()=>expect(aShareMarketApi.history).toHaveBeenLastCalledWith('600000','2026-01-01','2026-10-14','qfq',expect.any(AbortSignal),true));
  rerender({code:'600001',adjust:'raw'});
  await waitFor(()=>expect(aShareMarketApi.history).toHaveBeenLastCalledWith('600001','2026-01-01','2026-10-14','raw',expect.any(AbortSignal),false));
});
it('preserves the same-key completed history when read-only reload fails',async()=>{
  const {result}=renderHook(()=>useMarketHistory('600000','2026-01-01','2026-10-14','raw'));
  await waitFor(()=>expect(result.current.history?.items[0].close).toBe(25));
  vi.mocked(aShareMarketApi.history).mockRejectedValue(new Error('历史缓存暂不可读'));
  act(()=>result.current.reload());
  await waitFor(()=>expect(result.current.error).toBe('历史缓存暂不可读'));
  expect(result.current.history?.items[0].close).toBe(25);
});
it('reloads outlook without asking the server to force history jobs after an earlier explicit retry',async()=>{
  const {result}=renderHook(()=>useQuantOutlook('600000',2));
  await waitFor(()=>expect(result.current.result?.code).toBe('600000'));
  act(()=>result.current.retry());
  await waitFor(()=>expect(aShareMarketApi.outlook).toHaveBeenLastCalledWith('600000',2,expect.any(AbortSignal),true));
  act(()=>result.current.reload());
  await waitFor(()=>expect(aShareMarketApi.outlook).toHaveBeenLastCalledWith('600000',2,expect.any(AbortSignal),false));
});
