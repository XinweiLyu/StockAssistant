import { act, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { aShareMarketApi } from '../../../api/aShareMarket';
import type { Sector } from '../../../types/aShareMarket';
import SectorDetail from '../SectorDetail';

vi.mock('../../../api/aShareMarket', () => ({ aShareMarketApi: { members: vi.fn(), sectorHistory: vi.fn(), benchmarkHistory: vi.fn() } }));
vi.mock('../PriceChart', () => ({ default: () => null }));
vi.mock('../SectorComparisonChart', () => ({ default: () => null }));

it('shows the fetched membership version without reusing stale breadth from the sector snapshot', async () => {
  const sector = {
    sector_id: 'em:industry:BK001', code: 'BK001', name: '测试行业', kind: 'industry',
    classification: 'eastmoney-industry', source: 'fixture', change: null, fetched_at: '2026-10-13',
    membership_version: null, member_breadth: { total: 0, up: 0, down: 0, flat: 0, unknown: 0 },
  } as Sector;
  vi.mocked(aShareMarketApi.members).mockResolvedValue({
    items: [], total: 2, page: 1, page_size: 20,
    membership: { codes: ['000001', '000002'], version: 'v2', state: 'ready' },
  });
  vi.mocked(aShareMarketApi.sectorHistory).mockResolvedValue({ code: sector.sector_id, items: [], adjust: 'raw', requested_start: '2025-10-13', requested_end: '2026-10-13', state: 'ready', limitations: [] });
  vi.mocked(aShareMarketApi.benchmarkHistory).mockResolvedValue({ code: '000300', items: [], adjust: 'raw', requested_start: '2025-10-13', requested_end: '2026-10-13', state: 'ready', limitations: [] });

  render(<SectorDetail sector={sector} onSelectStock={() => {}} onClose={() => {}} />);
  expect(await screen.findByText(/已获取成员 2 家/)).toBeInTheDocument();
  expect(screen.getByText(/成员版本 v2/)).toBeInTheDocument();
  expect(screen.queryByText(/本地报价覆盖 0 家/)).not.toBeInTheDocument();
});

it('refreshes sector detail when membership is initially pending', async () => {
  const sector = {
    sector_id: 'em:concept:BK002', code: 'BK002', name: '测试概念', kind: 'concept',
    classification: 'eastmoney-concept', source: 'fixture', change: null, fetched_at: '2026-10-13',
    membership_version: null,
  } as Sector;
  vi.mocked(aShareMarketApi.members)
    .mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20, membership: { codes: [], version: null, state: 'pending' } })
    .mockResolvedValueOnce({ items: [], total: 2, page: 1, page_size: 20, membership: { codes: ['000001', '000002'], version: 'v2', state: 'ready' } });
  vi.mocked(aShareMarketApi.sectorHistory).mockResolvedValue({ code: sector.sector_id, items: [], adjust: 'raw', requested_start: '2025-10-13', requested_end: '2026-10-13', state: 'ready', limitations: [] });
  vi.mocked(aShareMarketApi.benchmarkHistory).mockResolvedValue({ code: '000300', items: [], adjust: 'raw', requested_start: '2025-10-13', requested_end: '2026-10-13', state: 'ready', limitations: [] });

  vi.useFakeTimers();
  try {
    render(<SectorDetail sector={sector} onSelectStock={() => {}} onClose={() => {}} />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByText(/已获取成员 待补齐 家/)).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(screen.getByText(/已获取成员 2 家/)).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

it('shows members immediately while optional comparison histories are still unavailable',async()=>{
  const sector={sector_id:'em:industry:BK003',code:'BK003',name:'铝行业',kind:'industry',classification:'eastmoney-industry',source:'fixture',change:.02,fetched_at:'2026-10-16'} as Sector;
  vi.mocked(aShareMarketApi.members).mockResolvedValue({items:[{code:'000807',name:'云铝股份',source:'fixture',quote:null,industries:[],concepts:[]}],total:1,page:1,page_size:20,membership:{codes:['000807'],version:'v3',state:'ready'}});
  vi.mocked(aShareMarketApi.sectorHistory).mockImplementation(()=>new Promise(()=>{}));
  vi.mocked(aShareMarketApi.benchmarkHistory).mockRejectedValue(new Error('基准未取得'));
  render(<SectorDetail sector={sector} onSelectStock={()=>{}} onClose={()=>{}}/>);
  expect(await screen.findByRole('button',{name:'查看云铝股份 000807'})).toBeInTheDocument();
  expect(screen.getByRole('table',{name:'板块成分股'})).toHaveTextContent('000807');
});

it('does not relabel a board membership total as the smaller filtered stock result',async()=>{
  const sector={sector_id:'em:industry:BK004',code:'BK004',name:'铝行业',kind:'industry',classification:'eastmoney-industry',source:'fixture',change:.02,fetched_at:'2026-10-16'} as Sector;
  vi.mocked(aShareMarketApi.members).mockResolvedValue({items:[{code:'000807',name:'云铝股份',source:'fixture',quote:null,industries:[],concepts:[]}],total:1,page:1,page_size:20,membership:{codes:['000807','601600'],version:'v4',state:'ready'}});
  render(<SectorDetail sector={sector} onSelectStock={()=>{}} onClose={()=>{}}/>);
  expect(await screen.findByText(/已获取成员 2 家/)).toBeInTheDocument();
  expect(screen.getByText('1 / 1 · 1 只')).toBeInTheDocument();
});
