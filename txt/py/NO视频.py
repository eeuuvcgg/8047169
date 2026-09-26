# -*- coding: utf-8 -*-
"""
NO视频 (https://www.novipnoad.uk) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.novipnoad.uk
采集: WordPress HTML + 播放器 iframe 嗅探
版本: 1.0.0
"""
import sys
import re

sys.path.append('..')

# ===== 兼容导入 =====
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


# ==================== 常量 ====================
SITE_URL = "https://www.novipnoad.uk"
PLAYER_URL = "https://player.novipnoad.uk/v1/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 16

# 首页分类 — type_id 即 URL 路径段
CLASSES = [
    {"type_id": "movie", "type_name": "电影"},
    {"type_id": "tv/hongkong", "type_name": "港剧"},
    {"type_id": "tv/taiwan", "type_name": "台剧"},
    {"type_id": "tv/western", "type_name": "欧美剧"},
    {"type_id": "tv/japan", "type_name": "日剧"},
    {"type_id": "tv/korea", "type_name": "韩剧"},
    {"type_id": "tv/thailand", "type_name": "泰剧"},
    {"type_id": "tv/turkey", "type_name": "土耳其剧"},
    {"type_id": "anime", "type_name": "动画"},
    {"type_id": "shows", "type_name": "综艺"},
    {"type_id": "music", "type_name": "音乐"},
    {"type_id": "short", "type_name": "短片"},
    {"type_id": "other", "type_name": "其他"},
]

# 排序筛选器 — 所有分类通用
_SORT_VALUES = [
    {"n": "按更新", "v": "date"},
    {"n": "按热度", "v": "view"},
    {"n": "按点赞", "v": "like"},
    {"n": "按评论", "v": "comment"},
    {"n": "按标题", "v": "title"},
]

_FILTERS_TEMPLATE = [{"key": "by", "name": "排序", "value": _SORT_VALUES}]

FILTERS = {c["type_id"]: _FILTERS_TEMPLATE for c in CLASSES}


