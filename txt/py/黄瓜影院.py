# -*- coding: utf-8 -*-
"""
黄瓜影院 (https://www.u36uj.com) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.u36uj.com
特点: 苹果CMS V10, 服务端渲染HTML, 多线路m3u8聚合
版本: 1.1.0
更新: 支持分类、列表、详情、播放、搜索; 修复列表备注提取、详情播放列表解析、分页总页数提取
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
SITE_URL = "https://www.u36uj.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 24

# 首页分类
CLASSES = [
    {"type_id": "1", "type_name": "电视剧"},
    {"type_id": "2", "type_name": "电影"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
]

# 子分类映射
TYPE_MAP = {
    # 电视剧
    "1": "全部电视剧",
    "6": "国产剧",
    "7": "香港剧",
    "8": "台湾剧",
    "9": "韩国剧",
    "10": "日本剧",
    "11": "欧美剧",
    "12": "海外剧",
    "13": "泰国剧",
    # 电影
    "2": "全部电影",
    "14": "动作片",
    "15": "喜剧片",
    "16": "爱情片",
    "17": "科幻片",
    "18": "恐怖片",
    "19": "剧情片",
    "20": "战争片",
    "21": "纪录片",
    # 综艺
    "3": "全部综艺",
    "22": "内地综艺",
    "23": "港台综艺",
    "24": "日韩综艺",
    "25": "欧美综艺",
    # 动漫
    "4": "全部动漫",
    "26": "国产动漫",
    "27": "日韩动漫",
    "28": "欧美动漫",
    "29": "海外动漫",
}

# 为各大类构建filters
FILTERS = {
    "1": {"类型": [{"n": "全部", "v": "1"}, {"n": "国产剧", "v": "6"},
                 {"n": "香港剧", "v": "7"}, {"n": "台湾剧", "v": "8"},
                 {"n": "韩国剧", "v": "9"}, {"n": "日本剧", "v": "10"},
                 {"n": "欧美剧", "v": "11"}, {"n": "海外剧", "v": "12"},
                 {"n": "泰国剧", "v": "13"}]},
    "2": {"类型": [{"n": "全部", "v": "2"}, {"n": "动作片", "v": "14"},
                 {"n": "喜剧片", "v": "15"}, {"n": "爱情片", "v": "16"},
                 {"n": "科幻片", "v": "17"}, {"n": "恐怖片", "v": "18"},
                 {"n": "剧情片", "v": "19"}, {"n": "战争片", "v": "20"},
                 {"n": "纪录片", "v": "21"}]},
    "3": {"类型": [{"n": "全部", "v": "3"}, {"n": "内地综艺", "v": "22"},
                 {"n": "港台综艺", "v": "23"}, {"n": "日韩综艺", "v": "24"},
                 {"n": "欧美综艺", "v": "25"}]},
    "4": {"类型": [{"n": "全部", "v": "4"}, {"n": "国产动漫", "v": "26"},
                 {"n": "日韩动漫", "v": "27"}, {"n": "欧美动漫", "v": "28"},
                 {"n": "海外动漫", "v": "29"}]},
}


class Spider(Spider):
    """黄瓜影院 Spider — 苹果CMS多线路m3u8聚合站"""

    def getName(self):
        return "黄瓜影院"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.siteUrl = SITE_URL

        # 支持从extend解析代理配置
        self.proxy = None
        if self.extend:
            if self.extend.startswith('http://') or self.extend.startswith('https://') or self.extend.startswith('socks'):
                self.proxy = self.extend
            elif self.extend.startswith('proxy='):
                self.proxy = self.extend.split('=', 1)[1]

        self.headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': SITE_URL + '/',
            'Upgrade-Insecure-Requests': '1',
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
        """获取页面HTML — 带重试和SSL容错"""
        last_err = None
        for attempt in range(3):
            try:
                kw = {}
                if self.proxy:
                    kw['proxies'] = {'http': self.proxy, 'https': self.proxy}
                try:
                    rsp = self.fetch(url, headers=self.headers, timeout=20, verify=False, **kw)
                except TypeError:
                    rsp = self.fetch(url, headers=self.headers, timeout=20, **kw)
                return rsp.text
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if any(x in err_str for x in ['timeout', 'connection', 'ssl', 'reset', 'closed']):
                    import time
                    time.sleep(1 + attempt)
                    continue
                break
        return ''

    def _parse_list_html(self, html):
        """解析列表页HTML, 返回视频列表"""
        videos = []
        if not html:
            return videos

        # 匹配 stui-vodlist__box 中的内容
        # 使用DOTALL匹配整个<a>...</a>块,再从中提取pic-text
        pattern = r'<div class="stui-vodlist__box">\s*<a class="stui-vodlist__thumb[^"]*" href="(/g/(\d+)\.html)" title="([^"]*)" data-original="([^"]*)"[^>]*>(.*?)</a>'
        
        matches = re.findall(pattern, html, re.DOTALL)
        for match in matches:
            href, vod_id, title, pic, inner = match
            # 从<a>内部提取备注(pic-text)
            remarks = ''
            remarks_match = re.search(r'<span class="pic-text[^"]*">([^<]*)</span>', inner)
            if remarks_match:
                remarks = remarks_match.group(1).strip()
            videos.append({
                'vod_id': vod_id,
                'vod_name': title.strip(),
                'vod_pic': self._fix_url(pic.strip()),
                'vod_remarks': remarks,
                'type_name': '',
            })

        return videos

    def _parse_detail_html(self, html):
        """解析详情页HTML, 返回影片详情和播放源"""
        result = {}
        if not html:
            return result

        # 提取标题
        title = ''
        title_match = re.search(r'<h1 class="title">([^<]+)</h1>', html)
        if title_match:
            title = title_match.group(1).strip()
        result['vod_name'] = title

        # 提取封面
        pic = ''
        pic_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if not pic_match:
            pic_match = re.search(r'data-original="([^"]+)"[^>]*class="[^"]*v-thumb[^"]*"', html)
        if pic_match:
            pic = self._fix_url(pic_match.group(1))
        result['vod_pic'] = pic

        # 提取描述
        desc = ''
        desc_match = re.search(r'<span class="detail-content"[^>]*>(.*?)</span>', html, re.DOTALL)
        if not desc_match:
            desc_match = re.search(r'<span class="detail-sketch"[^>]*>(.*?)</span>', html, re.DOTALL)
        if desc_match:
            desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
        if not desc:
            desc_match = re.search(r'<meta name="description" content="([^"]*)"', html)
            if desc_match:
                desc = desc_match.group(1).strip()
        result['vod_content'] = desc

        # 提取年份
        year = ''
        year_match = re.search(r'<a href="/search\.php\?[^"]*year=(\d{4})"', html)
        if year_match:
            year = year_match.group(1)
        result['vod_year'] = year

        # 提取地区
        area = ''
        area_match = re.search(r'地区.*?</span>\s*<a href="/search\.php\?[^"]*">([^<]+)</a>', html)
        if area_match:
            area = area_match.group(1).strip()
        result['vod_area'] = area

        # 提取导演
        director = ''
        director_match = re.search(r'<span class="text-muted">导演：</span>(.*?)</p>', html)
        if director_match:
            director_html = director_match.group(1)
            directors = re.findall(r'<a[^>]*>([^<]+)</a>', director_html)
            director = ', '.join(directors)
        result['vod_director'] = director

        # 提取演员
        actor = ''
        actor_match = re.search(r'<span class="text-muted">主演：</span>(.*?)</p>', html)
        if actor_match:
            actor_html = actor_match.group(1)
            actors = re.findall(r'<a[^>]*>([^<]+)</a>', actor_html)
            actor = ', '.join(actors)
        result['vod_actor'] = actor

        # 提取类型
        type_name = ''
        type_match = re.search(r'<span class="text-muted">类型：</span>\s*<a href="/h/(\d+)\.html">([^<]+)</a>', html)
        if type_match:
            type_name = type_match.group(2).strip()
        result['type_name'] = type_name

        # 提取播放线路和播放列表
        play_from = []
        play_url = []

        # 查找所有播放线路
        line_pattern = r'<li[^>]*>\s*<a href="#[^"]*" data-toggle="tab">([^<]+)</a>\s*</li>'
        lines = re.findall(line_pattern, html)

        # 查找所有播放列表 — 直接匹配ul内容,更稳健
        playlist_pattern = r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>(.*?)</ul>'
        playlists = re.findall(playlist_pattern, html, re.DOTALL)

        if lines and playlists:
            for i, line_name in enumerate(lines):
                if i < len(playlists):
                    # 提取该线路下的所有播放链接
                    episode_pattern = r'<a[^>]*href="(/play/(\d+-\d+-\d+)\.html)"[^>]*>([^<]+)</a>'
                    episodes = re.findall(episode_pattern, playlists[i])
                    
                    if episodes:
                        play_from.append(line_name.strip())
                        episode_urls = []
                        for ep in episodes:
                            ep_href, ep_id, ep_name = ep
                            episode_urls.append(f"{ep_name}${SITE_URL}{ep_href}")
                        play_url.append('#'.join(episode_urls))

        result['vod_play_from'] = '$$$'.join(play_from) if play_from else ''
        result['vod_play_url'] = '$$$'.join(play_url) if play_url else ''

        return result

    # ========== 核心接口 ==========

    def homeContent(self, filter):
        """首页内容 — 返回分类和推荐"""
        result = {}
        result['class'] = CLASSES
        if filter:
            result['filters'] = FILTERS

        # 获取首页推荐
        html = self._fetch_html(SITE_URL)
        videos = self._parse_list_html(html)
        result['list'] = videos[:12]  # 首页只显示12个
        return result

    def homeVideoContent(self):
        """首页视频推荐"""
        html = self._fetch_html(SITE_URL)
        videos = self._parse_list_html(html)
        return {'list': videos[:12]}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容 — 返回指定分类的视频列表"""
        result = {}
        page = self._safe_page(pg, 1)
        
        # 页面从0开始
        page_index = page - 1
        if page_index < 0:
            page_index = 0

        # 构建URL
        url = f"{SITE_URL}/h/{tid}-{page_index}.html"
        html = self._fetch_html(url)
        videos = self._parse_list_html(html)

        # 从分页信息提取总页数, 如 <span class="num">0/2464</span>
        pagecount = page
        total_pages_match = re.search(r'<span[^>]*class="[^"]*num[^"]*"[^>]*>\s*\d+\s*/\s*(\d+)\s*</span>', html)
        if total_pages_match:
            pagecount = int(total_pages_match.group(1)) + 1  # 网站页码从0开始, +1转成1-based
        else:
            # 备用: 检查是否有下一页或尾页链接
            has_next = f'/h/{tid}.html' in html or f'/h/{tid}-{page_index + 1}.html' in html
            if has_next:
                pagecount = page + 1

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = pagecount
        result['limit'] = PAGE_SIZE
        result['total'] = pagecount * PAGE_SIZE
        return result

    def detailContent(self, array):
        """详情内容 — 返回影片详情和播放源"""
        vod_id = array[0] if array else ''
        if not vod_id:
            return {'list': []}

        url = f"{SITE_URL}/g/{vod_id}.html"
        html = self._fetch_html(url)
        result = self._parse_detail_html(html)
        result['vod_id'] = vod_id
        return {'list': [result]}

    def playerContent(self, flag, id, vipFlags):
        """播放内容 — 返回播放URL"""
        # id 格式: https://www.u36uj.com/play/119150-0-0.html
        if id.startswith('http'):
            url = id
        else:
            url = f"{SITE_URL}/play/{id}.html"

        html = self._fetch_html(url)

        # 尝试提取m3u8或mp4链接
        video_url = ''
        
        # 查找iframe中的播放链接
        iframe_match = re.search(r'<iframe[^>]*src="([^"]+)"', html)
        if iframe_match:
            video_url = iframe_match.group(1)
            if not video_url.startswith('http'):
                video_url = self._fix_url(video_url)
        
        # 查找script中的播放链接
        if not video_url:
            script_match = re.search(r'var\s+url\s*=\s*["\']([^"\']+)["\']', html)
            if script_match:
                video_url = script_match.group(1)
        
        # 查找m3u8链接
        if not video_url:
            m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
            if m3u8_match:
                video_url = m3u8_match.group(1)
        
        # 查找mp4链接
        if not video_url:
            mp4_match = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html)
            if mp4_match:
                video_url = mp4_match.group(1)

        return {
            'parse': 1 if video_url and not video_url.endswith(('.m3u8', '.mp4', '.ts')) else 0,
            'playUrl': '',
            'url': video_url,
            'header': self.headers,
        }

    def searchContent(self, key, quick):
        """搜索内容
        注意: 该站点搜索接口目前返回503,可能是临时限制或反爬策略
        """
        result = {}
        search_word = urllib.parse.quote(key)
        url = f"{SITE_URL}/search.php?searchword={search_word}"
        html = self._fetch_html(url)
        videos = self._parse_list_html(html)
        result['list'] = videos
        return result

    def searchContentPage(self, key, quick, pg):
        """搜索内容(分页)"""
        return self.searchContent(key, quick)

    def localProxy(self, param):
        """本地代理"""
        return [200, "video/MP2T", "", ""]
