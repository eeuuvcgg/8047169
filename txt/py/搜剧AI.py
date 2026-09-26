# -*- coding: utf-8 -*-
"""
搜剧AI (souju.ai) — CatVod Spider，兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4)
站点: https://souju.ai  (React SPA，数据走 /v1/* JSON API)

接口链路
  1. GET /v1/feed/home                      首页推荐（8 个 section）
  2. GET /v1/browse/catalog?kind=&page=&genre=&area=&year=&q=   分类/筛选/搜索
  3. GET /v1/catalog/{id}                   详情（自带 episodes，含播放 token）
  4. GET /v1/catalog/{id}/episodes          剧集（详情分页不足时兜底拉取）
  5. GET /v1/playback/resolve/{token}       播放解析 -> line_options[]（已是 m3u8 直链）

鉴权
  所有 /v1/ 请求需要 HMAC-SHA256 签名：
      msg  = f"{METHOD}\n{pathname}{search}\n{timestamp}\n{nonce}"
      sig  = HMAC_SHA256(secret, msg).hexdigest()
  并带 4 个固定头 + 3 个签名头（x-ai-movie-*）。

关于「官方线路」
  resolve 结果里权重最高（999）的那条是 1080P-官方R，url_kind=resolve_ticket、
  url=resolve://av_xxx（347 位一次性串），resolve_required=true。
  站点前端把它单独归为「官方线路」组（普通线路组标注"网络公开收集"），
  且 UI 上带「N 词元」角标 —— 即需要登录账号消耗词元额度才能解析。
  已验证：Web 端 JS 里没有任何解析该 ticket 的调用（只有 zod schema
  { ticket } -> playback.line.resolve，属于 App/native 通道），
  /v1/playback/* 下所有候选端点均 404/400，带匿名会话、换 client 标识都一样。
  所以 Spider 拿不到官方线路，只能给已解析的公开源。此处保留说明，勿再重复排查。

播放速度
  站点给的是"采集源质量权重"，不等于当前网络下的实际速度：
  实测同一集 6 个源首包延迟 0.18s ~ 7.08s，差 40 倍。
  所以默认开启播放前测速（并发探测候选源首包，最快的排第一），
  同一部剧只测一次并缓存顺序，连播不重复等。extend 里写 nospeed 可关闭。
"""
import sys
import json
import time
import hmac
import hashlib
import secrets
import re
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

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
HOST = "https://souju.ai"

SIGN_SECRET = "f39d73aa7a6426203cdee1ef17b31d3b7ea8c23f4c59c62a3a8aa0f39ee5e79d"

CLIENT_NAME = "movie-search-frontend"
CLIENT_VER = "1.0.0"
BUILD_VER = "aimovie-v2026.09.24.4-4f6353a71c35-4f6353a71c35-4f6353a71c35"
PROTO_VER = "2026-07-05.library-v2.playback-v1"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
PLAY_UA = UA

# content_kind -> 分类名
KINDS = [
    ("movie", "电影"),
    ("series", "剧集"),
    ("short_drama", "短剧"),
    ("anime", "动漫"),
    ("variety", "综艺"),
    ("documentary", "纪录片"),
    ("sports", "体育"),
]

GENRES = ["剧情", "喜剧", "动作", "爱情", "科幻", "悬疑", "犯罪", "恐怖",
          "动画", "纪录片", "武侠", "古装", "家庭", "战争", "奇幻",
          "冒险", "惊悚", "历史", "传记", "音乐", "运动", "短片"]

AREAS = ["中国大陆", "中国香港", "中国台湾", "美国", "韩国", "日本", "英国",
         "法国", "德国", "印度", "泰国", "俄罗斯", "意大利", "西班牙",
         "加拿大", "澳大利亚"]

PAGE_SIZE = 20
MAX_LINES = 12          # 单条线路最多拼接的备选源数量
MAX_PROVIDERS = 30      # 详情页最多暴露的线路数（站点单次可给 25+ 个源，别再砍成 8 个）
API_TIMEOUT = 25        # 单次请求超时（秒）
API_RETRY = 2           # 失败重试次数

