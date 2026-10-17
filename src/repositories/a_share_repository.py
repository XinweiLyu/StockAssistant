"""Append-only research journal on DSA's database, isolated by demo/live namespace."""
from datetime import datetime, timezone
import hashlib
import json
from sqlalchemy import Table, Column, Integer, String, Text, Index, select, update
from sqlalchemy.dialects.sqlite import insert
from src.storage import Base, DatabaseManager

JOURNAL = Table('a_share_journal', Base.metadata,
                Column('id',Integer,primary_key=True), Column('mode',String(10),index=True,nullable=False),
                Column('kind',String(30),index=True,nullable=False), Column('key',String(200),nullable=False),
                Column('created_at',String(40),nullable=False), Column('payload',Text,nullable=False))
USAGE = Table('a_share_usage', Base.metadata,
              Column('key',String(80),primary_key=True), Column('calls',Integer,nullable=False))
LOOKUP=Index('ix_a_share_journal_lookup',JOURNAL.c.mode,JOURNAL.c.kind,JOURNAL.c.key,JOURNAL.c.id)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class AssistantRepository:
    def __init__(self, engine=None):
        self.engine = engine or DatabaseManager.get_instance()._engine
        Base.metadata.create_all(self.engine, tables=[JOURNAL,USAGE])
        LOOKUP.create(self.engine,checkfirst=True)

    @staticmethod
    def namespace(mode):
        return 'demo' if mode == 'demo' else 'live'

    def append(self, mode, kind, key, payload):
        with self.engine.begin() as conn:
            result = conn.execute(JOURNAL.insert().values(mode=self.namespace(mode),kind=kind,key=key,
                                  created_at=utc_now(),payload=json.dumps(payload,ensure_ascii=False,allow_nan=False)))
            return result.inserted_primary_key[0]

    def records(self, mode, kind, limit=100, key=None):
        query = select(JOURNAL).where(JOURNAL.c.mode==self.namespace(mode),JOURNAL.c.kind==kind)
        if key is not None:
            query = query.where(JOURNAL.c.key==key)
        with self.engine.connect() as conn:
            rows = conn.execute(query.order_by(JOURNAL.c.id.desc()).limit(limit)).mappings().all()
            return [dict(r) | {'payload':json.loads(r['payload'])} for r in rows]

    def latest(self, mode, kind, key=None, default=None):
        rows = self.records(mode,kind,limit=1,key=key)
        return rows[0]['payload'] if rows else default

    def add_event(self, mode, event):
        key = hashlib.sha256(json.dumps([event.get('source'),event.get('url') or event.get('title'),
                                        event.get('code'),event.get('published_at')],ensure_ascii=False).encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(event,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        previous = self.latest(mode,'event',key=key)
        if previous and previous['fingerprint']==fingerprint:
            return False
        payload = event | dict(fingerprint=fingerprint, first_seen=previous['first_seen'] if previous else utc_now(),
                               revised_at=utc_now(),revision=(previous['revision']+1) if previous else 1,
                               verified=False, previous_fingerprint=previous['fingerprint'] if previous else None)
        self.append(mode,'event',key,payload)
        return True

    def reserve_call(self, mode, day, limit):
        key = 'global:'+day
        with self.engine.begin() as conn:
            conn.execute(insert(USAGE).values(key=key,calls=0).on_conflict_do_nothing(index_elements=['key']))
            result = conn.execute(update(USAGE).where(USAGE.c.key==key,USAGE.c.calls<limit).values(calls=USAGE.c.calls+1))
            return result.rowcount == 1

    def usage(self, mode, day):
        with self.engine.connect() as conn:
            return conn.execute(select(USAGE.c.calls).where(USAGE.c.key=='global:'+day)).scalar() or 0

    def record_manual_call(self, day):
        key = 'manual:'+day
        with self.engine.begin() as conn:
            conn.execute(insert(USAGE).values(key=key,calls=1).on_conflict_do_update(
                index_elements=['key'],set_={'calls':USAGE.c.calls+1}))

    def manual_usage(self, mode, day):
        with self.engine.connect() as conn:
            return conn.execute(select(USAGE.c.calls).where(USAGE.c.key=='manual:'+day)).scalar() or 0
