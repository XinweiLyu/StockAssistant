from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine
from src.repositories.a_share_repository import AssistantRepository
from src.services.a_share_service import AssistantService
from src.schemas.a_share import AssistantSettings, RiskSettings
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def service(tmp_path):
    repo=AssistantRepository(create_engine('sqlite:///' + str(tmp_path/'assistant.db')))
    return AssistantService(repo)


def test_demo_has_fictional_candidates_no_network_or_actual_trades(tmp_path):
    svc=service(tmp_path)
    svc.sync('daily')
    board=svc.dashboard()
    assert board['settings']['mode']=='demo'
    assert board['report']['candidates']
    assert all(c['code'].startswith('DEMO') for c in board['report']['candidates'])
    assert board['report']['demo']
    assert board['portfolio']['demo']
    assert board['job']['state']=='complete'


def test_switching_live_never_leaks_demo_candidates_or_portfolio(tmp_path):
    svc=service(tmp_path)
    svc.sync('daily')
    svc.save_settings(AssistantSettings(mode='free'))
    board=svc.dashboard()
    assert board['report'] is None
    assert board['portfolio']['nav'] is None
    assert not board['history']


def test_stop_cannot_be_silently_lowered_and_confirmation_is_audited(tmp_path):
    svc=service(tmp_path)
    svc.confirm_holding(dict(code='DEMO001',stop=12,sellable=100,note='手动核实'))
    svc.confirm_holding(dict(code='DEMO001',stop=11,sellable=0,note='用户重新确认'))
    assert len(svc.repo.records('demo','holding_constraint'))==2
    assert svc.repo.latest('demo','holding_constraint',key='DEMO001')['stop']==11


def test_verified_event_veto_persists_and_unverified_keyword_is_not_a_fact(tmp_path):
    svc=service(tmp_path)
    svc.sync('daily')
    svc.repo.add_event('demo',dict(source='test',title='立案调查',code='DEMO001',content='传闻'))
    event=svc.repo.records('demo','event')[0]
    assert not svc.major_risks().get('DEMO001')
    svc.verify_event(event['id'],dict(code='DEMO001',major_risk=True,note='已核对公告'))
    assert svc.major_risks()['DEMO001'] is True


def test_expired_report_remains_in_history_but_cannot_issue_new_actions(tmp_path):
    svc=service(tmp_path)
    svc.sync('daily')
    now=datetime(2030,1,1,10,0,tzinfo=ZoneInfo('Asia/Shanghai'))
    result=svc.check(now=now)
    assert all(c['check']['status']!='triggered' for c in result['candidates'])
    assert svc.repo.records('demo','report')


def test_resolving_one_event_cannot_clear_another_verified_major_risk(tmp_path):
    svc=service(tmp_path)
    svc.repo.add_event('demo',dict(source='test',title='风险1',code='DEMO039'))
    svc.repo.add_event('demo',dict(source='test',title='风险2',code='DEMO039'))
    ids=[r['id'] for r in svc.repo.records('demo','event')]
    for event_id in ids:
        svc.verify_event(event_id,dict(code='DEMO039',major_risk=True,note='已核实'))
    svc.verify_event(ids[0],dict(code='DEMO039',major_risk=False,note='该项已消除'))
    assert svc.major_risks()['DEMO039']


def test_demo_holding_confirmation_changes_risk_display_without_live_account(tmp_path):
    svc=service(tmp_path)
    svc.sync('daily')
    svc.confirm_holding(dict(code='DEMO039',stop=17,sellable=200,note='模拟手动核实'))
    result=svc.check()
    holding=next(h for h in result['holdings'] if h['code']=='DEMO039')
    assert holding['stop']==17 and holding['sellable']==200


def test_same_dataset_does_not_duplicate_report_observation_samples(tmp_path):
    svc=service(tmp_path)
    svc.sync('daily')
    svc.sync('daily')
    assert len(svc.repo.records('demo','report'))==1


def live_portfolio(svc, monkeypatch):
    from src.services import portfolio_service
    trade=SimpleNamespace(id=1,symbol='600001.SH',side='buy',quantity=1000,trade_date=date(2026,10,8),market='cn',currency='CNY')
    mock=Mock()
    mock.get_portfolio_snapshot.return_value=dict(accounts=[dict(market='cn',base_currency='CNY',positions=[dict(symbol='SH600001',quantity=1000,avg_cost=10,market_value_base=10000)])],total_cash=90000,limitations=[],realized_pnl=0,fee_total=0,tax_total=0)
    mock.repo.list_trades.return_value=[trade]
    mock.repo.list_corporate_actions.return_value=[]
    monkeypatch.setattr(portfolio_service,'PortfolioService',lambda:mock)
    svc.settings=AssistantSettings(mode='free',account_id=1)
    svc.repo.append('free','dataset','current',dict(as_of='2026-10-08',calendar=['2026-10-08','2026-10-09'],stocks=[dict(code='600001',sector='制造',as_of='2026-10-08',bars=[dict(close=10)])]))
    return mock,trade


