from src.services.a_share_value_context import normalized_history, own_valuation_history, cycle_review_status


def test_normalization_scales_margins_preserving_loss_year_and_break_gap():
    rows=[]
    for year,revenue,profit in [(2020,100,10),(2021,200,20),(2022,300,-30),(2023,400,40),(2024,500,50)]:
        rows.append(dict(period=f'{year}-12-31',metrics={k:dict(value=v,unit='CNY',vendor='vendor',scope='consolidated',fact_ids=[str(year)+k]) for k,v in [('revenue',revenue),('net_profit',profit)]}))
    result=normalized_history(rows,1000)['net_profit']
    assert abs(result['scaled_amount']-60)<1e-10
    assert result['coverage_sufficient'] and result['years']==5
    assert not normalized_history(rows[:2]+rows[3:],1000)['net_profit']['coverage_sufficient']


def test_own_history_is_five_year_and_does_not_roll_back_to_positive_pe():
    rows=[dict(trade_date='2020-10-01',pe_ttm=100,pb=2),dict(trade_date='2021-10-30',pe_ttm=10,pb=1),
          dict(trade_date='2026-10-30',pe_ttm=-2,pb=2),dict(trade_date='2026-10-31',pe_ttm=20,pb=2)]
    view=own_valuation_history(rows,'2026-10-30',['2020-01-01','2021-10-30','2026-10-30'])
    assert view['actual_start']=='2021-10-30'
    assert view['observations']==2 and view['metrics']['pe_ttm']['percentile'] is None
    assert view['metrics']['pb']['percentile']==1
    assert view['coverage']==1


def test_cycle_explicit_sourced_structural_review_requires_observed_annual_periods():
    annual=[dict(period=f'{y}-12-31',metrics=dict(revenue={},net_profit={})) for y in range(2021,2026)]
    s=dict(economic_model={'model':'cyclical'},financial_view={'annual':annual},evidence=[{'id':'SOURCE'}])
    r=dict(status='reviewed',method='revenue_scaled_margins',periods=[a['period'] for a in annual],
        structural_change='adjusted',sources=['SOURCE'],rationale='分段核对并购与产能，逐年利润率及预测投资依据')
    assert cycle_review_status(s,{'cycle_review':r})['ready']
    assert not cycle_review_status(s,{'cycle_review':r | dict(periods=['1999-12-31']*5)})['ready']
