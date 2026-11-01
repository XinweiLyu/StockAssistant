import pytest
from src.services.a_share_value_economics import build_economic_analysis


def fv(value,period='2026-09-30',attribution='all_claims'):
    return dict(value=value,period=period,unit='CNY',vendor='eastmoney',scope='consolidated',
        attribution=attribution,fact_ids=[str(value)+period],period_basis='annual' if period.endswith('12-31') else 'ytd',
        formula='reported' if period.endswith('12-31') else 'YTD+previous_annual-previous_YTD')


def view():
    return dict(latest_period='2026-09-30',latest={'parent_equity':fv(120,attribution='parent_common')},
        ttm={'revenue':fv(100),'operating_profit':fv(20),'net_profit':fv(10,attribution='parent_common'),
             'total_net_profit':fv(12),'operating_cashflow':fv(24),'capex':fv(8)},
        periods=[dict(period='2025-09-30',metrics={'parent_equity':fv(80,'2025-09-30','parent_common')})],annual=[])


def test_cash_quality_uses_consolidated_profit_and_roe_average_equity():
    result=build_economic_analysis(view(),'operating')['metrics']
    assert result['cash_conversion']['value']==2
    assert result['roe']['value']==pytest.approx(.1)
    assert result['operating_margin']['value']==.2
    assert result['cash_surplus_proxy']['value']==16
    assert result['cash_conversion']['fact_ids']
    assert '归母' not in result['cash_conversion']['formula']


def test_unknown_profit_and_nonmatching_sources_are_not_replaced_with_zero_or_parent_profit():
    v=view();del v['ttm']['total_net_profit']
    result=build_economic_analysis(v,'operating')['metrics']
    assert result['cash_conversion']['value'] is None
    assert result['cash_conversion']['reason']
    v['ttm']['operating_profit']['vendor']='other'
    assert build_economic_analysis(v,'operating')['metrics']['operating_margin']['value'] is None


def test_parent_profit_mislabeled_as_consolidated_cannot_create_a_cash_conversion_ratio():
    v=view();v['ttm']['total_net_profit']['attribution']='parent_common'
    assert build_economic_analysis(v,'operating')['metrics']['cash_conversion']['value'] is None


def test_financial_company_does_not_receive_industrial_cash_conversion_or_roic():
    result=build_economic_analysis(view(),'bank')['metrics']
    assert result['roe']['value']==pytest.approx(.1)
    assert result['cash_conversion']['value'] is None
    assert '金融' in result['cash_conversion']['reason']
    assert result['roic_proxy']['value'] is None


def test_positive_accounting_profit_with_negative_cash_is_a_review_flag_not_a_probability():
    v=view();v['ttm']['operating_cashflow']=fv(-2)
    result=build_economic_analysis(v,'operating')
    assert any('现金流为负' in f['message'] for f in result['flags'])
    assert all('probability' not in f for f in result['flags'])


def test_quarterly_working_capital_flags_compare_matching_ytd_revenue_not_annual_or_ttm():
    v=view();v['latest'].update(receivables=fv(30),revenue=fv(90)|dict(period_basis='ytd'))
    v['periods'][0]['metrics'].update(receivables=fv(20,'2025-09-30'),revenue=fv(80,'2025-09-30')|dict(period_basis='ytd'))
    result=build_economic_analysis(v,'operating')
    assert any(f['code']=='receivables_growth' for f in result['flags'])
    v['periods'][0]['metrics']['revenue']['vendor']='other'
    assert not any(f['code']=='receivables_growth' for f in build_economic_analysis(v,'operating')['flags'])


def test_roic_proxy_requires_complete_normalized_operating_and_capital_bridge():
    v=view();v['ttm'].update(finance_expense=fv(1),investment_income=fv(2),fair_value_income=fv(0),
        asset_disposal_income=fv(0),other_income=fv(0),total_profit=fv(20),income_tax=fv(5))
    for group,p in [(v['latest'],'2026-09-30'),(v['periods'][0]['metrics'],'2025-09-30')]:
        group.update(minority_equity=fv(0,p,'minority'),short_debt=fv(10,p),long_debt=fv(0,p),bonds=fv(0,p),
            lease_liabilities=fv(0,p),noncurrent_due_within_year=fv(0,p),cash=fv(10,p))
    m=build_economic_analysis(v,'operating')['metrics']
    assert m['normalized_ebit_proxy']['value']==19
    assert m['roic_proxy']['value']==pytest.approx(.1425)
    assert m['roic_proxy']['limitation']
    del v['latest']['lease_liabilities']
    assert build_economic_analysis(v,'operating')['metrics']['roic_proxy']['value'] is None


def test_compound_proxy_does_not_mix_income_and_capital_vendors():
    v=view();v['ttm'].update(finance_expense=fv(1),investment_income=fv(2),fair_value_income=fv(0),
        asset_disposal_income=fv(0),other_income=fv(0),total_profit=fv(20),income_tax=fv(5))
    for group,p in [(v['latest'],'2026-09-30'),(v['periods'][0]['metrics'],'2025-09-30')]:
        group.update(minority_equity=fv(0,p,'minority'),short_debt=fv(10,p),long_debt=fv(0,p),bonds=fv(0,p),
            lease_liabilities=fv(0,p),noncurrent_due_within_year=fv(0,p),cash=fv(10,p))
        for f in group.values():f['vendor']='other'
    assert build_economic_analysis(v,'operating')['metrics']['roic_proxy']['value'] is None
