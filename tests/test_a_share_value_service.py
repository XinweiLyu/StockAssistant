from datetime import datetime
import pytest
from tests.test_a_share_market_integration import setup_market
from data_provider.a_share_value_facts import normalize_value_statements
from src.schemas.a_share_value import SaveValueRequest, EvaluateValueRequest, SupplementValueRequest
from tests.test_a_share_value_valuation import operating_case


def value_service(tmp_path):
    svc, _ = setup_market(tmp_path)
    svc.market.clock = lambda: datetime.fromisoformat('2026-10-30T10:00:00+08:00')
    now = svc.value.now()
    facts = normalize_value_statements('600034', [dict(ts_code='600034.SH', report_type='1',
        end_date='20251231', ann_date='20260330', total_share=10, total_assets=200)], 'tushare/balancesheet', now)
    from src.services.a_share_market_service import source_signature
    svc.repo.append('free', 'research_data', 'free:600034', dict(value_facts=facts, facts=[], events=[],
        coverage=[], source_signature=list(source_signature(svc.settings)), fetched_at=now))
    return svc


def test_get_is_read_only_and_freeze_does_not_require_price_history(tmp_path):
    svc = value_service(tmp_path)
    svc._provider = lambda: (_ for _ in ()).throw(AssertionError('network on GET'))
    assert svc.value.get('600034')['status'] == 'missing'
    snapshot = svc.value.capture('600034')
    assert snapshot['financial_view']['latest']['shares']['value'] == 10
    assert svc.value.get('600034')['snapshot']['snapshot_id'] == snapshot['snapshot_id']
    assert svc.repo.manual_usage('free', '2026-10-30') == 0
    assert svc.value.get('600034')['strategy']['company_drivers']['state']=='insufficient'


def test_saved_model_missing_prefixes_show_as_classified_unverified_gaps_without_a_new_call(tmp_path):
    svc=value_service(tmp_path);svc.settings=svc.settings.model_copy(update={'model':'mock'});s=svc.value.capture('600034')
    svc.repo.append('free','value_review','free:600034',dict(code='600034',snapshot_id=s['snapshot_id'],model='mock',
        published_revision=0,status='partial',missing=['delivery: 未送达财报附注']))
    gaps=svc.value.get('600034')['strategy']['gaps']
    assert any(g['kind']=='delivery' and '未送达财报附注' in g['item'] for g in gaps)
    assert svc.repo.manual_usage('free','2026-10-30')==0


def test_inverse_cannot_bypass_the_effective_model_applicability(tmp_path,monkeypatch):
    svc=value_service(tmp_path);monkeypatch.setattr(svc.value,'_quote',lambda stock:dict(valid=True,price=10,trade_date='2026-10-30',basis='raw'))
    s=svc.value.capture('600034')
    a=dict(code='600034',snapshot_id=s['snapshot_id'],primary_method='fcff',cases=[operating_case(scenario=x) for x in ('conservative','base','upside')])
    svc.value.save_assumptions('600034',SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=0,assumptions=a))
    r=svc.value.get('600034')
    assert r['strategy']['expectations']['state']!='solved'


def test_inverse_and_guidance_use_the_same_model_override_and_event_adjusted_case(tmp_path,monkeypatch):
    svc=value_service(tmp_path);monkeypatch.setattr(svc.value,'_quote',lambda stock:dict(valid=True,price=17.5,trade_date='2026-10-30',basis='raw'))
    d=svc.repo.latest('free','research_data',key='free:600034')
    svc.repo.append('free','research_data','free:600034',d|dict(events=[dict(id='E1',family_id='fam',published_at='2026-10-20',title='经营变化')]))
    s=svc.value.capture('600034');a=dict(code='600034',snapshot_id=s['snapshot_id'],primary_method='fcff',
        cases=[operating_case(scenario=x) for x in ('conservative','base','upside')],
        economic_model_override=dict(model='operating',reason='人工核对主营',evidence_ids=[s['facts'][0]['fact_id']]),
        driver_changes=[dict(event_id='E1',field='ebit_margin',unit='ratio',old=.2,new=.3,years=[1,2,3,4,5],
            temporal_type='structural',include_terminal=True,terminal_old=.2,already_in_baseline=False,rationale='经营利润率结构变化',sources=['E1'])])
    svc.value.save_assumptions('600034',SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=0,assumptions=a))
    svc.value.evaluate('600034',EvaluateValueRequest(snapshot_id=s['snapshot_id'],assumptions_revision=1))
    r=svc.value.get('600034')
    assert abs(r['strategy']['expectations']['solution'])<.0001
    assert any(g['method']=='fcff' for g in r['strategy']['method_guidance'])


