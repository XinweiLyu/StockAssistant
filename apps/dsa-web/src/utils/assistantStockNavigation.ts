export type AssistantMarket = 'cn' | 'hk' | 'us';

function isAssistantMarket(market: string): market is AssistantMarket {
  return market === 'cn' || market === 'hk' || market === 'us';
}

export function canonicalAssistantStock(market: string, value?: string | null): string | undefined {
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

export function assistantStockHref(market: string, value?: string | null): string | undefined {
  const code = canonicalAssistantStock(market, value);
  return code ? `/assistant?${new URLSearchParams({ market, stock: code })}` : undefined;
}

export function readAssistantStockLink(params: URLSearchParams): { market: AssistantMarket; code: string } | undefined {
  const market = params.get('market') || '';
  if (!isAssistantMarket(market)) return undefined;
  const code = canonicalAssistantStock(market, params.get('stock'));
  return code ? { market, code } : undefined;
}
