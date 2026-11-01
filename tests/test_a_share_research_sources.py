from datetime import datetime
import pytest

from src.schemas.a_share import AssistantSettings
from data_provider.a_share_fundamentals import normalize_financials, ResearchSources
from data_provider.a_share_disclosures import normalize_disclosures, disclosure_pdf_url, extract_pdf_bytes

NOW = '2026-10-16T10:00:00+08:00'


def test_latest_restatement_is_not_historical_vintage():
    fact = normalize_financials('000807', [{'SECUCODE': '000807.SZ', 'REPORT_DATE': '2025-12-31',
        'NOTICE_DATE': '2026-03-20', 'UPDATE_DATE': '2026-10-15',
        'TOTALOPERATEREVE': 100000000, 'PARENTNETPROFIT': -10000000,
        'ROEJQ': 12.5, 'ZCFZL': float('nan')}], 'eastmoney/main', NOW)[0]
    assert fact['available_at'] == NOW
    assert fact['historical_eligible'] is False
    assert fact['report_period'] == '2025-12-31'
    assert fact['values']['revenue'] == 100000000
    assert fact['values']['net_profit'] == -10000000
    assert fact['values']['roe'] == .125
    assert fact['values']['debt_ratio'] is None
    assert fact['units']['revenue'] == 'CNY'


def test_stock_mismatch_and_invalid_report_date_are_not_facts():
    with pytest.raises(ValueError):
        normalize_financials('000807', [{'SECUCODE': '600519.SH', 'REPORT_DATE': '2025-12-31'}], 'eastmoney', NOW)
    with pytest.raises(ValueError):
        normalize_financials('000807', [{'REPORT_DATE': '2025-02-31'}], 'eastmoney', NOW)


def test_tushare_units_report_type_and_announcement_are_preserved():
    fact = normalize_financials('000807', [{'ts_code': '000807.SZ', 'end_date': '20260630',
        'ann_date': '20260820', 'n_income_attr_p': 123., 'report_type': '1', 'comp_type': '1'}], 'tushare/income', NOW)[0]
    assert fact['report_period'] == '2026-06-30'
    assert fact['published_at'].startswith('2026-08-20')
    assert fact['values']['net_profit'] == 123.
    assert fact['report_type'] == '1'
    assert fact['values']['operating_cashflow'] is None


def test_title_alone_does_not_invent_strength_or_original_document():
    event = normalize_disclosures('000807', [{'代码': '000807', '公告标题': '云南铝业2026年半年度业绩预告',
        '公告时间': '2026-07-14', '公告链接': 'http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1225421954'}], NOW)[0]
    assert event['intensity'] is None
    assert event['text_status'] == 'missing'
    assert event['published_at'] == '2026-07-14T23:59:59+08:00'
    assert event['observed_at'] == NOW
    assert event['kind'] == 'earnings'
    assert event['direction'] == 'unknown'
    assert event['report_period'] == '2026-06-30'
    assert event['url'].startswith('https://www.cninfo.com.cn/')


@pytest.mark.parametrize('url', ['https://evil.test/x.pdf', 'http://127.0.0.1/x.pdf',
    'https://www.cninfo.com.cn.evil.test/x.pdf', 'https://user@static.cninfo.com.cn/x.pdf',
    'https://static.cninfo.com.cn:9000/x.pdf', 'https://static.cninfo.com.cn/../x.pdf'])
def test_disclosure_download_cannot_target_arbitrary_hosts(url):
    with pytest.raises(ValueError):
        disclosure_pdf_url(url, '2026-07-14')


def test_real_announcement_id_maps_only_to_official_pdf():
    assert disclosure_pdf_url('https://www.cninfo.com.cn/new/disclosure/detail?announcementId=1225421954',
        '2026-07-14') == 'https://static.cninfo.com.cn/finalpage/2026-07-14/1225421954.PDF'


def test_invalid_pdf_and_limits_do_not_become_article_text():
    assert extract_pdf_bytes(b'<html>error</html>')['status'] == 'failed'
    assert extract_pdf_bytes(b'%PDF-'+b'x'*100, max_bytes=20)['status'] == 'failed'


