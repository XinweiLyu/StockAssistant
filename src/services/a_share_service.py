"""DSA-integrated A-share research, provenance journal and bounded background jobs."""
from __future__ import annotations
from datetime import datetime, date, timedelta, time
import hashlib
import json
import logging
from math import sin
import threading
from functools import wraps
from zoneinfo import ZoneInfo

from data_provider.a_share import CapabilityProvider, permitted_sources, normalize_spot, normalize_tushare_quote, normalize_alternate_spot, number, daily_rows
from data_provider.base import normalize_stock_code
from src.repositories.a_share_repository import AssistantRepository
from src.schemas.a_share import AssistantSettings
from src.services.a_share_rules import (rank_universe, buy_plan, check_trigger, holding_risk,
                                       forward_observation, session_slot, indicators, validate_daily)

TZ=ZoneInfo('Asia/Shanghai')
logger=logging.getLogger(__name__)


def now_local():
    return datetime.now(TZ)


def ts_code(code):
    return code+('.SH' if code.startswith('6') else '.SZ' if code.startswith(('0','3')) else '.BJ')


def a_share_code(symbol):
    code=normalize_stock_code(symbol)
    return code if code.isdigit() and len(code)==6 else None


def holding_context(code,trades,corporate_actions):
    """Current holding cycle and ledger identity; an old flat position is not reused."""
    events=[]
    for row in trades:
        if a_share_code(row.symbol)==code and row.market=='cn' and row.currency=='CNY':
            events.append((row.trade_date,1,row.id,'trade',row))
    for row in corporate_actions:
        if a_share_code(row.symbol)==code and row.market=='cn' and row.currency=='CNY':
            events.append((row.effective_date,0,row.id,'corp',row))
    quantity=0.
    cycle=None
    started=None
    identity=[]
    for day,_,event_id,kind,row in sorted(events,key=lambda e:e[:3]):
        if kind=='trade':
            identity.append([str(day),event_id,row.side,row.quantity])
            if row.side=='buy':
                if quantity<=1e-8:
                    cycle=f'{day}:{event_id}'
                    started=day.isoformat()
                quantity+=row.quantity
            else:
                quantity=max(0.,quantity-row.quantity)
                if quantity<=1e-8:
                    cycle=None
                    started=None
        elif row.action_type=='split_adjustment':
            identity.append([str(day),event_id,'split',row.split_ratio])
            quantity*=row.split_ratio
            if cycle:
                cycle+=f':split:{event_id}:{row.split_ratio}'
    revision=hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return dict(cycle=cycle,ledger_revision=revision,started=started)


def settings_locked(fn):
    @wraps(fn)
    def run(self,*args,**kwargs):
        with self._settings_lock:
            return fn(self,*args,**kwargs)
    return run


def stable_input(value):
    if isinstance(value,dict):
        return {k:stable_input(v) for k,v in value.items() if k not in ('fetched_at','generated_at','checked_at')}
    if isinstance(value,list):
        return [stable_input(v) for v in value]
    return value


def settings_from_saved(payload):
    if payload is None:
        return AssistantSettings()
    return AssistantSettings.model_validate({'research_scope':'limited', **payload})


