# coding = utf-8
#!/usr/bin/python
"""
PPV体育直播 — TVBox / FongMi TV 爬虫
站点: https://ppv.st
API: https://api.ppv.st/api/streams
特点: 体育直播聚合, 多分类, iframe嵌入播放
播放: Web嗅探模式 (parse: 1) — 播放器加载iframe页面自动嗅探m3u8
版本: 1.0.0
"""
import sys
import json
import time
import re
from urllib.parse import quote, unquote, urljoin

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

        def post(self, url, data=None, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.post(url, data=data, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    """PPV体育直播 Spider — API驱动 + Web嗅探播放"""

    # ─── API 配置 ───
    API_BASE = "https://api.ppv.st/api"
    API_BASE2 = "https://api.ppv.cx/api"  # 备用域名
    SITE_URL = "https://ppv.st"

    # ─── 分类英中映射 ───
    CATEGORY_MAP = {
        "American Football": "美式足球",
        "Australian Football": "澳式足球",
        "Baseball": "棒球",
        "Basketball": "篮球",
        "Football": "足球",
        "Miscellaneous": "其他赛事",
        "Rugby": "橄榄球",
        "Wrestling": "摔角",
        "24/7 Streams": "24小时直播",
    }

    # ─── 缓存 ───
    _cache = None
    _cache_time = 0
    _cache_ttl = 300  # 5分钟缓存

    def getName(self):
        return "PPV体育"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|avi)(\?|$)', url or '', re.I))

    def manualVideoCheck(self):
        return True

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''

        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Origin': self.SITE_URL,
            'Referer': self.SITE_URL + '/',
        }

        # 播放时使用的header (用于iframe页面)
        self.play_header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.SITE_URL + '/',
        }

    # ═══════════════════════════════════════
    #  数据获取
    # ═══════════════════════════════════════

    def _fetch_streams(self):
        """从API获取所有直播流数据 (带缓存)"""
        now = int(time.time())
        if self._cache and now - self._cache_time < self._cache_ttl:
            return self._cache

        data = self._fetch_json(self.API_BASE + '/streams')
        if not data or not data.get('success'):
            # 尝试备用域名
            data = self._fetch_json(self.API_BASE2 + '/streams')

        if data and data.get('success') and data.get('streams'):
            self._cache = data
            self._cache_time = now
            return data

        return None

    def _fetch_json(self, url, timeout=15):
        """GET请求返回JSON"""
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout)
            try:
                rsp.encoding = 'utf-8'
            except Exception:
                pass
            return json.loads(rsp.text)
        except Exception:
            return None

    def _get_all_streams(self):
        """获取所有直播流的扁平列表"""
        data = self._fetch_streams()
        if not data:
            return []

        all_streams = []
        for cat in data.get('streams', []):
            cat_name = cat.get('category', '')
            cat_id = cat.get('id', 0)
            for s in cat.get('streams', []):
                s['_cat_name'] = cat_name
                s['_cat_id'] = cat_id
                all_streams.append(s)
        return all_streams

    def _get_status_text(self, stream):
        """获取直播状态文本"""
        if stream.get('always_live') == 1:
            return "直播中"
        now = int(time.time())
        starts_at = stream.get('starts_at', 0)
        ends_at = stream.get('ends_at', 0)
        if starts_at and ends_at:
            if now < starts_at:
                # 即将开始
                diff = starts_at - now
                if diff < 3600:
                    return f"{diff // 60}分钟后"
                elif diff < 86400:
                    return f"{diff // 3600}小时后"
                else:
                    return f"{diff // 86400}天后"
            elif starts_at <= now <= ends_at:
                viewers = stream.get('viewers', '0')
                return f"直播中 ({viewers}人)"
            else:
                return "已结束"
        return ""

    def _format_stream(self, s):
        """格式化直播流为TVBox视频对象"""
        vod_id = str(s.get('id', ''))
        name = s.get('name', '')
        poster = s.get('poster', '')
        remarks = self._get_status_text(s)
        tag = s.get('tag', '')

        # 将iframe URL和相关信息编码到vod_id中
        iframe = s.get('iframe', '')
        uri_name = s.get('uri_name', '')

        # 编码: stream_id||iframe_url||uri_name||stream_name||tag
        encoded_id = '{}||{}||{}||{}||{}'.format(
            vod_id,
            quote(iframe, safe=''),
            quote(uri_name, safe=''),
            quote(name, safe=''),
            quote(tag, safe='')
        )

        return {
            'vod_id': encoded_id,
            'vod_name': name,
            'vod_pic': poster,
            'vod_remarks': remarks,
        }

    def _decode_id(self, id):
        """解码vod_id获取直播流信息"""
        parts = str(id).split('||')
        if len(parts) < 5:
            # 兼容纯ID格式
            return {
                'stream_id': parts[0] if parts else '',
                'iframe': '',
                'uri_name': '',
                'name': '',
                'tag': '',
            }
        return {
            'stream_id': parts[0],
            'iframe': unquote(parts[1]),
            'uri_name': unquote(parts[2]),
            'name': unquote(parts[3]),
            'tag': unquote(parts[4]),
        }

    # ═══════════════════════════════════════
    #  首页
    # ═══════════════════════════════════════

    def homeContent(self, filter):
        result = {}

        data = self._fetch_streams()
        if not data:
            return result

        # 构建分类列表
        classes = []
        for cat in data.get('streams', []):
            cat_name = cat.get('category', '')
            cat_id = str(cat.get('id', ''))
            display_name = self.CATEGORY_MAP.get(cat_name, cat_name)
            classes.append({
                'type_id': cat_id,
                'type_name': display_name,
            })

        result['class'] = classes

        if filter:
            result['filters'] = self._build_filters(classes)

        # 首页推荐: 取正在直播的 + 即将开始的
        all_streams = self._get_all_streams()
        now = int(time.time())

        # 排序: 正在直播 > 即将开始 > 24小时 > 已结束
        def sort_key(s):
            if s.get('always_live') == 1:
                return (0, 0)
            starts_at = s.get('starts_at', 0)
            ends_at = s.get('ends_at', 0)
            if starts_at <= now <= ends_at:
                return (1, -int(s.get('viewers', '0') or '0'))
            elif now < starts_at:
                return (2, starts_at)
            else:
                return (3, -starts_at)

        all_streams.sort(key=sort_key)

        videos = [self._format_stream(s) for s in all_streams[:60]]
        result['list'] = videos

        return result

    def _build_filters(self, classes):
        filters = {}
        for c in classes:
            tid = c.get('type_id', '')
            if tid:
                filters[tid] = [
                    {
                        'key': 'status',
                        'name': '状态',
                        'value': [
                            {'n': '全部', 'v': ''},
                            {'n': '直播中', 'v': 'live'},
                            {'n': '即将开始', 'v': 'upcoming'},
                            {'n': '已结束', 'v': 'ended'},
                            {'n': '24小时', 'v': 'always'},
                        ]
                    },
                    {
                        'key': 'sort',
                        'name': '排序',
                        'value': [
                            {'n': '人气', 'v': 'viewers'},
                            {'n': '时间', 'v': 'time'},
                        ]
                    },
                ]
        return filters

    def homeVideoContent(self):
        data = self._fetch_streams()
        if not data:
            return {'list': []}

        all_streams = self._get_all_streams()
        now = int(time.time())

        # 只显示正在直播和即将开始的
        live_streams = []
        for s in all_streams:
            if s.get('always_live') == 1:
                live_streams.append(s)
            elif s.get('starts_at', 0) and s.get('ends_at', 0):
                if s.get('starts_at') <= now <= s.get('ends_at'):
                    live_streams.append(s)
                elif now < s.get('starts_at'):
                    live_streams.append(s)

        live_streams.sort(key=lambda s: (
            0 if s.get('always_live') == 1 else
            1 if s.get('starts_at', 0) <= now else 2
        ))

        videos = [self._format_stream(s) for s in live_streams[:72]]
        return {'list': videos}

    # ═══════════════════════════════════════
    #  分类
    # ═══════════════════════════════════════

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        page = int(pg) or 1
        page_size = 30

        data = self._fetch_streams()
        if not data:
            result['list'] = []
            result['page'] = page
            result['pagecount'] = 1
            result['limit'] = page_size
            result['total'] = 0
            return result

        # 找到对应分类的直播流
        streams = []
        for cat in data.get('streams', []):
            if str(cat.get('id', '')) == str(tid):
                streams = list(cat.get('streams', []))
                break

        # 应用筛选
        if extend:
            status = extend.get('status', '')
            if status:
                now = int(time.time())
                filtered = []
                for s in streams:
                    if status == 'always' and s.get('always_live') == 1:
                        filtered.append(s)
                    elif status == 'live' and s.get('starts_at', 0) and s.get('ends_at', 0):
                        if s.get('starts_at') <= now <= s.get('ends_at'):
                            filtered.append(s)
                    elif status == 'upcoming' and s.get('starts_at', 0):
                        if now < s.get('starts_at'):
                            filtered.append(s)
                    elif status == 'ended' and s.get('ends_at', 0):
                        if now > s.get('ends_at'):
                            filtered.append(s)
                streams = filtered

            sort = extend.get('sort', '')
            if sort == 'viewers':
                streams.sort(key=lambda s: -int(s.get('viewers', '0') or '0'))
            elif sort == 'time':
                streams.sort(key=lambda s: s.get('starts_at', 0) or 0)
        else:
            # 默认排序: 正在直播 > 即将开始 > 24小时 > 已结束
            now = int(time.time())
            def default_sort(s):
                if s.get('always_live') == 1:
                    return (0, 0)
                starts_at = s.get('starts_at', 0)
                ends_at = s.get('ends_at', 0)
                if starts_at and ends_at:
                    if starts_at <= now <= ends_at:
                        return (1, -int(s.get('viewers', '0') or '0'))
                    elif now < starts_at:
                        return (2, starts_at)
                    else:
                        return (3, -starts_at)
                return (4, 0)
            streams.sort(key=default_sort)

        # 分页
        total = len(streams)
        start = (page - 1) * page_size
        end = start + page_size
        page_streams = streams[start:end]

        videos = [self._format_stream(s) for s in page_streams]

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = max(1, (total + page_size - 1) // page_size)
        result['limit'] = page_size
        result['total'] = total

        return result

    # ═══════════════════════════════════════
    #  详情
    # ═══════════════════════════════════════

    def detailContent(self, id):
        info = self._decode_id(id)
        stream_id = info.get('stream_id', '')
        iframe = info.get('iframe', '')
        name = info.get('name', '')
        tag = info.get('tag', '')

        # 从缓存中查找完整的直播流信息
        all_streams = self._get_all_streams()
        stream = None
        for s in all_streams:
            if str(s.get('id', '')) == str(stream_id):
                stream = s
                break

        if not stream:
            return {}

        # 构建详情
        now = int(time.time())
        starts_at = stream.get('starts_at', 0)
        ends_at = stream.get('ends_at', 0)
        status = self._get_status_text(stream)
        viewers = stream.get('viewers', '0')
        category = stream.get('category_name', '')
        cat_cn = self.CATEGORY_MAP.get(category, category)
        poster = stream.get('poster', '')

        # 构建描述信息
        desc_parts = []
        desc_parts.append(f"赛事: {name}")
        if tag:
            desc_parts.append(f"频道: {tag}")
        desc_parts.append(f"分类: {cat_cn}")
        desc_parts.append(f"状态: {status}")
        if viewers and viewers != '0':
            desc_parts.append(f"观看: {viewers}人")
        if starts_at and not stream.get('always_live'):
            from datetime import datetime
            try:
                start_time = datetime.fromtimestamp(starts_at).strftime('%Y-%m-%d %H:%M')
                desc_parts.append(f"开始: {start_time}")
            except Exception:
                pass
        if ends_at and not stream.get('always_live'):
            try:
                from datetime import datetime
                end_time = datetime.fromtimestamp(ends_at).strftime('%Y-%m-%d %H:%M')
                desc_parts.append(f"结束: {end_time}")
            except Exception:
                pass

        vod = {
            'vod_id': id,
            'vod_name': name,
            'vod_pic': poster,
            'type_name': cat_cn,
            'vod_year': '',
            'vod_area': '',
            'vod_lang': stream.get('locale', 'en'),
            'vod_remarks': status,
            'vod_content': '\n'.join(desc_parts),
            'vod_play_from': 'PPV体育',
            'vod_play_url': name + '$' + id,
        }

        return {'list': [vod]}

    # ═══════════════════════════════════════
    #  播放
    # ═══════════════════════════════════════

    def playerContent(self, flag, id, vipFlags):
        """播放解析

        使用 Web 嗅探模式 (parse: 1):
        播放器加载 iframe 页面, 自动嗅探 m3u8 地址
        iframe 页面内 jwplayer 会自动加载并播放流
        """
        info = self._decode_id(id)
        iframe = info.get('iframe', '')

        if not iframe:
            return {"parse": 0, "playUrl": "", "url": ""}

        result = {
            "parse": 1,
            "playUrl": "",
            "url": iframe,
            "header": dict(self.play_header),
        }

        return result

    # ═══════════════════════════════════════
    #  搜索
    # ═══════════════════════════════════════

    def searchContent(self, key, quick):
        """搜索直播流"""
        if not key:
            return []

        all_streams = self._get_all_streams()
        key_lower = key.lower()

        results = []
        for s in all_streams:
            name = s.get('name', '').lower()
            tag = s.get('tag', '').lower()
            cat = s.get('category_name', '').lower()
            cat_cn = self.CATEGORY_MAP.get(s.get('category_name', ''), '').lower()

            if key_lower in name or key_lower in tag or key_lower in cat or key_lower in cat_cn:
                results.append(self._format_stream(s))

        return results[:50]

    # ═══════════════════════════════════════
    #  本地代理 (可选 — 用于m3u8代理)
    # ═══════════════════════════════════════

    def localProxy(self, param):
        """本地代理 — 代理m3u8流, 解决跨域问题"""
        try:
            raw_url = ''
            if isinstance(param, dict):
                raw_url = param.get('url', '') or param.get('u', '')
            elif isinstance(param, str):
                import urllib.parse as up
                qs = up.parse_qs(param)
                raw_url = qs.get('url', [''])[0] or qs.get('u', [''])[0]

            media_url = unquote(raw_url) if raw_url else ''
            if not media_url:
                return [404, 'text/plain', b'']

            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 '
                              '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Referer': 'https://embedindia.st/',
            }

            rsp = self.fetch(media_url, headers=headers, timeout=30)
            content = rsp.content
            ctype = rsp.headers.get('Content-Type', '') or ''

            # m3u8 内容处理: 改写相对路径
            try:
                text = content.decode('utf-8')
            except Exception:
                text = ''

            if '#EXTM3U' in text:
                out = []
                proxy_base = ''
                try:
                    proxy_base = self.getProxyUrl()
                except Exception:
                    pass

                for line in text.splitlines():
                    s = line.strip()
                    if not s or s.startswith('#'):
                        out.append(line)
                    else:
                        abs_url = urljoin(media_url, s)
                        if proxy_base:
                            out.append(proxy_base + '&url=' + quote(abs_url, safe=''))
                        else:
                            out.append(abs_url)
                data = '\n'.join(out).encode('utf-8')
                return [200, 'application/x-mpegURL', data]

            return [200, ctype or 'application/octet-stream', content]
        except Exception:
            return [500, 'text/plain', b'proxy error']
