import pytest
from src.schemas.a_share import AssistantSettings
from data_provider.a_share_fundamentals import ResearchSources


def test_free_dividend_description_has_explicit_per_ten_basis_and_no_paid_count():
    from data_provider.a_share_value_facts import normalize_distributions
    rows=[{'报告期':'2025-12-31','现金分红-现金分红比例':3,'现金分红-现金分红比例描述':'10派3元(含税)',
        '方案进度':'实施分配','股权登记日':'2026-06-10','除权除息日':'2026-06-11','最新公告日期':'2026-06-01'}]
    items=normalize_distributions('000807',rows,'eastmoney/stock_fhps_detail_em','2026-10-30T10:00:00+08:00')
    assert items[0]['cash_per_share']==pytest.approx(.3)
    assert items[0]['tax_basis']=='gross' and items[0]['payment_date'] is None
    assert items[0]['status']=='implemented'
    assert 'total_cash' not in items[0]  # No current-shares × old per-share fiction.


def test_tushare_uses_gross_per_share_and_does_not_treat_proposal_as_paid():
    from data_provider.a_share_value_facts import normalize_distributions
    row=dict(ts_code='000807.SZ',end_date='20251231',ann_date='20260330',cash_div_tax=.4,cash_div=.3,
        div_proc='预案',ex_date=None,pay_date=None,stk_div=.1)
    item=normalize_distributions('000807',[row],'tushare/dividend','2026-10-30')[0]
    assert item['cash_per_share']==.4 and item['status']=='proposed'
    assert item['stock_per_share']==.1


def test_distribution_source_respects_no_free_fallback():
    calls=[]
    class Provider:
        def call(self,name,params=None,tushare=False):
            calls.append((name,tushare));raise RuntimeError('permission')
    source=ResearchSources(Provider(),AssistantSettings(mode='tushare2000',free_fallback=False))
    result=source.distributions('000807','2026-10-30')
    assert result['items']==[] and calls==[('dividend',True)]
