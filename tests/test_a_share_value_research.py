import pytest
from concurrent.futures import ThreadPoolExecutor
from src.services.a_share_value_research import ValueResearchEngine
from src.schemas.a_share_value import GenerateValueRequest
from tests.test_a_share_value_service import value_service


def test_only_delivered_citations_survive_and_one_call_is_counted(tmp_path):
    svc = value_service(tmp_path)
    snapshot = svc.value.capture('600034')
    fact = snapshot['facts'][0]['fact_id']
    calls = []
    def completion(messages, model):
        calls.append(messages)
        return dict(perspectives=[dict(text='可核对的财务研究', sources=[fact]), dict(text='伪造乐观结论', sources=['invented'])],
                    theses=[], proposed_assumptions=None, counterevidence=[], missing=['现金受限情况未取得'])
    result = ValueResearchEngine(svc.repo, completion).run(snapshot, svc.settings.model_copy(update={'model': 'mock'}), lambda p: None)
    assert len(calls) == 1
    assert len(result['perspectives']) == 1
    assert result['rejected'] == 1
    assert svc.repo.manual_usage('free', snapshot['cutoff'][:10]) == 1


def test_atomic_duplicate_and_force_inflight_share_one_task(tmp_path):
    svc = value_service(tmp_path)
    svc.settings = svc.settings.model_copy(update={'research_enabled': True, 'model': 'mock'})
    snapshot = svc.value.capture('600034')
    req = GenerateValueRequest(snapshot_id=snapshot['snapshot_id'])
    results = list(ThreadPoolExecutor(4).map(lambda _: svc.value.generate('600034', req), range(8)))
    assert len({r['task_id'] for r in results}) == 1
    forced = svc.value.generate('600034', GenerateValueRequest(snapshot_id=snapshot['snapshot_id'], force=True))
    assert forced['task_id'] == results[0]['task_id']


def test_crash_after_paid_attempt_is_not_replayed(tmp_path, monkeypatch):
    svc = value_service(tmp_path)
    svc.settings = svc.settings.model_copy(update={'research_enabled': True, 'model': 'mock'})
    snapshot = svc.value.capture('600034')
    action = svc.value.generate('600034', GenerateValueRequest(snapshot_id=snapshot['snapshot_id']))
    svc.repo.append('free', 'value_attempt', action['task_id'], {'started': True})
    monkeypatch.setattr(ValueResearchEngine, 'run', lambda *a, **kw: pytest.fail('second paid request'))
    svc.value.jobs.set_profile('free')
    assert svc.value.jobs.run_one()
    state = svc.value.get('600034')
    assert state['review']['status'] == 'interrupted'
    assert svc.repo.manual_usage('free', snapshot['cutoff'][:10]) == 0


def test_model_change_during_request_keeps_old_result_out_of_current_report(tmp_path, monkeypatch):
    svc = value_service(tmp_path)
    svc.settings = svc.settings.model_copy(update={'research_enabled':True,'model':'old-model'})
    snapshot=svc.value.capture('600034')
    action=svc.value.generate('600034',GenerateValueRequest(snapshot_id=snapshot['snapshot_id']))
    def changed(*args,**kwargs):
        svc.settings=svc.settings.model_copy(update={'model':'new-model'})
        return dict(code='600034',snapshot_id=snapshot['snapshot_id'],model='old-model',status='partial',missing=[])
    monkeypatch.setattr(ValueResearchEngine,'run',changed)
    svc.value.jobs.set_profile('free');svc.value.jobs.run_one()
    assert svc.repo.latest('free','value_review',key='free:600034') is None
    assert svc.repo.latest('free','value_review_history',key=action['task_id'])


