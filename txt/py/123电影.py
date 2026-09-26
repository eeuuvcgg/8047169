# -*- coding: utf-8 -*-
"""
123电影 (https://a123tv.com) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://a123tv.com
特点: 传统PHP电影站, 服务端渲染HTML, 多线路m3u8聚合
版本: 1.0.0
"""
import sys
import json
import re
import urllib.parse

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    from bs4 import BeautifulSoup

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

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ==================== 常量 ====================
SITE_URL = "https://a123tv.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 24

# 首页分类
CLASSES = [
    {"type_id": "10", "type_name": "电影"},
    {"type_id": "11", "type_name": "连续剧"},
    {"type_id": "12", "type_name": "综艺"},
    {"type_id": "13", "type_name": "动漫"},
    {"type_id": "15", "type_name": "福利"},
]

# 子分类映射 (从首页HTML提取)
TYPE_MAP = {
    # 电影
    "10": "全部电影",
    "1001": "动作片",
    "1002": "喜剧片",
    "1003": "爱情片",
    "1004": "科幻片",
    "1005": "恐怖片",
    "1006": "剧情片",
    "1007": "战争片",
    "1008": "纪录片",
    "1010": "动漫电影",
    "1011": "奇幻片",
    "1013": "动画片",
    "1014": "犯罪片",
    "1016": "悬疑片",
    "1019": "邵氏电影",
    "1022": "歌舞片",
    "1024": "家庭片",
    "1025": "古装片",
    "1026": "历史片",
    "1027": "4K电影",
    # 连续剧
    "11": "全部连续剧",
    "1101": "国产剧",
    "1102": "香港剧",
    "1105": "台湾剧",
    "1103": "韩国剧",
    "1104": "欧美剧",
    "1106": "日本剧",
    "1108": "泰国剧",
    "1110": "港台剧",
    "1111": "日韩剧",
    "1112": "海外剧",
    # 综艺
    "12": "全部综艺",
    "1201": "内地综艺",
    "1202": "港台综艺",
    "1203": "日韩综艺",
    "1204": "欧美综艺",
    "1205": "国外综艺",
    # 动漫
    "13": "全部动漫",
    "1301": "国产动漫",
    "1302": "日韩动漫",
    "1303": "欧美动漫",
    "1304": "海外动漫",
    "1305": "里番",
    # 福利
    "15": "全部福利",
    "1501": "韩国情色片",
    "1502": "日本情色片",
    "1503": "大陆情色片",
    "1504": "香港情色片",
    "1505": "台湾情色片",
    "1506": "美国情色片",
    "1507": "欧洲情色片",
    "1508": "印度情色片",
    "1509": "东南亚情色片",
    "1510": "其它情色片",
}

# 为各大类构建filters
FILTERS = {
    "10": {"类型": [{"n": "全部", "v": "10"}, {"n": "动作片", "v": "1001"}, {"n": "喜剧片", "v": "1002"},
                 {"n": "爱情片", "v": "1003"}, {"n": "科幻片", "v": "1004"}, {"n": "恐怖片", "v": "1005"},
                 {"n": "剧情片", "v": "1006"}, {"n": "战争片", "v": "1007"}, {"n": "纪录片", "v": "1008"},
                 {"n": "动漫电影", "v": "1010"}, {"n": "奇幻片", "v": "1011"}, {"n": "动画片", "v": "1013"},
                 {"n": "犯罪片", "v": "1014"}, {"n": "悬疑片", "v": "1016"}, {"n": "邵氏电影", "v": "1019"},
                 {"n": "歌舞片", "v": "1022"}, {"n": "家庭片", "v": "1024"}, {"n": "古装片", "v": "1025"},
                 {"n": "历史片", "v": "1026"}, {"n": "4K电影", "v": "1027"}]},
    "11": {"类型": [{"n": "全部", "v": "11"}, {"n": "国产剧", "v": "1101"}, {"n": "香港剧", "v": "1102"},
                 {"n": "台湾剧", "v": "1105"}, {"n": "韩国剧", "v": "1103"}, {"n": "欧美剧", "v": "1104"},
                 {"n": "日本剧", "v": "1106"}, {"n": "泰国剧", "v": "1108"}, {"n": "港台剧", "v": "1110"},
                 {"n": "日韩剧", "v": "1111"}, {"n": "海外剧", "v": "1112"}]},
    "12": {"类型": [{"n": "全部", "v": "12"}, {"n": "内地综艺", "v": "1201"}, {"n": "港台综艺", "v": "1202"},
                 {"n": "日韩综艺", "v": "1203"}, {"n": "欧美综艺", "v": "1204"}, {"n": "国外综艺", "v": "1205"}]},
    "13": {"类型": [{"n": "全部", "v": "13"}, {"n": "国产动漫", "v": "1301"}, {"n": "日韩动漫", "v": "1302"},
                 {"n": "欧美动漫", "v": "1303"}, {"n": "海外动漫", "v": "1304"}, {"n": "里番", "v": "1305"}]},
    "15": {"类型": [{"n": "全部", "v": "15"}, {"n": "韩国情色片", "v": "1501"}, {"n": "日本情色片", "v": "1502"},
                 {"n": "大陆情色片", "v": "1503"}, {"n": "香港情色片", "v": "1504"}, {"n": "台湾情色片", "v": "1505"},
                 {"n": "美国情色片", "v": "1506"}, {"n": "欧洲情色片", "v": "1507"}, {"n": "印度情色片", "v": "1508"},
                 {"n": "东南亚情色片", "v": "1509"}, {"n": "其它情色片", "v": "1510"}]},
}


