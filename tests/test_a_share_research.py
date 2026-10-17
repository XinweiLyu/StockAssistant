from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.services.a_share_research import ResearchEngine, validate_claims
from src.schemas.a_share import AssistantSettings
import json


def test_fabricated_citations_and_model_action_fields_cannot_reach_report():
    result=validate_claims({'claims':[{'text':'事实','sources':['E999']},{'text':'趋势','sources':['D1']}],
                            'action':'BUY','quantity':99999}, {'D1'})
    assert result=={'claims':[{'text':'趋势','sources':['D1']}],'rejected':1}


def test_partial_role_failures_preserve_good_evidence_and_consume_budget(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db')))
    calls=[]
    def completion(messages, model):
        calls.append(messages)
        if len(calls)==2:
            raise TimeoutError('provider unavailable')
        return {'claims':[{'text':'有趋势证据','sources':['D1']}]}
    engine=ResearchEngine(repo,completion=completion)
    settings=AssistantSettings(mode='free',research_enabled=True,model='configured',daily_model_calls=3)
    evidence=[{'id':'D1','content':'已有完整日线趋势'}]
    result=engine.run('600001',evidence,'datahash',settings,'2026-10-09')
    assert repo.usage('free','2026-10-09')==3
    assert any(r['status']=='failed' for r in result['roles'])
    assert any(r['status']=='ok' for r in result['roles'])
    assert result['status']=='partial'
    assert len(calls)==3
    assert engine.run('600001',evidence,'datahash',settings,'2026-10-09')['cached']
    assert len(calls)==3


def test_disabled_research_makes_no_calls(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db')))
    engine=ResearchEngine(repo,completion=lambda *_:(_ for _ in ()).throw(AssertionError('unexpected call')))
    assert engine.run('600001',[],'hash',AssistantSettings(),'2026-10-09')['status']=='disabled'


def test_manual_research_ignores_daily_limit_but_counts_paid_attempts(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db')))
    calls=[]
    def complete(messages, model):
        calls.append(messages)
        return {'claims':[{'text':'需继续核对日线事实','sources':['D1']}]}
    settings=AssistantSettings(mode='free',research_enabled=True,model='mock',daily_model_calls=0)
    engine=ResearchEngine(repo,completion=complete)
    for code in ('600001','600002'):
        result=engine.run(code,[{'id':'D1','content':'完整日线'}],code,settings,'2026-10-09',manual=True)
        assert result['status']=='complete'
    assert len(calls)==6
    assert repo.usage('free','2026-10-09')==0
    assert repo.manual_usage('free','2026-10-09')==6


def test_changing_automatic_limit_does_not_repeat_completed_manual_research(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db')))
    calls=[]
    def complete(messages, model):
        calls.append(messages)
        return {'claims':[{'text':'需继续核对日线事实','sources':['D1']}]}
    engine=ResearchEngine(repo,completion=complete)
    evidence=[{'id':'D1','content':'完整日线'}]
    first=AssistantSettings(mode='free',research_enabled=True,model='mock',daily_model_calls=0)
    changed=first.model_copy(update={'daily_model_calls':20})
    engine.run('600001',evidence,'same-data',first,'2026-10-09',manual=True)
    assert engine.run('600001',evidence,'same-data',changed,'2026-10-09',manual=True)['cached']
    assert len(calls)==3


def test_only_complete_budgeted_evidence_is_citable_and_manager_sees_all_roles(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'db')))
    prompts=[]
    evidence=[dict(id='D1',content='长日线资料'*3000)]+[dict(id='E'+str(i),content='新闻资料'*100) for i in range(1,10)]
    def complete(messages,model):
        prompts.append(messages)
        return {'claims':[{'text':'引用未发送材料','sources':['E9']} ]}
    result=ResearchEngine(repo,complete).run('600001',evidence,'hash',AssistantSettings(mode='free',research_enabled=True,model='mock'),'2026-10-09')
    for prompt in prompts:
        data=json.loads(prompt[1]['content'])
        assert len(json.dumps(data['evidence'],ensure_ascii=False).encode())<=2200
        assert not any(e['id']=='E9' for e in data['evidence'])
    assert all(not r['claims'] for r in result['roles'])
    assert {r['role'] for r in json.loads(prompts[-1][1]['content'])['prior_roles']}=={r['role'] for r in result['roles'][:-1]}


def test_action_text_is_rejected_even_with_valid_evidence():
    result=validate_claims({'claims':[{'text':'建议立即买入10000股，仓位提高至100%','sources':['D1']},{'text':'营收假设有待公告核实','sources':['D1']}]},{'D1'})
    assert result['rejected']==1
    assert result['claims']==[{'text':'营收假设有待公告核实','sources':['D1']}]


def test_research_worker_uses_configured_reasoning_and_completion_budget(monkeypatch):
    from types import SimpleNamespace
    import src.config
    import src.services.a_share_research as research
    config=SimpleNamespace(llm_model_list=[dict(model_name='openai/test-reasoner',model_info={'assistant_research_stream':True},litellm_params={
        'model':'openai/test-reasoner','api_key':'test-only-key','api_base':'https://example.invalid/v1',
        'reasoning_effort':'xhigh','max_completion_tokens':131072,'timeout':1800,
        'extra_body':{'enable_thinking':True},'num_retries':7,
    })],litellm_model='openai/test-reasoner')
    monkeypatch.setattr(src.config,'get_config',lambda:config)
    def worker(*args,**kwargs):
        request=json.loads(kwargs['input'])
        params=request.get('params',{})
        assert params.get('reasoning_effort')=='xhigh'
        assert params['max_completion_tokens']==131072
        assert 'max_tokens' not in params
        assert params['timeout']==1800
        assert kwargs['timeout']==1810
        assert params['extra_body']=={'enable_thinking':True}
        assert params['num_retries']==0
        assert params['stream'] is True
        return SimpleNamespace(stdout='{"claims":[]}')
    monkeypatch.setattr(research.subprocess,'run',worker)
    assert ResearchEngine._complete([{'role':'user','content':'证据'}],'openai/test-reasoner')=={'claims':[]}


def test_research_worker_retains_default_bounds_for_ordinary_models(monkeypatch):
    from types import SimpleNamespace
    import src.config
    import src.services.a_share_research as research
    config=SimpleNamespace(llm_model_list=[dict(model_name='openai/test',litellm_params={
        'model':'openai/test','api_key':'test-only-key',
    })],litellm_model='openai/test')
    monkeypatch.setattr(src.config,'get_config',lambda:config)
    def worker(*args,**kwargs):
        params=json.loads(kwargs['input']).get('params',{})
        assert params.get('max_tokens')==800
        assert params['timeout']==35
        assert kwargs['timeout']==45
        return SimpleNamespace(stdout='{"claims":[]}')
    monkeypatch.setattr(research.subprocess,'run',worker)
    assert ResearchEngine._complete([],'openai/test')=={'claims':[]}


def test_streaming_worker_joins_answer_and_excludes_reasoning(monkeypatch,capsys):
    import io
    import runpy
    import sys
    from types import SimpleNamespace
    import litellm
    import src.services.a_share_research as research
    chunks=[
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None,reasoning_content='内部思考'))]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='{"claims":'))]),
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='[]}'))]),
    ]
    def provider(**params):
        assert params['stream'] is True
        assert params['num_retries']==0
        return iter(chunks)
    monkeypatch.setattr(litellm,'completion',provider)
    monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps({'params':{'model':'openai/test','stream':True},'messages':[]})))
    monkeypatch.setattr(sys,'argv',['worker','--completion'])
    runpy.run_path(research.__file__,run_name='__main__')
    assert json.loads(capsys.readouterr().out)=={'claims':[]}


