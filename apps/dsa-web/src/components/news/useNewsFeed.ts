import { useCallback, useEffect, useRef, useState } from 'react';
import { intelligenceApi, type NewsItem, type NewsMarket, type NewsRefresh, type NewsSource, type NewsView } from '../../api/intelligence';
import { workspaceWatchlist } from '../../api/marketWorkspace';
import { toApiErrorMessage } from '../../api/error';

export function useNewsFeed(market: NewsMarket, view: NewsView, query: string, days: number, page: number, source: string) {
  const [items, setItems] = useState<NewsItem[]>([]), [total, setTotal] = useState(0);
  const [sources, setSources] = useState<NewsSource[]>([]), [status, setStatus] = useState<NewsRefresh | null>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [emptyWatchlist, setEmptyWatchlist] = useState(false), [watchlistLimited, setWatchlistLimited] = useState(false);
  const [revision, setRevision] = useState(0);
  const previousFilter = useRef('');
  const reload = useCallback(() => setRevision(value => value + 1), []);

  useEffect(() => {
    let disposed = false, inFlight = false;
    let controller: AbortController | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const filter = JSON.stringify([market, view, query, days, page, source]);
    if (previousFilter.current !== filter) {
      setItems([]); setTotal(0); setEmptyWatchlist(false);
      previousFilter.current = filter;
    }
    setError(''); setLoading(true);
    const visible = () => document.visibilityState !== 'hidden';
    const tick = async (refreshSources: boolean) => {
      if (disposed || inFlight || !visible()) return;
      inFlight = true;
      const active = new AbortController(); controller = active;
      let running = false;
      try {
        const [nextSources, nextStatus, codes] = await Promise.all([
          intelligenceApi.sources(active.signal), intelligenceApi.status(active.signal),
          view === 'watchlist' ? workspaceWatchlist.get(market, active.signal) : Promise.resolve<string[]>([]),
        ]);
        if (disposed || active.signal.aborted) return;
        const params: Record<string, string | number | boolean> = {
          market, include_global: view !== 'watchlist', query, days, page, page_size: 20,
        };
        if (view === 'hot') params.source_type = 'newsnow';
        if (source) params.source_id = source;
        const empty = view === 'watchlist' && codes.length === 0;
        if (view === 'watchlist') params.symbols = codes.slice(0, 100).join(',');
        const result = empty ? { items: [], total: 0 } : await intelligenceApi.items(params, active.signal);
        if (disposed || active.signal.aborted) return;
        setItems(result.items); setTotal(result.total); setSources(nextSources);
        setEmptyWatchlist(empty); setWatchlistLimited(codes.length > 100);
        let currentStatus = nextStatus;
        if (refreshSources && nextSources.some(item => item.enabled)) {
          currentStatus = await intelligenceApi.refresh(active.signal);
          if (disposed || active.signal.aborted) return;
        }
        setStatus(currentStatus); running = currentStatus.running; setError('');
      } catch (err) {
        if (!disposed && !active.signal.aborted) setError(toApiErrorMessage(err));
      } finally {
        inFlight = false;
        if (!disposed && !active.signal.aborted) setLoading(false);
        if (!disposed && visible()) timer = setTimeout(() => void tick(!running), active.signal.aborted ? 0 : running ? 2000 : 300000);
      }
    };
    const onVisibility = () => {
      clearTimeout(timer);
      if (!visible()) controller?.abort();
      else if (!inFlight) void tick(true);
    };
    document.addEventListener('visibilitychange', onVisibility);
    void tick(true);
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); document.removeEventListener('visibilitychange', onVisibility); };
  }, [market, view, query, days, page, source, revision]);
  return { items, total, sources, status, loading, error, emptyWatchlist, watchlistLimited, reload };
}
