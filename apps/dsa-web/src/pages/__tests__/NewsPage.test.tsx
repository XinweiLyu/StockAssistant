import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../../api';
import NewsPage from '../NewsPage';

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }));
const item = { id: 1, title: '企业业绩公告', summary: '现金流变化', source: '官方公告', source_type: 'newsnow', market: 'cn', scope_type: 'symbol', scope_value: '600519', url: 'https://example.com/a', published_at: null, fetched_at: '2026-11-24T10:00:00' };
const idle = { running: false, processed: 0, total: 0, failed: 0, saved_count: 0, error: null };
const mount = () => render(<MemoryRouter><NewsPage /></MemoryRouter>);

describe('news workspace', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    vi.mocked(apiClient.get).mockImplementation(async url => ({ data: String(url).endsWith('/watchlist') ? { codes: [] } : String(url).endsWith('/refresh') ? idle : String(url).endsWith('/sources') ? { items: [], total: 0 } : { items: [item], total: 1 } }));
    vi.mocked(apiClient.post).mockResolvedValue({ data: idle });
  });
  afterEach(() => vi.useRealTimers());

  it('shows sources and unknown publication time, and links explicit stocks', async () => {
    mount();
    expect(await screen.findByText('企业业绩公告')).toBeInTheDocument();
    expect(screen.getByText('发布时间未知')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /查看股票 600519/ })).toHaveAttribute('href', '/assistant?market=cn&stock=600519');
    expect(screen.getByRole('link', { name: /阅读原文/ })).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText(/没有启用的来源/)).toBeInTheDocument();
  });

  it('empty watchlist does not request an unrestricted news list', async () => {
    mount();
    await screen.findByText('企业业绩公告');
    vi.mocked(apiClient.get).mockClear();
    fireEvent.click(screen.getByRole('tab', { name: '我的自选' }));
    expect(await screen.findByText(/当前市场暂无自选股票/)).toBeInTheDocument();
    expect(vi.mocked(apiClient.get).mock.calls.some(([url]) => String(url).endsWith('/items'))).toBe(false);
  });

  it('ignores a stale response after changing market and suppresses unsafe article links', async () => {
    let resolveOld: (value: unknown) => void = () => undefined;
    vi.mocked(apiClient.get).mockImplementation(async (url, config) => {
      if (!String(url).endsWith('/items')) return { data: String(url).endsWith('/refresh') ? idle : { items: [], total: 0 } };
      if (config?.params?.market === 'cn') return new Promise(resolve => { resolveOld = resolve; });
      return { data: { items: [{ ...item, id: 2, market: 'us', title: '美股新闻', scope_value: 'AAPL', url: 'javascript:alert(1)' }], total: 1 } };
    });
    mount();
    fireEvent.change(screen.getByLabelText('市场'), { target: { value: 'us' } });
    expect(await screen.findByText('美股新闻')).toBeInTheDocument();
    await act(async () => resolveOld({ data: { items: [item], total: 1 } }));
    expect(screen.queryByText('企业业绩公告')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /阅读原文/ })).not.toBeInTheDocument();
  });

  it('pauses polling while hidden and resumes when visible', async () => {
    mount();
    await screen.findByText('企业业绩公告');
    vi.useFakeTimers();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    fireEvent(document, new Event('visibilitychange'));
    vi.mocked(apiClient.get).mockClear();
    await act(async () => vi.advanceTimersByTimeAsync(300001));
    expect(apiClient.get).not.toHaveBeenCalled();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
    fireEvent(document, new Event('visibilitychange'));
    vi.useRealTimers();
    await waitFor(() => expect(apiClient.get).toHaveBeenCalled());
  });

  it('keeps the same-filter cached items if a manual refresh fails', async () => {
    mount();
    await screen.findByText('企业业绩公告');
    vi.mocked(apiClient.get).mockRejectedValue(new Error('连接中断'));
    fireEvent.click(screen.getByRole('button', { name: '刷新资讯' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('连接中断');
    expect(screen.getByText('企业业绩公告')).toBeInTheDocument();
  });
});