def test_live_constraints_are_account_scoped_and_qualified_symbols_work(tmp_path,monkeypatch):
    svc=service(tmp_path)
    mock,_=live_portfolio(svc,monkeypatch)
    mock.get_portfolio_snapshot.return_value['accounts'][0]['positions'][0]['symbol']='600001'
    assert svc.portfolio()['positions'][0]['code']=='600001'
    svc.confirm_holding(dict(code='600001',stop=9,sellable=800,note='核实账户一'))
    assert svc.portfolio()['positions'][0]['sellable']==800
    svc.settings=svc.settings.model_copy(update={'account_id':2})
    other=svc.portfolio()['positions'][0]
    assert other['sellable'] is None and other['stop'] is None
    svc.settings=svc.settings.model_copy(update={'account_id':None})
    with pytest.raises(ValueError):
        svc.confirm_holding(dict(code='600001',stop=9,sellable=800,note='未选择账户'))


def test_exchange_qualified_holding_code_matches_market_data(tmp_path,monkeypatch):
    svc=service(tmp_path)
    live_portfolio(svc,monkeypatch)
    assert svc.portfolio()['positions'][0]['code']=='600001'


def test_flat_then_rebuy_requires_new_confirmation_and_resets_holding_age(tmp_path,monkeypatch):
    svc=service(tmp_path)
    mock,buy=live_portfolio(svc,monkeypatch)
    mock.get_portfolio_snapshot.return_value['accounts'][0]['positions'][0]['symbol']='600001'
    buy.symbol='600001'
    svc.confirm_holding(dict(code='600001',stop=9,sellable=800,note='核实旧持仓'))
    assert svc.portfolio()['positions'][0]['stop']==9
    today=date.today()
    sell=SimpleNamespace(id=2,symbol='SH600001',side='sell',quantity=1000,trade_date=today-timedelta(days=1),market='cn',currency='CNY')
    rebuy=SimpleNamespace(id=3,symbol='600001',side='buy',quantity=1000,trade_date=today,market='cn',currency='CNY')
    mock.repo.list_trades.return_value=[buy,sell,rebuy]
    p=svc.portfolio()['positions'][0]
    assert p['stop'] is None and p['sellable'] is None
    assert p['held_sessions']==0


def test_trigger_plan_is_the_displayed_and_exportable_plan(tmp_path,monkeypatch):
    svc=service(tmp_path)
    now=datetime(2026,10,9,10,0,tzinfo=ZoneInfo('Asia/Shanghai'))
    c=dict(code='DEMO001',sector='DS01',strategy='trend_v1',entry=19.9,high=19.9,atr=.5,market_ok=True,valid_date='2026-10-09')
    svc.repo.append('demo','report','current',dict(candidates=[c],demo=True,input_hash='hash'))
    svc.repo.append('demo','dataset','current',dict(calendar=['2026-10-09']))
    svc.repo.append('demo','quotes','current',dict(quotes={'DEMO001':dict(price=20.09,source_time=now.isoformat(),trade_date='2026-10-09',suspended=False,limit_up=22,limit_down=18)}))
    monkeypatch.setattr(svc,'portfolio',lambda:dict(nav=100000,cash=100000,total_value=0,complete=True,positions=[]))
    c=svc.check(now)['candidates'][0]
    assert c['check']['status']=='triggered'
    assert c['plan']==c['check']['plan']
    assert c['plan']['entry']==20.09 and c['plan']['quantity']==400 and c['plan']['stop']==19.09


def test_corrected_revision_can_resolve_same_logical_risk(tmp_path):
    svc=service(tmp_path)
    event=dict(source='test',url='https://example.com/notice',title='风险公告',code='DEMO039',published_at='2026-10-09',content='原始版本')
    svc.repo.add_event('demo',event)
    old=svc.repo.records('demo','event')[0]['id']
    svc.verify_event(old,dict(code='DEMO039',major_risk=True,note='已核实旧版本'))
    svc.repo.add_event('demo',event|{'content':'更正已解除'})
    new=svc.repo.records('demo','event')[0]['id']
    svc.verify_event(new,dict(code='DEMO039',major_risk=False,note='更正已核实'))
    assert not svc.major_risks().get('DEMO039')
    assert len(svc.repo.records('demo','verification'))==2


def test_observations_use_persistent_prices_after_candidate_leaves_pool(tmp_path):
    svc=service(tmp_path)
    calendar=[(date.today()+timedelta(days=i)).isoformat() for i in range(30)]
    svc.repo.append('demo','report','r',dict(candidates=[dict(code='DEMO001',strategy='trend_v1')]))
    svc.repo.append('demo','stock_data','DEMO001',dict(code='DEMO001',bars=[dict(date=d,adjusted_close=10+i) for i,d in enumerate(calendar)]))
    svc.repo.append('demo','dataset','current',dict(stocks=[],calendar=calendar))
    result=svc.observations()[0]['results']
    assert all(r['return'] is not None for r in result)


