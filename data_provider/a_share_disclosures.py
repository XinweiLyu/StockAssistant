"""CNINFO metadata and bounded original PDF extraction; no model calls."""
from __future__ import annotations

import re
import json
import subprocess
import sys
from urllib.parse import urlsplit, parse_qs

from src.schemas.a_share_integrated import digest, stamp


def disclosure_pdf_url(url, published_day):
    parsed = urlsplit(str(url))
    if (parsed.scheme not in ('http', 'https') or parsed.hostname not in
            ('www.cninfo.com.cn', 'static.cninfo.com.cn') or parsed.username or parsed.password
            or parsed.port not in (None, 443) or '..' in parsed.path):
        raise ValueError('仅允许巨潮官方公告地址')
    if parsed.hostname == 'static.cninfo.com.cn':
        if not re.fullmatch(r'/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF', parsed.path, re.I):
            raise ValueError('公告PDF路径无效')
        stamp(parsed.path.split('/')[2])
        return 'https://static.cninfo.com.cn' + parsed.path
    identity = parse_qs(parsed.query).get('announcementId', [''])[0]
    if not identity.isdigit() or parsed.path != '/new/disclosure/detail':
        raise ValueError('缺少公告ID')
    day = stamp(str(published_day)[:10])[:10]
    return f'https://static.cninfo.com.cn/finalpage/{day}/{identity}.PDF'


def report_period(title):
    year = re.search(r'(20\d{2})年', title)
    if not year:
        return None
    suffix = '06-30' if '半年度' in title or '中期' in title else '03-31' if '一季度' in title else '09-30' if '三季度' in title else '12-31' if '年度' in title else None
    return f'{year[1]}-{suffix}' if suffix else None


def normalize_disclosures(code, rows, observed_at):
    output, seen = [], set()
    for row in rows:
        actual = str(row.get('代码', row.get('ts_code', code)))[:6]
        if actual != code:
            raise ValueError('公告股票身份不一致')
        title = str(row.get('公告标题', row.get('title', ''))).strip()
        published = stamp(row.get('公告时间', row.get('ann_date')))
        url = row.get('公告链接', row.get('url'))
        if not title or not published or not url:
            continue
        # Keep a clickable original disclosure entry; download paths are derived separately.
        disclosure_pdf_url(url, published[:10])
        url = 'https://' + str(url).split('://', 1)[1]
        family = parse_qs(urlsplit(url).query).get('announcementId', [url])[0]
        event_id = digest([code, family])
        if event_id in seen:
            continue
        seen.add(event_id)
        kind = ('earnings' if any(w in title for w in ('业绩', '年度报告', '季度报告')) else
                'buyback' if '回购' in title else 'ownership' if any(w in title for w in ('增持', '减持')) else
                'order' if any(w in title for w in ('合同', '订单', '产能')) else
                'regulatory' if any(w in title for w in ('诉讼', '处罚', '立案', '监管')) else 'disclosure')
        period = report_period(title)
        subtype = 'guidance' if '预告' in title else 'flash' if '快报' in title else 'report'
        family_id = digest([code,kind,period,subtype]) if kind == 'earnings' and period else event_id
        output.append(dict(id=event_id, code=code, family_id=family_id, title=title, kind=kind,
                           direction='unknown', intensity=None, intensity_unit=None,
                           report_period=period, published_at=published,
                           observed_at=observed_at, available_at=max(stamp(observed_at), published),
                           source='cninfo', url=url, text_status='missing', text='',
                           text_hash=None, verified=False, vintage_quality='reconstructed',
                           date_precision='date', mixed_events=False))
    return sorted(output, key=lambda e: e['published_at'], reverse=True)


def extract_pdf_bytes(data, max_bytes=8388608, max_pages=80):
    if len(data) > max_bytes or not data.startswith(b'%PDF-'):
        return dict(status='failed', text='', reason='非PDF或超过公告大小上限')
    worker = """
import sys,json,io
from pypdf import PdfReader
r=PdfReader(io.BytesIO(sys.stdin.buffer.read()),strict=False)
count=len(r.pages)
if count>int(sys.argv[1]):
 print(json.dumps({'status':'failed','text':'','pages':count,'reason':'公告页数超过上限'}))
else:
 parts=[]
 for page in r.pages:
  parts.append((page.extract_text() or '')[:30000])
  if sum(map(len,parts))>200000: break
 text='\\n'.join(parts)[:200000]
 print(json.dumps({'status':'ready' if text.strip() else 'missing','text':text,'pages':count,
 'truncated':len(text)>=200000,'reason':'' if text.strip() else 'PDF无可提取文本，可能为扫描件'},ensure_ascii=False))
"""
    try:
        result = subprocess.run([sys.executable, '-c', worker, str(max_pages)], input=data,
                                capture_output=True, check=True, timeout=15)
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, ValueError):
        return dict(status='failed', text='', reason='PDF解析未完成或超时')


def fetch_disclosure_text(url, published_day=None, max_bytes=8388608, max_pages=80):
    import requests
    try:
        target = disclosure_pdf_url(url, published_day)
        with requests.get(target, timeout=(5, 12), stream=True, allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('不接受公告下载重定向')
            content = bytearray()
            for part in response.iter_content(65536):
                content.extend(part)
                if len(content) > max_bytes:
                    raise ValueError('公告大小超过上限')
        result = extract_pdf_bytes(bytes(content), max_bytes, max_pages)
        return result | dict(url=target, content_hash=digest(bytes(content).hex()))
    except (ValueError, requests.RequestException):
        return dict(status='failed', text='', reason='官方公告未下载成功或地址不受支持')