def test_first_forward_observation_survives_more_than_a_hundred_revisions(tmp_path):
    svc=value_service(tmp_path);s=svc.value.capture('600034');fid=s['facts'][0]['fact_id']
    obs=dict(metric='revenue',period='2027-09-30',value=100.0,unit='CNY',basis='ttm',sources=[fid],rationale='原始经营假设')
    for i in range(1,102):
        a=dict(code='600034',snapshot_id=s['snapshot_id'],revision=i,cases=[],primary_method='fcff',forecast_observations=[obs|dict(value=100.0 if i==1 else 140.0)])
        svc.repo.append('free','value_assumptions','free:600034',a)
    result=svc.value.get('600034')['strategy']['monitoring']['forward_checks']
    assert result[0]['forecast']==100.0 and result[0]['revision']==1


def test_peer_rows_include_matching_operating_and_cash_metrics(tmp_path):
    from tests.test_a_share_value_economics import view
    svc=value_service(tmp_path);v=view()
    data=dict(facts=[dict(fact_id='Q1',source='eastmoney/stock_value_em',values=dict(trade_date='2026-10-30',market_cap=200))])
    row=svc.value._peer_row(dict(code='600034',identity_verified=True),data,{},v,{})
    assert row['metrics']['roe']==pytest.approx(.1)
    assert row['metrics']['operating_margin']==.2
    assert row['metrics']['cash_yield']==.08
    assert row['metric_basis']['cash_yield']['date']=='2026-10-30'
    assert '合并' in row['metric_basis']['cash_yield']['definition']


def test_monitor_rules_and_frozen_forward_observations_roundtrip_without_model_calls(tmp_path):
    svc=value_service(tmp_path);s=svc.value.capture('600034');fid=s['facts'][0]['fact_id']
    a=dict(code='600034',snapshot_id=s['snapshot_id'],cases=[],monitor_rules=[dict(id='sales',metric='revenue',
        operator='lt',threshold=80.0,unit='CNY',target_period='2027-09-30',review_on='2027-10-31',sources=[fid],rationale='收入低于假设则复核')],
        forecast_observations=[dict(metric='revenue',period='2027-09-30',value=100.0,unit='CNY',sources=[fid],rationale='基于已披露规模的待验证假设')])
    saved=svc.value.save_assumptions('600034',SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=0,assumptions=a))
    assert saved['monitor_rules'][0]['threshold']==80
    result=svc.value.get('600034')
    assert result['strategy']['monitoring']['rules'][0]['state']=='pending'
    assert result['strategy']['monitoring']['forward_checks'][0]['state']=='pending'
    assert svc.repo.manual_usage('free','2026-10-30')==0
    a['monitor_rules'][0]['sources']=['not-known']
    with pytest.raises(ValueError,match='来源'):
        svc.value.save_assumptions('600034',SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=1,assumptions=a))


def test_assumptions_optimistic_revision_and_zero_ai_calculation(tmp_path):
    svc = value_service(tmp_path)
    s = svc.value.capture('600034')
    a = dict(snapshot_id=s['snapshot_id'], code='600034', primary_method='fcff',
             cases=[operating_case(scenario=x) for x in ['conservative', 'base', 'upside']])
    body = SaveValueRequest(snapshot_id=s['snapshot_id'], expected_revision=0, assumptions=a, confirmed=True)
    saved = svc.value.save_assumptions('600034', body)
    assert saved['revision'] == 1
    with pytest.raises(ValueError, match='版本'):
        svc.value.save_assumptions('600034', body)
    result = svc.value.evaluate('600034', EvaluateValueRequest(snapshot_id=s['snapshot_id'], assumptions_revision=1))
    assert result['valuation_state'] in ('research_only', 'review_required')
    assert svc.repo.manual_usage('free', '2026-10-30') == 0


