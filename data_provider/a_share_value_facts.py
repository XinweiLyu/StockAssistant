"""Source-specific statement contracts. No implicit yuan/10k-yuan inference."""
from math import isfinite
from src.schemas.a_share_integrated import digest, stamp
from src.schemas.a_share_value import ValueFact

# These statement endpoints return yuan, NOT the ten-thousand-share daily_basic units.
INCOME = {
    'revenue': ('TOTAL_OPERATE_INCOME', 'total_revenue'),
    'operating_profit': ('OPERATE_PROFIT', 'operate_profit'),
    'net_profit': ('PARENT_NETPROFIT', 'n_income_attr_p'),
    'total_profit': ('TOTAL_PROFIT', 'total_profit'),
    'income_tax': ('INCOME_TAX', 'income_tax'),
    'rd_expense': ('RESEARCH_EXPENSE', 'rd_exp'),
    'interest_expense': ('FE_INTEREST_EXPENSE', None),
    'interest_income': ('FE_INTEREST_INCOME', None),
    'finance_expense': ('FINANCE_EXPENSE', None),
    'total_net_profit': ('NETPROFIT', 'n_income'),
    'adjusted_net_profit': ('DEDUCT_PARENT_NETPROFIT', None),
    'operating_cost': ('OPERATE_COST', None),
    'selling_expense': ('SALE_EXPENSE', None),
    'management_expense': ('MANAGE_EXPENSE', None),
    'investment_income': ('INVEST_INCOME', None),
    'fair_value_income': ('FAIRVALUE_CHANGE_INCOME', None),
    'asset_disposal_income': ('ASSET_DISPOSAL_INCOME', None),
    'other_income': ('OTHER_INCOME', None),
}
BALANCE = {
    'cash': ('MONETARYFUNDS', 'money_cap'), 'assets': ('TOTAL_ASSETS', 'total_assets'),
    'liabilities': ('TOTAL_LIABILITIES', 'total_liab'),
    'parent_equity': ('TOTAL_PARENT_EQUITY', 'total_hldr_eqy_exc_min_int'),
    'minority_equity': ('MINORITY_EQUITY', 'minority_int'),
    'short_debt': ('SHORT_LOAN', 'st_borr'), 'long_debt': ('LONG_LOAN', 'lt_borr'),
    'bonds': ('BOND_PAYABLE', 'bond_payable'), 'receivables': ('ACCOUNTS_RECE', 'accounts_receiv'),
    'inventory': ('INVENTORY', 'inventories'), 'payables': ('ACCOUNTS_PAYABLE', 'acct_payable'),
    'shares': ('TOTAL_SHARES', 'total_share'),
    'lease_liabilities': ('LEASE_LIAB', None),
    'fixed_assets': ('FIXED_ASSET', None),
    'construction_in_progress': ('CIP', None),
    'right_of_use_assets': ('USERIGHT_ASSET', None),
    'noncurrent_due_within_year': ('NONCURRENT_LIAB_1YEAR', None),
    'trading_financial_assets': ('TRADE_FINASSET_NOTFVTPL', None),
    'treasury_share_cost': ('TREASURY_SHARES', None),
    'contract_liabilities': ('CONTRACT_LIAB', None),
    'goodwill': ('GOODWILL', None),
    'development_assets': ('DEVELOP_EXPENSE', None),
    'current_assets': ('TOTAL_CURRENT_ASSETS', None),
    'current_liabilities': ('TOTAL_CURRENT_LIAB', None),
}
CASHFLOW = {
    'operating_cashflow': ('NETCASH_OPERATE', 'n_cashflow_act'),
    'capex': ('CONSTRUCT_LONG_ASSET', 'c_pay_acq_const_fiolta'),
    'borrowing': ('RECEIVE_LOAN_CASH', 'c_recp_borrow'),
    'debt_repayment': ('REPAY_DEBT_CASH', 'c_prepay_amt_borr'),
    # FA_IR_DEPR and OILGAS_BIOLOGY_DEPR may duplicate the same reported
    # aggregate; retain one and keep other amortization components separate.
    'depreciation': ('FA_IR_DEPR', None),
    'intangible_amortization': ('IA_AMORTIZE', None),
    'prepaid_amortization': ('LPE_AMORTIZE', None),
    'right_of_use_depreciation': ('USERIGHT_ASSET_AMORTIZE', None),
    'dividend_profit_interest_paid': ('ASSIGN_DIVIDEND_PORFIT', None),
}
CONTRACTS = {
    'eastmoney/stock_profit_sheet_by_report_em': (INCOME, 0),
    'eastmoney/stock_balance_sheet_by_report_em': (BALANCE, 0),
    'eastmoney/stock_cash_flow_sheet_by_report_em': (CASHFLOW, 0),
    'tushare/income': (INCOME, 1), 'tushare/balancesheet': (BALANCE, 1),
    'tushare/cashflow': (CASHFLOW, 1),
}


