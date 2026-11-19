"""Bounded original filing retrieval from SEC/HKEXnews, never arbitrary URLs."""
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
from src.schemas.a_share_integrated import digest


def official_document_url(url):
    parsed=urlsplit(str(url))
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or '..' in parsed.path:
        raise ValueError('需要受支持的官方HTTPS原文')
    sec=parsed.hostname=='www.sec.gov' and re.fullmatch(r'/Archives/edgar/data/\d+/\d+/[^/]+\.(?:htm|html|txt|pdf)',parsed.path,re.I)
    hk=parsed.hostname in ('www1.hkexnews.hk','www.hkexnews.hk') and re.fullmatch(r'/listedco/listconews/sehk/\d{4}/\d{4}/[^/]+\.pdf',parsed.path,re.I)
    if not (sec or hk):raise ValueError('暂只自动读取SEC及港交所披露易的正式文件路径')
    return parsed.geturl()


class FilingText(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)


def fetch_official_document(url,user_agent=''):
    import requests
    target=official_document_url(url)
    if urlsplit(target).hostname=='www.sec.gov' and not user_agent:
        return dict(status='failed',text='',reason='SEC_USER_AGENT未配置')
    try:
        headers={'User-Agent':user_agent} if user_agent else {}
        with requests.get(target,headers=headers,timeout=(5,12),stream=True,allow_redirects=False) as response:
            response.raise_for_status()
            if response.status_code!=200:raise ValueError('不接受官方文件重定向或访问挑战')
            content=bytearray()
            for part in response.iter_content(65536):
                content.extend(part)
                if len(content)>8388608:raise ValueError('文件超过8MB')
        if content.startswith(b'%PDF-'):
            from data_provider.a_share_disclosures import extract_pdf_bytes
            parsed=extract_pdf_bytes(bytes(content),max_pages=250)
            if parsed['status']!='ready':return parsed
            text=parsed['text']
        else:
            parser=FilingText();parser.feed(bytes(content).decode('utf-8',errors='replace'));text=' '.join(parser.parts)
        text=re.sub(r'\s+',' ',text).strip()
        return dict(status='ready' if len(text)>=100 else 'missing',text=text[:400000],truncated=len(text)>400000,
            content_hash=digest(bytes(content).hex()),url=target)
    except (requests.RequestException,ValueError):return dict(status='failed',text='',reason='官方原文未取得或访问被限制，保留标题/摘要状态')
