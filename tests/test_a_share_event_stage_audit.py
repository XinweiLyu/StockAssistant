"""Historical earnings analogues must represent the target's known disclosure stage."""
from datetime import date, timedelta

import pytest

from src.services.a_share_event_cases import event_context, match_event_cases


def guidance():
    return dict(id='target', code='600000', family_id='target', kind='earnings',
        title='2026年半年度业绩预告', direction='positive', intensity=.5,
        intensity_unit='profit_yoy_ratio', industry_id='industry', market_state='range', pre20=.05)


def historical(**changes):
    return guidance() | dict(id='case', code='600001', family_id='case',
        published_at='2024-07-10', public_verified=True, industry_quality='archived',
        stage_state='tracking', outcomes={'20': dict(start_date='2024-08-01',
            end_date='2024-08-28', stock_return=.1)}) | changes


@pytest.mark.parametrize('title', ['2024年半年度业绩快报', '2024年半年度报告', '业绩说明会通知', ''])
def test_formal_results_or_unknown_stage_cannot_match_an_outstanding_guidance(title):
    result = match_event_cases(guidance(), [historical(title=title)], '2026-10-16', horizons=(20,))
    assert result['cases'] == []
    assert result['excluded'] == {'earnings_stage': 1}


def test_guidance_already_superseded_at_its_aligned_stage_is_not_a_strict_analogue():
    result = match_event_cases(guidance(), [historical(stage_state='superseded')],
                               '2026-10-16', horizons=(20,))
    assert result['cases'] == []
    assert result['excluded'] == {'superseded_at_stage': 1}
    assert result['horizons']['20']['sample_size'] == 0


def test_later_lifecycle_supersession_does_not_rewrite_an_earlier_stage():
    result = match_event_cases(guidance(), [historical(lifecycle_state='superseded', stage_state='tracking')],
                               '2026-10-16', horizons=(20,))
    assert [case['id'] for case in result['cases']] == ['case']
    assert result['horizons']['20']['sample_size'] == 1


def test_legacy_target_without_a_known_stage_keeps_compatible_matching():
    result = match_event_cases(guidance() | dict(title=''), [historical(title='2024年半年度报告')],
                               '2026-10-16', horizons=(20,))
    assert result['horizons']['20']['sample_size'] == 1


def test_aligned_stage_anchor_is_exposed_only_when_its_price_exists():
    calendar = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(60)]
    rows = [dict(date=day, open=10., high=10., low=10., close=10., adjusted_close=10.) for day in calendar]
    event = dict(published_at=calendar[20])
    result = event_context(event, dict(stock=rows), calendar, calendar[-1], elapsed_sessions=10)
    assert result['stage_anchor_date'] == calendar[30]
    missing = event_context(event, dict(stock=[r for r in rows if r['date'] != calendar[30]]),
                            calendar, calendar[-1], elapsed_sessions=10)
    assert missing.get('stage_anchor_date') is None
