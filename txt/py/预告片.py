# -*- coding: utf-8 -*-
"""
预告片世界 (https://www.6huo.com) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.6huo.com
特点: 电影预告片聚合站, ckplayer播放, mp4直链无需解密
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


# ==================== 常量 ====================
SITE_URL = "https://www.6huo.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 30

# 首页分类
CLASSES = [
    {"type_id": "allmovies", "type_name": "全部电影"},
    {"type_id": "later", "type_name": "即将上映"},
    {"type_id": "nowplaying", "type_name": "正在热映"},
    {"type_id": "hd", "type_name": "高清预告"},
    {"type_id": "netdisk", "type_name": "素材网盘"},
]

# 地区筛选
_AREA_VALUES = [
    {"n": "全部", "v": ""},
    {"n": "美国", "v": "美国"},
    {"n": "中国大陆", "v": "中国大陆"},
    {"n": "中国香港", "v": "中国香港"},
    {"n": "中国台湾", "v": "中国台湾"},
    {"n": "日本", "v": "日本"},
    {"n": "韩国", "v": "韩国"},
    {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"},
    {"n": "德国", "v": "德国"},
    {"n": "印度", "v": "印度"},
    {"n": "其他", "v": "其他"},
]

FILTERS = {
    "allmovies": [
        {"key": "area", "name": "地区", "value": _AREA_VALUES},
    ],
}


class Spider(Spider):
    """预告片世界 Spider — 预告片聚合站"""

    def getName(self):
        return "预告片世界"

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
        video_formats = ['.mp4', '.m3u8', '.ts', '.mkv', '.avi', '.webm', '.flv']
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
            rsp = self._request(f'{SITE_URL}/allmovies')
            if rsp and rsp.status_code == 200:
                html = rsp.text
                videos = self._parse_list(html)
                return {'list': videos[:72]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, 'allmovies')
        page = self._safe_page(pg, 1)
        extend = extend or {}

        area = self._safe_str(extend.get('area', ''))

        # 构建URL
        if area:
            # 地区分类: /country/美国?page=2
            area_encoded = urllib.parse.quote(area)
            url = f'{SITE_URL}/country/{area_encoded}'
            if page > 1:
                url += f'?page={page}'
        else:
            # 普通分类: /allmovies?page=2
            url = f'{SITE_URL}/{tid}'
            if page > 1:
                url += f'?page={page}'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

            html = rsp.text
            videos = self._parse_list(html)

            # 解析页数
            pagecount = page + 1 if len(videos) >= 10 else page

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

        key_encoded = urllib.parse.quote(keyword)
        url = f'{SITE_URL}/?keyword={key_encoded}&view=search'

        if page > 1:
            url += f'&page={page}'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': PAGE_SIZE, 'total': 0}

            html = rsp.text
            # 搜索页包含热搜榜(topsearch)和搜索结果两部分
            # 只提取搜索结果区域 (<h1>搜索电影:xxx</h1> 之后的内容)
            search_m = re.search(r'<h1[^>]*>\s*搜索电影:', html)
            if search_m:
                html = html[search_m.start():]
            videos = self._parse_list(html)

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
        url = f'{SITE_URL}/movie/{vod_id}'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}
            html = rsp.text
        except Exception:
            return {'list': []}

        vod = {'vod_id': vod_id}

        # 标题
        h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if h1_m:
            vod['vod_name'] = re.sub(r'<[^>]+>', '', h1_m.group(1)).strip()
        else:
            title_m = re.search(r'<title>([^<]+)</title>', html)
            vod['vod_name'] = title_m.group(1).split('-')[0].strip() if title_m else ""

        # 图片 — 优先匹配 movie/{id}/poster 中的海报
        pic_m = re.search(rf'href="/movie/{vod_id}/poster[^"]*"[^>]*>\s*<img[^>]*src="([^"]+)"', html)
        if not pic_m:
            # 备用: 匹配 alt 含"海报"的图片
            pic_m = re.search(r'<img[^>]*src="([^"]+)"[^>]*alt="[^"]*海报"', html)
        if not pic_m:
            # 备用: 匹配 /files/mpic/ 中含该ID的图片
            pic_m = re.search(rf'<img[^>]*src="([^"]*p{vod_id}\.jpg[^"]*)"', html)
        if pic_m:
            vod['vod_pic'] = self._fix_url(SITE_URL, pic_m.group(1))

        # 类型 — 从信息表格提取
        type_m = re.search(r'<td>类型</td>\s*<td>\s*<a[^>]*>([^<]+)</a>', html)
        if not type_m:
            type_m = re.search(r'类型[：:]\s*</span>\s*<a[^>]*>([^<]+)</a>', html)
        if type_m:
            vod['type_name'] = type_m.group(1).strip()

        # 年份 — 从上映信息提取
        year_m = re.search(r'<td>上映</td>\s*<td>\s*(\d{4})', html)
        if not year_m:
            year_m = re.search(r'(\d{4})', html[:5000])
        if year_m:
            vod['vod_year'] = year_m.group(1)

        # 地区 — 从信息表格提取
        area_m = re.search(r'<td>国家/地区</td>\s*<td>\s*<a[^>]*href="/country/([^"]+)"', html)
        if not area_m:
            area_m = re.search(r'类型[：:]\s*</span>\s*<a[^>]*href="/country/([^"]+)"', html)
        if area_m:
            vod['vod_area'] = urllib.parse.unquote(area_m.group(1))

        # 简介
        desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html)
        if desc_m:
            vod['vod_content'] = desc_m.group(1)

        # 导演 — 从信息表格提取
        director_m = re.search(r'<td>导演</td>\s*<td>(.*?)</td>', html, re.S)
        if director_m:
            directors = re.findall(r'>([^<]+)</a>', director_m.group(1))
            vod['vod_director'] = " / ".join([d.strip() for d in directors if d.strip()])

        # 主演 — 从信息表格提取
        actor_m = re.search(r'<td>主演</td>\s*<td>(.*?)</td>', html, re.S)
        if actor_m:
            actors = re.findall(r'>([^<]+)</a>', actor_m.group(1))
            vod['vod_actor'] = " / ".join([a.strip() for a in actors if a.strip()])

        # 预告片列表 (播放源)
        trailers = re.findall(
            r'<a[^>]*href="/show/(\d+)"[^>]*class="tlist-bbs-tdtitle"[^>]*>(.*?)</a>'
            r'.*?<span class="tlist-bbs-addtime">([^<]*)</span>',
            html, re.S
        )

        if not trailers:
            # 备用: 只取show链接
            trailers_raw = re.findall(
                r'<a[^>]*href="/show/(\d+)"[^>]*>(.*?)</a>', html, re.S
            )
            trailers = [(tid, name, '') for tid, name in trailers_raw]

        ep_list = []
        for show_id, title, duration in trailers:
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            if duration:
                title_clean = f"{title_clean} [{duration.strip()}]"
            if not title_clean:
                title_clean = f"预告片{len(ep_list)+1}"
            ep_list.append(f"{title_clean}${show_id}")

        if ep_list:
            vod['vod_play_from'] = "预告片"
            vod['vod_play_url'] = "#".join(ep_list)
        else:
            # 无预告片的影片, 提供提示
            vod['vod_play_from'] = "暂无预告片"
            vod['vod_play_url'] = ""

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        show_id = str(id).strip()
        if not show_id:
            return {'parse': 0, 'url': '', 'header': {}}

        url = f'{SITE_URL}/show/{show_id}'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'parse': 0, 'url': '', 'header': {}}

            html = rsp.text
        except Exception:
            return {'parse': 0, 'url': '', 'header': {}}

        # 提取 videoObject 中的 video URL
        # 格式: video: 'https://...mp4' 或 video: "https://...mp4"
        play_url = ""

        # 主匹配: videoObject.video 字段
        video_m = re.search(r"video\s*:\s*['\"](https?://[^'\"]+)['\"]", html)
        if video_m:
            play_url = video_m.group(1)

        # 备用: 找所有mp4链接
        if not play_url:
            mp4_m = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html)
            if mp4_m:
                play_url = mp4_m.group(1)

        # 备用: m3u8
        if not play_url:
            m3u8_m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m3u8_m:
                play_url = m3u8_m.group(1)

        header = {
            'User-Agent': UA,
        }

        # 根据视频域名设置Referer (部分CDN有防盗链)
        if play_url:
            # mtime.cn 禁止来自6huo.com的Referer, 用mtime.cn或空Referer
            if 'mtime.cn' in play_url:
                header['Referer'] = 'https://www.mtime.cn/'
            # pipi.cn 允许6huo.com, 但也兼容空Referer
            elif 'pipi.cn' in play_url or 'p0.pipi.cn' in play_url:
                header['Referer'] = SITE_URL + '/'
            else:
                header['Referer'] = SITE_URL + '/'

            return {
                'parse': 0,
                'url': play_url,
                'header': header,
            }

        return {'parse': 0, 'url': '', 'header': {}}

    # ========== 列表解析 ==========

    def _parse_list(self, html):
        """解析列表页视频条目"""
        videos = []

        # 主解析: <li data-index="N"><a href="/movie/ID">...</a></li>
        pattern = re.compile(
            r'<li[^>]*data-index="\d+"[^>]*>\s*'
            r'<a[^>]*href="/movie/(\d+)"[^>]*>(.*?)</a>\s*</li>',
            re.S
        )

        matches = pattern.findall(html)
        seen = set()
        for vid, content in matches:
            if vid in seen:
                continue
            seen.add(vid)

            # 标题
            title_m = re.search(r'(?:title|alt)="([^"]*)"', content)
            title = title_m.group(1) if title_m else ""

            # 图片
            img_m = re.search(r'src="([^"]+)"', content)
            pic = img_m.group(1) if img_m else ""
            pic = self._fix_url(SITE_URL, pic)

            # 时间/备注
            time_m = re.search(r'item-pubtime"[^>]*title="([^"]*)"', content)
            if not time_m:
                time_m = re.search(r'item-pubtime"[^>]*>([^<]*)</span>', content)
            remarks = time_m.group(1).strip() if time_m else ""

            # 如果有时间标签但无title, 用文本内容
            if not title:
                title_m2 = re.search(r'item-title"[^>]*>([^<]*)</span>', content)
                title = title_m2.group(1).strip() if title_m2 else f"电影{vid}"

            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })

        # 备用解析: 直接找 movie 链接
        if not videos:
            items = re.findall(
                r'<a[^>]*href="/movie/(\d+)"[^>]*>(.*?)</a>',
                html, re.S
            )
            for vid, content in items:
                if vid in seen:
                    continue
                seen.add(vid)

                title_m = re.search(r'(?:title|alt)="([^"]*)"', content)
                title = title_m.group(1) if title_m else ""

                img_m = re.search(r'src="([^"]+)"', content)
                pic = img_m.group(1) if img_m else ""
                pic = self._fix_url(SITE_URL, pic)

                if not title:
                    title_m2 = re.search(r'item-title"[^>]*>([^<]*)</span>', content)
                    title = title_m2.group(1).strip() if title_m2 else f"电影{vid}"

                time_m = re.search(r'item-pubtime"[^>]*title="([^"]*)"', content)
                remarks = time_m.group(1).strip() if time_m else ""

                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': remarks,
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
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')} | {v.get('vod_pic', '')[:50]}")

    print("\n=== 分类(全部电影) ===")
    cat = spider.categoryContent("allmovies", "1", True, {})
    print(f"视频数: {len(cat['list'])}, 页数: {cat.get('page')}/{cat.get('pagecount')}")
    for v in cat["list"][:3]:
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')}")

    print("\n=== 分类(即将上映) ===")
    cat2 = spider.categoryContent("later", "1", True, {})
    print(f"视频数: {len(cat2['list'])}")
    for v in cat2["list"][:3]:
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')}")

    print("\n=== 搜索(变形金刚) ===")
    search = spider.searchContent("变形金刚", False)
    print(f"结果数: {len(search['list'])}")
    for v in search["list"][:5]:
        print(f"  - {v['vod_name']} (id: {v['vod_id']})")

    print("\n=== 详情(小黄人) ===")
    detail = spider.detailContent(["85495"])
    if detail["list"]:
        vod = detail["list"][0]
        print(f"标题: {vod.get('vod_name', '')}")
        print(f"图片: {vod.get('vod_pic', '')}")
        print(f"类型: {vod.get('type_name', '')}")
        print(f"地区: {vod.get('vod_area', '')}")
        print(f"导演: {vod.get('vod_director', '')}")
        print(f"播放线路: {vod.get('vod_play_from', '')}")
        play_urls = vod.get("vod_play_url", "").split("#")
        print(f"预告片数: {len(play_urls) if play_urls[0] else 0}")
        for ep in play_urls[:3]:
            print(f"  - {ep[:80]}")

        # 测试播放
        print("\n=== 播放解析 ===")
        if play_urls and play_urls[0]:
            first_ep = play_urls[0]
            parts = first_ep.split("$")
            if len(parts) >= 2:
                ep_name, ep_id = parts[0], parts[1]
                print(f"选集: {ep_name[:40]}, ID: {ep_id}")
                play = spider.playerContent("", ep_id, [])
                print(f"播放URL: {play.get('url', '')[:100]}")
                print(f"Referer: {play.get('header', {}).get('Referer', '')}")
                print(f"parse: {play.get('parse', '')}")