def normalize_value_statements(code, rows, source, observed_at):
    contract = CONTRACTS.get(source)
    if not contract:
        return []
    mapping, index = contract
    observed = stamp(observed_at)
    facts = []
    for row in rows:
        actual = str(row.get('SECUCODE', row.get('SECURITY_CODE', row.get('ts_code', code))))[:6]
        if actual != code:
            raise ValueError('财务股票身份不一致')
        period = stamp(row.get('REPORT_DATE', row.get('end_date')))
        if not period:
            raise ValueError('缺少有效报告期')
        end = period[:10]
        published = stamp(row.get('NOTICE_DATE', row.get('f_ann_date') or row.get('ann_date')))
        revised = stamp(row.get('UPDATE_DATE'))
        report_type = str(row.get('report_type', ''))
        scope = ('parent' if report_type in ('6', '7', '8', '9', '10', '11', '12') else
                 'consolidated' if not index or report_type in ('1', '2', '3', '4', '5') else 'unknown')
        for metric, aliases in mapping.items():
            raw = aliases[index]
            value = row.get(raw)
            if value is None or isinstance(value, bool):
                continue
            try:
                value = float(str(value).replace(',', ''))
            except (ValueError, TypeError):
                continue
            if not isfinite(value):
                continue
            instant = mapping is BALANCE
            quarter = index and report_type in ('2', '3', '7', '8')
            basis = 'instant' if instant else 'quarter' if quarter else 'annual' if end.endswith('12-31') else 'ytd'
            payload = dict(code=code, metric=metric, value=value, unit='shares' if metric == 'shares' else 'CNY',
                report_period=end, period_end=end, period_start=None if instant else end[:4]+'-01-01' if not quarter else None,
                period_basis=basis, scope=scope,
                attribution='parent_common' if metric in ('net_profit', 'adjusted_net_profit', 'parent_equity', 'shares') else
                            'minority' if metric == 'minority_equity' else 'all_claims',
                source=source, raw_field=raw, published_at=published, revised_at=revised, observed_at=observed,
                available_at=max(filter(None, [observed, published, revised])),
                url='https://tushare.pro/document/2?doc_id=79' if index else 'https://data.eastmoney.com/bbsj/')
            content_hash = digest({k: v for k, v in payload.items() if k not in ('observed_at', 'available_at')})
            facts.append(ValueFact(**payload, content_hash=content_hash, fact_id='VF'+content_hash[:20]).model_dump())
    return facts


def normalize_current_capital(code, rows, observed_at):
    """Eastmoney f84 is issued TOTAL shares; f85/free float is never a substitute."""
    data = {str(r.get('item')): r.get('value') for r in rows}
    if str(data.get('股票代码', '')).zfill(6) != code:
        raise ValueError('当前股本的股票身份未核实')
    value = data.get('总股本')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        return []
    observed = stamp(observed_at)
    payload = dict(code=code, metric='current_shares', value=value, unit='shares',
        report_period=observed[:10], period_end=observed[:10], period_basis='instant',
        scope='consolidated', attribution='parent_common', source='eastmoney/stock_individual_info_em',
        raw_field='总股本/f84', observed_at=observed, available_at=observed,
        url='https://quote.eastmoney.com/'+('sh' if code.startswith('6') else 'sz')+code+'.html')
    content = digest(payload)
    return [ValueFact(**payload, content_hash=content, fact_id='VC'+content[:20]).model_dump()]


def normalize_daily_capital(code, rows, observed_at):
    """Tushare daily_basic documents total_share in 10k shares, unlike balance sheets."""
    observed = stamp(observed_at)
    candidates = []
    for row in rows:
        if str(row.get('ts_code', ''))[:6] != code:
            raise ValueError('股本证券不匹配')
        day = stamp(row.get('trade_date'))
        value = row.get('total_share')
        if (not day or day[:10] > observed[:10] or isinstance(value, bool) or
            not isinstance(value, (int, float)) or not isfinite(value) or value <= 0):
            continue
        candidates.append((day[:10], value))
    if not candidates:
        return []
    day, value = max(candidates)
    payload = dict(code=code, metric='current_shares', value=value*10000, unit='shares',
        report_period=day, period_end=day, period_basis='instant', scope='consolidated', attribution='parent_common',
        source='tushare/daily_basic', raw_field='total_share(万股)*10000', observed_at=observed,
        available_at=observed, url='https://tushare.pro/document/2?doc_id=32')
    content = digest(payload)
    return [ValueFact(**payload, content_hash=content, fact_id='VC'+content[:20]).model_dump()]


