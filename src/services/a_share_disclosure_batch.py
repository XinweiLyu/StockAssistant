"""Incremental, bounded PDF acquisition shared by root and peer preparation jobs."""
from copy import deepcopy
from datetime import datetime, timedelta

from src.schemas.a_share_integrated import stamp
from src.services.a_share_event_lifecycle import annotate_lifecycle
from data_provider.a_share_disclosures import full_report_kind


def prepare_disclosure_batch(events, previous, now, calendar, anchor_date, fetch, limit=6, purpose='trading'):
    items = deepcopy(events)
    old_by_id = {e['id']: e for e in previous}
    retry_after = datetime.fromisoformat(stamp(now)) - timedelta(hours=1)
    candidates, waiting = [], 0
    for event in items:
        old = old_by_id.get(event['id'], {})
        # A changed original URL/time is a different document, even if a provider reused its ID.
        if old.get('url') == event.get('url') and old.get('published_at') == event.get('published_at'):
            for key in ('text', 'text_status', 'text_hash', 'text_attempted_at', 'text_attempts','text_pages','text_truncated','text_reason'):
                if key in old:
                    event[key] = old[key]
        if event.get('text_status') == 'ready' and event.get('text'):
            continue
        attempted = stamp(event.get('text_attempted_at'))
        if attempted and datetime.fromisoformat(attempted) > retry_after:
            waiting += 1
            continue
        candidates.append(event)
    def priority(e):
        tracking = current_review(e)
        rank = {'earnings': 0, 'order': 1, 'regulatory': 2, 'policy': 3, 'buyback': 4, 'ownership': 5}.get(e.get('kind'), 6)
        return (not tracking, rank, -(int((e.get('published_at') or '1900-01-01')[:10].replace('-', ''))))
    def current_review(e):
        lifecycle = annotate_lifecycle(e, calendar, anchor_date)
        return lifecycle['tracking_active'] and lifecycle['age_sessions'] <= lifecycle['review_sessions']
    # New documents precede retries, so a failed PDF cannot starve later documents.
    fresh = sorted([e for e in candidates if not e.get('text_attempted_at')], key=priority)
    retries = sorted([e for e in candidates if e.get('text_attempted_at')], key=lambda e: e['text_attempted_at'])
    current = [e for e in fresh if current_review(e)]
    archive = [e for e in fresh if e not in current]
    # Reserve one slot for the historical library when both queues have work.
    selected = current[:max(1, limit-1)] if archive and current and limit > 1 else current[:limit]
    selected += archive[:max(0, limit-len(selected))]
    selected += [e for e in current if e not in selected][:max(0, limit-len(selected))]
    selected += retries[:max(0, limit-len(selected))]
    if purpose=='value':
        # Short-lived catalysts must not starve the audited annual report.
        eligible=sorted(candidates,key=lambda e:e.get('published_at') or '',reverse=True)
        import re
        essential=[]
        for kind in ('annual','interim'):
            found=next((e for e in eligible if full_report_kind(e.get('title',''))==kind),None)
            if found: essential.append(found)
        half=next((e for e in eligible if full_report_kind(e.get('title','')) and '半年度报告' in e.get('title','')),None)
        if half and half not in essential: essential.append(half)
        patterns=[r'回购.*进展|发行.*结果|股本.*变动',r'回购报告书|回购.*方案|股份.*注销',
            r'股东回报规划|现金分红政策|权益分派实施']
        for pattern in patterns:
            found=next((e for e in eligible if re.search(pattern,e.get('title',''))),None)
            if found and found not in essential: essential.append(found)
        selected=(essential+ [e for e in selected if e not in essential])[:limit]
    for event in selected:
        try:
            doc = fetch(event['url'], event['published_at'][:10])
        except Exception:
            doc = dict(status='failed')
        text = doc.get('text') or ''
        event.update(text=text, text_status='ready' if doc.get('status') == 'ready' and text else doc.get('status') if doc.get('status') != 'ready' else 'empty',
            text_hash=doc.get('content_hash'), text_attempted_at=stamp(now), text_attempts=event.get('text_attempts', 0)+1,
            text_pages=doc.get('pages'),text_truncated=doc.get('truncated'),text_reason=doc.get('reason'))
    ready = sum(e.get('text_status') == 'ready' and bool(e.get('text')) for e in items)
    return items, dict(texts=ready, attempted=len(selected), pending=len(items)-ready,
        retry_wait=waiting, batch_limit=limit)