def test_provider_billing_failure_is_readable_without_disclosing_process_or_provider_secrets(tmp_path):
    import subprocess
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'billing')))
    def completion(*_):
        raise subprocess.CalledProcessError(1,['python','--api-key=sk-process-secret'],
            stderr='BadRequestError: Arrearage: account overdue; api_key=sk-provider-secret')
    result=ResearchEngine(repo,completion=completion).run('600001',[{'id':'D1','content':'日线'}],'hash',
        AssistantSettings(mode='free',research_enabled=True,model='configured'),'2026-10-17',manual=True)
    failed=result['roles'][0]
    assert failed['status']=='failed'
    assert '欠费' in failed['message'] and 'Arrearage' in failed['message']
    assert 'sk-process-secret' not in json.dumps(result) and 'sk-provider-secret' not in json.dumps(result)


def test_provider_timeout_remains_a_timeout_without_leaking_request_input(tmp_path):
    import subprocess
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'timeout')))
    def completion(*_):
        raise subprocess.TimeoutExpired(['python','--api-key=sk-secret'],10,stderr='private payload')
    result=ResearchEngine(repo,completion=completion).run('600001',[{'id':'D1','content':'日线'}],'hash',
        AssistantSettings(mode='free',research_enabled=True,model='configured'),'2026-10-17',manual=True)
    assert '超时' in result['roles'][0]['message']
    assert 'sk-secret' not in json.dumps(result) and 'private payload' not in json.dumps(result)
