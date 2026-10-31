"""Free-first financial and news adapters with explicit availability and gaps."""
from __future__ import annotations

import re
from math import isfinite
from datetime import date, timedelta
from urllib.parse import urlsplit
from src.schemas.a_share_integrated import ResearchFact, digest, stamp
from data_provider.a_share_disclosures import normalize_disclosures

# Values are yuan/per-share yuan or ratios, never assumed to be complete reports.
FIELDS = {
    'revenue': ('TOTALOPERATEREVE', 'TOTAL_OPERATE_INCOME', 'total_revenue', 'revenue'),
    'net_profit': ('PARENTNETPROFIT', 'PARENT_NETPROFIT', 'n_income_attr_p'),
    'deducted_profit': ('KCFJCXSYJLR', 'DEDUCT_PARENT_NETPROFIT', 'profit_dedt'),
    'revenue_yoy': ('TOTALOPERATEREVETZ', 'or_yoy'),
    'profit_yoy': ('PARENTNETPROFITTZ', 'netprofit_yoy'),
    'operating_cashflow': ('NETCASH_OPERATE', 'n_cashflow_act'),
    'cashflow_per_share': ('MGJYXJJE', 'ocfps'),
    'roe': ('ROEJQ', 'roe'), 'gross_margin': ('XSMLL', 'grossprofit_margin'),
    'debt_ratio': ('ZCFZL', 'debt_to_assets'),
    'eps': ('EPSJB', 'BASIC_EPS', 'eps'), 'bps': ('BPS', 'bps'),
    'assets': ('TOTAL_ASSETS', 'total_assets'), 'liabilities': ('TOTAL_LIABILITIES', 'total_liab'),
}
RATIOS = {'revenue_yoy', 'profit_yoy', 'roe', 'gross_margin', 'debt_ratio'}


def financial_coverage(facts):
    """Latest-period field coverage; never fill missing quarters from older reports."""
    financial = [f for f in facts if f.get('category') == 'financial']
    period = max((f.get('report_period') or '' for f in financial), default='')
    fields = {}
    for field in (*FIELDS, 'pe_ttm', 'pb', 'pe_percentile'):
        candidates = [f for f in financial if numeric(f.get('values', {}).get(field)) is not None
                      and (not f.get('report_period') if field in ('pe_ttm','pb','pe_percentile') else f.get('report_period') == period)]
        types={(f.get('source','').split('/')[0],f.get('report_type') or 'unknown') for f in candidates}
        mixed=len(types)>1
        fields[field] = dict(status='mixed_types' if mixed else 'ready' if candidates else 'missing', fact_ids=[f['fact_id'] for f in candidates],
            values=[] if mixed else [f['values'][field] for f in candidates],
            observations=[dict(fact_id=f['fact_id'],source=f.get('source'),report_type=f.get('report_type'),value=f['values'][field]) for f in candidates],
            reason='不同供应商报表类型分别保留，不能合并累计与单季口径' if mixed else '' if candidates else '最新报告期或同口径估值未取得该字段')
    cash = next((f for f in financial if f.get('report_period') == period
                 and numeric(f.get('values',{}).get('net_profit')) not in (None,0)
                 and numeric(f.get('values',{}).get('operating_cashflow')) is not None), None)
    fields['cash_profit_ratio'] = dict(status='ready' if cash else 'missing',
        value=cash['values']['operating_cashflow']/cash['values']['net_profit'] if cash else None,
        fact_ids=[cash['fact_id']] if cash else [],
        reason='' if cash else '缺少同一报表口径内的经营现金流和归母利润，未跨表拼接')
    return dict(report_period=period or None, fields=fields)


