import pytest
from src.services.a_share_value_financials import build_financial_view

NOW='2026-11-16T08:00:00+00:00'


def fact(metric,value,start,end,basis='annual',currency='USD'):
    return dict(fact_id=metric+start+end,code='us:AAPL',market='us',currency=currency,
        metric=metric,value=float(value),unit=currency,report_period=end,period_start=start,period_end=end,
        period_basis=basis,scope='consolidated',attribution='all_claims',source='sec/companyfacts',raw_field=metric,
        published_at='2026-10-31T00:00:00+00:00',observed_at=NOW,available_at='2026-10-31T00:00:00+00:00',content_hash=metric+start+end)


def test_noncalendar_annual_and_ttm_are_recognized():
    facts=[fact('revenue',100,'2024-10-01','2025-09-30'),
        fact('revenue',40,'2024-10-01','2025-03-31','ytd'),fact('revenue',50,'2025-10-01','2026-03-31','ytd')]
    result=build_financial_view(facts,NOW)
    assert result['annual'][0]['period']=='2025-09-30'
    assert result['ttm']['revenue']['value']==110


def test_four_contiguous_quarters_and_currency_conflict():
    facts=[fact('revenue',v,a,b,'quarter') for v,a,b in [
        (10,'2025-10-01','2025-12-31'),(20,'2026-01-01','2026-03-31'),
        (30,'2026-04-01','2026-06-30'),(40,'2026-07-01','2026-09-30')]]
    assert build_financial_view(facts,NOW)['ttm']['revenue']['value']==100
    assert 'revenue' not in build_financial_view(facts[1:],NOW)['ttm']
    other=facts[-1]|dict(fact_id='conflict',currency='HKD',unit='HKD')
    assert build_financial_view(facts+[other],NOW)['conflicts']


def test_quarter_ttm_keeps_fiscal_year_end_quarter_separate_from_full_year():
    facts=[fact('revenue',400,'2025-01-01','2025-12-31'),
        *[fact('revenue',v,a,b,'quarter') for v,a,b in [
        (10,'2025-10-01','2025-12-31'),(20,'2026-01-01','2026-03-31'),
        (30,'2026-04-01','2026-06-30'),(40,'2026-07-01','2026-09-30')]]]
    result=build_financial_view(facts,NOW)
    assert result['annual'][0]['metrics']['revenue']['value']==400
    assert result['ttm']['revenue']['value']==100


def test_yahoo_raw_and_pretty_labels_both_map_to_original_metric():
    from data_provider.offshore_research import normalize_yahoo_statements
    import pandas as pd
    rows=normalize_yahoo_statements('us:AAPL',pd.DataFrame({'2026-09-30':{'TotalRevenue':120.,'NetIncome':30.}}),'income','annual','USD',NOW)
    assert {r['metric'] for r in rows}=={'revenue','net_profit'}
    assert next(r for r in rows if r['metric']=='revenue')['raw_field']=='TotalRevenue'


def test_sec_tag_mapping_does_not_invent_missing_claims():
    from data_provider.sec_filings import normalize_sec_facts
    payload={'cik':320193,'facts':{'us-gaap':{'Revenues':{'units':{'USD':[
        dict(start='2025-10-01',end='2026-09-30',val=120,form='10-K',filed='2026-10-30',accn='0000320193-26-000001',fy=2026,fp='FY')]}}},'custom':{'Debt':{'units':{'USD':[dict(val=99)]}}}}}
    facts=normalize_sec_facts('us:AAPL',payload,NOW)
    assert any(f['metric']=='revenue' and f['unit']=='USD' for f in facts)
    assert not any(f['metric']=='long_debt' for f in facts)
    assert all(f['published_at'] and f['url'].startswith('https://www.sec.gov/') for f in facts)


def test_fx_binding_is_directional_dated_and_adr_aware():
    from src.services.market_workspace_financials import listing_binding
    raw=dict(instrument_id='hk:00700',market='hk',currency='HKD',financial_currency='CNY',asset_type='stock')
    capital=dict(underlying_per_listed=1.,effective_date='2026-10-01',verified_through='2026-11-13',sources=['filing'],confirmed=True)
    fx=dict(from_currency='CNY',to_currency='HKD',rate=1.08,date='2026-11-13',source='yfinance',pair='CNYHKD=X')
    assert listing_binding(raw,'2026-11-13','CNY',fx,capital)['ready']
    assert not listing_binding(raw,'2026-11-13','CNY',fx|dict(date='2026-11-16'),capital)['ready']
    assert not listing_binding(raw,'2026-11-13','CNY',fx|dict(rate=-1),capital)['ready']
    assert not listing_binding(raw,'2026-11-13','CNY',fx|dict(from_currency='HKD',to_currency='CNY'),capital)['ready']
    assert not listing_binding(raw,'2026-11-13','CNY',fx,None)['ready']


