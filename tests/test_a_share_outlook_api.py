from datetime import date, datetime, timedelta, timezone
from math import sin

import pytest

from tests.test_a_share_market_api import client_for
from tests.test_a_share_market_integration import setup_market


def long_market(tmp_path):
    svc, _ = setup_market(tmp_path, count=1)
    days, day = [], date(2021, 1, 4)
    while len(days) < 1000:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    rows = []
    for i, day_text in enumerate(days[:800]):
        close = 10 * (1.0006 ** i) * (1 + .025 * sin(i / 17))
        rows.append(dict(date=day_text, open=close, close=close, high=close * 1.012,
                         low=close * .988, volume=1000000, amount=100000000))
    end = rows[-1]['date']
    svc.market.clock = lambda: datetime.fromisoformat(days[800]).replace(hour=2, tzinfo=timezone.utc)
    svc.market.repo.set_state('free', 'calendar', {'dates': days})
    for adjust in ('raw', 'qfq'):
        svc.market.repo.replace_history('free', 'stock:600000', adjust, 'fixture', 'b1', rows, end,
                                       requested_start='2017-01-01', requested_end=end)
    svc.market.repo.replace_history('free', 'benchmark:000300', 'raw', 'fixture', 'index', rows, end,
                                   requested_start='2017-01-01', requested_end=end)
    return svc, end


def test_outlook_is_available_without_llm_or_candidate_and_keeps_old_scenarios(tmp_path, monkeypatch):
    svc, end = long_market(tmp_path)
    c = client_for(svc, monkeypatch)
    response = c.get('/assistant/market/stocks/600000/outlook')
    assert response.status_code == 200
    value = response.json()
    assert value['code'] == '600000' and value['as_of'] == end
    assert value['price_basis'] == 'raw' and value['history_sessions'] == 800
    assert {t['period'] for t in value['trends']} == {20, 60, 120, 250}
    assert value['generated_at'] and value['archive']['snapshots'] >= 1
    assert svc.repo.latest('free', 'report') is None
    assert svc.repo.usage('free', end) == 0
    assert c.get('/assistant/market/stocks/600000/scenarios').status_code == 200


def test_repeat_reads_reuse_snapshot_but_changed_price_creates_new_identity(tmp_path):
    svc, end = long_market(tmp_path)
    first = svc.quant_outlook('600000')
    second = svc.quant_outlook('600000')
    assert second['generated_at'] == first['generated_at']
    assert len(svc.repo.records('free', 'outlook')) == 1
    cached = svc.market.repo.get_history('free', 'stock:600000', 'raw', '1900-01-01', end)
    changed = [dict(r) for r in cached['items']]
    changed[-1]['close'] *= 1.002
    svc.market.repo.replace_history('free', 'stock:600000', 'raw', 'fixture', 'b1', changed, end,
                                   requested_start='2017-01-01', requested_end=end)
    result = svc.quant_outlook('600000')
    assert result['data_hash'] != first['data_hash']
    assert len(svc.repo.records('free', 'outlook')) == 2


@pytest.mark.parametrize('ratio', ['nan', 'inf', '.5', '6'])
def test_api_rejects_invalid_risk_ratios(tmp_path, monkeypatch, ratio):
    svc, _ = long_market(tmp_path)
    assert client_for(svc, monkeypatch).get('/assistant/market/stocks/600000/outlook',
                                          params={'min_reward_risk': ratio}).status_code == 422


def test_demo_never_queues_real_long_history_sources(tmp_path):
    from sqlalchemy import create_engine
    from src.repositories.a_share_repository import AssistantRepository
    from src.services.a_share_service import AssistantService
    svc = AssistantService(AssistantRepository(create_engine('sqlite:///' + str(tmp_path / 'demo.db'))))
    svc.sync('daily')
    result = svc.quant_outlook('DEMO001')
    assert result['demo'] is True
    assert not svc.market.repo.tasks('demo')


def test_source_mismatch_queues_pair_repair_and_does_not_train_mixed_sources(tmp_path):
    svc, end = long_market(tmp_path)
    cache = svc.market.repo.get_history('free', 'stock:600000', 'raw', '1900-01-01', end)
    svc.market.repo.replace_history('free', 'stock:600000', 'raw', 'akshare/tencent', 'b1', cache['items'], end)
    svc.market.repo.replace_history('free', 'stock:600000', 'qfq', 'akshare/eastmoney', 'b1', cache['items'], end)
    result = svc.quant_outlook('600000')
    assert result['status'] == 'pending' and not result['forecasts']
    assert any(t['payload'].get('forced_source') == 'akshare/tencent' for t in svc.market.repo.tasks('free'))


def test_verified_material_risk_blocks_outlook_without_duplicating_numerical_snapshot(tmp_path):
    svc, _ = long_market(tmp_path)
    original = svc.quant_outlook('600000')
    available = svc.market.clock().isoformat()
    svc.repo.append('free', 'event', 'risk', dict(code='600000', source='fixture', title='监管处罚',
                    url='https://example.org/event', first_seen=available, revised_at=available, revision=1))
    event = svc.repo.records('free', 'event')[0]
    svc.repo.append('free', 'verification', str(event['id']), dict(code='600000', major_risk=True,
                    note='已核实重大风险', event_id=event['id'], verified_at=available))
    result = svc.quant_outlook('600000')
    assert result['plan']['status'] == 'observe'
    assert any('重大风险' in reason for reason in result['plan']['reasons'])
    assert result['generated_at'] == original['generated_at']
    assert len(svc.repo.records('free', 'outlook')) == 1


