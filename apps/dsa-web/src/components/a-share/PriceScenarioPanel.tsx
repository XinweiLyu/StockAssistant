import type { PriceScenarioResult } from '../../types/aShareMarket';

const price = (value: number) => value.toFixed(2);

export default function PriceScenarioPanel({ result, onHighlight, onResearch, riskReasons, disabled }: {
  result?: PriceScenarioResult;
  onHighlight: (id: string) => void;
  onResearch?: () => void;
  riskReasons: string[];
  disabled?: boolean;
}) {
  const levels = result?.trade_levels;
  return <aside className="am-scenarios">
    <div className="as-section-heading"><div><h2>AI 价位与情景</h2><p>人民币 · 不复权实际参考价</p></div></div>
    {onResearch?<button className="am-primary" disabled={disabled} onClick={onResearch}>生成研究与价位</button>:<p className="as-footnote">已合并到上方“综合研究与价位”。以下仅保留旧版5/10/20日结果作历史对照。</p>}
    {onResearch&&<p className="as-footnote">手动生成不受每日调用上限限制，模型服务按实际用量计费；看图和切换指标不调用模型。</p>}
    <p className="am-status">{result?.status === 'stale' ? '已过期 · 请更新研究' : result?.status === 'ready' ? '结构已校验 · 预测未经校准' : result?.status === 'partial' ? '部分有效 · 资料有缺口' : onResearch ? '尚无有效 AI 价位' : '无可展示的旧版价位'}</p>
    {!result?.context && <p className="as-footnote">{onResearch?'需要最近120个完整交易日的原始与复权日线；资料补齐后，手动生成研究才会显示未来情景价位。':'旧版价位依赖最近120个完整交易日的原始与复权日线；缺少该价格版本的旧结果。当前综合情景请查看图表上方。'}</p>}
    {result?.context && !levels && !result.forecasts?.length && <p className="as-footnote">{onResearch?'价格资料已就绪，但尚未生成通过校验的 AI 买卖区间与未来情景。':'该价格版本下无有效旧版情景；当前综合结果请查看图表上方。'}</p>}
    {result?.context && <p className="as-footnote">锚点 {result.context.anchor_date} · 参考 ¥{price(result.context.reference_price)} · {result.model || '未生成'}<br/>生成 {result.generated_at || '—'}</p>}
    {levels && <>
      <button className="am-level" onClick={() => onHighlight('ai-entry')}><span>AI 买入观察区间</span><strong>¥{price(levels.entry_low)} – {price(levels.entry_high)}</strong></button>
      <button className="am-level" onClick={() => onHighlight('ai-stop')}><span>AI 止损参考</span><strong>¥{price(levels.stop_reference)}</strong></button>
      <button className="am-level" onClick={() => onHighlight('ai-sell')}><span>AI 卖出观察区间</span><strong>¥{price(levels.sell_low)} – ¥{price(levels.sell_high)}</strong></button>
      <p className="as-footnote">研究期 {levels.horizon_sessions} 交易日<br/>成立：{levels.conditions.join('；')}<br/>失效：{levels.invalidation.join('；')}<br/>来源：{levels.sources.join(', ')}</p>
    </>}
    {result?.forecasts?.map(forecast => <button className="am-level" key={`${forecast.horizon_sessions}-${forecast.scenario}`} onClick={() => onHighlight(`ai-${forecast.horizon_sessions}-${forecast.scenario}`)}>
      <span>{forecast.horizon_sessions} 日 · {{ bear: '谨慎', base: '中性', bull: '积极' }[forecast.scenario]}情景</span>
      <strong>¥{price(forecast.low)} – ¥{price(forecast.high)}</strong>
      <small>{forecast.conditions.join('；')} [{forecast.sources.join(', ')}]</small>
    </button>)}
    <h3>规则与账户约束</h3>
    {riskReasons.length ? riskReasons.map(reason => <p className="as-footnote" key={reason}>{reason}</p>) : <p className="as-footnote">未通过规则和账户核实的股票仅供研究。</p>}
    {(result?.limitations || ['目标价没有保证，当前没有验证出的盈利优势']).map(limit => <p key={limit} className="as-footnote">{limit}</p>)}
  </aside>;
}
