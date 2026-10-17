import importlib.util
from pathlib import Path
import requests


def test_poll_transient_disconnect_retries_only_read_and_never_paid_post(monkeypatch):
    spec=importlib.util.spec_from_file_location('research_smoke',Path('scripts/integrated-research-smoke.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    calls=[]
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return dict(accepted=True,status='running') if len(calls)==1 else dict(status='ready',bundle={},report=dict(forecasts=[{}],roles=[]))
    class Session:
        headers={}
        def request(self,method,url,timeout):
            calls.append(method)
            if len(calls)==2: raise requests.ConnectionError('transient')
            return Response()
    monkeypatch.setattr(module.requests,'Session',Session)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr('sys.argv',['smoke','--generate','--timeout','15'])
    assert module.main()==0
    assert calls==['POST','GET','GET']
