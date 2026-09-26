# -*- coding: utf-8 -*-
"""
555电影 (https://www.55dy8.com) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.55dy8.com
API: HTML采集 + AES-CBC播放解密(encrypt=3)
版本: 1.0.0
"""
import sys
import json
import re
import base64
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
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# ==================== 常量 ====================
SITE_URL = "https://www.55dy8.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 20

# AES解密参数 (encrypt=3模式, 从player.html混淆JS拦截获得)
AES_KEY = b"81f834a7f68d4c52"  # 16字节
AES_IV = b"zkz8scsGXttFVZBb"   # 16字节

# 首页分类
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "连续剧"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "3", "type_name": "综艺纪录"},
    {"type_id": "126", "type_name": "擦边短剧"},
]

# 筛选器 — 每个分类同结构
_YEAR_VALUES = [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"},
    {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"},
    {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"},
    {"n": "2010-2015", "v": "2010-2015"}, {"n": "2000-2009", "v": "2000-2009"},
    {"n": "1990-1999", "v": "1990-1999"},
]

_SORT_VALUES = [
    {"n": "按更新", "v": "time"},
    {"n": "按热度", "v": "hits"},
    {"n": "按评分", "v": "score"},
]

_CLASS_VALUES_1 = [
    {"n": "全部", "v": ""},
    {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
    {"n": "科幻", "v": "科幻"}, {"n": "恐怖", "v": "恐怖"}, {"n": "剧情", "v": "剧情"},
    {"n": "战争", "v": "战争"}, {"n": "悬疑", "v": "悬疑"}, {"n": "犯罪", "v": "犯罪"},
    {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"}, {"n": "冒险", "v": "冒险"},
    {"n": "武侠", "v": "武侠"}, {"n": "历史", "v": "历史"}, {"n": "惊悚", "v": "惊悚"},
]

_AREA_VALUES_1 = [
    {"n": "全部", "v": ""},
    {"n": "中国", "v": "中国"}, {"n": "美国", "v": "美国"}, {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"},
    {"n": "德国", "v": "德国"}, {"n": "印度", "v": "印度"}, {"n": "中国香港", "v": "中国香港"},
    {"n": "中国台湾", "v": "中国台湾"}, {"n": "意大利", "v": "意大利"},
    {"n": "西班牙", "v": "西班牙"}, {"n": "泰国", "v": "泰国"},
]

_CLASS_VALUES_2 = [
    {"n": "全部", "v": ""},
    {"n": "国产剧", "v": "国产剧"}, {"n": "日剧", "v": "日剧"}, {"n": "韩剧", "v": "韩剧"},
    {"n": "欧美剧", "v": "欧美剧"}, {"n": "港剧", "v": "港剧"}, {"n": "台剧", "v": "台剧"},
    {"n": "海外剧", "v": "海外剧"}, {"n": "泰剧", "v": "泰剧"}, {"n": "纪录片", "v": "纪录片"},
]

_AREA_VALUES_2 = [
    {"n": "全部", "v": ""},
    {"n": "中国", "v": "中国"}, {"n": "美国", "v": "美国"}, {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"}, {"n": "英国", "v": "英国"},
    {"n": "中国香港", "v": "中国香港"}, {"n": "中国台湾", "v": "中国台湾"},
]

_YEAR_VALUES_2 = [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"},
    {"n": "2020", "v": "2020"}, {"n": "2010-2019", "v": "2010-2019"},
]

_CLASS_VALUES_4 = [
    {"n": "全部", "v": ""},
    {"n": "国产动漫", "v": "国产动漫"}, {"n": "日本动漫", "v": "日本动漫"},
    {"n": "欧美动漫", "v": "欧美动漫"}, {"n": "海外动漫", "v": "海外动漫"},
]

_AREA_VALUES_4 = [
    {"n": "全部", "v": ""},
    {"n": "中国", "v": "中国"}, {"n": "日本", "v": "日本"},
    {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
]

_YEAR_VALUES_4 = [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"},
    {"n": "2020", "v": "2020"},
]

_CLASS_VALUES_3 = [
    {"n": "全部", "v": ""},
    {"n": "综艺", "v": "综艺"}, {"n": "纪录", "v": "纪录"},
]

_AREA_VALUES_3 = [
    {"n": "全部", "v": ""},
    {"n": "中国", "v": "中国"}, {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"}, {"n": "美国", "v": "美国"},
]

_YEAR_VALUES_3 = [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
]

_CLASS_VALUES_126 = [
    {"n": "全部", "v": ""},
    {"n": "短剧", "v": "短剧"},
]

_AREA_VALUES_126 = [
    {"n": "全部", "v": ""},
    {"n": "中国", "v": "中国"},
]

_YEAR_VALUES_126 = [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
]

_SORT_VALUES_126 = [
    {"n": "按更新", "v": "time"},
    {"n": "按热度", "v": "hits"},
]

FILTERS = {
    "1": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_1},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_1},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "2": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_2},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_2},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES_2},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "4": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_4},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_4},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES_4},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "3": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_3},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_3},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES_3},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "126": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_126},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_126},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES_126},
        {"key": "by", "name": "排序", "value": _SORT_VALUES_126},
    ],
}


