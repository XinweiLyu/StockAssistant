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
