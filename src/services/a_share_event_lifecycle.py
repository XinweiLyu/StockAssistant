"""Conservative evidence review windows, never estimates of causal effect duration."""
from datetime import datetime
from math import isfinite
import re

from src.schemas.a_share_integrated import stamp, earnings_stage

# Operational review policies, not fitted holding periods or return forecasts.
REVIEW_SESSIONS = {'earnings': 120, 'order': 250, 'policy': 250,
                   'buyback': 120, 'ownership': 60, 'regulatory': 250, 'disclosure': 20}


def event_anchor_index(published_at, calendar):
    published = stamp(published_at)
    if not published:
        return None
    day = published[:10]
    after_close = datetime.fromisoformat(published).hour >= 15
    before = [i for i, d in enumerate(calendar) if d <= day] if after_close else [i for i, d in enumerate(calendar) if d < day]
    return before[-1] if before else None


def annotate_lifecycle(event, calendar, anchor_date):
    days = sorted(set(d for d in calendar if d <= anchor_date))
    published = stamp(event.get('published_at'))
    index = event_anchor_index(published, days)
    age = len(days)-1-index if index is not None else None
    window = REVIEW_SESSIONS.get(event.get('kind'), 20)
    verified = bool(event.get('public_verified'))
    withdrawn = event.get('extraction_status') == 'withdrawn' or bool(re.search(r'撤销|撤回|作废', event.get('title', '')))
    # Persist unresolved risk for investigation, without assuming its direction or impact size.
    risk_words = r'立案|诉讼|仲裁|处罚|涉嫌|违规|调查|退市|监管函|警示函'
    risk_title = re.sub(r'(?:不存在|未被|未受到|无重大|无新增)[^，。；;]{0,60}(?:'+risk_words+r')', '', event.get('title', ''))
    risk = event.get('kind') == 'regulatory' and bool(re.search(risk_words, risk_title))
    # freeze enforces known-as-of cutoff. Weekend/intraday news can use the last close.
    usable = age is not None
    within = usable and age <= window
    tracking = bool(usable and not withdrawn and (within or risk))
    state = ('withdrawn' if withdrawn else 'unanchored' if not usable else
             'needs_text' if tracking and not verified else 'needs_review' if tracking and not within else
             'tracking' if tracking else 'background')
    strength = event.get('intensity')
    quantified = isinstance(strength, (int, float)) and not isinstance(strength, bool) and isfinite(strength)
    reason = {'withdrawn': '已撤回，不能沿用原催化判断', 'unanchored': '缺少事件前价格或尚未形成完整收盘锚点',
              'needs_text': '需补齐公告原文后判断兑现状态', 'needs_review': '风险尚无已核对的解除证据，需继续核查',
              'tracking': '处于类型核查周期；仍需验证兑现、预期差及已反映涨幅',
              'background': '超过核查周期且无已核对的新进展，仅作历史背景'}[state]
    return event | dict(age_sessions=age, review_sessions=window, lifecycle_state=state,
        tracking_active=tracking, active_catalyst=bool(within and not withdrawn and verified and quantified
            and event.get('direction') in ('positive', 'negative', 'neutral')),
        review_reason=reason, duration_estimated=False)


def annotate_lifecycles(events, calendar, anchor_date):
    """Known later results retire same-period guidance without inventing consensus surprise."""
    result = [annotate_lifecycle(e, calendar, anchor_date) for e in events]
    def stage(event):
        return earnings_stage(event.get('title',''))
    for event in result:
        if event.get('kind') != 'earnings' or not event.get('report_period') or not stage(event):
            continue
        replacements = [e for e in result if e.get('code') == event.get('code') and
            e.get('kind') == 'earnings' and e.get('report_period') == event['report_period'] and
            stage(e) > stage(event) and e.get('published_at', '') >= event.get('published_at', '')]
        if replacements:
            newer = max(replacements, key=lambda e: e.get('published_at', ''))
            event.update(tracking_active=False, active_catalyst=False, lifecycle_state='superseded',
                superseded_by=newer['id'], review_reason='同报告期已有后续业绩披露，须核对新原文，不再沿用旧预告为独立催化')
    return result
