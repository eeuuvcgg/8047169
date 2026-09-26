# -*- coding: utf-8 -*-
"""
木偶|4K (http://123.666291.xyz) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: http://123.666291.xyz
CMS类型: 苹果CMS(MacCMS)
特点: 网盘资源聚合站, 与玩偶(wogg)同构
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
SITE_URL = "http://123.666291.xyz"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
PAGE_SIZE = 72

# 首页分类
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "剧集"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "25", "type_name": "天翼专区"},
    {"type_id": "27", "type_name": "短剧"},
    {"type_id": "4", "type_name": "纪录片"},
]


# ==================== 筛选器构建 ====================

def _build_year_opts():
    """构建年份筛选选项"""
    opts = [{"n": "全部", "v": ""}]
    for y in range(2026, 2009, -1):
        opts.append({"n": str(y), "v": str(y)})
    return opts


def _build_letter_opts():
    """构建字母筛选选项"""
    opts = [{"n": "全部", "v": ""}, {"n": "0-9", "v": "0"}]
    for c in range(ord('A'), ord('Z') + 1):
        opts.append({"n": chr(c), "v": chr(c)})
    return opts


# 地区筛选选项
_AREA_OPTS = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"},
    {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"},
    {"n": "美国", "v": "美国"},
    {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"},
    {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"},
    {"n": "德国", "v": "德国"},
    {"n": "泰国", "v": "泰国"},
    {"n": "印度", "v": "印度"},
    {"n": "加拿大", "v": "加拿大"},
    {"n": "西班牙", "v": "西班牙"},
    {"n": "俄罗斯", "v": "俄罗斯"},
    {"n": "其他", "v": "其他"},
]

# 排序筛选选项
_BY_OPTS = [
    {"n": "时间", "v": "time"},
    {"n": "人气", "v": "hits"},
    {"n": "评分", "v": "score"},
]


def _build_filters():
    """为每个分类构建筛选器(地区/年份/字母/排序)"""
    filters = {}
    for cls in CLASSES:
        filters[cls["type_id"]] = {
            "地区": [dict(o) for o in _AREA_OPTS],
            "年份": _build_year_opts(),
            "字母": _build_letter_opts(),
            "排序": [dict(o) for o in _BY_OPTS],
        }
    return filters


FILTERS = _build_filters()


class Spider(Spider):
    """木偶|4K Spider — 苹果CMS网盘资源聚合站(与玩偶同构)"""

    def getName(self):
        return "木偶|4K"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.siteUrl = SITE_URL

        # 支持从extend解析站点URL和代理配置
        self.proxy = None
        if self.extend:
            if self.extend.startswith('http://') or self.extend.startswith('https://'):
                # 以http开头的extend视为站点URL
                self.siteUrl = self.extend.rstrip('/')
            elif self.extend.startswith('socks'):
                self.proxy = self.extend
            elif self.extend.startswith('proxy='):
                self.proxy = self.extend.split('=', 1)[1]

        self.headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': self.siteUrl + '/',
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

    def _fix_url(self, url):
        """修复URL — 补全协议和域名"""
        if not url:
            return ''
        url = str(url).strip()
        if url.startswith('//'):
            return 'http:' + url
        if url.startswith('http'):
            return url
        if url.startswith('/'):
            return self.siteUrl + url
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
                if hasattr(rsp, 'status_code') and rsp.status_code == 404:
                    return ''
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

    def _build_category_url(self, tid, page, extend):
        """构建分类页URL — 路径格式(与玩偶不同)

        无筛选时: {siteUrl}/index.php/vod/show/id/{cateId}/page/{page}.html
        有筛选时: {siteUrl}/index.php/vod/show{/area/x}{/by/x}{/class/x}{/lang/x}/id/{cateId}{/letter/x}/page/{page}{/year/x}.html
        by默认"time"
        """
        extend = extend or {}
        # 提取筛选值 — 键名与FILTERS中的键名一致
        area = self._safe_str(extend.get('地区'))
        by_val = self._safe_str(extend.get('排序'))
        cls = self._safe_str(extend.get('类型'))
        lang = self._safe_str(extend.get('语言'))
        letter = self._safe_str(extend.get('字母'))
        year = self._safe_str(extend.get('年份'))

        # 判断是否有任何筛选
        has_filter = any([area, by_val, cls, lang, letter, year])

        if not has_filter:
            # 无筛选 — 简单URL
            return f"{self.siteUrl}/index.php/vod/show/id/{tid}/page/{page}.html"

        # 有筛选 — 按格式拼接, by默认"time"
        if not by_val:
            by_val = "time"

        url = f"{self.siteUrl}/index.php/vod/show"
        if area:
            url += f"/area/{area}"
        if by_val:
            url += f"/by/{by_val}"
        if cls:
            url += f"/class/{cls}"
        if lang:
            url += f"/lang/{lang}"
        url += f"/id/{tid}"
        if letter:
            url += f"/letter/{letter}"
        url += f"/page/{page}"
        if year:
            url += f"/year/{year}"
        url += ".html"
        return url

    # ========== 列表页解析 ==========

    def _extract_link_info(self, container):
        """从容器元素中提取链接(href)和标题文本

        container可能是<a>标签本身, 也可能是包含<a>的容器
        """
        if container is None:
            return '', ''
        # 如果容器本身是<a>标签, 直接使用
        if container.name == 'a':
            href = container.get('href', '')
            title = container.get_text(strip=True) or container.get('title', '')
            return href, title
        # 在容器内查找<a>标签
        a = container.find('a')
        if a:
            href = a.get('href', '')
            title = a.get_text(strip=True) or a.get('title', '') or container.get_text(strip=True)
            return href, title
        # 没有<a>标签, 仅提取文本
        return '', container.get_text(strip=True)

    def _parse_items(self, items, title_selectors):
        """通用列表项解析 — 用BeautifulSoup解析

        items: BeautifulSoup元素列表
        title_selectors: 标题链接选择器优先级列表
        """
        videos = []
        for item in items:
            # 标题链接 — 按优先级依次尝试
            # 优先级高的选择器提供标题, 若无链接则继续回退到下一个选择器获取链接
            vod_id = ''
            vod_name = ''
            for sel in title_selectors:
                title_el = item.select_one(sel)
                if title_el:
                    href, title = self._extract_link_info(title_el)
                    if not vod_name and title:
                        vod_name = title
                    if not vod_id and href:
                        vod_id = href
                    if vod_id and vod_name:
                        break

            # 封面图 — data-src优先, src回退
            pic = ''
            img = item.select_one('.module-item-pic img')
            if img:
                pic = img.get('data-src') or img.get('src') or ''

            # 备注 — .module-item-text 或 .video-tag-icon
            remarks = ''
            rem_el = item.select_one('.module-item-text')
            if rem_el:
                remarks = rem_el.get_text(strip=True)
            else:
                rem_el = item.select_one('.video-tag-icon')
                if rem_el:
                    remarks = rem_el.get_text(strip=True)

            if vod_name:
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': vod_name,
                    'vod_pic': self._fix_url(pic),
                    'vod_remarks': remarks,
                })
        return videos

    def _parse_list_html(self, html):
        """解析列表页HTML — 用BeautifulSoup, 返回视频列表

        选择器: .module-item
        标题链接: .module-item-title 优先, 回退 .video-name a, .module-item-pic a
        封面图: .module-item-pic img 的 data-src 优先, src 回退
        备注: .module-item-text 或 .video-tag-icon
        """
        videos = []
        if not html:
            return videos

        if BeautifulSoup:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('.module-item')
            videos = self._parse_items(
                items,
                ['.module-item-title', '.video-name a', '.module-item-pic a']
            )
        else:
            # 正则回退
            videos = self._parse_list_regex(html)

        return videos

    def _parse_list_regex(self, html):
        """正则回退解析列表页 — BeautifulSoup不可用时使用"""
        videos = []
        if not html:
            return videos

        # 匹配 module-item-pic 中的链接和图片
        pic_pattern = (
            r'module-item-pic[^>]*>.*?'
            r'<a[^>]*href="([^"]*)"[^>]*?(?:\s*title="([^"]*)")?[^>]*>.*?'
            r'<img[^>]*?(?:data-src="([^"]*)")?[^>]*?(?:src="([^"]*)")?'
        )
        pic_matches = re.findall(pic_pattern, html, re.DOTALL)

        # 匹配所有备注文本
        remarks_list = re.findall(r'module-item-text[^>]*>([^<]*)</div>', html)

        # 匹配所有标题文本(module-item-title内)
        title_list = re.findall(
            r'module-item-title[^>]*>(?:<a[^>]*>)?([^<]+)', html
        )

        for i, m in enumerate(pic_matches):
            href, title_attr, data_src, src = m
            if not href:
                continue
            pic = data_src or src or ''
            title = (title_attr or '').strip()
            if not title and i < len(title_list):
                title = title_list[i].strip()
            if not title:
                title = '未知'
            remarks = remarks_list[i].strip() if i < len(remarks_list) else ''
            videos.append({
                'vod_id': href,
                'vod_name': title,
                'vod_pic': self._fix_url(pic),
                'vod_remarks': remarks,
            })
        return videos

    def _extract_total_and_pages(self, html):
        """从列表页HTML中提取总数和最大页码

        总数: 正则匹配 $("​.mac_total").text('(\\d+)');
        最大页码: 正则匹配所有 /page/(\\d+) 取最大值
        返回: (total, pagecount)
        """
        total = 0
        pagecount = 1

        if not html:
            return total, pagecount

        # 提取总数
        total_match = re.search(r'\$\("\.mac_total"\)\.text\(\'(\d+)\'\);', html)
        if total_match:
            total = int(total_match.group(1))

        # 提取最大页码
        page_numbers = re.findall(r'/page/(\d+)', html)
        if page_numbers:
            pagecount = max(int(p) for p in page_numbers)

        return total, pagecount

    # ========== 详情页解析 ==========

    def _parse_detail_html(self, html):
        """解析详情页HTML — 用BeautifulSoup, 返回影片详情和播放源

        标题: .video-info-header > .page-title → 回退 .page-title
        封面: .module-item-pic img 的 data-src/src
        地区: .video-info-header a.tag-link 最后一个
        类型: .video-info-header div.tag-link a 拼接
        导演/主演/年代/备注/剧情: 遍历 .video-info-item, 按前导标签文本匹配
        网盘分享链接: .module-row-text 的 data-clipboard-text, .module-row-info p 文本提取 http(s):// 链接
        注意: 木偶默认 reverseShareLinks=true, 分享链接倒序排列
        播放线路: vod_play_from="网盘分享", vod_play_url格式为 标题$URL
        """
        result = {}
        if not html:
            return result

        if BeautifulSoup:
            result = self._parse_detail_bs(html)
        else:
            # 正则回退
            result = self._parse_detail_regex(html)

        return result

    def _parse_detail_bs(self, html):
        """用BeautifulSoup解析详情页"""
        result = {}
        soup = BeautifulSoup(html, 'html.parser')

        # ===== 标题 =====
        title = ''
        title_el = soup.select_one('.video-info-header > .page-title')
        if not title_el:
            title_el = soup.select_one('.page-title')
        if title_el:
            title = title_el.get_text(strip=True)
        result['vod_name'] = title

        # ===== 封面 =====
        pic = ''
        img = soup.select_one('.module-item-pic img')
        if img:
            pic = img.get('data-src') or img.get('src') or ''
        result['vod_pic'] = self._fix_url(pic)

        # ===== 地区 =====
        area = ''
        area_links = soup.select('.video-info-header a.tag-link')
        if area_links:
            area = area_links[-1].get_text(strip=True)
        result['vod_area'] = area

        # ===== 类型 =====
        type_name = ''
        type_links = soup.select('.video-info-header div.tag-link a')
        if type_links:
            type_names = [a.get_text(strip=True) for a in type_links if a.get_text(strip=True)]
            type_name = ' / '.join(type_names)
        result['type_name'] = type_name

        # ===== 导演/主演/年代/备注/剧情 =====
        # 遍历 .video-info-item, 按前导标签文本匹配
        label_map = [
            ('导演', 'vod_director'),
            ('主演', 'vod_actor'),
            ('年代', 'vod_year'),
            ('年份', 'vod_year'),
            ('备注', 'vod_remarks'),
            ('剧情', 'vod_content'),
            ('简介', 'vod_content'),
            ('介绍', 'vod_content'),
        ]
        for item in soup.select('.video-info-item'):
            text = item.get_text(strip=True)
            for label, field in label_map:
                if text.startswith(label):
                    # 去掉标签和冒号
                    value = text[len(label):].lstrip('：: \t\n')
                    # 导演/主演: 优先提取链接文本
                    if field in ('vod_director', 'vod_actor'):
                        links = item.find_all('a')
                        if links:
                            link_texts = [a.get_text(strip=True) for a in links if a.get_text(strip=True)]
                            if link_texts:
                                value = ', '.join(link_texts)
                    # 剧情字段: 仅在未设置时赋值(避免被"简介"覆盖"剧情")
                    if field == 'vod_content':
                        if not result.get(field):
                            result[field] = value
                    else:
                        result[field] = value
                    break

        # ===== 网盘分享链接 =====
        share_links = self._extract_share_links(soup)

        # 木偶默认 reverseShareLinks=true — 分享链接倒序排列
        share_links.reverse()

        # 构建播放线路 — 把网盘分享链接作为播放线路
        if share_links:
            result['vod_play_from'] = '网盘分享'
            result['vod_play_url'] = '#'.join(
                [f"{t}${u}" for t, u in share_links]
            )
        else:
            result['vod_play_from'] = ''
            result['vod_play_url'] = ''

        return result

    def _extract_share_links(self, soup):
        """从详情页提取网盘分享链接

        来源1: .module-row-text 的 data-clipboard-text 属性
        来源2: .module-row-info p 文本中的 http(s):// 链接
        返回: [(标题, URL), ...] 按页面顺序
        """
        share_links = []
        collected_urls = set()

        # 来源1: .module-row-text 的 data-clipboard-text
        for row_text in soup.select('.module-row-text'):
            url = (row_text.get('data-clipboard-text') or '').strip()
            title = row_text.get_text(strip=True)
            # 如果 data-clipboard-text 不是直接URL, 尝试从中提取
            if url and not url.startswith('http'):
                m = re.search(r'https?://[^\s"\'<>]+', url)
                if m:
                    url = m.group(0)
            if url and url not in collected_urls:
                collected_urls.add(url)
                if not title or title == url:
                    title = '网盘资源'
                share_links.append((title, url))

        # 来源2: .module-row-info p 文本中的链接
        for info in soup.select('.module-row-info'):
            for p in info.find_all('p'):
                text = p.get_text()
                urls = re.findall(r'https?://[^\s"\'<>]+', text)
                for u in urls:
                    if u not in collected_urls:
                        collected_urls.add(u)
                        # 标题取链接外的文本
                        title = text.replace(u, '').strip().rstrip('：:').strip()
                        if not title:
                            title = '网盘资源'
                        share_links.append((title, u))

        return share_links

    def _parse_detail_regex(self, html):
        """正则回退解析详情页 — BeautifulSoup不可用时使用"""
        result = {}

        # 标题
        title = ''
        title_match = re.search(r'<[^>]*class="[^"]*page-title[^"]*"[^>]*>([^<]+)<', html)
        if title_match:
            title = title_match.group(1).strip()
        result['vod_name'] = title

        # 封面
        pic = ''
        pic_match = re.search(r'module-item-pic.*?<img[^>]*?(?:data-src="([^"]*)")?(?:[^>]*?src="([^"]*)")?', html, re.DOTALL)
        if pic_match:
            pic = pic_match.group(1) or pic_match.group(2) or ''
        result['vod_pic'] = self._fix_url(pic)

        # 地区
        area = ''
        area_matches = re.findall(r'class="[^"]*tag-link[^"]*"[^>]*>([^<]+)<', html)
        if area_matches:
            area = area_matches[-1].strip()
        result['vod_area'] = area

        # 类型
        type_links = re.findall(r'<div[^>]*class="[^"]*tag-link[^"]*"[^>]*>\s*<a[^>]*>([^<]+)</a>', html)
        if type_links:
            result['type_name'] = ' / '.join(t.strip() for t in type_links)
        else:
            result['type_name'] = ''

        # 导演/主演/年代/备注/剧情 — 正则匹配
        for label, field in [
            ('导演', 'vod_director'), ('主演', 'vod_actor'),
            ('年代', 'vod_year'), ('年份', 'vod_year'),
            ('备注', 'vod_remarks'),
            ('剧情', 'vod_content'), ('简介', 'vod_content'),
        ]:
            m = re.search(r'%s[：:]\s*(.*?)(?:<|(?:导演|主演|年代|年份|备注|剧情|简介|介绍)[：:])' % label, html, re.DOTALL)
            if m:
                value = re.sub(r'<[^>]+>', '', m.group(1)).strip()
                if value and not result.get(field):
                    result[field] = value

        # 网盘分享链接
        share_links = []
        collected_urls = set()

        # data-clipboard-text
        for m in re.finditer(r'data-clipboard-text="([^"]*)"', html):
            url = m.group(1).strip()
            if url and not url.startswith('http'):
                um = re.search(r'https?://[^\s"\'<>]+', url)
                if um:
                    url = um.group(0)
            if url and url not in collected_urls:
                collected_urls.add(url)
                share_links.append(('网盘资源', url))

        # module-row-info p 中的链接
        for m in re.finditer(r'module-row-info.*?<p[^>]*>(.*?)</p>', html, re.DOTALL):
            text = re.sub(r'<[^>]+>', '', m.group(1))
            urls = re.findall(r'https?://[^\s"\'<>]+', text)
            for u in urls:
                if u not in collected_urls:
                    collected_urls.add(u)
                    share_links.append(('网盘资源', u))

        # 倒序
        share_links.reverse()

        if share_links:
            result['vod_play_from'] = '网盘分享'
            result['vod_play_url'] = '#'.join([f"{t}${u}" for t, u in share_links])
        else:
            result['vod_play_from'] = ''
            result['vod_play_url'] = ''

        return result

    # ========== 搜索页解析 ==========

    def _parse_search_html(self, html):
        """解析搜索页HTML — 用BeautifulSoup

        选择器: .module-search-item, 若无则回退到 .module-item
        标题链接: .video-serial 优先, 回退 .module-item-title, .video-name a
        """
        videos = []
        if not html:
            return videos

        if BeautifulSoup:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('.module-search-item')
            if not items:
                items = soup.select('.module-item')
            videos = self._parse_items(
                items,
                ['.video-serial', '.module-item-title', '.video-name a', '.module-item-pic a']
            )
        else:
            # 正则回退 — 复用列表正则解析
            videos = self._parse_list_regex(html)

        return videos

    # ========== 核心接口 ==========

    def homeContent(self, filter):
        """首页内容 — 返回分类和推荐"""
        result = {}
        result['class'] = list(CLASSES)
        if filter:
            result['filters'] = FILTERS

        # 获取首页推荐视频
        try:
            html = self._fetch_html(self.siteUrl)
            videos = self._parse_list_html(html)
            result['list'] = videos[:PAGE_SIZE]
        except Exception:
            result['list'] = []
        return result

    def homeVideoContent(self):
        """首页视频推荐"""
        try:
            html = self._fetch_html(self.siteUrl)
            videos = self._parse_list_html(html)
            return {'list': videos[:PAGE_SIZE]}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容 — 返回指定分类的视频列表"""
        result = {}
        tid = self._safe_str(tid, '1')
        page = self._safe_page(pg, 1)
        extend = extend or {}

        try:
            # 构建分类页URL(路径格式)
            url = self._build_category_url(tid, page, extend)
            html = self._fetch_html(url)
            videos = self._parse_list_html(html)

            # 提取总数和最大页码
            total, pagecount = self._extract_total_and_pages(html)
            if pagecount < page:
                pagecount = page

            result['list'] = videos
            result['page'] = page
            result['pagecount'] = pagecount if pagecount > 0 else page
            result['limit'] = PAGE_SIZE
            result['total'] = total if total > 0 else pagecount * PAGE_SIZE
        except Exception:
            result['list'] = []
            result['page'] = page
            result['pagecount'] = page
            result['limit'] = PAGE_SIZE
            result['total'] = 0
        return result

    def detailContent(self, array):
        """详情内容 — 返回影片详情和播放源

        id若以http开头直接用, 否则 {siteUrl}{id} 或 {siteUrl}/index.php/vod/detail/id/{id}.html
        """
        vod_id = array[0] if array else ''
        if not vod_id:
            return {'list': []}

        vod_id = str(vod_id).strip()

        try:
            # 构建详情页URL
            if vod_id.startswith('http'):
                url = vod_id
            elif vod_id.startswith('/'):
                url = self.siteUrl + vod_id
            elif vod_id.isdigit():
                url = f"{self.siteUrl}/index.php/vod/detail/id/{vod_id}.html"
            else:
                url = f"{self.siteUrl}/{vod_id}"

            html = self._fetch_html(url)
            result = self._parse_detail_html(html)
            result['vod_id'] = vod_id
            return {'list': [result]}
        except Exception:
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        """播放内容 — 返回播放URL

        如果播放ID是 http(s):// 直链, 直接返回 {parse:0, url:id}
        否则返回 {parse:1, url:id}
        """
        if str(id).startswith('http'):
            return {
                'parse': 0,
                'url': id,
                'header': self.headers,
            }
        return {
            'parse': 1,
            'url': id,
            'header': self.headers,
        }

    def searchContent(self, key, quick, pg="1"):
        """搜索内容 — 依次尝试3种URL

        URL1: {siteUrl}/index.php/vod/search/page/{page}/wd/{wd}.html
        URL2: {siteUrl}/index.php/vodsearch/{wd}----------{page}---.html
        URL3: {siteUrl}/index.php/vod/search/wd/{wd}.html
        """
        page = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

        encoded = urllib.parse.quote(keyword)

        # 依次尝试3种搜索URL
        urls = [
            f"{self.siteUrl}/index.php/vod/search/page/{page}/wd/{encoded}.html",
            f"{self.siteUrl}/index.php/vodsearch/{encoded}----------{page}---.html",
            f"{self.siteUrl}/index.php/vod/search/wd/{encoded}.html",
        ]

        for url in urls:
            try:
                html = self._fetch_html(url)
                if not html:
                    continue
                videos = self._parse_search_html(html)
                if videos:
                    return {
                        'list': videos,
                        'page': str(page),
                        'pagecount': page + 1 if len(videos) >= PAGE_SIZE else page,
                        'limit': PAGE_SIZE,
                        'total': len(videos),
                    }
            except Exception:
                continue

        return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': PAGE_SIZE, 'total': 0}

    def searchContentPage(self, key, quick, pg):
        """搜索内容(分页)"""
        return self.searchContent(key, quick, pg)

    def localProxy(self, param):
        """本地代理"""
        return [200, "video/MP2T", "", ""]