def test_sec_without_access_identity_returns_explicit_configuration_gap():
    from data_provider.sec_filings import SecFilings
    with pytest.raises(ValueError,match='SEC_USER_AGENT'):
        SecFilings('').company('AAPL',NOW)


def test_sec_mixed_periods_keep_each_interval_basis():
    from data_provider.sec_filings import normalize_sec_facts
    rows=[dict(start='2025-10-01',end='2026-09-30',val=120,form='10-K',filed='2026-10-30',accn='a'),
          dict(start='2025-10-01',end='2025-12-31',val=20,form='10-Q',filed='2026-01-30',accn='b')]
    result=normalize_sec_facts('us:AAPL',{'cik':1,'facts':{'us-gaap':{'Revenues':{'units':{'USD':rows}}}}},NOW)
    assert {r['report_period']:r['period_basis'] for r in result}=={'2026-09-30':'annual','2025-12-31':'quarter'}


def test_fx_inverse_is_tried_after_direct_pair_failure(monkeypatch):
    import pandas as pd
    import yfinance as yf
    from src.services.market_workspace_financials import fetch_fx
    class Ticker:
        def __init__(self,symbol):self.symbol=symbol
        def history(self,**kwargs):
            if self.symbol=='CNYHKD=X':raise RuntimeError('provider timeout')
            return pd.DataFrame({'Close':[.9]},index=pd.to_datetime(['2026-11-13']))
    monkeypatch.setattr(yf,'Ticker',Ticker)
    result=fetch_fx('CNY','HKD','2026-11-13')
    assert result['inverted'] and result['rate']==pytest.approx(1/.9)


def test_53_week_fiscal_ytd_aligns_intervals_instead_of_month_day():
    rows=[fact('revenue',100,'2023-10-01','2024-09-28'),
        fact('revenue',40,'2023-10-01','2024-03-30','ytd'),
        fact('revenue',50,'2024-09-29','2025-03-29','ytd')]
    result=build_financial_view(rows,NOW)
    assert result['ttm']['revenue']['value']==110
    assert len(result['ttm']['revenue']['fact_ids'])==3


def test_vendor_dividend_candidates_do_not_claim_verified_payment_currency():
    import pandas as pd
    from data_provider.offshore_research import normalize_yahoo_dividends
    rows=normalize_yahoo_dividends('hk:00700',pd.Series([3.4],index=pd.to_datetime(['2026-06-01'])),'HKD',NOW)
    assert rows[0]['cash_per_share']==3.4 and rows[0]['currency']=='HKD'
    assert rows[0]['status']=='vendor_observed' and not rows[0]['payment_currency_verified']
    assert rows[0]['published_at'] is None


def test_later_cover_page_share_count_does_not_erase_financial_period():
    revenue=fact('revenue',120,'2025-09-28','2026-09-26')
    shares=fact('shares',10,'2026-10-16','2026-10-16','instant')|dict(unit='shares',attribution='parent_common')
    view=build_financial_view([revenue,shares],NOW)
    assert view['latest_period']=='2026-09-26'
    assert view['ttm']['revenue']['value']==120


def test_fiscal_and_quarter_ttm_monitoring_reuses_same_normalization():
    from src.services.a_share_value_monitoring import _actual
    rows=[fact('revenue',v,a,b,'quarter') for v,a,b in [
        (10,'2025-10-01','2025-12-31'),(20,'2026-01-01','2026-03-31'),
        (30,'2026-04-01','2026-06-30'),(40,'2026-07-01','2026-09-30')]]
    view=build_financial_view(rows,NOW)
    assert _actual({'financial_view':view},'revenue','2026-09-30')[0]==100
    view=build_financial_view([fact('revenue',120,'2024-09-29','2025-09-27')],NOW)
    assert _actual({'financial_view':view},'revenue','2025-09-27')[0]==120
    view['latest_period']='2026-09-26'
    assert _actual({'financial_view':view},'revenue','2025-09-27')[0]==120
