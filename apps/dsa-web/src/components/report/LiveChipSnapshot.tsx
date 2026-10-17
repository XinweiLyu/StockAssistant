import { useEffect, useState } from 'react';
import { getCurrentChip, type CurrentChip } from '../../api/chip';
import type { ReportLanguage } from '../../types/analysis';
import { Card } from '../common';

type State = 'loading' | 'available' | 'missing' | 'error';

const copy = {
  zh: { title: '最新筹码参考', loading: '正在获取最新筹码…', missing: '当前筹码数据暂不可用', error: '暂时无法刷新筹码', note: '独立查询最近日线；这是成本模型估算，并非真实持仓。旧报告的 AI 结论未使用这些数据，重新分析后才会进入新报告。', cost: '平均成本', profit: '获利比例', range: '90% 成本区间', source: '来源' },
  en: { title: 'Latest chip reference', loading: 'Loading latest chips…', missing: 'Current chip data unavailable', error: 'Could not refresh chips', note: 'Estimated from daily prices and turnover, not observed holdings. The old AI conclusion did not use these figures; rerun analysis to include them.', cost: 'Average cost', profit: 'Profitable shares', range: '90% cost range', source: 'Source' },
  ko: { title: '최신 매물대 참고', loading: '최신 데이터를 가져오는 중…', missing: '현재 매물대 데이터를 사용할 수 없습니다', error: '데이터를 갱신할 수 없습니다', note: '일봉과 회전율로 추정한 원가 분포이며 실제 보유 현황이 아닙니다. 이전 AI 결론에는 반영되지 않았고 다시 분석하면 새 보고서에 반영됩니다.', cost: '평균 원가', profit: '수익 비율', range: '90% 원가 범위', source: '출처' },
} as const;

export function LiveChipSnapshot({ code, language = 'zh' }: { code: string; language?: ReportLanguage }) {
  const [chip, setChip] = useState<CurrentChip | null>(null);
  const [state, setState] = useState<State>('loading');
  const text = copy[language];
  useEffect(() => {
    const controller = new AbortController();
    setChip(null);
    setState('loading');
    getCurrentChip(code, controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setChip(value);
      setState(value ? 'available' : 'missing');
    }).catch(() => {
      if (!controller.signal.aborted) setState('error');
    });
    return () => controller.abort();
  }, [code]);

  return (
    <Card variant="bordered" className="home-panel-card" data-testid="live-chip-snapshot">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-foreground">{text.title}</h3>
        {chip ? <span className="text-xs text-muted-text">{chip.date}</span> : null}
      </div>
      {state === 'available' && chip ? (
        <div className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
          <p>{text.cost}: ¥{chip.avg_cost.toFixed(2)}</p>
          <p>{text.profit}: {(chip.profit_ratio * 100).toFixed(1)}%</p>
          <p>{text.range}: ¥{chip.cost_90_low.toFixed(2)}–¥{chip.cost_90_high.toFixed(2)}</p>
        </div>
      ) : <p className="mt-2 text-sm text-muted-text">{text[state === 'available' ? 'missing' : state]}</p>}
      {chip ? <p className="mt-2 text-xs text-muted-text">{text.source}: {chip.source}</p> : null}
      <p className="mt-2 text-xs text-muted-text">{text.note}</p>
    </Card>
  );
}
