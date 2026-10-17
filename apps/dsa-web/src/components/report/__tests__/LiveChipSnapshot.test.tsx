import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getCurrentChip } from '../../../api/chip';
import { LiveChipSnapshot } from '../LiveChipSnapshot';

vi.mock('../../../api/chip', () => ({ getCurrentChip: vi.fn() }));

describe('LiveChipSnapshot', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows live estimated values while preserving the historical report boundary', async () => {
    vi.mocked(getCurrentChip).mockResolvedValue({
      code: '000807', date: '2026-10-12', source: 'baostock/estimated_cyq',
      profit_ratio: 0.2765, avg_cost: 26.59, cost_90_low: 22.93,
      cost_90_high: 32.41, concentration_90: 0.17, cost_70_low: 24,
      cost_70_high: 29, concentration_70: 0.09,
    });
    render(<LiveChipSnapshot code="000807" />);
    await waitFor(() => expect(screen.getByText('平均成本: ¥26.59')).toBeInTheDocument());
    expect(screen.getByText('获利比例: 27.7%')).toBeInTheDocument();
    expect(screen.getByText('90% 成本区间: ¥22.93–¥32.41')).toBeInTheDocument();
    expect(screen.getByText(/旧报告的 AI 结论未使用这些数据/)).toBeInTheDocument();
    expect(getCurrentChip).toHaveBeenCalledWith('000807', expect.any(AbortSignal));
  });

  it('keeps the missing state truthful when all sources fail', async () => {
    vi.mocked(getCurrentChip).mockResolvedValue(null);
    render(<LiveChipSnapshot code="000807" />);
    await waitFor(() => expect(screen.getByText('当前筹码数据暂不可用')).toBeInTheDocument());
  });
});
