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