class Spider(Spider):
    """123电影 Spider — 多线路m3u8聚合站"""

    def getName(self):
        return "123电影"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.siteUrl = SITE_URL
        self.headers = {
            'User-Agent': UA,
            'Referer': SITE_URL + '/',
        }

    def isVideoFormat(self, url):
        video_formats = ['.mp4', '.m3u8', '.ts', '.mkv', '.avi', '.webm', '.flv']
        if url and str(url).startswith('http'):
            for fmt in video_formats:
                if fmt in str(url).lower():
                    return True
        return False

    def manualVideoCheck(self):
        return False

    # ========== 工具函数 ==========

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
        if url.startswith('/'):
            return SITE_URL + url
        return url

    def _fetch_html(self, url):
        """获取页面HTML"""
        try:
            rsp = self.fetch(url, headers=self.headers, timeout=15)
            return rsp.text
        except Exception:
            return ''

    def _parse_list_html(self, html):
        """解析列表页HTML, 返回视频列表"""
        videos = []
        if not html:
            return videos

        # 使用正则解析列表项 (比BeautifulSoup更轻量, 兼容性更好)
        # 匹配每个 .w4-item
        items = re.findall(
            r'<a class="w4-item" href="(/v/[^"]+)">.*?<img[^>]+(?:data-src|src)="([^"]+)"[^>]*alt="([^"]*)".*?</figure>\s*<div class="w4-item-info">\s*<div class="t"[^>]*>([^<]+)</div>\s*<div class="i">([^<]+)</div>',
            html, re.DOTALL
        )

        for item in items:
            href, pic, alt, title, info = item
            # info 格式: "剧情片 / 2026年"
            parts = [p.strip() for p in info.split('/')]
            type_name = parts[0] if len(parts) > 0 else ''
            year = parts[1] if len(parts) > 1 else ''

            # 从href提取slug: /v/zhifajiaochadian.html -> zhifajiaochadian
            slug_match = re.search(r'/v/([^/]+)\.html', href)
            slug = slug_match.group(1) if slug_match else ''

            pic = self._fix_url(pic)

            videos.append({
                'vod_id': slug,
                'vod_name': title.strip(),
                'vod_pic': pic,
                'vod_remarks': year,
                'type_name': type_name,
            })

        return videos

    def _parse_detail_html(self, html):
        """解析详情页HTML, 返回影片详情和播放源"""
        result = {}
        if not html:
            return result

        # 提取 var pp={...} 数据
        pp_match = re.search(r'var\s+pp\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not pp_match:
            return result

        try:
            pp = json.loads(pp_match.group(1))
        except Exception:
            return result

        # pp.la: 线路数组 [id, name, episode_count, flag, m3u8_url]
        lines = pp.get('la', [])
        if not lines:
            return result

        # 先判断影片是否多集
        all_ep_counts = set()
        for line in lines:
            if len(line) >= 3:
                all_ep_counts.add(line[2])
        is_multi_ep = len(all_ep_counts) > 1 or (len(all_ep_counts) == 1 and list(all_ep_counts)[0] > 1)

        # 按线路名称分组, 去重 (同一线路同一集只保留一个URL)
        groups = {}
        for line in lines:
            if len(line) < 5:
                continue
            line_id, line_name, ep_count, flag, url = line
            if not url or not str(url).startswith('http'):
                continue
            if line_name not in groups:
                groups[line_name] = {}
            # 用 ep_count 作为key, 同一线路同一集只保留第一个URL
            if ep_count not in groups[line_name]:
                if is_multi_ep:
                    ep_name = f'第{ep_count}集'
                else:
                    ep_name = '正片'
                groups[line_name][ep_count] = {
                    'name': ep_name,
                    'url': url,
                    'ep_count': ep_count,
                }

        # 构建vod_play_from和vod_play_url
        play_from = []
        play_url = []
        for line_name, eps_dict in groups.items():
            # 按集数排序
            eps_sorted = sorted(eps_dict.values(), key=lambda x: x['ep_count'])
            play_from.append(line_name)
            play_url.append('#'.join([f"{ep['name']}${ep['url']}" for ep in eps_sorted]))

        result['vod_play_from'] = '$$$'.join(play_from)
        result['vod_play_url'] = '$$$'.join(play_url)
        return result

    def _has_next_page(self, html):
        """检查是否有下一页"""
        if not html:
            return False
        # 查找下一页链接
        return bool(re.search(r'<a[^>]*href="[^"]*p\d+\.html"[^>]*>下页</a>', html))

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        result['class'] = list(CLASSES)
        if filter:
            result['filters'] = dict(FILTERS)
        return result

    def homeVideoContent(self):
        """首页推荐 — 从首页各分类获取"""
        try:
            html = self._fetch_html(self.siteUrl)
            videos = self._parse_list_html(html)
            return {'list': videos[:48]}
        except Exception:
            return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, '10')
        page = self._safe_page(pg, 1)
        extend = extend or {}

        # 如果有筛选, 使用筛选的类型
        sub_type = extend.get('类型', tid)
        if sub_type:
            tid = sub_type

        try:
            if page == 1:
                url = f"{self.siteUrl}/t/{tid}.html"
            else:
                url = f"{self.siteUrl}/t/{tid}/p{page}.html"

            html = self._fetch_html(url)
            videos = self._parse_list_html(html)

            has_next = self._has_next_page(html) or len(videos) >= PAGE_SIZE
            pagecount = page + 1 if has_next else page

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': PAGE_SIZE,
                'total': 9999,
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

        try:
            encoded = urllib.parse.quote(keyword)
            if page == 1:
                url = f"{self.siteUrl}/s/{encoded}.html"
            else:
                url = f"{self.siteUrl}/s/{encoded}/p{page}.html"

            html = self._fetch_html(url)
            videos = self._parse_list_html(html)

            has_next = self._has_next_page(html) or len(videos) >= PAGE_SIZE
            pagecount = page + 1 if has_next else page

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': PAGE_SIZE,
                'total': 9999,
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if not ids:
            return {'list': []}

        slug = self._safe_str(ids[0])
        if not slug:
            return {'list': []}

        try:
            url = f"{self.siteUrl}/v/{slug}.html"
            html = self._fetch_html(url)

            # 解析详情页获取线路
            detail = self._parse_detail_html(html)
            if not detail:
                return {'list': []}

            # 从HTML中提取更多信息
            # 标题
            title_match = re.search(r'<h1>([^<]+)</h1>', html)
            title = title_match.group(1).strip() if title_match else slug

            # 封面
            pic_match = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
            pic = self._fix_url(pic_match.group(1)) if pic_match else ''
            if not pic:
                pic_match2 = re.search(r'<img[^>]+data-poster="([^"]+)"', html)
                pic = self._fix_url(pic_match2.group(1)) if pic_match2 else ''

            # 描述
            desc_match = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]*)"', html)
            desc = desc_match.group(1).strip() if desc_match else ''

            # 类型/年份/地区等信息
            type_match = re.search(r'<div class="w4-bread">.*?<li><a href="/t/\d+\.html">([^<]+)</a></li>', html, re.DOTALL)
            type_name = type_match.group(1).strip() if type_match else ''

            vod = {
                'vod_id': slug,
                'vod_name': title,
                'vod_pic': pic,
                'type_name': type_name,
                'vod_content': desc,
                'vod_play_from': detail.get('vod_play_from', ''),
                'vod_play_url': detail.get('vod_play_url', ''),
            }

            return {'list': [vod]}
        except Exception:
            return {'list': []}

    # ========== 播放 ==========

    def playerContent(self, flag, id, vipFlags):
        """
        flag: 线路名称
        id: 播放URL (m3u8)
        """
        return {
            'parse': 0,
            'url': id,
            'header': json.dumps(self.headers),
        }

    def localProxy(self, param):
        return [200, "video/MP2T", "", ""]