def normalize_valuation_capital(code, rows, source, observed_at):
    """Retain issued shares from the valuation download, dated to its actual session."""
    if source == 'tushare/daily_basic':
        return normalize_daily_capital(code, rows, observed_at)
    if source != 'eastmoney/stock_value_em':
        raise ValueError('估值股本来源尚未核实')
    observed = stamp(observed_at)
    dated = []
    for row in rows:
        # AKShare binds the request symbol and drops SECURITY_CODE from its frame.
        if str(row.get('SECURITY_CODE', code)).zfill(6) != code:
            raise ValueError('估值股本证券不匹配')
        day = stamp(row.get('数据日期'))
        if day and day[:10] <= observed[:10]:
            dated.append((day[:10], row.get('总股本')))
    if not dated:
        return []
    day = max(d for d, _ in dated)
    values = [v for d, v in dated if d == day]
    if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0 for v in values)
            or len(set(values)) != 1):
        return []
    payload = dict(code=code, metric='current_shares', value=values[0], unit='shares',
        report_period=day, period_end=day, period_basis='instant', scope='consolidated', attribution='parent_common',
        source=source, raw_field='总股本/TOTAL_SHARES', observed_at=observed, available_at=observed,
        url='https://data.eastmoney.com/gzfx/detail/'+code+'.html')
    content = digest(payload)
    return [ValueFact(**payload, content_hash=content, fact_id='VC'+content[:20]).model_dump()]


def normalize_distributions(code, rows, source, observed_at):
    """Retain announced actions, never confuse ex-date with cash payment date."""
    import re
    if source not in ('eastmoney/stock_fhps_detail_em','tushare/dividend'):
        return []
    paid=source=='tushare/dividend'
    observed=stamp(observed_at)
    def numeric(value):
        if isinstance(value,bool):
            return None
        try:
            value=float(value)
            return value if isfinite(value) and value>=0 else None
        except (TypeError,ValueError):
            return None
    output={}
    for row in rows:
        if str(row.get('ts_code',code))[:6] != code:
            raise ValueError('分红证券身份不一致')
        period=stamp(row.get('end_date') if paid else row.get('报告期'))
        published=stamp(row.get('imp_ann_date') or row.get('ann_date') if paid else row.get('最新公告日期'))
        if not period or not published or published>observed:
            continue
        description=str(row.get('现金分红-现金分红比例描述') or '')
        cash=numeric(row.get('cash_div_tax')) if paid else None
        if not paid:
            # Use an explicit contract in the text instead of guessing ratio units.
            match=re.search(r'(\d+(?:\.\d+)?)\s*(?:股)?\s*(?:(?:送|转(?:增)?)\s*\d+(?:\.\d+)?\s*(?:股)?\s*)*派\s*(\d+(?:\.\d+)?)',description)
            if match and float(match[1])>0 and '含税' in description:
                cash=float(match[2])/float(match[1])
        stage=str(row.get('div_proc') if paid else row.get('方案进度'))
        ex=stamp(row.get('ex_date') if paid else row.get('除权除息日'))
        payment=stamp(row.get('pay_date')) if paid else None
        item=dict(code=code,report_period=period[:10],source=source,published_at=published,available_at=observed,
            status='implemented' if stage in ('实施','实施分配') else 'proposed',raw_stage=stage,
            cash_per_share=cash,tax_basis='gross' if cash is not None else 'unknown',
            stock_per_share=numeric(row.get('stk_div')) if paid else None,
            ex_date=ex[:10] if ex else None,payment_date=payment[:10] if payment else None,
            description=description,vintage_quality='latest_reconstructed',
            url='https://tushare.pro/document/2?doc_id=103' if paid else 'https://data.eastmoney.com/yjfp/detail/'+code+'.html',
            limitation='预案不等于实施；除息日不等于到账日；不以当前股数推算历史分红总额或自动预测未来分红')
        identity=digest({k:v for k,v in item.items() if k!='available_at'})
        item['id']='VD'+identity[:20]
        output[item['id']]=item
    return sorted(output.values(),key=lambda r:r['report_period'])
