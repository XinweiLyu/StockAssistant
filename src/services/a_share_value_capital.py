"""Explicit DDM share/cash scenarios; repurchases are never investor dividends."""
from decimal import Decimal


def project_dividend_capital(case, required):
    b=case['capital_bridge']
    if not isinstance(b,dict): raise ValueError('股本桥接须为完整对象')
    if (b.get('basis') not in ('model_proposal','user_assumption','reference_sensitivity') or not isinstance(b.get('sources'),list)
        or not b['sources'] or not all(isinstance(x,str) and x for x in b['sources'])
        or not b.get('rationale') or b.get('timing')!='actions_before_dividend'
        or b.get('terminal_capital_stable') is not True):
        raise ValueError('股利资本桥接须注明假设、来源、先资本变动后分红时序及稳定期资本不变')
    issued=required(case,'shares',1e-12)
    treasury=required(b,'initial_treasury_shares',0)
    initial=issued-treasury
    if initial<=0: raise ValueError('初始参与分红普通股须为正，库存股不能参与分红')
    cash=Decimal(str(required(b,'opening_available_cash',0)))
    minimum=Decimal(str(required(b,'minimum_cash',0)))
    years=b.get('years',[])
    if not isinstance(years,list) or len(years)!=5 or not all(isinstance(y,dict) for y in years) or len(case.get('dividends',[]))!=5:
        raise ValueError('股利资本桥接须有5年完整股数、现金及盈利路径')
    rows,flows=[],[]
    for index,y in enumerate(years):
        new=required(y,'new_shares',0);proceeds=required(y,'issuance_cash',0)
        bought=required(y,'repurchased_shares',0);cost=required(y,'repurchase_cash',0)
        cancelled=required(y,'cancelled_shares',0)
        reissued=required(y,'treasury_reissued_shares',0);reissue_cash=required(y,'treasury_reissue_cash',0)
        if (bought>0)!=(cost>0) or (new==0 and proceeds>0) or (reissued==0 and reissue_cash>0):
            raise ValueError('回购或发行现金须与对应股数一致，不能凭空增加现金')
        if cancelled+reissued>treasury+bought:
            raise ValueError('注销与再发行股数超过可用库存股')
        issued=required({'value':issued+new-cancelled},'value',1e-12)
        treasury=required({'value':treasury+bought-cancelled-reissued},'value',0)
        entitled=issued-treasury
        if issued<=0 or entitled<=0: raise ValueError('资本变动后普通股及分红股数须为正')
        dividend=required({'value':case['dividends'][index]},'value',0)
        earnings=required(y,'earnings',0)
        if dividend>earnings: raise ValueError('本模型的分红不得超过当年普通股盈利；动用留存收益需另行桥接')
        incoming=[required(y,'operating_cashflow'),required(y,'net_debt_financing'),proceeds,reissue_cash]
        outgoing=[required(y,'capex',0),cost,dividend,required(y,'financing_cash_costs',0),required(y,'minority_distributions',0)]
        cash+=sum((Decimal(str(v)) for v in incoming),Decimal(0))-sum((Decimal(str(v)) for v in outgoing),Decimal(0))
        required({'value':float(cash)},'value')
        if cash<minimum: raise ValueError('分红及回购后的可用现金不足最低经营现金约束')
        # Equivalent claims of the initial outside shares, rather than future
        # aggregate distributions divided by an unchanged issued share count.
        flows.append(dividend/entitled*initial)
        rows.append(dict(year=index+1,issued_shares=issued,treasury_shares=treasury,
            dividend_shares=entitled,dividend_per_share=dividend/entitled,ending_cash=float(cash)))
    terminal=required(case,'terminal_dividend',0)
    terminal_cash=Decimal(str(required(b,'terminal_operating_cashflow')))-sum((Decimal(str(required(b,k,0)))
        for k in ('terminal_capex','terminal_financing_cash_costs','terminal_minority_distributions')),Decimal(0))
    if Decimal(str(terminal))>Decimal(str(required(b,'terminal_earnings',0))) or Decimal(str(terminal))>terminal_cash:
        raise ValueError('稳定期分红超过盈利或扣除再投资后的经营现金')
    return dict(flows=flows,terminal_flow=terminal/rows[-1]['dividend_shares']*initial,
        initial_dividend_shares=initial,years=rows,basis=b['basis'],sources=b['sources'],
        limitation='资本与经营路径均为待核对假设；先发生资本行动再分红，稳定期不再融资或回购')