def test_pdf_text_is_extracted_in_bounded_worker():
    from pypdf import PdfWriter
    from io import BytesIO
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    stream = BytesIO()
    writer.write(stream)
    result = extract_pdf_bytes(stream.getvalue())
    assert result['status'] == 'missing'
    assert result['pages'] == 1
    assert result['text'] == ''


def test_normal_annual_report_length_is_not_rejected_as_an_oversized_document():
    from pypdf import PdfWriter
    from io import BytesIO
    writer=PdfWriter()
    for _ in range(243): writer.add_blank_page(width=100,height=100)
    stream=BytesIO();writer.write(stream)
    result=extract_pdf_bytes(stream.getvalue())
    assert result['status']=='missing'
    assert result['pages']==243
    assert extract_pdf_bytes(stream.getvalue(),max_pages=80)['status']=='failed'


def test_paid_failure_respects_fallback_and_retains_partial_free_tables():
    class Provider:
        def call(self, name, params=None, tushare=False):
            if tushare:
                raise RuntimeError('permission')
            if name == 'stock_financial_analysis_indicator_em':
                return [{'SECUCODE': '000807.SZ', 'REPORT_DATE': '20260630', 'PARENTNETPROFIT': 23.}]
            raise RuntimeError('upstream')
    result = ResearchSources(Provider(), AssistantSettings(mode='tushare2000')).financials('000807', NOW)
    assert result['status'] == 'partial'
    assert result['facts'][0]['values']['net_profit'] == 23.
    assert result['errors']
    blocked = ResearchSources(Provider(), AssistantSettings(mode='tushare2000', free_fallback=False)).financials('000807', NOW)
    assert blocked['facts'] == []
    assert blocked['status'] in ('failed', 'unauthorized')


def test_news_requires_stock_identity_and_real_publication_before_cutoff():
    from data_provider.a_share_fundamentals import normalize_news
    rows = [dict(title='云铝股份业绩说明', content='000807经营情况', url='https://example.com/a', published_date='2026-10-15'),
            dict(title='同名无关公司', content='无关内容', url='https://example.com/b', published_date='2026-10-15'),
            dict(title='云铝股份未来报道', content='000807', url='https://example.com/c', published_date='2026-10-17'),
            dict(title='云铝股份无日期', content='000807', url='https://example.com/d')]
    result = normalize_news('000807', '云铝股份', rows, NOW)
    assert len(result['facts']) == 1
    assert result['facts'][0]['url'] == 'https://example.com/a'
    assert result['excluded'] == 3


def test_unchanged_financial_content_has_stable_identity_on_refetch():
    row = {'SECUCODE': '000807.SZ', 'REPORT_DATE': '20260630', 'PARENTNETPROFIT': 123.}
    first = normalize_financials('000807', [row], 'eastmoney/main', NOW)[0]
    later = normalize_financials('000807', [row], 'eastmoney/main', '2026-10-17T10:00:00+08:00')[0]
    assert first['fact_id'] == later['fact_id']
    assert first['observed_at'] != later['observed_at']


def test_news_adapter_uses_bounded_existing_search(monkeypatch):
    from types import SimpleNamespace
    import src.search_service
    class Search:
        def search_topic_news_bounded(self, topic, max_results, focus_keywords, timeout_seconds):
            assert timeout_seconds <= 30
            return SimpleNamespace(results=[SimpleNamespace(title='云铝股份公告', snippet='000807经营情况',
                source='原文网站', url='https://example.com/original', published_date='2026-10-15')])
    monkeypatch.setattr(src.search_service, 'get_search_service', lambda: Search())
    result = ResearchSources(None, AssistantSettings(mode='free')).news('000807', '云铝股份', [], NOW)
    assert result['status'] == 'ready'
    assert result['facts'][0]['values']['content'] == '000807经营情况'


