from copy import deepcopy
from datetime import timedelta, datetime, timezone
import pytest

from tests.test_a_share_outlook_api import long_market
from src.services.a_share_integrated_service import IntegratedResearchService
from data_provider.a_share_fundamentals import normalize_financials


def facts(code='600000', profit=123.):
    return normalize_financials(code, [dict(SECUCODE=code+'.SH', REPORT_DATE='20230630',
        NOTICE_DATE='20230820', PARENTNETPROFIT=profit)], 'eastmoney/main', '2024-01-01T10:00:00+08:00')


def test_get_is_read_only_and_does_not_queue_data_or_model(tmp_path):
    svc, _ = long_market(tmp_path)
    service = svc.integrated
    before = len(svc.market.repo.tasks('free'))
    result = service.get('600000')
    assert result['status'] == 'missing' and result['code'] == '600000'
    assert len(svc.market.repo.tasks('free')) == before
    assert svc.repo.manual_usage('free', '2026-10-16') == 0


def test_restatement_changes_immutable_bundle_but_refetch_does_not(tmp_path):
    svc, _ = long_market(tmp_path)
    first = svc.integrated.freeze('600000', facts())
    repeated = svc.integrated.freeze('600000', facts())
    assert first['data_hash'] == repeated['data_hash']
    second = svc.integrated.freeze('600000', facts(profit=456.))
    assert second['data_hash'] != first['data_hash']
    assert svc.integrated.bundle(first['data_hash'])['facts'][0]['values']['net_profit'] == 123.
    assert svc.integrated.get('600000')['bundle']['data_hash'] == second['data_hash']


def test_prepare_deduplicates_durable_data_task_and_never_charges(tmp_path):
    svc, _ = long_market(tmp_path)
    first = svc.integrated.prepare('600000')
    second = svc.integrated.prepare('600000')
    assert first['task_id'] == second['task_id']
    assert first['status'] == 'preparing'
    assert svc.repo.manual_usage('free', '2026-10-16') == 0
    assert svc.market_jobs.run_one() is False
    assert svc.integrated.jobs.repo.claim('free', datetime.now(timezone.utc), kinds=['research_data'])['kind'] == 'research_data'


def test_future_financial_facts_are_not_sent_to_bundle(tmp_path):
    svc, _ = long_market(tmp_path)
    future = facts()
    future[0]['available_at'] = '2030-01-01T10:00:00+08:00'
    bundle = svc.integrated.freeze('600000', future)
    assert not bundle['facts']
    assert any('未来' in reason for reason in bundle['missing'])


def test_new_history_generation_invalidates_old_bundle_without_calling_model(tmp_path):
    svc, end = long_market(tmp_path)
    svc.integrated.freeze('600000', facts())
    cache = svc.market.repo.get_history('free', 'stock:600000', 'qfq', '1900-01-01', end)
    svc.market.repo.replace_history('free','stock:600000','qfq','fixture','new-basis',cache['items'],end)
    result = svc.integrated.get('600000')
    assert result['status'] == 'stale'
    assert result['bundle']
    assert svc.repo.records('free', 'integrated_report') == []


def test_unknown_stock_or_invalid_peer_offset_cannot_start_jobs(tmp_path):
    svc, _ = long_market(tmp_path)
    with pytest.raises(ValueError): svc.integrated.prepare('123456')
    with pytest.raises(ValueError): svc.integrated.prepare('600000', -1)
    with pytest.raises(ValueError): svc.integrated.prepare('600000', 501)


def test_demo_preparation_does_not_query_real_sources(tmp_path):
    from sqlalchemy import create_engine
    from src.repositories.a_share_repository import AssistantRepository
    from src.services.a_share_service import AssistantService
    svc = AssistantService(AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'demo.db'))))
    svc.sync('daily')
    result = svc.integrated.prepare('DEMO001')
    assert result['demo'] is True
    assert svc.market.repo.tasks('demo') == []


def test_data_task_cannot_publish_after_permissions_change(tmp_path):
    svc, _ = long_market(tmp_path)
    result = svc.integrated.prepare('600000')
    task = svc.integrated.jobs.repo.claim('free', datetime.now(timezone.utc), kinds=['research_data'])
    svc.settings = svc.settings.model_copy(update={'free_fallback':False})
    svc.integrated.handle_task(task)
    assert svc.integrated.get('600000')['bundle'] is None


def test_completed_preparation_can_be_manually_refreshed_same_day(tmp_path):
    svc, _ = long_market(tmp_path)
    first = svc.integrated.prepare('600000')
    task = svc.market.repo.claim('free', datetime.now(timezone.utc), kinds=['research_data'])
    svc.market.repo.finish(task['id'], task['claim_version'], 'complete')
    second = svc.integrated.prepare('600000')
    assert second['task_id'] != first['task_id']


def test_data_worker_recovery_cannot_reset_running_quote_job(tmp_path):
    svc, _ = long_market(tmp_path)
    svc.market_jobs.submit('free','quote-test','snapshot',{},0)
    quote = svc.market.repo.claim('free', datetime.now(timezone.utc), exclude_kinds=['research_data'])
    svc.market.repo.recover_running('free', kinds=['research_data'])
    assert svc.market.repo.task(quote['id'])['state'] == 'running'
    assert svc.market.repo.task(quote['id'])['claim_version'] == quote['claim_version']


def industry_groups(svc, memberships):
    groups = [dict(sector_id=k, name=k, kind='industry', classification='eastmoney-industry') for k in memberships]
    svc.market.repo.put_sectors('free', groups)
    for key, codes in memberships.items():
        svc.market.repo.replace_members('free', key, 'current', codes)


