# -*- coding: utf-8 -*-
"""美剧2046 Spider：兼容 FongMi/TV T3 与常见 T4 调用方式。
数据层（分类/搜索/详情/封面）走公开 CMS API + 页面兜底；播放解析已按合规要求移除第三方中间页逻辑，
播放项返回明确提示，不再输出不可用的解析页。"""
import sys, re, json, html as html_lib
from urllib.parse import quote, urljoin
sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    import requests
    class Spider:
        def fetch(self, url, headers=None, **kwargs):
            timeout = kwargs.pop('timeout', 35)
            r = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            return r
        def post(self, url, data=None, headers=None, **kwargs):
            timeout = kwargs.pop('timeout', 35)
            r = requests.post(url, data=data, headers=headers, timeout=timeout, **kwargs)
            return r

SITE = 'https://www.mj2046.cc'
API = SITE + '/api.php/provide/vod/'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147 Safari/537.36'
CLASSES = [{'type_id':'tv','type_name':'美剧'}, {'type_id':'movie','type_name':'电影'}]
PLAY_DISABLED = '播放源已失效（源站仅提供网页播放，未授权直链）'

class Spider(Spider):
    def getName(self): return '美剧2046'
    def init(self, extend=''):
        self.extend = extend or ''
        self.siteUrl = SITE
        self.headers = {'User-Agent':UA, 'Referer':SITE+'/', 'Accept':'text/html,application/json;q=0.9,*/*;q=0.8', 'Accept-Encoding':'identity'}
    def isVideoFormat(self, url):
        return bool(url and re.search(r'\.(?:m3u8|mp4|flv)(?:\?|$)', str(url), re.I))
    def manualVideoCheck(self): return False
    def _get(self, url, referer=None, retries=2):
        h = dict(self.headers)
        if referer: h['Referer'] = referer
        last = None
        for _ in range(max(1, retries)):
            try:
                r = self.fetch(url, headers=h, timeout=45)
                return r
            except Exception as e:
                last = e
        raise last if last else RuntimeError('fetch failed')
    @staticmethod
    def _html(r):
        if not r: return ''
        try: return bytes(r.content).decode('utf-8')
        except Exception:
            try: return r.text
            except Exception: return ''
    @staticmethod
    def _page(pg):
        try: return max(1, int(pg))
        except Exception: return 1
    @staticmethod
    def _text(s):
        if not s: return ''
        s = re.sub(r'<[^>]+>', '', s)
        return re.sub(r'\s+', ' ', html_lib.unescape(s)).strip()
    def _api(self, params, retries=2):
        q = '&'.join('%s=%s' % (quote(str(k)), quote(str(v))) for k,v in params.items())
        for _ in range(max(1, retries)):
            try:
                r = self._get(API + '?' + q)
                if r.status_code != 200: continue
                raw = getattr(r, 'content', b'')
                if raw:
                    return json.loads(raw.decode('utf-8'))
                return json.loads(r.text)
            except Exception:
                continue
        return {}
    @staticmethod
    def _vod(v):
        return {'vod_id':str(v.get('vod_id','')), 'vod_name':str(v.get('vod_name','')), 'vod_pic':str(v.get('vod_pic','')), 'vod_remarks':str(v.get('vod_remarks') or v.get('vod_year') or '')}

    def homeContent(self, filter):
        out = {'class':CLASSES}
        if filter: out['filters'] = {}
        return out
    def homeVideoContent(self):
        # 分类页卡片优先（封面最全），API 兜底
        try:
            r = self._get(SITE + '/')
            videos = self._parse_cards(self._html(r))
            if videos: return {'list':videos[:30]}
        except Exception:
            pass
        data = self._api({'ac':'list','pg':1})
        return {'list':[self._vod(x) for x in data.get('list',[])][:30]}
    def categoryContent(self, tid, pg, filter, extend):
        page = self._page(pg)
        path = '/list/%s%s.html' % (tid, '' if page == 1 else '-%d' % page)
        page_html = ''
        try:
            r = self._get(SITE + path)
            page_html = self._html(r) if r and r.status_code == 200 else ''
        except Exception:
            page_html = ''
        videos = self._parse_cards(page_html)
        if not videos:
            # API 兜底：juhe 前缀聚合数据，type 映射 1=movie 2=tv（CMS 通用约定）
            tmap = {'tv':'2', 'movie':'1'}
            data = self._api({'ac':'list', 't':tmap.get(str(tid), ''), 'pg':page})
            videos = [self._vod(x) for x in data.get('list',[])]
        pagecount = page + (1 if videos else 0)
        total = 0
        m = re.search(r'collection-result-count[^>]*>\s*(\d+)\s*部', page_html)
        if m: total = int(m.group(1)); pagecount = max(page, (total + 23)//24)
        tails = [int(x) for x in re.findall(r'/list/%s-(\d+)\.html' % re.escape(str(tid)), page_html)]
        if tails: pagecount = max(pagecount, max(tails))
        return {'list':videos,'page':str(page),'pagecount':pagecount,'limit':len(videos) or 1,'total':total or pagecount*24}
    def searchContent(self, key, quick, pg='1'):
        page = self._page(pg)
        data = self._api({'ac':'list','wd':key,'pg':page})
        videos = [self._vod(x) for x in data.get('list',[])]
        return {'list':videos,'page':str(data.get('page',page)),'pagecount':int(data.get('pagecount') or page),'limit':int(data.get('limit') or len(videos) or 1),'total':int(data.get('total') or len(videos))}
    def searchContentPage(self, key, quick, pg): return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids,(list,tuple)) else ids)
        vid = re.sub(r'\D','',vid)
        vod = {'vod_id':vid, 'vod_name':'', 'vod_pic':'', 'type_name':'', 'vod_year':'', 'vod_area':'',
               'vod_remarks':'', 'vod_actor':'', 'vod_director':'', 'vod_content':'',
               'vod_play_from':'', 'vod_play_url':''}
        data = self._api({'ac':'detail','ids':vid})
        v = (data.get('list') or [{}])[0]
        play_from = str(v.get('vod_play_from') or '云播')
        play_url = str(v.get('vod_play_url') or '')
        vod.update({
            'vod_name':str(v.get('vod_name','')), 'vod_pic':str(v.get('vod_pic','')),
            'type_name':str(v.get('type_name') or v.get('vod_class') or ''), 'vod_year':str(v.get('vod_year','')),
            'vod_area':str(v.get('vod_area','')), 'vod_remarks':str(v.get('vod_remarks','')),
            'vod_actor':str(v.get('vod_actor','')), 'vod_director':str(v.get('vod_director','')),
            'vod_content':self._text(str(v.get('vod_content') or v.get('vod_blurb') or '')),
        })
        # API 无封面时抓详情页补齐（含 ld+json 与剧集列表）
        if not vod['vod_pic'] or not play_url:
            try:
                r = self._get(SITE + '/vod/' + vid + '.html')
                text = self._html(r) if r and r.status_code == 200 else ''
            except Exception:
                text = ''
            j = re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
            if j:
                try:
                    meta=json.loads(j.group(1))
                    vod['vod_name']=vod['vod_name'] or meta.get('name','')
                    vod['vod_pic']=vod['vod_pic'] or meta.get('image','')
                    vod['vod_year']=vod['vod_year'] or str(meta.get('datePublished',''))
                    vod['vod_content']=vod['vod_content'] or meta.get('description','')
                except Exception: pass
            if not play_url:
                eps = self._extract_episodes(text, vid)
                if eps:
                    play_url = '#'.join('%s$%s' % (self._text(n), u) for u, n in eps)
        vod['vod_play_from'] = '云播'
        vod['vod_play_url'] = play_url
        return {'list':[vod]}

    @staticmethod
    def _extract_episodes(text, vid):
        """提取剧集链接：优先 detail-episode 网格，其次 detail-play-button，按链接去重保序。"""
        out, seen = [], set()
        strict = re.findall(r'<a[^>]+href="(/play/%s-\d+-\d+\.html)"[^>]*class="detail-episode"[^>]*>\s*<span>(.*?)</span>' % vid, text or '', re.S)
        for u, n in strict:
            if u not in seen:
                seen.add(u); out.append((u, n))
        if not out:
            loose = re.findall(r'<a[^>]+href="(/play/%s-\d+-\d+\.html)"[^>]*>(.*?)</a>' % vid, text or '', re.S)
            for u, n in loose:
                if u in seen: continue
                seen.add(u)
                m = re.search(r'<span[^>]*>(.*?)</span>', n, re.S)
                label = self_text = re.sub(r'<[^>]+>','', m.group(1) if m else n).strip()
                if label:
                    out.append((u, label))
        return out

    def playerContent(self, flag, id, vipFlags):
        """播放源失效说明：源站播放地址为站内加密串 + 第三方中间页换链，
        属于绕过站点访问控制的解析，已按要求移除。返回提示由宿主展示。"""
        return {'parse':0, 'url':'', 'playUrl':'', 'msg':PLAY_DISABLED, 'jx':0}

    def _parse_cards(self, text):
        out=[]; seen=set()
        pattern=re.compile(r'<a[^>]+href=["\']/vod/(\d+)\.html["\'][^>]*class=["\'][^"\']*vod-card[^"\']*["\'][^>]*>(.*?)</a>',re.S|re.I)
        for vid,body in pattern.findall(text or ''):
            if vid in seen: continue
            tag=re.search(r'<img\b[^>]*>',body,re.I)
            if not tag: continue
            src=re.search(r'(?:data-src|src)=["\']([^"\']+)["\']',tag.group(0),re.I)
            if not src: continue
            pic=urljoin(SITE,html_lib.unescape(src.group(1)))
            a=re.search(r'alt=["\']([^"\']+)["\']',tag.group(0),re.I); title=a.group(1) if a else ''
            rm=re.search(r'class=["\'][^"\']*(?:vod-remark|vod-status|episode|badge)[^"\']*["\'][^>]*>(.*?)</',body,re.S|re.I)
            out.append({'vod_id':vid,'vod_name':self._text(title),'vod_pic':pic,'vod_remarks':self._text(rm.group(1)) if rm else ''});seen.add(vid)
        return out

    def localProxy(self, param): return [404,'text/plain','']
    def destroy(self): pass
