# -*- coding: utf-8 -*-
"""
南瓜影视 (https://www.nanguays.net) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.nanguays.net
采集: MacCMS HTML + player_aaaa m3u8 直链
版本: 1.0.0
"""
import sys
import re
import json
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
SITE_URL = "https://www.nanguays.net"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 首页分类 — MacCMS type_id
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "21", "type_name": "短剧"},
    {"type_id": "22", "type_name": "AI漫剧"},
]

# 排序筛选器
_SORT_VALUES = [
    {"n": "按时间", "v": "time"},
    {"n": "按人气", "v": "hits"},
    {"n": "按评分", "v": "score"},
    {"n": "按更新", "v": "up"},
]

_YEAR_VALUES = [
    {"n": "全部", "v": ""},
    {"n": "2026", "v": "2026"},
    {"n": "2025", "v": "2025"},
    {"n": "2024", "v": "2024"},
    {"n": "2023", "v": "2023"},
    {"n": "2022", "v": "2022"},
    {"n": "2021", "v": "2021"},
    {"n": "2020", "v": "2020"},
    {"n": "2019", "v": "2019"},
    {"n": "2018", "v": "2018"},
    {"n": "2017", "v": "2017"},
    {"n": "2016", "v": "2016"},
    {"n": "2015", "v": "2015"},
    {"n": "2014", "v": "2014"},
    {"n": "2013", "v": "2013"},
    {"n": "2012", "v": "2012"},
    {"n": "2011", "v": "2011"},
    {"n": "2010", "v": "2010"},
]

