"""A durable priority queue; long warmups release control after each stock."""
from datetime import datetime, timedelta, timezone
import threading
import logging

logger=logging.getLogger(__name__)


class Deferred(RuntimeError):
    def __init__(self,seconds=30):
        self.seconds=seconds
        super().__init__('等待依赖资料')


class MarketJobs:
    def __init__(self,repo,handler,clock=None,profile='demo',kinds=None,exclude_kinds=None):
        self.repo=repo
        self.handler=handler
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.profile=profile
        self.kinds=kinds
        self.exclude_kinds=exclude_kinds
        self._stop=threading.Event()
        self._wake=threading.Event()
        self._thread=None

    def submit(self,profile,key,kind,payload,priority):
        identity=self.repo.enqueue(profile,key,kind,payload,priority)
        self._wake.set()
        return identity

    def set_profile(self,profile):
        if profile!=self.profile:
            self.repo.recover_running(profile,kinds=self.kinds,exclude_kinds=self.exclude_kinds)
            self.profile=profile
            self._wake.set()

    def set_paused(self,profile,paused):
        self.repo.pause(profile,paused)
        self._wake.set()

    def finish_failure(self,task,exc):
        failed=task['attempts']>=3
        # Exception details from credentials-bearing providers do not cross this boundary.
        message='来源调用失败或字段缺失：'+type(exc).__name__
        self.repo.finish(task['id'],task['claim_version'],'failed' if failed else 'pending',error=message,
                         next_attempt=None if failed else (self.clock()+timedelta(minutes=15)).astimezone(timezone.utc).isoformat())

    def run_one(self):
        task=self.repo.claim(self.profile,self.clock(),kinds=self.kinds,exclude_kinds=self.exclude_kinds)
        if task is None:
            return False
        try:
            self.handler(task)
        except Deferred as exc:
            self.repo.defer(task,(self.clock()+timedelta(seconds=exc.seconds)).astimezone(timezone.utc).isoformat())
        except Exception as exc:
            logger.warning('Market task %s failed: %s',task['kind'],type(exc).__name__)
            self.finish_failure(task,exc)
        else:
            self.repo.finish(task['id'],task['claim_version'],'complete')
        return True

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.repo.recover_running(self.profile,kinds=self.kinds,exclude_kinds=self.exclude_kinds)
        self._stop.clear()
        def run():
            while not self._stop.is_set():
                if not self.run_one():
                    self._wake.wait(1)
                    self._wake.clear()
        self._thread=threading.Thread(target=run,daemon=True,name='a-share-market-queue')
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
