# -*- coding: utf-8 -*-
"""
片库 (4k01.pianku.online) — CatVod Spider，兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4)

站点形态
  苹果CMS 风格模板，服务端渲染 HTML（无 JSON API），全部靠正则提取。

页面链路
  首页        GET /                                  若干 vod-list-section（电影/剧集/动漫/综艺/B站…）
  分类/分页   GET /vodtype/{tid}.html                GET /vodtype/{tid}-{page}.html
  搜索        GET /vodsearch/-------------.html?wd={kw}&page={pg}
  详情        GET /voddetail/{vid}.html              基本信息 + 多个播放源 tab + 每源集数
  播放        GET /vodplay/{vid}-{sid}-{nid}.html    页面里 var player_aaaa = {...} 含真实 url / from

播放的两类情况（关键）
  1) 自营源  from = jlm3u8 / mjzy  ->  url 本身就是 m3u8 直链
             https://jimaoys94.com/public/playback/<hash>/smart.m3u8
             实测 200、TS 为 https 绝对地址、首字节 0x47，直接可播。
  2) 官网源  from = qq / qiyi / youku / bilibili / mgtv
             url 是 v.qq.com / iqiyi.com / bilibili.com 的网页地址，
             站点自己也是丢给第三方解析站（tv.time1080.xyz 及它下面 9 条 iframe 线路）
             —— 那些解析站带域名授权校验 + 反调试，Spider 里硬解不了。
             所以这类直接 parse=1 交回壳子解析（TVBox/FongMi 内置有对应解析器）。

  实测 35 个样本：约 20% 的片子带自营直链源，其余只有官网源。
  详情里会把「自营」直链源排到最前面，能直播的优先。

其他说明
  - 分类页只有子分类筛选，没有地区/年份/排序参数，所以不给 filters。
  - 首页推荐按 section 合并去重，最多 60 条。
"""
import sys
import re
import json
import base64
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider
except ImportError:
    import requests as rq

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=20, **kw)
            r.encoding = 'utf-8'
            return r

        def post(self, url, data=None, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.post(url, data=data, headers=headers, timeout=20, **kw)
            r.encoding = 'utf-8'
            return r


# ==================== 常量 ====================
HOST = "https://4k01.pianku.online"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

TIMEOUT = 20
RETRY = 2

# 分类（子分类也是独立 tid，直接平铺，站上没有其他筛选参数）
CLASSES = [
    ("电影", "20"), ("动作片", "21"), ("喜剧片", "22"), ("爱情片", "23"),
    ("科幻片", "24"), ("恐怖片", "25"), ("剧情片", "26"), ("战争片", "27"),
    ("惊悚片", "28"), ("犯罪片", "29"), ("冒险片", "30"), ("动画片", "31"),
    ("悬疑片", "32"), ("武侠片", "33"), ("奇幻片", "34"), ("纪录片", "35"),
    ("其他片", "36"),
    ("连续剧", "37"), ("国产剧", "38"), ("港台剧", "39"), ("欧美剧", "40"),
    ("日韩剧", "41"), ("其他剧", "42"),
    ("动漫", "43"), ("动漫片", "44"),
    ("综艺", "45"), ("综艺片", "46"),
    ("B站", "47"), ("番剧", "48"), ("国创", "49"), ("电影(B站)", "50"), ("电视剧(B站)", "51"),
]

# 采集源（url 多为直链），排序时优先
DIRECT_FROMS = ("jlm3u8", "mjzy", "wsym3u8", "360zy")
DIRECT_HOST_HINT = ("jimaoys", "mujizy", "wsyzy", "maccms.xyz")

HOME_MAX = 60

# ===== 正则 =====
RE_ITEM = re.compile(
    r'<div class="vod-item">\s*<a href="/voddetail/(\d+)\.html"[^>]*?title="([^"]*)"[^>]*>'
    r'(.*?)</a>\s*</div>', re.S)

RE_IMG = re.compile(r'<img[^>]*?(?:data-src|data-original|src)="([^"]+)"', re.S)

RE_REMARK = re.compile(r'<span class="remarks">(.*?)</span>', re.S)
RE_TITLE = re.compile(r'<h4 class="title">(.*?)</h4>', re.S)
RE_SUB = re.compile(r'<p class="subtitle">(.*?)</p>', re.S)

RE_SECTION = re.compile(r'<section class="vod-list-section".*?<h2>(.*?)</h2>(.*?)</section>', re.S)

RE_POSTER = re.compile(r'<div class="detail-poster">\s*<img src="([^"]+)"', re.S)
RE_DTITLE = re.compile(r'<h1 class="detail-title">(.*?)(?:<span class="detail-remarks">(.*?)</span>)?</h1>', re.S)
RE_DESC = re.compile(r'<div class="detail-desc">.*?<p>(.*?)</p>', re.S)
RE_META = re.compile(r'<span>([^<：]{2,6})：([^<]*)</span>', re.S)

RE_TAB = re.compile(r'data-target="playlist-(\d+)">([^<]+)</span>', re.S)
RE_PANE = re.compile(
    r'<div class="source-pane[^"]*" id="playlist-(\d+)">((?:(?!<div class="source-pane).)*)', re.S)
RE_EP = re.compile(r'href="/vodplay/(\d+)-(\d+)-(\d+)\.html"[^>]*>([^<]*)</a>', re.S)

RE_PLAYER = re.compile(r'var player_aaaa=(\{.*?\})</script>', re.S)


def _txt(s):
    """去标签 + 常用实体 + 空白压缩"""
    if s is None:
        return ''
    s = re.sub(r'<[^>]+>', '', str(s))
    s = (s.replace('&nbsp;', ' ').replace('&amp;', '&')
          .replace('&quot;', '"').replace('&#39;', "'")
          .replace('&lt;', '<').replace('&gt;', '>'))
    return re.sub(r'\s+', ' ', s).strip()


class Spider(Spider):
    """片库 Spider"""

    def getName(self):
        return "片库"

    def init(self, extend=""):
        self.extend = '' if isinstance(extend, list) else (extend or '')
        self.host = HOST
        self._proxy = None   # 代理基址缓存（仅 http 明文源才用得上）
        self._pb_cache = {}

    # ---------- 基础请求 ----------
    def _headers(self, referer=None):
        h = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        if referer:
            h['Referer'] = referer
        return h

    def _get(self, path_or_url, referer=None, retry=RETRY):
        """返回 HTML 文本，失败返回 ''"""
        url = path_or_url if path_or_url.startswith('http') else (self.host + path_or_url)
        for i in range(retry + 1):
            try:
                rsp = self.fetch(url, headers=self._headers(referer), timeout=TIMEOUT)
            except Exception:
                rsp = None
            if rsp is None:
                continue
            code = getattr(rsp, 'status_code', 200) or 200
            if code >= 400:
                continue
            try:
                text = rsp.text
            except Exception:
                text = ''
            if not text and getattr(rsp, 'content', None):
                try:
                    text = rsp.content.decode('utf-8', 'ignore')
                except Exception:
                    text = ''
            if text:
                return text
        return ''

    # ---------- 列表解析 ----------
    @staticmethod
    def _parse_items(html):
        """解析 vod-item 卡片 -> vod dict 列表"""
        out = []
        seen = set()
        if not html:
            return out
        for m in RE_ITEM.finditer(html):
            vid, title_attr, block = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            img = ''
            im = RE_IMG.search(block)
            if im:
                img = im.group(1)
                if img.endswith('/load.gif') or img == '/load.gif':
                    img = ''
            rm = RE_REMARK.search(block)
            tm = RE_TITLE.search(block)
            sm = RE_SUB.search(block)
            title = _txt(tm.group(1)) if tm else _txt(title_attr)
            if not title:
                continue
            sub = _txt(sm.group(1)) if sm else ''
            year = ''
            area = ''
            if sub:
                parts = [x.strip() for x in sub.split('/')]
                if parts and re.match(r'^\d{4}$', parts[0]):
                    year = parts[0]
                if len(parts) > 1:
                    area = parts[1]
            out.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': img,
                'vod_remarks': _txt(rm.group(1)) if rm else (year or ''),
                'vod_year': year,
                'vod_area': area,
            })
        return out

    # ---------- 首页 ----------
    def homeContent(self, filter):
        result = {'class': [{'type_name': n, 'type_id': t} for n, t in CLASSES]}
        if filter:
            result['filters'] = {}
        html = self._get('/')
        videos = []
        if html:
            # 精选推荐
            i = html.find('recommend-overlay')
            if i > 0:
                seg = html[i:html.find('</section>', i)]
                videos += self._parse_items(seg)
            # 各分类 section
            for m in RE_SECTION.finditer(html):
                videos += self._parse_items(m.group(2))
            # 兜底：整页解析
            if not videos:
                videos += self._parse_items(html)
        # 去重
        uniq = []
        seen = set()
        for v in videos:
            if v['vod_id'] in seen:
                continue
            seen.add(v['vod_id'])
            uniq.append(v)
        result['list'] = uniq[:HOME_MAX]
        return result

    def homeVideoContent(self):
        return {'list': []}

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        tid = str(tid or '20').strip()
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        path = '/vodtype/%s.html' % tid if pg <= 1 else '/vodtype/%s-%d.html' % (tid, pg)
        html = self._get(path)
        return {'list': self._parse_items(html), 'page': pg, 'pagecount': 9999,
                'limit': 30, 'total': 999999}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg='1'):
        key = (key or '').strip()
        if not key:
            return {'list': []}
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        path = '/vodsearch/-------------.html?wd=%s&page=%d' % (quote(key), pg)
        html = self._get(path, referer=self.host + '/')
        return {'list': self._parse_items(html), 'page': pg}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        vid = str((ids or [''])[0]).strip()
        if not vid:
            return {'list': []}
        html = self._get('/voddetail/%s.html' % vid)
        if not html:
            return {'list': []}

        poster = ''
        pm = RE_POSTER.search(html)
        if pm:
            poster = pm.group(1)

        title, remarks = '', ''
        tm = RE_DTITLE.search(html)
        if tm:
            title = _txt(tm.group(1))
            remarks = _txt(tm.group(2) or '')

        meta = {}
        for m in RE_META.finditer(html):
            k, v = _txt(m.group(1)), _txt(m.group(2))
            if k and v and k not in meta:
                meta[k] = v
        # 分类那项带 <a>，上面正则会吃掉标签内的文字，单独补
        cm = re.search(r'分类：<a href="/vodtype/\d+\.html">([^<]*)</a>', html)
        if cm:
            meta['分类'] = _txt(cm.group(1))

        desc = ''
        dm = RE_DESC.search(html)
        if dm:
            desc = _txt(dm.group(1))

        year = meta.get('年份', '')
        area = meta.get('地区', '')
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': poster,
            'vod_year': year,
            'vod_area': area,
            'vod_remarks': remarks or meta.get('备注', ''),
            'vod_actor': meta.get('主演', ''),
            'vod_director': meta.get('导演', ''),
            'vod_content': desc,
            'type_name': meta.get('分类', ''),
        }

        # ---- 播放源 ----
        names = {}
        for m in RE_TAB.finditer(html):
            names[m.group(1)] = _txt(m.group(2))
        groups = []
        for m in RE_PANE.finditer(html):
            sid = m.group(1)
            eps = []
            for e in RE_EP.finditer(m.group(2)):
                if e.group(1) != vid:
                    continue
                eps.append('%s$%s-%s-%s' % (_txt(e.group(4)) or ('第%s集' % e.group(3)),
                                            vid, e.group(2), e.group(3)))
            if not eps:
                continue
            groups.append((sid, names.get(sid, ('源%s' % sid)), eps))

        # 自营直链源排前面
        def _rank(g):
            nm = g[1]
            return 0 if ('自营' in nm or '4K' in nm) else 1
        groups.sort(key=_rank)

        if groups:
            vod['vod_play_from'] = '$$$'.join(g[1] for g in groups)
            vod['vod_play_url'] = '$$$'.join('#'.join(g[2]) for g in groups)
        else:
            vod['vod_play_from'] = ''
            vod['vod_play_url'] = ''
        return {'list': [vod]}

    # ---------- 播放 ----------
    @staticmethod
    def _decode_url(url, enc):
        try:
            if str(enc) == '1':
                return unquote(url)
            if str(enc) == '2':
                return unquote(base64.b64decode(unquote(url)).decode('utf-8', 'ignore'))
        except Exception:
            pass
        return url

    def playerContent(self, flag, id, vipFlags):
        pid = str(id or '').strip()
        # pid 形如 vid-sid-nid
        m = re.match(r'^(\d+)-(\d+)-(\d+)$', pid)
        if not m:
            return {}
        html = self._get('/vodplay/%s.html' % pid)
        if not html:
            return {}
        pm = RE_PLAYER.search(html)
        if not pm:
            return {}
        try:
            data = json.loads(pm.group(1))
        except Exception:
            return {}

        url = self._decode_url(str(data.get('url') or '').strip(), data.get('encrypt'))
        if not url:
            return {}
        frm = str(data.get('from') or '').strip().lower()
        lu = url.lower()

        # 直链判定
        is_direct = False
        if url.startswith('http'):
            if any(x in lu for x in ('.m3u8', '.mp4', '.flv', '.m4a', 'm3u8?')):
                is_direct = True
            elif frm in DIRECT_FROMS or any(h in lu for h in DIRECT_HOST_HINT):
                is_direct = True

        if not is_direct:
            # 官网源：交回壳子解析
            return {
                'parse': 1,
                'playUrl': '',
                'url': url,
                'header': {'User-Agent': UA, 'Referer': self.host + '/'},
            }

        url = self._proxify(url)
        out = {
            'parse': 0,
            'playUrl': '',
            'url': url,
            'header': {'User-Agent': UA, 'Referer': self.host + '/'},
        }
        if '.m3u8' in lu:
            out['format'] = 'application/x-mpegURL'
            out['contentType'] = 'application/x-mpegURL'
        return out

    # ---------- 代理（仅 http 明文源需要；采集源基本都是 https） ----------
    def _proxy_base(self):
        if self._proxy is not None:
            return self._proxy
        base = ''
        try:
            if hasattr(self, 'getProxyUrl'):
                base = self.getProxyUrl() or ''
        except Exception:
            base = ''
        self._proxy = base
        return base

    def _proxify(self, url):
        url = str(url or '').strip()
        if not url.lower().startswith('http://'):
            return url
        base = self._proxy_base()
        if not base:
            return url
        if base.rstrip().endswith('url='):
            return base + quote(url, safe='')
        sep = '&' if '?' in base else '?'
        return base + sep + 'url=' + quote(url, safe='')

    def localProxy(self, param):
        """m3u8 相对路径改写 + 二进制透传"""
        try:
            import urllib.parse as up
            raw = ''
            if isinstance(param, dict):
                raw = param.get('url', '') or param.get('u', '')
            elif isinstance(param, str):
                p = param.strip()
                if '?' in p:
                    p = p.split('?', 1)[1]
                qs = up.parse_qs(p)
                raw = (qs.get('url') or qs.get('u') or [''])[0]
                if not raw and p.lower().startswith('http'):
                    raw = p
            media_url = up.unquote(raw) if raw else ''
            if not media_url:
                return [404, 'text/plain', b'']

            rsp = self.fetch(media_url, headers={'User-Agent': UA}, timeout=30)
            content = rsp.content if hasattr(rsp, 'content') else str(getattr(rsp, 'text', '') or '').encode('utf-8')
            try:
                text = content.decode('utf-8')
            except Exception:
                return [200, 'application/octet-stream', content]
            if '#EXTM3U' not in text:
                return [200, 'application/octet-stream', content]

            sp = urlsplit(media_url)
            base = urlunsplit((sp.scheme, sp.netloc, '', '', ''))
            query = ('?' + sp.query) if sp.query else ''
            out = []
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith('#'):
                    out.append(line)
                    continue
                if s.startswith('/'):
                    s = base + s + query
                elif not s.lower().startswith('http'):
                    s = urljoin(media_url, s)
                out.append(s)
            return [200, 'application/x-mpegURL; charset=utf-8', '\n'.join(out).encode('utf-8')]
        except Exception:
            return [500, 'text/plain', b'proxy error']

    def destroy(self):
        pass


