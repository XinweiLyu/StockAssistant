"""Isolate market workers/cache while retaining shared journal and usage accounting."""
from functools import wraps


class WorkspaceMarketRepository:
    PROFILE_METHODS={'set_state','get_state','states_with_prefix','replace_catalog','put_quotes','quotes','put_sectors',
        'sector','list_sectors','replace_members','members','ensure_members_task','stock','catalog_codes','associations',
        'list_stocks','replace_history','get_history','enqueue','enqueue_value_research','claim','tasks','pause','recover_running','progress'}

    def __init__(self,repo,market):self.base=repo;self.market=market;self.engine=repo.engine
    def physical(self,profile):return 'workspace-'+self.market+':'+profile
    def _logical_task(self,result):
        if isinstance(result,dict) and 'profile' in result:
            prefix='workspace-'+self.market+':'
            if not result['profile'].startswith(prefix):return None
            return result|dict(profile=result['profile'][len(prefix):])
        return result
    def task(self,identity):return self._logical_task(self.base.task(identity))
    def begin_value_attempt(self,task,snapshot_id):
        return self.base.begin_value_attempt(task|dict(profile=self.physical(task['profile'])),snapshot_id)
    def __getattr__(self,name):
        method=getattr(self.base,name)
        if name not in self.PROFILE_METHODS:return method
        @wraps(method)
        def call(profile,*args,**kwargs):
            result=method(self.physical(profile),*args,**kwargs)
            if name=='claim':return self._logical_task(result)
            if name=='tasks':return [self._logical_task(row) for row in result]
            return result
        return call
