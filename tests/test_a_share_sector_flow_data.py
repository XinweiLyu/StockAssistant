from datetime import datetime,timezone
import pytest

NOW='2026-11-17T02:05:00+00:00'
SECTOR=dict(sector_id='em:industry:BK0478',kind='industry',classification='eastmoney-industry',code='BK0478',name='有色金属')


def test_rank_keeps_codes_raw_yuan_zero_missing_and_unknown_source_time():
    from data_provider.a_share_sector_flow import normalize_rank
    rows=normalize_rank([dict(f12='BK0478',f14='有色金属',f62=100000000,f66=0,f72='-',f184=2.5,f3=-.3)],'industry',NOW)
    r=rows[0]
    assert r['sector_id']=='em:industry:BK0478' and r['unit']=='CNY'
    assert r['values']['main']==100000000 and r['values']['super']==0 and r['values']['large'] is None
    assert r['ratios']['main']==.025 and r['change']==-.003
    assert r['source_time'] is None and r['source_date'] is None and r['session_day']=='2026-11-17'
    assert r['measure']=='cumulative_snapshot'


def test_history_is_daily_net_and_rejects_duplicate_future_or_wrong_board():
    from data_provider.a_share_sector_flow import normalize_history
    raw=['2026-11-16,100,-20,-80,0,100,1,-.2,-.8,0,1,4000,2']
    result=normalize_history(raw,SECTOR,NOW)
    assert result[0]['source_date']=='2026-11-16' and result[0]['measure']=='daily_net'
    assert result[0]['values']==dict(main=100.,small=-20.,medium=-80.,large=0.,super=100.)
    assert result[0]['close']==4000 and result[0]['change']==.02
    assert result[0]['observed_at']==NOW
    with pytest.raises(ValueError):normalize_history(raw+raw,SECTOR,NOW)
    with pytest.raises(ValueError):normalize_history(['2026-11-18'+raw[0][10:]],SECTOR,NOW)
    with pytest.raises(ValueError):normalize_history(raw,SECTOR|dict(sector_id='hk:industry:BK0478'),NOW)


def test_invalid_numbers_do_not_become_zero_or_untyped_infinity():
    from data_provider.a_share_sector_flow import normalize_rank
    rows=normalize_rank([dict(f12='BK0478',f14='有色金属',f62=float('nan'),f66=-10,f72=float('inf'))],'industry',NOW)
    assert rows[0]['values']['main'] is None and rows[0]['values']['super']==-10
    assert rows[0]['values']['large'] is None
    with pytest.raises(ValueError):normalize_rank([dict(f12='BK0000',f14='无有效资金')],'industry',NOW)


def test_members_require_a_share_stock_identity_and_keep_sector_binding():
    from data_provider.a_share_sector_flow import normalize_members
    rows=normalize_members([dict(f12='000807',f14='云铝股份',f62=25,f184=-1.2)],SECTOR,NOW)
    assert rows[0]['code']=='000807' and rows[0]['sector_id']==SECTOR['sector_id']
    assert rows[0]['ratios']['main']==-.012
    with pytest.raises(ValueError):normalize_members([dict(f12='hk:00700',f14='腾讯',f62=25)],SECTOR,NOW)

def test_rank_paginates_complete_source_and_rejects_duplicate_pages(monkeypatch):
 from data_provider import a_share_sector_flow as m
 calls=[]
 def source(path,params,**kwargs):
  calls.append(params['pn'])
  return dict(total=2,diff=[dict(f12='BK000'+str(params['pn']),f14='行业',f62=1)])
 monkeypatch.setattr(m,'_get',source)
 assert len(m.fetch_rank('industry'))==2 and calls==[1,2]
 monkeypatch.setattr(m,'_get',lambda *args,**kwargs:dict(total=2,diff=[dict(f12='BK0001')]))
 with pytest.raises(ValueError):m.fetch_rank('industry')

def test_rank_can_use_verified_same_provider_history_gateway(monkeypatch):
 from data_provider import a_share_sector_flow as m
 urls=[]
 class Response:
  def raise_for_status(self):pass
  def json(self):return dict(rc=0,data=dict(total=1,diff=[dict(f12='BK0478',f14='有色金属',f62=123)]))
 class Session:
  trust_env=True
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def get(self,url,**kwargs):
   urls.append(url)
   assert kwargs['allow_redirects'] is False and kwargs['timeout']<=7
   if url.startswith('https://push2his.eastmoney.com/'):return Response()
   raise m.requests.ConnectionError('route unavailable')
 monkeypatch.setattr(m.requests,'Session',Session)
 assert m.fetch_rank('industry')[0]['f62']==123
 assert len(urls)==3 and urls[-1].startswith('https://push2his.eastmoney.com/')
