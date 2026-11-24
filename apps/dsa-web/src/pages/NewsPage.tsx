import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, Newspaper, RefreshCw } from 'lucide-react';
import { intelligenceApi, type NewsMarket, type NewsView } from '../api/intelligence';
import { toApiErrorMessage } from '../api/error';
import { AppPage, Button } from '../components/common';
import { useNewsFeed } from '../components/news/useNewsFeed';
import { newsStockLink, newsTime, safeNewsUrl } from '../components/news/newsUtils';

const views: [NewsView, string][] = [['hot', '市场热点'], ['news', '新闻快讯'], ['watchlist', '我的自选']];
const field = 'rounded-xl border border-border bg-card px-3 py-2 text-sm text-foreground';

export default function NewsPage() {
  const [market, setMarket] = useState<NewsMarket>('cn'), [view, setView] = useState<NewsView>('hot');
  const [draft, setDraft] = useState(''), [query, setQuery] = useState(''), [days, setDays] = useState(7);
  const [page, setPage] = useState(1), [source, setSource] = useState('');
  const [acting, setActing] = useState(false), [actionError, setActionError] = useState('');
  const feed = useNewsFeed(market, view, query, days, page, source);
  const change = (fn: () => void) => { fn(); setPage(1); };
  const act = async (fn: () => Promise<unknown>) => {
    setActing(true); setActionError('');
    try { await fn(); feed.reload(); } catch (error) { setActionError(toApiErrorMessage(error)); }
    finally { setActing(false); }
  };
  const sourceRows = feed.sources.filter(row => row.market === market || row.market === 'global');
  return <AppPage className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
      <div><p className="mb-2 text-xs tracking-widest text-cyan">MARKET INTELLIGENCE</p><h1 className="flex items-center gap-2 text-2xl font-semibold"><Newspaper size={24} />热点资讯</h1><p className="mt-2 text-sm text-secondary-text">浏览市场关注、新闻和明确关联自选的资讯。页面可见时每5分钟检查，不自动调用AI。</p></div>
      <Button variant="secondary" onClick={feed.reload} disabled={feed.loading}><RefreshCw size={16} />刷新资讯</Button>
    </header>
    <div className="flex gap-5 border-b border-border" role="tablist" aria-label="资讯视图">
      {views.map(([key, name]) => <button key={key} role="tab" aria-selected={view === key} className={`border-b-2 pb-3 text-sm ${view === key ? 'border-cyan text-cyan' : 'border-transparent text-secondary-text'}`} onClick={() => change(() => { setView(key); setSource(''); })}>{name}</button>)}
    </div>
    <form className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); change(() => setQuery(draft.trim())); }}>
      <label className="grid gap-1 text-sm">市场<select className={field} value={market} onChange={event => change(() => { setMarket(event.target.value as NewsMarket); setSource(''); })}><option value="cn">A股</option><option value="hk">港股</option><option value="us">美股</option></select></label>
      <label className="grid gap-1 text-sm">来源<select className={field} value={source} onChange={event => change(() => setSource(event.target.value))}><option value="">全部来源</option>{sourceRows.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
      <label className="grid gap-1 text-sm">采集范围<select className={field} value={days} onChange={event => change(() => setDays(Number(event.target.value)))}>{[1, 3, 7, 30].map(day => <option key={day} value={day}>最近采集{day}天</option>)}</select></label>
      <label className="grid min-w-48 flex-1 gap-1 text-sm">关键词<input className={field} placeholder="搜索标题或摘要" value={draft} onChange={event => setDraft(event.target.value)} /></label><Button type="submit" variant="secondary">搜索</Button>
    </form>
    <div className="space-y-2 text-sm text-secondary-text" aria-live="polite">
      {feed.status?.running ? <p role="status">正在采集：已检查{feed.status.processed}/{feed.status.total || '待统计'}个来源；已有资讯可继续浏览。</p> : <p>已存资讯 {feed.total} 条{feed.status?.finished_at ? ` · 最近检查 ${newsTime(feed.status.finished_at)}` : ''}</p>}
      {feed.status?.failed ? <p className="text-warning">{feed.status.failed}个来源未成功，查看下方来源状态；已有资讯保留。</p> : null}
      {feed.status?.error && <p role="alert">{feed.status.error}</p>}
      {!feed.loading && !feed.sources.some(row => row.enabled) && <p>没有启用的来源；已有缓存仍可阅读，请在来源管理中添加或启用来源。</p>}
      {feed.error && <p role="alert">读取失败：{feed.error}。保留同一筛选下已加载的内容，请重试。</p>}
      {actionError && <p role="alert">{actionError}</p>}
      {feed.status?.next_allowed_at && <p>下一轮来源刷新不早于 {newsTime(feed.status.next_allowed_at)}；重复点击复用当前任务或缓存。</p>}
      {view === 'hot' && <p>聚合源的市场关注内容，可能包含快讯和热门股票；关注度不代表利好或收益。</p>}
      {view === 'watchlist' && <p>仅显示来源明确关联当前市场自选股票的资讯；市场级新闻不自动归属给个股。</p>}
      {feed.watchlistLimited && <p>当前展示前100只自选的已关联资讯。</p>}
    </div>
    <section aria-label="资讯列表" className="divide-y divide-border rounded-2xl border border-border bg-card/50">
      {feed.loading && !feed.items.length && <p role="status" className="p-6 text-secondary-text">正在读取资讯…</p>}
      {!feed.loading && !feed.items.length && <div className="p-8 text-secondary-text">{feed.emptyWatchlist ? '当前市场暂无自选股票，可先到交易助手添加。' : feed.sources.some(row => row.enabled) ? '此筛选暂无已采集资讯；可能是来源覆盖不足、尚未采集或采集失败，请查看来源状态。' : '没有启用的来源，请在下方添加免费来源或启用已有来源。'}</div>}
      {feed.items.map(item => {
        const url = safeNewsUrl(item.url), stock = newsStockLink(item);
        return <article key={item.id} className="space-y-3 p-5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-secondary-text"><span>{item.source || item.source_name || '来源未标注'}</span><span>{newsTime(item.published_at, true)}</span><span>采集 {newsTime(item.fetched_at)}</span>{item.market === 'global' && <span>全球市场背景</span>}</div>
          <h2 className="text-lg font-medium leading-relaxed">{item.title}</h2>
          {item.summary && <p className="whitespace-pre-wrap break-words text-sm leading-7 text-secondary-text">{item.summary}</p>}
          <div className="flex flex-wrap gap-5 text-sm text-cyan">{url && <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1">阅读原文<ExternalLink size={14} /></a>}{stock && <Link to={stock}>查看股票 {item.scope_value} →</Link>}</div>
        </article>;
      })}
    </section>
    <div className="flex items-center justify-between"><Button variant="ghost" disabled={page <= 1 || feed.loading} onClick={() => setPage(value => value - 1)}>上一页</Button><span className="text-sm text-secondary-text">{page} / {Math.max(1, Math.ceil(feed.total / 20))}</span><Button variant="ghost" disabled={page * 20 >= feed.total || feed.loading} onClick={() => setPage(value => value + 1)}>下一页</Button></div>
    <details className="rounded-2xl border border-border p-5" open={!feed.sources.some(row => row.enabled)}>
      <summary className="cursor-pointer font-medium">来源状态与管理 · {feed.sources.length}个来源</summary>
      <p className="my-3 text-sm text-secondary-text">复用现有RSS、Atom与NewsNow来源。未启用、连接失败和发布时间未知会分别展示；未采集不代表市场没有新闻。添加来源不会配置密钥或调用模型。</p>
      <Button size="sm" variant="secondary" disabled={acting} onClick={() => void act(intelligenceApi.addDefaults)}>添加内置免费来源</Button>
      <ul className="mt-4 divide-y divide-border">{feed.sources.map(row => <li key={row.id} className="flex flex-wrap items-start justify-between gap-3 py-4"><div><p className="text-sm font-medium">{row.name} <span className="text-secondary-text">· {row.market.toUpperCase()} · {row.source_type}</span></p><p className="mt-1 text-xs text-secondary-text">{!row.enabled ? '未启用' : row.last_status === 'failed' ? '采集失败' : row.last_status === 'success' ? '上次采集成功' : '尚未采集'} · {newsTime(row.last_fetched_at)}</p>{row.last_error && <p className="mt-1 max-w-2xl break-words text-xs text-warning">{row.last_error}</p>}</div><label className="flex items-center gap-2 text-sm"><input type="checkbox" aria-label={`启用 ${row.name}`} checked={row.enabled} disabled={acting} onChange={event => void act(() => intelligenceApi.toggle(row.id, event.target.checked))} />启用</label></li>)}</ul>
    </details>
  </AppPage>;
}
