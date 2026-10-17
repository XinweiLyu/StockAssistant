"""Indexed mutable market cache, separate from immutable research journals."""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import nullcontext
import json
import uuid
from sqlalchemy import Table, Column, String, Text, Integer, Float, Boolean, UniqueConstraint, select, delete, update, func, and_, or_
from sqlalchemy.dialects.sqlite import insert
from src.storage import Base
from src.schemas.a_share_market import MarketStock, MarketBar, CatalogQuery, SectorQuery


def table(name, *columns):
    return Table('a_share_market_'+name, Base.metadata, *columns)


CATALOG=table('catalog',Column('profile',String(32),primary_key=True),Column('code',String(12),primary_key=True),
              Column('name',String(120),index=True),Column('board',String(20),index=True),Column('st',Boolean),Column('payload',Text))
QUOTES=table('quotes',Column('profile',String(32),primary_key=True),Column('code',String(12),primary_key=True),
             Column('change',Float,index=True),Column('amount',Float,index=True),Column('payload',Text))
SECTORS=table('sectors',Column('profile',String(32),primary_key=True),Column('sector_id',String(180),primary_key=True),
              Column('kind',String(20),index=True),Column('classification',String(80),index=True),Column('payload',Text))
MEMBERS=table('members',Column('profile',String(32),primary_key=True),Column('sector_id',String(180),primary_key=True),
              Column('version',String(100),primary_key=True),Column('code',String(12),primary_key=True,index=True))
RANGES=table('history_ranges',Column('profile',String(32),primary_key=True),Column('entity',String(180),primary_key=True),
             Column('adjust',String(8),primary_key=True),Column('payload',Text))
BARS=table('bars',Column('profile',String(32),primary_key=True),Column('entity',String(180),primary_key=True),
           Column('adjust',String(8),primary_key=True),Column('date',String(10),primary_key=True),Column('payload',Text))
STATE=table('state',Column('profile',String(32),primary_key=True),Column('key',String(220),primary_key=True),Column('payload',Text))
TASKS=table('tasks',Column('id',String(40),primary_key=True),Column('profile',String(32),index=True),
            Column('key',String(250),index=True),Column('kind',String(30)),Column('state',String(20),index=True),
            Column('priority',Integer),Column('payload',Text),Column('attempts',Integer),Column('claim_version',Integer),
            Column('created_at',String(40)),Column('updated_at',String(40)),Column('next_attempt',String(40)),Column('error',Text),
            UniqueConstraint('profile','key',name='uq_market_task_request'))


def jsonable(value):
    return value.model_dump(mode='json') if hasattr(value,'model_dump') else value


def encode(value):
    return json.dumps(jsonable(value),ensure_ascii=False,allow_nan=False)


def stamp(now=None):
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