def test_manual_supplement_is_not_an_override_or_historical_fact(tmp_path):
    svc = value_service(tmp_path)
    s = svc.value.capture('600034')
    body = SupplementValueRequest(snapshot_id=s['snapshot_id'], attested=True, facts=[dict(metric='assets', value=300,
        unit='CNY', report_period='2025-12-31', period_basis='instant', scope='consolidated', attribution='all_claims',
        url='https://www.cninfo.com.cn/example', title='人工核对原文', published_at='2026-03-30', quote='资产300元', reason='核对差异')])
    result = svc.value.supplement('600034', body)
    assert result['snapshot_id'] != s['snapshot_id']
    assert result['financial_view']['conflicts']
    assert result['facts'][-1]['vintage_quality'] == 'user_attested'


def test_mode_change_does_not_read_other_profile_snapshot(tmp_path):
    svc = value_service(tmp_path)
    svc.value.capture('600034')
    stock = svc.market.repo.stock('free', '600034')
    svc.market.repo.replace_catalog('tushare2000', 'paid-catalog', [stock])
    svc.settings = svc.settings.model_copy(update={'mode': 'tushare2000'})
    assert svc.value.get('600034')['snapshot'] is None


def test_manual_business_model_and_peer_attestations_are_auditable(tmp_path):
    svc = value_service(tmp_path)
    s = svc.value.capture('600034')
    a = dict(code='600034', snapshot_id=s['snapshot_id'], primary_method='fcff',
        cases=[operating_case(scenario=x) for x in ('conservative','base','upside')],
        economic_model_override=dict(model='operating',reason='核对年度报告主营',evidence_ids=[s['facts'][0]['fact_id']]))
    saved = svc.value.save_assumptions('600034', SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=0,assumptions=a,confirmed=False))
    report = svc.value.evaluate('600034', EvaluateValueRequest(snapshot_id=s['snapshot_id'],assumptions_revision=saved['revision']))
    assert all(c['state']=='ready' for c in report['valuation_cases'])
    assert report['valuation_state']=='draft'


def test_duplicate_primary_scenarios_are_not_silently_overwritten(tmp_path):
    svc = value_service(tmp_path)
    s = svc.value.capture('600034')
    a = dict(code='600034',snapshot_id=s['snapshot_id'],cases=[operating_case(),operating_case()])
    with pytest.raises(ValueError,match='重复'):
        svc.value.save_assumptions('600034',SaveValueRequest(snapshot_id=s['snapshot_id'],expected_revision=0,assumptions=a))


def test_pending_peer_data_is_visible_and_prevents_paid_generation(tmp_path):
    from src.schemas.a_share_value import GenerateValueRequest
    svc=value_service(tmp_path)
    svc.settings=svc.settings.model_copy(update={'research_enabled':True,'model':'mock'})
    snapshot=svc.value.capture('600034')
    task=svc.market.repo.enqueue('free','peer-pending','research_data',dict(code='600001',root_code='600034',settings=svc.settings.model_dump()),95)
    svc.market.repo.set_state('free','research_peers:600034',dict(task_ids=[task]))
    assert svc.value.get('600034')['status']=='preparing'
    with pytest.raises(ValueError,match='同行'):
        svc.value.generate('600034',GenerateValueRequest(snapshot_id=snapshot['snapshot_id']))


def test_user_can_correct_own_supplement_without_erasing_journal_or_provider(tmp_path):
    svc=value_service(tmp_path);s=svc.value.capture('600034')
    fact=dict(metric='cash',value=100,unit='CNY',report_period='2025-12-31',period_basis='instant',scope='consolidated',
        attribution='all_claims',url='https://example.com/report',title='核对原文',published_at='2026-03-30',quote='资金100',reason='核实')
    first=svc.value.supplement('600034',SupplementValueRequest(snapshot_id=s['snapshot_id'],attested=True,facts=[fact]))
    own=next(f for f in first['facts'] if f['vintage_quality']=='user_attested')
    second=svc.value.supplement('600034',SupplementValueRequest(snapshot_id=first['snapshot_id'],attested=True,
        facts=[fact | dict(value=200,supersedes_fact_id=own['fact_id'],reason='更正录入错误')]))
    assert own['fact_id'] not in {f['fact_id'] for f in second['facts']}
    assert second['financial_view']['latest']['cash']['value']==200
    assert len(svc.repo.records('free','value_supplements',key='free:600034'))==2
    with pytest.raises(ValueError):
        svc.value.supplement('600034',SupplementValueRequest(snapshot_id=second['snapshot_id'],attested=True,
            facts=[fact | dict(supersedes_fact_id=s['facts'][0]['fact_id'])]))


