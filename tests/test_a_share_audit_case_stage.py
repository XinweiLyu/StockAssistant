from tests.test_a_share_outlook_api import long_market
import pytest


def case_events(days):
    common=dict(code='600000',kind='earnings',report_period='2021-03-31',text_status='ready',
                text='归属于上市公司股东的净利润同比增长50%')
    return [common|dict(id='guide',family_id='guide',title='2021年第一季度业绩预告',published_at=days[100]),
            common|dict(id='report',family_id='report',title='2021年第一季度报告',published_at=days[140])]


def test_historical_guidance_after_formal_report_is_not_still_outstanding(tmp_path):
    svc,end=long_market(tmp_path)
    days=[d for d in svc.market.calendar() if d<=end]
    library=svc.integrated._case_library('600000',case_events(days),svc.integrated._now(),None,60)
    guidance=next(e for e in library if e['id']=='guide')
    assert guidance['stage_anchor_date']==days[160]
    assert guidance['stage_state']=='superseded'


def test_report_published_after_aligned_stage_does_not_retire_guidance_early(tmp_path):
    svc,end=long_market(tmp_path)
    days=[d for d in svc.market.calendar() if d<=end]
    library=svc.integrated._case_library('600000',case_events(days),svc.integrated._now(),None,20)
    guidance=next(e for e in library if e['id']=='guide')
    assert guidance['stage_anchor_date']==days[120]
    assert guidance['stage_state']=='outstanding'


@pytest.mark.parametrize('published_time,expected', [
    ('T14:00:00+08:00','superseded'),
    ('T16:00:00+08:00','outstanding'),
    ('','outstanding'),  # A date alone does not prove availability before the close.
])
def test_stage_uses_information_known_at_close_not_later_that_evening(tmp_path,published_time,expected):
    svc,end=long_market(tmp_path)
    days=[d for d in svc.market.calendar() if d<=end]
    events=case_events(days)
    events[1]['published_at']=days[120]+published_time
    library=svc.integrated._case_library('600000',events,svc.integrated._now(),None,20)
    assert next(e for e in library if e['id']=='guide')['stage_state']==expected
