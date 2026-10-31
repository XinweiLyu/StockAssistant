"""Same-board Eastmoney F10 membership fallback; publish only complete snapshots."""
import re
import time

import requests


def fetch_members(symbol):
    if not re.fullmatch(r'BK\d{4}', symbol):
        raise ValueError('东方财富板块代码无效')
    board = str(int(symbol[2:]))
    params = dict(reportName='RPT_F10_CORETHEME_BOARDTYPE',
                  columns='SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,BOARD_CODE,BOARD_NAME',
                  filter=f'(BOARD_CODE="{board}")', pageSize=500, pageNumber=1,
                  sortColumns='SECURITY_CODE', sortTypes='1', source='WEB', client='WEB')
    rows, seen = [], set()
    count = pages = None
    deadline = time.monotonic() + 28
    while pages is None or params['pageNumber'] <= pages:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('F10成分股分页超时，保留原缓存')
        response = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get',
                                params=dict(params), timeout=min(12, remaining), allow_redirects=False)
        response.raise_for_status()
        value = response.json()
        data = value.get('result') if value.get('success') is True else None
        if not isinstance(data, dict):
            raise ValueError('F10成分股未取得')
        total, page_count = data.get('count'), data.get('pages')
        if (not isinstance(total, int) or isinstance(total, bool) or not 0 < total <= 10000
                or not isinstance(page_count, int) or not 0 < page_count <= 20
                or (count is not None and (count, pages) != (total, page_count))):
            raise ValueError('F10成分股分页数量无效或变化')
        count, pages = total, page_count
        batch = data.get('data')
        if not isinstance(batch, list) or not batch:
            raise ValueError('F10成分股分页缺失')
        for row in batch:
            code = row.get('SECURITY_CODE')
            if (str(row.get('BOARD_CODE')) != board or not isinstance(code, str)
                    or not re.fullmatch(r'\d{6}', code) or code in seen):
                raise ValueError('F10成分股代码冲突或板块不匹配')
            seen.add(code)
            rows.append(row)
        params['pageNumber'] += 1
    if len(rows) != count:
        raise ValueError('F10成分股快照不完整，保留原缓存')
    return rows