class Spider(Spider):
    """NO视频 Spider — WordPress HTML 采集 + iframe 嗅探"""

    def getName(self):
        return "NO视频"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.siteUrl = SITE_URL
        self.headers = {
            'User-Agent': UA,
            'Referer': SITE_URL + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

    def isVideoFormat(self, url):
        video_formats = ['.mp4', '.m3u8', '.ts', '.mkv', '.avi', '.webm']
        if url and str(url).startswith('http'):
            for fmt in video_formats:
                if fmt in str(url).lower():
                    return True
        return False

    def manualVideoCheck(self):
        return False

    # ========== 工具函数 ==========

    def _request(self, url, referer=None):
        headers = dict(self.headers)
        if referer:
            headers['Referer'] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=15)
            return rsp
        except Exception:
            return None

    @staticmethod
    def _safe_str(val, default=''):
        if val is None or val == '' or val == 'None':
            return default
        return str(val).strip()

    @staticmethod
    def _safe_page(pg, default=1):
        try:
            p = int(pg)
            return p if p > 0 else default
        except Exception:
            return default

    @staticmethod
    def _fix_url(url):
        if not url:
            return ''
        url = str(url).strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('http'):
            return url
        return url

    @staticmethod
    def _decode_entities(text):
        if not text:
            return ''
        entities = {
            '&#8216;': "'", '&#8217;': "'", '&#8220;': '"', '&#8221;': '"',
            '&hellip;': '...', '&amp;': '&', '&nbsp;': ' ',
            '&#039;': "'", '&quot;': '"', '&lt;': '<', '&gt;': '>',
        }
        for k, v in entities.items():
            text = text.replace(k, v)
        # 通用数字实体
        text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))) if int(m.group(1)) < 65536 else '', text)
        return text

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        result['class'] = list(CLASSES)
        if filter:
            result['filters'] = dict(FILTERS)
        return result

    def homeVideoContent(self):
        try:
            rsp = self._request(f'{SITE_URL}/movie/')
            if rsp and rsp.status_code == 200:
                videos = self._parse_list(rsp.text)
                return {'list': videos[:72]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, 'movie')
        page = self._safe_page(pg, 1)
        extend = extend or {}
        by = self._safe_str(extend.get('by', 'date')) or 'date'

        url = f'{SITE_URL}/{tid}/page/{page}/?orderby={by}'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

            html = rsp.text
            videos = self._parse_list(html)

            # 解析总页数
            pagecount = page
            pc_match = re.search(r'/page/(\d+)/', html)
            if pc_match:
                pagecount = max(page, int(pc_match.group(1)))
            # 查找最大页码
            all_pages = re.findall(r'/page/(\d+)/', html)
            if all_pages:
                pagecount = max(page, max(int(p) for p in all_pages))

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': PAGE_SIZE,
                'total': 999999,
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

        # URL编码关键词
        import urllib.parse
        key_encoded = urllib.parse.quote(keyword)
        url = f'{SITE_URL}/search/{key_encoded}'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

            videos = self._parse_list(rsp.text)

            return {
                'list': videos,
                'page': str(page),
                'pagecount': page,
                'limit': PAGE_SIZE,
                'total': len(videos),
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])  # e.g. "movie/154456" or "tv/korea/154411"
        url = f'{SITE_URL}/{vod_id}.html'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}
            html = rsp.text
        except Exception:
            return {'list': []}

        vod = {'vod_id': vod_id}

        # 标题 — 从 h1 提取
        title_match = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', html, re.S)
        if not title_match:
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        vod['vod_name'] = self._decode_entities(re.sub(r'<[^>]+>', '', title_match.group(1)).strip()) if title_match else ""

        # 封面图
        pic_match = re.search(r'data-original=(https://img\.novipnoad\.uk/[^"\s>]+)', html)
        vod['vod_pic'] = self._fix_url(pic_match.group(1)) if pic_match else ""

        # 类型 — 从 category-xxx class 提取
        cat_match = re.search(r'category-(\w+)', html)
        cat_map = {
            'movie': '电影', 'hongkong': '港剧', 'taiwan': '台剧', 'western': '欧美剧',
            'japan': '日剧', 'korea': '韩剧', 'thailand': '泰剧', 'turkey': '土耳其剧',
            'anime': '动画', 'shows': '综艺', 'music': '音乐', 'short': '短片', 'other': '其他',
        }
        vod['type_name'] = cat_map.get(cat_match.group(1), cat_match.group(1)) if cat_match else ""

        # 年份 — 从标题中提取
        year_match = re.search(r'\((20\d{2})\)', html)
        vod['vod_year'] = year_match.group(1) if year_match else ""

        # 标签作为演员/导演信息
        tags = re.findall(r'rel=tag>([^<]+)<', html)
        vod['vod_actor'] = " / ".join(tags[:8]) if tags else ""
        vod['vod_director'] = ""

        # 简介 — 从 item-content 提取，去除 script/style 标签
        desc_section = re.search(r'class="item-content[^"]*"[^>]*>(.*?)</div>\s*<div class=clearfix', html, re.S)
        if desc_section:
            desc_raw = desc_section.group(1)
            desc_raw = re.sub(r'<script[^>]*>.*?</script>', '', desc_raw, flags=re.S)
            desc_raw = re.sub(r'<style[^>]*>.*?</style>', '', desc_raw, flags=re.S)
            desc_raw = re.sub(r'<[^>]+>', '', desc_raw).strip()
            vod['vod_content'] = self._decode_entities(desc_raw)
        else:
            vod['vod_content'] = ""

        # ===== 播放列表 =====
        # 提取 playInfo 中的 vid（电影类型）
        vid_match = re.search(r'window\.playInfo\s*=\s*\{[^}]*vid:"([^"]*)"', html)
        play_vid = vid_match.group(1) if vid_match else ""

        # 提取多集 data-vid（电视剧类型）
        multi_eps = re.findall(r'data-vid=([^\s>]+)[^>]*>(.*?)</a>', html, re.S)

        play_from_list = []
        play_url_list = []

        if multi_eps:
            # 电视剧：多集
            ep_list = []
            for vid, label in multi_eps:
                label_clean = re.sub(r'<[^>]+>', '', label).strip()
                if not label_clean:
                    label_clean = "播放"
                # 播放ID格式: vid|vod_id（嗅探模式返回详情页 URL）
                play_key = f"{vid}|{vod_id}"
                ep_list.append(f"{label_clean}${play_key}")

            if ep_list:
                play_from_list.append("NO视频")
                play_url_list.append("#".join(ep_list))
        elif play_vid:
            # 电影：单集
            play_key = f"{play_vid}|{vod_id}"
            play_from_list.append("NO视频")
            play_url_list.append(f"播放${play_key}")

        vod['vod_play_from'] = "$$$".join(play_from_list)
        vod['vod_play_url'] = "$$$".join(play_url_list)

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        """
        返回详情页 URL + parse=1 嗅探模式。

        为什么不用 player iframe URL：
        player.novipnoad.uk/v1/?url=... 直接在 WebView 中加载会 403（Cloudflare 检查嵌入上下文），
        且播放器内部需要 play.js 生成 ckey → postMessage AUTH → enc-vod JS 才能拿到 videoUrl，
        多层 iframe 嵌套导致嗅探超时。

        详情页会自动执行 play.js → 生成 ckey → 加载播放器 → 播放视频，
        App WebView 嗅探到 MP4 直链（腾讯 CDN，无需 Referer）即可播放。
        """
        # 解析播放 ID: vid|vod_id  或  vid|pkey|vod_id（兼容旧格式）
        parts = str(id).split("|")
        vod_id = parts[-1] if parts else ""

        if not vod_id:
            return {'parse': 0, 'url': '', 'header': {}}

        # 构造详情页 URL — App 在详情页嗅探 MP4 直链
        detail_url = f'{SITE_URL}/{vod_id}.html'

        header = {
            'User-Agent': UA,
            'Referer': SITE_URL + '/',
        }

        return {
            'parse': 1,
            'url': detail_url,
            'header': header,
        }

    # ========== 列表解析 ==========

    def _parse_list(self, html):
        """解析列表页 — WordPress video-item 结构"""
        videos = []

        # 主解析: 匹配 video-item 块
        # 结构: id=post-{ID} class="video-item ..."><div class=qv_tooltip title=" <h4 class=gv-title>{TITLE}</h4>...href={URL}...Watch Now..."><div class=item-thumbnail> <a href={URL}> <img ... data-original={THUMB}
        pattern = re.compile(
            r'id=post-(\d+)\s+class="video-item[^"]*"[^>]*>'
            r'.*?<h4 class=gv-title>([^<]*)</h4>'
            r'.*?href=(https://www\.novipnoad\.uk/[^"\s>]+\.html)[^>]*>Watch Now'
            r'.*?data-original=(https://img\.novipnoad\.uk/[^"\s>]+)',
            re.S
        )

        matches = pattern.findall(html)
        seen = set()
        for pid, title, url, thumb in matches:
            if pid in seen:
                continue
            seen.add(pid)

            # 从 URL 提取 vod_id (去掉域名和 .html)
            # e.g. https://www.novipnoad.uk/movie/154456.html -> movie/154456
            vod_id = re.sub(r'https://www\.novipnoad\.uk/', '', url)
            vod_id = re.sub(r'\.html$', '', vod_id)

            videos.append({
                'vod_id': vod_id,
                'vod_name': self._decode_entities(title.strip()),
                'vod_pic': self._fix_url(thumb),
                'vod_remarks': '',
            })

        # 备用解析: 搜索结果使用不同的布局 (blog-item + video-item)
        if not videos:
            pattern2 = re.compile(
                r'id=post-(\d+)\s+class="[^"]*video-item[^"]*"[^>]*>'
                r'.*?href=(https://www\.novipnoad\.uk/[^"\s>]+\.html)[^>]*title="([^"]*)"'
                r'.*?data-original=(https://img\.novipnoad\.uk/[^"\s>]+)',
                re.S
            )
            for pid, url, title, thumb in pattern2.findall(html):
                if pid in seen:
                    continue
                seen.add(pid)
                vod_id = re.sub(r'https://www\.novipnoad\.uk/', '', url)
                vod_id = re.sub(r'\.html$', '', vod_id)
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': self._decode_entities(title.strip()),
                    'vod_pic': self._fix_url(thumb),
                    'vod_remarks': '',
                })

        # 最终备用: 只提取链接和标题
        if not videos:
            items = re.findall(
                r'href=(https://www\.novipnoad\.uk/(?:movie|tv|anime|shows|music|short|other)/[^"\s>]+\.html)[^>]*title="([^"]*)"',
                html
            )
            for url, title in items:
                vod_id = re.sub(r'https://www\.novipnoad\.uk/', '', url)
                vod_id = re.sub(r'\.html$', '', vod_id)
                if vod_id not in seen:
                    seen.add(vod_id)
                    videos.append({
                        'vod_id': vod_id,
                        'vod_name': self._decode_entities(title.strip()),
                        'vod_pic': '',
                        'vod_remarks': '',
                    })

        return videos