class Spider(Spider):
    """555电影 Spider — HTML采集型"""

    def getName(self):
        return "555电影"

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
        """统一请求方法 — 使用基类fetch"""
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
    def _fix_url(site_url, url):
        if not url:
            return ''
        url = str(url).strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('http'):
            return url
        if url.startswith('/'):
            return site_url.rstrip('/') + url
        return url

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        result['class'] = list(CLASSES)
        if filter:
            result['filters'] = dict(FILTERS)
        return result

    def homeVideoContent(self):
        try:
            rsp = self._request(f'{SITE_URL}/vodshow/1--time------1---.html')
            if rsp and rsp.status_code == 200:
                html = rsp.text
                videos = self._parse_list(html)
                return {'list': videos[:72]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, '1')
        page = self._safe_page(pg, 1)
        extend = extend or {}

        area = self._safe_str(extend.get('area', ''))
        by = self._safe_str(extend.get('by', 'time')) or 'time'
        cls = self._safe_str(extend.get('class', ''))
        year = self._safe_str(extend.get('year', ''))

        # URL编码中文参数
        if area:
            area = urllib.parse.quote(area)
        if cls:
            cls = urllib.parse.quote(cls)
        if year:
            year = urllib.parse.quote(year)

        # URL格式: /vodshow/{tid}-{area}-{by}-{cls}----{year}-{page}---.html
        url = f'{SITE_URL}/vodshow/{tid}-{area}-{by}-{cls}----{year}-{page}---.html'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

            html = rsp.text
            videos = self._parse_list(html)

            # 解析页数
            pagecount = page
            pc_match = re.search(r'<a[^>]*href="[^"]*-(\d+)---\.html"[^>]*>下一页</a>', html)
            if pc_match:
                pagecount = max(page, int(pc_match.group(1)))

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

        key_encoded = urllib.parse.quote(keyword)
        url = f'{SITE_URL}/vodsearch/{key_encoded}-------------.html'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

            html = rsp.text
            videos = self._parse_search(html)

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
        vod_id = str(ids[0])
        url = f'{SITE_URL}/voddetail/{vod_id}.html'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}
            html = rsp.text
        except Exception:
            return {'list': []}

        vod = {'vod_id': vod_id}

        # 标题
        title_match = re.search(r'<h1[^>]*class="page-title"[^>]*>(.*?)</h1>', html, re.S)
        if not title_match:
            title_match = re.search(r'<h1[^>]*>([^<]*)</h1>', html)
        vod['vod_name'] = title_match.group(1).strip() if title_match else ""

        # 图片
        pic_match = re.search(r'<img[^>]*class="lazy lazyload"[^>]*data-original="([^"]*)"', html)
        if not pic_match:
            pic_match = re.search(r'<img[^>]*data-original="([^"]*)"', html)
        vod['vod_pic'] = pic_match.group(1).replace("&amp;", "&") if pic_match else ""

        # 类型
        cat_links = re.findall(r'href="/vodshow/\d+---%[0-9A-Fa-f]+[^"]*"[^>]*>([^<]+)</a>', html)
        if cat_links:
            vod['type_name'] = " ".join(cat_links)
        else:
            vod['type_name'] = ""

        # 年份
        year_match = re.search(r'href="/vodshow/\d+-----------(20\d{2})\.html"', html)
        if not year_match:
            year_match = re.search(r'>(20\d{2})</a>', html)
        vod['vod_year'] = year_match.group(1) if year_match else ""

        # 地区
        area_match = re.search(r'href="/vodshow/\d+-%[0-9A-Fa-f]+[^"]*"[^>]*>([^<]+)</a>', html)
        if area_match:
            vod['vod_area'] = area_match.group(1)
        else:
            vod['vod_area'] = ""

        # 导演
        director_match = re.search(r'导演[：:]\s*</span>\s*<div[^>]*>(.*?)</div>', html, re.S)
        if director_match:
            directors = re.findall(r'>([^<]+)</a>', director_match.group(1))
            vod['vod_director'] = " / ".join([d.strip() for d in directors if d.strip()])
        else:
            vod['vod_director'] = ""

        # 主演
        actor_match = re.search(r'主演[：:]\s*</span>\s*<div[^>]*>(.*?)</div>', html, re.S)
        if actor_match:
            actors = re.findall(r'>([^<]+)</a>', actor_match.group(1))
            vod['vod_actor'] = " / ".join([a.strip() for a in actors if a.strip()])
        else:
            vod['vod_actor'] = ""

        # 简介
        desc_match = re.search(r'class="module-info-introduction-content[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if desc_match:
            desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
            desc = re.sub(r'&nbsp;', ' ', desc)
            vod['vod_content'] = desc
        else:
            vod['vod_content'] = ""

        # 播放列表
        play_from_list = []
        play_url_list = []

        tab_items = re.findall(r'<div class="module-tab-item[^"]*"[^>]*>(.*?)</div>', html, re.S)
        episode_blocks = re.findall(r'<div class="module-play-list-content[^"]*">(.*?)</div>', html, re.S)

        for i, block in enumerate(episode_blocks):
            line_name = f"线路{i+1}"
            if i < len(tab_items):
                name_match = re.search(r'>([^<]+)<', tab_items[i])
                if name_match:
                    line_name = name_match.group(1).strip()

            episodes = re.findall(
                r'<a[^>]*href="(/vodplay/[^"]+\.html)"[^>]*>(?:.*?<span>)?([^<]*)(?:</span>)?</a>',
                block, re.S
            )
            if not episodes:
                episodes = re.findall(
                    r'<a[^>]*href="(/vodplay/[^"]+\.html)"[^>]*title="([^"]*)"',
                    block, re.S
                )

            ep_list = []
            for ep_url, ep_name in episodes:
                ep_name = ep_name.strip() if ep_name else ""
                if not ep_name:
                    ep_name = "播放"
                play_match = re.search(r'/vodplay/(\d+)-(\d+)-(\d+)\.html', ep_url)
                if play_match:
                    play_key = f"{play_match.group(1)}-{play_match.group(2)}-{play_match.group(3)}"
                    ep_list.append(f"{ep_name}${play_key}")

            if ep_list:
                play_from_list.append(line_name)
                play_url_list.append("#".join(ep_list))

        vod['vod_play_from'] = "$$$".join(play_from_list)
        vod['vod_play_url'] = "$$$".join(play_url_list)

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        result = {}

        parts = str(id).split("-")
        if len(parts) < 3:
            return {'parse': 0, 'url': '', 'header': {}}

        vod_id, sid, nid = parts[0], parts[1], parts[2]
        play_url = f'{SITE_URL}/vodplay/{vod_id}-{sid}-{nid}.html'

        try:
            rsp = self._request(play_url)
            if not rsp or rsp.status_code != 200:
                return {'parse': 0, 'url': '', 'header': {}}

            html = rsp.text
        except Exception:
            return {'parse': 0, 'url': '', 'header': {}}

        # 提取player_aaaa (用括号匹配获取完整JSON)
        player_match = re.search(r'player_aaaa\s*=\s*', html)
        if not player_match:
            return {'parse': 0, 'url': '', 'header': {}}

        json_start = html.find('{', player_match.end())
        if json_start < 0:
            return {'parse': 0, 'url': '', 'header': {}}

        depth = 0
        json_end = json_start
        for i in range(json_start, min(json_start + 10000, len(html))):
            if html[i] == '{':
                depth += 1
            elif html[i] == '}':
                depth -= 1
                if depth == 0:
                    json_end = i + 1
                    break

        try:
            player_data = json.loads(html[json_start:json_end])
        except Exception:
            return {'parse': 0, 'url': '', 'header': {}}

        encrypt = player_data.get("encrypt", 0)
        enc_url = player_data.get("url", "")

        if not enc_url:
            return {'parse': 0, 'url': '', 'header': {}}

        # 根据encrypt类型解密
        play_url = ""
        if encrypt == 0 or encrypt == 1 or encrypt == 2:
            play_url = enc_url
        elif encrypt == 3:
            play_url = self._decrypt_url(enc_url)

        header = {
            'User-Agent': UA,
            'Referer': SITE_URL + '/',
        }

        if play_url and self.isVideoFormat(play_url):
            return {
                'parse': 0,
                'url': play_url,
                'header': header,
            }
        elif play_url:
            return {
                'parse': 1,
                'url': play_url,
                'header': header,
            }
        else:
            # 嗅探备用方案
            sniff_patterns = [
                r'"url"\s*:\s*"([^"]*\.m3u8[^"]*)"',
                r'"url"\s*:\s*"([^"]*\.mp4[^"]*)"',
                r'source\s*=\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            ]
            for sniff_re in sniff_patterns:
                sniff_match = re.search(sniff_re, html)
                if sniff_match:
                    sniffed_url = sniff_match.group(1).replace("\\/", "/")
                    return {
                        'parse': 0,
                        'url': sniffed_url,
                        'header': header,
                    }

        return {'parse': 0, 'url': '', 'header': {}}

    # ========== 解密 ==========

    def _decrypt_url(self, enc_url):
        if not HAS_CRYPTO:
            return enc_url
        try:
            processed = enc_url.replace("O0O0O", "=").replace("o000o", "+").replace("oo00o", "/")
            ciphertext = base64.b64decode(processed)
            cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
            decrypted = cipher.decrypt(ciphertext)
            try:
                result = unpad(decrypted, AES.block_size)
                return result.decode('utf-8')
            except Exception:
                return decrypted.rstrip(b'\x00').decode('utf-8', errors='ignore')
        except Exception:
            return ""

    # ========== 列表解析 ==========

    def _parse_list(self, html):
        """解析列表页"""
        videos = []

        # 主解析: 匹配 <a> 包含 module-poster-item 的完整块
        pattern = re.compile(
            r'<a[^>]*href="/voddetail/(\d+)\.html"[^>]*title="([^"]*)"[^>]*>.*?'
            r'data-original="([^"]*)"[^>]*>.*?'
            r'class="module-item-note"[^>]*>([^<]*)</div>.*?</a>',
            re.S
        )

        matches = pattern.findall(html)
        for vid, title, pic, note in matches:
            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic.replace("&amp;", "&"),
                'vod_remarks': note.strip(),
            })

        # 备用解析: data-original 在 href 之前的情况
        if not videos:
            pattern2 = re.compile(
                r'data-original="([^"]*)"[^>]*alt="([^"]*)".*?'
                r'<a[^>]*href="/voddetail/(\d+)\.html"',
                re.S
            )
            for pic, title, vid in pattern2.findall(html):
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic.replace("&amp;", "&"),
                    'vod_remarks': '',
                })

        # 最终备用: 只取 voddetail 链接
        if not videos:
            items = re.findall(
                r'<a[^>]*href="/voddetail/(\d+)\.html"[^>]*title="([^"]*)"',
                html
            )
            seen = set()
            for vid, title in items:
                if vid not in seen:
                    seen.add(vid)
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': '',
                        'vod_remarks': '',
                    })

        return videos

    def _parse_search(self, html):
        """解析搜索结果"""
        videos = []

        # 主解析: 搜索结果中的 module-card-item-poster
        pattern = re.compile(
            r'<a[^>]*href="/voddetail/(\d+)\.html"[^>]*class="module-card-item-poster"[^>]*>.*?'
            r'class="module-item-note"[^>]*>([^<]*)</div>.*?'
            r'data-original="([^"]*)"[^>]*alt="([^"]*)"',
            re.S
        )

        matches = pattern.findall(html)
        for vid, note, pic, title in matches:
            title = re.sub(r'<[^>]+>', '', title).strip()
            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic.replace("&amp;", "&"),
                'vod_remarks': note.strip(),
            })

        # 备用解析: 标题在 <em> 标签中
        if not videos:
            items = re.findall(
                r'<a[^>]*href="/voddetail/(\d+)\.html"[^>]*>(?:<strong>)?<em>([^<]*)</em>',
                html
            )
            seen = set()
            for vid, title in items:
                if vid not in seen:
                    seen.add(vid)
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
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
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')}")

    print("\n=== 分类(电影) ===")
    cat = spider.categoryContent("1", "1", True, {})
    print(f"视频数: {len(cat['list'])}, 页数: {cat.get('page')}/{cat.get('pagecount')}")
    for v in cat["list"][:3]:
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')}")

    print("\n=== 搜索(八仙) ===")
    search = spider.searchContent("八仙", False)
    print(f"结果数: {len(search['list'])}")
    for v in search["list"][:3]:
        print(f"  - {v['vod_name']} (id: {v['vod_id']})")

    print("\n=== 详情 ===")
    if search["list"]:
        detail = spider.detailContent([search["list"][0]["vod_id"]])
        if detail["list"]:
            vod = detail["list"][0]
            print(f"标题: {vod.get('vod_name', '')}")
            print(f"类型: {vod.get('type_name', '')}")
            print(f"导演: {vod.get('vod_director', '')}")
            print(f"播放线路: {vod.get('vod_play_from', '')[:80]}")

            # 测试播放
            print("\n=== 播放解析 ===")
            play_urls = vod.get("vod_play_url", "").split("$$$")
            if play_urls and play_urls[0]:
                first_ep = play_urls[0].split("#")[0]
                parts = first_ep.split("$")
                if len(parts) >= 2:
                    ep_name, ep_id = parts[0], parts[1]
                    print(f"选集: {ep_name}, ID: {ep_id}")
                    play = spider.playerContent("", ep_id, [])
                    print(f"播放URL: {play.get('url', '')[:100]}")
                    print(f"parse: {play.get('parse', '')}")
