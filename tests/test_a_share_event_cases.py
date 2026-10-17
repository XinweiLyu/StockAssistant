from copy import deepcopy
from datetime import date, timedelta
import pytest

from src.services.a_share_event_cases import match_event_cases, case_price_references, event_context, extract_event_facts


def target():
    return dict(id='target', code='000807', family_id='target', kind='earnings', direction='positive',
                intensity=.4, industry_id='eastmoney:aluminium', industry_quality='historical',
                market_state='up', pre20=.05, valuation_percentile=.4)


def cases():
    return [dict(target(), id=f'case{i}', family_id=f'family{i}', code=f'60000{i%5}',
        published_at=f'2024-{i+1:02d}-01T23:59:59+08:00', public_verified=True,
        outcomes={str(h):dict(end_date=(date(2024,i+1,2)+timedelta(days=h)).isoformat(), start_date=f'2024-{i+1:02d}-02',
            stock_return=.1, market_return=.02, industry_return=.04,
            market_excess=.08, industry_excess=.06, adverse=-.05, favorable=.2,
            execution_status='unverified') for h in (1,5,20,60)}) for i in range(10)]


def test_eligible_distribution_reports_separate_excesses_and_actual_sample_counts():
    result = match_event_cases(target(), cases(), '2026-10-16')
    h = result['horizons']['20']
    assert h['sample_size'] == 10 and h['companies'] == 5
    assert h['numerical_eligible'] is True
    assert h['median_return'] == .1 and h['median_market_excess'] == .08
    assert h['median_industry_excess'] == .06
    assert case_price_references(result, 20.)[0]['median'] == pytest.approx(22.)


@pytest.mark.parametrize('patch, reason', [
    ({'industry_quality':'current_membership_only'}, 'unverified_industry'),
    ({'kind':'order'}, 'event_kind'), ({'public_verified':False}, 'unverified_publication'),
    ({'published_at':'2026-10-17T10:00:00+08:00'}, 'future'),
    ({'industry_id':'shenwan:aluminium'}, 'industry'),
    ({'direction':'negative'}, 'direction'),
])
def test_bad_or_incomparable_cases_are_excluded(patch, reason):
    data = [dict(cases()[0], **patch)]
    result = match_event_cases(target(), data, '2026-10-16')
    assert result['horizons']['20']['sample_size'] == 0
    assert result['excluded'][reason] == 1


def test_future_or_unmatured_outcome_does_not_enter_any_past_statistic():
    data = cases()
    data[0]['outcomes']['20']['end_date'] = '2026-11-01'
    result = match_event_cases(target(), data, '2026-10-16')
    assert result['horizons']['20']['sample_size'] == 9
    assert result['horizons']['5']['sample_size'] == 10
    assert result['horizons']['20']['numerical_eligible'] is False


def test_duplicate_family_and_overlapping_same_stock_windows_do_not_inflate_n():
    data = cases()
    data.append(deepcopy(data[0]))
    data.append(dict(deepcopy(data[0]), id='other', family_id='other'))
    result = match_event_cases(target(), data, '2026-10-16')
    assert result['horizons']['20']['sample_size'] == 10
    assert result['excluded']['duplicate_family'] == 1


def test_different_market_or_runup_is_reference_not_strict_numeric_sample():
    data = cases()
    data[0]['market_state'] = 'down'
    data[1]['pre20'] = .8
    result = match_event_cases(target(), data, '2026-10-16')
    assert result['horizons']['20']['sample_size'] == 8
    assert result['horizons']['20']['numerical_eligible'] is False
    assert len(result['reference_cases']) == 2


def test_unknown_target_dimensions_do_not_match_as_zero():
    result = match_event_cases(dict(target(), pre20=None), cases(), '2026-10-16')
    assert not result['horizons']['20']['numerical_eligible']
    assert 'pre20' in result['missing_dimensions']


def test_revised_family_uses_latest_known_original_instead_of_superseded_gain():
    old=cases()[0]; revised=deepcopy(old)
    revised.update(id='corrected',published_at='2024-01-02T23:59:59+08:00')
    revised['outcomes']['20']['stock_return']=-.2
    result=match_event_cases(target(),[old,revised],'2026-10-16')
    assert result['horizons']['20']['median_return']==-.2


def test_elapsed_event_window_does_not_repeat_the_already_realized_response():
    calendar=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(100)]
    stock=[dict(date=d,open=10.+i,close=10.+i,adjusted_close=10.+i,high=11.+i,low=9.+i) for i,d in enumerate(calendar)]
    event=dict(published_at=calendar[20],code='000807')
    result=event_context(event,dict(stock=stock),calendar,calendar[-1],elapsed_sessions=10)
    assert result['outcomes']['5']['stock_return']==pytest.approx(45/40-1)
    assert result['outcomes']['5']['anchor_date']==calendar[30]
    assert result['event_pre20']==pytest.approx(30/10-1)


def test_withdrawn_announcement_does_not_retain_positive_strength():
    event=dict(title='撤销业绩预告',text_status='ready',text='此前净利润同比增长50%，现撤销该预告。')
    result=extract_event_facts(event,[])
    assert result['intensity'] is None and result['direction']=='unknown'


def test_numeric_earnings_extraction_requires_actual_text_and_exact_quotes():
    event = dict(id='a', code='000807', kind='earnings', title='业绩预增', text='')
    assert extract_event_facts(event, [])['intensity'] is None
    text = '预计归属于上市公司股东的净利润同比增长30%至50%。'
    result = extract_event_facts(dict(event, text=text), [])
    assert result['direction'] == 'positive'
    assert result['intensity'] == pytest.approx(.4)
    assert result['evidence_quote'] in text
    assert result['expectation_surprise'] is None
    assert extract_event_facts(dict(event, text='订单金额10亿元，营收规模未给出'), [])['intensity'] is None


def test_fabricated_model_quote_cannot_be_verified():
    event = dict(id='e', kind='order', title='合同', text='公司签订合同。')
    result = extract_event_facts(event, [], completion=lambda *_: {'intensity':.8,'evidence_quote':'营收占比80%'})
    assert result['intensity'] is None


def test_context_uses_completed_aligned_calendar_and_pre_event_returns():
    calendar = [(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(100)]
    rows = [dict(date=d, open=10.+i, high=11.+i, low=9.+i, close=10.+i, adjusted_close=10.+i) for i,d in enumerate(calendar)]
    event = dict(target(), published_at=calendar[30]+'T23:59:59+08:00', public_verified=True)
    context = event_context(event, {'stock':rows,'benchmark':rows,'industry':rows}, calendar, calendar[-1])
    assert context['pre20'] == pytest.approx(40/20-1)
    assert context['outcomes']['5']['stock_return'] == pytest.approx(45/40-1)
    assert context['outcomes']['5']['market_excess'] == 0
    assert context['outcomes']['5']['execution_status'] == 'unverified'