# ==================== 自测 ====================
if __name__ == '__main__':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    s = Spider()
    s.init()
    ok = fail = 0

    def chk(name, cond, extra=''):
        global ok, fail
        if cond:
            ok += 1
            print('[OK] %-28s %s' % (name, extra))
        else:
            fail += 1
            print('[!!] %-28s %s' % (name, extra))

    print('=== homeContent ===')
    h = s.homeContent(True)
    hl = h.get('list', [])
    chk('首页有数据', len(hl) > 0, '%d 条' % len(hl))
    chk('首页有分类', len(h.get('class', [])) > 10, '%d 个' % len(h.get('class', [])))
    chk('首页有封面', sum(1 for v in hl if v.get('vod_pic')) > 0,
        '%d/%d' % (sum(1 for v in hl if v.get('vod_pic')), len(hl)))
    if hl:
        print('    sample:', hl[0]['vod_name'], '|', hl[0]['vod_remarks'], '|', hl[0]['vod_pic'][:60])

    print('\n=== categoryContent ===')
    for tid, nm in [('20', '电影'), ('38', '国产剧'), ('48', '番剧'), ('45', '综艺')]:
        c = s.categoryContent(tid, '1', True, {})
        chk('分类 %s(%s)' % (nm, tid), len(c.get('list', [])) > 0, '%d 条' % len(c.get('list', [])))
    c2 = s.categoryContent('20', '2', True, {})
    chk('分类第2页', len(c2.get('list', [])) > 0, '%d 条' % len(c2.get('list', [])))
    if c2.get('list') and hl:
        same = c2['list'][0]['vod_id'] == (s.categoryContent('20', '1', True, {}).get('list') or [{}])[0].get('vod_id')
        chk('第2页内容与第1页不同', not same)

    print('\n=== searchContent ===')
    sr = s.searchContent('庆余年', False, '1')
    chk('搜索有结果', len(sr.get('list', [])) > 0, '%d 条' % len(sr.get('list', [])))
    if sr.get('list'):
        print('    ', [v['vod_name'] for v in sr['list'][:5]])

    print('\n=== detailContent ===')
    vid = (sr.get('list') or hl or [{}])[0].get('vod_id') or (hl[0]['vod_id'] if hl else '')
    d = s.detailContent([vid])
    dt = (d.get('list') or [{}])[0]
    chk('详情标题', bool(dt.get('vod_name')), dt.get('vod_name', ''))
    chk('详情封面', bool(dt.get('vod_pic')), str(dt.get('vod_pic'))[:60])
    chk('详情简介', len(dt.get('vod_content') or '') > 10, '%d 字' % len(dt.get('vod_content') or ''))
    frms = dt.get('vod_play_from', '').split('$$$')
    chk('详情有播放源', len(frms) > 0, str(frms))
    print('    演员:', (dt.get('vod_actor') or '')[:40], '| 年份:', dt.get('vod_year'), '| 地区:', dt.get('vod_area'))

    print('\n=== playerContent（逐源） ===')
    groups = dt.get('vod_play_url', '').split('$$$')
    for i, fm in enumerate(frms):
        eps = (groups[i] if i < len(groups) else '').split('#')
        if not eps or not eps[0]:
            continue
        pid = eps[0].split('$', 1)[1]
        r = s.playerContent(fm, pid, [])
        u = r.get('url', '')
        tag = '直链' if r.get('parse') == 0 else '需解析'
        print('    [%s] %-6s parse=%s %s' % (tag, fm, r.get('parse'), u[:80]))
        if r.get('parse') == 0:
            try:
                import requests
                rr = requests.get(u, headers={'User-Agent': UA}, timeout=25)
                head = rr.text[:30].replace('\n', '|') if rr.status_code == 200 else ''
                chk('  直链可取 %s' % fm, rr.status_code == 200 and '#EXTM3U' in rr.text,
                    '%s %s' % (rr.status_code, head))
            except Exception as e:
                chk('  直链可取 %s' % fm, False, '%s %s' % (type(e).__name__, str(e)[:50]))
        else:
            chk('  官网源已回填 %s' % fm, u.startswith('http'), u[:60])

    print('\n=== 结果 ===')
    print('PASS=%d FAIL=%d' % (ok, fail))
