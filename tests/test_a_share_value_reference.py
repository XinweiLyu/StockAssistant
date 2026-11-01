from copy import deepcopy
from src.services.a_share_value_reference import build_value_reference
from src.services.a_share_value_valuation import evaluate_value


def snapshot():
    def field(value):
        return dict(value=value,unit='CNY',fact_ids=['F1'],period='2026-09-30')
    return dict(code='600034',name='测试',snapshot_id='s',cutoff='2026-10-30T10:00:00+08:00',
        facts=[],evidence=[dict(id='F1',source='财报',content='原文')],distributions=[dict(status='implemented',cash_per_share=1)],events=[],
        economic_model=dict(model='operating',allowed_methods=['ddm'],checklist=[]),peers={},
        binding=dict(eligibility={'eligible':True},quote={'price':30,'valid':True,'trade_date':'2026-10-30'}),
        financial_view=dict(latest_period='2026-09-30',current_capital={'value':10,'period':'2026-10-30','available_at':'2026-10-30T10:00:00+08:00','fact_ids':['F1']},
            ttm={k:field(v) for k,v in dict(net_profit=100,operating_cashflow=150,capex=30,interest_expense=2).items()},
            latest={k:field(v) for k,v in dict(minority_equity=0,treasury_share_cost=0).items()},conflicts=[],quality={}))


def test_reference_is_explicit_parameter_sensitivity_not_a_model_or_safe_price():
    result=build_value_reference(snapshot())
    assert result['state']=='ready'
    assert result['report']['valuation_state']=='reference'
    assert result['report']['parameter_origin']=='reference_sensitivity_v1'
    cases=result['report']['valuation_cases']
    assert len(cases)==3 and all(c['state']=='ready' for c in cases)
    assert all(c['value_per_share']>0 for c in cases)
    assert result['report']['comparison']['conditional_price'] is None
    assert result['report']['comparison']['margin'] is None
    assert result['assumptions']['confirmed'] is False
    assert all(c['parameter_origin']=='reference_sensitivity_v1' for c in result['assumptions']['cases'])


def test_missing_financial_or_capital_facts_do_not_become_reference_defaults():
    for mutate in ('interest','treasury','risk'):
        s=deepcopy(snapshot())
        if mutate=='interest':del s['financial_view']['ttm']['interest_expense']
        elif mutate=='treasury':del s['financial_view']['latest']['treasury_share_cost']
        else:s['binding']['eligibility']['eligible']=False
        result=build_value_reference(s)
        assert result['state']=='unavailable' and not result.get('report')


def test_reported_buyback_quantity_is_required_when_treasury_cost_is_positive():
    s=snapshot();s['financial_view']['latest']['treasury_share_cost']['value']=5
    assert build_value_reference(s)['state']=='unavailable'
    s['events']=[dict(id='F1',code='600034',source='cninfo',kind='buyback',published_at='2026-10-01',text_status='ready',text='累计已回购A股股数 1股；累计已回购A股金额 5元')]
    r=build_value_reference(s)
    assert r['state']=='ready'
    assert r['assumptions']['cases'][0]['capital_bridge']['initial_treasury_shares']==1


def test_post_statement_buyback_and_old_financials_do_not_become_current_zero_or_current_ttm():
    s=snapshot();s['events']=[dict(id='F1',code='600034',source='cninfo',kind='buyback',published_at='2026-10-10',text_status='ready',text='累计已回购A股股数1股，累计已回购A股金额5元')]
    assert build_value_reference(s)['state']=='unavailable'
    s=snapshot();s['financial_view']['latest_period']='2020-09-30'
    assert build_value_reference(s)['state']=='unavailable'


def test_reference_origin_survives_confirmation_and_disputed_parameters():
    s=snapshot();r=build_value_reference(s);a=r['assumptions'];a['confirmed']=True
    a['risk_review']={k:dict(status='reviewed',sources=['F1']) for k in ('audit','debt','capital','reinvestment','nonoperating_assets')}
    assert evaluate_value(a,s)['valuation_state']=='reference'
    a['cases'][0]['discount']=.01
    result=evaluate_value(a,s)
    assert result['valuation_state']=='disputed'
    assert result['parameter_origin']=='reference_sensitivity_v1'
    assert result['comparison']['margin'] is None and result['comparison']['conditional_price'] is None


def test_saved_disputed_and_historical_references_keep_origin_and_no_price_judgment(tmp_path,monkeypatch):
    from tests.test_a_share_value_service import value_service
    svc=value_service(tmp_path);monkeypatch.setattr(svc.value,'_quote',lambda stock:dict(price=60,valid=True,trade_date='2026-10-30'))
    current=svc.value.capture('600034')
    report=build_value_reference(snapshot())['report']
    svc.repo.append('free','value_report','free:600034',report|dict(snapshot_id='older'))
    svc.repo.append('free','value_report','free:600034',report|dict(snapshot_id=current['snapshot_id'],valuation_state='disputed'))
    result=svc.value.get('600034')
    assert result['report']['parameter_origin']=='reference_sensitivity_v1'
    assert result['report']['comparison']['margin'] is None
    assert result['history'][0]['parameter_origin']=='reference_sensitivity_v1'