def numeric(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(',', '').removesuffix('%'))
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def normalize_financials(code, rows, source, observed_at):
    observed_at = stamp(observed_at)
    result = []
    for row in rows:
        actual = str(row.get('SECUCODE', row.get('SECURITY_CODE', row.get('ts_code', code))))[:6]
        if actual != code:
            raise ValueError('财务股票身份不一致')
        period = stamp(row.get('REPORT_DATE', row.get('end_date')))
        if period is None:
            raise ValueError('缺少有效报告期')
        published = stamp(row.get('NOTICE_DATE', row.get('ann_date', row.get('f_ann_date'))))
        revised = stamp(row.get('UPDATE_DATE'))
        values, raw_fields, units = {}, {}, {}
        for field, aliases in FIELDS.items():
            key = next((k for k in aliases if row.get(k) is not None), None)
            value = numeric(row.get(key)) if key else None
            values[field] = value / 100 if value is not None and field in RATIOS else value
            units[field] = 'ratio' if field in RATIOS else 'CNY/share' if field in {'eps', 'bps', 'cashflow_per_share'} else 'CNY'
            if key:
                raw_fields[key] = numeric(row[key])
        if not any(v is not None for v in values.values()):
            continue
        payload = dict(code=code, category='financial', values=values, units=units, source=source,
                       published_at=published, observed_at=observed_at,
                       available_at=max(filter(None, (observed_at, published, revised))), revised_at=revised,
                       report_period=period[:10], report_type=str(row.get('REPORT_TYPE', row.get('report_type', 'unknown'))),
                       vintage_quality='provider_latest', historical_eligible=False,
                       raw_fields=raw_fields, url='https://data.eastmoney.com/bbsj/' if 'tushare' not in source else 'https://tushare.pro/document/2?doc_id=79')
        payload['content_hash'] = digest({k: v for k, v in payload.items()
                                          if k not in ('observed_at', 'available_at')})
        payload['fact_id'] = 'F' + payload['content_hash'][:18]
        result.append(ResearchFact.model_validate(payload).model_dump())
    return sorted(result, key=lambda f: f['report_period'], reverse=True)


def normalize_news(code, name, rows, cutoff):
    output, seen, excluded = [], set(), 0
    cutoff = stamp(cutoff)
    for row in rows:
        title, content = str(row.get('title', '')), str(row.get('content', row.get('snippet', '')))
        url = row.get('url', '')
        published = row.get('published_date', row.get('published_at'))
        try:
            published = stamp(published)
            valid = urlsplit(url).scheme in ('https', 'http') and bool(urlsplit(url).hostname)
        except (ValueError, TypeError):
            valid, published = False, None
        # Search summaries can contain unrelated-stock sidebars. Require the
        # article headline itself to identify the issuer; body mentions are not proof.
        subject_matches = bool(re.search(r'(?<!\d)' + re.escape(code) + r'(?!\d)', title)) or bool(name and name != code and name in title)
        if not valid or not published or published > cutoff or not subject_matches:
            excluded += 1
            continue
        key = digest([title.strip(), published[:10]])
        if key in seen:
            excluded += 1
            continue
        seen.add(key)
        version=digest([key,title,content,url,published,row.get('source')])
        original_date=row.get('published_date',row.get('published_at'))
        output.append(dict(fact_id='N' + version[:18], family_id=key,code=code, category='news', values=dict(title=title, content=content[:6000]),
                           source=row.get('source') or urlsplit(url).hostname, url=url, published_at=published,
                           observed_at=cutoff, available_at=cutoff, vintage_quality='search_summary',
                           historical_eligible=False, content_hash=version,
                           date_precision='date' if len(str(original_date).strip()) in (8,10) else 'datetime'))
    return dict(status='ready' if output else 'missing', facts=output, excluded=excluded,
                limitations=['搜索摘要不是完整新闻库；仅采用标题明确对应该公司的有日期结果，排除仅正文或侧栏命中'])


