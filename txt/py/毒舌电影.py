# -*- coding: utf-8 -*-
"""
毒舌电影 — 兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4) 双壳子
站点: https://www.dushe02.com
CMS: 苹果CMS V10 (API已关闭，纯HTML爬取)
版本: 1.0.0
"""
import sys
import json
import re
import time
import base64
from html import unescape
from urllib.parse import quote, unquote, urljoin

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    import requests as rq

    class BaseSpider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=30, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(BaseSpider):
    """毒舌电影 Spider — 苹果CMS V10 HTML爬取"""

    def getName(self):
        return "毒舌电影"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''

        self.host = "https://www.dushe.live"
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Referer': self.host + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        }

        self._home_cache = []
        self._home_cache_time = 0
        self._class_list = []

    # ========== 网络请求封装 ==========
    def _txt(self, url, referer=None, timeout=30):
        """获取页面文本"""
        headers = dict(self.header)
        if referer:
            headers['Referer'] = referer
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            try:
                rsp.encoding = 'utf-8'
            except Exception:
                pass
            text = rsp.text
            # 检测CF拦截
            if '520' in text[:500] and 'cloudflare' in text[:500].lower():
                return ''
            return text
        except Exception:
            return ''

    def _match(self, pattern, text, default='', flags=re.S):
        m = re.search(pattern, text or '', flags)
        return m.group(1).strip() if m else default

    def _clean(self, text):
        if not text:
            return ''
        text = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', '', text)
        text = re.sub(r'(?is)<br\s*/?>', ' ', text)
        text = re.sub(r'(?is)<.*?>', '', text)
        text = unescape(text).replace('\xa0', ' ')
        return re.sub(r'\s+', ' ', text).strip()

    def _url(self, path):
        if not path:
            return ''
        if path.startswith('http'):
            return path
        if path.startswith('//'):
            return 'https:' + path
        return urljoin(self.host + '/', path)

    def _fix_pic(self, pic):
        if not pic:
            return ''
        if pic.startswith('//'):
            return 'https:' + pic
        if pic.startswith('/'):
            return self.host + pic
        return pic

    def _is_direct_media(self, url):
        url = (url or '').lower()
        return '.m3u8' in url or '.mp4' in url or '.flv' in url or '.mkv' in url

    # ========== 首页 ==========
    def homeContent(self, filter):
        result = {}

        # 毒舌电影标准分类
        classes = [
            {'type_id': '1', 'type_name': '电影'},
            {'type_id': '2', 'type_name': '电视剧'},
            {'type_id': '3', 'type_name': '综艺'},
            {'type_id': '4', 'type_name': '动漫'},
        ]
        self._class_list = classes
        result['class'] = classes

        if filter:
            result['filters'] = self._build_filters()

        return result

    def _build_filters(self):
        filters = {}
        year_values = [
            {'n': '全部', 'v': ''},
            {'n': '2026', 'v': '2026'}, {'n': '2025', 'v': '2025'},
            {'n': '2024', 'v': '2024'}, {'n': '2023', 'v': '2023'},
            {'n': '2022', 'v': '2022'}, {'n': '2021', 'v': '2021'},
            {'n': '2020', 'v': '2020'}, {'n': '2019', 'v': '2019'},
        ]
        area_values = [
            {'n': '全部', 'v': ''},
            {'n': '大陆', 'v': '大陆'}, {'n': '香港', 'v': '香港'},
            {'n': '台湾', 'v': '台湾'}, {'n': '美国', 'v': '美国'},
            {'n': '日本', 'v': '日本'}, {'n': '韩国', 'v': '韩国'},
            {'n': '英国', 'v': '英国'}, {'n': '法国', 'v': '法国'},
            {'n': '泰国', 'v': '泰国'}, {'n': '印度', 'v': '印度'},
        ]

        # 各分类的子类型 (苹果CMS标准分类ID)
        class_maps = {
            '1': [
                {'n': '全部', 'v': ''}, {'n': '动作片', 'v': '6'},
                {'n': '喜剧片', 'v': '7'}, {'n': '爱情片', 'v': '8'},
                {'n': '科幻片', 'v': '9'}, {'n': '恐怖片', 'v': '10'},
                {'n': '剧情片', 'v': '11'}, {'n': '战争片', 'v': '12'},
                {'n': '动画片', 'v': '13'}, {'n': '纪录片', 'v': '20'},
            ],
            '2': [
                {'n': '全部', 'v': ''}, {'n': '国产剧', 'v': '14'},
                {'n': '港台剧', 'v': '15'}, {'n': '日韩剧', 'v': '16'},
                {'n': '欧美剧', 'v': '17'}, {'n': '海外剧', 'v': '21'},
            ],
            '3': [
                {'n': '全部', 'v': ''}, {'n': '大陆综艺', 'v': '22'},
                {'n': '港台综艺', 'v': '23'}, {'n': '日韩综艺', 'v': '24'},
                {'n': '欧美综艺', 'v': '25'},
            ],
            '4': [
                {'n': '全部', 'v': ''}, {'n': '国产动漫', 'v': '26'},
                {'n': '日本动漫', 'v': '27'}, {'n': '欧美动漫', 'v': '28'},
                {'n': '海外动漫', 'v': '29'},
            ],
        }

        for c in self._class_list:
            tid = c.get('type_id', '')
            if tid:
                cls_vals = class_maps.get(tid, [{'n': '全部', 'v': ''}])
                filters[tid] = [
                    {'key': 'cate', 'name': '分类', 'value': cls_vals},
                    {'key': 'area', 'name': '地区', 'value': area_values},
                    {'key': 'year', 'name': '年份', 'value': year_values},
                ]
        return filters

    def homeVideoContent(self):
        now = int(time.time())
        if self._home_cache and now - self._home_cache_time < 300:
            return {'list': self._home_cache[:72]}

        tids = ['1', '2', '3', '4']
        urls = [
            self.host + '/vodshow/' + tid + '-----------.html'
            for tid in tids
        ]
        videos = []
        seen = set()

        def load(url):
            html = self._txt(url, timeout=12)
            return self._parse_list(html)

        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            pool = ThreadPoolExecutor(max_workers=4)
            futures = [pool.submit(load, u) for u in urls]
            try:
                for fu in as_completed(futures, timeout=18):
                    for v in fu.result() or []:
                        vid = v.get('vod_id')
                        if vid and vid not in seen:
                            seen.add(vid)
                            videos.append(v)
                        if len(videos) >= 72:
                            break
                    if len(videos) >= 72:
                        break
            finally:
                pool.shutdown(wait=False)
        except Exception:
            for u in urls:
                for v in load(u):
                    vid = v.get('vod_id')
                    if vid and vid not in seen:
                        seen.add(vid)
                        videos.append(v)
                    if len(videos) >= 72:
                        break

        # 兜底：首页
        if len(videos) < 20:
            html = self._txt(self.host + '/', timeout=15)
            for v in self._parse_list(html):
                vid = v.get('vod_id')
                if vid and vid not in seen:
                    seen.add(vid)
                    videos.append(v)

        self._home_cache = videos[:72]
        self._home_cache_time = now
        return {'list': self._home_cache}

    # ========== 分类列表 ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or '1')
        tid = str(tid or '1')

        cate = ''
        area = ''
        year = ''
        if isinstance(extend, dict):
            cate = extend.get('cate', '') or ''
            area = extend.get('area', '') or ''
            year = extend.get('year', '') or ''

        # 构建苹果CMS vodshow URL
        # 格式: /vodshow/{tid}-{cate}-{by}-{class}-{year}-{area}-{letter}-{order}-{page}.html
        area_enc = quote(area, safe='')
        year_enc = quote(year, safe='')
        if cate or area or year:
            url = self.host + '/vodshow/' + tid + '-' + cate + '----' + year_enc + '--' + area_enc + '--' + pg + '.html'
        else:
            url = self.host + '/vodshow/' + tid + '-----------' + pg + '.html'

        videos = []
        for attempt_url in [url,
                            self.host + '/vodtype/' + tid + '.html',
                            self.host + '/vodtype/' + tid + '-' + pg + '.html']:
            html = self._txt(attempt_url, timeout=30)
            if html and len(html) > 1000:
                videos = self._parse_list(html)
                if videos:
                    break

        # 分页估算
        total_match = self._match(r'共\s*(\d+)\s*条', html if html else '')
        if total_match and total_match.isdigit():
            total = int(total_match)
            pagecount = (total + 23) // 24
        else:
            total = 9999
            pagecount = 999

        return {
            'list': videos,
            'page': pg,
            'pagecount': pagecount,
            'limit': len(videos) or 20,
            'total': total,
        }

    # ========== 列表解析 ==========
    def _parse_list(self, html):
        """解析列表页HTML，兼容多种苹果CMS模板"""
        videos = []
        if not html or len(html) < 500:
            return videos

        # 模式1: stui/myui 模板 (毒舌电影常见)
        # <li> <a href="/voddetail/123.html"> <img src/alt> <h4>标题</h4> <span>备注</span> </a> </li>
        items = re.findall(
            r'<li[^>]*>.*?'
            r'<a[^>]+href=["\']([^"\']*voddetail/(\d+)\.html[^"\']*)["\']',
            html, re.S
        )
        if items:
            for href, vid in items:
                # 提取上下文：找这个a标签附近的内容
                # 图片
                img_match = re.search(
                    r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']',
                    html[max(0, html.find(href) - 500):html.find(href) + 500],
                    re.S
                )
                pic = img_match.group(1) if img_match else ''
                if 'load.gif' in pic or 'loading' in pic:
                    pic = ''

                # 标题
                title_match = re.search(
                    r'(?:title|alt)=["\']([^"\']+)["\']',
                    html[max(0, html.find(href) - 300):html.find(href) + 300],
                    re.S
                )
                title = title_match.group(1) if title_match else ''

                # 备注
                remark_match = re.search(
                    r'<[^>]*class=["\'][^"\']*(?:remarks?|tag|note|status|text|score)[^"\']*["\'][^>]*>(.*?)</[^>]*>',
                    html[max(0, html.find(href) - 300):html.find(href) + 800],
                    re.S
                )
                remarks = remark_match.group(1) if remark_match else ''
                remarks = re.sub(r'<[^>]+>', '', remarks).strip()

                videos.append({
                    'vod_id': vid,
                    'vod_name': self._clean(title),
                    'vod_pic': self._fix_pic(pic),
                    'vod_remarks': self._clean(remarks),
                })
            if videos:
                return videos

        # 模式2: 宽松 a+img 匹配
        blocks = re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:voddetail|vod|detail)/(\d+)\.html[^"\']*)["\']'
            r'[^>]*>.*?'
            r'<img[^>]+(?:data-original|src)=["\']([^"\']+)["\']',
            html, re.S
        )
        for href, vid, pic in blocks:
            if 'load.gif' in pic:
                continue
            # 从href附近提取标题
            chunk = html[max(0, html.find(href) - 400):html.find(href) + 600]
            title = self._match(r'(?:title|alt)=["\']([^"\']+)["\']', chunk)
            remarks = self._match(
                r'<[^>]*class=["\'][^"\']*(?:remarks?|tag|note|status|text|score|pic-text)[^"\']*["\'][^>]*>(.*?)</[^>]*>',
                chunk
            )
            videos.append({
                'vod_id': vid,
                'vod_name': self._clean(title) or '未知',
                'vod_pic': self._fix_pic(pic),
                'vod_remarks': self._clean(remarks),
            })

        return videos

    # ========== 详情页 ==========
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])

        # 尝试多种详情页URL
        urls = [
            self.host + '/voddetail/' + vod_id + '.html',
            self.host + '/detail/' + vod_id + '.html',
            self.host + '/vod/' + vod_id + '.html',
        ]

        html = ''
        for url in urls:
            html = self._txt(url, timeout=30)
            if html and len(html) > 1000 and '520' not in html[:500]:
                break

        if not html:
            return {'list': []}

        # === 解析影片信息 ===
        # 标题: <title>标签 (最可靠)
        name = self._match(r'<title>(.*?)</title>', html)
        if name:
            # 清理: 去掉 "-毒舌电影" "-高清在线免费观看" 等后缀
            name = re.sub(r'《(.*?)》.*', r'\1', name) or name
            name = re.sub(r'-(?:高清|完整版|毒舌电影|在线).*$', '', name).strip()
        if not name:
            name = self._match(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html)
        if not name:
            name = self._match(r'<h1[^>]*>(.*?)</h1>', html)

        # 封面: og:image / poster
        pic = self._match(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html)
        if not pic:
            pic = self._match(
                r'<img[^>]+(?:alt=["\']poster["\']|class=["\'][^"\']*(?:poster|pic|thumb|vod|detail)[^"\']*["\'])[^>]+src=["\']([^"\']+)["\']',
                html
            )
        if not pic:
            pic = self._match(r'<img[^>]+src=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*(?:poster|pic|thumb)[^"\']*["\']',
                             html)

        # 简介: og:description 或 页面内容
        content = self._match(r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']', html)
        if not content:
            content = self._match(r'(?:简介|剧情)[：:]\s*(?:</?[^>]*>\s*)*(.*?)(?:</div>|</p>|$)', html)
        if not content:
            content = self._match(r'class=["\']desc["\'][^>]*>(.*?)</[^>]*>', html)

        # 字段提取 — 毒舌电影用 <span class="text-muted">字段：</span> 格式
        type_name = self._match(r'(?:类型|分类)[：:](?:</span>)?\s*(?:<a[^>]*>)?\s*([^<,\s]+)', html)
        if not type_name:
            # fallback: 找 "类型：</span>xxx"
            m = re.search(r'类型[：:]\s*</span>\s*<a[^>]*>([^<]+)</a>', html)
            type_name = m.group(1) if m else ''

        year = self._match(r'(?:年份|年代)[：:](?:</span>)?\s*<a[^>]*>\s*(\d{4})\s*</a>', html)
        if not year:
            year = self._match(r'class=["\']year["\'][^>]*>\s*(\d{4})\s*</', html)

        area = self._match(r'地区[：:](?:</span>)?\s*<a[^>]*>\s*([^<]+)\s*</a>', html)
        if not area:
            area = self._match(r'地区[：:](?:</span>)?\s*([^<\n,，]+)', html)

        remarks = self._match(r'状态[：:](?:</span>)?\s*<a[^>]*>\s*([^<]+)\s*</a>', html)
        if not remarks:
            remarks = self._match(r'class=["\'][^"\']*remarks?[^"\']*["\'][^>]*>([^<]+)</[^>]*>', html)
        if not remarks:
            remarks = self._match(r'class=["\'][^"\']*note[^"\']*["\'][^>]*>([^<]+)</[^>]*>', html)

        # 提取演员：手动匹配
        actor = ''
        m = re.search(r'主演[：:](?:</span>)?\s*(.*?)(?:</p>|<br)', html, re.S)
        if m:
            actor = re.sub(r'<[^>]+>', ' ', m.group(1)).strip()
            actor = re.sub(r'\s+', ' ', actor)

        # 提取导演：手动匹配
        director = ''
        m2 = re.search(r'导演[：:](?:</span>)?\s*(.*?)(?:</p>|<br)', html, re.S)
        if m2:
            director = re.sub(r'<[^>]+>', ' ', m2.group(1)).strip()
            director = re.sub(r'\s+', ' ', director)

        # === 解析播放列表 ===
        play_from_list, play_url_list = self._extract_playlist(html)

        vod = {
            'vod_id': vod_id,
            'vod_name': self._clean(name) or '未知影片',
            'vod_pic': self._fix_pic(pic),
            'type_name': self._clean(type_name) or '',
            'vod_year': self._clean(year) or '',
            'vod_area': self._clean(area) or '',
            'vod_remarks': self._clean(remarks) or '',
            'vod_actor': self._clean(actor) or '',
            'vod_director': self._clean(director) or '',
            'vod_content': self._clean(content) or '暂无简介',
            'vod_play_from': '$$$'.join(play_from_list) if play_from_list else '默认线路',
            'vod_play_url': '$$$'.join(play_url_list) if play_url_list else '正片$' + vod_id,
        }

        return {'list': [vod]}

    def _extract_field(self, html, patterns):
        """通用字段提取"""
        for p in patterns:
            val = self._match(p, html)
            if val:
                return val
        return ''

    def _extract_playlist(self, html):
        """提取播放来源和集数列表"""
        play_from = []
        play_url = []

        # 模式1: 标准苹果CMS多线路 (stui/myui模板)
        # <ul class="stui-content__playlist"> + <li>选项卡切换
        tabs = re.findall(
            r'<li[^>]*>.*?href=["\']#playlist(\d+)["\'][^>]*>(.*?)</a>',
            html, re.S
        )
        if not tabs:
            # 其他模板的选项卡
            tabs = re.findall(
                r'<a[^>]+href=["\']#play_(\d+)["\'][^>]*>(.*?)</a>',
                html, re.S
            )
        if not tabs:
            tabs = re.findall(
                r'<a[^>]+href=["\']#tab(\d+)["\'][^>]*>(.*?)</a>',
                html, re.S
            )

        if tabs:
            for pid, flag_html in tabs:
                flag = self._clean(flag_html) or ('线路' + pid)
                # 找对应 tab 内容
                block_patterns = [
                    r'<div\s+id=["\']playlist' + pid + r'["\'][^>]*>',
                    r'<div\s+id=["\']play_' + pid + r'["\'][^>]*>',
                    r'<div\s+id=["\']tab' + pid + r'["\'][^>]*>',
                ]
                block = ''
                for bp in block_patterns:
                    m = re.search(bp, html, re.S)
                    if m:
                        start = m.start()
                        # 取到下一个 playlist div 或足够远
                        end_match = re.search(r'<div\s+id=["\'][^"\']*(?:playlist|play_|tab)\d+[^"\']*["\']', html[start + len(m.group(0)):], re.S)
                        if end_match:
                            end = start + len(m.group(0)) + end_match.start()
                        else:
                            end = min(start + 15000, len(html))
                        block = html[start:end]
                        break

                eps = []
                for ep_href, ep_title in re.findall(
                    r'<a[^>]+href=["\']([^"\']*vodplay/\d+[^"\']*)["\'][^>]*>(.*?)</a>',
                    block or html, re.S
                ):
                    ep_title = self._clean(ep_title) or '播放'
                    ep_url = self._url(ep_href)
                    eps.append(ep_title + '$' + ep_url)

                if eps:
                    play_from.append(flag)
                    play_url.append('#'.join(eps))

        # 模式2: 单一线路 (没有选项卡)
        if not play_from:
            eps = re.findall(
                r'<a[^>]+href=["\']([^"\']*vodplay/\d+[^"\']*)["\'][^>]*>(.*?)</a>',
                html, re.S
            )
            if eps:
                play_from.append('默认线路')
                ep_strs = []
                for ep_href, ep_title in eps:
                    ep_title = self._clean(ep_title) or '播放'
                    ep_strs.append(ep_title + '$' + self._url(ep_href))
                play_url.append('#'.join(ep_strs))

        # 兜底：直接构造播放URL
        if not play_from:
            play_from.append('默认线路')
            # 尝试从HTML中提取vod_id确认
            vod_id = self._match(r'/voddetail/(\d+)\.html', html)
            if vod_id:
                play_url.append('正片$' + self.host + '/vodplay/' + vod_id + '-1-1.html')
            else:
                play_url.append('正片$' + self.host + '/')

        return play_from, play_url

    # ========== 搜索 ==========
    def searchContent(self, key, quick, pg="1"):
        pg = str(pg or '1')
        wd = quote(key)

        # 苹果CMS标准搜索URL
        urls = [
            self.host + '/vodsearch/' + wd + '-------------.html',
            self.host + '/vodsearch/' + wd + '----------' + pg + '---.html',
            self.host + '/vodsearch/-------------.html?wd=' + wd + '&page=' + pg,
            self.host + '/index.php/vodsearch/-------------.html?wd=' + wd + '&page=' + pg,
            self.host + '/search.html?wd=' + wd + '&page=' + pg,
        ]

        videos = []
        for url in urls:
            html = self._txt(url, timeout=30)
            if html and len(html) > 500:
                videos = self._parse_list(html)
                if videos:
                    break

        return {'list': videos}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 播放解析 ==========
    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {'parse': 1, 'playUrl': '', 'url': ''}

        url = id if str(id).startswith('http') else self._url(id)

        # 如果已经是直链媒体
        if self._is_direct_media(url):
            if '.m3u8' in url.lower():
                url = self._resolve_m3u8_child(url)
            return {
                'parse': 0,
                'playUrl': '',
                'url': url,
                'header': {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': self.host + '/',
                },
                'format': 'application/x-mpegURL' if '.m3u8' in url.lower() else '',
                'contentType': 'application/x-mpegURL' if '.m3u8' in url.lower() else '',
            }

        # 获取播放页HTML
        html = self._txt(url, referer=self.host + '/', timeout=30)
        if not html:
            return {'parse': 1, 'playUrl': '', 'url': url}

        real = ''

        # 1. player_aaaa JSON (苹果CMS标准)
        m = re.search(r'var\s+player_[a-zA-Z0-9_]+\s*=\s*(\{.*?\})\s*</script>', html, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                real = data.get('url', '') or ''
                encrypt = data.get('encrypt', 0)
                if encrypt == 1 and real:
                    try:
                        real = unquote(real)
                    except Exception:
                        pass
                elif encrypt == 2 and real:
                    try:
                        real = unquote(base64.b64decode(real).decode('utf-8'))
                    except Exception:
                        pass
            except Exception:
                real = self._match(r'"url"\s*:\s*"([^"]+)"', m.group(1))

        # 2. 其他 player 变量
        if not real:
            m2 = re.search(r'var\s+player\s*=\s*["\']([^"\']+)["\']', html, re.S)
            if m2:
                real = m2.group(1)
                if real.startswith('//'):
                    real = 'https:' + real

        # 3. iframe 嵌套
        if not real:
            iframe = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.S)
            if iframe:
                iframe_url = self._url(iframe.group(1))
                iframe_html = self._txt(iframe_url, referer=url, timeout=30)
                if iframe_html:
                    real = self._match(r'"url"\s*:\s*"([^"]+)"', iframe_html)
                    if not real:
                        real = self._match(
                            r'["\'](https?://[^"\']+\.(?:m3u8|mp4)[^"\']*)["\']',
                            iframe_html, re.I
                        )

        # 4. 全局匹配 m3u8/mp4
        if not real:
            for pat in [
                r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']',
                r'["\'](https?://[^"\']+\.mp4[^"\']*)["\']',
                r'data-(?:url|src)=["\']([^"\']+)["\']',
                r'<video[^>]+src=["\']([^"\']+)["\']',
            ]:
                m3 = re.search(pat, html, re.I)
                if m3:
                    real = m3.group(1)
                    break

        if real:
            real = real.replace('\\/', '/')
            if real.startswith('//'):
                real = 'https:' + real

            if '.m3u8' in real.lower():
                real = self._resolve_m3u8_child(real, referer=url)

            return {
                'parse': 0 if self._is_direct_media(real) else 1,
                'playUrl': '',
                'url': real,
                'header': {
                    'User-Agent': self.header['User-Agent'],
                    'Referer': url,
                },
                'format': 'application/x-mpegURL' if '.m3u8' in real.lower() else '',
                'contentType': 'application/x-mpegURL' if '.m3u8' in real.lower() else '',
            }

        # 没找到，交给壳子嗅探
        return {
            'parse': 1,
            'playUrl': '',
            'url': url,
            'header': {
                'User-Agent': self.header['User-Agent'],
                'Referer': url,
            },
        }

    # ========== m3u8 子解析 ==========
    def _resolve_m3u8_child(self, m3u8_url, referer=''):
        """解析master m3u8到子m3u8，提升Exo兼容性"""
        if not m3u8_url or '.m3u8' not in m3u8_url.lower():
            return m3u8_url
        try:
            text = self._txt(m3u8_url, referer=referer or self.host + '/', timeout=15)
            if not text or '#EXTM3U' not in text:
                return m3u8_url
            lines = [x.strip() for x in text.splitlines() if x.strip()]
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    for nxt in lines[i + 1:]:
                        if nxt and not nxt.startswith('#'):
                            return urljoin(m3u8_url, nxt)
            return m3u8_url
        except Exception:
            return m3u8_url

    # ========== 本地代理 ==========
    def localProxy(self, param):
        try:
            import urllib.parse as up
            raw_url = ''
            referer = self.host + '/'
            if isinstance(param, dict):
                raw_url = param.get('url', '') or param.get('u', '')
                referer = param.get('referer', '') or param.get('ref', '') or referer
            elif isinstance(param, str):
                qs = up.parse_qs(param)
                raw_url = qs.get('url', [''])[0] or qs.get('u', [''])[0]
                referer = qs.get('referer', [''])[0] or qs.get('ref', [''])[0] or referer

            media_url = unquote(raw_url) if raw_url else ''
            referer = unquote(referer) if referer else self.host + '/'

            if not media_url:
                return [404, 'text/plain', b'']

            headers = {
                'User-Agent': self.header['User-Agent'],
                'Referer': referer,
            }

            rsp = self.fetch(media_url, headers=headers, timeout=30)
            content = rsp.content if hasattr(rsp, 'content') else rsp.text.encode('utf-8')
            ctype = ''
            if hasattr(rsp, 'headers'):
                ctype = rsp.headers.get('Content-Type', '') or ''

            # m3u8 内容处理
            text = ''
            try:
                text = content.decode('utf-8')
            except Exception:
                text = ''
            if '#EXTM3U' in text:
                out = []
                for line in text.splitlines():
                    s = line.strip()
                    if not s or s.startswith('#'):
                        out.append(line)
                    else:
                        abs_url = urljoin(media_url, s)
                        out.append(abs_url)
                data = '\n'.join(out).encode('utf-8')
                return [200, 'application/x-mpegURL', data]

            return [200, ctype or 'application/octet-stream', content]
        except Exception:
            return [500, 'text/plain', b'proxy error']

    # ========== 可选接口 ==========
    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|avi)(\?|$)', url or '', re.I))

    def manualVideoCheck(self):
        return True

    # ========== 清理 ==========
    def destroy(self):
        pass

    def close(self):
        self.destroy()


if __name__ == '__main__':
    spider = Spider()
    spider.init()
    # === 测试开关 ===
    # 首页
    print(json.dumps(spider.homeContent(True), ensure_ascii=False, indent=2)[:2000])
    # 分类
    # print(json.dumps(spider.categoryContent('1', '1', None, {}), ensure_ascii=False, indent=2)[:2000])
    # 搜索
    # print(json.dumps(spider.searchContent('狂飙', False), ensure_ascii=False, indent=2)[:2000])
    # 详情
    # print(json.dumps(spider.detailContent('73302'), ensure_ascii=False, indent=2)[:3000])
    # 播放
    # print(json.dumps(spider.playerContent('', 'https://www.dushe02.com/vodplay/73302-1-1.html', ''), ensure_ascii=False, indent=2))