def test_eta_uses_observed_same_model_durations_only(tmp_path):
    svc=value_service(tmp_path)
    assert svc.value._eta('mock',10) is None
    for seconds in (50,60,70):
        svc.repo.append('free','value_review','free:600034',dict(status='partial',model='mock',elapsed_seconds=seconds))
    assert svc.value._eta('mock',10)==[40,60]
    assert svc.value._eta('different',10) is None
    assert svc.value._eta('mock',80) is None


def test_current_integrated_case_dictionary_is_reused_with_version_binding(tmp_path,monkeypatch):
    from src.schemas.a_share_integrated import VERSION
    from src.services.a_share_market_service import source_signature
    svc=value_service(tmp_path)
    svc.repo.append('free','research_pointer','free:600034',dict(data_hash='current'))
    bundle=dict(code='600034',version=VERSION,cutoff='2026-10-20',cases={'qualified_count':0,'reason':'严格样本不足'},
        history_binding=svc.integrated._binding('600034'),context=dict(source_signature=list(source_signature(svc.settings))))
    monkeypatch.setattr(svc.integrated,'bundle',lambda _:bundle)
    snapshot=svc.value.capture('600034')
    assert snapshot['cases']==[bundle['cases']]
    assert any(e['id']=='VALUE_CASES' for e in snapshot['evidence'])


def test_prepared_data_without_a_model_run_has_explicit_progress(tmp_path):
    svc=value_service(tmp_path)
    svc.value.capture('600034')
    svc.market.repo.set_state('free','value_progress:600034',dict(phase='preparing',percent=0,message='排队补齐财报'))
    result=svc.value.get('600034')
    assert result['status']=='ready' and result['report'] is None and result['review'] is None
    assert result['progress']['phase']=='prepared'
    assert '尚未调用AI' in result['progress']['message']


def test_value_preparation_uses_same_download_capital_when_snapshot_endpoint_fails(tmp_path,monkeypatch):
    from data_provider.a_share_value_facts import normalize_valuation_capital
    svc=value_service(tmp_path)
    now=svc.value.now()
    fact=normalize_valuation_capital('600034',[{'数据日期':now[:10],'总股本':734199310}], 'eastmoney/stock_value_em',now)[0]
    class Source:
        def __init__(self,*args): pass
        def financials(self,*args): return dict(facts=[],value_facts=[],status='missing')
        def capital(self,*args): return dict(facts=[],status='failed',reason='push2 offline')
        def valuation(self,*args): return dict(facts=[],history=[],status='missing',value_facts=[fact])
        def distributions(self,*args): return dict(items=[],errors=[],status='missing')
        def disclosures(self,*args): return dict(events=[],errors=[],status='missing')
        def news(self,*args): return dict(facts=[],status='missing')
    monkeypatch.setattr('src.services.a_share_integrated_service.ResearchSources',Source)
    action=svc.value.prepare('600034',refresh=True)
    svc.integrated.handle_task(svc.market.repo.task(action['task_id']))
    result=svc.value.get('600034')
    assert result['snapshot']['financial_view']['current_capital']['value']==734199310
    assert not any('总股数未核实' in m for m in result['snapshot']['missing'])
    data=svc.repo.latest('free','research_data',key='free:600034')
    assert next(c for c in data['coverage'] if c['category']=='capital')['sources']==['eastmoney/stock_value_em']
    assert svc.repo.manual_usage('free',now[:10])==0


def test_old_failed_model_does_not_hide_new_data_preparation(tmp_path):
    from src.schemas.a_share_value import GenerateValueRequest
    from datetime import timezone
    svc=value_service(tmp_path)
    svc.settings=svc.settings.model_copy(update={'research_enabled':True,'model':'mock'})
    snapshot=svc.value.capture('600034')
    action=svc.value.generate('600034',GenerateValueRequest(snapshot_id=snapshot['snapshot_id']))
    task=svc.market.repo.claim('free',datetime.now(timezone.utc),kinds=['value_research'])
    svc.market.repo.finish(task['id'],task['claim_version'],'failed',error='previous model failure')
    svc.value.prepare('600034',refresh=True)
    result=svc.value.get('600034')
    assert result['task']['id']==action['task_id'] and result['task']['state']=='failed'
    assert result['data_task']['state']=='pending'
    assert result['status']=='preparing'


