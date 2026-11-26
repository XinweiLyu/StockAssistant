import { describe, expect, it } from 'vitest';
import { canonicalAssistantStock, readAssistantStockLink } from '../../utils/assistantStockNavigation';
import { newsTime } from './newsUtils';

describe('news identity and time provenance', () => {
  it.each([['hk', '00000'], ['us', 'ABCDEFGHIJK'], ['us', 'ABC.ABCD']])('rejects unsupported identity %s:%s', (market, code) => {
    expect(canonicalAssistantStock(market, code)).toBeUndefined();
  });
  it('uses the same class-share identity as the assistant', () => {
    expect(canonicalAssistantStock('us', 'BRK-B')).toBe('us:BRK.B');
    expect(canonicalAssistantStock('hk', '700')).toBe('hk:00700');
    expect(readAssistantStockLink(new URLSearchParams('market=hk&stock=us:AAPL'))).toBeUndefined();
  });
  it('does not invent UTC for a stored timestamp with no offset', () => {
    expect(newsTime('2026-11-24T09:30:00', true)).toContain('时区未标注');
    expect(newsTime('2026-11-24T09:30:00', true)).not.toContain('UTC');
    expect(newsTime('2026-11-24T01:30:00Z', true)).toContain('北京时间');
  });
});