class ResearchSources:
    def __init__(self, provider, settings):
        self.provider, self.settings = provider, settings

    def _paid_rows(self, name, params):
        rows, seen = [], set()
        for _ in range(8):
            page = self.provider.call(name, params, tushare=True)
            fresh = [r for r in page if digest(r) not in seen]
            rows.extend(fresh)
            seen.update(digest(r) for r in fresh)
            if len(page) < 100:
                return rows
            if not fresh:
                raise ValueError('财务分页没有推进')
            earliest = min(stamp(r['end_date'])[:10] for r in page)
            end = (date.fromisoformat(earliest) - timedelta(days=1)).strftime('%Y%m%d')
            if end < params['start_date']:
                return rows
            params = params | dict(end_date=end)
        raise ValueError('财务分页超过有界上限')

    def financials(self, code, observed_at):
        errors, facts, value_facts = [], [], []
        suffix = '.SH' if code.startswith('6') else '.SZ' if code.startswith(('0', '3')) else '.BJ'
        paid = self.settings.mode.startswith('tushare')
        endpoints = [('fina_indicator', 'income', 'cashflow', 'balancesheet')] if paid else []
        if not paid or self.settings.free_fallback:
            endpoints += [('stock_financial_analysis_indicator_em', 'stock_profit_sheet_by_report_em',
                           'stock_cash_flow_sheet_by_report_em', 'stock_balance_sheet_by_report_em')]
        for group in endpoints:
            group_facts, group_values = [], []
            for name in group:
                is_paid = not name.startswith('stock_')
                params = dict(ts_code=code + suffix, start_date='20000101') if is_paid else (
                    dict(symbol=code + suffix, indicator='按报告期') if name == 'stock_financial_analysis_indicator_em'
                    else dict(symbol=suffix[1:] + code))
                try:
                    rows = self._paid_rows(name, params) if is_paid else self.provider.call(name, params)
                    source = ('tushare/' if is_paid else 'eastmoney/') + name
                    group_facts += normalize_financials(code, rows, source, observed_at)
                    from data_provider.a_share_value_facts import normalize_value_statements
                    group_values += normalize_value_statements(code, rows, source, observed_at)
                except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                    errors.append(dict(source=name, error=type(exc).__name__))
            if group_facts:
                facts, value_facts = group_facts, group_values
                break
        return dict(status='partial' if facts and errors else 'ready' if facts else 'failed', facts=facts, value_facts=value_facts,
                    errors=errors, limitations=['最新修订财报不能当作过去当时已知版本；未获取字段保留缺失'])

    def capital(self, code, observed_at):
        from data_provider.a_share_value_facts import normalize_current_capital, normalize_daily_capital
        if self.settings.mode.startswith('tushare'):
            try:
                suffix = '.SH' if code.startswith('6') else '.SZ' if code.startswith(('0', '3')) else '.BJ'
                day = date.fromisoformat(stamp(observed_at)[:10])
                rows = self.provider.call('daily_basic', dict(ts_code=code+suffix,
                    start_date=(day-timedelta(days=20)).strftime('%Y%m%d'), end_date=day.strftime('%Y%m%d'),
                    fields='ts_code,trade_date,total_share'), tushare=True)
                facts = normalize_daily_capital(code, rows, observed_at)
                if facts:
                    return dict(facts=facts, status='ready')
            except (ValueError, RuntimeError, KeyError, TypeError):
                pass
            if not self.settings.free_fallback:
                return dict(facts=[], status='missing', reason='付费股本接口未取得资料，未越权调用免费回退')
        try:
            rows = self.provider.call('stock_individual_info_em', dict(symbol=code, timeout=15))
            facts = normalize_current_capital(code, rows, observed_at)
            return dict(facts=facts, status='ready' if facts else 'missing')
        except (ValueError, RuntimeError, KeyError, TypeError):
            return dict(facts=[], status='failed', reason='当前总股本未核实，未使用流通股或注册资本替代')

    def distributions(self, code, observed_at):
        from data_provider.a_share_value_facts import normalize_distributions
        errors=[]
        names=['dividend'] if self.settings.mode.startswith('tushare') else []
        if not names or self.settings.free_fallback:
            names.append('stock_fhps_detail_em')
        for name in names:
            paid=name=='dividend'
            suffix='.SH' if code.startswith('6') else '.SZ' if code.startswith(('0','3')) else '.BJ'
            try:
                rows=self.provider.call(name,dict(ts_code=code+suffix) if paid else dict(symbol=code),tushare=paid)
                items=normalize_distributions(code,rows,('tushare/' if paid else 'eastmoney/')+name,observed_at)
                if items:
                    return dict(status='ready',items=items,errors=errors)
            except (ValueError,RuntimeError,KeyError,TypeError) as exc:
                errors.append(type(exc).__name__)
        return dict(status='missing',items=[],errors=errors)

    def disclosures(self, code, start, end, observed_at):
        errors = []
        if self.settings.announcements_entitled:
            try:
                rows = self.provider.call('anns_d', dict(ts_code=code + ('.SH' if code.startswith('6') else '.SZ'),
                    start_date=start.replace('-', ''), end_date=end.replace('-', '')), tushare=True)
                return dict(status='ready', events=normalize_disclosures(code, rows, observed_at), errors=[])
            except (ValueError, RuntimeError, KeyError, TypeError) as exc:
                errors.append(dict(source='tushare/anns_d', error=type(exc).__name__))
                if not self.settings.free_fallback:
                    return dict(status='failed', events=[], errors=errors)
        try:
            rows = self.provider.call('stock_zh_a_disclosure_report_cninfo', dict(symbol=code, market='沪深京',
                category='', start_date=start.replace('-', ''), end_date=end.replace('-', '')))
            events = normalize_disclosures(code, rows, observed_at)
            return dict(status='partial' if errors else 'ready' if events else 'missing', events=events, errors=errors)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            return dict(status='failed', events=[], errors=errors + [dict(source='cninfo', error=type(exc).__name__)])

    def news(self, code, company_name, industries, cutoff):
        try:
            from src.search_service import get_search_service
            response = get_search_service().search_topic_news_bounded(
                f'{code} {company_name}', max_results=8,
                focus_keywords=[code, company_name, '公告 业绩 政策'], timeout_seconds=25.)
            rows = [r.to_dict() if hasattr(r, 'to_dict') else vars(r) for r in response.results]
            return normalize_news(code, company_name, rows, cutoff)
        except Exception as exc:
            # Search providers may include secrets in exception text.
            return dict(status='failed', facts=[], error=type(exc).__name__, limitations=['相关新闻未取得，不代表没有风险'])

    def valuation(self, code, observed_at):
        """Current valuation plus explicitly reconstructed historical observations."""
        errors, rows, source = [], [], 'eastmoney/stock_value_em'
        if self.settings.mode.startswith('tushare'):
            try:
                rows = self.provider.call('daily_basic', dict(ts_code=code+('.SH' if code.startswith('6') else '.SZ' if code.startswith(('0','3')) else '.BJ'),
                    start_date='20210101', end_date=observed_at[:10].replace('-','')) ,tushare=True)
                source='tushare/daily_basic'
            except (ValueError,RuntimeError,KeyError,TypeError) as exc:
                errors.append(type(exc).__name__)
                if not self.settings.free_fallback:
                    return dict(status='failed',facts=[],history=[],errors=errors)
        if not rows and self.settings.mode.startswith('tushare') and not self.settings.free_fallback:
            return dict(status='missing', facts=[], history=[], errors=errors)
        if not rows:
            try:
                rows=self.provider.call('stock_value_em',dict(symbol=code))
                source='eastmoney/stock_value_em'
            except (ValueError,RuntimeError,KeyError,TypeError) as exc:
                return dict(status='failed',facts=[],history=[],errors=errors+[type(exc).__name__])
        history=[]
        for row in rows:
            day=stamp(row.get('数据日期',row.get('trade_date')))
            if not day or day[:10]>observed_at[:10]:
                continue
            history.append(dict(trade_date=day[:10],pe_ttm=numeric(row.get('PE(TTM)',row.get('pe_ttm'))),
                pb=numeric(row.get('市净率',row.get('pb'))),close=numeric(row.get('当日收盘价',row.get('close'))),
                market_cap=numeric(row.get('总市值')) if source.startswith('eastmoney') else (numeric(row.get('total_mv')) or 0)*10000 or None))
        history.sort(key=lambda r:r['trade_date'])
        if not history:
            return dict(status='missing',facts=[],history=[],errors=errors)
        latest=history[-1]
        pe=latest['pe_ttm']
        prior=[r['pe_ttm'] for r in history if r['pe_ttm'] is not None and r['pe_ttm']>0]
        values=latest | dict(pe_percentile=sum(v<=pe for v in prior)/len(prior) if pe is not None and pe>0 and prior else None,
                             percentile_observations=len(prior),history_vintage='provider_reconstructed')
        identity=digest([code,source,values])
        fact=dict(fact_id='FV'+identity[:17],code=code,category='financial',source=source,
            values=values,units=dict(pe_ttm='multiple',pb='multiple',market_cap='CNY'),
            observed_at=observed_at,available_at=observed_at,published_at=None,report_period=None,
            vintage_quality='provider_latest',historical_eligible=False,content_hash=identity,
            url='https://data.eastmoney.com/gzfx/detail/'+code+'.html')
        from data_provider.a_share_value_facts import normalize_valuation_capital
        return dict(status='partial' if errors else 'ready',facts=[fact],history=history,errors=errors,
                    value_facts=normalize_valuation_capital(code, rows, source, observed_at))