# ==================== 本地测试 ====================
if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()

    spider = Spider()
    spider.init()

    print("=== 首页 ===")
    home = spider.homeContent(True)
    print("分类:", [c["type_name"] for c in home["class"]])
    print("筛选器:", list(home.get("filters", {}).keys()))

    print("\n=== 首页推荐 ===")
    homeVid = spider.homeVideoContent()
    print(f"推荐视频数: {len(homeVid['list'])}")
    for v in homeVid["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']}")

    print("\n=== 分类(电影) ===")
    cat = spider.categoryContent("movie", "1", True, {})
    print(f"视频数: {len(cat['list'])}, 页数: {cat.get('page')}/{cat.get('pagecount')}")
    for v in cat["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']}")

    print("\n=== 分类(韩剧) ===")
    cat2 = spider.categoryContent("tv/korea", "1", True, {})
    print(f"视频数: {len(cat2['list'])}, 页数: {cat2.get('page')}/{cat2.get('pagecount')}")
    for v in cat2["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']}")

    print("\n=== 搜索(导火线) ===")
    search = spider.searchContent("导火线", False)
    print(f"结果数: {len(search['list'])}")
    for v in search["list"][:3]:
        print(f"  - {v['vod_name']} (id: {v['vod_id']})")

    print("\n=== 详情(电影) ===")
    detail = spider.detailContent(["movie/154456"])
    if detail["list"]:
        vod = detail["list"][0]
        print(f"标题: {vod.get('vod_name', '')}")
        print(f"类型: {vod.get('type_name', '')}")
        print(f"年份: {vod.get('vod_year', '')}")
        print(f"演员: {vod.get('vod_actor', '')}")
        print(f"简介: {vod.get('vod_content', '')[:100]}...")
        print(f"播放线路: {vod.get('vod_play_from', '')}")
        print(f"播放URL: {vod.get('vod_play_url', '')[:200]}")

        print("\n=== 播放解析(电影) ===")
        play_urls = vod.get("vod_play_url", "").split("$$$")
        if play_urls and play_urls[0]:
            first_ep = play_urls[0].split("#")[0]
            ep_parts = first_ep.split("$")
            if len(ep_parts) >= 2:
                ep_name, ep_id = ep_parts[0], ep_parts[1]
                print(f"选集: {ep_name}, ID: {ep_id}")
                play = spider.playerContent("", ep_id, [])
                print(f"播放URL: {play.get('url', '')}")
                print(f"parse: {play.get('parse', '')}")
                print(f"header: {play.get('header', {})}")

    print("\n=== 详情(电视剧) ===")
    detail2 = spider.detailContent(["tv/korea/154411"])
    if detail2["list"]:
        vod2 = detail2["list"][0]
        print(f"标题: {vod2.get('vod_name', '')}")
        print(f"播放线路: {vod2.get('vod_play_from', '')}")
        play_url_raw = vod2.get('vod_play_url', '')
        eps = play_url_raw.split("#") if play_url_raw else []
        print(f"集数: {len(eps)}")
        for ep in eps[:3]:
            ep_parts = ep.split("$")
            if len(ep_parts) >= 2:
                print(f"  - {ep_parts[0]} | id: {ep_parts[1][:60]}...")

        print("\n=== 播放解析(电视剧 E09) ===")
        if eps:
            first_ep = eps[0]
            ep_parts = first_ep.split("$")
            if len(ep_parts) >= 2:
                play2 = spider.playerContent("", ep_parts[1], [])
                print(f"播放URL: {play2.get('url', '')}")
                print(f"parse: {play2.get('parse', '')}")
