"""Chronology, price-basis and honest-evidence tests for the pure outlook engine."""
import copy
import importlib
import math
from datetime import date, timedelta

import numpy as np
import pytest


def engine():
    return importlib.import_module('src.services.a_share_outlook')


def sessions(count=1400, start=date(2018, 1, 1)):
    days = []
    while len(days) < count:
        if start.weekday() < 5:
            days.append(start.isoformat())
        start += timedelta(days=1)
    return days


def history(count=1250, *, calendar=None, drift=.0007):
    calendar = calendar or sessions(count + 100)
    rows = []
    for i, day in enumerate(calendar[:count]):
        close = 12 * math.exp(drift * i + .018 * math.sin(i / 12) + .007 * math.sin(i / 3))
        rows.append(dict(date=day, open=close * .998, high=close * 1.008, low=close * .99,
                         close=close, adjusted_close=close * .8,
                         volume=1_000_000 + 30_000 * math.sin(i / 7), amount=close * 1_000_000))
    return rows


def test_future_bars_never_change_cutoff_features_fits_or_labels():
    calendar = sessions(950)
    rows = history(900, calendar=calendar)
    cutoff = rows[799]['date']
    before = engine().build_outlook(rows[:800], calendar, cutoff)
    poisoned = copy.deepcopy(rows[800:])
    for row in poisoned:
        row.update(close=float('nan'), adjusted_close=1e9)
    assert engine().build_outlook(rows[:800] + poisoned, calendar, cutoff) == before


def test_ma250_requires_250_observed_sessions_and_rebases_adjusted_prices():
    calendar = sessions(300)
    rows = history(249, calendar=calendar)
    out = engine().build_outlook(rows, calendar, rows[-1]['date'])
    ma = next(t for t in out['trends'] if t['period'] == 250)
    assert ma['ma'] is None and ma['state'] == 'insufficient'
    rows = [dict(r, close=20, adjusted_close=10, open=20, high=21, low=19) for r in history(250, calendar=calendar)]
    out = engine().build_outlook(rows, calendar, rows[-1]['date'])
    ma = next(t for t in out['trends'] if t['period'] == 250)
    assert ma['ma'] == pytest.approx(20)
    assert out['reference_price'] == out['raw_anchor'] == 20
    assert out['qfq_anchor'] == 10 and out['price_basis'] == 'raw'


def test_incomplete_week_cannot_move_completed_week_summary():
    calendar = sessions(330)
    rows = history(325, calendar=calendar)
    friday = next(i for i in range(310, 320) if date.fromisoformat(rows[i]['date']).weekday() == 4)
    wed = friday + 3
    out = engine().build_outlook(rows[:wed + 1], calendar, rows[wed]['date'])
    changed = copy.deepcopy(rows[:wed + 1])
    for r in changed[friday + 1:]:
        r.update(open=r['open'] * 4, high=r['high'] * 4, low=r['low'] * 4,
                 close=r['close'] * 4, adjusted_close=r['adjusted_close'] * 4)
    other = engine().build_outlook(changed, calendar, rows[wed]['date'])
    assert out['weekly']['as_of'] == rows[friday]['date']
    assert other['weekly']['ma10'] == pytest.approx(out['weekly']['ma10'])
    assert other['weekly']['state'] == out['weekly']['state']


def test_calendar_proves_a_holiday_shortened_week_is_finished():
    calendar = sessions(400)
    rows = history(360, calendar=calendar)
    wed = next(i for i in range(330, 340) if date.fromisoformat(rows[i]['date']).weekday() == 2)
    closed_calendar = [d for d in calendar if d not in (calendar[wed + 1], calendar[wed + 2])]
    out = engine().build_outlook(rows[:wed + 1], closed_calendar, rows[wed]['date'])
    assert out['weekly']['as_of'] == rows[wed]['date']


@pytest.mark.parametrize('field,value', [('close', float('nan')), ('adjusted_close', float('inf')),
                                        ('high', -1), ('volume', float('inf')), ('close', True)])
def test_nonfinite_or_invalid_completed_prices_are_rejected(field, value):
    calendar = sessions(300)
    rows = history(260, calendar=calendar)
    rows[-1][field] = value
    with pytest.raises(ValueError):
        engine().build_outlook(rows, calendar, rows[-1]['date'])


