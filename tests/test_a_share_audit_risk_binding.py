"""Risk changes must invalidate cached research even when prices stay unchanged."""
import pytest

from tests.test_a_share_outlook_api import long_market
from tests.test_a_share_integrated_service import facts


def save_report(svc, bundle, valid_until='2099-12-31'):
    svc.repo.append('free','integrated_report','free:600000',dict(code='600000',
        data_hash=bundle['data_hash'],status='complete',plans=[dict(valid_until=valid_until)]))


def verify_risk(svc, monkeypatch):
    monkeypatch.setattr('src.services.a_share_service.now_local',svc.market.clock)
    svc.repo.add_event('free',dict(code='600000',source='fixture',title='已核实重大风险',
        published_at=svc.integrated._now(),content='人工核对的风险事实'))
    event=svc.repo.records('free','event')[0]
    svc.verify_event(event['id'],dict(code='600000',major_risk=True,note='原始公告已核对'))


def test_manual_risk_change_invalidates_report_without_changing_prices(tmp_path,monkeypatch):
    svc,_=long_market(tmp_path)
    bundle=svc.integrated.freeze('600000',facts())
    save_report(svc,bundle)
    assert not svc.integrated.get('600000')['report'].get('stale')
    verify_risk(svc,monkeypatch)
    state=svc.integrated.get('600000')
    assert state['status']=='stale'
    assert state['report']['stale']


def test_new_freeze_cannot_reuse_old_non_risk_bundle(tmp_path,monkeypatch):
    svc,_=long_market(tmp_path)
    old=svc.integrated.freeze('600000',facts())
    verify_risk(svc,monkeypatch)
    fresh=svc.integrated.freeze('600000',facts())
    assert fresh['data_hash']!=old['data_hash']
    assert fresh['context']['major_risk'] is True
    assert old['context'].get('major_risk') is not True


@pytest.mark.parametrize('patch',[{'st':True},{'identity_verified':False},{'board':'star'}])
def test_security_eligibility_change_invalidates_report(tmp_path,patch):
    svc,_=long_market(tmp_path)
    old=svc.integrated.freeze('600000',facts())
    save_report(svc,old)
    stock=svc.market.repo.stock('free','600000')
    svc.market.repo.replace_catalog('free','updated',[stock|patch])
    state=svc.integrated.get('600000')
    assert state['status']=='stale'
    assert state['report']['stale']


@pytest.mark.parametrize('value',['20240101','2024-W01-1','invalid',None])
def test_legacy_invalid_or_noncanonical_plan_date_cannot_look_current(tmp_path,value):
    svc,_=long_market(tmp_path)
    bundle=svc.integrated.freeze('600000',facts())
    save_report(svc,bundle,value)
    assert svc.integrated.get('600000')['report']['stale']


def test_legacy_missing_risk_snapshot_does_not_claim_a_verified_risk_change(tmp_path):
    svc,_=long_market(tmp_path)
    bundle=svc.integrated.freeze('600000',facts())
    bundle['context'].pop('eligibility_binding')
    svc.repo.append('free','research_bundle',bundle['data_hash'],bundle)
    state=svc.integrated.get('600000')
    assert state['status']=='stale'
    assert any('缺少证券资格与风险快照' in reason for reason in state['stale_reasons'])
    assert not any('重大风险已变化' in reason for reason in state['stale_reasons'])
