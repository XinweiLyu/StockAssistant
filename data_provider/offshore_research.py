"""Current-vintage offshore financials and news with explicit source coverage."""
from datetime import date,datetime,timedelta,timezone
import re
from src.schemas.a_share_integrated import digest,stamp
from src.schemas.a_share_value import ValueFact
from data_provider.market_workspace import finite

FIELDS={
 'Total Revenue':'revenue','Operating Revenue':'revenue','Net Income':'net_profit','Net Income Including Noncontrolling Interests':'total_net_profit',
 'Operating Income':'operating_profit','Cost Of Revenue':'operating_cost','Tax Provision':'income_tax','Pretax Income':'total_profit',
 'Interest Expense':'interest_expense','Operating Cash Flow':'operating_cashflow','Capital Expenditure':'capex',
 'Depreciation And Amortization':'da','Cash And Cash Equivalents':'cash','Total Assets':'assets',
 'Total Liabilities Net Minority Interest':'liabilities','Stockholders Equity':'parent_equity','Minority Interest':'minority_equity',
 'Accounts Receivable':'receivables','Inventory':'inventory','Long Term Debt':'long_debt','Current Debt':'short_debt',
 'Common Stock Equity':'parent_equity','Ordinary Shares Number':'shares','Treasury Shares Number':'treasury_shares',
 'Treasury Stock':'treasury_share_cost','Cash Dividends Paid':'dividend_cash',
}


def normalize_yahoo_statements(code,frame,statement,basis,currency,observed_at):
    if frame is None or frame.empty or not currency:return []
    from src.services.market_workspace_symbols import resolve_instrument
    source_symbol=resolve_instrument(code.split(':')[0],code).source_symbol
    columns=sorted([(date.fromisoformat(str(c)[:10]),c) for c in frame.columns])
    names={re.sub(r'[^a-z0-9]','',str(label).lower()):label for label in frame.index}
    output=[];used=set()
    for i,(end,column) in enumerate(columns):
        previous=columns[i-1][0] if i else None
        actual_basis=basis
        start=None
        if statement!='balance' and previous:
            days=(end-previous).days
            if basis=='annual' and 330<=days<=400:start=(previous+timedelta(days=1)).isoformat()
            elif basis=='quarter' and 65<=days<=115:start=(previous+timedelta(days=1)).isoformat()
            elif basis=='quarter' and 150<=days<=210:start=(previous+timedelta(days=1)).isoformat();actual_basis='half_year'
        for raw,metric in FIELDS.items():
            actual=names.get(re.sub(r'[^a-z0-9]','',raw.lower()))
            if actual is None or (metric,end,statement) in used:continue
            value=finite(frame.loc[actual,column])
            if value is None:continue
            if metric in ('capex','dividend_cash'):value=abs(value)
            units='shares' if metric in ('shares','treasury_shares') else currency
            attribution='parent_common' if metric in ('net_profit','parent_equity','shares','treasury_shares') else 'minority' if metric=='minority_equity' else 'all_claims'
            record=dict(code=code,market=code.split(':')[0],currency=currency,metric=metric,value=value,unit=units,
                report_period=end.isoformat(),period_start=start,period_end=end.isoformat(),
                period_basis='instant' if statement=='balance' else actual_basis,scope='consolidated',attribution=attribution,
                source='yfinance/'+statement,raw_field=str(actual),published_at=None,observed_at=observed_at,available_at=observed_at,
                url='https://finance.yahoo.com/quote/'+source_symbol+'/financials/',
                vintage_quality='latest_reconstructed')
            identity=digest(record)
            try:output.append(ValueFact(**record,fact_id='YF'+identity[:24],content_hash=identity).model_dump());used.add((metric,end,statement))
            except ValueError:continue
    return output