def test_duplicate_completed_dates_are_rejected():
    rows = history(260)
    with pytest.raises(ValueError, match='重复|duplicate'):
        engine().build_outlook(rows + [rows[-1]], sessions(400), rows[-1]['date'])


def test_calendar_gap_cannot_be_silently_compressed_into_trading_horizons():
    calendar = sessions(1000)
    rows = history(900, calendar=calendar)
    del rows[700]
    out = engine().build_outlook(rows, calendar, rows[-1]['date'])
    assert out['status'] != 'ready' and out['forecasts'] == []
    assert out['plan']['status'] == 'observe'
    assert any('日历' in x or '空缺' in x for x in out['limitations'])


def test_missing_adjusted_history_is_explicit_and_never_used_as_raw_training_labels():
    rows = history(800)
    for row in rows:
        del row['adjusted_close']
    out = engine().build_outlook(rows, sessions(1000), rows[-1]['date'])
    assert out['forecasts'] == [] and out['qfq_anchor'] is None
    assert out['plan']['status'] == 'observe'
    assert any('复权' in x for x in out['limitations'])


def test_missing_future_calendar_never_invents_target_dates():
    rows = history()
    out = engine().build_outlook(rows, [r['date'] for r in rows], rows[-1]['date'])
    assert {f['horizon_sessions'] for f in out['forecasts']} == {5, 20, 60}
    assert all(f['target_date'] is None for f in out['forecasts'])
    assert all(p['date'] is None for f in out['forecasts'] for p in f['points'])


def test_every_forecast_is_positive_ordered_and_each_point_has_its_own_horizon():
    rows = history()
    calendar = sessions(1400)
    out = engine().build_outlook(rows, calendar, rows[-1]['date'])
    assert {f['horizon_sessions'] for f in out['forecasts']} == {5, 20, 60}
    for f in out['forecasts']:
        assert 0 < f['low'] <= f['median'] <= f['high'] < math.inf
        assert f['target_date'] == calendar[len(rows) - 1 + f['horizon_sessions']]
        assert f['calibration_state'] == 'historical' and f['sample_size'] > 0
        assert f['points'][-1]['median'] == f['median']
        assert len({p['sessions'] for p in f['points']}) == len(f['points'])
        assert all(0 < p['low'] <= p['median'] <= p['high'] < math.inf for p in f['points'])


def test_validation_reports_only_purged_chronological_nonoverlapping_origins():
    rows = history()
    out = engine().build_outlook(rows, sessions(1400), rows[-1]['date'])
    for f in out['forecasts']:
        v = f['validation']
        assert v['state'] == 'measured' and v['samples'] >= 8
        assert v['mean_absolute_error'] >= 0 and v['baseline_mean_absolute_error'] >= 0
        assert 'rolling' in v['method'] and 'purged' in v['method']
        assert len(v['origins']) == v['samples']
        for i, item in enumerate(v['origins']):
            assert item['last_training_label_date'] <= item['origin_date'] < item['target_date'] <= rows[-1]['date']
            if i:
                assert v['origins'][i - 1]['target_date'] <= item['origin_date']
            assert item['calibration_last_target_date'] is None or item['calibration_last_target_date'] <= item['origin_date']
        assert v['coverage'] is None or 0 <= v['coverage'] <= 1


def test_forward_labels_and_preprocessing_use_only_data_available_at_each_origin():
    calendar = sessions(1400)
    rows = history()
    initial = engine().build_outlook(rows, calendar, rows[-1]['date'])
    sample = next(f for f in initial['forecasts'] if f['horizon_sessions'] == 20)['validation']['origins'][5]
    index = calendar.index(sample['origin_date'])
    changed = copy.deepcopy(rows)
    for row in changed[index + 1:]:
        for key in ('close', 'open', 'high', 'low', 'adjusted_close'):
            row[key] *= 100
    result = engine().build_outlook(changed, calendar, rows[-1]['date'])
    audit = next(f for f in result['forecasts'] if f['horizon_sessions'] == 20)['validation']['origins']
    same = next(o for o in audit if o['origin_date'] == sample['origin_date'])
    assert same['predicted_log_return'] == pytest.approx(sample['predicted_log_return'], abs=1e-12)


