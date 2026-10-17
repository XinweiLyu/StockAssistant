import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ASharePage from '../ASharePage';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import apiClient from '../../api';
import { outlookFixture } from '../../components/a-share/__tests__/outlookFixture';
import { unavailableLive } from '../../components/a-share/__tests__/liveFixture';

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const settings = { mode: 'demo', watchlist: [], risk: { stock_cap: .1, sector_cap: .2, total_cap: .6, risk_per_trade: .005, commission: .0003, minimum_fee: 5, transfer_fee: .00001 }, pool_size: 40, account_id: null, snapshot_provider: 'akshare', research_enabled: false, model: '', daily_model_calls: 20 };
const board = { settings, report: null, portfolio: { positions: [], demo: true, nav: 100000, cash: 100000 }, holdings: [], events: [], health: [], history: [], alerts: [], research: [], model_usage: 0, job: { state: 'idle', completed: 0, total: 0, errors: [], message: '待同步' }, sources: {}, schedule: { running: true }, limitations: [] };
function mount() { render(<MemoryRouter><UiLanguageProvider><ASharePage /></UiLanguageProvider></MemoryRouter>); }

describe('A-share research workspace', () => {
  beforeEach(() => { vi.resetAllMocks(); vi.mocked(apiClient.get).mockImplementation(async (url) => ({ data: url?.includes('/accounts') ? { accounts: [] } : board })); });
  it('clearly labels synthetic research and unavailable candidates', async () => {
    mount();
    expect(await screen.findByText('虚构演示')).toBeInTheDocument();
    expect(screen.getByText('尚未生成研究候选')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '同步盘后研究' })).toBeEnabled();
  });
  it('offers an explicit retry when the API fails', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('连接中断'));
    mount();
    expect(await screen.findByText('连接中断')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
    await waitFor(() => expect(screen.getByText('虚构演示')).toBeInTheDocument());
  });
  it('refreshes an open detail with the current verified plan', async () => {
    const candidate = { code: 'DEMO001', name: '模拟样本', sector: 'DS01', strategy: 'trend_v1', score: 90, r20: .1, r60: .2, atr: .5, high: 19.9, source: 'demo', valid_date: '2026-10-09', plan: { entry: 19.9, quantity: 500, stop: 18.9, reasons: [] }, check: { status: 'observe', reasons: [] } };
    let current = { ...board, report: { demo: true, as_of: '2026-10-08', sample_size: 40, market_ok: true, candidates: [candidate], sectors: [], limitations: [] } };
    vi.mocked(apiClient.get).mockImplementation(async (url) => ({ data: url?.endsWith('/live') ? {...unavailableLive('DEMO001'),demo:true} : url?.endsWith('/outlook') ? {...outlookFixture('DEMO001'),demo:true,status:'insufficient',forecasts:[]} : url?.includes('/accounts') ? { accounts: [] } : url?.includes('/history') ? { code: 'DEMO001', items: [], adjust: 'qfq', state: 'partial', limitations: [] } : url?.includes('/scenarios') ? { status: 'insufficient', trade_levels: null, forecasts: [] } : url?.endsWith('/market/stocks') ? { items: [], total: 0 } : url?.includes('/market/stocks/') ? { code: 'DEMO001', name: '模拟样本', industries: [], concepts: [], quote: null } : url?.includes('/sectors') ? { items: [], classification: 'demo-industry' } : url?.includes('/jobs') ? { paused: false, counts: {} } : current }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: '查看模拟样本详情' }));
    expect(within(await screen.findByRole('region', { name: '股票研究详情' })).getByText(/计划股数：500/)).toBeInTheDocument();
    current = { ...current, report: { ...current.report, candidates: [{ ...candidate, plan: { ...candidate.plan, entry: 20.09, quantity: 400, stop: 19.09 }, check: { status: 'triggered', reasons: [] } }] } };
    fireEvent.click(screen.getByRole('button', { name: '刷新页面' }));
    await waitFor(() => expect(within(screen.getByRole('region', { name: '股票研究详情' })).getByText(/计划股数：400/)).toBeInTheDocument());
    expect(within(screen.getByRole('region', { name: '股票研究详情' })).getByText(/本次计划参考价：20.09/)).toBeInTheDocument();
    for(let i=0;i<2;i++){
      fireEvent.click(screen.getByRole('tab',{name:'行业与概念'}));
      fireEvent.click(screen.getByRole('button',{name:'查看模拟样本详情'}));
      expect(screen.getByRole('tab',{name:'个股行情'})).toHaveAttribute('aria-selected','true');
      expect(screen.getByRole('region',{name:'股票研究详情'})).toBeInTheDocument();
    }
  });
});
