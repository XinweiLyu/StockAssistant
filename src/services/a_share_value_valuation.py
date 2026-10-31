"""Auditable valuation arithmetic. LLMs never supply authoritative totals."""
from copy import deepcopy
from datetime import datetime
from math import isfinite
from src.schemas.a_share_value import ValueAssumptions, ValueSnapshot, ValueReport


def number(value, name, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(name+'须为有限数值，缺失不能当0')
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(name+'超出允许范围')
    return float(value)


def required(data, key, low=None, high=None):
    return number(data.get(key), key, low, high)


def project_operating_case(case, financial_view):
    op = case.get('operating', {})
    revenue, nwc = required(op, 'revenue0', 0), required(op, 'nwc0')
    years = op.get('years', [])
    if len(years) != 5 or not isinstance(op.get('terminal'), dict):
        raise ValueError('须提供5年经营预测及独立稳定期投资桥接')
    rows = []
    for year in [*years, op['terminal']]:
        growth = required(year, 'growth', -.99, 5)
        revenue *= 1+growth
        ebit = revenue*required(year, 'ebit_margin', -2, 1)
        tax = required(year, 'tax', 0, 1)
        da = revenue*required(year, 'da_ratio', 0, 2)
        capex = revenue*required(year, 'capex_ratio', 0, 5)
        new_nwc = revenue*required(year, 'nwc_ratio', -2, 5)
        # A negative operating result does not automatically create a cash tax refund.
        nopat = ebit-max(ebit, 0)*tax
        fcff = nopat+da-capex-(new_nwc-nwc)
        row = dict(revenue=revenue, ebit=ebit, nopat=nopat, da=da, capex=capex,
                   nwc=new_nwc, delta_nwc=new_nwc-nwc, fcff=fcff)
        if case.get('method') == 'fcfe':
            row['fcfe'] = fcff-required(year, 'after_tax_interest', 0)+required(year, 'net_borrowing')-required(year, 'minority_cashflow', 0)
        nwc = new_nwc
        rows.append(row)
    field = 'fcfe' if case.get('method') == 'fcfe' else 'fcff'
    return dict(rows=rows[:5], flows=[r[field] for r in rows[:5]], terminal_flow=rows[5][field], terminal_row=rows[5])


def _times(case):
    if not case.get('start_date'):
        return [1., 2., 3., 4., 5.]
    from src.services.a_share_value_holding import cashflow_schedule
    return [v['time'] for v in cashflow_schedule(case, case['start_date'])]


def evaluate_method(method, case, financial_view, eligibility):
    result = dict(method=method, scenario=case.get('scenario', 'base'), state='blocked', missing=[])
    try:
        if eligibility.get('allowed_methods') is not None and method not in eligibility['allowed_methods']:
            raise ValueError('该经济模型不适用'+method+'；请先核实主营或选用适配方法')
        shares = required(case, 'shares', 1e-12)
        if case.get('fixed_capital') is not True or case.get('capital_changes'):
            raise ValueError('须核实固定普通股资本；融资增发/回购/重组需完整桥接')
        if method == 'nav':
            if case.get('complete') is not True:
                raise ValueError('NAV须确认重大资产、索取权、税费清单完整')
            assets, liabilities = case.get('assets', []), case.get('liabilities', [])
            if not assets or not isinstance(liabilities, list):
                raise ValueError('缺少不重叠资产/负债清单')
            ids = [v.get('id') for v in assets+liabilities]
            if any(not v for v in ids) or len(ids) != len(set(ids)):
                raise ValueError('NAV资产或负债标识重复/缺失，不能重复计价')
            value = sum(required(v, 'value', 0) for v in assets)-sum(required(v, 'value', 0) for v in liabilities)-required(case, 'costs', 0)
            return result | dict(state='ready', value_total=value, value_per_share=value/shares, terminal_share=0,
                                 bridge=dict(assets=assets, liabilities=liabilities, costs=case['costs']))
        r = required(case, 'discount', .0001, 1)
        times = _times(case)
        g = required(case, 'terminal_growth', -.99, .2) if method != 'rim' else 0
        if method != 'rim' and r-g < .01-1e-12:
            raise ValueError('折现率必须高于终值增长至少1个百分点')
        terminal, adjustment, rows = 0, 0, []
        if method in ('fcfe', 'fcff'):
            if abs(required(case.get('operating', {}).get('terminal', {}), 'growth')-g) > 1e-9:
                raise ValueError('稳定期营收增长须与终值增长一致')
            projected = project_operating_case(case | dict(method=method), financial_view)
            flows, rows = projected['flows'], projected['rows']
            terminal = projected['terminal_flow']/(r-g)
            nonop = case.get('nonoperating', {})
            if nonop.get('treatment') == 'separate':
                adjustment += required(nonop, 'value', 0)
                if nonop.get('cashflows'):
                    raise ValueError('非经营资产不能既加价值又计入释放现金流')
            elif nonop.get('treatment') == 'included_in_flows' and method == 'fcfe':
                releases = nonop.get('cashflows', [])
                if len(releases) != 5 or 'value' in nonop:
                    raise ValueError('非经营资产需唯一释放计划，不能另加价值')
                flows = [v+number(releases[i], 'nonoperating.cashflows') for i, v in enumerate(flows)]
            else:
                raise ValueError('须明确非经营资产是单独估值还是已计入现金流')
            if method == 'fcff':
                adjustment -= required(case, 'debt', 0)+required(case, 'senior_claims', 0)+required(case, 'minority_value', 0)
        elif method == 'ddm':
            flows = case.get('dividends', [])
            if len(flows) != 5 or case.get('capital_feasible') is not True:
                raise ValueError('DDM需5年股利及盈利/资本可持续依据')
            flows = [number(v, 'dividend', 0) for v in flows]
            terminal = required(case, 'terminal_dividend', 0)/(r-g)
        elif method == 'rim':
            book = required(case, 'book_equity', 1e-12)
            adjustment = book
            years = case.get('years', [])
            if len(years) != 5:
                raise ValueError('RIM需5年ROE/分配/OCI及资本约束计划')
            flows = []
            for year in years:
                earning = book*required(year, 'roe', -2, 2)
                dividend, oci = required(year, 'dividend', 0), required(year, 'oci')
                if abs(oci) > 1e-9:
                    raise ValueError('非零OCI需完整clean-surplus调节，首版不自动估值')
                flows.append(earning-r*book)
                book += earning-dividend
                if book <= 0:
                    raise ValueError('预测普通股权益耗尽，RIM正常持续经营前提不成立')
            omega = required(case, 'omega', 0, 1)
            terminal = flows[-1]*omega/(1+r-omega)
        else:
            raise ValueError('不支持的估值方法')
        pv_flows = sum(flow/(1+r)**t for flow, t in zip(flows, times))
        terminal_pv = terminal/(1+r)**times[-1]
        value = pv_flows+terminal_pv+adjustment
        number(value, 'valuation')
        return result | dict(state='ready', value_total=value, value_per_share=value/shares,
            operating_equity=pv_flows+terminal_pv, terminal_value=terminal, terminal_pv=terminal_pv,
            terminal_share=terminal_pv/value if value else None, flows=flows, times=times,
            rows=rows, adjustment=adjustment, discount=r, shares=shares)
    except (ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as exc:
        # Messages are our field validation only; no provider exception reaches this calculator.
        return result | dict(missing=[str(exc) if isinstance(exc, ValueError) else '估值字段结构不完整'])


def compare_price(conservative_value, quote, margin_required, eligibility):
    result = dict(margin=None, upside=None, conditional_price=None, price=quote.get('price'),
                  reference_value=conservative_value, denominator='保守价值', reason='资料或当前不复权价格不足')
    try:
        value = number(conservative_value, '保守价值', 1e-12)
        price = required(quote, 'price', 1e-12)
        if not quote.get('valid'):
            return result
        result.update(margin=(value-price)/value, upside=(value-price)/price, reason='')
        if margin_required is not None and eligibility.get('eligible'):
            result['conditional_price'] = value*(1-number(margin_required, '要求安全边际', 0, .8))
    except ValueError:
        pass
    return result


def evaluate_value(assumptions, snapshot):
    a = ValueAssumptions.model_validate(assumptions).model_dump()
    s = ValueSnapshot.model_validate(snapshot).model_dump()
    if a['snapshot_id'] != s['snapshot_id'] or a['code'] != s['code']:
        raise ValueError('估值假设与资料股票/版本不一致')
    eligibility = s['binding'].get('eligibility', {})
    allowed = s['economic_model'].get('allowed_methods')
    results = [evaluate_method(c.get('method'), c, s['financial_view'], dict(allowed_methods=allowed) if allowed is not None else {}) for c in a['cases']]
    primary = {r['scenario']: r for r in results if r['method'] == a['primary_method'] and r['state'] == 'ready'}
    missing = [m for r in results for m in r.get('missing', [])]
    complete = all(k in primary for k in ('conservative', 'base', 'upside'))
    state = 'draft' if not a['confirmed'] else 'review_required'
    if not complete:
        state = 'research_only'
        missing.append('主方法需保守/基准/有利三组可计算假设')
    elif not (primary['conservative']['value_per_share'] <= primary['base']['value_per_share'] <= primary['upside']['value_per_share']):
        state = 'disputed'
        missing.append('三情景价值次序不一致，请复核驱动与资本桥接')
    disputed = complete and any(r['method'] != a['primary_method'] and r['scenario'] == 'base' and r['state'] == 'ready'
        and abs(r['value_per_share']-primary['base']['value_per_share']) > abs(primary['base']['value_per_share'])*.3 for r in results)
    if disputed:
        state = 'disputed'
        missing.append('主方法与交叉方法差异超过30%，禁止机械平均')
    required_reviews = ('audit', 'debt', 'capital', 'reinvestment', 'nonoperating_assets')
    reviewed = all(a['risk_review'].get(k, {}).get('status') == 'reviewed' and a['risk_review'][k].get('sources') for k in required_reviews)
    ids = {f['fact_id'] for f in s['facts']} | {e['id'] for e in s['evidence'] if e.get('id')}
    refs_ok = all(c.get('evidence_ids') and set(c['evidence_ids']) <= ids for c in a['cases']) and all(
        set(a['risk_review'].get(k, {}).get('sources', [])) <= ids for k in required_reviews)
    capital = s['financial_view'].get('current_capital') or {}
    quote = s['binding'].get('quote', {})
    fresh_capital = capital.get('available_at', '')[:10] == s['cutoff'][:10] and capital.get('period', '') >= (quote.get('trade_date') or s['cutoff'][:10])
    shares_fact = capital.get('value') if fresh_capital else None
    capital_matches = shares_fact and all(c.get('shares') == shares_fact for c in a['cases'])
    if not reviewed:
        missing.append('审计、债务、资本、再投资或非经营资产风险尚未完成有来源的复核')
    from src.services.a_share_value_context import cycle_review_status
    cycle = cycle_review_status(s, a)
    missing += cycle['reasons']
    if not capital_matches:
        missing.append('缺少与报价日期一致的当前总股本，或三情景股数与核实资本不一致')
    if complete and state not in ('disputed', 'research_only') and a['confirmed'] and reviewed and refs_ok and capital_matches and cycle['ready'] and eligibility.get('eligible') and not s['financial_view'].get('conflicts'):
        state = 'conditional'
    value = primary.get('conservative', {}).get('value_per_share')
    comparison = compare_price(value, s['binding'].get('quote', {}), a['margin_required'], dict(eligible=state == 'conditional'))
    sensitivities = []
    base_case = next((c for c in a['cases'] if c.get('method') == a['primary_method'] and c.get('scenario') == 'conservative'), None)
    if base_case:
        for label, change in [('折现率上升2个百分点', 'discount'), ('无额外收益摊薄10%', 'dilution'), ('经营不利冲击', 'operating')]:
            case = deepcopy(base_case)
            if change == 'discount':
                case['discount'] = case.get('discount', .1)+.02
            elif change == 'dilution':
                case['shares'] = case.get('shares', 1)*1.1
            elif case.get('operating'):
                for y in [*case['operating']['years'], case['operating']['terminal']]:
                    y['ebit_margin'] -= .02
                    y['capex_ratio'] += .02
            elif case.get('method') == 'rim':
                for y in case['years']:
                    y['roe'] -= .02
            elif case.get('method') == 'ddm':
                case['dividends'] = [d*.8 for d in case['dividends']]
                case['terminal_dividend'] *= .8
            elif case.get('method') == 'nav':
                for asset in case['assets']:
                    asset['value'] *= .8
            stress = evaluate_method(case.get('method'), case, s['financial_view'], {})
            sensitivities.append(dict(label=label, value=stress.get('value_per_share'), missing=stress.get('missing', []), note='显式机械压力，不是概率'))
    return ValueReport(code=a['code'], snapshot_id=s['snapshot_id'], assumptions_revision=a['revision'],
        generated_at=s['cutoff'], valuation_state=state, primary_method=a['primary_method'], valuation_cases=results,
        comparison=comparison, quality=s['financial_view'].get('quality', {}), peers=s['peers'], theses=a['theses'],
        risks=s['economic_model'].get('checklist', []), missing=list(dict.fromkeys(s['missing']+missing)),
        sensitivities=sensitivities).model_dump()
