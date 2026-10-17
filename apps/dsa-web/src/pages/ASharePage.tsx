import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Download, ArrowUpRight, ChevronRight, X } from 'lucide-react';
import InvestmentWorkspace from '../components/a-share/InvestmentWorkspace';
import apiClient from '../api';
import { toApiErrorMessage } from '../api/error';
import { portfolioApi } from '../api/portfolio';
import type { PortfolioAccountItem } from '../types/portfolio';
import type { AssistantBoard, AssistantSettings, Candidate, Evidence, Journal, Observation, ResearchMode } from '../types/aShare';
import { AppPage, Button, InlineAlert, Loading } from '../components/common';
import './ASharePage.css';

const BASE = '/api/v1/a-share';
const modes: Record<ResearchMode, string> = { demo: '虚构演示', free: '免费数据', tushare2000: 'Tushare 2000积分', tushare5000: 'Tushare 5000积分' };
const states: Record<string, string> = { observe: '观察', triggered: '条件已核实', blocked: '风险阻止', expired: '已失效' };
const money = (v: number | null | undefined) => v == null ? '待补充' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
const pct = (v: number | null | undefined) => v == null ? '—' : `${(v * 100).toFixed(2)}%`;
const safeUrl = (s?: string) => { try { const u = new URL(s || ''); return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined; } catch { return undefined; } };

