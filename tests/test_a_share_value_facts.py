import pytest
from data_provider.a_share_value_facts import normalize_value_statements
from src.schemas.a_share_value import ValueFact

NOW = '2026-10-30T12:00:00+08:00'


def row(**kwargs):
    return dict(SECUCODE='000807.SZ', REPORT_DATE='2025-12-31', NOTICE_DATE='2026-03-30', **kwargs)


def test_cash_zero_and_missing_are_distinct():
    facts = normalize_value_statements('000807', [row(MONETARYFUNDS=0, TOTAL_ASSETS=None)],
                                       'eastmoney/stock_balance_sheet_by_report_em', NOW)
    assert [(f['metric'], f['value'], f['unit']) for f in facts] == [('cash', 0, 'CNY')]
    assert facts[0]['period_basis'] == 'instant'
    assert facts[0]['scope'] == 'consolidated'
    assert facts[0]['available_at'] == NOW


def test_value_inputs_preserve_reported_interest_leases_and_depreciation_components():
    rows=[('eastmoney/stock_profit_sheet_by_report_em',row(FE_INTEREST_EXPENSE=68,FE_INTEREST_INCOME=278),{'interest_expense':68,'interest_income':278}),
        ('eastmoney/stock_balance_sheet_by_report_em',row(LEASE_LIAB=383,FIXED_ASSET=6738,CIP=870,USERIGHT_ASSET=364,LONG_LOAN=None),{'lease_liabilities':383,'fixed_assets':6738,'construction_in_progress':870,'right_of_use_assets':364}),
        ('eastmoney/stock_cash_flow_sheet_by_report_em',row(FA_IR_DEPR=426,OILGAS_BIOLOGY_DEPR=426,IA_AMORTIZE=23,LPE_AMORTIZE=17,USERIGHT_ASSET_AMORTIZE=28),{'depreciation':426,'intangible_amortization':23,'prepaid_amortization':17,'right_of_use_depreciation':28})]
    for source,data,expected in rows:
        facts=normalize_value_statements('000807',[data],source,NOW)
        assert {f['metric']:f['value'] for f in facts}==expected
        assert all(f['unit']=='CNY' for f in facts)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, 'bad'])
def test_invalid_amounts_do_not_become_facts(value):
    assert not normalize_value_statements('000807', [row(MONETARYFUNDS=value)],
                                         'eastmoney/stock_balance_sheet_by_report_em', NOW)


def test_code_and_vintage_are_checked():
    with pytest.raises(ValueError):
        normalize_value_statements('600519', [row(MONETARYFUNDS=10)],
                                   'eastmoney/stock_balance_sheet_by_report_em', NOW)
    fact = normalize_value_statements('000807', [row(MONETARYFUNDS=10, UPDATE_DATE='2026-11-01')],
                                      'eastmoney/stock_balance_sheet_by_report_em', NOW)[0]
    assert fact['available_at'].startswith('2026-11-01')
    assert fact['vintage_quality'] == 'latest_reconstructed'


def test_tushare_cumulative_profit_is_not_parent_statement():
    f = normalize_value_statements('000807', [dict(ts_code='000807.SZ', end_date='20260930',
        ann_date='20261028', report_type='1', n_income_attr_p=12)], 'tushare/income', NOW)[0]
    assert f['metric'] == 'net_profit'
    assert f['period_basis'] == 'ytd'
    assert f['attribution'] == 'parent_common'
    assert f['value'] == 12


def test_parent_statement_and_unknown_endpoint_cannot_claim_consolidation():
    f = normalize_value_statements('000807', [dict(end_date='20261231', ann_date='20261028',
        report_type='6', n_income_attr_p=12)], 'tushare/income', NOW)[0]
    assert f['scope'] == 'parent'
    assert not normalize_value_statements('000807', [row(MONETARYFUNDS=10)], 'untrusted/api', NOW)


def test_fact_schema_rejects_bool_and_extra_fields():
    f = normalize_value_statements('000807', [row(MONETARYFUNDS=10)],
                                  'eastmoney/stock_balance_sheet_by_report_em', NOW)[0]
    with pytest.raises(ValueError):
        ValueFact.model_validate(f | dict(value=True))
    with pytest.raises(ValueError):
        ValueFact.model_validate(f | dict(api_key='not-a-real-key'))


def test_current_capital_uses_total_shares_not_float_or_registered_capital():
    from data_provider.a_share_value_facts import normalize_current_capital
    rows = [dict(item='股票代码', value='000807'), dict(item='总股本', value=100000000), dict(item='流通股', value=70000000)]
    f = normalize_current_capital('000807', rows, NOW)[0]
    assert f['metric'] == 'current_shares' and f['value'] == 100000000
    assert f['period_basis'] == 'instant'
    with pytest.raises(ValueError):
        normalize_current_capital('600519', rows, NOW)


def test_paid_capital_uses_daily_basic_units_and_honors_no_free_fallback():
    from data_provider.a_share_fundamentals import ResearchSources
    from src.schemas.a_share import AssistantSettings
    calls=[]
    class Provider:
        def call(self,name,params=None,tushare=False):
            calls.append((name,tushare))
            return [dict(ts_code='000807.SZ',trade_date='20261029',total_share=42.5,float_share=40)]
    result=ResearchSources(Provider(),AssistantSettings(mode='tushare2000',free_fallback=False)).capital('000807',NOW)
    assert calls==[('daily_basic',True)]
    assert result['facts'][0]['value']==425000
    assert result['facts'][0]['period_end']=='2026-10-29'


def test_valuation_capital_keeps_total_shares_and_actual_valuation_date():
    from data_provider.a_share_value_facts import normalize_valuation_capital
    rows=[{'SECURITY_CODE':'605499','数据日期':'2026-10-30','总股本':734199310,'流通股本':676016900},
          {'SECURITY_CODE':'605499','数据日期':'2026-10-29','总股本':734199310}]
    f=normalize_valuation_capital('605499',rows,'eastmoney/stock_value_em','2026-10-31T14:43:00+08:00')[0]
    assert f['value']==734199310 and f['unit']=='shares'
    assert f['report_period']=='2026-10-30'
    assert f['metric']=='current_shares'
    assert f['source']=='eastmoney/stock_value_em'
    assert f['available_at'].startswith('2026-10-31')
    with pytest.raises(ValueError):
        normalize_valuation_capital('600519',rows,'eastmoney/stock_value_em','2026-10-31T14:43:00+08:00')
    assert normalize_valuation_capital('605499',[{'数据日期':'2026-10-30','总股本':None},rows[1]],'eastmoney/stock_value_em','2026-10-31T14:43:00+08:00')==[]


def test_free_valuation_preserves_capital_for_same_download_fallback():
    from data_provider.a_share_fundamentals import ResearchSources
    from src.schemas.a_share import AssistantSettings
    class Public:
        def call(self,name,params=None,**kwargs):
            assert name=='stock_value_em' and params['symbol']=='605499'
            return [{'数据日期':'2026-10-30','总股本':734199310,'当日收盘价':108,'PE(TTM)':20,'市净率':3}]
    result=ResearchSources(Public(),AssistantSettings(mode='free')).valuation('605499','2026-10-31T14:43:00+08:00')
    assert result['value_facts'][0]['value']==734199310
    assert result['value_facts'][0]['metric']=='current_shares'