def test_evidence_budget_keeps_latest_operating_data_with_long_cash_history(tmp_path):
    import json
    from data_provider.a_share_value_facts import normalize_value_statements
    svc=value_service(tmp_path);snapshot=svc.value.capture('600034')
    now=snapshot['cutoff']
    income=normalize_value_statements('600034',[dict(ts_code='600034.SH',end_date='20260930',ann_date='20261020',report_type='1',total_revenue=100)],'tushare/income',now)
    cash=[]
    for year in range(1980,2026):
        for month in ('03-31','06-30','09-30','12-31'):
            cash+=normalize_value_statements('600034',[dict(SECUCODE='600034.SH',REPORT_DATE=f'{year}-{month}',NOTICE_DATE='2026-03-30',MONETARYFUNDS=year)],'eastmoney/stock_balance_sheet_by_report_em',now)
    snapshot['facts']+=cash+income
    snapshot['evidence']=[dict(id=f['fact_id'],source=f['source'],content=json.dumps(f,ensure_ascii=False)) for f in snapshot['facts']]
    sent=[]
    def completion(messages,model):
        assert len(json.dumps(messages,ensure_ascii=False).encode())<=48000
        sent.extend(e['id'] for e in json.loads(messages[1]['content'])['evidence'])
        return dict(perspectives=[],proposed_assumptions=None,missing=[])
    ValueResearchEngine(svc.repo,completion).run(snapshot,svc.settings.model_copy(update={'model':'mock'}),lambda p:None)
    assert income[0]['fact_id'] in sent


def test_value_call_has_structured_output_budget_without_capping_configured_reasoner(monkeypatch):
    from types import SimpleNamespace
    import src.config
    from src.services.a_share_research import completion_params
    config=SimpleNamespace(llm_model_list=[dict(model_name='mock',litellm_params={'model':'mock'})],litellm_model='mock')
    monkeypatch.setattr(src.config,'get_config',lambda:config)
    params=completion_params('mock',purpose='value')
    assert params['max_tokens']>=8192 and params['timeout']>=300
    assert params['num_retries']==0
    config.llm_model_list[0]['litellm_params'].update(max_completion_tokens=131072,timeout=1800,reasoning_effort='xhigh')
    params=completion_params('mock',purpose='value')
    assert params['max_completion_tokens']==131072 and params['timeout']==1800
    assert 'max_tokens' not in params


def test_delivery_keeps_quote_dividends_capital_notes_and_older_annuals_when_events_flood_snapshot(tmp_path):
    import json
    from data_provider.a_share_value_facts import normalize_value_statements
    svc=value_service(tmp_path);s=svc.value.capture('600034');now=s['cutoff']
    for year in range(2017,2026):
        s['facts']+=normalize_value_statements('600034',[dict(ts_code='600034.SH',end_date=f'{year}1231',ann_date='20260330',report_type='1',total_revenue=100+year,n_income_attr_p=20)],'tushare/income',now)
    s['evidence']=[dict(id=f['fact_id'],source=f['source'],content=json.dumps(f)) for f in s['facts']]
    s['evidence'].append(dict(id='QUOTE',source='eastmoney/stock_value_em',content=json.dumps(dict(values=dict(close=108,pe_ttm=16.5,trade_date='2026-10-30')))))
    s['evidence'].append(dict(id='DIVIDEND',source='eastmoney/stock_fhps_detail_em',content=json.dumps(dict(report_period='2025-12-31',cash_per_share=2.5,status='implemented'))))
    s['events']=[dict(id=f'E{i}',title='董事会决议公告',published_at='2026-10-29',text_status='missing',text='') for i in range(900)]
    text='财报标题\n'+'无关正文\n'*2000+'公司在香港联交所发行H股，募集资金增加货币资金；总股本为734199310股。'+'\n其他内容'*100
    s['events'].insert(0,dict(id='REPORT',title='2026年第三季度报告',kind='earnings',published_at='2026-10-30',text_status='ready',text=text))
    s['evidence'] += [dict(id=e['id'],source='cninfo',content=json.dumps(e,ensure_ascii=False)[:6000]) for e in s['events']]
    delivered={}
    def completion(messages,model):
        assert len(json.dumps(messages,ensure_ascii=False).encode())<=48000
        delivered.update({e['id']:e for e in json.loads(messages[1]['content'])['evidence']})
        return dict(perspectives=[],proposed_assumptions=None,missing=[])
    result=ValueResearchEngine(svc.repo,completion).run(s,svc.settings.model_copy(update={'model':'mock'}),lambda p:None)
    assert {'QUOTE','DIVIDEND','REPORT'} <= delivered.keys()
    assert '734199310' in json.dumps(delivered['REPORT'],ensure_ascii=False)
    assert any(f['report_period']=='2021-12-31' and f['fact_id'] in result['sent_ids'] for f in s['facts'])


