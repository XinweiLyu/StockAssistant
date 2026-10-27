"""Economic meaning must be verified before a quoted number enables a strategy."""
import pytest

from src.services.a_share_event_cases import extract_event_facts
from src.services.a_share_event_lifecycle import annotate_lifecycle
from src.services.a_share_integrated_prediction import strategy_candidates


def earnings(text, **changes):
    return dict(id='event', code='600000', kind='earnings', title='2026年第三季度业绩预告',
                report_period='2026-09-30', published_at='2026-10-16', text_status='ready',
                text=text) | changes


@pytest.mark.parametrize('kind,title', [
    ('regulatory', '关于收到行政处罚决定书的公告'),
    ('order', '关于签订重大合同的公告'),
])
def test_background_profit_growth_does_not_enable_a_non_earnings_event_trade(kind, title):
    document = earnings('公司上年度净利润同比增长50%。本次事项的影响尚不确定。', kind=kind, title=title)
    event = annotate_lifecycle(extract_event_facts(document, []),
                               ['2026-10-15', '2026-10-16'], '2026-10-16')
    assert event['intensity'] is None
    assert event['extraction_status'] == 'insufficient'
    candidates = strategy_candidates(dict(events=[event], context=dict(
        identity_verified=True, st=False, board='main')), 2.)
    assert not next(c['eligible'] for c in candidates if c['strategy_kind'] == 'event_followthrough')


@pytest.mark.parametrize('text', [
    '更正前：净利润同比增长50%。更正后：净利润同比下降50%。',
    '更正后：净利润同比下降50%。更正前：净利润同比增长50%。',
    '原预计净利润同比增长50%；现预计净利润为负2亿元。',
    '修订前：净利润同比增长50%；修订后：本期预计亏损2亿元。',
])
def test_correction_comparisons_cannot_reactivate_an_old_numeric_statement(text):
    result = extract_event_facts(earnings(text, title='2026年第三季度业绩预告更正公告'), [])
    assert result['extraction_status'] == 'insufficient'
    assert result['intensity'] is None
    assert result['direction'] == 'unknown'
    assert result['evidence_quote'] is None


@pytest.mark.parametrize('text', [
    '归母净利润同比增长50%；扣除非经常性损益后的净利润同比下降30%。',
    '前三季度净利润同比增长50%；第三季度净利润同比增长10%。',
    '净利润同比增长50%。另一口径净利润同比增长50%。',
    '净利润为1亿元，营业收入同比增长50%。',
    '净利润为1亿元。每股收益同比增长50%。',
    '净利润为1亿元，销售量同比增长50%。',
    '净利润为1亿元，经营活动产生的现金流量净额同比增长50%。',
])
def test_ambiguous_or_different_metrics_do_not_become_profit_growth(text):
    result = extract_event_facts(earnings(text), [])
    assert result['intensity'] is None
    assert result['extraction_status'] == 'insufficient'


@pytest.mark.parametrize('text', [
    '上年同期净利润同比增长50%；本报告期预计亏损2亿元。',
    '去年净利润同比增长50%；本报告期业绩尚未确定。',
    '2025年净利润同比增长50%；本报告期预计亏损2亿元。',
    '2026年净利润同比增长50%；本报告期业绩尚未确定。',
    '2026年第一季度净利润同比增长50%；本报告期业绩尚未确定。',
    '2026年1-6月净利润同比增长50%；本报告期业绩尚未确定。',
])
def test_only_historical_or_other_period_growth_is_not_current_event_strength(text):
    result = extract_event_facts(earnings(text), [])
    assert result['intensity'] is None
    assert result['direction'] == 'unknown'


def test_explicitly_mixed_event_document_is_not_a_single_quantified_catalyst():
    result = extract_event_facts(earnings('净利润同比增长50%。', mixed_events=True), [])
    assert result['intensity'] is None


@pytest.mark.parametrize('text', [
    '更正前：净利润同比增长50%；更正后：净利润同比下降50%。',
    '上年同期净利润同比增长50%；本报告期预计亏损2亿元。',
    '归母净利润同比增长50%；扣非净利润同比下降30%。',
])
def test_optional_completion_cannot_cherry_pick_a_span_from_an_ambiguous_document(text):
    result = extract_event_facts(earnings(text), [], completion=lambda *_: dict(
        evidence_quote='净利润同比增长50%', intensity=.5, direction='positive'))
    assert result['intensity'] is None
    assert result['extraction_status'] == 'insufficient'


