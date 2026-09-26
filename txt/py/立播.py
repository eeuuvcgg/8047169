# -*- coding: utf-8 -*-
"""
立播|4K (LIBVIO) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.libvio.pw
CMS类型: 苹果CMS(MacCMS) + 自定义播放解析
特点: 多线路播放, 需服务端解析(/vid/yd.php, /vid/ty4.php)
版本: 2.0.0
更新: 完全重写播放解析(服务端解析替代encrypt=3客户端解密), 修正分类页page为1-indexed,
      修正搜索参数为wd=, 使用BeautifulSoup解析HTML, base64urlsafe编码播放ID
"""
import sys
import json
import re
import time
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
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ==================== 常量 ====================
SITE_URL = "https://www.libvio.pw"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
PAGE_SIZE = 20

# 首页分类: 电影(1)、剧集(2)、番剧(4)、日韩(15)、欧美(16)
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "剧集"},
    {"type_id": "4", "type_name": "番剧"},
    {"type_id": "15", "type_name": "日韩"},
    {"type_id": "16", "type_name": "欧美"},
]

# 筛选选项 — 地区
_AREA_OPTIONS = [
    {"n": "全部地区", "v": ""},
    {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"},
    {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
    {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"}, {"n": "德国", "v": "德国"},
    {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"}, {"n": "其他", "v": "其他"},
]

# 筛选选项 — 年份 (2015-2026)
_YEAR_OPTIONS = [{"n": "全部年份", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2014, -1)]

# 筛选选项 — 语言
_LANG_OPTIONS = [
    {"n": "全部语言", "v": ""},
    {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"}, {"n": "粤语", "v": "粤语"},
    {"n": "闽南语", "v": "闽南语"}, {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"},
    {"n": "法语", "v": "法语"}, {"n": "德语", "v": "德语"}, {"n": "其他", "v": "其他"},
]

# 筛选选项 — 排序
_BY_OPTIONS = [
    {"n": "时间排序", "v": "time"},
    {"n": "人气排序", "v": "hits"},
    {"n": "评分排序", "v": "score"},
]

# 为每个分类构建filters: area(地区)、year(年份)、lang(语言)、by(排序)
FILTERS = {
    tid: {"地区": _AREA_OPTIONS, "年份": _YEAR_OPTIONS, "语言": _LANG_OPTIONS, "排序": _BY_OPTIONS}
    for tid in ["1", "2", "4", "15", "16"]
}

# 播放线路映射
PLAYER_LIST = {
    "yd189": "HD5播放",
    "ty_new1": "BD播放",
}


class Spider(Spider):
    """立播|4K (LIBVIO) Spider — 苹果CMS + 自定义播放解析"""

    def getName(self):
        return "立播|4K"

    def init(self, extend=""):
        # 处理extend参数
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
        """安全字符串转换"""
        if val is None or val == '' or val == 'None':
            return default
        return str(val).strip()

    @staticmethod
    def _safe_page(pg, default=1):
        """安全页码转换"""
        try:
            p = int(pg)
            return p if p > 0 else default
        except Exception:
            return default

    @staticmethod
    def _fix_url(url):
        """修复URL — 补全协议和域名"""
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

    def _fetch_html(self, url, headers=None):
        """获取页面HTML — 带重试和SSL容错"""
        use_headers = headers if headers else self.headers
        for attempt in range(3):
            try:
                kw = {}
                if self.proxy:
                    kw['proxies'] = {'http': self.proxy, 'https': self.proxy}
                try:
                    rsp = self.fetch(url, headers=use_headers, timeout=20, verify=False, **kw)
                except TypeError:
                    rsp = self.fetch(url, headers=use_headers, timeout=20, **kw)
                if hasattr(rsp, 'status_code') and rsp.status_code == 404:
                    return ''
                return rsp.text
            except Exception as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ['timeout', 'connection', 'ssl', 'reset', 'closed']):
                    time.sleep(1 + attempt)
                    continue
                break
        return ''

    # ========== 列表页解析 ==========

    def _parse_list_html(self, html):
        """解析列表页HTML, 返回视频列表
        选择器: a.stui-vodlist__thumb[href^="/detail/"]
        标题: title属性, 缺则取文本
        封面: data-original → data-src → src
        备注: .pic-text 文本
        ID: 从href提取 /detail/{id}.html → {id}
        """
        videos = []
        if not html:
            return videos

        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('a.stui-vodlist__thumb[href^="/detail/"]')
            for item in items:
                href = item.get('href', '')
                id_match = re.search(r'/detail/(\d+)\.html', href)
                if not id_match:
                    continue
                vod_id = id_match.group(1)
                # 标题: title属性, 缺则取文本
                title = self._safe_str(item.get('title', ''))
                if not title:
                    title = self._safe_str(item.get_text(strip=True))
                # 封面: data-original → data-src → src
                pic = item.get('data-original') or item.get('data-src') or item.get('src') or ''
                # 备注: .pic-text
                remarks = ''
                pic_text = item.select_one('.pic-text')
                if pic_text:
                    remarks = self._safe_str(pic_text.get_text(strip=True))
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': title,
                    'vod_pic': self._fix_url(pic),
                    'vod_remarks': remarks,
                    'type_name': '',
                })
        else:
            # Regex fallback (BeautifulSoup不可用时)
            pattern = (r'<a[^>]*class="stui-vodlist__thumb[^"]*"[^>]*'
                       r'href="(/detail/(\d+)\.html)"[^>]*?(?:title="([^"]*)")?[^>]*?'
                       r'(?:data-original="([^"]*)")?[^>]*>(.*?)</a>')
            for match in re.findall(pattern, html, re.DOTALL):
                href, vod_id, title, pic, inner = match
                if not title:
                    title = re.sub(r'<[^>]+>', '', inner).strip()
                if not pic:
                    pic_m = re.search(r'data-src="([^"]*)"', inner)
                    if not pic_m:
                        pic_m = re.search(r'src="([^"]*)"', inner)
                    if pic_m:
                        pic = pic_m.group(1)
                remarks = ''
                rm = re.search(r'<span class="pic-text[^"]*">([^<]*)</span>', inner)
                if rm:
                    remarks = rm.group(1).strip()
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': title.strip(),
                    'vod_pic': self._fix_url(pic),
                    'vod_remarks': remarks,
                    'type_name': '',
                })

        return videos

    # ========== 详情页解析 ==========

    def _parse_detail_html(self, html):
        """解析详情页HTML, 返回影片详情和播放源"""
        result = {}
        if not html:
            return result

        if BeautifulSoup is not None:
            result = self._parse_detail_bs4(html)
        else:
            result = self._parse_detail_regex(html)
        return result

    def _parse_detail_bs4(self, html):
        """使用BeautifulSoup解析详情页"""
        soup = BeautifulSoup(html, 'html.parser')
        result = {}

        # 标题: .vod-info h1.title
        title_el = soup.select_one('.vod-info h1.title')
        if not title_el:
            title_el = soup.select_one('h1.title')
        result['vod_name'] = self._safe_str(title_el.get_text(strip=True)) if title_el else ''

        # 封面: .vod-poster__wrap img 的 data-original/data-src/src
        pic = ''
        poster_img = soup.select_one('.vod-poster__wrap img')
        if poster_img:
            pic = (poster_img.get('data-original') or
                   poster_img.get('data-src') or
                   poster_img.get('src') or '')
        result['vod_pic'] = self._fix_url(pic)

        # 描述: .detail-content 优先, 回退 .detail-sketch
        desc = ''
        desc_el = soup.select_one('.detail-content')
        if not desc_el:
            desc_el = soup.select_one('.detail-sketch')
        if desc_el:
            desc = self._safe_str(desc_el.get_text(strip=True))
        result['vod_content'] = desc

        # meta解析: .vod-info .vod-meta .meta-item, 按文本前缀匹配
        actor = ''
        director = ''
        year = ''
        area = ''
        type_name = ''
        meta_items = soup.select('.vod-info .vod-meta .meta-item')
        for item in meta_items:
            text = item.get_text(separator=' ', strip=True)
            if '主演' in text:
                links = item.select('a')
                if links:
                    actor = ', '.join(a.get_text(strip=True) for a in links)
                else:
                    actor = re.sub(r'^.*?主演[：:]\s*', '', text)
            elif '导演' in text:
                links = item.select('a')
                if links:
                    director = ', '.join(a.get_text(strip=True) for a in links)
                else:
                    director = re.sub(r'^.*?导演[：:]\s*', '', text)
            elif '地区' in text:
                links = item.select('a')
                if links:
                    area = ', '.join(a.get_text(strip=True) for a in links)
                else:
                    area = re.sub(r'^.*?地区[：:]\s*', '', text)
            elif '类型' in text:
                links = item.select('a')
                if links:
                    type_name = ', '.join(a.get_text(strip=True) for a in links)
            else:
                # 尝试匹配年份 (19xx/20xx)
                year_match = re.search(r'((?:19|20)\d{2})', text)
                if year_match:
                    year = year_match.group(1)

        result['vod_actor'] = actor
        result['vod_director'] = director
        result['vod_year'] = year
        result['vod_area'] = area
        result['type_name'] = type_name

        # 播放线路: div.playlist-panel (排除 .netdisk-panel)
        play_from = []
        play_url = []
        panels = soup.select('div.playlist-panel')
        for panel in panels:
            # 排除网盘面板
            classes = panel.get('class', [])
            if 'netdisk-panel' in classes:
                continue
            # 线路名: .panel-head h3, 缺则为"LIBVIO"
            h3 = panel.select_one('.panel-head h3')
            line_name = self._safe_str(h3.get_text(strip=True)) if h3 else 'LIBVIO'
            # 集数链接: ul.stui-content__playlist a[href^="/w/"]
            ep_links = panel.select('ul.stui-content__playlist a[href^="/w/"]')
            if not ep_links:
                continue
            play_from.append(line_name)
            ep_urls = []
            for a in ep_links:
                href = a.get('href', '')
                ep_name = self._safe_str(a.get_text(strip=True))
                play_id = self._encode_play_id(href)
                ep_urls.append(f"{ep_name}${play_id}")
            play_url.append('#'.join(ep_urls))

        result['vod_play_from'] = '$$$'.join(play_from) if play_from else ''
        result['vod_play_url'] = '$$$'.join(play_url) if play_url else ''
        return result

    def _parse_detail_regex(self, html):
        """Regex fallback — BeautifulSoup不可用时解析详情页"""
        result = {}

        # 标题
        title = ''
        m = re.search(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h1>', html)
        if m:
            title = m.group(1).strip()
        result['vod_name'] = title

        # 封面
        pic = ''
        m = re.search(r'data-original="([^"]+)"', html)
        if m:
            pic = m.group(1)
        result['vod_pic'] = self._fix_url(pic)

        # 描述
        desc = ''
        m = re.search(r'<[^>]*class="[^"]*detail-content[^"]*"[^>]*>(.*?)</', html, re.DOTALL)
        if not m:
            m = re.search(r'<[^>]*class="[^"]*detail-sketch[^"]*"[^>]*>(.*?)</', html, re.DOTALL)
        if m:
            desc = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        result['vod_content'] = desc

        # 年份
        year = ''
        m = re.search(r'((?:19|20)\d{2})', html)
        if m:
            year = m.group(1)
        result['vod_year'] = year

        # 导演
        director = ''
        m = re.search(r'导演[：:]\s*</span>(.*?)</li>', html, re.DOTALL)
        if m:
            ds = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            director = ', '.join(ds) if ds else re.sub(r'<[^>]+>', '', m.group(1)).strip()
        result['vod_director'] = director

        # 演员
        actor = ''
        m = re.search(r'主演[：:]\s*</span>(.*?)</li>', html, re.DOTALL)
        if m:
            actors = re.findall(r'<a[^>]*>([^<]+)</a>', m.group(1))
            actor = ', '.join(actors) if actors else re.sub(r'<[^>]+>', '', m.group(1)).strip()
        result['vod_actor'] = actor

        result['vod_area'] = ''
        result['type_name'] = ''

        # 播放线路 (Regex fallback)
        play_from = []
        play_url = []
        panel_pattern = (r'<div[^>]*class="playlist-panel"[^>]*>.*?'
                         r'<h3>([^<]+)</h3>.*?'
                         r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>(.*?)</ul>')
        for line_name, playlist_html in re.findall(panel_pattern, html, re.DOTALL):
            episodes = re.findall(r'<a[^>]*href="(/w/[^"]+\.html)"[^>]*>([^<]+)</a>', playlist_html)
            if episodes:
                play_from.append(line_name.strip())
                ep_urls = []
                for href, ep_name in episodes:
                    play_id = self._encode_play_id(href)
                    ep_urls.append(f"{ep_name.strip()}${play_id}")
                play_url.append('#'.join(ep_urls))

        result['vod_play_from'] = '$$$'.join(play_from) if play_from else ''
        result['vod_play_url'] = '$$$'.join(play_url) if play_url else ''
        return result

    # ========== 播放ID编解码 ==========

    @staticmethod
    def _encode_play_id(path):
        """编码播放ID: libvio: + base64urlsafe(/w/{vod_id}-{line}-{ep}.html)
        base64urlsafe: 标准base64但 +→- /→_ 去尾=
        """
        encoded = base64.b64encode(path.encode('utf-8')).decode('utf-8')
        encoded = encoded.replace('+', '-').replace('/', '_').rstrip('=')
        return f"libvio:{encoded}"

    @staticmethod
    def _decode_play_id(play_id):
        """解码播放ID: 去掉libvio:前缀, -→+ _→/ 补= base64解码"""
        if play_id.startswith('libvio:'):
            encoded = play_id[7:]
        else:
            encoded = play_id
        encoded = encoded.replace('-', '+').replace('_', '/')
        padding = (4 - len(encoded) % 4) % 4
        encoded += '=' * padding
        return base64.b64decode(encoded).decode('utf-8')

    # ========== 播放解析 ==========

    def _libvio_play(self, play_id):
        """立播播放解析主函数
        播放ID格式: libvio:{base64urlsafe(/w/{vod_id}-{line}-{ep}.html)}
        解析流程: 解码 → 请求播放页 → 提取player_aaaa → 根据from类型路由
        """
        # 1. 解码play_id: 去掉"libvio:"前缀, -→+, _→/, 补=, base64解码得到 /w/xxx.html
        try:
            path = self._decode_play_id(play_id)
        except Exception:
            return {'parse': 1, 'playUrl': '', 'url': play_id, 'header': self.headers}

        # 2. 请求播放页
        play_url = self.siteUrl + path
        html = self._fetch_html(play_url)

        # 3. 提取 player_aaaa JSON
        player_match = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.DOTALL)
        if not player_match:
            # 备用正则
            player_match = re.search(r'player_aaaa\s*=\s*(\{[^<]+\})', html)
        if not player_match:
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

        try:
            player_data = json.loads(player_match.group(1))
        except (json.JSONDecodeError, ValueError):
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

        url = player_data.get('url', '').replace('\\/', '/')
        from_type = player_data.get('from', '').lower()
        vod_id = player_data.get('id', '')
        nid = player_data.get('nid', '1')
        url_next = player_data.get('url_next', '')

        # 4. 如果url本身是http直链, 直接返回
        if url.startswith('http'):
            return {'parse': 0, 'playUrl': '', 'url': url, 'header': self.headers}

        # 5. 根据from类型路由
        if from_type == 'yd189':
            return self._parse_yd189(url, vod_id, nid, play_url)
        elif from_type == 'ty_new1':
            return self._parse_ty_new1(url, url_next, vod_id, nid, play_url)
        else:
            # 不支持的线路, 让壳子解析
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

    def _parse_yd189(self, url, vod_id, nid, play_url):
        """HD5播放线路解析 — 请求 /vid/yd.php
        流程: yd.php → 提取parse_yd.php URL → parse_yd.php返回最终URL
        """
        ts = str(int(time.time() * 1000))
        api_url = (f"{self.siteUrl}/vid/yd.php?url={urllib.parse.quote(url)}"
                   f"&id={urllib.parse.quote(str(vod_id))}"
                   f"&nid={urllib.parse.quote(str(nid))}"
                   f"&_ts={ts}")
        headers = {**self.headers, 'Referer': play_url}
        resp = self._fetch_html(api_url, headers)

        # 从响应中提取 parse_yd.php 的URL
        # 正则: fetch('.../vid/parse_yd.php?...')
        parse_match = re.search(r"fetch\(['\"]([^'\"]*?/vid/parse_yd\.php\?[^'\"]+)['\"]", resp)
        if not parse_match:
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

        parse_url = parse_match.group(1).replace('\\/', '/').replace('&amp;', '&')
        if parse_url.startswith('/'):
            parse_url = self.siteUrl + parse_url

        # 请求 parse_yd.php 获取最终URL
        final_resp = self._fetch_html(parse_url, headers)
        try:
            data = json.loads(final_resp)
            final_url = data.get('url', '')
            if final_url:
                return {'parse': 0, 'playUrl': '', 'url': final_url, 'header': self.headers}
        except (json.JSONDecodeError, ValueError):
            pass

        return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

    def _parse_ty_new1(self, url, url_next, vod_id, nid, play_url):
        """BD播放线路解析 — 请求 /vid/ty4.php
        流程: ty4.php → 提取window.LIBVIO_CFG → POST parseUrl获取最终URL (最多重试6次)
        """
        ts = str(int(time.time() * 1000))
        api_url = (f"{self.siteUrl}/vid/ty4.php?url={urllib.parse.quote(url)}"
                   f"&next={urllib.parse.quote(str(url_next))}"
                   f"&id={urllib.parse.quote(str(vod_id))}"
                   f"&nid={urllib.parse.quote(str(nid))}"
                   f"&_ts={ts}")
        headers = {**self.headers, 'Referer': play_url}
        resp = self._fetch_html(api_url, headers)

        # 从响应中提取 window.LIBVIO_CFG = {...}
        cfg_match = re.search(r'window\.LIBVIO_CFG\s*=\s*(\{.*?\});', resp, re.DOTALL)
        if not cfg_match:
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

        try:
            cfg = json.loads(cfg_match.group(1))
        except (json.JSONDecodeError, ValueError):
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

        parse_url = cfg.get('parseUrl', '')
        raw_url = cfg.get('rawUrl', url)

        if not parse_url:
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

        if parse_url.startswith('/'):
            parse_url = self.siteUrl + parse_url

        # POST JSON 请求, 最多重试6次
        post_headers = {
            'User-Agent': UA,
            'Referer': api_url,
            'Origin': self.siteUrl,
            'Accept': '*/*',
            'Content-Type': 'application/json; charset=utf-8'
        }

        for i in range(6):
            try:
                try:
                    r = self.post(parse_url, data=json.dumps({'url': raw_url}),
                                  headers=post_headers, timeout=20, verify=False)
                except TypeError:
                    r = self.post(parse_url, data=json.dumps({'url': raw_url}),
                                  headers=post_headers, timeout=20)
                r.encoding = 'utf-8'
                try:
                    data = json.loads(r.text)
                except (json.JSONDecodeError, ValueError):
                    data = {}

                final_url = data.get('url', '')
                if final_url:
                    return {'parse': 0, 'playUrl': '', 'url': final_url,
                            'header': {'User-Agent': UA}}

                # fatal表示永久失败, 不再重试
                if data.get('fatal'):
                    break

                if i < 5:
                    time.sleep(1.2)
            except Exception:
                if i < 5:
                    time.sleep(1.2)

        return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': self.headers}

    # ========== 核心接口 ==========

    def homeContent(self, filter):
        """首页内容 — 返回分类和推荐"""
        result = {}
        result['class'] = CLASSES
        if filter:
            result['filters'] = FILTERS

        html = self._fetch_html(self.siteUrl)
        videos = self._parse_list_html(html)
        result['list'] = videos[:12]
        return result

    def homeVideoContent(self):
        """首页视频推荐"""
        html = self._fetch_html(self.siteUrl)
        videos = self._parse_list_html(html)
        return {'list': videos[:12]}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容 — 返回指定分类的视频列表
        URL格式: /show/{id}-{area}-{by}-{class}-{lang}-{letter}---{page}---{year}.html
        page是1-indexed (不是page-1!)
        空过滤器为空字符串
        """
        result = {}
        page = self._safe_page(pg, 1)

        # 解析筛选参数
        area = ''
        by = ''
        cls = ''
        lang = ''
        letter = ''
        year = ''
        if extend:
            # 兼容extend为JSON字符串的情况
            if isinstance(extend, str):
                try:
                    extend = json.loads(extend)
                except (json.JSONDecodeError, ValueError):
                    extend = {}
            if isinstance(extend, dict):
                area = self._safe_str(extend.get('地区', ''))
                by = self._safe_str(extend.get('排序', ''))
                lang = self._safe_str(extend.get('语言', ''))
                year = self._safe_str(extend.get('年份', ''))
                cls = self._safe_str(extend.get('class', ''))
                letter = self._safe_str(extend.get('letter', ''))

        # 构建分类URL (page是1-indexed, 空过滤器为空字符串)
        url = (f"{self.siteUrl}/show/{tid}-{area}-{by}-{cls}-{lang}-{letter}"
               f"---{page}---{year}.html")
        html = self._fetch_html(url)
        videos = self._parse_list_html(html)

        # 判断是否有下一页
        pagecount = page
        next_page = page + 1
        has_next = f'---{next_page}---' in html
        if has_next:
            pagecount = page + 1
        elif len(videos) >= PAGE_SIZE:
            pagecount = page + 1

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = pagecount
        result['limit'] = PAGE_SIZE
        result['total'] = pagecount * PAGE_SIZE
        return result

    def detailContent(self, array):
        """详情内容 — 返回影片详情和播放源
        URL: {siteUrl}/detail/{id}.html
        """
        vod_id = array[0] if array else ''
        if not vod_id:
            return {'list': []}

        url = f"{self.siteUrl}/detail/{vod_id}.html"
        html = self._fetch_html(url)
        result = self._parse_detail_html(html)
        result['vod_id'] = vod_id
        return {'list': [result]}

    def playerContent(self, flag, id, vipFlags):
        """播放内容 — 返回播放URL
        播放ID格式: libvio:{base64urlsafe(/w/{vod_id}-{line}-{ep}.html)}
        """
        # 1. 如果id以"libvio:"开头, 走立播解析
        if id.startswith("libvio:"):
            return self._libvio_play(id)
        # 2. 如果id是http直链, 直接返回
        if id.startswith("http"):
            return {'parse': 0, 'playUrl': '', 'url': id, 'header': self.headers}
        # 3. 其他情况让壳子解析
        return {'parse': 1, 'playUrl': '', 'url': id, 'header': self.headers}

    def searchContent(self, key, quick):
        """搜索内容
        URL: {siteUrl}/search/-------------.html?wd={wd}
        参数名是 wd= (不是 searchword=!)
        用 _parse_list_html 解析结果
        """
        result = {}
        wd = urllib.parse.quote(key)
        url = f"{self.siteUrl}/search/-------------.html?wd={wd}"
        html = self._fetch_html(url)
        videos = self._parse_list_html(html)
        result['list'] = videos
        return result

    def searchContentPage(self, key, quick, pg):
        """搜索内容(分页) — 当前仅支持第1页"""
        return self.searchContent(key, quick)

    def localProxy(self, param):
        """本地代理"""
        return [200, "video/MP2T", "", ""]