def test_research_excludes_other_company_search_results(tmp_path,monkeypatch):
    from src.services.a_share_research import ResearchEngine
    import src.services.a_share_service as module
    svc=service(tmp_path)
    svc.settings=AssistantSettings(research_enabled=True,model='mock')
    svc.repo.append('demo','report','r',dict(candidates=[dict(code='DEMO001')],input_hash='hash',source='demo',as_of='2026-10-09'))
    svc.repo.add_event('demo',dict(source='test/stock-news',code=None,related_code='DEMO002',title='其他公司'))
    svc.repo.add_event('demo',dict(source='test/stock-news',code=None,related_code='DEMO001',title='本公司'))
    svc.repo.add_event('demo',dict(source='test/market',code=None,title='市场资料'))
    captured=[]
    manual=[]
    def capture(self,code,evidence,*args,**kwargs):
        captured.extend(evidence)
        manual.append(kwargs.get('manual'))
    monkeypatch.setattr(ResearchEngine,'run',capture)
    class ImmediateThread:
        def __init__(self,target,**kwargs): self.target=target
        def start(self): self.target()
    monkeypatch.setattr(module.threading,'Thread',ImmediateThread)
    svc.research_async('DEMO001')
    text=' '.join(e['content'] for e in captured)
    assert '本公司' in text and '市场资料' in text and '其他公司' not in text
    assert manual == [True]


def test_invalid_daily_cache_retries_and_pending_samples_are_downloaded(tmp_path,monkeypatch):
    from tests.test_a_share_rules import bars
    svc=service(tmp_path)
    svc.settings=AssistantSettings(mode='free',pool_size=30)
    history=bars()
    as_of=history[-1]['date']
    calendar=[r['date'] for r in history]+[date.today().isoformat()]
    monkeypatch.setattr(svc,'_calendar',lambda:calendar)
    monkeypatch.setattr(svc,'portfolio',lambda:dict(positions=[]))
    monkeypatch.setattr(svc,'_metadata',lambda *args:{'股票简称':'样本','上市时间':'20200101'})
    monkeypatch.setattr(svc,'_fetch',lambda *args,**kwargs:(history,'akshare'))
    monkeypatch.setattr(svc,'_build_report',lambda data:None)
    svc.repo.append('free','universe',as_of,[dict(code='600001',amount=1e8)])
    svc.repo.append('free','stock_data','600001',dict(code='600001',sector=None,as_of=as_of,profile='free',bars=history[:-1]))
    svc.repo.append('free','report','past',dict(candidates=[dict(code='600002',strategy='trend_v1')]))
    called=[]
    monkeypatch.setattr(svc,'_history',lambda code,*args:(called.append(code) or history,'mock','qfq'))
    # Freeze the cutoff before today's close so the fixture's complete end date is used.
    import src.services.a_share_service as module
    monkeypatch.setattr(module,'now_local',lambda:datetime.combine(date.today(),datetime.min.time(),tzinfo=ZoneInfo('Asia/Shanghai')).replace(hour=10))
    svc._daily()
    assert '600001' in called and '600002' in called
    assert svc.repo.latest('free','dataset')['daily_complete']


def test_scheduler_retries_quality_failure_even_after_news_resets_job(tmp_path,monkeypatch):
    import src.services.a_share_service as module
    svc=service(tmp_path)
    svc.settings=AssistantSettings(mode='free')
    now=datetime(2026,10,9,19,0,tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr(module,'now_local',lambda:now)
    svc.repo.append('free','dataset','current',dict(as_of='2026-10-09',calendar=['2026-10-09'],daily_complete=False))
    selected=[]
    monkeypatch.setattr(svc,'sync_async',lambda kind:selected.append(kind) or True)
    svc.tick()
    assert selected==['daily']


def test_settings_change_immediately_recalculates_visible_plan(tmp_path,monkeypatch):
    svc=service(tmp_path)
    c=dict(code='DEMO001',sector='DS01',strategy='trend_v1',entry=20,high=20,atr=.5,market_ok=True,valid_date='2026-10-09')
    svc.repo.append('demo','report','current',dict(candidates=[c],demo=True,input_hash='hash'))
    monkeypatch.setattr(svc,'portfolio',lambda:dict(nav=100000,cash=100000,total_value=0,complete=True,positions=[]))
    svc.check()
    assert svc.dashboard()['report']['candidates'][0]['plan']['quantity']==400
    svc.save_settings(AssistantSettings(risk=RiskSettings(stock_cap=.02)))
    assert svc.dashboard()['report']['candidates'][0]['plan']['quantity']==0  # fee prevents a ¥2,000 lot