class MarketRepository:
    def __init__(self,engine):
        self.engine=engine
        Base.metadata.create_all(engine,tables=[CATALOG,QUOTES,SECTORS,MEMBERS,RANGES,BARS,STATE,TASKS])

    @staticmethod
    def _upsert(conn, tbl, values):
        keys=[c.name for c in tbl.primary_key]
        statement=insert(tbl).values(values)
        conn.execute(statement.on_conflict_do_update(index_elements=keys,
                     set_={k:getattr(statement.excluded,k) for k in values if k not in keys}))

    def set_state(self,profile,key,value,conn=None):
        values=dict(profile=profile,key=key,payload=encode(value))
        if conn is not None:
            self._upsert(conn,STATE,values)
        else:
            with self.engine.begin() as connection:
                self._upsert(connection,STATE,values)

    def get_state(self,profile,key,default=None):
        with self.engine.connect() as conn:
            payload=conn.execute(select(STATE.c.payload).where(STATE.c.profile==profile,STATE.c.key==key)).scalar()
        return json.loads(payload) if payload is not None else default

    def states_with_prefix(self,profile,prefix):
        with self.engine.connect() as conn:
            rows=conn.execute(select(STATE.c.key,STATE.c.payload).where(STATE.c.profile==profile,STATE.c.key.startswith(prefix))).all()
        return {k:json.loads(v) for k,v in rows}

    def replace_catalog(self,profile,version,stocks):
        rows=[MarketStock.model_validate(jsonable(s)).model_dump(mode='json') for s in stocks]
        if not rows or len({s['code'] for s in rows})!=len(rows):
            raise ValueError('目录为空或存在重复身份，保留上一版')
        with self.engine.begin() as conn:
            conn.execute(delete(CATALOG).where(CATALOG.c.profile==profile))
            conn.execute(CATALOG.insert(),[dict(profile=profile,code=s['code'],name=s['name'],board=s['board'],st=s['st'],payload=encode(s)) for s in rows])
            self.set_state(profile,'catalog',dict(version=version,count=len(rows),fetched_at=rows[0]['fetched_at']),conn)

    def put_quotes(self,profile,batch,quotes,update_batch=True,conn=None):
        with self.engine.begin() if conn is None else nullcontext(conn) as conn:
            for value in quotes:
                value=jsonable(value)
                self._upsert(conn,QUOTES,dict(profile=profile,code=value['code'],change=value.get('change'),amount=value.get('amount'),payload=encode(value|{'batch':batch})))
            if update_batch:
                self.set_state(profile,'quote_batch',dict(batch=batch,fetched_at=stamp()),conn)

    def quotes(self,profile,codes=None):
        query=select(QUOTES.c.payload).where(QUOTES.c.profile==profile)
        if codes is not None:
            query=query.where(QUOTES.c.code.in_(codes))
        with self.engine.connect() as conn:
            return {v['code']:v for v in [json.loads(r[0]) for r in conn.execute(query)]}

    def put_sectors(self,profile,sectors):
        with self.engine.begin() as conn:
            for s in sectors:
                value=jsonable(s)
                self._upsert(conn,SECTORS,dict(profile=profile,sector_id=value['sector_id'],kind=value['kind'],classification=value['classification'],payload=encode(value)))

    def sector(self,profile,sector_id):
        with self.engine.connect() as conn:
            raw=conn.execute(select(SECTORS.c.payload).where(SECTORS.c.profile==profile,SECTORS.c.sector_id==sector_id)).scalar()
        return json.loads(raw) if raw else None

    def list_sectors(self,profile,query:SectorQuery):
        statement=select(SECTORS.c.payload).where(SECTORS.c.profile==profile,SECTORS.c.kind==query.kind)
        if query.classification:
            statement=statement.where(SECTORS.c.classification==query.classification)
        with self.engine.connect() as conn:
            return [json.loads(r[0]) for r in conn.execute(statement)]

    def replace_members(self,profile,sector_id,version,codes):
        codes=sorted(set(codes))
        if not codes:
            raise ValueError('成分股为空，保留上一版')
        with self.engine.begin() as conn:
            conn.execute(delete(MEMBERS).where(MEMBERS.c.profile==profile,MEMBERS.c.sector_id==sector_id,MEMBERS.c.version==version))
            conn.execute(MEMBERS.insert(),[dict(profile=profile,sector_id=sector_id,version=version,code=c) for c in codes])
            self.set_state(profile,'members:'+sector_id,dict(version=version,fetched_at=stamp()),conn)

    def members(self,profile,sector_id,version=None):
        current=self.get_state(profile,'members:'+sector_id,{})
        chosen=version or current.get('version')
        if not chosen:
            return dict(codes=[],version=None,fetched_at=None,state='pending')
        with self.engine.connect() as conn:
            codes=list(conn.execute(select(MEMBERS.c.code).where(MEMBERS.c.profile==profile,MEMBERS.c.sector_id==sector_id,MEMBERS.c.version==chosen).order_by(MEMBERS.c.code)).scalars())
        return dict(codes=codes,version=chosen,fetched_at=current.get('fetched_at'),state='ready')

    def stock(self,profile,code):
        with self.engine.connect() as conn:
            raw=conn.execute(select(CATALOG.c.payload).where(CATALOG.c.profile==profile,CATALOG.c.code==code)).scalar()
        return json.loads(raw) if raw else None

    def catalog_codes(self,profile):
        with self.engine.connect() as conn:
            return list(conn.execute(select(CATALOG.c.code).where(CATALOG.c.profile==profile).order_by(CATALOG.c.code)).scalars())

    def associations(self,profile,codes=None):
        with self.engine.connect() as conn:
            versions={r['key'][8:]:json.loads(r['payload']) for r in conn.execute(select(STATE).where(STATE.c.profile==profile,STATE.c.key.like('members:%'))).mappings()}
            statement=select(MEMBERS.c.code,MEMBERS.c.sector_id,MEMBERS.c.version,SECTORS.c.payload).select_from(
                MEMBERS.join(SECTORS,and_(MEMBERS.c.profile==SECTORS.c.profile,MEMBERS.c.sector_id==SECTORS.c.sector_id))).where(MEMBERS.c.profile==profile)
            if codes is not None:
                statement=statement.where(MEMBERS.c.code.in_(codes))
            rows=conn.execute(statement).mappings().all()
        output={}
        for row in rows:
            active=versions.get(row['sector_id'],{})
            if row['version']==active.get('version'):
                s=json.loads(row['payload'])|dict(membership_version=row['version'],membership_fetched_at=active.get('fetched_at'))
                output.setdefault(row['code'],[]).append(s)
        return output

    def list_stocks(self,profile,query:CatalogQuery,codes=None):
        join=CATALOG.outerjoin(QUOTES,and_(QUOTES.c.profile==CATALOG.c.profile,QUOTES.c.code==CATALOG.c.code))
        filters=[CATALOG.c.profile==profile]
        if codes is not None: filters.append(CATALOG.c.code.in_(codes))
        if query.q:
            escaped=query.q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            filters.append(or_(CATALOG.c.code.contains(escaped,escape='\\'),CATALOG.c.name.contains(escaped,escape='\\')))
        if query.board:
            filters.append(CATALOG.c.board==query.board)
        if query.st is not None:
            filters.append(CATALOG.c.st==query.st)
        for sector_id in (query.industry_id,query.concept_id):
            if sector_id:
                if sector_id=='__unknown__':
                    mapped=[c for c,groups in self.associations(profile).items() if any(s['kind']=='industry' for s in groups)]
                    filters.append(CATALOG.c.code.not_in(mapped))
                else:
                    codes=self.members(profile,sector_id)['codes']
                    filters.append(CATALOG.c.code.in_(codes))
        sort={'code':CATALOG.c.code,'name':CATALOG.c.name,'change':QUOTES.c.change,'amount':QUOTES.c.amount}[query.sort]
        order=sort.desc() if query.direction=='desc' else sort.asc()
        with self.engine.connect() as conn:
            total=conn.execute(select(func.count()).select_from(join).where(*filters)).scalar()
            rows=conn.execute(select(CATALOG.c.payload,QUOTES.c.payload.label('quote')).select_from(join).where(*filters)
                              .order_by(sort.is_(None),order,CATALOG.c.code.asc()).offset((query.page-1)*query.page_size).limit(query.page_size)).mappings().all()
        items=[json.loads(r['payload'])|{'quote':json.loads(r['quote']) if r['quote'] else None} for r in rows]
        associations=self.associations(profile,[s['code'] for s in items]) if items else {}
        for s in items:
            groups=associations.get(s['code'],[])
            s['industries']=[g for g in groups if g['kind']=='industry']
            s['concepts']=[g for g in groups if g['kind']=='concept']
        return dict(items=items,total=total,page=query.page,page_size=query.page_size,
                    catalog=self.get_state(profile,'catalog',{}))

    def replace_history(self,profile,entity,adjust,source,basis,bars,fetched_at,requested_start=None,requested_end=None,conn=None):
        values=sorted([MarketBar.model_validate(jsonable(r)).model_dump(mode='json') for r in bars],key=lambda r:r['date'])
        if not values or len({r['date'] for r in values})!=len(values):
            raise ValueError('历史为空或日期重复，保留上一版')
        meta=dict(source=source,adjustment_basis=basis,fetched_at=fetched_at,
                  requested_start=requested_start or values[0]['date'],requested_end=requested_end or values[-1]['date'],
                  actual_start=values[0]['date'],actual_end=values[-1]['date'])
        with self.engine.begin() if conn is None else nullcontext(conn) as conn:
            conn.execute(delete(BARS).where(BARS.c.profile==profile,BARS.c.entity==entity,BARS.c.adjust==adjust))
            conn.execute(BARS.insert(),[dict(profile=profile,entity=entity,adjust=adjust,date=r['date'],payload=encode(r)) for r in values])
            self._upsert(conn,RANGES,dict(profile=profile,entity=entity,adjust=adjust,payload=encode(meta)))

    def get_history(self,profile,entity,adjust,start,end):
        with self.engine.connect() as conn:
            raw=conn.execute(select(RANGES.c.payload).where(RANGES.c.profile==profile,RANGES.c.entity==entity,RANGES.c.adjust==adjust)).scalar()
            if not raw:
                return None
            rows=conn.execute(select(BARS.c.payload).where(BARS.c.profile==profile,BARS.c.entity==entity,BARS.c.adjust==adjust,BARS.c.date>=start,BARS.c.date<=end).order_by(BARS.c.date)).scalars().all()
        return json.loads(raw)|dict(items=[json.loads(r) for r in rows],adjust=adjust)

    def enqueue(self,profile,key,kind,payload,priority):
        with self.engine.begin() as conn:
            previous=conn.execute(select(TASKS.c.id).where(TASKS.c.profile==profile,TASKS.c.key==key,TASKS.c.state.in_(['pending','running','complete']))).scalar()
            if previous:
                conn.execute(update(TASKS).where(TASKS.c.id==previous,TASKS.c.state=='pending',TASKS.c.priority>priority).values(priority=priority))
                return previous
            identity=uuid.uuid4().hex
            now=stamp()
            conn.execute(insert(TASKS).values(id=identity,profile=profile,key=key,kind=kind,state='pending',priority=priority,
                         payload=encode(payload),attempts=0,claim_version=0,created_at=now,updated_at=now,next_attempt=None,error=None)
                         .on_conflict_do_nothing(index_elements=['profile','key']))
            identity=conn.execute(select(TASKS.c.id).where(TASKS.c.profile==profile,TASKS.c.key==key)).scalar_one()
        return identity

    def claim(self,profile,now,kinds=None,exclude_kinds=None):
        paused=self.get_state(profile,'paused',False)
        with self.engine.begin() as conn:
            query=select(TASKS).where(TASKS.c.profile==profile,TASKS.c.state=='pending',
                   or_(TASKS.c.next_attempt.is_(None),TASKS.c.next_attempt<=stamp(now)))
            if kinds is not None:
                query=query.where(TASKS.c.kind.in_(kinds))
            if exclude_kinds:
                query=query.where(TASKS.c.kind.not_in(exclude_kinds))
            if paused:
                query=query.where(TASKS.c.priority<90)
            row=conn.execute(query.order_by(TASKS.c.priority,TASKS.c.created_at,TASKS.c.id).limit(1)).mappings().first()
            if row is None:
                return None
            version=row['claim_version']+1
            changed=conn.execute(update(TASKS).where(TASKS.c.id==row['id'],TASKS.c.state=='pending',TASKS.c.claim_version==row['claim_version'])
                                 .values(state='running',attempts=row['attempts']+1,claim_version=version,updated_at=stamp(now)))
            if not changed.rowcount:
                return None
            return dict(row)|dict(payload=json.loads(row['payload']),attempts=row['attempts']+1,claim_version=version)

    def finish(self,task_id,claim_version,state,error=None,next_attempt=None):
        with self.engine.begin() as conn:
            changed=conn.execute(update(TASKS).where(TASKS.c.id==task_id,TASKS.c.state=='running',TASKS.c.claim_version==claim_version)
                                 .values(state=state,error=error,next_attempt=next_attempt,updated_at=stamp()))
            return bool(changed.rowcount)

    def defer(self,task,until):
        with self.engine.begin() as conn:
            return bool(conn.execute(update(TASKS).where(TASKS.c.id==task['id'],TASKS.c.state=='running',TASKS.c.claim_version==task['claim_version'])
                         .values(state='pending',attempts=max(0,task['attempts']-1),next_attempt=until,updated_at=stamp())).rowcount)

    def task(self,task_id):
        with self.engine.connect() as conn:
            row=conn.execute(select(TASKS).where(TASKS.c.id==task_id)).mappings().first()
        return (dict(row)|dict(payload=json.loads(row['payload']))) if row else None

    def tasks(self,profile,limit=100):
        with self.engine.connect() as conn:
            rows=conn.execute(select(TASKS).where(TASKS.c.profile==profile).order_by(TASKS.c.updated_at.desc()).limit(limit)).mappings().all()
        return [dict(r)|dict(payload=json.loads(r['payload'])) for r in rows]

    def pause(self,profile,paused):
        self.set_state(profile,'paused',paused)

    def recover_running(self,profile,kinds=None,exclude_kinds=None):
        with self.engine.begin() as conn:
            query=update(TASKS).where(TASKS.c.profile==profile,TASKS.c.state=='running')
            if kinds is not None:
                query=query.where(TASKS.c.kind.in_(kinds))
            if exclude_kinds:
                query=query.where(TASKS.c.kind.not_in(exclude_kinds))
            conn.execute(query.values(state='pending',claim_version=TASKS.c.claim_version+1,next_attempt=None))

    def progress(self,profile):
        with self.engine.connect() as conn:
            counts=dict(conn.execute(select(TASKS.c.state,func.count()).where(TASKS.c.profile==profile).group_by(TASKS.c.state)).all())
        return dict(counts=counts,paused=self.get_state(profile,'paused',False),tasks=self.tasks(profile,limit=20))
