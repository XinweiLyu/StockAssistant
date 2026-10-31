import { useEffect, useRef, useState } from 'react';
import { aShareMarketApi } from '../../api/aShareMarket';
import type { CatalogPage, Sector } from '../../types/aShareMarket';

type Props = {
  onSelectStock: (code: string) => void;
  selectedCode?: string;
  reloadRevision?: number;
  watchlistSignature?: string;
  industry?: Sector;
  concept?: Sector;
  industries: Sector[];
  concepts: Sector[];
  sectorStatus: 'loading' | 'failed' | 'ready';
  onSelectIndustry: (sector?: Sector) => void;
  onSelectConcept: (sector?: Sector) => void;
  onClearSector: () => void;
  onRefreshSectors?: () => void;
};

export default function MarketStockBrowser({
  onSelectStock, selectedCode, industry, concept, industries, concepts, sectorStatus,
  onSelectIndustry, onSelectConcept, onClearSector, onRefreshSectors, reloadRevision=0, watchlistSignature='',
}: Props) {
  const [q, setQ] = useState('');
  const [scope, setScope] = useState('all');
  const watchlistKey = scope === 'watchlist' ? watchlistSignature : '';
  const [board, setBoard] = useState('');
  const [sort, setSort] = useState('change');
  const [paging, setPaging] = useState({ filter: '', page: 1 });
  const [retry, setRetry] = useState(0);
  const [membershipRetry, setMembershipRetry] = useState(0);
  const [membership, setMembership] = useState<{ filter: string; state: 'pending' | 'ready' | 'failed'; error?: string; cached?: boolean }>({ filter: '', state: 'ready' });
  const refreshMembers = useRef<string | undefined>(undefined);
  const lastChecked = useRef(0);
  const [unknown, setUnknown] = useState(false);
  const industryId = unknown ? undefined : industry?.sector_id;
  const conceptId = concept?.sector_id;
  const filterKey = [industryId, conceptId].join('|');
  const page = paging.filter === filterKey ? paging.page : 1;
  const setPage = (value: number | ((current: number) => number)) =>
    setPaging({ filter: filterKey, page: typeof value === 'function' ? value(page) : value });
  const key = JSON.stringify([q, scope, board, sort, page, industry?.sector_id, concept?.sector_id, unknown]);
  const [saved, setSaved] = useState<{ key: string; result?: CatalogPage; error?: string; checkedAt?: number }>({ key: '' });
  const industryOptions = industry && !industries.some(s => s.sector_id === industry.sector_id) ? [industry, ...industries] : industries;
  const conceptOptions = concept && !concepts.some(s => s.sector_id === concept.sector_id) ? [concept, ...concepts] : concepts;

  useEffect(() => {
    const selected = [industryId, conceptId].filter((id): id is string => Boolean(id));
    if (!selected.length) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let busy = false;
    let signature = '';
    let force = refreshMembers.current === filterKey;
    refreshMembers.current = undefined;
    const check = async () => {
      if (busy || controller.signal.aborted) return;
      busy = true;
      if (timer) clearTimeout(timer);
      let delay = 30000;
      try {
        const refresh = force;
        force = false;
        const pages = await Promise.all(selected.map(id => aShareMarketApi.members(id, { page: 1, page_size: 1, ...(refresh ? {refresh:true} : {}) }, controller.signal)));
        if (controller.signal.aborted) return;
        const ready = pages.every(value => value.membership.state === 'ready');
        const failed = pages.find(value => value.membership.error || value.membership.state === 'failed');
        if (failed) {
          setMembership({filter:filterKey,state:'failed',cached:ready,error:failed.membership.error||'来源暂不可用，请重试'});
        } else if (ready) {
          setMembership({ filter: filterKey, state: 'ready' });
        } else {
          setMembership({ filter: filterKey, state: 'pending' });
        }
        if (ready) {
          const next = pages.map(value => value.membership.version).join('|');
          if (next !== signature) { signature = next; setRetry(value => value + 1); }
        }
        delay = failed ? 30000 : !ready || pages.some(value => value.membership.refreshing) ? 5000 : 5 * 60 * 1000;
      } catch (error) {
        if (!controller.signal.aborted) setMembership({ filter: filterKey, state: 'failed', error: error instanceof Error ? error.message : '板块成员资料未取得' });
      } finally {
        busy = false;
        if (!controller.signal.aborted) timer = setTimeout(() => {
          if (document.visibilityState === 'visible') void check();
        }, delay);
      }
    };
    const onVisible = () => { if (document.visibilityState === 'visible') void check(); };
    document.addEventListener('visibilitychange', onVisible);
    void check();
    return () => { controller.abort(); if (timer) clearTimeout(timer); document.removeEventListener('visibilitychange', onVisible); };
  }, [industryId, conceptId, filterKey, membershipRetry]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void aShareMarketApi.stocks({
        q, scope, board: board || undefined, sort, page, page_size: 50,
        industry_id: unknown ? '__unknown__' : industry?.sector_id,
        concept_id: concept?.sector_id,
      }, controller.signal).then(result => {
        if (!controller.signal.aborted) {
          const lastPage = Math.max(1, Math.ceil(result.total / 50));
          if (scope === 'watchlist' && page > lastPage) {
            setPaging({ filter: filterKey, page: lastPage });
            return;
          }
          lastChecked.current = Date.now();
          setSaved({ key, result, checkedAt: lastChecked.current });
        }
      }).catch(error => {
        if (!controller.signal.aborted) {
          lastChecked.current = Date.now();
          const message = error instanceof Error ? error.message : '目录查询未完成';
          setSaved(previous => previous.key === key
            ? { ...previous, error: message, checkedAt: lastChecked.current }
            : { key, error: message, checkedAt: lastChecked.current });
        }
      });
    }, 200);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [q, scope, board, sort, page, industry, concept, key, retry, unknown, reloadRevision, watchlistKey, filterKey]);

  useEffect(() => {
    lastChecked.current = Date.now();
    const refresh = () => setRetry(value => value + 1);
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
    }, 5 * 60 * 1000);
    const onVisible = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastChecked.current >= 5 * 60 * 1000) refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', onVisible); };
  }, []);

  const result = saved.key === key ? saved.result : undefined;
  const membershipState = industryId || conceptId ? membership.filter === filterKey ? membership.state : 'pending' : 'ready';
  return <aside className="am-stock-browser">
    <div className="am-scope">{[['all', '全部股票'], ['candidates', '规则候选'], ['watchlist', '自选股票']].map(([value, name]) =>
      <button key={value} aria-pressed={scope === value} onClick={() => { setScope(value); setPage(1); }}>{name}</button>)}</div>
    <input className="am-search" aria-label="搜索股票" value={q} placeholder="代码或股票名称" onChange={e => { setQ(e.target.value); setPage(1); }} />
    <div className="am-toolbar">
      <select aria-label="股票市场" value={board} onChange={e => { setBoard(e.target.value); setPage(1); }}><option value="">所有市场</option><option value="main">沪深主板</option><option value="growth">创业板</option><option value="star">科创板</option><option value="beijing">北交所</option><option value="unknown">市场待核实</option></select>
      <select aria-label="股票排序" value={sort} onChange={e => { setSort(e.target.value); setPage(1); }}><option value="change">涨跌幅</option><option value="amount">成交额</option><option value="code">代码</option><option value="name">名称</option></select>
    </div>
    <div className="am-sector-selects">
      <label>行业<select aria-label="行业筛选" onFocus={onRefreshSectors} value={industryId || ''} onChange={e => { onSelectIndustry(industryOptions.find(s => s.sector_id === e.target.value)); setUnknown(false); setPage(1); }}><option value="">全部行业</option>{industryOptions.map(s => <option key={s.sector_id} value={s.sector_id}>{s.name}</option>)}</select></label>
      <label>概念<select aria-label="概念筛选" onFocus={onRefreshSectors} value={concept?.sector_id || ''} onChange={e => { onSelectConcept(conceptOptions.find(s => s.sector_id === e.target.value)); setUnknown(false); setPage(1); }}><option value="">全部概念</option>{conceptOptions.map(s => <option key={s.sector_id} value={s.sector_id}>{s.name}</option>)}</select></label>
    </div>
    <p className="as-footnote am-sector-hint" role={sectorStatus === 'failed' ? 'status' : undefined}>{sectorStatus === 'failed' ? '板块目录更新失败；保留已取得的选项，可点击“刷新筛选项”重试。' : '行业与概念取交集；选择后按需获取成员，完成后自动更新。'}</p>
    {onRefreshSectors && <button className="am-button" onClick={onRefreshSectors}>刷新筛选项</button>}
    <p className="as-footnote am-auto-refresh">股票列表每 5 分钟自动检查；{saved.key === key && saved.checkedAt ? `最近检查 ${new Date(saved.checkedAt).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' })}` : '等待首次检查'}。报价以数据源时间为准。</p>
    <label className="am-checkbox"><input aria-label="未知行业" type="checkbox" checked={unknown} onChange={e => { setUnknown(e.target.checked); if(e.target.checked) onSelectIndustry(undefined); setPage(1); }} />仅看行业未归类</label>
    {(industry || concept) && <button className="am-button am-clear-sectors" onClick={() => { onClearSector(); setUnknown(false); setPage(1); }}>清除板块筛选</button>}
    {membershipState === 'pending' && <p className="as-footnote" role="status">正在获取板块成分股，完成后自动更新股票列表…</p>}
    {membershipState === 'failed' && <p role="alert">板块成分股更新失败：{membership.error}。{membership.cached ? '正在显示上一版成员缓存。' : '成员资料尚未取得，此时空列表不代表板块没有股票。'}<button onClick={() => { refreshMembers.current = filterKey; setMembershipRetry(value => value + 1); }}>重试板块成员</button></p>}
    {saved.key === key && saved.error && <p role="alert">{saved.error}；如仍显示股票，列表为上次成功获取的缓存。<button onClick={() => setRetry(value => value + 1)}>重试目录</button></p>}
    <div className="am-stock-list">{result?.items?.map(stock => <button className={selectedCode === stock.code ? 'active' : ''} key={stock.code} aria-label={`${stock.name} ${stock.code}`} onClick={() => onSelectStock(stock.code)}><span><b>{stock.name}</b><small>{stock.code} · {stock.identity_verified ? '已核实' : stock.demo ? '虚构' : '身份待核实'}</small></span><span className={stock.quote?.change == null ? '' : stock.quote.change >= 0 ? 'am-up' : 'am-down'}><b>{stock.quote?.price?.toFixed(2) ?? '—'}</b><small>{stock.quote?.change == null ? '资料不足' : `${stock.quote.change >= 0 ? '+' : ''}${(stock.quote.change * 100).toFixed(2)}%`}</small></span></button>)}</div>
    {!result?.items?.length && membershipState === 'ready' && <p className="as-footnote">{result ? '所选范围暂无匹配股票；行业与概念取交集，可清除一个板块或调整搜索、市场、候选范围。' : '查询目录…'}</p>}
    <div className="am-pagination"><button disabled={page <= 1} onClick={() => setPage(current => current - 1)}>上页</button><span>{page} / {Math.max(1, Math.ceil((result?.total || 0) / 50))} · {result?.total || 0} 只</span><button disabled={page * 50 >= (result?.total || 0)} onClick={() => setPage(current => current + 1)}>下页</button></div>
  </aside>;
}
