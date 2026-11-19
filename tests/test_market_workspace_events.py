def test_us_after_close_event_uses_prior_completed_session():
    from src.services.a_share_event_lifecycle import event_anchor_index
    days=['2026-11-12','2026-11-13','2026-11-16']
    # 14:00 New York Friday: only Thursday is available before publication.
    assert event_anchor_index('2026-11-13T19:00:00+00:00',days,market='us')==0
    assert event_anchor_index('2026-11-13T22:00:00+00:00',days,market='us')==1


def test_hk_after_close_and_holiday_are_market_local():
    from src.services.a_share_event_lifecycle import event_anchor_index
    days=['2026-11-12','2026-11-13','2026-11-16']
    assert event_anchor_index('2026-11-14T12:00:00+08:00',days,market='hk')==1


def test_official_earnings_change_requires_known_same_basis_facts_and_full_text():
    from src.services.a_share_event_cases import extract_event_facts
    event=dict(id='e',code='us:AAPL',market='us',kind='earnings',report_period='2026-09-30',published_at='2026-10-30T23:00:00+00:00',text='Original annual report',text_status='ready')
    facts=[dict(fact_id='current',code='us:AAPL',source='sec/companyfacts',report_period='2026-09-30',available_at='2026-10-30T21:00:00+00:00',values={'net_profit':120.,'period_basis':'annual'},units={'net_profit':'USD'}),
        dict(fact_id='previous',code='us:AAPL',source='sec/companyfacts',report_period='2025-09-30',available_at='2025-10-30T21:00:00+00:00',values={'net_profit':100.,'period_basis':'annual'},units={'net_profit':'USD'})]
    result=extract_event_facts(event,facts)
    assert result['intensity']==.2 and result['expectation_surprise'] is None
    assert set(result['metric_sources'])=={'current','previous'}
    assert extract_event_facts(event|{'text_status':'not_fetched'},facts)['intensity'] is None
    facts[0]['available_at']='2026-11-01T00:00:00+00:00'
    assert extract_event_facts(event,facts)['intensity'] is None


def test_original_document_fetcher_only_accepts_official_hosts():
    from data_provider.offshore_disclosures import official_document_url
    import pytest
    assert official_document_url('https://www.sec.gov/Archives/edgar/data/1/2/report.htm')
    assert official_document_url('https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1113/a.pdf')
    for url in ['http://127.0.0.1/','https://www.sec.gov.evil.test/x','https://www.sec.gov@evil.test/x','https://www.sec.gov:444/x']:
        with pytest.raises(ValueError):official_document_url(url)


def test_comparable_events_cannot_silently_cross_markets():
    from src.services.a_share_event_cases import match_event_cases
    base=dict(kind='policy',published_at='2025-01-01T10:00:00+00:00',public_verified=True,intensity_unit='ratio',direction='positive',industry_quality='archived',industry_id='same',market_state='up',pre20=.1,intensity=.1)
    target=base|dict(id='target',code='us:AAPL',market='us')
    other=base|dict(id='other',code='hk:00700',market='hk')
    result=match_event_cases(target,[other],'2026-11-16T00:00:00+00:00')
    assert result['excluded'].get('market')==1


def test_hk_closing_auction_prices_are_not_known_at_1605():
    from src.services.a_share_event_lifecycle import event_anchor_index
    days=['2026-11-12','2026-11-13','2026-11-16']
    assert event_anchor_index('2026-11-13T16:05:00+08:00',days,market='hk')==0
    assert event_anchor_index('2026-11-13T16:10:00+08:00',days,market='hk')==1
