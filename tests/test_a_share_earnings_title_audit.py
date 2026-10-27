"""Disclosure schedules are not new earnings statements or reporting stages."""
import pytest

from src.schemas.a_share_integrated import earnings_stage
from src.services.a_share_event_cases import effective_event_families
from src.services.a_share_event_lifecycle import annotate_lifecycles


ADMINISTRATIVE_TITLES = [
    '关于延期披露2026年半年度报告的公告',
    '关于延迟披露2026年半年度报告的公告',
    '关于2026年半年度报告延期披露的公告',
    '关于2026年半年度报告披露延期的公告',
    '关于2026年半年度报告预约披露的公告',
    '关于2026年半年度报告披露预约的公告',
    '关于变更2026年半年度报告披露时间的公告',
    '关于2026年半年度报告披露日期调整的公告',
    '关于2026年半年度报告披露时间变更的更正公告',
    '关于2026年半年度报告披露安排的公告',
    '关于延期披露2026年半年度业绩预告的公告',
    '关于2026年半年度业绩快报披露时间调整的公告',
    '关于延期2026年半年度报告披露的公告',
    '关于延期2026年半年度报告的披露的公告',
    '关于调整2026年半年度报告披露日的公告',
    '关于2026年半年度报告延期的公告',
    '关于召开2026年半年度报告业绩说明会的公告',
    '关于2026年半年度报告业绩说明会召开情况的公告',
    '关于2026年半年度报告业绩说明会举办结果的公告',
    '关于参加2026年半年度报告网上业绩说明会的公告',
    '关于2026年半年度报告业绩集体说明会的公告',
    '关于举行2026年半年度报告投资者交流会的通知',
    '关于2026年半年度报告投资者交流的通知',
    '关于举办2026年半年度报告投资者交流活动的公告',
    '关于2026年半年度报告投资者交流会召开结果的公告',
    '关于2026年半年度报告投资者关系活动的公告',
    '关于2026年半年度报告业绩说明会征集问题的公告',
]


@pytest.mark.parametrize('title', ADMINISTRATIVE_TITLES + [
    '关于召开2025年年度报告业绩说明会的公告',
    '关于举办2025年年度报告暨2026年第一季度报告业绩说明会的公告',
    '关于召开2026年第一季度报告投资者交流会的通知',
])
def test_administrative_disclosure_title_has_no_earnings_stage(title):
    assert earnings_stage(title) == 0


@pytest.mark.parametrize('title,stage', [
    ('2026年半年度报告', 3),
    ('2026年半年度报告摘要', 3),
    ('2026年第三季度报告（更正后）', 3),
    ('关于2026年半年度报告的更正公告', 3),
    ('2026年半年度报告修订版', 3),
    ('2026年半年度业绩快报修正公告', 2),
    ('2026年半年度业绩预告', 1),
    ('关于2026年半年度业绩预告的修正公告', 1),
    ('关于因项目延期修正2026年半年度业绩预告的公告', 1),
    ('关于2026年半年度报告披露内容的更正公告', 3),
    ('关于2026年半年度业绩预告披露数据的修正公告', 1),
    ('关于因项目延期对2026年半年度业绩预告披露数据进行修正的公告', 1),
    ('2026年第一季度报告摘要', 3),
    ('关于因订单推迟交付修正2026年半年度业绩预告的公告', 1),
])
def test_real_statements_and_corrections_keep_their_reporting_stage(title, stage):
    assert earnings_stage(title) == stage


def guidance():
    return dict(id='guidance', code='600000', kind='earnings', family_id='legacy',
        report_period='2026-06-30', title='2026年半年度业绩预告', published_at='2026-07-10',
        text_status='ready', text='净利润同比增长50%', public_verified=True,
        direction='positive', intensity=.5)


@pytest.mark.parametrize('title', ADMINISTRATIVE_TITLES)
def test_unread_schedule_notice_does_not_supersede_outstanding_guidance(title):
    notice = guidance() | dict(id='schedule', title=title, published_at='2026-07-14',
        text_status='missing', text='', public_verified=False, intensity=None, direction='unknown')
    result = annotate_lifecycles([guidance(), notice],
        ['2026-07-10', '2026-07-13', '2026-07-14', '2026-07-15'], '2026-07-15')
    old = next(event for event in result if event['id'] == 'guidance')
    assert old['lifecycle_state'] == 'tracking'
    assert old['active_catalyst'] is True
    assert old.get('superseded_by') is None


@pytest.mark.parametrize('title,original_title', [
    ('关于延期披露2026年半年度报告的公告', '2026年半年度报告'),
    ('关于2026年半年度报告预约披露的公告', '2026年半年度报告摘要'),
    ('关于2026年半年度报告披露时间变更的公告', '2026年半年度报告（更正后）'),
    ('关于延期披露2026年半年度业绩预告的公告', '2026年半年度业绩预告'),
    ('关于2026年半年度业绩快报披露时间调整的公告', '2026年半年度业绩快报'),
    ('关于2026年半年度报告业绩说明会召开情况的公告', '2026年半年度报告'),
    ('关于举办2026年半年度报告投资者交流活动的公告', '2026年半年度报告摘要'),
    ('关于2026年半年度报告业绩说明会举办结果的公告', '2026年半年度报告（更正后）'),
])
def test_schedule_notice_does_not_replace_a_real_statement_in_its_family(title, original_title):
    statement = guidance() | dict(title=original_title)
    notice = statement | dict(id='schedule', title=title, published_at='2026-07-14',
        text_status='missing', text='')
    result = effective_event_families([statement, notice])
    assert {event['id'] for event in result} == {'guidance', 'schedule'}
    assert next(event for event in result if event['id'] == 'schedule')['family_id'] == 'schedule'


@pytest.mark.parametrize('title', ['2026年半年度报告摘要', '关于2026年半年度报告的更正公告'])
def test_actual_later_report_still_retires_guidance_before_its_text_is_available(title):
    actual = guidance() | dict(id='actual', title=title, published_at='2026-07-14',
        text_status='missing', text='', public_verified=False, intensity=None, direction='unknown')
    result = annotate_lifecycles([guidance(), actual],
        ['2026-07-10', '2026-07-13', '2026-07-14', '2026-07-15'], '2026-07-15')
    old = next(event for event in result if event['id'] == 'guidance')
    assert old['lifecycle_state'] == 'superseded'
    assert old['active_catalyst'] is False
    assert old['superseded_by'] == 'actual'
