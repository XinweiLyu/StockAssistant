import type { SavedState } from './savedAnalysis';
const field = (value: unknown) => typeof value === 'string' && value.trim() ? value.trim() : null;
const reportTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
};

export default function SavedAnalysisPanel({ code, state }: { code: string; state: SavedState }) {
  const current = state.code === code ? state : { code, status: 'loading' as const };
  const report = current.report;
  const raw = report?.details?.rawResult;
  const shortOutlook = field(raw?.shortTermOutlook);
  const mediumOutlook = field(raw?.mediumTermOutlook);
  const prices = report?.strategy;
  return <section className="am-saved-analysis" aria-label="已保存的首页分析">
    <div className="am-saved-heading"><h3>已有 AI 分析与策略点位</h3><span>首页历史报告</span></div>
    {current.status === 'loading' && <p className="as-footnote">正在读取该股已保存的分析…</p>}
    {current.status === 'missing' && <p className="as-footnote">该股没有已保存的首页分析报告；理想买入、二次买入和止盈目标尚未生成。可在图表上方统一生成综合研究、未来情景与条件策略。</p>}
    {current.status === 'error' && <p className="as-footnote">已有分析暂时无法读取，请稍后重试或刷新页面。</p>}
    {report && <>
      <p className="as-footnote">{reportTime(report.meta.createdAt)} · {report.meta.modelUsed || '模型未记录'} · 历史报告，仅供对照；不会随盘中行情自动重算。</p>
      <div className="am-saved-decision"><span>趋势判断 <strong>{report.summary.trendPrediction || '未提供'}</strong></span><span>操作建议 <strong>{report.summary.operationAdvice || '未提供'}</strong></span></div>
      {report.summary.analysisSummary && <p className="am-saved-summary">{report.summary.analysisSummary}</p>}
      <dl className="am-saved-levels">
        {([['理想买入', prices?.idealBuy], ['二次买入', prices?.secondaryBuy], ['止损点', prices?.stopLoss], ['止盈目标', prices?.takeProfit]] as const).map(([label, value]) =>
          <div key={label}><dt>{label}</dt><dd>{field(value) || '未提供'}</dd></div>)}
      </dl>
      {(shortOutlook || mediumOutlook) && <div className="am-saved-outlook">
        {shortOutlook && <p><b>短期展望</b> {shortOutlook}</p>}
        {mediumOutlook && <p><b>中期展望</b> {mediumOutlook}</p>}
      </div>}
    </>}
  </section>;
}
