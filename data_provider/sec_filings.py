"""SEC standard-taxonomy facts with filing/period provenance, no inferred zeros."""
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo
import threading
import time
import requests
from src.schemas.a_share_integrated import digest,stamp
from src.schemas.a_share_value import ValueFact

TAGS={
 'revenue':('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','Revenue'),
 'net_profit':('NetIncomeLoss','ProfitLossAttributableToOwnersOfParent'),
 'total_net_profit':('ProfitLoss',),
 'operating_cashflow':('NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities'),
 'capex':('PaymentsToAcquirePropertyPlantAndEquipment','PurchaseOfPropertyPlantAndEquipment'),
 'cash':('CashAndCashEquivalentsAtCarryingValue','CashAndCashEquivalents'),
 'assets':('Assets',),'liabilities':('Liabilities',),'parent_equity':('StockholdersEquity','EquityAttributableToOwnersOfParent'),
 'minority_equity':('MinorityInterest','NoncontrollingInterests'),
 'short_debt':('ShortTermBorrowings',),'long_debt':('LongTermDebtNoncurrent',),
 'bonds':('BondsPayable',),'lease_liabilities':('OperatingLeaseLiabilityNoncurrent','LeaseLiabilities'),
 'operating_profit':('OperatingIncomeLoss','ProfitLossFromOperatingActivities'),
 'operating_cost':('CostOfRevenue','CostOfSales'),'receivables':('AccountsReceivableNetCurrent','TradeAndOtherCurrentReceivables'),
 'inventory':('InventoryNet','Inventories'),'income_tax':('IncomeTaxExpenseBenefit','IncomeTaxExpenseContinuingOperations'),
 'total_profit':('IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest','ProfitLossBeforeTax'),
 'da':('DepreciationDepletionAndAmortization','DepreciationDepletionAndAmortizationPropertyPlantAndEquipment'),
 'shares':('EntityCommonStockSharesOutstanding','CommonStockSharesOutstanding'),
 'dividend_cash':('PaymentsOfDividendsCommonStock','DividendsPaid'),
}
INSTANT={'cash','assets','liabilities','parent_equity','minority_equity','short_debt','long_debt','bonds','lease_liabilities','receivables','inventory','shares'}
FORMS={'10-K','10-Q','8-K','20-F','6-K','40-F','10-K/A','10-Q/A','20-F/A','6-K/A','8-K/A','40-F/A'}


def normalize_sec_facts(code,payload,observed_at):
    output=[];market=code.split(':')[0]
    for namespace in ('us-gaap','ifrs-full','dei'):
        taxonomy=payload.get('facts',{}).get(namespace,{})
        for metric,tags in TAGS.items():
            for tag in tags:
                content=taxonomy.get(tag,{})
                for unit,records in content.get('units',{}).items():
                    if (metric=='shares' and unit!='shares') or (metric!='shares' and (len(unit)!=3 or not unit.isupper())):continue
                    grouped={}
                    for row in records:
                        if row.get('form') not in FORMS or not row.get('filed') or not row.get('end'):continue
                        try:
                            released=datetime.combine(date.fromisoformat(row['filed']),datetime.max.time(),ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()
                            if stamp(released)>stamp(observed_at):continue
                            days=(date.fromisoformat(row['end'])-date.fromisoformat(row['start'])).days+1 if row.get('start') else 0
                        except ValueError:continue
                        if metric in INSTANT:
                            if row.get('start'):continue
                            basis='instant'
                        elif not row.get('start'):continue
                        else:basis='annual' if 330<=days<=400 else 'quarter' if 65<=days<=115 else 'half_year' if 150<=days<=210 else 'ytd' if 210<days<330 else None
                        if not basis:continue
                        key=(row.get('start'),row['end'],basis)
                        # A filed amendment supersedes that same fiscal interval; retain lineage in raw field/id.
                        old=grouped.get(key)
                        if old is None or row['filed']>old[0]['filed']:grouped[key]=(row,released)
                        elif row['filed']==old[0]['filed'] and row.get('val')!=old[0].get('val'):
                            grouped[key]=(old[0]|dict(conflicting=True),old[1])
                    for interval,(row,released) in grouped.items():
                        attribution='parent_common' if metric in ('net_profit','parent_equity','shares') else 'minority' if metric=='minority_equity' else 'all_claims'
                        identity=digest([code,namespace,tag,row,unit])
                        try:
                            output.append(ValueFact(fact_id='SEC'+identity[:24],code=code,market=market,currency=unit if unit!='shares' else 'USD',
                                metric=metric,value=float(row['val']),unit=unit,report_period=row['end'],period_start=row.get('start'),period_end=row['end'],
                                period_basis=interval[2],
                                scope='consolidated',attribution=attribution,source='sec/companyfacts',raw_field=namespace+'/'+tag,
                                published_at=released,observed_at=observed_at,available_at=released,content_hash=identity,
                                conflicts=['同次披露数值冲突'] if row.get('conflicting') else [],
                                url='https://www.sec.gov/Archives/edgar/data/'+str(payload.get('cik'))+'/'+row.get('accn','').replace('-','')+'/').model_dump())
                        except (ValueError,TypeError):continue
    return output


class SecFilings:
    _lock=threading.Lock();_last=0.;_mapping=None;_mapping_at=0.
    def __init__(self,user_agent):self.user_agent=str(user_agent or '').strip()
    def _get(self,url):
        if not self.user_agent:raise ValueError('未配置SEC_USER_AGENT真实访问标识；可先使用供应商财报或补录原文')
        with self._lock:
            delay=.25-(time.monotonic()-SecFilings._last)
            if delay>0:time.sleep(delay)
            SecFilings._last=time.monotonic()
        response=requests.get(url,headers={'User-Agent':self.user_agent,'Accept-Encoding':'gzip, deflate'},timeout=(5,20))
        response.raise_for_status();return response.json()
    def company(self,symbol,observed_at):
        if not self.user_agent:raise ValueError('未配置SEC_USER_AGENT真实访问标识')
        if self._mapping is None or time.monotonic()-self._mapping_at>86400:
            SecFilings._mapping=self._get('https://www.sec.gov/files/company_tickers.json');SecFilings._mapping_at=time.monotonic()
        rows=[r for r in self._mapping.values() if r.get('ticker','').replace('-','.').upper()==symbol.upper()]
        if len(rows)!=1:raise ValueError('SEC发行人映射不存在或不唯一；不能由代码猜测ADR股权比例')
        cik=str(rows[0]['cik_str']).zfill(10)
        facts=self._get('https://data.sec.gov/api/xbrl/companyfacts/CIK'+cik+'.json')
        filings=self._get('https://data.sec.gov/submissions/CIK'+cik+'.json')
        return dict(cik=cik,facts=normalize_sec_facts('us:'+symbol,facts,observed_at),filings=filings)
