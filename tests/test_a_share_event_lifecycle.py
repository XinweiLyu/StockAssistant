from datetime import date, timedelta
import pytest

from src.services.a_share_event_lifecycle import annotate_lifecycle
from src.services.a_share_disclosure_batch import prepare_disclosure_batch
from src.services.a_share_event_cases import event_context, match_event_cases


def calendar():
    return [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(400)]


def test_earnings_older_than_twenty_sessions_remain_under_review_but_not_forever():
    days = calendar()
    event = dict(id='earnings', kind='earnings', published_at=days[50], text_status='ready',
                 public_verified=True, direction='positive', intensity=.5, title='业绩预告')
    current = annotate_lifecycle(event, days, days[110])
    assert current['age_sessions'] == 60
    assert current['tracking_active'] and current['active_catalyst']
    assert current['lifecycle_state'] == 'tracking'
    assert not annotate_lifecycle(event, days, days[250])['active_catalyst']
    assert not annotate_lifecycle(dict(event, text_status='missing', public_verified=False), days, days[110])['active_catalyst']
    assert not annotate_lifecycle(dict(event, title='撤回业绩预告'), days, days[110])['active_catalyst']


def test_unresolved_old_regulatory_risk_is_still_visible_without_inventing_alpha():
    days = calendar()
    event = dict(kind='regulatory', title='收到立案告知书', published_at=days[10], public_verified=True)
    result = annotate_lifecycle(event, days, days[390])
    assert result['tracking_active']
    assert result['lifecycle_state'] == 'needs_review'
    assert not result['active_catalyst']


def test_same_age_remaining_return_can_start_sixty_sessions_after_announcement():
    days = calendar()
    rows = [dict(date=d, open=10+i, close=10+i, adjusted_close=10+i, high=11+i, low=9+i) for i,d in enumerate(days)]
    result = event_context(dict(published_at=days[20]), {'stock': rows}, days, days[-1], 60)
    assert result['outcomes']['20']['anchor_date'] == days[80]
    assert result['outcomes']['20']['stock_return'] == pytest.approx(110/90-1)
    assert '250' in result['outcomes']


def test_no_target_does_not_claim_every_historical_event_has_wrong_type():
    result = match_event_cases({}, [dict(id='historic', kind='earnings', published_at='2023-01-01')], '2024-01-01')
    assert result['status'] == 'no_target'
    assert result['excluded'] == {}
    assert result['missing_dimensions'] == []
    assert result['horizons']['20']['sample_size'] == 0


def test_ready_documents_do_not_consume_fetch_slots_and_failed_batch_does_not_starve_queue():
    days = calendar()
    events = [dict(id=str(i), title='业绩预告', kind='earnings', url='https://example/'+str(i),
                   published_at=days[80-i], text_status='missing') for i in range(10)]
    previous = [dict(events[0], text='已经保存的正文', text_status='ready', text_hash='hash')]
    calls = []
    def failed(url, day):
        calls.append(url)
        return dict(status='failed')
    first, coverage = prepare_disclosure_batch(events, previous, days[100], days, days[100], failed, limit=2)
    assert first[0]['text'] == '已经保存的正文'
    assert coverage['attempted'] == 2 and coverage['texts'] == 1
    second, _ = prepare_disclosure_batch(events, first, days[100], days, days[100], failed, limit=2)
    assert len(set(calls)) == 4
    assert second[0]['text'] == '已经保存的正文'


def test_changed_document_url_does_not_inherit_old_verified_text():
    days = calendar()
    old = dict(id='same', url='https://old', published_at=days[80], text_status='ready', text='旧原文', text_hash='old')
    new = dict(old, url='https://corrected', text_status='missing', text='')
    result, _ = prepare_disclosure_batch([new], [old], days[100], days, days[100],
        lambda *_: dict(status='ready', text='修订原文', content_hash='new'))
    assert result[0]['text'] == '修订原文'


@pytest.mark.parametrize('published', ['2026-10-17T12:00:00+08:00', '2026-10-19T09:00:00+08:00'])
def test_known_weekend_and_intraday_announcements_use_last_completed_close(published):
    days = ['2026-10-15', '2026-10-16']
    event = dict(kind='earnings',title='业绩预告',published_at=published,public_verified=True,
                 direction='positive',intensity=.4)
    result = annotate_lifecycle(event,days,'2026-10-16')
    assert result['age_sessions'] == 0
    assert result['tracking_active'] and result['active_catalyst']


@pytest.mark.parametrize('title', ['关于签署募集资金监管协议的公告', '关于公司最近五年不存在被证券监管部门处罚情况的公告',
                                  '关于股票期权激励计划获得国资监管部门批复的公告'])
def test_routine_supervision_and_explicit_absence_of_penalties_are_not_permanent_risk(title):
    days=calendar()
    event=dict(kind='regulatory',title=title,published_at=days[10],public_verified=True)
    result=annotate_lifecycle(event,days,days[390])
    assert result['lifecycle_state']=='background'
    assert not result['tracking_active']