_AREA_VALUES = [
    {"n": "全部", "v": ""},
    {"n": "中国大陆", "v": "中国大陆"},
    {"n": "中国香港", "v": "中国香港"},
    {"n": "中国台湾", "v": "中国台湾"},
    {"n": "美国", "v": "美国"},
    {"n": "韩国", "v": "韩国"},
    {"n": "日本", "v": "日本"},
    {"n": "泰国", "v": "泰国"},
    {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"},
    {"n": "德国", "v": "德国"},
    {"n": "印度", "v": "印度"},
    {"n": "其它", "v": "其它"},
]


def _make_filters(tid):
    return [
        {"key": "by", "name": "排序", "value": _SORT_VALUES},
        {"key": "year", "name": "年份", "value": _YEAR_VALUES},
        {"key": "area", "name": "地区", "value": _AREA_VALUES},
    ]


FILTERS = {c["type_id"]: _make_filters(c["type_id"]) for c in CLASSES}


class Spider(Spider):
    """南瓜影视 Spider — MacCMS HTML 采集 + player_aaaa m3u8 直链"""

    def getName(self):
        return "南瓜影视"

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
        if url.startswith('/'):
            return SITE_URL + url
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
            rsp = self._request(f'{SITE_URL}/')
            if rsp and rsp.status_code == 200:
                videos = self._parse_list(rsp.text)
                return {'list': videos[:72]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, '1')
        page = self._safe_page(pg, 1)
        extend = extend or {}
        by = self._safe_str(extend.get('by', ''))
        year = self._safe_str(extend.get('year', ''))
        area = self._safe_str(extend.get('area', ''))

        # MacCMS 筛选页: /index.php/vod/show/id/{tid}/by/{by}/year/{year}/area/{area}/page/{page}.html
        path_parts = [f'/index.php/vod/show/id/{tid}']
        if by:
            path_parts.append(f'by/{by}')
        if year:
            path_parts.append(f'year/{year}')
        if area:
            path_parts.append(f'area/{urllib.parse.quote(area)}')
        path_parts.append(f'page/{page}.html')
        url = SITE_URL + '/'.join(path_parts)

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 40, 'total': 0}

            html = rsp.text
            videos = self._parse_list(html)

            # 解析总页数
            pagecount = page
            page_matches = re.findall(r'/vod/show/id/\d+/[^"]*page/(\d+)\.html', html)
            if page_matches:
                pagecount = max(page, max(int(p) for p in page_matches))

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': 40,
                'total': 999999,
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 40, 'total': 0}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 40, 'total': 0}

        key_encoded = urllib.parse.quote(keyword)
        url = f'{SITE_URL}/index.php/vod/search/page/{page}/wd/{key_encoded}.html'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 40, 'total': 0}

            videos = self._parse_list(rsp.text)

            pagecount = page
            page_matches = re.findall(r'/vod/search/page/(\d+)/wd/', rsp.text)
            if page_matches:
                pagecount = max(page, max(int(p) for p in page_matches))

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': 40,
                'total': len(videos),
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 40, 'total': 0}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])
        url = f'{SITE_URL}/index.php/vod/detail/id/{vod_id}.html'

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}
            html = rsp.text
        except Exception:
            return {'list': []}

        vod = {'vod_id': vod_id}

        # 标题
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        vod['vod_name'] = self._decode_entities(re.sub(r'<[^>]+>', '', title_match.group(1)).strip()) if title_match else ""

        # 封面
        pic_match = re.search(r'data-original="([^"]*)"[^>]*alt="' + re.escape(vod['vod_name']) + '"', html)
        if not pic_match:
            pic_match = re.search(r'module-item-pic[^>]*>.*?data-original="([^"]*)"', html, re.S)
        vod['vod_pic'] = self._fix_url(pic_match.group(1)) if pic_match else ""

        # 信息标签 — module-info-tag-link
        tag_links = re.findall(r'module-info-tag-link[^"]*"[^>]*>\s*<a[^>]*>(.*?)</a>', html, re.S)
        tag_texts = [self._decode_entities(re.sub(r'<[^>]+>', '', t).strip()) for t in tag_links]
        tag_texts = [t for t in tag_texts if t]

        # 类型名
        vod['type_name'] = tag_texts[2] if len(tag_texts) > 2 else ""

        # 年份
        vod['vod_year'] = tag_texts[0] if tag_texts else ""

        # 地区
        vod['vod_area'] = tag_texts[1] if len(tag_texts) > 1 else ""

        # 演员/导演 — 从 vod_data 或 info-item 中获取
        actor_match = re.search(r'vod_actor["\s:]+([^"<]+)', html)
        vod['vod_actor'] = self._safe_str(actor_match.group(1).strip()) if actor_match else ""
        director_match = re.search(r'vod_director["\s:]+([^"<]+)', html)
        vod['vod_director'] = self._safe_str(director_match.group(1).strip()) if director_match else ""

        # 简介
        desc_match = re.search(r'module-info-introduction-content[^"]*"[^>]*>(.*?)</div>', html, re.S)
        if desc_match:
            desc_raw = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
            vod['vod_content'] = self._decode_entities(desc_raw)
        else:
            vod['vod_content'] = ""

        # ===== 播放列表 =====
        # 线路名称
        line_names = re.findall(r'data-dropdown-value="([^"]*)"', html)

        # 选集 — 按 panel 分组
        # 结构: id="panel0" → 线路一选集, id="panel1" → 线路二选集
        panels = re.findall(r'id="panel(\d+)"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.S)

        play_from_list = []
        play_url_list = []

        if panels:
            for panel_id, panel_html in panels:
                idx = int(panel_id)
                line_name = line_names[idx] if idx < len(line_names) else f"线路{idx + 1}"

                eps = re.findall(
                    r'<a[^>]*class="module-play-list-link"[^>]*href="(/index\.php/vod/play/id/\d+/sid/(\d+)/nid/(\d+)\.html)"[^>]*>.*?<span>(.*?)</span>',
                    panel_html, re.S
                )

                if eps:
                    ep_list = []
                    for href, sid, nid, label in eps:
                        play_key = f"{vod_id}|{sid}|{nid}"
                        ep_list.append(f"{label}${play_key}")

                    play_from_list.append(line_name)
                    play_url_list.append("#".join(ep_list))
        else:
            # 备用：直接找所有 module-play-list-link
            all_eps = re.findall(
                r'<a[^>]*class="module-play-list-link"[^>]*href="(/index\.php/vod/play/id/\d+/sid/(\d+)/nid/(\d+)\.html)"[^>]*>.*?<span>(.*?)</span>',
                html, re.S
            )
            if all_eps:
                # 按 sid 分组
                from collections import defaultdict
                groups = defaultdict(list)
                sids_order = []
                for href, sid, nid, label in all_eps:
                    if sid not in groups:
                        sids_order.append(sid)
                    groups[sid].append(f"{label}${vod_id}|{sid}|{nid}")

                for sid in sids_order:
                    line_idx = sids_order.index(sid)
                    line_name = line_names[line_idx] if line_idx < len(line_names) else f"线路{line_idx + 1}"
                    play_from_list.append(line_name)
                    play_url_list.append("#".join(groups[sid]))

        vod['vod_play_from'] = "$$$".join(play_from_list)
        vod['vod_play_url'] = "$$$".join(play_url_list)

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        """
        MacCMS 标准解析：请求播放页 → 提取 player_aaaa → 返回 m3u8 直链
        """
        # 解析播放 ID: vod_id|sid|nid
        parts = str(id).split("|")
        if len(parts) < 3:
            return {'parse': 0, 'url': '', 'header': {}}

        vod_id = parts[0]
        sid = parts[1]
        nid = parts[2]

        # 请求播放页
        play_url = f'{SITE_URL}/index.php/vod/play/id/{vod_id}/sid/{sid}/nid/{nid}.html'

        try:
            rsp = self._request(play_url, referer=f'{SITE_URL}/index.php/vod/detail/id/{vod_id}.html')
            if not rsp or rsp.status_code != 200:
                return {'parse': 1, 'url': play_url, 'header': {}}

            html = rsp.text

            # 提取 player_aaaa
            player_match = re.search(r'var player_aaaa\s*=\s*(\{.*?\})\s*</script>', html, re.S)
            if player_match:
                player_data = json.loads(player_match.group(1))
                video_url = player_data.get('url', '')
                encrypt = player_data.get('encrypt', 0)

                if video_url and encrypt == 0:
                    # 直链模式 — m3u8 无需 Referer
                    return {
                        'parse': 0,
                        'url': video_url,
                        'header': {
                            'User-Agent': UA,
                        },
                    }
                elif video_url and encrypt > 0:
                    # 加密模式 — 降级嗅探
                    return {
                        'parse': 1,
                        'url': play_url,
                        'header': {
                            'User-Agent': UA,
                            'Referer': SITE_URL + '/',
                        },
                    }

            # 未找到 player_aaaa — 降级嗅探
            return {
                'parse': 1,
                'url': play_url,
                'header': {
                    'User-Agent': UA,
                    'Referer': SITE_URL + '/',
                },
            }
        except Exception:
            return {'parse': 1, 'url': play_url, 'header': {}}

    # ========== 列表解析 ==========

    def _parse_list(self, html):
        """解析列表页 — MacCMS module-poster-item 结构"""
        videos = []

        # 主解析: module-poster-item（分类/首页列表）
        pattern = re.compile(
            r'<a\s+href="(/index\.php/vod/detail/id/(\d+)\.html)"\s+title="([^"]*)"\s+class="module-poster-item\s+module-item"[^>]*>'
            r'.*?data-original="([^"]*)"'
            r'.*?module-item-note"[^>]*>(.*?)</div>',
            re.S
        )

        matches = pattern.findall(html)
        seen = set()
        for href, vid_id, title, thumb, note in matches:
            if vid_id in seen:
                continue
            seen.add(vid_id)

            note_clean = re.sub(r'<[^>]+>', '', note).strip()
            videos.append({
                'vod_id': vid_id,
                'vod_name': self._decode_entities(title.strip()),
                'vod_pic': self._fix_url(thumb),
                'vod_remarks': note_clean,
            })

        # 搜索结果: module-card-item 结构
        if not videos:
            card_pattern = re.compile(
                r'<a\s+href="(/index\.php/vod/detail/id/(\d+)\.html)"\s+class="module-card-item-poster"[^>]*>'
                r'.*?data-original="([^"]*)"'
                r'.*?module-item-note"[^>]*>(.*?)</div>'
                r'.*?<strong>(.*?)</strong>',
                re.S
            )
            for href, vid_id, thumb, note, title in card_pattern.findall(html):
                if vid_id in seen:
                    continue
                seen.add(vid_id)
                note_clean = re.sub(r'<[^>]+>', '', note).strip()
                videos.append({
                    'vod_id': vid_id,
                    'vod_name': self._decode_entities(title.strip()),
                    'vod_pic': self._fix_url(thumb),
                    'vod_remarks': note_clean,
                })

        # 备用解析：更宽松的匹配
        if not videos:
            pattern2 = re.compile(
                r'href="(/index\.php/vod/detail/id/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*>.*?data-original="([^"]*)"',
                re.S
            )
            for href, vid_id, title, thumb in pattern2.findall(html):
                if vid_id in seen:
                    continue
                seen.add(vid_id)
                videos.append({
                    'vod_id': vid_id,
                    'vod_name': self._decode_entities(title.strip()),
                    'vod_pic': self._fix_url(thumb),
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
        print(f"  - {v['vod_name']} | id: {v['vod_id']} | 备注: {v['vod_remarks']}")

    print("\n=== 分类(电影) ===")
    cat = spider.categoryContent("1", "1", True, {})
    print(f"视频数: {len(cat['list'])}, 页数: {cat.get('page')}/{cat.get('pagecount')}")
    for v in cat["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']} | 备注: {v['vod_remarks']}")

    print("\n=== 分类(电影) 第2页 ===")
    cat2 = spider.categoryContent("1", "2", True, {})
    print(f"视频数: {len(cat2['list'])}, 页数: {cat2.get('page')}/{cat2.get('pagecount')}")
    for v in cat2["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']}")

    print("\n=== 分类(电影) 筛选:2025+美国 ===")
    cat3 = spider.categoryContent("1", "1", True, {"year": "2025", "area": "美国"})
    print(f"视频数: {len(cat3['list'])}, 页数: {cat3.get('page')}/{cat3.get('pagecount')}")
    for v in cat3["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']} | 备注: {v['vod_remarks']}")

    print("\n=== 搜索(变形金刚) ===")
    search = spider.searchContent("变形金刚", False)
    print(f"结果数: {len(search['list'])}")
    for v in search["list"][:5]:
        print(f"  - {v['vod_name']} (id: {v['vod_id']})")

    print("\n=== 详情(电影 冬歇) ===")
    detail = spider.detailContent(["9280"])
    if detail["list"]:
        vod = detail["list"][0]
        print(f"标题: {vod.get('vod_name', '')}")
        print(f"类型: {vod.get('type_name', '')}")
        print(f"年份: {vod.get('vod_year', '')}")
        print(f"地区: {vod.get('vod_area', '')}")
        print(f"演员: {vod.get('vod_actor', '')}")
        print(f"简介: {vod.get('vod_content', '')[:100]}...")
        print(f"播放线路: {vod.get('vod_play_from', '')}")
        play_url_raw = vod.get('vod_play_url', '')
        eps = play_url_raw.split("#") if play_url_raw else []
        print(f"集数: {len(eps)}")
        for ep in eps[:3]:
            ep_parts = ep.split("$")
            if len(ep_parts) >= 2:
                print(f"  - {ep_parts[0]} | id: {ep_parts[1]}")

        print("\n=== 播放解析(电影) ===")
        if eps:
            first_ep = eps[0]
            ep_parts = first_ep.split("$")
            if len(ep_parts) >= 2:
                play = spider.playerContent("", ep_parts[1], [])
                print(f"播放URL: {play.get('url', '')}")
                print(f"parse: {play.get('parse', '')}")
                print(f"header: {play.get('header', {})}")

    print("\n=== 详情(电视剧 爱从发球开始) ===")
    detail2 = spider.detailContent(["165069"])
    if detail2["list"]:
        vod2 = detail2["list"][0]
        print(f"标题: {vod2.get('vod_name', '')}")
        print(f"播放线路: {vod2.get('vod_play_from', '')}")
        play_url_raw2 = vod2.get('vod_play_url', '')
        lines = play_url_raw2.split("$$$") if play_url_raw2 else []
        for li, line_urls in enumerate(lines):
            eps2 = line_urls.split("#") if line_urls else []
            print(f"  线路{li+1}: {len(eps2)} 集")
            for ep in eps2[:3]:
                ep_parts = ep.split("$")
                if len(ep_parts) >= 2:
                    print(f"    - {ep_parts[0]} | id: {ep_parts[1]}")

            print(f"\n=== 播放解析(电视剧 线路{li+1}) ===")
            if eps2:
                first_ep2 = eps2[0]
                ep_parts2 = first_ep2.split("$")
                if len(ep_parts2) >= 2:
                    play2 = spider.playerContent("", ep_parts2[1], [])
                    print(f"播放URL: {play2.get('url', '')}")
                    print(f"parse: {play2.get('parse', '')}")