def test_archive_does_not_claim_old_reconstructed_forecasts_as_issued_predictions(tmp_path):
    svc, end = long_market(tmp_path)
    result = svc.quant_outlook('600000')
    assert result['archive']['matured'] == 0 and result['archive']['coverage'] is None
    assert result['forecasts']
    assert all(f['target_date'] is None or f['target_date'] > end for f in result['forecasts'])


def test_source_published_index_closes_are_a_known_market_return_baseline(tmp_path):
    svc, _ = long_market(tmp_path)
    result = svc.quant_outlook('600000')
    assert result['environment']['market_state'] != 'unknown'
    assert result['environment']['relative20'] == pytest.approx(0)
    assert result['environment']['relative60'] == pytest.approx(0)


def test_future_event_and_confirmation_do_not_enter_current_risk_evidence(tmp_path):
    svc, _ = long_market(tmp_path)
    future = (svc.market.clock() + timedelta(days=1)).isoformat()
    identity = svc.repo.append('free', 'event', 'later', dict(code='600000', title='未来风险',
        first_seen=future, revised_at=future, revision=1, source='fixture'))
    svc.repo.append('free', 'verification', str(identity), dict(code='600000', event_id=identity,
        major_risk=True, verified_at=future, note='未来确认'))
    result = svc.quant_outlook('600000')
    assert not any('重大风险' in reason for reason in result['plan']['reasons'])
    assert not result['events']


def test_existing_ai_price_evidence_receives_long_cycle_facts_without_extra_calls(tmp_path):
    svc, end = long_market(tmp_path)
    context = svc.price_context('600000')
    assert context['features']['sma250'] > 0
    assert context['features']['sma120'] > 0
    assert context['features']['weekly_state'] in ('up', 'down', 'range')
    assert context['features']['long_cycle_status'] == 'available'
    assert svc.repo.usage('free', end) == 0


def test_old_invalid_long_history_does_not_remove_valid_recent_ai_evidence(tmp_path):
    svc, end = long_market(tmp_path)
    q = svc.market.repo.get_history('free', 'stock:600000', 'qfq', '1900-01-01', end)
    rows = [dict(r) for r in q['items']]
    rows[0].update(open=-1, close=-1, high=-.8, low=-1.2)
    svc.market.repo.replace_history('free', 'stock:600000', 'qfq', 'fixture', 'b1', rows, end,
                                   requested_start='2017-01-01', requested_end=end)
    context = svc.price_context('600000')
    assert context['reference_price'] > 0
    assert context['features']['long_cycle_status'] == 'invalid_history'


def test_archive_counts_first_eligible_twenty_day_forecast_after_same_day_warmup(tmp_path):
    from src.services.a_share_outlook_service import archive_metrics
    svc, end = long_market(tmp_path)
    bars = svc.market.repo.get_history('free', 'stock:600000', 'raw', '1900-01-01', end)['items']
    calendar = svc.market.calendar()
    anchor, target = bars[300]['date'], bars[320]['date']
    issued = bars[301]['date'] + 'T09:00:00+08:00'
    actual = bars[320]['close']
    base = dict(as_of=anchor, generated_at=issued, source='fixture')
    records = [dict(id=2, payload=base | {'forecasts': [dict(horizon_sessions=20, target_date=target,
                low=actual - 2, median=actual + 1, high=actual + 2)]}),
               dict(id=1, payload=base | {'forecasts': [dict(horizon_sessions=5, low=1, median=2, high=3)]})]
    result = archive_metrics(records, bars, calendar, svc.market.clock(), 'fixture')
    assert result['snapshots'] == 1 and result['matured'] == 1
    assert result['coverage'] == 1 and result['mean_absolute_error'] == pytest.approx(1)


def test_archive_never_scores_a_future_endpoint_even_if_future_bars_are_supplied(tmp_path):
    from src.services.a_share_outlook_service import archive_metrics
    svc, end = long_market(tmp_path)
    bars = svc.market.repo.get_history('free', 'stock:600000', 'raw', '1900-01-01', end)['items']
    anchor = bars[700]['date']
    records = [dict(id=1, payload=dict(as_of=anchor, generated_at=bars[701]['date'] + 'T09:00:00+08:00',
               source='fixture', forecasts=[dict(horizon_sessions=20, low=1, median=10, high=100)]))]
    before_maturity = datetime.fromisoformat(bars[710]['date']).replace(hour=2, tzinfo=timezone.utc)
    result = archive_metrics(records, bars, svc.market.calendar(), before_maturity, 'fixture')
    assert result['matured'] == 0


def test_invalid_long_history_returns_failed_diagnostics_instead_of_throwing_again(tmp_path, monkeypatch):
    svc, end = long_market(tmp_path)
    q = svc.market.repo.get_history('free', 'stock:600000', 'qfq', '1900-01-01', end)
    rows = [dict(r) for r in q['items']]
    rows[0].update(open=-1, close=-1, high=-.8, low=-1.2)
    svc.market.repo.replace_history('free', 'stock:600000', 'qfq', 'fixture', 'b1', rows, end,
                                   requested_start='2017-01-01', requested_end=end)
    response = client_for(svc, monkeypatch).get('/assistant/market/stocks/600000/outlook')
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'failed' and not result['forecasts']
    assert any('完整性校验' in item for item in result['limitations'])
    assert svc.price_context('600000')['features']['long_cycle_status'] == 'invalid_history'
