"""Calendar-month holding scenarios on the SAME dated cashflow schedule as V0."""
from calendar import monthrange
from datetime import date
from src.services.a_share_value_valuation import number, required


def add_months(start, months):
    day = date.fromisoformat(start[:10])
    index = day.year*12+day.month-1+months
    year, month = divmod(index, 12)
    return date(year, month+1, min(day.day, monthrange(year, month+1)[1])).isoformat()


def cashflow_schedule(case, start_date):
    start = date.fromisoformat(start_date[:10])
    dates = case.get('payment_dates') or [add_months(start.isoformat(), i*12) for i in range(1, 6)]
    if len(dates) != 5 or dates != sorted(set(dates)) or dates[0] <= start.isoformat():
        raise ValueError('现金流日期须为5个递增且晚于估值日的日期')
    amounts = case.get('dividends') or [0]*5
    return [dict(date=d, time=(date.fromisoformat(d)-start).days/365.25, amount=number(amounts[i], '现金流')) for i, d in enumerate(dates)]


def evaluate_holding(case, valuation, start_date, months):
    result = dict(months=months, method=case.get('method'), scenario=case.get('scenario', 'base'), state='insufficient', reason='', price=None, intrinsic_value=None,
                  dividends=None, gross_return=None, net_return=None)
    if months not in (6, 12, 24, 36):
        return result | dict(state='blocked', reason='持有期仅支持6/12/24/36个自然月')
    if case.get('method') != 'ddm':
        return result | dict(reason='该方法需未来分配、留存现金、非经营资产与负债滚动勾稽；先展示当下价值与持有期核查节点')
    try:
        if valuation.get('state') != 'ready':
            raise ValueError('当下估值尚未通过数学与适用性检查')
        k = required(case, 'realization_factor', 0, 5)
        initial = required(case, 'price', 1e-12)
        r, shares = required(case, 'discount', .0001, 1), required(valuation if valuation.get('capital_bridge') else case, 'shares', 1e-12)
        end = add_months(start_date, months)
        t = (date.fromisoformat(end)-date.fromisoformat(start_date[:10])).days/365.25
        schedule = cashflow_schedule(case, start_date)
        if valuation.get('capital_bridge'):
            if len(valuation.get('flows',[]))!=5: raise ValueError('股本桥接后的分红排程缺失')
            schedule=[v|dict(amount=valuation['flows'][i]) for i,v in enumerate(schedule)]
        future = sum(v['amount']/(1+r)**(v['time']-t) for v in schedule if v['date'] > end)
        future += valuation['terminal_value']/(1+r)**(schedule[-1]['time']-t)
        intrinsic = future/shares
        dividends = sum(v['amount'] for v in schedule if v['date'] <= end)/shares
        price = intrinsic*k
        gross = (price+dividends-initial)/initial
        costs = case.get('costs_per_share')
        net = (price+dividends-initial-number(costs, '税费及全部费用', 0))/initial if costs is not None else None
        return result | dict(state='ready', end_date=end, year_fraction=t, price=price, intrinsic_value=intrinsic,
            realization_factor=k, dividends=dividends, gross_return=gross, net_return=net,
            annualized_gross=(1+gross)**(1/t)-1 if gross > -1 else -1,
            reason='兑现因子为P/V；非概率，未填写税费时仅展示毛收益')
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return result | dict(reason=str(exc) if isinstance(exc, ValueError) else '持有期输入不完整')