def test_training_fit_is_not_presented_as_validation_on_short_history():
    rows = history(370)
    out = engine().build_outlook(rows, sessions(500), rows[-1]['date'])
    assert out['status'] in ('partial', 'insufficient') and not out['forecasts']
    assert out['plan']['status'] == 'observe'
    assert any('样本' in x for x in out['limitations'])


def test_unchanged_price_error_is_computed_from_actual_future_outcomes():
    rows = history()
    out = engine().build_outlook(rows, sessions(1400), rows[-1]['date'])
    f = next(f for f in out['forecasts'] if f['horizon_sessions'] == 20)
    by_date = {r['date']: r for r in rows}
    absolute = []
    for sample in f['validation']['origins']:
        a, b = by_date[sample['origin_date']], by_date[sample['target_date']]
        absolute.append(a['close'] * abs(b['adjusted_close'] / a['adjusted_close'] - 1))
    assert f['validation']['baseline_mean_absolute_error'] == pytest.approx(np.mean(absolute))


def test_minimum_reward_risk_filters_without_moving_independent_targets():
    rows = history()
    calendar = sessions(1400)
    benchmark = history(len(rows), calendar=calendar, drift=.0003)
    easy = engine().build_outlook(rows, calendar, rows[-1]['date'], benchmark=benchmark, min_reward_risk=1)
    strict = engine().build_outlook(rows, calendar, rows[-1]['date'], benchmark=benchmark, min_reward_risk=5)
    assert easy['forecasts'] == strict['forecasts']
    for field in ('entry_low', 'entry_high', 'stop', 'target_low', 'target_high', 'reward_risk'):
        assert easy['plan'][field] == strict['plan'][field]
    if strict['plan']['reward_risk'] is not None and strict['plan']['reward_risk'] < 5:
        assert strict['plan']['status'] == 'observe'
        assert any('盈亏比' in reason for reason in strict['plan']['reasons'])
    assert strict['plan']['target_low'] == next(f for f in strict['forecasts'] if f['horizon_sessions'] == 20)['median']


def test_missing_benchmark_blocks_conditional_plan():
    rows = history()
    out = engine().build_outlook(rows, sessions(1400), rows[-1]['date'])
    assert out['environment']['market_state'] == 'unknown' and out['environment']['relative20'] is None
    assert out['plan']['status'] == 'observe'


@pytest.mark.parametrize('ratio', [float('nan'), float('inf'), 0, 6, True])
def test_invalid_reward_risk_is_rejected(ratio):
    with pytest.raises(ValueError):
        engine().build_outlook([], [], '2020-01-01', min_reward_risk=ratio)


def event_fixture(rows, indices):
    return [dict(id=str(i), event_key=f'e-{i}', title='业绩预告', kind='earnings',
                 published_at=rows[i]['date'] + 'T09:00:00+08:00', first_seen=rows[i]['date'] + 'T09:10:00+08:00',
                 source='exchange', url=f'https://example.test/e/{i}', verified=True) for i in indices]


def test_event_revisions_keep_first_seen_source_and_do_not_inflate_samples():
    calendar = sessions(1400)
    rows = history()
    benchmark = history(len(rows), calendar=calendar, drift=.0001)
    events = event_fixture(rows, [800, 820, 840, 860, 880, 900])
    revision = dict(events[0], id='revision', first_seen=rows[950]['date'] + 'T18:00:00+08:00',
                    revised_at=rows[950]['date'] + 'T18:00:00+08:00', title='业绩预告修订')
    out = engine().event_observations(events + [revision], rows, calendar, rows[-1]['date'], benchmark=benchmark)
    assert len(out) == 6
    revised = next(e for e in out if e['event_key'] == 'e-800')
    assert revised['first_seen'] == events[0]['first_seen'] and revised['source'] == 'exchange'
    assert revised['title'] == '业绩预告修订'
    assert all(e['impact']['samples'] == 6 and e['impact']['state'] == 'observed' for e in out)