def test_nested_industries_choose_verified_narrowest_membership(tmp_path):
    svc, _ = long_market(tmp_path)
    industry_groups(svc, {'parent':['600000','600001','600002'], 'child':['600000','600001']})
    result = svc.integrated.freeze('600000', facts())
    assert result['context']['industry']['sector_id'] == 'child'
    assert not any('行业资料未核实' in r for r in result['missing'])


def test_incomparable_industries_remain_ambiguous(tmp_path):
    svc, _ = long_market(tmp_path)
    industry_groups(svc, {'left':['600000','600001'], 'right':['600000','600002']})
    assert svc.integrated.freeze('600000', facts())['context']['industry'] is None


def test_event_input_is_extracted_but_old_catalyst_cannot_enable_strategy(tmp_path):
    svc, end = long_market(tmp_path)
    def event(day):
        return dict(id=day,code='600000',title='业绩预告',kind='earnings',published_at=day,
                    text='归属于上市公司股东的净利润同比增长50%至80%',text_status='ready')
    old = svc.integrated.freeze('600000', facts(), [event('2022-01-01')])
    assert old['events'][0]['intensity'] == .65
    assert old['events'][0]['active_catalyst'] is False
    assert old['cases']['target_event'] is None
    recent = svc.integrated.freeze('600000', facts(), [event(end)])
    assert recent['events'][0]['active_catalyst'] is True
    assert recent['cases']['target_event']['id'] == end


def test_waiting_history_is_visible_and_successful_freeze_clears_it(tmp_path):
    svc, _ = long_market(tmp_path)
    svc.market.repo.set_state('free','research_waiting:600000',dict(reason='等待完整同源历史'))
    assert svc.integrated.get('600000')['status'] == 'waiting_history'
    svc.integrated.freeze('600000',facts())
    assert svc.integrated.get('600000')['status'] == 'ready'


def test_expired_plan_and_changed_model_are_visible_history_without_ai_calls(tmp_path):
    svc, _ = long_market(tmp_path)
    bundle=svc.integrated.freeze('600000',facts())
    svc.repo.append('free','integrated_report','free:600000',dict(data_hash=bundle['data_hash'],model='previous',
        plans=[dict(valid_until='2020-01-01')],status='complete'))
    svc.settings=svc.settings.model_copy(update={'model':'new-model'})
    result=svc.integrated.get('600000')
    assert result['report']['stale'] is True
    assert svc.repo.manual_usage('free','2026-10-16')==0


def test_root_reads_peer_progress_separately_without_model_calls(tmp_path):
    svc,_=long_market(tmp_path)
    task=svc.integrated.jobs.submit('free','peer-progress','research_data',dict(code='600001',root_code='600000'),95)
    svc.market.repo.set_state('free','research_peers:600000',dict(task_ids=[task],next_offset=20))
    result=svc.integrated.get('600000')
    assert result['peer_progress']==dict(total=1,complete=0,pending=1,running=0,failed=0,next_offset=20)


def test_long_lived_earnings_reach_separate_same_age_cohorts_even_with_newer_title_only_news(tmp_path):
    svc, end = long_market(tmp_path)
    days = [d for d in svc.market.calendar() if d <= end]
    def event(identity, day, kind='earnings', text=True):
        return dict(id=identity, code='600000', family_id=identity, kind=kind, title='业绩预告',
                    published_at=day, text_status='ready' if text else 'missing',
                    text='净利润同比增长50%' if text else '')
    bundle = svc.integrated.freeze('600000', facts(), [event('a', days[-61]), event('b', days[-31]), event('recent', end, text=False)])
    assert {c['target_event']['id'] for c in bundle['cases']['cohorts']} == {'a','b'}
    assert {c['elapsed_sessions'] for c in bundle['cases']['cohorts']} == {60,30}
    assert bundle['cases']['target_event']['id'] == 'b'
    assert bundle['cases']['diagnostics']['tracking_events'] == 3
    assert bundle['cases']['diagnostics']['quantified_targets'] == 2
    assert next(e for e in bundle['events'] if e['id'] == 'a')['tracking_active']


def test_later_actual_report_supersedes_same_period_guidance_even_before_text_is_fetched(tmp_path):
    svc,end=long_market(tmp_path)
    days=[d for d in svc.market.calendar() if d<=end]
    guidance=dict(id='guidance',code='600000',kind='earnings',family_id='guidance',report_period='2023-06-30',
        title='2023年半年度业绩预告',published_at=days[-61],text_status='ready',text='净利润同比增长50%')
    actual=dict(guidance,id='actual',family_id='actual',title='2023年半年度报告',published_at=days[-10],text_status='missing',text='')
    bundle=svc.integrated.freeze('600000',facts(),[guidance,actual])
    assert bundle['cases']['target_event'] is None
    old=next(e for e in bundle['events'] if e['id']=='guidance')
    assert old['lifecycle_state']=='superseded' and not old['active_catalyst']


def test_coverage_counts_raw_announcements_while_tracking_counts_effective_families(tmp_path):
    svc,end=long_market(tmp_path)
    first=dict(id='first',code='600000',family_id='same',kind='earnings',title='业绩预告',published_at=end,
        text_status='ready',text='净利润同比增长50%')
    second=dict(first,id='second')
    bundle=svc.integrated.freeze('600000',facts(),[first,second])
    assert bundle['cases']['diagnostics']['announcements']==2
    assert bundle['cases']['diagnostics']['verified_texts']==2
    assert bundle['cases']['diagnostics']['tracking_events']==1