@pytest.mark.parametrize('source_status,matching_signature,expected_count',[
    ('failed',True,1),('failed',False,0),('ready',True,0),('missing',True,0),('ready_with_metadata',True,1),('ready_after_partial_batch',True,1),('ready_after_disjoint_batch',True,1),('failed_after_authoritative_empty',True,0),
])
def test_failed_disclosure_refresh_preserves_only_same_source_archive(tmp_path,monkeypatch,source_status,matching_signature,expected_count):
    from src.services.a_share_market_service import source_signature
    svc=value_service(tmp_path)
    now=svc.value.now()
    signature=list(source_signature(svc.settings))
    old=dict(id='old-capital',code='600034',title='回购进展公告',kind='buyback',
        published_at='2026-10-29T00:00:00+08:00',observed_at='2026-10-29T12:00:00+08:00',
        available_at='2026-10-29T12:00:00+08:00',url='https://example.com/report',
        text_status='ready',text='累计回购股份，未完成计划。',text_hash='original')
    archive=dict(facts=[],value_facts=[],events=[old,old|dict(id='other',code='600035'),
        old|dict(id='future',published_at='2027-01-01T00:00:00+08:00')],
        coverage=[],source_signature=signature if matching_signature else ['other-source'],fetched_at=old['observed_at'])
    svc.repo.append('free','research_data','free:600034',archive)
    # An already persisted failure must not prevent recovery from the journal.
    svc.repo.append('free','research_data','free:600034',archive|dict(events=[]))
    if source_status=='ready_after_partial_batch':
        svc.repo.append('free','research_data','free:600034',archive|dict(events=[old|dict(text='',text_status='missing',text_hash=None)]))
    if source_status=='ready_after_disjoint_batch':
        svc.repo.append('free','research_data','free:600034',archive|dict(events=[old|dict(id='newer-unrelated')]))
    if source_status=='failed_after_authoritative_empty':
        svc.repo.append('free','research_data','free:600034',archive|dict(events=[],coverage=[dict(category='disclosures',status='ready',errors=[])]))
        svc.repo.append('free','research_data','free:600034',archive|dict(events=[],coverage=[dict(category='disclosures',status='failed',errors=['offline'])]))
    class Source:
        def __init__(self,*args): pass
        def financials(self,*args): return dict(facts=[],value_facts=[],status='missing')
        def capital(self,*args): return dict(facts=[],status='failed')
        def valuation(self,*args): return dict(facts=[],history=[],status='missing')
        def distributions(self,*args): return dict(items=[],errors=[],status='missing')
        def disclosures(self,*args): return dict(events=[old|dict(text='',text_status='missing',text_hash=None)] if source_status.startswith('ready_') else [],errors=[{'source':'cninfo','error':'RuntimeError'}] if source_status.startswith('failed') else [],status='ready' if source_status.startswith('ready_') else 'failed' if source_status.startswith('failed') else source_status)
        def news(self,*args): return dict(facts=[],status='missing')
    monkeypatch.setattr('src.services.a_share_integrated_service.ResearchSources',Source)
    monkeypatch.setattr('src.services.a_share_integrated_service.fetch_disclosure_text',lambda *args:pytest.fail('ready cache must not be refetched'))
    action=svc.value.prepare('600034',refresh=True)
    svc.integrated.handle_task(svc.market.repo.task(action['task_id']))
    data=svc.repo.latest('free','research_data',key='free:600034')
    assert len(data['events'])==expected_count
    coverage=next(c for c in data['coverage'] if c['category']=='disclosures')
    if expected_count and source_status=='failed':
        assert data['events'][0]==old
        assert coverage['status']=='partial' and coverage['cached'] is True
        assert coverage['cached_at']==old['observed_at'] and coverage['errors']
        assert any('公告接口本次失败' in m for m in svc.value.get('600034')['snapshot']['missing'])
    else:
        assert not coverage.get('cached')
        if expected_count:
            assert data['events'][0]==old
    assert svc.repo.manual_usage('free',now[:10])==0


def test_cached_disclosure_freshness_invalidates_existing_snapshot(tmp_path):
    svc=value_service(tmp_path)
    original=svc.value.capture('600034')
    data=svc.repo.latest('free','research_data',key='free:600034')
    svc.repo.append('free','research_data','free:600034',data|dict(coverage=[dict(category='disclosures',status='partial',cached=True,cached_at=svc.value.now(),errors=['offline'])]))
    assert svc.value.get('600034')['status']=='stale'
    updated=svc.value.capture('600034')
    assert updated['snapshot_id']!=original['snapshot_id']
    assert any('公告接口本次失败' in m for m in updated['missing'])