function ASharePage() {
  const [board, setBoard] = useState<AssistantBoard | null>(null);
  const [draft, setDraft] = useState<AssistantSettings | null>(null);
  const [tab, setTab] = useState('市场与候选');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [accounts, setAccounts] = useState<PortfolioAccountItem[]>([]);
  const [selectedCode, setSelectedCode] = useState('');
  const [selectedStrategy, setSelectedStrategy] = useState<string>();
  const [stockNavigationRevision, setStockNavigationRevision] = useState(0);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [event, setEvent] = useState<Journal<Evidence> | null>(null);
  const [eventCode, setEventCode] = useState('');
  const [eventNote, setEventNote] = useState('');
  const [constraint, setConstraint] = useState({ code: '', sellable: '', stop: '', note: '' });
  const initialized = useRef(false);
  const mounted = useRef(true);
  const refreshSequence = useRef(0);
  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    try {
      const r = await apiClient.get<AssistantBoard>(`${BASE}/dashboard`);
      if (!mounted.current || sequence !== refreshSequence.current) return;
      setBoard(r.data);
      if (!initialized.current) { setDraft(r.data.settings); initialized.current = true; }
      setError('');
    } catch (e) { if (mounted.current) setError(e instanceof Error && !('response' in e) ? e.message : toApiErrorMessage(e)); }
  }, []);
  useEffect(() => {
    mounted.current = true;
    void refresh();
    void portfolioApi.getAccounts().then(r => { if (mounted.current) setAccounts(r.accounts || []); }).catch(() => undefined);
    const timer = setInterval(() => void refresh(), 10000);
    return () => { mounted.current = false; clearInterval(timer); };
  }, [refresh]);
  const act = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true); setError('');
    try { await action(); if (message) setNotice(message); await refresh(); return true; }
    catch (e) { setError(toApiErrorMessage(e)); return false; }
    finally { setBusy(false); }
  };
  const sync = (kind: string) => act(async () => {
    const r = await apiClient.post<{ accepted: boolean }>(`${BASE}/sync?kind=${kind}`);
    if (!r.data.accepted) throw new Error('已有同步任务正在运行，请查看同步进度');
  }, '同步任务已开始。页面会自动更新进度。');
  const details = (c: Candidate) => { setStockNavigationRevision(value => value + 1); setSelectedCode(c.code); setSelectedStrategy(c.strategy); document.getElementById('am-workspace')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }); };
  const researchStock = (code: string) => void act(async () => { const r = await apiClient.post<{message?:string}>(`${BASE}/research/${code}?include_price_scenarios=true`); if (r.data?.message) setNotice(r.data.message); }, '');
  const watchStock = (code: string) => void act(() => apiClient.put(`${BASE}/settings`, { ...board?.settings, watchlist: board?.settings.watchlist.includes(code) ? board.settings.watchlist.filter(c => c !== code) : [...(board?.settings.watchlist || []), code] }), '自选列表已更新。');
  const exportFile = async (format: string, id?: number) => {
    try {
      const r = await apiClient.get(`${BASE}/export`, { params: { format, report_id: id }, responseType: 'blob' });
      const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url;
      a.download = `a-share-${id || board?.report?.as_of || 'research'}.${format === 'csv' ? 'csv' : 'md'}`;
      a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : '导出未完成'); }
  };
  const changeTab = (name: string) => {
    setTab(name);
    if (name === '复盘记录') void apiClient.get<{ items: Observation[] }>(`${BASE}/observations`).then(r => setObservations(r.data.items)).catch(e => setError(e.message));
  };
  if (!board) return <AppPage>{error ? <InlineAlert variant="danger" message={error} action={<Button onClick={() => void refresh()}>重试加载</Button>} /> : <Loading />}</AppPage>;
  const report = board.report;
  return <AppPage className="a-share-page">
    <div className="as-heading">
      <div><p className="as-eyebrow">A SHARE · RESEARCH WORKSPACE</p><h1>A股交易助手</h1><p className="as-muted">盘后研究，盘中检查。把规则、证据和账户约束放在一起。</p></div>
      <div className="as-actions"><span className="as-chip">{modes[board.settings.mode]}</span><Button size="sm" variant="secondary" onClick={() => void refresh()} aria-label="刷新页面"><RefreshCw size={15} /></Button><Button size="sm" disabled={busy || board.job.state === 'running'} onClick={() => void sync('daily')}>同步盘后研究</Button></div>
    </div>
    {board.settings.mode === 'demo' && <div className="as-demo">演示股票、行业和交易日历均为虚构样本，仅用于体验功能。</div>}
    {error && <InlineAlert variant="danger" message={error} />}
    {notice && <InlineAlert message={notice} action={<button aria-label="关闭提示" onClick={() => setNotice('')}><X size={16} /></button>} />}
    <div className="as-tabs" role="tablist">{['市场与候选', '持仓风险', '资讯证据', '复盘记录', '设置与数据'].map(name => <button role="tab" aria-selected={tab === name} className={tab === name ? 'active' : ''} key={name} onClick={() => changeTab(name)}>{name}</button>)}</div>
    {board.job.state === 'running' && <div className="as-progress" aria-live="polite"><RefreshCw size={15} className="animate-spin" /><span>{board.job.message} · {board.job.completed}/{board.job.total || '准备中'}</span></div>}
    {tab === '市场与候选' && <>
      <InvestmentWorkspace key={board.settings.mode} board={board} selectedCode={selectedCode} selectedStrategy={selectedStrategy} navigationRevision={stockNavigationRevision} onSelectStock={code => { setSelectedCode(code); setSelectedStrategy(undefined); }} onResearch={researchStock} onWatchlist={watchStock} />
      <div className="as-overview"><div><span>最近完整交易日</span><strong>{report?.as_of || '待同步'}</strong></div><div><span>市场环境</span><strong>{report?.market_ok === true ? '允许继续检查条件' : report?.market_ok === false ? '暂停新增买入条件' : '资料不足，暂停新条件'}</strong></div><div><span>同日有效样本</span><strong>{report?.sample_size || 0}<small> 只</small></strong></div><div><span>后台监控</span><strong>{board.schedule.running ? '服务运行中' : '尚未启用'}<small> · 每5分钟</small></strong></div></div>
      <div className="as-research-grid"><section><div className="as-section-heading"><div><h2>规则研究候选</h2><p>突破前一日高点且不超过1%，仍需报价、风险与账户检查。</p></div><div className="as-actions"><Button size="sm" variant="ghost" disabled={!report} onClick={() => void exportFile('csv')}><Download size={14} />CSV</Button><Button size="sm" variant="secondary" disabled={!report} onClick={() => void exportFile('markdown')}>研究报告</Button></div></div>
        {!report?.candidates.length ? <div className="as-empty"><h3>尚未生成研究候选</h3><p>先同步完整日线。真实模式需至少30只同日有效样本，条件不满足时保留空结果。</p></div> : <div className="as-table-wrap"><table className="as-table"><thead><tr><th>股票 / 规则</th><th>得分</th><th>20日表现</th><th>状态</th><th>突破观察价</th><th /></tr></thead><tbody>{report.candidates.map(c => <tr key={`${c.code}-${c.strategy}`}><td><button className="as-stock" onClick={() => void details(c)}>{c.name}<span>{c.code} · {c.strategy === 'trend_v1' ? '个股趋势' : '行业结合'}</span></button></td><td>{c.score.toFixed(1)}</td><td>{pct(c.r20)}</td><td><span className={`as-state ${c.check?.status || 'observe'}`}>{states[c.check?.status || 'observe']}</span></td><td>¥{c.high.toFixed(2)}</td><td><button aria-label={`查看${c.name}详情`} onClick={() => void details(c)}><ChevronRight size={18} /></button></td></tr>)}</tbody></table></div>}
        <div className="as-footnote">得分是研究池内的相对排名。策略尚未证明盈利优势；提示不代表成交。</div>
      </section><aside><h2>行业观察</h2><p className="as-muted">同一分类体系下比较20/60日趋势</p>{report?.sectors.slice(0, 12).map((s, i) => <div className="as-sector" key={s.code}><span className="as-sector-rank">{String(i + 1).padStart(2, '0')}</span><div><b>{s.name}</b><div className="as-bar"><div style={{ width: `${s.strength || 0}%` }} /></div></div><strong>{s.strength?.toFixed(0) || '—'}</strong></div>)}{!report?.sector_ready && <p className="as-footnote">至少10个同分类行业有完整历史后启用行业规则。</p>}<hr /><h3>当前缺失与约束</h3>{(report?.limitations || ['尚未准备好完整日线及市场基准']).map(s => <p className="as-footnote" key={s}>{s}</p>)}</aside></div>
      <section className="as-notifications"><h2>状态变化</h2>{board.alerts.slice(0, 5).map(a => <div key={a.id}><span>{a.payload.code || '研究'} · {states[a.payload.message] || a.payload.message}</span><time>{new Date(a.created_at).toLocaleString('zh-CN')}</time></div>)}{!board.alerts.length && <p className="as-muted">状态变化后记录提醒；相同状态不反复提醒。</p>}</section>
    </>}
    {tab === '持仓风险' && <section><div className="as-section-heading"><div><h2>账户与持仓约束</h2><p>{board.portfolio.demo ? '演示账户' : '使用 DSA 的手动账户与成交记录'} · 可卖数量需每日核实</p></div><Link to="/portfolio" className="as-link">录入账户 / 现金 / 成交 <ArrowUpRight size={15} /></Link></div><div className="as-overview"><div><span>参考净值（元）</span><strong>{money(board.portfolio.nav)}</strong></div><div><span>现金（元）</span><strong>{money(board.portfolio.cash)}</strong></div><div><span>账户完整度</span><strong>{board.portfolio.complete ? '已有参考数据' : '缺失项待补充'}</strong></div><div><span>单只 / 行业 / 总仓位上限</span><strong>{pct(board.settings.risk.stock_cap)} / {pct(board.settings.risk.sector_cap)} / {pct(board.settings.risk.total_cap)}</strong></div></div>
      {board.holdings.map(h => <article className="as-holding" key={h.code}><div><h3>{h.code} · {h.action}</h3><p>持股 {h.quantity} · 可卖 {h.sellable ?? '待确认'} · 止损参考 {money(h.stop)}</p><p className="as-footnote">{h.reasons.join('；') || '等待交易者自行决策'}</p></div><Button size="sm" variant="secondary" onClick={() => setConstraint({ code: h.code, sellable: h.sellable?.toString() || '', stop: h.stop?.toString() || '', note: '' })}>核实可卖数量与参考价</Button></article>)}
      {!board.holdings.length && <div className="as-empty">请先在持仓页建立账户，并在助手设置中选择该账户。</div>}
      {constraint.code && <form className="as-form" onSubmit={e => { e.preventDefault(); void act(() => apiClient.post(`${BASE}/holdings/constraints`, { code: constraint.code, sellable: constraint.sellable === '' ? null : Number(constraint.sellable), stop: constraint.stop === '' ? null : Number(constraint.stop), note: constraint.note }), '持仓核实记录已保存。').then(ok => { if (ok) setConstraint({ code: '', sellable: '', stop: '', note: '' }); }); }}><h3>{constraint.code} 人工确认</h3><label>今日可卖数量<input type="number" min="0" value={constraint.sellable} onChange={e => setConstraint({ ...constraint, sellable: e.target.value })} /></label><label>持续使用的止损参考（元）<input type="number" min="0.01" step="0.01" value={constraint.stop} onChange={e => setConstraint({ ...constraint, stop: e.target.value })} /></label><label>确认依据（修改参考价也会记录）<input required minLength={2} value={constraint.note} onChange={e => setConstraint({ ...constraint, note: e.target.value })} /></label><Button type="submit" disabled={busy}>保存人工确认</Button></form>}
    </section>}
    {tab === '资讯证据' && <section><div className="as-section-heading"><div><h2>新闻与公告</h2><p>公告标题、新闻摘要和关键词标签均需核实。未发现资讯不表示没有风险。</p></div><Button size="sm" disabled={busy || board.job.state === 'running'} onClick={() => void sync('news')}>同步资讯</Button></div>
      {board.events.map(e => <article className="as-event" key={e.id}><div><div className="as-event-meta">{e.payload.source} · {e.payload.published_at || '发布时间未知'} · {e.payload.precision === 'date' ? '仅日期' : '来源时间'} · 修订 {e.payload.revision}</div><h3>{safeUrl(e.payload.url) ? <a href={safeUrl(e.payload.url)} target="_blank" rel="noreferrer">{e.payload.title} ↗</a> : e.payload.title}</h3><p>{e.payload.content?.slice(0, 250)}</p><p className="as-footnote">{e.payload.coverage} · 首次发现 {new Date(e.payload.first_seen).toLocaleString('zh-CN')}</p><p className="as-footnote">{e.payload.verification ? `人工核实：${e.payload.verification.major_risk ? '重大风险，阻止新增买入' : '此项未确认重大风险'} · ${e.payload.verification.note}` : `待核实${e.payload.tags?.length ? ' · ' + e.payload.tags.join('、') : ''}`}</p></div><Button variant="secondary" size="sm" onClick={() => { setEvent(e); setEventCode(e.payload.verification?.code || e.payload.code || e.payload.related_code || ''); setEventNote(''); }}>核实此事件</Button></article>)}
      {!board.events.length && <div className="as-empty">暂无已获取的资讯。请同步，并查看数据状态中的覆盖与失败原因。</div>}
      {event && <form className="as-form" onSubmit={e => e.preventDefault()}><h3>核实：{event.payload.title}</h3><label>确认关联股票代码<input required value={eventCode} onChange={e => setEventCode(e.target.value)} /></label><label>核实依据<input required minLength={2} value={eventNote} onChange={e => setEventNote(e.target.value)} /></label><div className="as-actions">{[true, false].map(risk => <Button key={String(risk)} variant={risk ? 'danger-subtle' : 'secondary'} disabled={busy || eventNote.length < 2 || !eventCode} onClick={() => void act(() => apiClient.post(`${BASE}/events/${event.id}/verify`, { code: eventCode, note: eventNote, major_risk: risk }), '人工核实结果已记录。').then(ok => { if (ok) setEvent(null); })}>{risk ? '确认重大风险' : '此项未确认重大风险'}</Button>)}<Button variant="ghost" onClick={() => setEvent(null)}>取消</Button></div></form>}
    </section>}
    {tab === '复盘记录' && <section><div className="as-section-heading"><div><h2>研究记录与前瞻观察</h2><p>以保存后首个完整交易日的收盘价为参考，固定5/10/20日端点。缺失时不移到别的日期。</p></div><Link className="as-link" to="/portfolio">手动成交与成本记录 <ArrowUpRight size={15} /></Link></div>
      <div className="as-demo">候选价格表现与真实账户收益分别记录。当前没有足够样本证明收益优势。</div>
      {board.history.map(r => <div className="as-history" key={r.id}><div><strong>{r.payload.as_of} · {r.payload.candidates.length} 条规则候选</strong><p className="as-footnote">保存 {new Date(r.created_at).toLocaleString('zh-CN')} · 输入 {r.payload.input_hash.slice(0, 16)}</p></div><Button size="sm" variant="ghost" onClick={() => void exportFile('markdown', r.id)}>查看原报告</Button></div>)}
      {observations.slice(0, 20).map((o, i) => <div className="as-observation" key={`${o.report_id}-${o.code}-${o.strategy}-${i}`}><b>{o.code}</b><span>{o.strategy}</span>{o.results.map(r => <span key={r.horizon}>{r.horizon}日：{r.return == null ? '尚未到期 / 缺数据' : pct(r.return)} <small>({r.start_date || '待定'} → {r.end_date || '待定'})</small></span>)}</div>)}
      {!board.history.length && <div className="as-empty">生成研究后会保存可追溯的记录。</div>}
    </section>}
    {tab === '设置与数据' && draft && <section><div className="as-section-heading"><div><h2>数据方案与研究预算</h2><p>免费方案不需要模型密钥。积分档位与实时、资讯权限分别控制。</p></div><Link className="as-link" to="/settings">配置 Token / 模型密钥 <ArrowUpRight size={15} /></Link></div>
      <form className="as-form as-settings" onSubmit={e => { e.preventDefault(); void act(async () => { const r = await apiClient.put<AssistantSettings>(`${BASE}/settings`, draft); setDraft(r.data); }, '设置已保存；请同步所选方案的数据。'); }}>
        <label>数据方案<select value={draft.mode} onChange={e => setDraft({ ...draft, mode: e.target.value as ResearchMode })}>{Object.entries(modes).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
        <label>研究范围<select value={draft.research_scope || 'limited'} onChange={e => setDraft({ ...draft, research_scope: e.target.value as 'all' | 'limited' })}><option value="all">全目录逐步准备</option><option value="limited">限量研究池</option></select></label>
        {(draft.research_scope || 'limited') === 'limited' && <label>限量研究池上限<input type="number" min="30" max="200" value={draft.pool_size} onChange={e => setDraft({ ...draft, pool_size: Number(e.target.value) })} /></label>}
        <label>使用的手动账户<select value={draft.account_id || ''} onChange={e => setDraft({ ...draft, account_id: e.target.value ? Number(e.target.value) : null })}><option value="">未选择，仅研究</option>{accounts.filter(a => a.market === 'cn').map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
        <label>自选股票（逗号分隔）<input value={draft.watchlist.join(',')} onChange={e => setDraft({ ...draft, watchlist: e.target.value.split(/[,，\s]+/).filter(Boolean) })} placeholder="600000,000001" /></label>
        <label>盘中快照<select value={draft.snapshot_provider} onChange={e => setDraft({ ...draft, snapshot_provider: e.target.value as 'akshare' | 'tushare' })}><option value="akshare">免费行情</option><option value="tushare">Tushare rt_k（独立权限）</option></select></label>
        <label>研究模型<input value={draft.model} onChange={e => setDraft({ ...draft, model: e.target.value })} placeholder="留空沿用原设置中的模型" /></label>
        <div className="as-checkboxes">{(['realtime_entitled', 'news_entitled', 'announcements_entitled', 'free_fallback', 'research_enabled'] as const).map((key, i) => <label key={key}><input type="checkbox" checked={Boolean(draft[key])} onChange={e => setDraft({ ...draft, [key]: e.target.checked })} />{['已开通Tushare实时权限', '已开通Tushare新闻权限', '已开通Tushare公告权限', '允许已记录的免费备用源', '启用CN多角色增强研究'][i]}</label>)}</div>
        <label>自动研究每日模型调用上限（手动不限次）<input type="number" min="0" max="20" value={draft.daily_model_calls} onChange={e => setDraft({ ...draft, daily_model_calls: Number(e.target.value) })} /></label>
        {(['stock_cap', 'sector_cap', 'total_cap', 'risk_per_trade', 'commission', 'transfer_fee'] as const).map((key, i) => <label key={key}>{['单只股票上限（%）', '单行业上限（%）', '总股票仓位上限（%）', '单笔计划风险（%）', '佣金费率（%）', '过户费率（%）'][i]}<input type="number" step="0.001" min="0" max="100" value={Number((draft.risk[key] * 100).toFixed(5))} onChange={e => setDraft({ ...draft, risk: { ...draft.risk, [key]: Number(e.target.value) / 100 } })} /></label>)}
        <label>最低佣金（元）<input type="number" min="0" max="100" step="0.01" value={draft.risk.minimum_fee} onChange={e => setDraft({ ...draft, risk: { ...draft.risk, minimum_fee: Number(e.target.value) } })} /></label><div className="as-actions"><Button type="submit" disabled={busy || board.job.state === 'running'}>保存设置</Button><span className="as-muted">今日手动调用：{board.manual_model_usage??0} 次 · 自动限额计数：{board.model_usage}/{board.settings.daily_model_calls}</span></div>
      </form>
      <div className="as-section-heading"><div><h2>数据状态</h2><p>报价源时间未知时，只能观察价格条件。交易日历未覆盖时暂停新操作条件。</p></div><Button size="sm" variant="secondary" disabled={busy || board.job.state === 'running'} onClick={() => void sync('snapshot')}>检查盘中快照</Button></div>
      <div className="as-health">{Object.entries(board.sources).map(([key, value]) => <div key={key}><span>{({ daily: '日线', snapshot: '快照', news: '新闻', announcements: '公告', sector: '行业' } as Record<string, string>)[key] || key}</span><b>{value}</b><span>{board.health.find(h => h.kind === key)?.status || '待验证'}</span></div>)}</div>
      {board.health.map(h => <p className="as-footnote" key={h.kind}>{h.kind} · {h.source} · {h.fetched_at} · {h.error || h.reason || `返回${h.count ?? 0}条`}</p>)}
      {board.job.errors.map((e, i) => <p className="as-footnote" key={i}>{e}</p>)}{board.limitations.map(s => <p className="as-footnote" key={s}>{s}</p>)}
    </section>}

  </AppPage>;
}
export default ASharePage;
