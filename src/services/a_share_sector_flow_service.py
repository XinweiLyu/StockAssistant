"""Cached source-defined flow evidence; no price prediction or model calls here."""
from datetime import date,timedelta,time
from zoneinfo import ZoneInfo
import hashlib,json
from src.schemas.a_share import AssistantSettings
from src.schemas.a_share_sector_flow import CATEGORIES,utc_time
from src.repositories.a_share_sector_flow_repository import SectorFlowRepository
from data_provider.a_share_sector_flow import board_identity,normalize_rank,normalize_history,normalize_members

TZ=ZoneInfo('Asia/Shanghai')
FLOW_KINDS={'sector_flow_rank','sector_flow_history','sector_flow_members'}
DISCLAIMER='主力为来源按成交单大小分类的净额，不等于机构持仓或真实资金进出市场；主力已包含超大单和大单，不能叠加求和。'

class SectorFlowService:
 def __init__(self,market):
  self.market=market
  self.repo=SectorFlowRepository(market.repo.engine)

 @property
 def profile(self):return self.market.profile

 def sessions(self):
  from src.core.trading_calendar import get_trading_dates
  today=self.market.clock().astimezone(TZ).date()
  days=get_trading_dates('cn',today-timedelta(days=400),today)
  return [d.date().isoformat() for d in days] if days is not None else []

 def _timing(self):
  now=self.market.clock().astimezone(TZ);day=now.date().isoformat();days=self.sessions()
  trading=day in days;t=now.time().replace(tzinfo=None)
  active=trading and (time(9,30)<=t<=time(11,30) or time(13)<=t<=time(15))
  closed=[d for d in days if d<day or d==day and t>=time(15,10)]
  return now,closed,active

 def _board(self,sector_id):
  board=self.market.repo.sector(self.profile,sector_id)
  if not board:raise ValueError('请先加载有效A股行业或概念板块')
  board_identity(board)
  return board

 def _queue(self,task_kind,scope,refresh=False,**payload):
  now,closed,active=self._timing();key='sector-flow:task:'+task_kind+':'+scope
  old=self.market.repo.get_state(self.profile,key,{})
  task=self.market.repo.task(old.get('id','')) if old else None
  priority={'sector_flow_history':1,'sector_flow_members':2,'sector_flow_rank':3}[task_kind]
  if task and task['state'] in ('pending','running','retry'):
   if task['state']=='pending' and task['priority']>priority:
    self.market.repo.enqueue(self.profile,task['key'],task_kind,task['payload'],priority)
   return task['id']
  last=old.get('bucket');bucket=int(now.timestamp())//300
  if not refresh and task_kind=='sector_flow_history' and old.get('anchor')==(closed[-1] if closed else None) and old:return None
  # Source failures use the existing bounded queue retry policy, never a tight client loop.
  if not refresh and old and (last==bucket or not active and task_kind!='sector_flow_history'):return None
  if self.profile=='demo' or not self.market.assistant.settings.free_fallback:return None
  nonce=now.isoformat() if refresh else str(bucket)
  value=self.market._submit(task_kind,'sector-flow:'+task_kind+':'+scope+':'+nonce,priority,**payload)
  task_id=value['id'] if isinstance(value,dict) else value
  self.market.repo.set_state(self.profile,key,dict(id=task_id,bucket=bucket,anchor=closed[-1] if closed else None))
  return task_id

 def _poll_pending(self,ids):
  tasks=[self.market.repo.task(i) for i in ids if i]
  return any(t and (t['state']=='running' or t['state']=='pending' and not t.get('next_attempt')) for t in tasks)

 def rankings(self,kind,refresh=False):
  if kind not in ('industry','concept'):raise ValueError('不支持此板块资金分类')
  state=self.market.repo.get_state(self.profile,'sector-flow:rank:'+kind,{})
  task_id=self._queue('sector_flow_rank',kind,refresh,kind=kind) if refresh or self._timing()[2] or not state else None
  return dict(items=state.get('items',[]),observed_at=state.get('observed_at'),source_time=None,source='eastmoney/sector-flow',unit='CNY',task_id=task_id,poll_pending=self._poll_pending([task_id]),
   health=self.market.repo.get_state(self.profile,'sector-flow:health:rank:'+kind,{}),limitations=[DISCLAIMER,'来源未提供快照交易日期，采样时间不能证明报价属于今天。'])

 def comparison(self,kind,ids,refresh=False):
  if kind not in ('industry','concept'):raise ValueError('只支持A股行业或概念对比')
  if len(ids)>8 or len(set(ids))!=len(ids):raise ValueError('最多选择8个不重复板块')
  boards=[self._board(i) for i in ids]
  if any(b['kind']!=kind for b in boards):raise ValueError('行业和概念须分别对比')
  now,closed,active=self._timing();day=now.date().isoformat()
  rank=self.rankings(kind,refresh) if boards else {}
  series=[]
  for board in boards:
   points=self.repo.read_observations(self.profile,board['sector_id'],day)
   series.append(dict(sector=board,points=points,latest=points[-1] if points else None))
  return dict(kind=kind,day=day,profile=self.profile,series=series,unit='CNY',
   measure='cumulative_snapshot',source='eastmoney/sector-flow',source_date_verified=False,
   active=active,calendar_available=bool(closed),task_id=rank.get('task_id'),
   poll_pending=rank.get('poll_pending',False),health=rank.get('health',{}),
   observed_at=rank.get('observed_at'),limitations=[DISCLAIMER,
    '横轴为今日系统采样时间，源交易日期未核实；仅绘制实际采集值，不代表完整开盘以来分钟历史。',
    '同一板块累计值不求和；不同概念可能重叠，不能汇总为全市场资金。'])

 def get(self,sector_id,period=0,refresh=False):
  if period not in (0,5,20,60):raise ValueError('资金期间仅支持0/5/20/60交易日')
  board=self._board(sector_id);now,closed,active=self._timing()
  rank=self.rankings(board['kind'],refresh)
  history_task=self._queue('sector_flow_history',sector_id,refresh,sector=board)
  members_task=self._queue('sector_flow_members',sector_id,refresh,sector=board)
  raw=self.repo.read_daily(self.profile,sector_id,closed[0],closed[-1]) if closed else []
  known={r['source_date']:r for r in raw}
  expected=closed[-period:] if period else []
  points=[known.get(d) or dict(source_date=d,session_day=d,observed_at=None,values={k:None for k in CATEGORIES},ratios={},change=None,close=None) for d in expected]
  complete=bool(period and len(expected)==period and all(r['values']['main'] is not None for r in points))
  if not period:
   # Query-context dates cannot establish a trade date. These are labelled observations,
   # collected only during an exchange session, rather than a backfilled minute history.
   points=self.repo.read_observations(self.profile,sector_id,now.date().isoformat())
  total=sum(r['values']['main'] for r in points) if complete else None
  latest=self.market.repo.get_state(self.profile,'sector-flow:members:'+sector_id,{})
  health={k:self.market.repo.get_state(self.profile,'sector-flow:health:'+k+':'+(board['kind'] if k=='rank' else sector_id),{}) for k in ('rank','history','members')}
  def net(count):
   window=closed[-count:]
   if len(window)!=count or any(d not in known or known[d]['values']['main'] is None for d in window):return None
   return sum(known[d]['values']['main'] for d in window)
  streak=0
  for d in reversed(closed):
   n=known.get(d,{}).get('values',{}).get('main')
   if n is None:streak=None;break
   if n<=0:break
   streak+=1
  six=net(6);three=net(3)
  return dict(sector=board,period=period,unit='CNY',source='eastmoney/sector-flow',source_time=None,
   measure='daily_net' if period else 'cumulative_snapshot',points=points,complete=complete,
   summary=dict(main_net=total,net_5d=net(5),net_20d=net(20),consecutive_positive=streak,
    acceleration_3d=2*three-six if six is not None and three is not None else None,positive_days=sum(r['values']['main']>0 for r in points) if complete else None,
    cumulative=total,covered=sum(r['values']['main'] is not None for r in points),required=period or None),
   member_flows=latest.get('items',[]),member_observed_at=latest.get('observed_at'),rank_observed_at=rank.get('observed_at'),
   observed_at=max((r['observed_at'] for r in points if r.get('observed_at')),default=None),
   anchor_date=closed[-1] if closed else None,active=active,calendar_available=bool(closed),
   task_ids=[t for t in (rank['task_id'],history_task,members_task) if t],
   poll_pending=self._poll_pending([rank['task_id'],history_task,members_task]),health=health,
   limitations=[DISCLAIMER,'今日曲线为打开页面后采集的累计快照，非逐笔资金或历史分钟回放；午休和缺口断线。','未核实来源交易日期；盘中采样只标示获取时间。','日资金仅统计完整交易日；缺失交易日不补零，区间累计暂停计算。'])

 def handle_task(self,task):
  profile=task['profile'];payload=task['payload'];settings=AssistantSettings.model_validate(payload['settings'])
  name=task['kind'].removeprefix('sector_flow_');scope=payload['kind'] if name=='rank' else payload['sector']['sector_id']
  try:
   provider=self.market.provider_for(settings).provider
   params=dict(kind=payload['kind']) if name=='rank' else dict(symbol=payload['sector']['code'])
   raw=provider.call('sector_fund_flow_'+name+'_em',params)
   now=self.market.clock();observed=utc_time(now.isoformat())
   if name=='rank':rows=normalize_rank(raw,payload['kind'],observed)
   elif name=='history':rows=normalize_history(raw,payload['sector'],observed)
   else:rows=normalize_members(raw,payload['sector'],observed)
   with self.market._publication(task):
    if name=='history':self.repo.save_daily(profile,rows)
    else:
     self.market.repo.set_state(profile,'sector-flow:'+name+':'+scope,dict(items=rows,observed_at=observed))
     if name=='rank' and self._timing()[2]:self.repo.save_observations(profile,rows)
    self.market.repo.set_state(profile,'sector-flow:health:'+name+':'+scope,dict(status='ready',observed_at=observed))
  except Exception as exc:
   # Error text is deliberately not relayed; upstream exception bodies may contain settings.
   self.market.repo.set_state(profile,'sector-flow:health:'+name+':'+scope,dict(status='failed',checked_at=utc_time(self.market.clock().isoformat()),error='资金来源暂不可用，保留上次缓存',error_type=type(exc).__name__))
   raise

 def research_fact(self,stock_code,industry,cutoff,anchor_date):
  if not industry:return None
  try:board_identity(industry)
  except (ValueError,KeyError):return None
  days=[d for d in self.sessions() if d<=anchor_date][-20:]
  if len(days)<5:return None
  rows=self.repo.read_daily(self.profile,industry['sector_id'],days[0],days[-1],as_of=cutoff)
  byday={r['source_date']:r for r in rows};five=[byday.get(d) for d in days[-5:]]
  if any(r is None or r['values']['main'] is None for r in five):return None
  twenty=[byday.get(d) for d in days]
  observed=max(r['observed_at'] for r in rows)
  values=dict(sector_id=industry['sector_id'],industry_name=industry['name'],source_date=days[-1],
   main_net_5d=sum(r['values']['main'] for r in five),unit='CNY',not_institutional_holdings=True,
   main_net_20d=sum(r['values']['main'] for r in twenty) if len(days)==20 and all(r and r['values']['main'] is not None for r in twenty) else None,
   observed_at=observed,vintage_quality='latest_reconstructed',definition=DISCLAIMER)
  identity=hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
  return dict(fact_id='sector_flow_'+identity,code=stock_code,category='market',source='eastmoney/sector-flow',
   available_at=observed,published_at=days[-1]+'T15:10:00+08:00',values=values,
   observed_at=observed,vintage_quality='latest_reconstructed',historical_eligible=False,
   units={'main_net_5d':'CNY','main_net_20d':'CNY'},url='https://data.eastmoney.com/bkzj/',content_hash=identity)