# ==================== 本地测试 ====================
if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()

    spider = Spider()
    spider.init()

    print("=== 站点: %s ===" % spider.getName())
    print("站点URL: %s" % spider.siteUrl)
    print()

    # 测试首页
    print("=== 首页 ===")
    home = spider.homeContent(True)
    print("分类:", [c["type_name"] for c in home["class"]])
    print("筛选器分类:", list(home.get("filters", {}).keys()))
    print("首页推荐数:", len(home.get("list", [])))
    for v in home.get("list", [])[:5]:
        print("  - %s | %s | %s" % (v.get("vod_name", ""), v.get("vod_remarks", ""), v.get("vod_pic", "")[:60]))

    # 测试首页推荐
    print("\n=== 首页推荐 ===")
    homeVid = spider.homeVideoContent()
    print("推荐视频数:", len(homeVid["list"]))

    # 测试分类
    print("\n=== 分类(电影) ===")
    cat = spider.categoryContent("1", "1", True, {})
    print("视频数: %s, 页数: %s/%s, 总数: %s" % (
        len(cat["list"]), cat.get("page"), cat.get("pagecount"), cat.get("total")))
    for v in cat["list"][:5]:
        print("  - %s | %s | id=%s" % (v["vod_name"], v.get("vod_remarks", ""), v.get("vod_id", "")[:50]))

    # 测试分类(带筛选)
    print("\n=== 分类(电影 + 地区筛选:美国) ===")
    cat2 = spider.categoryContent("1", "1", True, {"地区": "美国"})
    print("视频数:", len(cat2["list"]))
    for v in cat2["list"][:3]:
        print("  - %s | %s" % (v["vod_name"], v.get("vod_remarks", "")))

    # 测试搜索
    print("\n=== 搜索(测试) ===")
    search = spider.searchContent("测试", False)
    print("结果数:", len(search["list"]))
    for v in search["list"][:5]:
        print("  - %s | id=%s" % (v["vod_name"], v.get("vod_id", "")[:50]))

    # 测试详情
    if cat["list"]:
        test_item = cat["list"][0]
        print("\n=== 详情(%s) ===" % test_item["vod_name"])
        detail = spider.detailContent([test_item["vod_id"]])
        if detail["list"]:
            vod = detail["list"][0]
            print("标题:", vod.get("vod_name", ""))
            print("封面:", vod.get("vod_pic", "")[:80])
            print("类型:", vod.get("type_name", ""))
            print("地区:", vod.get("vod_area", ""))
            print("年份:", vod.get("vod_year", ""))
            print("导演:", vod.get("vod_director", ""))
            print("主演:", vod.get("vod_actor", "")[:80])
            print("备注:", vod.get("vod_remarks", ""))
            print("剧情:", (vod.get("vod_content", "") or "")[:80])
            print("播放线路:", vod.get("vod_play_from", ""))
            play_url = vod.get("vod_play_url", "")
            episodes = play_url.split("#") if play_url else []
            print("选集数:", len(episodes))
            for ep in episodes[:5]:
                print("  - %s" % ep[:80])
            if len(episodes) > 5:
                print("  ... (共%s集)" % len(episodes))

            # 测试播放
            if episodes:
                first_ep = episodes[0]
                if "$" in first_ep:
                    ep_name, ep_id = first_ep.split("$", 1)
                    print("\n=== 播放解析 ===")
                    print("选集:", ep_name)
                    play = spider.playerContent("", ep_id, [])
                    print("parse:", play.get("parse"))
                    print("url:", play.get("url", "")[:80])