@pytest.mark.parametrize('text,amount,quote', [
    ('预计归属于上市公司股东的净利润同比增长30%至50%。', .4, '净利润同比增长30%至50%'),
    ('本报告期净利润比上年同期下降30%至50%。', -.4, '净利润比上年同期下降30%至50%'),
    ('本报告期净利润同比增长-20%。', -.2, '净利润同比增长-20%'),
    ('2026年前三季度净利润同比增长50%。', .5, '净利润同比增长50%'),
    ('2026年1-9月净利润同比增长50%。', .5, '净利润同比增长50%'),
])
def test_unambiguous_current_earnings_keeps_exact_quoted_units(text, amount, quote):
    result = extract_event_facts(earnings(text), [])
    assert result['intensity'] == pytest.approx(amount)
    assert result['intensity_unit'] == 'profit_yoy_ratio'
    assert result['evidence_quote'] == quote
    assert quote in text
    assert result['expectation_surprise'] is None


def test_explicit_current_half_year_is_not_confused_with_a_full_year():
    result = extract_event_facts(earnings('2026年半年度净利润同比增长50%。',
        title='2026年半年度业绩预告', report_period='2026-06-30'), [])
    assert result['intensity'] == pytest.approx(.5)
    assert result['evidence_quote'] == '净利润同比增长50%'


@pytest.mark.parametrize('subject', ['扣非', '归母扣非', '扣除非经常性损益后的',
    '归属于上市公司股东的扣除非经常性损益的'])
def test_deducted_profit_is_a_separate_comparable_metric(subject):
    result=extract_event_facts(earnings(subject+'净利润同比增长50%。'),[])
    assert result['intensity']==.5
    assert result['intensity_unit']=='deducted_profit_yoy_ratio'


@pytest.mark.parametrize('subject', ['归母与扣非', '扣非和归母', '归母、扣非'])
def test_joint_ambiguous_profit_subject_cannot_be_assigned_one_metric(subject):
    assert extract_event_facts(earnings(subject+'净利润同比增长50%。'),[])['intensity'] is None


def test_deducted_background_does_not_change_a_later_parent_profit_subject():
    result=extract_event_facts(earnings('扣非指标另行披露，归母净利润同比增长50%。'),[])
    assert result['intensity_unit']=='profit_yoy_ratio'


@pytest.mark.parametrize('target_subject,case_subject,eligible',[
    ('归母','扣非',False),('扣非','归母',False),('扣非','扣非',True),('归母','归母',True)])
def test_historical_profit_comparisons_cannot_cross_metric_units(target_subject,case_subject,eligible):
    from tests.test_a_share_event_cases import target,cases
    from src.services.a_share_event_cases import match_event_cases
    current=extract_event_facts(earnings(target_subject+'净利润同比增长50%。')|target(),[])
    past=[extract_event_facts(e|dict(title='2024年第三季度业绩预告',report_period='2024-09-30',
        text_status='ready',text=case_subject+'净利润同比增长50%。'),[]) for e in cases()]
    result=match_event_cases(current,past,'2026-10-24')
    assert result['horizons']['20']['numerical_eligible'] is eligible
    assert result['horizons']['20']['sample_size']==(10 if eligible else 0)
    if not eligible:
        assert result['excluded']['intensity_unit']==10


def test_research_evidence_retains_the_profit_metric_and_its_supporting_subject():
    from src.services.a_share_integrated_research import _evidence
    document=earnings('扣非净利润同比增长50%。')
    event=extract_event_facts(document,[])
    bundle=dict(code='600000',anchor_date='2026-10-16',reference_price=10.,source='fixture',events=[event])
    evidence=next(e for e in _evidence(bundle) if e['category']=='event')
    assert evidence['intensity_unit']=='deducted_profit_yoy_ratio'
    assert '扣非' in evidence['evidence_quote']
    assert evidence['evidence_quote'] in document['text']
