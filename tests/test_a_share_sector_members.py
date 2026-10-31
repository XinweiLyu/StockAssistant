"""F10 membership snapshots must be complete and bound to one board."""
import pytest


def page(rows, count, pages):
    return dict(success=True, result=dict(data=rows, count=count, pages=pages))


def row(code, board='800'):
    return dict(SECURITY_CODE=code, BOARD_CODE=board, SECUCODE=code+'.SZ')


def test_f10_reads_all_pages_and_normalizes_leading_zero_board(monkeypatch):
    from data_provider.a_share_sector_members import fetch_members
    import requests
    responses = [page([row('000001')], 2, 2), page([row('000002')], 2, 2)]
    calls = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return responses.pop(0)
    def get(url, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(requests, 'get', get)
    assert [r['SECURITY_CODE'] for r in fetch_members('BK0800')] == ['000001', '000002']
    assert [c['params']['pageNumber'] for c in calls] == [1, 2]
    assert all(c['params']['filter'] == '(BOARD_CODE="800")' for c in calls)
    assert all(c['timeout'] <= 12 for c in calls)


@pytest.mark.parametrize('responses', [
    [page([row('000001', '477')], 1, 1)],
    [page([row('000001')], 2, 2), page([row('000001')], 2, 2)],
    [page([row('000001')], 2, 2), page([], 2, 2)],
    [page([row('000001')], 2, 2), page([row('000002')], 3, 2)],
    [page([], 0, 0)],
    [dict(success=False, result=None)],
    [page([row('not-a-code')], 1, 1)],
])
def test_f10_rejects_mixed_incomplete_or_empty_snapshots(monkeypatch, responses):
    from data_provider.a_share_sector_members import fetch_members
    import requests
    class Response:
        def raise_for_status(self): pass
        def json(self): return responses.pop(0)
    monkeypatch.setattr(requests, 'get', lambda *a, **k: Response())
    with pytest.raises(ValueError): fetch_members('BK0800')