# 播放前测速：并发探测候选源的首包延迟，把最快的排到最前面。
# 站点给的 preference_weight 是"采集源质量"权重，不等于当前网络下的实际速度，
# 所以默认线路常常不是最快的那个（表现就是"播放慢/卡顿"）。
SPEED_TEST_N = 6        # 最多探测几条
SPEED_TIMEOUT = 3.5     # 单条探测超时（秒）


class Spider(Spider):
    """搜剧AI Spider"""

    def getName(self):
        return "搜剧AI"

    def init(self, extend=""):
        self.extend = '' if isinstance(extend, list) else (extend or '')
        self.host = HOST
        self._pb = None          # 代理基址缓存
        self._sp = {}            # 测速结果缓存：同一部剧只测一次，连播不重复等

    # ========== 签名与请求 ==========

    @staticmethod
    def _nonce():
        return secrets.token_hex(16)

    @staticmethod
    def _sign(msg):
        return hmac.new(SIGN_SECRET.encode('utf-8'), msg.encode('utf-8'),
                        hashlib.sha256).hexdigest()

    def _hdr(self, path, search, method='GET'):
        ts = str(int(time.time() * 1000))
        nonce = self._nonce()
        sig = self._sign(f'{method}\n{path}{search}\n{ts}\n{nonce}')
        return {
            'User-Agent': UA,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'x-ai-movie-client-name': CLIENT_NAME,
            'x-ai-movie-client-version': CLIENT_VER,
            'x-ai-movie-build-version': BUILD_VER,
            'x-ai-movie-protocol-version': PROTO_VER,
            'x-ai-movie-timestamp': ts,
            'x-ai-movie-nonce': nonce,
            'x-ai-movie-signature': sig,
        }

    def _api(self, path, params=None, try_json=True):
        """path 需已编码；params 会拼成 query 并参与签名。
        站点偶发超时/5xx，失败自动重试，避免用户看到"播放失败"。"""
        search = ''
        if params:
            search = '?' + urlencode(params, encoding='utf-8')
        url = self.host + path + search
        last = None
        for attempt in range(API_RETRY + 1):
            try:
                rsp = self.fetch(url, headers=self._hdr(path, search), timeout=API_TIMEOUT)
            except Exception:
                rsp = None
            if rsp is None:
                last = None
            else:
                code = getattr(rsp, 'status_code', 200) or 200
                if code >= 400:
                    last = None
                elif not try_json:
                    return rsp
                else:
                    try:
                        text = (rsp.text if hasattr(rsp, 'text')
                                else str(rsp.content, 'utf-8', 'ignore'))
                        return json.loads(text)
                    except Exception:
                        last = None
            if attempt < API_RETRY:
                try:
                    time.sleep(0.5 + 0.4 * attempt)
                except Exception:
                    pass
        return last

    # ========== 首页 ==========

    def homeContent(self, filter):
        classes = [{'type_id': k, 'type_name': n} for k, n in KINDS]

        filters = {}
        for k, _n in KINDS:
            filters[k] = [
                {'key': 'genre', 'name': '类型',
                 'value': [{'n': '全部', 'v': ''}] + [{'n': g, 'v': g} for g in GENRES]},
                {'key': 'area', 'name': '地区',
                 'value': [{'n': '全部', 'v': ''}] + [{'n': a, 'v': a} for a in AREAS]},
                {'key': 'year', 'name': '年份',
                 'value': [{'n': '全部', 'v': ''}] +
                          [{'n': str(y), 'v': str(y)} for y in range(2026, 1989, -1)]},
            ]

        result = {'class': classes}
        if filter:
            result['filters'] = filters
        try:
            result['list'] = self.homeVideoContent().get('list', [])
        except Exception:
            result['list'] = []
        return result

    def homeVideoContent(self):
        data = self._api('/v1/feed/home')
        videos, seen = [], set()
        if data:
            for sec in data.get('sections', []) or []:
                for item in sec.get('cards', []) or []:
                    v = self._vod(item)
                    if v and v['vod_id'] not in seen:
                        seen.add(v['vod_id'])
                        videos.append(v)
        if not videos:
            data = self._api('/v1/browse/catalog', {'page': '1', 'limit': str(PAGE_SIZE)})
            for item in (data or {}).get('cards', []) or []:
                v = self._vod(item)
                if v and v['vod_id'] not in seen:
                    seen.add(v['vod_id'])
                    videos.append(v)
        return {'list': videos}

    # ========== 数据转换 ==========

    @staticmethod
    def _clean(text):
        text = re.sub(r'<[^>]+>', '', str(text or ''))
        return re.sub(r'\s+\n\s*', '\n', text).strip()

    @staticmethod
    def _remarks(item):
        for key in ('remarks',):
            val = str(item.get(key) or '').strip()
            if val:
                return val
        kind = str(item.get('content_kind') or '')
        cnt = item.get('episode_count') or item.get('available_episode_count')
        if kind == 'movie':
            return '电影'
        if cnt:
            return f'{cnt}集全'
        return ''

    def _vod(self, item):
        if not isinstance(item, dict):
            return None
        vid = str(item.get('id') or '')
        title = str(item.get('title') or item.get('normalized_title') or '').strip()
        if not vid or not title:
            return None
        pic = (item.get('poster_url') or item.get('carousel_url')
               or item.get('backdrop_url') or '')
        actors = item.get('actors') or []
        directors = item.get('directors') or []
        genres = item.get('genres') or []
        return {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': str(pic or ''),
            'type_name': self._kind_name(item.get('content_kind')),
            'vod_year': str(item.get('year') or ''),
            'vod_area': str(item.get('area') or ''),
            'vod_remarks': self._remarks(item),
            'vod_actor': '、'.join(str(a) for a in actors[:12] if a),
            'vod_director': '、'.join(str(d) for d in directors[:4] if d),
            'vod_content': (str(item.get('description') or '')
                            or '、'.join(str(g) for g in genres[:8] if g)),
        }

    @staticmethod
    def _kind_name(kind):
        for k, n in KINDS:
            if k == kind:
                return n
        return ''

    # ========== 分类 ==========

    def categoryContent(self, tid, pg, filter, extend):
        pg = self._page(pg)
        params = {'page': str(pg), 'limit': str(PAGE_SIZE)}
        tid = str(tid or '')
        if tid and tid in dict(KINDS):
            params['kind'] = tid
        ex = extend if isinstance(extend, dict) else {}
        for key in ('genre', 'area', 'year'):
            val = str(ex.get(key) or '').strip()
            if val and val not in ('全部', '-1', '0'):
                params[key] = val
        return self._browse(params)

    def _browse(self, params):
        data = self._api('/v1/browse/catalog', params)
        videos, seen = [], set()
        if data:
            for item in data.get('cards', []) or []:
                v = self._vod(item)
                if v and v['vod_id'] not in seen:
                    seen.add(v['vod_id'])
                    videos.append(v)
        pg = int(params.get('page', '1') or 1)
        pginfo = (data or {}).get('pagination', {}) or {}
        has_more = bool(pginfo.get('has_more')) if pginfo else len(videos) >= PAGE_SIZE
        return {
            'list': videos,
            'page': str(pg),
            'pagecount': pg + 1 if has_more else pg,
            'limit': max(len(videos), 1),
            'total': int(pginfo.get('total') or 0) or 999999,
        }

    @staticmethod
    def _page(pg):
        try:
            pg = int(pg or 1)
        except Exception:
            pg = 1
        return 1 if pg < 1 else pg

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        keyword = str(key or '').strip()
        if not keyword:
            return {'list': []}
        pg = self._page(pg)
        params = {'page': str(pg), 'limit': str(PAGE_SIZE), 'q': keyword}
        return self._browse(params)

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情 ==========

    def detailContent(self, ids):
        ids = [ids] if isinstance(ids, str) else (ids or [])
        vid = str(ids[0]) if ids else ''

        vod = {
            'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'type_name': '',
            'vod_year': '', 'vod_area': '', 'vod_remarks': '', 'vod_actor': '',
            'vod_director': '', 'vod_content': '',
            'vod_play_from': '', 'vod_play_url': '',
        }
        if not vid:
            return {'list': [vod]}

        data = self._api('/v1/catalog/' + quote(vid, safe=''))
        if not data:
            return {'list': [vod]}

        vod['vod_name'] = str(data.get('title') or data.get('normalized_title') or '')
        vod['vod_pic'] = str(data.get('poster_url') or data.get('carousel_url')
                             or data.get('backdrop_url') or '')
        vod['type_name'] = self._kind_name(data.get('content_kind'))
        vod['vod_year'] = str(data.get('year') or '')
        vod['vod_area'] = str(data.get('area') or '')
        vod['vod_remarks'] = self._remarks(data)
        vod['vod_actor'] = '、'.join(str(a) for a in (data.get('actors') or [])[:12] if a)
        vod['vod_director'] = '、'.join(str(d) for d in (data.get('directors') or [])[:4] if d)
        vod['vod_content'] = self._clean(data.get('description'))

        episodes = self._all_episodes(vid, data)
        if not episodes:
            vod['vod_play_from'] = '默认'
            vod['vod_play_url'] = f'正片${vid}'
            return {'list': [vod]}

        ep_str = '#'.join(
            '%s$%s' % (self._ep_name(e), str(e.get('token') or e.get('id') or ''))
            for e in episodes
        )

        # 用首集探测可切换的线路（失败则退化为单一线路）
        providers = []
        try:
            providers = self._providers(str(episodes[0].get('token') or ''))
        except Exception:
            providers = []

        if providers:
            vod['vod_play_from'] = '$$$'.join(p for p in providers)
            vod['vod_play_url'] = '$$$'.join(
                self._with_provider(ep_str, p) for p in providers
            )
        else:
            vod['vod_play_from'] = '秒播'
            vod['vod_play_url'] = self._with_provider(ep_str, '')
        return {'list': [vod]}

    @staticmethod
    def _ep_name(e):
        title = str(e.get('title') or '').strip()
        num = e.get('number')
        if title:
            return title
        if num:
            return f'第{num}集'
        return '正片'

    def _all_episodes(self, vid, detail):
        """详情自带 episodes；分页不足时用 /episodes 补齐"""
        eps = [e for e in (detail.get('episodes') or []) if isinstance(e, dict)
               and (e.get('token') or e.get('id'))]
        pginfo = detail.get('episode_pagination') or {}
        if not pginfo.get('has_more'):
            return eps
        out, seen = list(eps), {str(e.get('token') or e.get('id')) for e in eps}
        limit = int(pginfo.get('limit') or 48) or 48
        total = int(pginfo.get('total_count') or 0) or (limit * 4)
        offset = 0
        while offset + limit < total + limit and len(out) < total:
            offset += limit
            if offset >= total:
                break
            d = self._api('/v1/catalog/%s/episodes' % quote(vid, safe=''),
                          {'offset': str(offset), 'limit': str(limit)})
            batch = [e for e in ((d or {}).get('episodes') or []) if isinstance(e, dict)]
            if not batch:
                break
            added = 0
            for e in batch:
                key = str(e.get('token') or e.get('id'))
                if key and key not in seen:
                    seen.add(key)
                    out.append(e)
                    added += 1
            if not added:
                break
        return out

    @staticmethod
    def _with_provider(ep_str, provider):
        """把线路名附加到每一集的播放 id 上：token|||provider"""
        out = []
        for part in str(ep_str or '').split('#'):
            if '$' not in part:
                continue
            name, _, pid = part.partition('$')
            out.append('%s$%s|||%s' % (name, pid, provider))
        return '#'.join(out)

    def _providers(self, token):
        """解析首集，返回可切换的线路名（按权重降序、去重、限量）"""
        if not token:
            return []
        data = self._api('/v1/playback/resolve/' + quote(token, safe=''))
        names = []
        for line in self._sorted_lines(data):
            name = str(line.get('provider_name') or line.get('label') or '').strip()
            if name and name not in names:
                names.append(name)
            if len(names) >= MAX_PROVIDERS:
                break
        return names

    @staticmethod
    def _sorted_lines(data):
        """取已解析、可直接播的线路，按权重降序"""
        lines = []
        for line in ((data or {}).get('line_options') or []):
            if not isinstance(line, dict):
                continue
            url = str(line.get('url') or '').strip()
            if not url.lower().startswith(('http://', 'https://')):
                continue
            if line.get('resolve_required'):
                continue
            try:
                w = float(line.get('preference_weight') or 0)
            except Exception:
                w = 0.0
            lines.append((w, line))
        lines.sort(key=lambda x: -x[0])
        return [l for _w, l in lines]

    def _rank_by_speed(self, lines):
        """
        并发探测候选源首包延迟，按实测速度重排，最快的排最前。
        站点的 preference_weight 是采集源质量权重，跟当前网络下的实际速度无关，
        默认线路常常不是最快的那个（表现就是播放慢 / 卡）。
        探测失败或超时的源排到后面，不影响可用性；extend 里写 nospeed 可关闭。
        """
        if not lines or 'nospeed' in str(self.extend or '').lower():
            return lines
        cands = lines[:SPEED_TEST_N]
        rest = lines[SPEED_TEST_N:]
        if len(cands) < 2:
            return lines

        # 同一部剧的候选源构成基本不变，测过一次就按上次的快慢顺序排，
        # 连播第 2、3 集不用每集都干等 3 秒。
        key = tuple(self._pname(l) for l in cands)
        cached = self._sp.get(key)
        if cached:
            idx = {n: i for i, n in enumerate(cached)}
            head = sorted(cands, key=lambda l: idx.get(self._pname(l), 999))
            return head + rest

        cost = {}

        def probe(item):
            idx, ln = item
            url = str(ln.get('url') or '').strip()
            if not url:
                return
            t0 = time.time()
            try:
                rsp = self.fetch(url, headers={'User-Agent': PLAY_UA,
                                               'Range': 'bytes=0-4095'},
                                 timeout=SPEED_TIMEOUT)
                if (getattr(rsp, 'status_code', 200) or 200) >= 400:
                    return
                body = getattr(rsp, 'content', None)
                if body is None:
                    body = str(getattr(rsp, 'text', '') or '').encode('utf-8', 'ignore')
                if body and b'#EXTM3U' not in body[:4096]:
                    return          # 拿到的不是 m3u8（防盗链页 / 错误页），判为不可用
                cost[idx] = time.time() - t0
            except Exception:
                return

        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(len(cands), SPEED_TEST_N)) as pool:
                list(pool.map(probe, list(enumerate(cands))))
        except Exception:
            return lines
        if not cost:
            return lines
        ok = sorted((i for i in cost), key=lambda i: cost[i])
        bad = [i for i in range(len(cands)) if i not in cost]
        ranked = [cands[i] for i in ok] + [cands[i] for i in bad]
        if len(self._sp) > 64:
            self._sp.clear()
        self._sp[key] = [self._pname(l) for l in ranked]
        return ranked + rest

    @staticmethod
    def _pname(line):
        return str((line or {}).get('provider_name')
                   or (line or {}).get('label') or '').strip()

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        try:
            raw = str(id or '')
            token, _, provider = raw.partition('|||')
            token = token.strip()
            if not token:
                return {}
            data = self._api('/v1/playback/resolve/' + quote(token, safe=''))
            if not data:
                return {}

            lines = self._sorted_lines(data)
            provider = provider.strip()
            if provider:
                matched = [l for l in lines if self._pname(l) == provider]
                if matched:
                    # 用户选的线路排前面，其余作为备选（按名称过滤，避免 dict 相等误判）
                    lines = matched + [l for l in lines if self._pname(l) != provider]
            else:
                # 没手动指定线路：实测一把，把最快的源顶到第一位
                lines = self._rank_by_speed(lines)

            urls = []
            for line in lines[:MAX_LINES]:
                u = self._proxify(str(line.get('url') or '').strip())
                if u:
                    urls.append(u)
            if not urls:
                return {}

            url = '***'.join(urls)
            out = {'parse': 0, 'playUrl': '', 'url': url,
                   'header': {'User-Agent': PLAY_UA}}
            if '.m3u8' in url or 'mpegurl' in url:
                out['format'] = 'application/x-mpegURL'
                out['contentType'] = 'application/x-mpegURL'
            return out
        except Exception:
            return {}

    # ========== 本地代理（http 明文源在 Android 9+ 会被 cleartext 拦截） ==========

    def _proxy_base(self):
        cached = getattr(self, '_pb', None)
        if cached is not None:
            return cached
        base = ''
        for name in ('getProxyUrl', 'getProxy', 'getProxyURL'):
            try:
                fn = getattr(self, name, None)
                if fn is None:
                    continue
                val = fn() if callable(fn) else fn
                if isinstance(val, str) and val.strip():
                    base = val.strip()
                    break
            except Exception:
                continue
        self._pb = base
        return base

    def _proxify(self, url):
        """
        只有 http 明文才走代理（Android 9+ cleartext 会拦截）。
        本源的播放地址基本都是 https，直连即可，不要白白绕一层 python 拖慢播放。
        """
        url = str(url or '').strip()
        if not url.lower().startswith(('http://', 'https://')):
            return url
        # 默认只代理 http 明文；配置里写 proxy 可强制 https 也走代理
        force = 'proxy' in str(self.extend or '').lower()
        if not force and url.lower().startswith('https://'):
            return url
        base = self._proxy_base()
        if not base:
            return url
        b = base.rstrip()
        if b.endswith('url='):
            return b + quote(url, safe='')
        b = b.rstrip('&').rstrip('?')
        sep = '&' if '?' in b else '?'
        return b + sep + 'url=' + quote(url, safe='')

    @staticmethod
    def _param_url(param):
        import urllib.parse as up
        raw = ''
        if isinstance(param, dict):
            raw = param.get('url') or param.get('u') or ''
        elif isinstance(param, str):
            p = param.strip()
            # 只有传入完整 proxy url 时才剥 path；纯 query 里目标地址自带 ? 不能乱切
            if p.lower().startswith('http'):
                p = p.split('?', 1)[1] if '?' in p else ''
            qs = up.parse_qs(p, keep_blank_values=True)
            raw = (qs.get('url') or qs.get('u') or [''])[0]
            if not raw and param.strip().lower().startswith('http'):
                raw = param.strip()
        raw = str(raw or '').strip()
        if raw.lower().startswith('http'):
            return raw
        return up.unquote(raw) if '%' in raw else raw

    @staticmethod
    def _guess_ctype(url, is_m3u8):
        low = str(url or '').lower()
        if is_m3u8:
            return 'application/vnd.apple.mpegurl; charset=utf-8'
        for ext, ct in (('.ts', 'video/mp2t'), ('.mp4', 'video/mp4'),
                        ('.m4s', 'video/iso.segment'), ('.aac', 'audio/aac'),
                        ('.m4a', 'audio/mp4'), ('.vtt', 'text/vtt')):
            if ext in low:
                return ct
        return 'application/octet-stream'

    def _fetch_media(self, url, timeout=30):
        hdr = {'User-Agent': PLAY_UA}
        rsp = None
        try:
            rsp = self.fetch(url, headers=hdr, timeout=timeout)
        except Exception:
            rsp = None
        if rsp is not None and (getattr(rsp, 'status_code', 200) or 200) < 400:
            return rsp
        if url.startswith('https://'):
            try:
                alt = self.fetch('http://' + url[8:], headers=hdr, timeout=timeout)
                if alt is not None and (getattr(alt, 'status_code', 200) or 200) < 400:
                    return alt
            except Exception:
                pass
        return rsp

    def localProxy(self, param):
        """m3u8 递归代理：根相对路径的 TS / KEY 全部改写为代理地址；其它直接透传"""
        try:
            media_url = self._param_url(param)
            if not media_url.lower().startswith('http'):
                return [404, 'text/plain', b'']
            rsp = self._fetch_media(media_url)
            if rsp is None:
                return [502, 'text/plain', b'upstream error']
            content = (rsp.content if hasattr(rsp, 'content')
                       else str(getattr(rsp, 'text', '') or '').encode('utf-8'))
            if content is None:
                return [502, 'text/plain', b'empty upstream']
            try:
                text = content.decode('utf-8')
            except Exception:
                return [200, self._guess_ctype(media_url, False), content]
            if '#EXTM3U' not in text[:400]:
                return [200, self._guess_ctype(media_url, False), content]

            sp = urlsplit(media_url)
            origin = urlunsplit((sp.scheme, sp.netloc, '', '', ''))
            query = ('?' + sp.query) if sp.query else ''

            def _abs(u):
                u = u.strip().strip('"')
                if u.startswith('//'):
                    return sp.scheme + ':' + u
                if u.startswith('/'):
                    return origin + u + query
                if u.lower().startswith(('http', 'data:', 'skd:')):
                    return u
                return urljoin(media_url, u)

            out = []
            for line in text.splitlines():
                s = line.strip()
                if not s:
                    out.append(line)
                    continue
                if s.startswith('#'):
                    if 'URI=' in s:
                        m = re.search(r'URI="([^"]+)"', line)
                        if m:
                            line = (line[:m.start(1)] + self._proxify(_abs(m.group(1)))
                                    + line[m.end(1):])
                    out.append(line)
                    continue
                out.append(self._proxify(_abs(s)))
            return [200, 'application/vnd.apple.mpegurl; charset=utf-8',
                    '\n'.join(out).encode('utf-8')]
        except Exception:
            return [500, 'text/plain', b'proxy error']

    # ========== 其它 ==========

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