def test_paid_financials_paginate_instead_of_truncating_at_one_hundred():
    from datetime import date, timedelta
    class Provider:
        first = True
        def call(self, name, params=None, tushare=False):
            if name != 'fina_indicator':
                return []
            if self.first:
                self.first = False
                return [dict(ts_code='000807.SZ', end_date=(date(2026, 6, 30)-timedelta(days=i)).strftime('%Y%m%d'), eps=1.) for i in range(100)]
            assert params['end_date'] == '20260322'
            return [dict(ts_code='000807.SZ', end_date='20260321', eps=2.)]
    result = ResearchSources(Provider(), AssistantSettings(mode='tushare2000', free_fallback=False)).financials('000807', NOW)
    assert len(result['facts']) == 101


def test_free_valuation_retains_real_date_and_does_not_backdate_availability():
    class Provider:
        def call(self, name, params=None, tushare=False):
            assert name == 'stock_value_em'
            return [dict(数据日期='2026-10-14', **{'当日收盘价':20., 'PE(TTM)':10., '市净率':2.}),
                    dict(数据日期='2026-10-15', **{'当日收盘价':21., 'PE(TTM)':12., '市净率':2.1}),
                    dict(数据日期='2026-10-17', **{'当日收盘价':22., 'PE(TTM)':15.})]
    result = ResearchSources(Provider(), AssistantSettings(mode='free')).valuation('000807', NOW)
    assert result['facts'][0]['values']['pe_ttm'] == 12.
    assert result['facts'][0]['values']['trade_date'] == '2026-10-15'
    assert result['facts'][0]['available_at'] == NOW
    assert result['facts'][0]['historical_eligible'] is False
    assert len(result['history']) == 2


def test_empty_paid_valuation_does_not_bypass_disabled_free_fallback():
    class Provider:
        def call(self, name, params=None, tushare=False):
            assert tushare is True
            return []
    result = ResearchSources(Provider(),AssistantSettings(mode='tushare2000',free_fallback=False)).valuation('000807',NOW)
    assert result['status']=='missing' and result['facts']==[]


def test_corrected_earnings_share_family_without_merging_different_periods():
    rows=[dict(代码='000807',公告标题=title,公告时间='2026-07-14',公告链接=f'https://www.cninfo.com.cn/new/disclosure/detail?announcementId={i}') for i,title in enumerate([
        '2026年半年度业绩预告','2026年半年度业绩预告修正公告','2025年年度业绩预告'],1)]
    events=normalize_disclosures('000807',rows,NOW)
    assert events[0]['family_id']==events[1]['family_id']
    assert events[0]['family_id']!=events[2]['family_id']


def test_financial_coverage_explains_missing_fields_instead_of_filling_them():
    from data_provider.a_share_fundamentals import financial_coverage
    rows=normalize_financials('000807',[dict(REPORT_DATE='20260630',PARENTNETPROFIT=10.)],'eastmoney/main',NOW)
    result=financial_coverage(rows)
    assert result['fields']['net_profit']['status']=='ready'
    assert result['fields']['operating_cashflow']['status']=='missing'
    assert result['fields']['cash_profit_ratio']['reason']


def test_news_sidebar_stock_mentions_cannot_identify_the_article_subject():
    from data_provider.a_share_fundamentals import normalize_news
    rows = [
        dict(title='魯西化工 (000830.SZ) 股價、新聞、報價和記錄',
             content='其他人也注意：000807.SZ 雲鋁股份 25.03 -4.72%',
             url='https://hk.finance.yahoo.com/quote/000830.SZ', published_date='2026-10-14'),
        dict(title='0008070 行业报道', content='云铝股份',
             url='https://example.com/other', published_date='2026-10-14'),
        dict(title='000807：半年报业绩说明', content='营业收入与成本情况',
             url='https://example.com/real-news', published_date='2026-10-14'),
    ]
    result=normalize_news('000807','云铝股份',rows,NOW)
    assert [fact['url'] for fact in result['facts']] == ['https://example.com/real-news']
    assert result['excluded'] == 2
