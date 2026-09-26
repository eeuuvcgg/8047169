# -*- coding: utf-8 -*-
"""
立播|4K (libvio) — 兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4) 双壳子
站点: https://www.libvio.pw
API: HTML采集 + 自定义播放解析(yd189/ty_new1)
版本: 1.0.0
来源: 从 CatVod index.js (esbuild打包) 反编译转换
"""
import sys
import json
import re
import time
import base64
from urllib.parse import quote, urlencode, urljoin

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
    from pyquery import PyQuery as pq
    HAS_PQ = True
except ImportError:
    HAS_PQ = False


# ==================== 常量（从JS源码提取） ====================
DOMAIN_LIST = [
    "https://www.libvio.pw",
    "https://www.libvio.com",
    "https://www.libvio.net",
    "https://www.libvio.cc",
]
PLAY_FLAG = "libvio:"
PAGE_SIZE = 20
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)

# 正则
RE_ID = re.compile(r'(\d+)')
RE_PLAYER = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', re.S)
RE_FETCH = re.compile(r"""fetch\(['"]([^'"]*?/vid/parse_yd\.php\?[^'"]+)['"]\)""", re.S)
RE_CFG = re.compile(r'window\.LIBVIO_CFG\s*=\s*(\{.*?\});', re.S)

# 地区匹配正则
RE_AREA = re.compile(
    r'(大陆|港|台|美|英|法|德|日|韩|泰|印|俄|加|澳|意|西|瑞|荷|巴|越|马|菲|新|瑞典|挪威|丹麦|芬兰|比利时|波兰|土耳其|埃及|墨西哥|阿根廷|智利|哥伦比亚)'
)

# 首页分类
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "剧集"},
    {"type_id": "4", "type_name": "番剧"},
    {"type_id": "15", "type_name": "日韩"},
    {"type_id": "16", "type_name": "欧美"},
]

# 筛选器 — 每个分类同结构
_YEAR_VALUES = [{"n": "全部", "v": ""}]
for _y in range(2026, 2014, -1):
    _YEAR_VALUES.append({"n": str(_y), "v": str(_y)})