def normalize_yahoo_dividends(code,series,currency,observed_at):
    from src.services.market_workspace_symbols import resolve_instrument
    identity=resolve_instrument(code.split(':')[0],code)
    result=[]
    if series is None or not currency:return result
    for when,amount in series.items():
        value=finite(amount);day=when.date().isoformat()
        if value is None or value<=0 or day>observed_at[:10]:continue
        result.append(dict(id='YFD'+digest([code,day,value])[:24],code=code,source='yfinance/dividends',
            ex_date=day,cash_per_share=value,currency=currency,payment_currency_verified=False,
            status='vendor_observed',published_at=None,available_at=observed_at,observed_at=observed_at,
            url='https://finance.yahoo.com/quote/'+identity.source_symbol+'/history/',
            limitation='供应商分红候选，除息日不等于支付日；支付币种及实施状态需原文核实'))
    return result


class OffshoreResearchSources:
    def fetch(self,identity,metadata,cutoff):
        import yfinance as yf
        from src.config import get_config
        from data_provider.sec_filings import SecFilings
        ticker=yf.Ticker(identity.source_symbol)
        currency=metadata.get('financial_currency')
        value_facts=[];events=[];facts=[];coverage=[];missing=[];distributions=[]
        official=None
        if identity.market=='us':
            try:
                official=SecFilings(get_config().sec_user_agent).company(identity.symbol,cutoff)
                value_facts=official['facts']
                coverage.append(dict(category='sec',status='ready' if value_facts else 'partial',count=len(value_facts),source='SEC'))
            except Exception as exc:
                missing.append('SEC_USER_AGENT未配置或SEC资料未取得；未替代为官方完整资料')
                coverage.append(dict(category='sec',status='failed',count=0,error=type(exc).__name__))
        if not value_facts:
            if not currency:missing.append('财报币种未核实；不能用报价币种代替财报原币种')
            for statement,method in [('income','get_income_stmt'),('balance','get_balance_sheet'),('cashflow','get_cash_flow')]:
                for basis,freq in [('annual','yearly'),('quarter','quarterly')]:
                    try:
                        rows=normalize_yahoo_statements(identity.instrument_id,getattr(ticker,method)(freq=freq),statement,basis,currency,cutoff)
                        value_facts.extend(rows)
                    except Exception as exc:missing.append(statement+'/'+freq+'未取得：'+type(exc).__name__)
            missing.append('供应商财报为当前修订资料，原始公布时点未知；不得用于历史当时已知回测')
        try:
            series=ticker.get_dividends(period='5y')
            distributions=normalize_yahoo_dividends(identity.instrument_id,series,metadata.get('currency'),cutoff)
            coverage.append(dict(category='distributions',status='partial' if distributions else 'missing',count=len(distributions),source='yfinance/dividends'))
        except Exception as exc:
            coverage.append(dict(category='distributions',status='failed',count=0,error=type(exc).__name__))
        # Expose source currency on equity counts as well; never convert share units with FX.
        for item in value_facts:
            if item['unit']=='shares' and currency:item['currency']=currency
            facts.append(dict(fact_id=item['fact_id'],code=identity.instrument_id,category='financial',values={item['metric']:item['value']},
                units={item['metric']:item['unit']},source=item['source'],published_at=item['published_at'],available_at=item['available_at'],
                observed_at=cutoff,report_period=item['report_period'],vintage_quality=item['vintage_quality'],url=item.get('url')))
            facts[-1]['values']['period_basis']=item['period_basis']
        coverage.append(dict(category='financial',status='partial' if value_facts else 'missing',count=len(value_facts),source='SEC' if official else 'yfinance'))
        # Preserve latest observed shares as a candidate, not a falsely dated current-share fact.
        if metadata.get('info',{}).get('sharesOutstanding'):
            missing.append('供应商总股数仅为候选；股权类别、库存股及截至报价日的资本行动覆盖需核实')
        if official:
            recent=official['filings'].get('filings',{}).get('recent',{})
            for index,form in enumerate(recent.get('form',[])[:200]):
                if form not in ('10-K','10-Q','8-K','20-F','6-K','10-K/A','10-Q/A'):continue
                filed=recent.get('filingDate',[])[index];acc=recent.get('accessionNumber',[])[index]
                document=recent.get('primaryDocument',[])[index]
                when=stamp(filed+'T23:59:59-05:00')
                if not when or when>stamp(cutoff):continue
                url='https://www.sec.gov/Archives/edgar/data/'+str(int(official['cik']))+'/'+acc.replace('-','')+'/'+document
                events.append(dict(id='SECE'+digest([identity.instrument_id,acc])[:20],code=identity.instrument_id,market=identity.market,
                    source='sec/submissions',title=form+' '+filed,published_at=when,observed_at=cutoff,available_at=cutoff,url=url,
                    report_period=(recent.get('reportDate') or ['']*len(recent.get('form',[])))[index] or None,
                    kind='earnings' if form.startswith(('10-K','10-Q','20-F')) else 'disclosure',text='',text_status='not_fetched',public_verified=False))
            missing.append('SEC申报目录已获取；标题未取原文的条目不作为已核实事件幅度证据')
        try:
            from src.search_service import get_search_service
            response=get_search_service().search_topic_news_bounded(identity.symbol+' '+metadata.get('name',''),max_results=8,
                focus_keywords=['earnings guidance regulation buyback industry'],timeout_seconds=25.)
            for row in response.results:
                content=vars(row);key='NEWS'+digest([identity.instrument_id,content.get('url'),content.get('title')])[:20]
                # Summary stays a lead. It cannot acquire full-text status through normalization.
                facts.append(dict(fact_id=key,code=identity.instrument_id,category='news',source=content.get('source') or 'search',
                    available_at=cutoff,published_at=stamp(content.get('published_date')),observed_at=cutoff,vintage_quality='latest_reconstructed',
                    url=content.get('url'),values=dict(title=content.get('title'),summary=content.get('snippet'),text_status='summary_only')))
            coverage.append(dict(category='news',status='partial' if response.results else 'missing',count=len(response.results),source=response.provider))
        except Exception as exc:coverage.append(dict(category='news',status='failed',count=0,error=type(exc).__name__))
        if identity.market=='hk':
            try:
                from data_provider.offshore_disclosures import official_document_url
                response=get_search_service().search_topic_news_bounded('site:hkexnews.hk '+identity.symbol+' '+metadata.get('name',''),max_results=4,timeout_seconds=20.)
                for row in response.results:
                    try:url=official_document_url(row.url)
                    except ValueError:continue
                    published=stamp(row.published_date)
                    if not published or published>stamp(cutoff):continue
                    events.append(dict(id='HKEX'+digest([identity.instrument_id,url])[:20],code=identity.instrument_id,market='hk',source='hkexnews/search_discovery',
                        title=row.title,url=url,published_at=published,observed_at=cutoff,available_at=cutoff,kind='earnings' if re.search('results|report|業績|业绩|報告|报告',row.title,re.I) else 'disclosure',
                        text='',text_status='not_fetched',public_verified=False))
            except Exception as exc:missing.append('港交所原文发现未完成：'+type(exc).__name__)
            missing.append('港交所原文仅覆盖已发现并验证的文件，不代表完整历史公告库')
        from data_provider.offshore_disclosures import fetch_official_document
        for event in events[:6]:
            original=fetch_official_document(event['url'],get_config().sec_user_agent)
            company_ok=identity.market=='us'
            if identity.market=='hk' and original.get('text'):
                name=re.sub(r'[^A-Z0-9\u4e00-\u9fff]','',metadata.get('name','').upper())
                text_name=re.sub(r'[^A-Z0-9\u4e00-\u9fff]','',original['text'][:20000].upper())
                company_ok=bool(len(name)>=5 and name in text_name)
            event.update(text=original.get('text','') if company_ok else '',text_status=original['status'] if company_ok else 'identity_unverified',
                text_hash=original.get('content_hash'),public_verified=company_ok and original['status']=='ready',text_truncated=original.get('truncated',False))
        coverage.append(dict(category='disclosures',status='partial' if events else 'missing',count=len(events),
            verified_texts=sum(e.get('text_status')=='ready' for e in events),source='SEC' if identity.market=='us' else 'HKEXnews'))
        return dict(facts=facts,value_facts=value_facts,events=events,coverage=coverage,missing=missing,
            distributions=distributions,valuation_history=[])
