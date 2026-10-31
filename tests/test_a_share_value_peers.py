from src.services.a_share_value_peers import build_peer_comparison, select_economic_model


def peer(code, pe=14, **kwargs):
    return dict(code=code, industry_id='industry:x', economic_model='operating', verified=True,parent_equity=100,
                period='2026-06-30', metrics={'pe': pe, 'pb': 2, 'roe': .12},
                metric_basis={key:dict(date='2026-10-30',definition=key,source='fixture') for key in ('pe','pb','roe')}, **kwargs)


def test_peers_need_business_evidence_and_five_comparable_samples():
    target = peer('000001')
    candidates = [peer(str(i), v) for i, v in enumerate([10, 12, 14, 16, 18])]
    assert build_peer_comparison(target, candidates, [])['metrics']['pe']['n'] == 0
    confirmations = [dict(code=p['code'], evidence_ids=['business:'+p['code']]) for p in candidates]
    result = build_peer_comparison(target, candidates, confirmations)
    assert result['metrics']['pe']['median'] == 14
    assert result['metrics']['pe']['percentile'] == .6
    assert build_peer_comparison(target, candidates[:4], confirmations)['metrics']['pe']['percentile'] is None


def test_wrong_industry_period_and_losses_are_excluded():
    candidates = [peer('2', -4), peer('3') | dict(industry_id='other'), peer('4') | dict(period='2025-12-31')]
    result = build_peer_comparison(peer('1'), candidates, [dict(code=p['code'], evidence_ids=['B']) for p in candidates])
    assert result['metrics']['pe']['n'] == 0
    assert result['excluded']


def test_financial_industries_do_not_receive_generic_fcff():
    for name in ['银行', '证券', '保险', '多元金融']:
        model = select_economic_model({'name': name, 'classification': 'eastmoney-industry'}, [], None)
        assert 'fcff' not in model['allowed_methods']
    assert select_economic_model({'name': '无法识别的产业'}, [], None)['model'] == 'unresolved'
