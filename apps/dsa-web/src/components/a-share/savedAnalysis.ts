import { useEffect, useState } from 'react';
import { historyApi } from '../../api/history';
import type { AnalysisReport } from '../../types/analysis';

export type SavedState = { code: string; status: 'loading' | 'missing' | 'error' | 'ready'; report?: AnalysisReport };

const stockCode = (value: string) => /^\d{6}(?:\.(?:SH|SZ|BJ))?$/i.exec(value)?.[0].slice(0, 6) ?? '';

export const strategyPrice = (value: unknown) => {
  const text = typeof value === 'string' ? value.trim() : '';
  const match = text.match(/^\s*[¥￥]?\s*(\d{1,6}(?:\.\d{1,3})?)\s*(?:元)?(?=$|[\s（(，,。；;])/u);
  const price = match ? Number(match[1]) : null;
  return price != null && Number.isFinite(price) && price > 0 ? price : null;
};

export function useSavedAnalysis(code: string): SavedState {
  const [state, setState] = useState<SavedState>({ code, status: 'loading' });
  useEffect(() => {
    let active = true;
    let busy = false;
    let latestId: number | undefined;
    const load = async () => {
      if (busy || document.visibilityState === 'hidden') return;
      busy = true;
      try {
        const list = await historyApi.getList({ stockCode: code, limit: 1 });
        const item = list.items.find(row => stockCode(row.stockCode) === code && row.reportType !== 'market_review');
        if (!item) {
          latestId = undefined;
          if (active) setState({ code, status: 'missing' });
          return;
        }
        if (item.id === latestId) return;
        const report = await historyApi.getDetail(item.id);
        if (active) {
          const valid = stockCode(report.meta.stockCode) === code && report.meta.reportType !== 'market_review';
          latestId = valid ? item.id : undefined;
          setState(valid ? { code, status: 'ready', report } : { code, status: 'missing' });
        }
      } catch {
        if (active) setState(previous => previous.code === code && previous.report ? previous : { code, status: 'error' });
      } finally {
        busy = false;
      }
    };
    void load();
    const timer = setInterval(() => void load(), 30000);
    const onFocus = () => void load();
    window.addEventListener('focus', onFocus);
    return () => { active = false; clearInterval(timer); window.removeEventListener('focus', onFocus); };
  }, [code]);

  return state.code === code ? state : { code, status: 'loading' };
}
