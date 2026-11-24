import type { NewsItem, NewsMarket } from '../../api/intelligence';

export function safeNewsUrl(value: string) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

export function newsTime(value?: string | null, publication = false) {
  if (!value) return publication ? '发布时间未知' : '采集时间未知';
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    return `${value.replace('T', ' ').slice(0, 19)}${publication ? '（时区未标注）' : '（服务时间；时区未标注）'}`;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间无效' : `${date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })} 北京时间`;
}

export function canonicalNewsStock(market: string, value?: string | null): string | undefined {
  const upper = (value || '').trim().toUpperCase();
  if (market === 'cn') {
    const code = upper.replace(/^CN:/, '');
    return /^\d{6}$/.test(code) ? code : undefined;
  }
  if (market === 'us') {
    const code = upper.replace(/^US:/, '');
    return /^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,3})?$/.test(code) ? `us:${code.replace('-', '.')}` : undefined;
  }
  if (market === 'hk') {
    const code = upper.replace(/^HK:?/, '').replace(/\.HK$/, '');
    return /^\d{1,5}$/.test(code) && Number(code) > 0 ? `hk:${code.padStart(5, '0')}` : undefined;
  }
}

export function newsStockLink(item: NewsItem) {
  const code = item.scope_type === 'symbol' ? canonicalNewsStock(item.market, item.scope_value) : undefined;
  return code ? `/assistant?${new URLSearchParams({ market: item.market, stock: code })}` : undefined;
}

export function readNewsStockLink(params: URLSearchParams): { market: NewsMarket; code: string } | undefined {
  const market = params.get('market') || '';
  const code = canonicalNewsStock(market, params.get('stock'));
  return code ? { market: market as NewsMarket, code } : undefined;
}