def test_value_delivery_includes_latest_full_annual_notes_and_peer_context(tmp_path):
    import json
    from src.services.a_share_value_research import build_value_payload
    svc=value_service(tmp_path);s=svc.value.capture('600034')
    annual='目录：审计意见、货币资金。\n'+'无关正文\n'*3000+'审计意见\n我们认为，上述报表公允反映财务状况。\n所有权或使用权受限资产\n受限货币资金为168万元。'
    s['events']=[dict(id='Q3',title='2026年第三季度报告',kind='earnings',published_at='2026-10-30',text_status='ready',text='最新三季报'),dict(id='ANNUAL',title='2025年年度报告',kind='earnings',published_at='2026-03-31',text_status='ready',text=annual)]
    s['evidence'] += [dict(id=e['id'],source='cninfo',content=json.dumps(e,ensure_ascii=False)[:6000]) for e in s['events']]
    s['evidence'].append(dict(id='VALUE_PEERS',source='同行候选资料',content=json.dumps({'candidates':[{'code':'600001','metrics':{'pe':20}}],'confirmed':[]})))
    p,sent,_=build_value_payload(s)
    delivered={e['id']:e for e in p['evidence']}
    assert {'Q3','ANNUAL','VALUE_PEERS'}<=sent
    text=json.dumps(delivered['ANNUAL'],ensure_ascii=False)
    assert '168万元' in text and '公允反映' in text
    assert 'candidates' in json.dumps(delivered['VALUE_PEERS'])


def test_heavy_current_statements_do_not_displace_annual_current_capital_or_peers(tmp_path):
    import json
    from data_provider.a_share_value_facts import CONTRACTS,normalize_value_statements
    from src.services.a_share_value_research import build_value_payload,PROMPT
    svc=value_service(tmp_path);s=svc.value.capture('600034')
    for source,(mapping,index) in CONTRACTS.items():
        if index: continue
        for period in ('2025-12-31','2026-09-30'):
            data=dict(SECUCODE='600034.SH',REPORT_DATE=period,NOTICE_DATE='2026-10-20')
            data.update({aliases[0]:float(i+100) for i,aliases in enumerate(mapping.values())})
            s['facts']+=normalize_value_statements('600034',[data],source,s['cutoff'])
    s['evidence']=[dict(id=f['fact_id'],source=f['source'],content=json.dumps(f,ensure_ascii=False)) for f in s['facts']]
    text='我们认为，报表公允反映公司财务状况。所有权或使用权受限资产。'+'审计现金资金数据。'*600
    s['events']=[dict(id=i,title=t,published_at=d,text_status='ready',text=text,kind='earnings') for i,t,d in [('ANNUAL','2025年年度报告','2026-03-31'),('Q3','2026年第三季度报告','2026-10-30'),('HALF','2026年半年度报告','2026-08-30'),('CAP','股份回购进展公告','2026-10-10')]]
    s['evidence'] += [dict(id=e['id'],source='cninfo',content=json.dumps(e)) for e in s['events']]
    s['evidence'] += [dict(id=f'DIV{i}',source='eastmoney/stock_fhps_detail_em',content=json.dumps(dict(report_period=f'202{i}-12-31',cash_per_share=2.5,description='详细历史分配资料'*200))) for i in range(9)]
    s['evidence'].append(dict(id='VALUE_PEERS',source='同行候选资料',content=json.dumps(dict(candidates=[dict(code=f'60000{i}',metrics=dict(pe=20,pb=2),metric_basis={}) for i in range(7)],confirmed=[]))))
    p,sent,_=build_value_payload(s)
    assert {'ANNUAL','Q3','HALF','CAP','VALUE_PEERS'}<=sent
    assert len(json.dumps([dict(role='system',content=PROMPT),dict(role='user',content=json.dumps(p,ensure_ascii=False))],ensure_ascii=False).encode())<=48000
