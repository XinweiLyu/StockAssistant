"""Additive flow history and non-additive observation buckets on the existing DB."""
from datetime import datetime,time
from zoneinfo import ZoneInfo
from sqlalchemy import Table,Column,String,Text,Integer,select,Index
from sqlalchemy.dialects.sqlite import insert
from src.storage import Base
from src.schemas.a_share_sector_flow import FlowPoint,utc_time
from src.repositories.a_share_market_repository import encode
import json

DAILY=Table('a_share_sector_flow_daily',Base.metadata,
    Column('profile',String(40),primary_key=True),Column('sector_id',String(180),primary_key=True),
    Column('day',String(10),primary_key=True),Column('observed_at',String(40),primary_key=True),Column('payload',Text))
OBS=Table('a_share_sector_flow_observations',Base.metadata,
    Column('profile',String(40),primary_key=True),Column('sector_id',String(180),primary_key=True),
    Column('day',String(10),primary_key=True),Column('bucket',Integer,primary_key=True),Column('payload',Text))


class SectorFlowRepository:
    def __init__(self,engine):
        self.engine=engine
        Base.metadata.create_all(engine,tables=[DAILY,OBS])

    def save_daily(self,profile,rows):
        points=[FlowPoint.model_validate(r).model_dump() for r in rows]
        if any(r['measure']!='daily_net' for r in points):raise ValueError('日净额与累计采样不可混存')
        with self.engine.begin() as conn:
            for r in points:
                conn.execute(insert(DAILY).values(profile=profile,sector_id=r['sector_id'],day=r['source_date'],observed_at=r['observed_at'],payload=encode(r)).on_conflict_do_nothing())

    def save_observations(self,profile,rows):
        points=[FlowPoint.model_validate(r).model_dump() for r in rows]
        if any(r['measure']!='cumulative_snapshot' for r in points):raise ValueError('采样只接受累计快照')
        with self.engine.begin() as conn:
            for r in points:
                bucket=int(datetime.fromisoformat(r['observed_at']).timestamp())//300
                stmt=insert(OBS).values(profile=profile,sector_id=r['sector_id'],day=r['session_day'],bucket=bucket,payload=encode(r))
                conn.execute(stmt.on_conflict_do_update(index_elements=['profile','sector_id','day','bucket'],set_={'payload':stmt.excluded.payload}))

    def read_daily(self,profile,sector_id,start,end,as_of=None):
        query=select(DAILY).where(DAILY.c.profile==profile,DAILY.c.sector_id==sector_id,DAILY.c.day>=start,DAILY.c.day<=end)
        if as_of:query=query.where(DAILY.c.observed_at<=utc_time(as_of))
        query=query.order_by(DAILY.c.day.asc(),DAILY.c.observed_at.desc())
        found={}
        with self.engine.connect() as conn:
            for r in conn.execute(query).mappings():
                value=json.loads(r['payload'])
                observed=datetime.fromisoformat(value['observed_at']).astimezone(ZoneInfo('Asia/Shanghai'))
                # A morning snapshot never becomes a completed daily record by aging.
                # Keep the raw vintage, but require a fresh post-cutoff observation.
                if observed.date().isoformat()==r['day'] and observed.time().replace(tzinfo=None)<time(15,10):continue
                if r['day'] not in found:found[r['day']]=value
        return list(found.values())

    def read_observations(self,profile,sector_id,day):
        query=select(OBS.c.payload).where(OBS.c.profile==profile,OBS.c.sector_id==sector_id,OBS.c.day==day).order_by(OBS.c.bucket)
        with self.engine.connect() as conn:return [json.loads(r[0]) for r in conn.execute(query)]
