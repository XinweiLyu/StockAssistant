import type { NewsItem } from '../../api/intelligence';
import { assistantStockHref } from '../../utils/assistantStockNavigation';

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

export function newsStockLink(item: NewsItem) {
  return item.scope_type === 'symbol' ? assistantStockHref(item.market, item.scope_value) : undefined;
}
