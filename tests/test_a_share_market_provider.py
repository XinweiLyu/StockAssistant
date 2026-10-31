import pytest
from src.schemas.a_share import AssistantSettings


def test_eastmoney_has_real_open_and_correct_volume():
    from data_provider.a_share_market import normalize_history
    row=normalize_history([{'日期':'2026-10-09','开盘':10,'最高':12,'最低':9,'收盘':11,'成交量':25,'成交额':27000}], 'akshare/eastmoney')[0]
    assert row.open==10 and row.volume==2500 and row.amount==27000


def test_tencent_history_keeps_share_units_and_missing_amount():
    from data_provider.a_share_market import normalize_history
    row=normalize_history([dict(date='2026-10-09',open=10,high=12,low=9,close=11,volume=25)],'akshare/tencent')[0]
    assert row.volume==25 and row.amount is None


def test_unknown_units_and_duplicate_dates_are_not_accepted():
    from data_provider.a_share_market import normalize_history
    row=dict(date='2026-10-09',open=10,high=12,low=9,close=11,volume=25)
    with pytest.raises(ValueError):
        normalize_history([row,row],'akshare/tencent')
    with pytest.raises(ValueError):
        normalize_history([row],'unverified-source')


def test_exchange_listing_defines_identity_instead_of_a_code_guess():
    from data_provider.a_share_market import normalize_listing
    rows=normalize_listing([{'证券代码':'920001','证券简称':'目录样本','上市日期':'2020-01-02'}],'BSE','beijing','fixture')
    assert rows[0].identity_verified and rows[0].exchange=='BSE'
    assert rows[0].listed_date=='2020-01-02'


def test_tushare_adjusts_all_four_prices_with_the_last_factor():
    from data_provider.a_share_market import normalize_tushare_history
    raw=[dict(trade_date='20261008',open=10,high=12,low=9,close=11,vol=25,amount=50),
         dict(trade_date='20261009',open=11,high=13,low=10,close=12,vol=30,amount=60)]
    factors=[dict(trade_date='20261008',adj_factor=2),dict(trade_date='20261009',adj_factor=4)]
    row=normalize_tushare_history(raw,factors,'qfq')[0]
    assert (row.open,row.high,row.low,row.close)==(5,6,4.5,5.5)
    assert row.volume==2500 and row.amount==50000
    with pytest.raises(ValueError):
        normalize_tushare_history(raw,factors[:1],'qfq')


def test_board_ids_do_not_use_a_display_name():
    from data_provider.a_share_market import MarketProvider
    class Source:
        def call(self,name,params=None,**kwargs):
            return [{'板块名称':'同名','板块代码':'BK123','涨跌幅':2.5,'上涨家数':10,'下跌家数':2}]
    value=MarketProvider(Source(),AssistantSettings(mode='free')).sectors('industry')[0]
    assert value.sector_id=='em:industry:BK123' and value.change==.025


def test_sector_index_volume_is_unknown_until_its_unit_is_verified():
    from data_provider.a_share_market import MarketProvider
    class Source:
        def call(self,*args,**kwargs):
            return [{'日期':'2026-10-09','开盘':100,'最高':110,'最低':90,'收盘':105,'成交量':10}]
    sector=dict(sector_id='em:industry:BK1',code='BK1',kind='industry',source='akshare/eastmoney')
    value=MarketProvider(Source(),AssistantSettings(mode='free')).sector_history(sector,'2026-10-01','2026-10-09')
    assert value.items[0].volume is None


def test_benchmark_fetch_is_an_index_not_a_same_code_stock():
    from data_provider.a_share_market import MarketProvider
    class Source:
        def call(self,name,params=None,**kwargs):
            assert params['symbol']=='sh000300'
            return [dict(date='2026-10-09',open=100,high=110,low=90,close=105,volume=10)]
    value=MarketProvider(Source(),AssistantSettings(mode='free')).benchmark_history('2026-10-01','2026-10-09')
    assert value.code=='benchmark:000300' and value.items[0].close==105


def test_tencent_snapshot_uses_its_actual_zdf_percent_field():
    from data_provider.a_share_market import MarketProvider
    class Public:
        def call(self,name,*args,**kwargs):
            if name=='stock_zh_a_spot_em':raise RuntimeError('offline')
            return [dict(code='sh600519',name='贵州茅台',zxj='1288.00',zd='25.00',zdf='1.98',volume='31556.00',turnover='404286')]
    quote=MarketProvider(Public(),AssistantSettings(mode='free')).quotes()[0]
    assert quote.price==1288 and quote.change==pytest.approx(.0198)
    assert quote.amount is None and quote.volume is None


def test_history_preserves_reported_daily_change_without_deriving_raw_gap():
    from data_provider.a_share_market import MarketProvider
    class Public:
        def call(self,*args,**kwargs):
            return [{'日期':'2026-10-09','开盘':9,'最高':9,'最低':9,'收盘':9,'涨跌幅':0}]
    p=MarketProvider(Public(),AssistantSettings(mode='free'))
    assert p.history('000001','2026-10-09','2026-10-09','raw').latest_change==0
    assert p.history('000001','2026-10-09','2026-10-09','qfq').latest_change is None


def test_inconsistent_turnover_units_are_withheld_instead_of_wrong_share_count():
    from data_provider.a_share_market import normalize_history
    row=normalize_history([dict(date='2026-10-14',open=26.3,high=26.8,low=26.06,close=26.27,
                                volume=354489,amount=938670600)],'akshare/tencent')[0]
    assert row.volume is None and row.amount is None


def test_members_fall_back_to_same_board_f10_without_changing_classification():
    from data_provider.a_share_market import MarketProvider
    class Public:
        def call(self, name, params=None, **kwargs):
            if name == 'stock_board_concept_cons_em':
                raise RuntimeError('push2 unavailable')
            assert name == 'stock_board_members_f10_em'
            assert params == {'symbol': 'BK0800'}
            return [{'SECURITY_CODE': '000001', 'BOARD_CODE': '800'},
                    {'SECURITY_CODE': '600001', 'BOARD_CODE': '800'}]
    provider = MarketProvider(Public(), AssistantSettings(mode='free'))
    sector = dict(source='akshare/eastmoney', kind='concept', code='BK0800')
    assert provider.members(sector) == ['000001', '600001']
    assert provider.members_source == 'eastmoney/F10'
    assert sector['source'] == 'akshare/eastmoney'