class AssistantService:
    def __init__(self, repo=None):
        self.repo=repo or AssistantRepository()
        self.settings=settings_from_saved(self.repo.latest('live','settings'))
        self.provider=None
        self._lock=threading.Lock()
        self._settings_lock=threading.RLock()
        self._stop=threading.Event()
        self._slots={}
        self.job=dict(state='idle',completed=0,total=0,errors=[],message='待同步')
        self._thread=None
        self._research_codes=set()
        self._research_lock=threading.Lock()
        from src.repositories.a_share_market_repository import MarketRepository
        from src.services.a_share_market_jobs import MarketJobs
        from src.services.a_share_market_service import MarketService
        self.market_jobs=MarketJobs(MarketRepository(self.repo.engine),lambda task:self.market.handle_task(task),profile=self.settings.mode,exclude_kinds=['research_data'])
        self.market=MarketService(self,self.market_jobs.repo,self.market_jobs)
        from src.services.a_share_integrated_service import IntegratedResearchService
        self.integrated=IntegratedResearchService(self)

    def save_settings(self, settings):
        if 'research_scope' not in settings.model_fields_set:
            settings=settings.model_copy(update={'research_scope':self.settings.research_scope})
        if not self._lock.acquire(blocking=False):
            raise ValueError('同步任务运行中，请完成后切换方案')
        try:
            with self._settings_lock:
                if settings.account_id is not None:
                    from src.services.portfolio_service import PortfolioService
                    valid=next((a for a in PortfolioService().list_accounts() if a['id']==settings.account_id and a['market']=='cn' and a['base_currency']=='CNY'),None)
                    if valid is None:
                        raise ValueError('请选择有效的人民币A股账户')
                self.repo.append('live','settings','current',settings.model_dump())
                self.settings=settings
                self.provider=None
                self.market_jobs.set_profile(settings.mode)
                self.integrated.jobs.set_profile(settings.mode)
                self.check()  # Account/risk changes invalidate the old displayed plan immediately.
            return settings.model_dump()
        finally:
            self._lock.release()

    def _provider(self):
        from src.config import get_config
        token=get_config().tushare_token or ''
        if self.provider is None or self.provider.token!=token:
            self.provider=CapabilityProvider(token)
        return self.provider

    def _fetch(self, kind, name, params=None, paid_name=None, paid_params=None):
        source=permitted_sources(self.settings).get(kind,'akshare')
        try:
            if source=='tushare' and paid_name:
                value=self._provider().call(paid_name,paid_params or params,tushare=True)
            else:
                source='akshare'
                value=self._provider().call(name,params)
            self.repo.append(self.settings.mode,'health',kind,dict(kind=kind,source=source,status='ok',
                             fetched_at=now_local().isoformat(),count=len(value)))
            return value,source
        except (ValueError,RuntimeError) as exc:
            self.repo.append(self.settings.mode,'health',kind,dict(kind=kind,source=source,status='failed',
                             fetched_at=now_local().isoformat(),error=str(exc)))
            if self.settings.free_fallback:
                fallbacks=[(name,params,'akshare')] if source=='tushare' else []
                if name=='stock_zh_index_daily_em':
                    fallbacks += [('stock_zh_a_hist_tx',dict(symbol=params['symbol'],start_date=params['start_date'],end_date=params['end_date'],adjust='',timeout=25),'akshare/tencent')]
                if name=='stock_zh_a_spot_em':
                    fallbacks += [('stock_zh_a_spot_tx',{},'akshare/tencent'),('stock_zh_a_spot',{},'akshare/sina')]
                for fallback_name,fallback_params,fallback_source in fallbacks:
                    try:
                        value=self._provider().call(fallback_name,fallback_params)
                        self.repo.append(self.settings.mode,'health',kind,dict(kind=kind,source=fallback_source,status='fallback',
                                         fetched_at=now_local().isoformat(),reason=str(exc),count=len(value)))
                        return value,fallback_source
                    except (ValueError,RuntimeError):
                        continue

            raise

    def sync_async(self, kind='daily'):
        if self.settings.mode!='demo' and self.settings.research_scope=='all' and kind in ('daily','snapshot'):
            if kind=='daily':
                self.market.warmup()
            else:
                self.market.snapshot(now_local().strftime('%Y-%m-%dT%H:%M'))
            return True
        if not self._lock.acquire(blocking=False):
            return False
        self.job=dict(state='running',kind=kind,completed=0,total=0,errors=[],message='正在准备')
        thread=threading.Thread(target=self._sync_locked,args=(kind,),daemon=True,name='a-share-'+kind)
        thread.start()
        return True

    def sync(self, kind='daily'):
        if self.settings.mode!='demo' and self.settings.research_scope=='all' and kind=='daily':
            return self.market.warmup()
        if not self._lock.acquire(blocking=False):
            raise ValueError('已有同步任务')
        return self._sync_locked(kind)

    def _sync_locked(self, kind):
        self.job=dict(state='running',kind=kind,completed=0,total=0,errors=[],message='正在准备')
        try:
            if self.settings.mode=='demo':
                self._demo()
            elif kind=='daily':
                self._daily()
            elif kind=='snapshot':
                self._quotes()
            elif kind=='news':
                self._news()
            elif kind=='market_news':
                self._news(scope='market')
            else:
                raise ValueError('未知任务类型')
            self.check()
            self.job['state']='complete'
            self.job['message']='同步完成；缺失项见数据状态'
        except Exception as exc:
            logger.warning('A-share task %s failed: %s',kind,type(exc).__name__)
            self.job['state']='failed'
            self.job['errors'].append(str(exc)[:300])
            self.job['message']='同步未完成，保留原始缓存时间'
        finally:
            try:
                self.repo.append(self.settings.mode,'job',kind,self.job.copy())
            finally:
                self._lock.release()
        return self.job.copy()

    def build_market_report(self,profile,warmup):
        from src.services.a_share_market_research import MarketResearch
        with self._settings_lock:
            return MarketResearch(self).build(profile,warmup)

    def stock_data(self,code,profile=None):
        profile=profile or self.settings.mode
        data=self.repo.latest(profile,'dataset',default={})
        value=next((s for s in data.get('stocks',[]) if s['code']==code),None)
        if value:
            return value
        from src.services.a_share_market_research import MarketResearch
        return MarketResearch(self).stock(profile,code,data.get('as_of')) or self.repo.latest(profile,'stock_data',key=code)

    def market_quotes_updated(self,profile,quotes):
        with self._settings_lock:
            if profile!=self.settings.mode:
                return
            report=self.repo.latest(profile,'report',default={})
            codes={c['code'] for c in report.get('candidates',[])}|set(self.settings.watchlist)
            codes|={p['code'] for p in self.portfolio()['positions']}
            focused={c:q for c,q in quotes.items() if c in codes}
            for code,q in focused.items():
                self.repo.append(profile,'quote',code,q)
            self.repo.append(profile,'quotes','current',dict(quotes=focused,fetched_at=now_local().isoformat(),source='market-cache'))
            self.check()

    def _demo(self):
        # Fictional companies and a synthetic calendar cannot contaminate live research.
        cutoff=date(2026,9,30)
        days=[(cutoff-timedelta(days=i)).isoformat() for i in range(280,-1,-1)
              if (cutoff-timedelta(days=i)).weekday()<5][-180:]
        def make_bars(index):
            rows=[]
            for i,d in enumerate(days):
                p=10+index*.15+i*(.006+index*.0007)+.12*sin(i/(3+index%4))
                rows.append(dict(date=d,close=round(p,4),high=round(p+.35,4),low=round(p-.35,4),
                                 adjusted_close=round(p,4),amount=80_000_000+index*2_000_000,volume=1_000_000))
            return rows
        stocks=[dict(code=f'DEMO{i:03d}',name=f'演示公司{i:02d}',sector=f'DS{i%12:02d}',
                     listed_sessions=300,st=False,suspended=False,bars=make_bars(i),source='synthetic') for i in range(40)]
        sectors=[dict(code=f'DS{i:02d}',name=f'演示行业{i:02d}',classification='demo',bars=make_bars(i*3)) for i in range(12)]
        data=dict(as_of=cutoff.isoformat(),calendar=days+['2026-10-09','2026-10-12'],stocks=stocks,
                  sectors=sectors,benchmark=make_bars(20),source='synthetic',demo=True)
        self.repo.append('demo','dataset','current',data)
        self.repo.add_event('demo',dict(source='演示公告',title='演示公司39发布业绩预告',code='DEMO039',
                                      content='这是虚构资料，用于验证证据、修订与人工核实流程。',url=None,
                                      published_at='2026-09-30',precision='date',coverage='示例'))
        self._build_report(data)
        self.job.update(completed=40,total=40)

    def _calendar(self):
        previous=self.repo.latest(self.settings.mode,'calendar',default={})
        today=now_local().date().isoformat()
        if previous.get('fetched_date')==today and max(previous.get('dates') or [''])>today:
            return previous['dates']
        rows,source=self._fetch('daily','tool_trade_date_hist_sina',paid_name='trade_cal',
                               paid_params=dict(exchange='SSE',start_date=(date.today()-timedelta(days=600)).strftime('%Y%m%d'),
                                                end_date=(date.today()+timedelta(days=90)).strftime('%Y%m%d'),is_open='1'))
        dates=[]
        for r in rows:
            d=str(r.get('trade_date',r.get('cal_date','')))[:10]
            if len(d)==8:
                d=f'{d[:4]}-{d[4:6]}-{d[6:8]}'
            if len(d)==10:
                dates.append(d)
        dates=sorted(set(dates))
        if not dates or max(dates)<today:
            raise ValueError('交易日历未覆盖当前日期，暂停新建议')
        self.repo.append(self.settings.mode,'calendar','current',dict(dates=dates,source=source,fetched_date=today))
        return dates

    def _daily(self):
        calendar=self._calendar()
        now=now_local()
        completed=[d for d in calendar if d<now.date().isoformat() or
                   (d==now.date().isoformat() and now.time().replace(tzinfo=None)>=time(18,40))]
        if not completed:
            raise ValueError('尚无完整交易日')
        as_of=completed[-1]
        start=(date.fromisoformat(as_of)-timedelta(days=500)).strftime('%Y%m%d')
        end=as_of.replace('-','')
        # Persist a close-based seed pool; an intraday snapshot never substitutes yesterday's turnover.
        seed=self.repo.latest(self.settings.mode,'universe',key=as_of)
        if seed is None:
            if permitted_sources(self.settings)['daily']=='tushare':
                try:
                    raw=self._provider().call('daily',dict(trade_date=end),tushare=True)
                    seed=[dict(code=r['ts_code'][:6],amount=number(r['amount'])*1000) for r in raw]
                except (ValueError,RuntimeError):
                    seed=None
            if seed is None:
                raw,seed_source=self._fetch('snapshot','stock_zh_a_spot_em')
                normalized=[normalize_spot(r,now.isoformat()) if seed_source=='akshare' else normalize_alternate_spot(r,now.isoformat(),seed_source) for r in raw]
                seed=[dict(code=r['code'],name=r.get('name'),amount=r.get('amount') or r.get('download_sort_value') or 0) for r in normalized]
                self.job['errors'].append('免费下载种子来自当前行情截面；源时间未知，不保证全市场上个交易日成交额前N名')
            seed=sorted([s for s in seed if s['code'].startswith(('600','601','603','605','000','001','002'))],
                        key=lambda s:-s['amount'])[:self.settings.pool_size]
            if seed:
                self.repo.append(self.settings.mode,'universe',as_of,seed)
        portfolio=self.portfolio()
        research_codes=list(dict.fromkeys([p['code'] for p in portfolio['positions']]+self.settings.watchlist+[r['code'] for r in seed]))
        pending=self._pending_observation_codes(calendar,as_of)
        codes=list(dict.fromkeys(research_codes+pending))
        stocks=[]
        self.job['total']=len(codes)
        for code in codes:
            if self._stop.is_set():
                raise ValueError('服务停止，同步已中断')
            self.job['message']='同步日线 '+code
            cached=self.repo.latest(self.settings.mode,'stock_data',key=code)
            if cached and cached['as_of']==as_of and cached.get('profile')==self.settings.mode:
                try:
                    validate_daily(cached['bars'],calendar,as_of)
                    stocks.append(cached|{'research_member':code in research_codes})
                    self.job['completed']+=1
                    continue
                except (ValueError,KeyError,TypeError):
                    pass  # A requested date label is not proof that prices are complete.
            try:
                history,source,adjustment=self._history(code,start,end,calendar)
                validate_daily(history,calendar,as_of)
                metadata=self._metadata(code,seed,calendar,as_of)
                name=str(metadata.get('股票简称',''))
                listed=str(metadata.get('上市时间',''))[:8]
                listed_day=f'{listed[:4]}-{listed[4:6]}-{listed[6:8]}' if len(listed)==8 else None
                stock=dict(code=code,name=name,sector=metadata.get('行业'),
                           listed_sessions=sum(listed_day<=d<=as_of for d in calendar) if listed_day else 0,
                           st=('ST' in name.upper() or '退' in name) if name else None,
                           suspended=False if history and history[-1]['date']==as_of else None,
                           bars=history,as_of=as_of,source=source,profile=self.settings.mode,
                           adjustment=adjustment,research_member=code in research_codes,fetched_at=now_local().isoformat())
                self.repo.append(self.settings.mode,'stock_data',code,stock)
                stocks.append(stock)
            except (ValueError,RuntimeError,KeyError,TypeError) as exc:
                self.job['errors'].append(code+': '+str(exc)[:120])
            self.job['completed']+=1
        sectors=[]
        for sector_name in sorted({s['sector'] for s in stocks if s.get('sector')}):
            try:
                cached=self.repo.latest(self.settings.mode,'sector_data',key=sector_name)
                if cached and cached['as_of']==as_of:
                    try:
                        validate_daily(cached['bars'],calendar,as_of,require_amount=False)
                        sectors.append(cached)
                        continue
                    except (ValueError,KeyError,TypeError):
                        pass
                rows,_=self._fetch('sector','stock_board_industry_hist_em',
                                   dict(symbol=sector_name,start_date=start,end_date=end,adjust=''))
                value=dict(code=sector_name,name=sector_name,classification='eastmoney-industry',
                           bars=daily_rows(rows),as_of=as_of,source='akshare/eastmoney')
                validate_daily(value['bars'],calendar,as_of,require_amount=False)
                self.repo.append(self.settings.mode,'sector_data',sector_name,value)
                sectors.append(value)
            except (ValueError,RuntimeError,KeyError) as exc:
                self.job['errors'].append('行业 '+sector_name+': '+str(exc)[:100])
        rows,_=self._fetch('sector','stock_zh_index_daily_em',dict(symbol='sh000300',start_date=start,end_date=end))
        benchmark=daily_rows(rows)
        try:
            validate_daily(benchmark,calendar,as_of,require_amount=False)
        except (ValueError,KeyError,TypeError) as exc:
            self.job['errors'].append('沪深300: '+str(exc))
        data=dict(as_of=as_of,calendar=calendar,stocks=stocks,sectors=sectors,benchmark=benchmark,
                  daily_complete=len(stocks)==len(codes) and not self.job['errors'],
                  demo=False,source='capability-adapters',fetched_at=now_local().isoformat())
        self.repo.append(self.settings.mode,'dataset','current',data)
        self._build_report(data)
        if self.settings.mode.startswith('tushare'):
            for stock in stocks:
                try:
                    raw=self._provider().call('daily_basic',dict(ts_code=ts_code(stock['code']),trade_date=end),tushare=True)
                    self.repo.append(self.settings.mode,'fundamentals',stock['code'],dict(as_of=as_of,rows=raw,source='tushare/daily_basic',
                                     limitation='估值快照，不等于完整财务报表'))
                except (ValueError,RuntimeError):
                    break

    def _history(self,code,start,end,calendar=None):
        source=permitted_sources(self.settings)['daily']
        if source=='tushare':
            try:
                rows=self._provider().call('daily',dict(ts_code=ts_code(code),start_date=start,end_date=end),tushare=True)
                factors=self._provider().call('adj_factor',dict(ts_code=ts_code(code),start_date=start,end_date=end),tushare=True)
                fm={r['trade_date']:r.get('adj_factor') for r in factors}
                history=daily_rows([r|{'adj_factor':fm.get(r['trade_date'])} for r in rows],tushare=True)
                if not history:
                    raise ValueError('日线为空')
                if calendar:
                    validate_daily(history,calendar,f'{end[:4]}-{end[4:6]}-{end[6:8]}')
                return history,'tushare','adj_factor'
            except (ValueError,RuntimeError) as exc:
                self.repo.append(self.settings.mode,'health','daily',dict(kind='daily',source='tushare',status='failed',error=str(exc),fetched_at=now_local().isoformat()))
                if not self.settings.free_fallback:
                    raise
        symbol=('sh' if code.startswith('6') else 'sz' if code.startswith(('0','3')) else 'bj')+code
        sources=[('stock_zh_a_hist',dict(symbol=code,start_date=start,end_date=end),'akshare/eastmoney')]
        if self.settings.free_fallback:
            sources += [('stock_zh_a_daily',dict(symbol=symbol,start_date=start,end_date=end),'akshare/sina'),
                        ('stock_zh_a_hist_tx',dict(symbol=symbol,start_date=start,end_date=end,timeout=25),'akshare/tencent')]
        errors=[]
        for name,params,label in sources:
            try:
                raw=self._provider().call(name,params|dict(adjust=''))
                adjusted=self._provider().call(name,params|dict(adjust='qfq'))
                history=daily_rows(raw,adjusted)
                if not history:
                    raise ValueError('日线为空')
                if calendar:
                    validate_daily(history,calendar,f'{end[:4]}-{end[4:6]}-{end[6:8]}')
                self.repo.append(self.settings.mode,'health','daily',dict(kind='daily',source=label,status='ok' if not errors else 'fallback',reason='; '.join(errors),fetched_at=now_local().isoformat()))
                return history,label,'qfq'
            except (ValueError,RuntimeError,KeyError) as exc:
                errors.append(label+': '+str(exc)[:100])
        raise ValueError('日线及同源复权均不可用：'+'; '.join(errors))

    def _metadata(self,code,seed,calendar,as_of):
        cached=self.repo.latest(self.settings.mode,'metadata',key=code)
        if cached and (now_local().date()-date.fromisoformat(cached['fetched_date'])).days<7:
            return cached['value']
        try:
            info=self._provider().call('stock_individual_info_em',dict(symbol=code,timeout=20))
            value={r['item']:r['value'] for r in info}
            self.repo.append(self.settings.mode,'metadata',code,dict(value=value,fetched_date=now_local().date().isoformat(),source='eastmoney'))
            return value
        except (ValueError,RuntimeError):
            if not self.settings.free_fallback:
                raise
        board='sh' if code.startswith('6') else 'sz'
        listings=self.repo.latest(self.settings.mode,'listings',key=board)
        if listings is None:
            name='stock_info_sh_name_code' if board=='sh' else 'stock_info_sz_name_code'
            listings=self._provider().call(name,dict(symbol='主板A股' if board=='sh' else 'A股列表'))
            self.repo.append(self.settings.mode,'listings',board,listings)
        for row in listings:
            row_code=str(row.get('证券代码',row.get('A股代码',''))).zfill(6)
            if row_code==code:
                listing_date=str(row.get('上市日期',row.get('A股上市日期','')))[:10].replace('-','')
                name=row.get('证券简称',row.get('A股简称'))
                # Official listing classifications are not merged into Eastmoney sectors.
                return {'股票简称':name,'上市时间':listing_date,'行业':None}
        raise ValueError('证券身份与上市日期未核实')

    def _build_report(self, data):
        result=rank_universe([s for s in data['stocks'] if s.get('research_member',True)],data['sectors'],data['benchmark'],data['as_of'],data['demo'],calendar=data['calendar'])
        future=[d for d in data['calendar'] if d>data['as_of']]
        for c in result['candidates']:
            c['valid_date']=future[0] if future else None
            c['holding_horizon']='5–20交易日'
        evidence=self.repo.records(self.settings.mode,'event',limit=100)
        result.update(evidence=evidence,evidence_as_of=now_local().isoformat(),as_of=data['as_of'],generated_at=now_local().isoformat(),demo=data['demo'],
                      input_hash=hashlib.sha256(json.dumps(stable_input(data),sort_keys=True).encode()).hexdigest(),
                      config=self.settings.model_dump(),strategy_versions=['trend_v1','sector_trend_v1'],
                      source=data['source'],limitations=result['limitations']+['趋势基线尚未证明盈利优势；排名得分不是上涨概率',
                      '资讯覆盖可能不完整；未发现资讯不表示没有风险'])
        previous=self.repo.latest(self.settings.mode,'report')
        if previous and previous['input_hash']==result['input_hash'] and previous['config']==result['config'] and previous.get('evidence')==result['evidence']:
            return previous
        report_id=self.repo.append(self.settings.mode,'report',data['as_of'],result)
        self.repo.append(self.settings.mode,'alert','report',dict(message='新的盘后研究已生成',report_id=report_id,
                         timestamp=now_local().isoformat(),demo=data['demo']))
        return result

    def _quotes(self):
        data=self.repo.latest(self.settings.mode,'dataset',default={})
        codes={s['code'] for s in data.get('stocks',[])}|set(self.settings.watchlist)
        if self.settings.research_scope=='all':
            codes|={c['code'] for c in self.repo.latest(self.settings.mode,'report',default={}).get('candidates',[])}
            codes|={p['code'] for p in self.portfolio()['positions']}
        fetched=now_local().isoformat()
        rows,source=self._fetch('snapshot','stock_zh_a_spot_em',paid_name='rt_k',
                               paid_params=dict(ts_code=','.join(ts_code(c) for c in sorted(codes)),
                                                fields='ts_code,name,close,vol,amount,trade_time'))
        limits={}
        suspended=None
        if source=='tushare':
            try:
                trade_date=now_local().strftime('%Y%m%d')
                limits={r['ts_code'][:6]:r for r in self._provider().call('stk_limit',dict(trade_date=trade_date),tushare=True) if r.get('trade_date')==trade_date}
                suspension_rows=self._provider().call('suspend_d',dict(trade_date=trade_date),tushare=True)
                suspended={r['ts_code'][:6] for r in suspension_rows if r.get('suspend_type')=='S'}
            except (ValueError,RuntimeError,KeyError) as exc:
                self.job['errors'].append('交易状态与涨跌停权限/资料缺失：'+str(exc)[:100])
        quotes={}
        for r in rows:
            if source=='akshare':
                q=normalize_spot(r,fetched)
            elif source.startswith('akshare/'):
                q=normalize_alternate_spot(r,fetched,source)
            else:
                q=normalize_tushare_quote(r,fetched)
                if q['code'] in limits and suspended is not None:
                    q.update(limit_up=number(limits[q['code']].get('up_limit')),limit_down=number(limits[q['code']].get('down_limit')),
                             suspended=q['code'] in suspended)
                if not q.get('name') or 'ST' in str(q['name']).upper() or '退' in str(q['name']):
                    q['suspended']=None  # Current identity/risk state must be verified.
            if q['code'] in codes:
                previous=self.repo.latest(self.settings.mode,'quote',key=q['code'])
                q['cumulative_regressed']=bool(previous and q.get('trade_date') and previous.get('trade_date')==q['trade_date']
                                               and previous.get('amount') is not None and q.get('amount') is not None
                                               and q['amount']<previous['amount'])
                self.repo.append(self.settings.mode,'quote',q['code'],q)
                quotes[q['code']]=q
        self.repo.append(self.settings.mode,'quotes','current',dict(quotes=quotes,fetched_at=fetched,source=source))
        self.job.update(completed=len(quotes),total=len(codes))

    def _news(self,scope='all'):
        today=now_local().date()
        rows,source=self._fetch('news','stock_info_global_em',paid_name='news',
                               paid_params=dict(src='sina',start_date=(today-timedelta(days=1)).isoformat()+' 00:00:00',
                                                end_date=now_local().strftime('%Y-%m-%d %H:%M:%S')))
        for r in rows:
            self._event(dict(source=source+'/market-news',title=r.get('标题',r.get('title','')),
                             content=r.get('摘要',r.get('content','')),published_at=r.get('发布时间',r.get('datetime')),
                             url=r.get('链接'),code=None,precision='second',coverage='摘要'))
        if scope=='market':
            return
        for d in [today-timedelta(days=1),today]:
            try:
                rows,source=self._fetch('announcements','stock_notice_report',dict(date=d.strftime('%Y%m%d')),
                                       paid_name='anns_d',paid_params=dict(ann_date=d.strftime('%Y%m%d')))
                for r in rows:
                    self._event(dict(source=source+'/announcements',title=r.get('公告标题',r.get('title','')),
                                     content='',published_at=str(r.get('公告日期',r.get('ann_date',d.isoformat())))[:10],
                                     url=r.get('网址',r.get('url')),code=str(r.get('代码',r.get('ts_code','')))[:6],
                                     precision='date',coverage='公告列表；未获取全文'))
            except (ValueError,RuntimeError) as exc:
                self.job['errors'].append('公告: '+str(exc))
        report=self.repo.latest(self.settings.mode,'report',default={})
        codes=list(dict.fromkeys([p['code'] for p in self.portfolio()['positions']]+
                                [c['code'] for c in report.get('candidates',[])]+self.settings.watchlist))[:50]
        self.job['total']=len(codes)
        for code in codes:
            if self._stop.is_set():
                break
            try:
                rows=self._provider().call('stock_news_em',dict(symbol=code))
                for r in rows:
                    self._event(dict(source=str(r.get('文章来源','akshare'))+'/stock-news',
                                     title=r.get('新闻标题',''),content=r.get('新闻内容',''),
                                     published_at=r.get('发布时间'),url=r.get('新闻链接'),code=None,
                                     related_code=code,precision='second',coverage='搜索结果，关联主体需人工核实'))
            except (ValueError,RuntimeError) as exc:
                self.job['errors'].append(code+' 新闻: '+str(exc)[:100])
            self.job['completed']+=1

    def _event(self, event):
        event=event|dict(title=str(event.get('title') or ''),content=str(event.get('content') or ''))
        title=event['title']
        event['tags']=[word for word in ('立案','退市','减持','业绩','回购','亏损','诉讼') if word in title]
        event['tags_status']='关键词待核实'
        if title:
            self.repo.add_event(self.settings.mode,event)

    @settings_locked
    def major_risks(self):
        latest={}
        results={}
        event_keys={r['id']:r['key'] for r in self.repo.records(self.settings.mode,'event',limit=10000)}
        for r in self.repo.records(self.settings.mode,'verification',limit=10000):
            value=r['payload']
            logical_key=event_keys.get(value['event_id'],str(value['event_id']))
            latest.setdefault(logical_key,value)
        for value in latest.values():
            results[value['code']]=results.get(value['code'],False) or value['major_risk']
        return results

    @settings_locked
    def verify_event(self, event_id, value):
        events=self.repo.records(self.settings.mode,'event',limit=10000)
        if not any(e['id']==event_id for e in events):
            raise ValueError('当前模式下找不到该事件')
        self.repo.append(self.settings.mode,'verification',str(event_id),value|dict(event_id=event_id,verified_at=now_local().isoformat()))

    @settings_locked
    def confirm_holding(self, value):
        if self.settings.mode=='demo':
            key=value['code']
            context={}
        else:
            if not self.settings.account_id:
                raise ValueError('请先选择人民币A股账户，再确认持仓约束')
            position=next((p for p in self.portfolio()['positions'] if p['code']==value['code']),None)
            if not position or not position.get('cycle'):
                raise ValueError('当前账户没有该持仓或持仓来源不完整')
            if value.get('sellable') is not None and value['sellable']>position['quantity']:
                raise ValueError('可卖数量不能超过当前账户持股数量')
            key=f"account:{self.settings.account_id}:{value['code']}"
            context={k:position[k] for k in ('cycle','ledger_revision')}
            context['account_id']=self.settings.account_id
        self.repo.append(self.settings.mode,'holding_constraint',key,value|context|dict(confirmed_at=now_local().isoformat()))

    @settings_locked
    def portfolio(self):
        if self.settings.mode=='demo':
            result=dict(nav=100000.,cash=70000.,total_value=30000.,complete=True,demo=True,
                        positions=[dict(code='DEMO039',quantity=1000,sector='DS03',market_value=18000,avg_cost=16.,sellable=800,
                                        stop=16.,held_sessions=12),dict(code='DEMO026',quantity=800,sector='DS02',market_value=12000,
                                        avg_cost=15.,sellable=None,stop=13.,held_sessions=21)])
            for p in result['positions']:
                constraint=self.repo.latest('demo','holding_constraint',key=p['code'],default={})
                if constraint:
                    p['stop']=constraint.get('stop')
                    p['sellable']=constraint.get('sellable') if constraint['confirmed_at'][:10]==now_local().date().isoformat() else None
            return result
        if not self.settings.account_id:
            return dict(nav=None,cash=None,total_value=None,complete=False,demo=False,positions=[],
                        limitations=['在持仓页建立账户并选择账户ID，方可计算计划股数'])
        from src.services.portfolio_service import PortfolioService
        portfolio_service=PortfolioService()
        try:
            snapshot=portfolio_service.get_portfolio_snapshot(account_id=self.settings.account_id,include_realtime=False,read_only=True)
        except ValueError as exc:
            return dict(nav=None,cash=None,total_value=None,complete=False,demo=False,positions=[],limitations=[str(exc)])
        positions=[]
        data=self.repo.latest(self.settings.mode,'dataset',default={})
        stock_map={s['code']:s for s in data.get('stocks',[])}
        total=0.
        complete=bool(snapshot['accounts']) and not snapshot.get('fx_stale',False)
        trades=portfolio_service.repo.list_trades(self.settings.account_id,now_local().date())
        corporate_actions=portfolio_service.repo.list_corporate_actions(self.settings.account_id,now_local().date())
        for a in snapshot['accounts']:
            if a['base_currency']!='CNY' or a['market']!='cn':
                complete=False
            for p in a['positions']:
                code=a_share_code(p['symbol'])
                if not code:
                    complete=False
                    continue
                stock=stock_map.get(code) or self.stock_data(code) or {}
                close=stock.get('bars',[{}])[-1].get('close') if stock.get('bars') else None
                value=p['quantity']*close if close else p['market_value_base']
                total+=value
                context=holding_context(code,trades,corporate_actions)
                constraint=self.repo.latest(self.settings.mode,'holding_constraint',key=f'account:{self.settings.account_id}:{code}',default={})
                if not context['cycle'] or constraint.get('cycle')!=context['cycle']:
                    constraint={}
                # A manual sellable confirmation expires daily. Stops persist until explicitly reconfirmed.
                current=(constraint.get('confirmed_at','')[:10]==now_local().date().isoformat()
                         and constraint.get('ledger_revision')==context['ledger_revision'])
                item=dict(code=code,quantity=p['quantity'],avg_cost=p['avg_cost'],market_value=value,
                          sector=stock.get('sector'),sellable=constraint.get('sellable') if current else None,
                          stop=constraint.get('stop'),**context)
                if context['started']:
                    item['held_sessions']=sum(context['started']<d<=now_local().date().isoformat() for d in data.get('calendar',[]))
                q=self.repo.latest(self.settings.mode,'quote',key=code,default={})
                from src.services.a_share_rules import quote_issues
                if not quote_issues(q,now_local()):
                    item['market_value']=p['quantity']*q['price']
                    total+=item['market_value']-value
                else:
                    complete=False
                if stock.get('as_of')!=data.get('as_of') or not close or not item['sector']:
                    complete=False
                positions.append(item)
        return dict(nav=snapshot['total_cash']+total,cash=snapshot['total_cash'],total_value=total,
                    complete=complete,demo=False,positions=positions,limitations=snapshot['limitations'],
                    realized_pnl=snapshot['realized_pnl'],fees=snapshot['fee_total'],tax=snapshot['tax_total'])

    @staticmethod
    def _account_for(portfolio,candidate):
        return {k:portfolio.get(k) for k in ('nav','cash','total_value','complete')} | dict(
            stock_value=sum(p['market_value'] for p in portfolio['positions'] if p['code']==candidate['code']),
            sector_value=sum(p['market_value'] for p in portfolio['positions'] if p.get('sector')==candidate.get('sector')))

    @settings_locked
    def check(self, now=None):
        now=now or now_local()
        report=self.repo.latest(self.settings.mode,'report')
        if not report:
            return dict(candidates=[],holdings=[])
        data=self.repo.latest(self.settings.mode,'dataset',default={})
        portfolio=self.portfolio()
        risks=self.major_risks()
        quotes=self.repo.latest(self.settings.mode,'quotes',default={}).get('quotes',{})
        previous=self.repo.latest(self.settings.mode,'check',default={})
        previous_states={c['code']+c['strategy']:c['check']['status'] for c in previous.get('candidates',[])}
        candidates=[]
        for c in report['candidates']:
            item=c|{'major_risk':risks.get(c['code'],False)}
            account=self._account_for(portfolio,c)
            check=check_trigger(item,quotes.get(c['code'],{}),account,now,data.get('calendar',[]),self.settings.risk.model_dump())
            plan=check.get('plan') or buy_plan(item,account,self.settings.risk.model_dump())
            candidate=item|dict(check=check,plan=plan)
            candidates.append(candidate)
            key=c['code']+c['strategy']
            if previous_states.get(key)!=check['status'] and check['status'] in ('triggered','blocked','expired'):
                self.repo.append(self.settings.mode,'alert',key,dict(code=c['code'],strategy=c['strategy'],
                                 message=check['status'],reasons=check['reasons'],timestamp=now.isoformat(),demo=report['demo']))
        holdings=[]
        for p in portfolio['positions']:
            c=p|dict(major_risk=risks.get(p['code'],False),overexposed=bool(portfolio.get('nav') and
                     (p['market_value']/portfolio['nav']>self.settings.risk.stock_cap or
                      sum(h['market_value'] for h in portfolio['positions'] if h.get('sector')==p.get('sector'))/portfolio['nav']>self.settings.risk.sector_cap or
                      portfolio['total_value']/portfolio['nav']>self.settings.risk.total_cap)))
            stock=self.stock_data(p['code'])
            if stock:
                try:
                    m=indicators(stock['bars'],data['as_of'])
                    c.update(daily_close=m['close'],sma20=m['sma20'],sma60=m['sma60'])
                except ValueError:
                    pass
            q=quotes.get(p['code'],{})
            risk=holding_risk(c,q,now,data.get('calendar',[]))|{'quantity':p['quantity']}
            holdings.append(risk)
            prev=next((h for h in previous.get('holdings',[]) if h['code']==risk['code']),None)
            if (not prev or prev['action']!=risk['action']) and risk['action']!='持有观察':
                self.repo.append(self.settings.mode,'alert','holding:'+risk['code'],dict(code=risk['code'],message=risk['action'],reasons=risk['reasons'],timestamp=now.isoformat(),demo=report['demo']))
        result=dict(candidates=candidates,holdings=holdings,checked_at=now.isoformat(),demo=report['demo'],report_hash=report['input_hash'])
        if stable_input(previous)!=stable_input(result):
            self.repo.append(self.settings.mode,'check','current',result)
        return result

    @settings_locked
    def dashboard(self):
        mode=self.settings.mode
        data=self.repo.latest(mode,'dataset',default={})
        report=self.repo.latest(mode,'report')
        check=self.repo.latest(mode,'check',default={})
        if report:
            report=report|dict(candidates=check.get('candidates',report['candidates']))
        health=[]
        for row in self.repo.records(mode,'health',limit=100):
            if not any(h['kind']==row['key'] for h in health):
                health.append(row['payload'])
        events=self.repo.records(mode,'event',limit=200)
        verifications=self.repo.records(mode,'verification',limit=1000)
        for event in events:
            match=next((v['payload'] for v in verifications if v['payload']['event_id']==event['id']),None)
            event['payload']['verification']=match
        return dict(settings=self.settings.model_dump(),report=report,portfolio=self.portfolio(),
                    holdings=check.get('holdings',[]),events=events,health=health,
                    history=self.repo.records(mode,'report',limit=30),alerts=self.repo.records(mode,'alert',limit=100),
                    job=self.job.copy(),sources=permitted_sources(self.settings),
                    research=self.repo.records(mode,'research',limit=20),
                    model_usage=self.repo.usage(mode,now_local().date().isoformat()),
                    manual_model_usage=self.repo.manual_usage(mode,now_local().date().isoformat()),
                    calendar_covered=max(data.get('calendar') or [''])>=now_local().date().isoformat(),
                    schedule=dict(snapshot='交易日每5分钟',news='快讯5分钟；公司/公告15分钟',daily='18:40–20:00',
                                  running=bool(self._thread and self._thread.is_alive())),
                    limitations=['服务关闭/电脑休眠期间没有监控','模型只补充论据，不改变规则和仓位约束'])

    @settings_locked
    def quant_outlook(self,code,min_reward_risk=2.0,refresh=False):
        from src.services.a_share_outlook_service import OutlookService
        return OutlookService(self).get(code,min_reward_risk,refresh)

    @settings_locked
    def price_context(self,code):
        from src.schemas.a_share_price_scenarios import PriceContext
        profile=self.settings.mode
        if profile=='demo': self.market.ensure_demo()
        raw=self.market.repo.get_history(profile,'stock:'+code,'raw','1900-01-01',self.market.completed_day())
        qfq=self.market.repo.get_history(profile,'stock:'+code,'qfq','1900-01-01',self.market.completed_day())
        from src.services.a_share_market_service import price_family
        if not raw or not qfq or price_family(raw['source'])!=price_family(qfq['source']): return None
        raw_items=raw['items'][-120:]
        qfq_map={b['date']:b for b in qfq['items']}
        end=self.market.completed_day()
        if not raw_items or raw_items[-1]['date']!=end or any(b['date'] not in qfq_map for b in raw_items): return None
        daily=[b|{'adjusted_close':qfq_map[b['date']]['close']} for b in raw_items]
        try:
            features=validate_daily(daily,self.market.calendar(),end,require_amount=False)
            reference=raw_items[-1]['close']
            features={k:v for k,v in features.items() if isinstance(v,(int,float,bool,str))}
            from src.services.a_share_outlook import technical_summary
            from src.services.a_share_outlook_service import merged_bars
            try:
                long=technical_summary(merged_bars(raw,qfq),self.market.calendar(),end)
                for trend in long['trends']:
                    if trend['period'] in (120,250):
                        features['sma'+str(trend['period'])]=trend['ma']
                        features['slope'+str(trend['period'])]=trend['slope']
                        features['trend'+str(trend['period'])]=trend['state']
                features.update(weekly_state=long['weekly']['state'],weekly_as_of=long['weekly']['as_of'],
                                weekly_ma10=long['weekly']['ma10'],weekly_ma30=long['weekly']['ma30'])
                features['long_cycle_status']='available' if features.get('sma250') is not None and long['weekly']['state']!='insufficient' else 'partial'
            except ValueError:
                # Old invalid adjusted prices do not destroy otherwise valid
                # recent120-day evidence; explicitly withhold the extra facts.
                features['long_cycle_status']='invalid_history'
            digest=hashlib.sha256(json.dumps([daily,raw['source'],qfq['adjustment_basis'],features],sort_keys=True).encode()).hexdigest()
            return PriceContext(code=code,anchor_date=end,reference_price=reference,data_hash=digest,adjustment_basis=qfq['adjustment_basis'],features=features,raw_anchor=reference,qfq_anchor=qfq_map[end]['close'],source=raw['source'],demo=profile=='demo').model_dump()
        except (ValueError,KeyError,TypeError): return None

    @settings_locked
    def price_scenarios(self,code):
        context=self.price_context(code)
        records=self.repo.records(self.settings.mode,'research',limit=100)
        value=next((r['payload'].get('price_scenarios') for r in records if r['payload'].get('code')==code and r['payload'].get('price_scenarios')),None)
        if not value: return dict(code=code,status='insufficient',trade_levels=None,forecasts=[],message='尚未生成有效AI价位；请手动生成研究',context=context)
        old=value.get('context',{})
        model=self.settings.model
        stale=not context or any(old.get(k)!=context.get(k) for k in ('code','anchor_date','data_hash','adjustment_basis')) or (model and value.get('model')!=model)
        return value|dict(status='stale' if stale else value['status'])

    @settings_locked
    def research_async(self,code,include_price_scenarios=False):
        from src.services.a_share_research import ResearchEngine
        price_context=self.price_context(code) if include_price_scenarios else None
        if include_price_scenarios and price_context is None:
            if not self.market.stock(code): raise ValueError('股票不在当前目录')
            end=self.market.completed_day()
            self.market.repair_pair(self.settings.mode,code,end,priority=5)
            start=(date.fromisoformat(end)-timedelta(days=500)).isoformat()
            for adjust in ('raw','qfq'): self.market.history(code,start,end,adjust)
            return dict(accepted=False,state='preparing',message='正在补齐120交易日原始/复权资料，完成后请再次生成研究；尚未调用模型')
        report=self.repo.latest(self.settings.mode,'report',default={})
        candidate=next((c for c in report.get('candidates',[]) if c['code']==code),None)
        if candidate is None:
            stock=self.stock_data(code)
            if not stock:
                raise ValueError('该股票的历史资料尚未就绪，请先查看K线并补齐原始/复权日线')
            try:
                metrics=validate_daily(stock['bars'][-120:],self.market.calendar(),stock['as_of'],require_amount=False)
            except (ValueError,KeyError,TypeError) as exc:
                raise ValueError('手动研究需要完整的120交易日价格资料') from exc
            candidate=dict(code=code,name=stock['name'],source=stock['source'],as_of=stock['as_of'],
                           scope='手动选择股票，不属于当前规则候选',**metrics)
            report=dict(source=stock['source'],as_of=stock['as_of'],input_hash=hashlib.sha256(json.dumps(candidate,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
        if not self.settings.research_enabled:
            raise ValueError('请先启用增强研究并配置模型')
        from src.config import get_config
        if not (self.settings.model or get_config().litellm_model):
            raise ValueError('模型未配置，请在原设置页添加模型密钥及模型名称')
        mode=self.settings.mode
        settings=self.settings.model_copy(deep=True)
        evidence=[dict(id='D1',content=json.dumps(candidate,ensure_ascii=False),source=report['source'],as_of=report['as_of'])]
        fund=self.repo.latest(mode,'fundamentals',key=code)
        if fund:
            evidence.append(dict(id='F1',content=json.dumps(fund,ensure_ascii=False)))
        for event in self.repo.records(mode,'event',limit=200):
            value=event['payload']
            if (value.get('code')==code or value.get('related_code')==code or
                    (value.get('code') is None and value.get('related_code') is None)):
                evidence.append(dict(id='E'+str(event['id']),content=value['title']+' '+value.get('content',''),
                                     url=value.get('url'),source=value['source'],first_seen=value['first_seen'],
                                     coverage=value.get('coverage'),verified=value.get('verified',False)))
        evidence=evidence[:10]
        with self._research_lock:
            if code in self._research_codes:
                return dict(accepted=False,message='该股票研究正在运行')
            self._research_codes.add(code)
        def run():
            try:
                ResearchEngine(self.repo).run(code,evidence,report['input_hash'],settings,now_local().date().isoformat(),manual=True,**({'price_context':price_context} if price_context else {}))
            finally:
                with self._research_lock:
                    self._research_codes.discard(code)
        threading.Thread(target=run,daemon=True,name='cn-research-'+code).start()
        return dict(accepted=True,message='手动研究已排队；不受应用每日调用上限限制，模型服务按实际请求计费')

    @settings_locked
    def observations(self):
        data=self.repo.latest(self.settings.mode,'dataset',default={})
        output=[]
        seen=set()
        for record in reversed(self.repo.records(self.settings.mode,'report',limit=100)):
            for c in record['payload']['candidates']:
                local_saved=datetime.fromisoformat(record['created_at']).astimezone(TZ).date().isoformat()
                key=(c['code'],c['strategy'],local_saved)
                if key in seen:
                    continue
                seen.add(key)
                stock=self.stock_data(c['code'])
                if not stock:
                    stock=next((s for s in data.get('stocks',[]) if s['code']==c['code']),{})
                output.append(dict(report_id=record['id'],code=c['code'],strategy=c['strategy'],
                                   saved_date=local_saved,results=forward_observation(
                                   datetime.fromisoformat(record['created_at']).astimezone(TZ).date().isoformat(),
                                   stock.get('bars',[]),data.get('calendar',[]))))
        return output

    def _pending_observation_codes(self,calendar,as_of):
        codes=[]
        for record in self.repo.records(self.settings.mode,'report',limit=1000):
            saved=datetime.fromisoformat(record['created_at']).astimezone(TZ).date().isoformat()
            sessions=[d for d in calendar if d>saved]
            for candidate in record['payload']['candidates']:
                code=candidate['code']
                stock=self.stock_data(code) or {}
                results=forward_observation(saved,stock.get('bars',[]),calendar)
                # Keep tracking both not-yet-due and missing fixed endpoints.
                if len(sessions)<21 or any(r['return'] is None for r in results):
                    codes.append(code)
        return list(dict.fromkeys(codes))

    def start(self):
        from src.scheduler import Scheduler
        scheduler=Scheduler(register_signals=False)
        import schedule
        scheduler.schedule=schedule.Scheduler()  # Keep this app's jobs isolated from DSA daily jobs.
        scheduler.add_background_task(self.tick,interval_seconds=30,name='a-share-capability-monitor',run_immediately=False)
        self._scheduler=scheduler
        self._thread=threading.Thread(target=scheduler.run,daemon=True,name='a-share-scheduler')
        self._thread.start()
        self.market_jobs.start()
        self.integrated.jobs.start()

    def stop(self):
        self._stop.set()
        self.market_jobs.stop()
        self.integrated.jobs.stop()
        if hasattr(self,'_scheduler'):
            self._scheduler.stop()

    def tick(self):
        if self.settings.mode=='demo' or self._stop.is_set():
            return
        now=now_local()
        day=now.date().isoformat()
        data=self.repo.latest(self.settings.mode,'dataset',default={})
        calendar=self.market.calendar() if self.settings.research_scope=='all' else data.get('calendar') or self.repo.latest(self.settings.mode,'calendar',default={}).get('dates',[])
        slot=session_slot(now,calendar)
        if slot:
            self.check(now)  # Invalidate stale actions even while a data crawler is busy.
        kind=None
        if slot and self._slots.get('snapshot')!=slot:
            kind='snapshot'
        elif day in calendar and time(18,40)<=now.time().replace(tzinfo=None)<=time(20) and self._slots.get('daily')!=day+':'+str(now.hour*4+now.minute//15) and (data.get('as_of')!=day or not data.get('daily_complete',False)):
            kind='daily'
        elif time(8,30)<=now.time().replace(tzinfo=None)<=time(20):
            news_slot=now.strftime('%Y-%m-%dT%H:')+str(now.minute//15)
            market_slot=now.strftime('%Y-%m-%dT%H:')+str(now.minute//5)
            if self._slots.get('news')!=news_slot:
                kind='news'
            elif self._slots.get('market_news')!=market_slot:
                kind='market_news'
        if kind and self.sync_async(kind):
            self._slots[kind]=slot if kind=='snapshot' else day+':'+str(now.hour*4+now.minute//15) if kind=='daily' else market_slot if kind=='market_news' else news_slot
            if kind=='news':
                self._slots['market_news']=market_slot


_service=None
_service_lock=threading.Lock()


def get_assistant_service():
    global _service
    with _service_lock:
        if _service is None:
            _service=AssistantService()
    return _service