def test_event_observations_require_maturity_and_aligned_benchmark_endpoints():
    calendar = sessions(1400)
    rows = history()
    events = event_fixture(rows, [800, 820, 840, 860, 880, 1249])
    benchmark = history(len(rows), calendar=calendar, drift=.0001)
    observed = engine().event_observations(events, rows, calendar, rows[-1]['date'], benchmark=benchmark)
    newest = next(e for e in observed if e['event_key'] == 'e-1249')
    assert newest['impact']['state'] == 'insufficient' and newest['impact']['median_excess'] is None
    missing = [r for r in benchmark if r['date'] != rows[844]['date']]
    out = engine().event_observations(events[:5], rows, calendar, rows[-1]['date'], benchmark=missing)
    assert all(e['impact']['state'] == 'insufficient' for e in out)
    assert max(e['impact']['samples'] for e in out) == 4


def test_backdated_news_uses_first_seen_instead_of_publication_for_maturity():
    calendar = sessions(1400)
    rows = history()
    events = event_fixture(rows, [800, 820, 840, 860, 880, 900])
    events[-1]['first_seen'] = rows[-1]['date'] + 'T18:00:00+08:00'
    benchmark = history(len(rows), calendar=calendar)
    out = engine().event_observations(events, rows, calendar, rows[-1]['date'], benchmark=benchmark)
    late = next(e for e in out if e['event_key'] == 'e-900')
    assert late['date'] is None or late['date'] > rows[-1]['date']
    assert late['impact']['state'] == 'insufficient'


def test_event_excess_returns_use_actual_date_aligned_adjusted_returns():
    calendar = sessions(1400)
    rows = history()
    benchmark = history(len(rows), calendar=calendar, drift=.0001)
    events = event_fixture(rows, [800, 820, 840, 860, 880])
    out = engine().event_observations(events, rows, calendar, rows[-1]['date'], benchmark=benchmark)
    returns = [(rows[i + 4]['adjusted_close'] / rows[i - 1]['adjusted_close'] - 1) -
               (benchmark[i + 4]['adjusted_close'] / benchmark[i - 1]['adjusted_close'] - 1)
               for i in (800, 820, 840, 860, 880)]
    assert out[0]['impact']['median_excess'] == pytest.approx(float(np.median(returns)))
    assert out[0]['impact']['samples'] == 5


def test_empty_history_is_insufficient_and_technical_summary_does_not_fit():
    out = engine().build_outlook([], [], '2020-01-01')
    assert out['status'] == 'insufficient' and out['reference_price'] is None
    assert out['forecasts'] == [] and out['plan']['entry_low'] is None
    rows = history(280)
    summary = engine().technical_summary(rows, sessions(500), rows[-1]['date'])
    assert set(summary) == {'trends', 'weekly'}
    assert summary['trends'] == engine().build_outlook(rows, sessions(500), rows[-1]['date'])['trends']


def test_date_only_first_seen_cannot_assume_before_close_availability():
    calendar = sessions(1400)
    rows = history()
    events = event_fixture(rows, [800, 820, 840, 860, 880])
    for event in events:
        event['first_seen'] = event['published_at'][:10]
    out = engine().event_observations(events, rows, calendar, rows[-1]['date'], benchmark=rows)
    event = next(e for e in out if e['event_key'] == 'e-800')
    assert event['date'] == calendar[801]


def test_revised_publication_date_never_restarts_original_event_response_window():
    calendar = sessions(1400)
    rows = history()
    events = event_fixture(rows, [800, 820, 840, 860, 880])
    events.append(dict(events[0], id='updated', first_seen=calendar[1000] + 'T09:00:00+08:00',
                       revised_at=calendar[1000] + 'T09:00:00+08:00',
                       published_at=calendar[1000] + 'T09:00:00+08:00', title='修订披露'))
    out = engine().event_observations(events, rows, calendar, rows[-1]['date'], benchmark=rows)
    event = next(e for e in out if e['event_key'] == 'e-800')
    assert event['date'] == calendar[800] and event['published_at'] == events[0]['published_at']
    assert event['title'] == '修订披露'


def test_unknown_taxonomy_does_not_pool_unrelated_news_as_an_impact_estimate():
    calendar = sessions(1400)
    rows = history()
    events = event_fixture(rows, [800, 820, 840, 860, 880])
    for event in events:
        event.update(kind='unknown', title='事实待核实')
    out = engine().event_observations(events, rows, calendar, rows[-1]['date'], benchmark=rows)
    assert all(e['kind'] == 'other' and e['impact']['state'] == 'insufficient' for e in out)