_AREA_VALUES_1 = [
    {"n": "全部", "v": ""},
    {"n": "中国大陆", "v": "中国大陆"},
    {"n": "中国香港", "v": "中国香港"},
    {"n": "中国台湾", "v": "中国台湾"},
    {"n": "美国", "v": "美国"},
    {"n": "法国", "v": "法国"},
    {"n": "英国", "v": "英国"},
    {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"},
    {"n": "德国", "v": "德国"},
    {"n": "泰国", "v": "泰国"},
    {"n": "印度", "v": "印度"},
    {"n": "意大利", "v": "意大利"},
    {"n": "西班牙", "v": "西班牙"},
    {"n": "加拿大", "v": "加拿大"},
    {"n": "其他", "v": "其他"},
]

_AREA_VALUES_15 = [
    {"n": "全部", "v": ""},
    {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"},
    {"n": "泰国", "v": "泰国"},
    {"n": "其他", "v": "其他"},
]

_AREA_VALUES_16 = [
    {"n": "全部", "v": ""},
    {"n": "美国", "v": "美国"},
    {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"},
    {"n": "德国", "v": "德国"},
    {"n": "加拿大", "v": "加拿大"},
    {"n": "意大利", "v": "意大利"},
    {"n": "西班牙", "v": "西班牙"},
    {"n": "其他", "v": "其他"},
]

_LANG_VALUES_1 = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"},
    {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"},
    {"n": "闽南语", "v": "闽南语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "日语", "v": "日语"},
    {"n": "法语", "v": "法语"},
    {"n": "德语", "v": "德语"},
    {"n": "其它", "v": "其它"},
]

_LANG_VALUES_2 = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"},
    {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"},
    {"n": "闽南语", "v": "闽南语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "日语", "v": "日语"},
    {"n": "其它", "v": "其它"},
]

_LANG_VALUES_4 = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"},
    {"n": "日语", "v": "日语"},
    {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"},
    {"n": "闽南语", "v": "闽南语"},
    {"n": "韩语", "v": "韩语"},
    {"n": "其它", "v": "其它"},
]

_SORT_VALUES = [
    {"n": "默认", "v": ""},
    {"n": "时间", "v": "time"},
    {"n": "人气", "v": "hits"},
    {"n": "评分", "v": "score"},
]

_CLASS_VALUES_2 = [
    {"n": "全部", "v": ""},
    {"n": "国产剧", "v": "国产剧"},
    {"n": "海外剧", "v": "海外剧"},
]

_CLASS_VALUES_4 = [
    {"n": "全部", "v": ""},
    {"n": "番剧", "v": "番剧"},
    {"n": "国创", "v": "国创"},
]

FILTERS_TEMPLATE = {
    "1": [
        {"key": "area", "name": "地区", "value": _AREA_VALUES_1},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "lang", "name": "语言", "value": _LANG_VALUES_1},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "2": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_2},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_1},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "lang", "name": "语言", "value": _LANG_VALUES_2},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "4": [
        {"key": "class", "name": "类型", "value": _CLASS_VALUES_4},
        {"key": "area", "name": "地区", "value": _AREA_VALUES_15},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "lang", "name": "语言", "value": _LANG_VALUES_4},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "15": [
        {"key": "area", "name": "地区", "value": _AREA_VALUES_15},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
    "16": [
        {"key": "area", "name": "地区", "value": _AREA_VALUES_16},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
    ],
}


class Spider(Spider):
    """立播|4K Spider — HTML采集型"""

    def getName(self):
        return "立播|4K"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.site = self._resolve_domain()
        self.headers = {
            'User-Agent': UA,
            'Referer': self.site + '/',
        }

    # ========== 工具函数 ==========

    def _resolve_domain(self):
        """域名解析，尝试访问站点获取可用域名"""
        for domain in DOMAIN_LIST:
            try:
                rsp = self.fetch(domain, headers={'User-Agent': UA}, timeout=8, allow_redirects=True)
                if rsp and rsp.status_code == 200 and len(rsp.text) > 500:
                    # 使用最终URL（跟随重定向）
                    return domain.rstrip('/')
            except Exception:
                continue
        # 兜底返回第一个
        return DOMAIN_LIST[0].rstrip('/')

    def _request(self, url, referer=None):
        """统一请求方法"""
        headers = dict(self.headers)
        if referer:
            headers['Referer'] = referer
        else:
            headers['Referer'] = self.site + '/'
        try:
            rsp = self.fetch(url, headers=headers, timeout=15)
            return rsp
        except Exception:
            return None

    def _post_request(self, url, data=None, headers=None):
        """统一POST请求"""
        hdrs = dict(self.headers)
        if headers:
            hdrs.update(headers)
        try:
            rsp = self.post(url, data=data, headers=hdrs, timeout=15)
            return rsp
        except Exception:
            return None

    def _pq(self, html):
        """创建 pyquery 对象"""
        if HAS_PQ:
            return pq(html)
        return None

    @staticmethod
    def _fix_url(site_url, url):
        """URL修复（相对→绝对）"""
        if not url:
            return ''
        url = str(url).strip()
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('http'):
            return url
        if url.startswith('/'):
            return site_url.rstrip('/') + url
        return urljoin(site_url + '/', url)

    @staticmethod
    def _strip_trailing_slash(url):
        """去除尾部斜杠"""
        return str(url).rstrip('/') if url else ''

    @staticmethod
    def _safe_str(val, default=''):
        """空值返回默认值，否则转字符串"""
        if val is None or val == '' or val == 'None':
            return default
        return str(val).strip()

    @staticmethod
    def _safe_page(val, default=1):
        """安全解析页码"""
        try:
            p = int(val)
            return max(1, p)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_json(text):
        """安全 JSON 解析"""
        try:
            return json.loads(text)
        except Exception:
            return None

    @staticmethod
    def _base64url_encode(text):
        """base64url 编码"""
        raw = base64.b64encode(str(text).encode('utf-8'))
        return raw.replace(b'+', b'-').replace(b'/', b'_').rstrip(b'=').decode('utf-8')

    @staticmethod
    def _base64url_decode(text):
        """base64url 解码"""
        text = str(text).replace('-', '+').replace('_', '/')
        padding = 4 - len(text) % 4
        if padding != 4:
            text += '=' * padding
        return base64.b64decode(text).decode('utf-8', errors='replace')

    @staticmethod
    def _encode_play_id(href):
        """编码播放ID: base64url(href) + PLAY_FLAG 前缀"""
        encoded = base64.b64encode(str(href).encode('utf-8'))
        encoded = encoded.replace(b'+', b'-').replace(b'/', b'_').rstrip(b'=')
        return PLAY_FLAG + encoded.decode('utf-8')

    @staticmethod
    def _decode_play_id(play_id):
        """解码播放ID: 去掉 libvio: 前缀，base64url 解码"""
        if not play_id or not play_id.startswith(PLAY_FLAG):
            return ''
        data = play_id[len(PLAY_FLAG):]
        data = data.replace('-', '+').replace('_', '/')
        padding = 4 - len(data) % 4
        if padding != 4:
            data += '=' * padding
        try:
            return base64.b64decode(data).decode('utf-8', errors='replace')
        except Exception:
            return ''

    @staticmethod
    def _clean_ep_name(text):
        """集名清理：替换 $ 和 # 为 _"""
        return str(text or '').replace('$', '_').replace('#', '_')

    @staticmethod
    def _clean_html(text):
        """清理HTML标签"""
        text = str(text or '')
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
        text = re.sub(r'</?(p|div|h[1-6]|ul|li|ol|section|article)[^>]*>', '\n', text, flags=re.I)
        text = re.sub(r'<[^>]*>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _match_area(text):
        """匹配地区名"""
        m = RE_AREA.search(str(text or ''))
        return m.group(1) if m else ''

    # ========== HTML 解析辅助 ==========

    def _parse_list_items(self, doc):
        """解析列表页视频条目 — 通用"""
        items = []
        if HAS_PQ:
            for a in doc('a.stui-vodlist__thumb[href^="/detail/"]').items():
                href = a.attr('href') or ''
                m = RE_ID.search(href)
                if not m:
                    continue
                vod_id = m.group(1)
                vod_name = a.attr('title') or a.text().strip()
                vod_pic = a.attr('data-original') or a.attr('data-src') or a.attr('src') or ''
                remarks = ''
                pic_text = a('.pic-text')
                if pic_text:
                    remarks = pic_text.text().strip()
                items.append({
                    'vod_id': vod_id,
                    'vod_name': self._safe_str(vod_name),
                    'vod_pic': self._safe_str(vod_pic),
                    'vod_remarks': self._safe_str(remarks),
                })
        else:
            # BeautifulSoup 兜底
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(str(doc), 'html.parser')
                for a in soup.select('a.stui-vodlist__thumb[href^="/detail/"]'):
                    href = a.get('href', '')
                    m = RE_ID.search(href)
                    if not m:
                        continue
                    vod_id = m.group(1)
                    vod_name = a.get('title', '') or a.get_text(strip=True)
                    vod_pic = a.get('data-original') or a.get('data-src') or a.get('src', '')
                    remarks = ''
                    pic_el = a.select_one('.pic-text')
                    if pic_el:
                        remarks = pic_el.get_text(strip=True)
                    items.append({
                        'vod_id': vod_id,
                        'vod_name': self._safe_str(vod_name),
                        'vod_pic': self._safe_str(vod_pic),
                        'vod_remarks': self._safe_str(remarks),
                    })
            except Exception:
                pass
        return items

    def _parse_home_items(self, doc):
        """从首页解析推荐视频列表"""
        items = []
        if HAS_PQ:
            for a in doc('a.stui-vodlist__thumb').items():
                href = a.attr('href') or ''
                if not href.startswith('/detail/'):
                    continue
                m = RE_ID.search(href)
                if not m:
                    continue
                vod_id = m.group(1)
                vod_name = a.attr('title') or a.text().strip()
                vod_pic = a.attr('data-original') or a.attr('data-src') or a.attr('src') or ''
                remarks = ''
                pic_text = a('.pic-text')
                if pic_text:
                    remarks = pic_text.text().strip()
                items.append({
                    'vod_id': vod_id,
                    'vod_name': self._safe_str(vod_name),
                    'vod_pic': self._safe_str(vod_pic),
                    'vod_remarks': self._safe_str(remarks),
                })
        else:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(str(doc), 'html.parser')
                for a in soup.select('a.stui-vodlist__thumb'):
                    href = a.get('href', '')
                    if not href.startswith('/detail/'):
                        continue
                    m = RE_ID.search(href)
                    if not m:
                        continue
                    vod_id = m.group(1)
                    vod_name = a.get('title', '') or a.get_text(strip=True)
                    vod_pic = a.get('data-original') or a.get('data-src') or a.get('src', '')
                    remarks = ''
                    pic_el = a.select_one('.pic-text')
                    if pic_el:
                        remarks = pic_el.get_text(strip=True)
                    items.append({
                        'vod_id': vod_id,
                        'vod_name': self._safe_str(vod_name),
                        'vod_pic': self._safe_str(vod_pic),
                        'vod_remarks': self._safe_str(remarks),
                    })
            except Exception:
                pass
        return items

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}

        # 尝试从页面动态获取分类（可选，失败则用默认）
        classes = list(CLASSES)
        filters = dict(FILTERS_TEMPLATE)

        # 尝试请求首页获取最新分类信息
        try:
            rsp = self._request(self.site + '/')
            if rsp and rsp.status_code == 200:
                html = rsp.text
                doc = self._pq(html)
                if doc:
                    dynamic_classes = self._parse_home_classes(doc)
                    if dynamic_classes:
                        classes = dynamic_classes
        except Exception:
            pass

        result['class'] = classes
        if filter:
            result['filters'] = filters
        return result

    def _parse_home_classes(self, doc):
        """从首页导航栏解析分类列表"""
        classes = []
        if HAS_PQ:
            for a in doc('ul.stui-header__menu a[href^="/show/"], ul.stui-header__menu a[href^="/type/"]').items():
                href = a.attr('href') or ''
                name = a.text().strip()
                m = RE_ID.search(href)
                if m and name:
                    tid = m.group(1)
                    classes.append({'type_id': tid, 'type_name': name})
        else:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(str(doc), 'html.parser')
                for a in soup.select('ul.stui-header__menu a[href^="/show/"], ul.stui-header__menu a[href^="/type/"]'):
                    href = a.get('href', '')
                    name = a.get_text(strip=True)
                    m = RE_ID.search(href)
                    if m and name:
                        tid = m.group(1)
                        classes.append({'type_id': tid, 'type_name': name})
            except Exception:
                pass
        return classes

    # ========== 首页推荐 ==========

    def homeVideoContent(self):
        try:
            rsp = self._request(self.site + '/')
            if rsp and rsp.status_code == 200:
                html = rsp.text
                doc = self._pq(html)
                if doc:
                    items = self._parse_home_items(doc)
                    if items:
                        return {'list': items[:72]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, '1')
        pg = self._safe_page(pg, 1)
        extend = extend or {}

        area = self._safe_str(extend.get('area', ''))
        year = self._safe_str(extend.get('year', ''))
        lang = self._safe_str(extend.get('lang', ''))
        by = self._safe_str(extend.get('by', ''))
        cls = self._safe_str(extend.get('class', ''))
        letter = ''

        # URL 格式: /show/{tid}-{area}-{by}-{class}-{lang}-{letter}---{page}---{year}.html
        url = (
            f'{self.site}/show/{tid}-{area}-{by}-{cls}-{lang}-{letter}'
            f'---{pg}---{year}.html'
        )

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(pg), 'pagecount': pg, 'limit': PAGE_SIZE, 'total': 0}

            html = rsp.text
            doc = self._pq(html)
            if not doc:
                return {'list': [], 'page': str(pg), 'pagecount': pg, 'limit': PAGE_SIZE, 'total': 0}

            items = self._parse_list_items(doc)

            # 判断是否有下一页
            pagecount = pg
            if HAS_PQ:
                next_a = doc('a.stui-page__item[href*="---"]')
                for a in next_a.items():
                    href = a.attr('href') or ''
                    m_page = re.search(r'---(\d+)---', href)
                    if m_page:
                        next_pg = int(m_page.group(1))
                        if next_pg > pg:
                            pagecount = next_pg
                            break
                # 也检查 "下一页" 链接
                next_btn = doc('a.page-next, a:contains("下一页")')
                for a in next_btn.items():
                    href = a.attr('href') or ''
                    if href:
                        pagecount = pg + 1
                        break
            else:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(str(doc), 'html.parser')
                    for a in soup.select('a.stui-page__item[href*="---"], a.page-next'):
                        href = a.get('href', '')
                        if href:
                            m_page = re.search(r'---(\d+)---', href)
                            if m_page and int(m_page.group(1)) > pg:
                                pagecount = int(m_page.group(1))
                                break
                            elif not m_page and ('next' in (a.get('class', '') or '')):
                                pagecount = pg + 1
                                break
                except Exception:
                    pass

            if not items and pg == 1:
                pagecount = pg

            return {
                'list': items,
                'page': str(pg),
                'pagecount': pagecount,
                'limit': PAGE_SIZE,
                'total': 0,
            }
        except Exception:
            return {'list': [], 'page': str(pg), 'pagecount': pg, 'limit': PAGE_SIZE, 'total': 0}

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vid = str(ids[0])

        url = f'{self.site}/detail/{vid}.html'
        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return self._empty_detail(vid)

            html = rsp.text
            doc = self._pq(html)
            if not doc:
                return self._empty_detail(vid)

            return self._parse_detail(doc, vid)
        except Exception:
            return self._empty_detail(vid)

    def _empty_detail(self, vid):
        """返回空详情"""
        vod = {
            'vod_id': vid,
            'vod_name': '',
            'vod_pic': '',
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': '',
            'vod_play_url': '',
        }
        return {'list': [vod]}

    def _parse_detail(self, doc, vid):
        """解析详情页"""
        vod = {
            'vod_id': vid,
            'vod_name': '',
            'vod_pic': '',
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': '',
            'vod_play_url': '',
        }

        if HAS_PQ:
            # 标题
            h1 = doc('.vod-info h1.title')
            if h1:
                vod['vod_name'] = self._safe_str(h1.text())

            # 图片
            poster = doc('.vod-poster__wrap img')
            if poster:
                vod['vod_pic'] = self._safe_str(
                    poster.attr('data-original') or poster.attr('data-src') or poster.attr('src')
                )

            # 简介
            content = doc('.detail-content')
            if not content:
                content = doc('.detail-sketch')
            if content:
                vod['vod_content'] = self._clean_html(content.html())

            # 元信息
            meta_items = doc('.vod-info .vod-meta .meta-item')
            for mi in meta_items.items():
                text = mi.text().strip()
                # text 格式通常为 "标签：值" 或 "标签 值"
                if text.startswith('主演：') or text.startswith('主演:'):
                    vod['vod_actor'] = self._safe_str(text.split('：', 1)[-1].split(':', 1)[-1])
                elif text.startswith('导演：') or text.startswith('导演:'):
                    vod['vod_director'] = self._safe_str(text.split('：', 1)[-1].split(':', 1)[-1])
                elif re.search(r'(19|20)\d{2}', text):
                    ym = re.search(r'(19|20)\d{2}', text)
                    if ym:
                        vod['vod_year'] = ym.group()
                else:
                    area = self._match_area(text)
                    if area:
                        vod['vod_area'] = area

            # 备注（更新状态）
            remarks_el = doc('.vod-info .vod-meta .slide-info, .pic-text')
            if remarks_el:
                vod['vod_remarks'] = self._safe_str(remarks_el.text())

            # 播放列表
            play_from_list = []
            play_url_list = []
            panels = doc('div.playlist-panel')
            for panel in panels.items():
                # 排除网盘面板
                panel_classes = panel.attr('class') or ''
                if 'netdisk' in panel_classes:
                    continue

                # 来源名
                source_name = ''
                h3 = panel('.panel-head h3')
                if h3:
                    source_name = self._safe_str(h3.text())
                if not source_name:
                    source_name = '默认'

                # 集数链接
                episodes = []
                links = panel('ul.stui-content__playlist a[href^="/w/"]')
                for a in links.items():
                    href = a.attr('href') or ''
                    ep_name = self._clean_ep_name(a.text().strip())
                    if not ep_name:
                        ep_name = self._clean_ep_name(a.attr('title') or '')
                    if not ep_name:
                        continue
                    play_id = self._encode_play_id(href)
                    episodes.append(f'{ep_name}${play_id}')

                if episodes:
                    play_from_list.append(source_name)
                    play_url_list.append('#'.join(episodes))

            vod['vod_play_from'] = '$$$'.join(play_from_list)
            vod['vod_play_url'] = '$$$'.join(play_url_list)

        else:
            # BeautifulSoup 兜底
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(str(doc), 'html.parser')

                # 标题
                h1 = soup.select_one('.vod-info h1.title')
                if h1:
                    vod['vod_name'] = self._safe_str(h1.get_text(strip=True))

                # 图片
                poster = soup.select_one('.vod-poster__wrap img')
                if poster:
                    vod['vod_pic'] = self._safe_str(
                        poster.get('data-original') or poster.get('data-src') or poster.get('src', '')
                    )

                # 简介
                content = soup.select_one('.detail-content')
                if not content:
                    content = soup.select_one('.detail-sketch')
                if content:
                    vod['vod_content'] = self._clean_html(str(content))

                # 元信息
                for mi in soup.select('.vod-info .vod-meta .meta-item'):
                    text = mi.get_text(strip=True)
                    if text.startswith('主演：') or text.startswith('主演:'):
                        vod['vod_actor'] = self._safe_str(text.split('：', 1)[-1].split(':', 1)[-1])
                    elif text.startswith('导演：') or text.startswith('导演:'):
                        vod['vod_director'] = self._safe_str(text.split('：', 1)[-1].split(':', 1)[-1])
                    elif re.search(r'(19|20)\d{2}', text):
                        ym = re.search(r'(19|20)\d{2}', text)
                        if ym:
                            vod['vod_year'] = ym.group()
                    else:
                        area = self._match_area(text)
                        if area:
                            vod['vod_area'] = area

                # 备注
                remarks_el = soup.select_one('.pic-text')
                if remarks_el:
                    vod['vod_remarks'] = self._safe_str(remarks_el.get_text(strip=True))

                # 播放列表
                play_from_list = []
                play_url_list = []
                for panel in soup.select('div.playlist-panel'):
                    panel_classes = ' '.join(panel.get('class', []))
                    if 'netdisk' in panel_classes:
                        continue

                    h3 = panel.select_one('.panel-head h3')
                    source_name = h3.get_text(strip=True) if h3 else '默认'

                    episodes = []
                    for a in panel.select('ul.stui-content__playlist a[href^="/w/"]'):
                        href = a.get('href', '')
                        ep_name = self._clean_ep_name(a.get_text(strip=True))
                        if not ep_name:
                            continue
                        play_id = self._encode_play_id(href)
                        episodes.append(f'{ep_name}${play_id}')

                    if episodes:
                        play_from_list.append(source_name)
                        play_url_list.append('#'.join(episodes))

                vod['vod_play_from'] = '$$$'.join(play_from_list)
                vod['vod_play_url'] = '$$$'.join(play_url_list)

            except Exception:
                pass

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址"""
        # 如果不是 libvio: 前缀，走通用播放器
        if not str(id).startswith(PLAY_FLAG):
            return {'parse': 1, 'url': str(id), 'playUrl': ''}

        # 解码获取相对URL
        href = self._decode_play_id(id)
        if not href:
            return {'parse': 0, 'url': '', 'playUrl': ''}

        # 构建完整URL
        full_url = self._fix_url(self.site, href)
        referer = full_url

        try:
            # 请求播放页面
            rsp = self._request(full_url, referer=referer)
            if not rsp or rsp.status_code != 200:
                return {'parse': 0, 'url': '', 'playUrl': ''}

            html = rsp.text

            # 用 tdt 正则提取 player_aaaa JSON
            m = RE_PLAYER.search(html)
            if not m:
                return {'parse': 0, 'url': '', 'playUrl': ''}

            player_data = self._safe_json(m.group(1))
            if not player_data:
                return {'parse': 0, 'url': '', 'playUrl': ''}

            play_url = self._safe_str(player_data.get('url', ''))
            play_from = self._safe_str(player_data.get('from', ''))

            # 如果 url 是 http 开头，直接返回
            if play_url.startswith('http'):
                return {
                    'parse': 0,
                    'url': play_url,
                    'playUrl': '',
                    'header': {'Referer': self.site + '/'},
                }

            # 根据 from 走不同解析通道
            if play_from == 'yd189':
                final_url = self._parse_yd189(play_url, full_url, html)
            elif play_from == 'ty_new1':
                final_url = self._parse_ty_new1(play_url, full_url, html)
            else:
                final_url = play_url

            if not final_url:
                return {'parse': 0, 'url': '', 'playUrl': ''}

            return {
                'parse': 0,
                'url': final_url,
                'playUrl': '',
                'header': {'Referer': self.site + '/'},
            }

        except Exception:
            return {'parse': 0, 'url': '', 'playUrl': ''}

    def _parse_yd189(self, play_url, page_url, page_html):
        """yd189 播放源解析"""
        try:
            # 请求 /vid/yd.php?url=xxx&id=xxx&nid=xxx&_ts=timestamp
            ts = str(int(time.time()))
            yd_url = f'{self.site}/vid/yd.php?url={quote(play_url)}&id=0&nid=0&_ts={ts}'

            rsp = self._request(yd_url, referer=page_url)
            if not rsp or rsp.status_code != 200:
                return ''

            yd_html = rsp.text

            # 用 rdt 正则提取 fetch URL
            m = RE_FETCH.search(yd_html)
            if not m:
                return ''

            fetch_url = m.group(1)
            # 修复为完整URL
            fetch_url = self._fix_url(self.site, fetch_url)

            # 请求 fetch URL 获取最终播放地址
            fetch_rsp = self._request(fetch_url, referer=page_url)
            if not fetch_rsp or fetch_rsp.status_code != 200:
                return ''

            result = self._safe_json(fetch_rsp.text)
            if result and isinstance(result, dict):
                url = self._safe_str(result.get('url', '') or result.get('data', ''))
                if url.startswith('http'):
                    return url

            # 如果返回的不是JSON，可能直接是URL
            text = fetch_rsp.text.strip()
            if text.startswith('http'):
                return text

            return ''
        except Exception:
            return ''

    def _parse_ty_new1(self, play_url, page_url, page_html):
        """ty_new1 播放源解析（最多重试6次）"""
        try:
            for _ in range(6):
                # 请求 /vid/ty4.php?url=xxx&next=xxx&id=xxx&nid=xxx&_ts=timestamp
                ts = str(int(time.time()))
                ty_url = (
                    f'{self.site}/vid/ty4.php?url={quote(play_url)}'
                    f'&next=0&id=0&nid=0&_ts={ts}'
                )

                rsp = self._request(ty_url, referer=page_url)
                if not rsp or rsp.status_code != 200:
                    continue

                ty_html = rsp.text

                # 用 idt 正则提取 LIBVIO_CFG 配置
                m = RE_CFG.search(ty_html)
                if not m:
                    continue

                cfg = self._safe_json(m.group(1))
                if not cfg or not isinstance(cfg, dict):
                    continue

                parse_url = self._safe_str(cfg.get('parseUrl', ''))
                if not parse_url:
                    continue

                parse_url = self._fix_url(self.site, parse_url)

                # POST 请求 parseUrl 解析获取最终地址
                post_data = {
                    'url': play_url,
                }
                post_rsp = self._post_request(
                    parse_url,
                    data=urlencode(post_data).encode('utf-8'),
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Referer': self.site + '/',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                )
                if not post_rsp or post_rsp.status_code != 200:
                    continue

                result = self._safe_json(post_rsp.text)
                if result and isinstance(result, dict):
                    url = self._safe_str(result.get('url', '') or result.get('data', ''))
                    if url.startswith('http'):
                        return url

                # 如果返回的不是JSON，可能直接是URL
                text = post_rsp.text.strip()
                if text.startswith('http'):
                    return text

            return ''
        except Exception:
            return ''

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        pg = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': []}

        url = f'{self.site}/search/-------------.html?wd={quote(keyword)}&page={pg}'
        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}

            html = rsp.text
            doc = self._pq(html)
            if not doc:
                return {'list': []}

            items = self._parse_list_items(doc)

            pagecount = pg
            if HAS_PQ:
                next_a = doc('a.stui-page__item[href*="page="]')
                for a in next_a.items():
                    href = a.attr('href') or ''
                    m_page = re.search(r'page=(\d+)', href)
                    if m_page:
                        next_pg = int(m_page.group(1))
                        if next_pg > pg:
                            pagecount = next_pg
                            break
            else:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(str(doc), 'html.parser')
                    for a in soup.select('a.stui-page__item[href*="page="]'):
                        href = a.get('href', '')
                        m_page = re.search(r'page=(\d+)', href)
                        if m_page and int(m_page.group(1)) > pg:
                            pagecount = int(m_page.group(1))
                            break
                except Exception:
                    pass

            return {
                'list': items,
                'page': str(pg),
                'pagecount': pagecount,
                'limit': PAGE_SIZE,
                'total': 0,
            }
        except Exception:
            return {'list': []}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 本地代理 ==========

    def localProxy(self, param):
        """本地代理接口（libvio 播放走自定义解析，此方法保留用于通用播放器 proxy 转发）"""
        try:
            import urllib.parse as up
            raw_url = ''
            if isinstance(param, dict):
                raw_url = param.get('url', '') or param.get('u', '')
            elif isinstance(param, str):
                qs = up.parse_qs(param)
                raw_url = qs.get('url', [''])[0] or qs.get('u', [''])[0]

            media_url = up.unquote(raw_url) if raw_url else ''
            if not media_url:
                return [404, 'text/plain', b'']

            # 转发请求
            headers = {'User-Agent': UA, 'Referer': self.site + '/'}
            rsp = self.fetch(media_url, headers=headers, timeout=30)
            content = rsp.content if hasattr(rsp, 'content') else rsp.text.encode('utf-8')

            # 判断内容类型
            text = ''
            try:
                text = content.decode('utf-8')
            except Exception:
                pass

            if '#EXTM3U' in text:
                return [200, 'application/x-mpegURL; charset=utf-8', content]

            return [200, 'application/octet-stream', content]
        except Exception:
            return [500, 'text/plain', b'proxy error']

    # ========== 可选接口 ==========

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|avi)(\?|$)', url or '', re.I))

    def manualVideoCheck(self):
        return True

    def destroy(self):
        pass

    def close(self):
        self.destroy()


if __name__ == '__main__':
    spider = Spider()
    spider.init()
    # 测试首页
    print(json.dumps(spider.homeContent(1), ensure_ascii=False, indent=2)[:2000])
    # 测试分类
    # print(json.dumps(spider.categoryContent('1', 1, 0, {}), ensure_ascii=False, indent=2)[:2000])
    # 测试搜索
    # print(json.dumps(spider.searchContent('电影', False), ensure_ascii=False, indent=2)[:2000])
    # 测试详情
    # print(json.dumps(spider.detailContent('12345'), ensure_ascii=False, indent=2)[:3000])