if __name__ == '__main__':
    # 本地自测：python 搜剧AI.py
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    s = Spider()
    s.init()
    s.getProxyUrl = lambda: 'http://127.0.0.1:9978/proxy?do=py&type=all&'

    print('=== homeContent ===')
    h = s.homeContent(True)
    print('分类:', [c['type_name'] for c in h['class']])
    print('首页条数:', len(h.get('list', [])))
    if h['list']:
        print('样例:', json.dumps(h['list'][0], ensure_ascii=False)[:220])

    print('\n=== categoryContent (剧集) ===')
    c = s.categoryContent('series', '1', True, {})
    print('条数:', len(c['list']), '| page', c.get('page'), '| pagecount', c.get('pagecount'))
    if c['list']:
        print('样例:', c['list'][0]['vod_name'], '|', c['list'][0]['vod_remarks'])

    print('\n=== categoryContent 筛选 (电影+动作) ===')
    c2 = s.categoryContent('movie', '1', True, {'genre': '动作'})
    print('条数:', len(c2['list']))

    print('\n=== 分页 ===')
    c3 = s.categoryContent('series', '3', True, {})
    print('第3页条数:', len(c3['list']))

    print('\n=== searchContent ===')
    sr = s.searchContent('庆余年', False, '1')
    print('条数:', len(sr['list']), [v['vod_name'] for v in sr['list'][:5]])

    print('\n=== detailContent ===')
    vid = (c['list'][0]['vod_id'] if c['list'] else '')
    dt = s.detailContent([vid])['list'][0]
    print('剧名:', dt['vod_name'], '| 备注:', dt['vod_remarks'])
    print('线路:', dt['vod_play_from'][:180])
    eps = dt['vod_play_url'].split('$$$')[0].split('#')
    print('集数:', len(eps), '| 首集:', eps[0][:90])

    print('\n=== playerContent ===')
    flag = dt['vod_play_from'].split('$$$')[0]
    pid = eps[0].split('$', 1)[1]
    pc = s.playerContent(flag, pid, [])
    url = (pc or {}).get('url', '')
    parts = url.split('***')
    print('返回线路数:', len(parts) if url else 0)
    for u in parts[:3]:
        print('  ', u[:120])

    print('\n=== 实际取流校验 ===')
    try:
        import requests as _rq
        for u in parts[:3]:
            real = u
            if u.startswith('http://127.0.0.1'):
                code, ct, body = s.localProxy(u.split('?', 1)[1])
                print(f'  [代理] code={code} ct={ct} size={len(body)}')
                if code != 200:
                    continue
                txt = body.decode('utf-8', 'ignore')
                real_u = [x.strip() for x in txt.splitlines()
                          if x.strip() and not x.startswith('#')]
                print('    分片数:', len(real_u), '| 首片:', (real_u[0][:90] if real_u else ''))
                continue
            r = _rq.get(u, headers={'User-Agent': PLAY_UA}, timeout=15)
            print(f'  [直连] {r.status_code} {r.headers.get("Content-Type", "")[:30]} '
                  f'{r.text[:30]!r}')
    except Exception as e:
        print('  校验异常:', type(e).__name__, e)
