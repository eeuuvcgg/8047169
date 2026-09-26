# -*- coding: utf-8 -*-
"""
星河影视 (https://www.xhkan.top) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.xhkan.top
采集: Next.js API (filter/search) + RSC allepidetail + player/resolve m3u8
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
            if isinstance(data, dict):
                r = rq.post(url, json=data, headers=headers, timeout=15, **kw)
            else:
                r = rq.post(url, data=data, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


# ==================== 常量 ====================
SITE_URL = "https://www.xhkan.top"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 首页分类 — catId
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
]

# 排序筛选器
_SORT_VALUES = [
    {"n": "最新", "v": "ranklatest"},
    {"n": "最热", "v": "rankhot"},
    {"n": "评分", "v": "rankscore"},
]

_FILTERS_TEMPLATE = [{"key": "sort", "name": "排序", "value": _SORT_VALUES}]
FILTERS = {c["type_id"]: _FILTERS_TEMPLATE for c in CLASSES}

# 播放源名称映射
SOURCE_NAMES = {
    'qiyi': '爱奇艺', 'imgo': '芒果TV', 'youku': '优酷',
    'qq': '腾讯视频', 'leshi': '乐视', 'douyin': '抖音',
    'xigua': '西瓜视频', 'bf': 'B线路云播',
}


class Spider(Spider):
    """星河影视 Spider — Next.js API 采集 + player/resolve m3u8"""

    def getName(self):
        return "星河影视"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.siteUrl = SITE_URL
        self.headers = {
            'User-Agent': UA,
            'Referer': SITE_URL + '/',
            'Accept': 'application/json, text/plain, */*',
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

    def _request(self, url, referer=None, headers=None):
        h = headers or dict(self.headers)
        if referer:
            h['Referer'] = referer
        try:
            rsp = self.fetch(url, headers=h, timeout=15)
            return rsp
        except Exception:
            return None

    def _post_json(self, url, data, referer=None):
        h = dict(self.headers)
        h['Content-Type'] = 'application/json'
        h['x-player-request'] = '1'
        if referer:
            h['Referer'] = referer
        try:
            rsp = self.post(url, data=data, headers=h, timeout=15)
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
    def _clean_html(text):
        if not text:
            return ''
        return re.sub(r'<[^>]+>', '', text).strip()

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        result['class'] = list(CLASSES)
        if filter:
            result['filters'] = dict(FILTERS)
        return result

    def homeVideoContent(self):
        try:
            url = f'{SITE_URL}/api/filter?catId=1&sort=ranklatest&page=1&size=24'
            rsp = self._request(url)
            if rsp and rsp.status_code == 200:
                data = rsp.json()
                movies = data.get('movies', [])
                videos = [self._parse_movie(m) for m in movies]
                return {'list': videos[:72]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, '1')
        page = self._safe_page(pg, 1)
        extend = extend or {}
        sort = self._safe_str(extend.get('sort', 'ranklatest')) or 'ranklatest'

        url = f'{SITE_URL}/api/filter?catId={tid}&sort={sort}&page={page}&size=24'

        try:
            rsp = self._request(url, referer=f'{SITE_URL}/category/movie')
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 24, 'total': 0}

            data = rsp.json()
            movies = data.get('movies', [])
            videos = [self._parse_movie(m) for m in movies]
            total = data.get('total', 0)
            pagecount = (total + 23) // 24 if total else page

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': 24,
                'total': total,
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 24, 'total': 0}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 24, 'total': 0}

        kw_encoded = urllib.parse.quote(keyword)
        url = f'{SITE_URL}/api/search?q={kw_encoded}'

        try:
            rsp = self._request(url, referer=f'{SITE_URL}/search?q={kw_encoded}')
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 24, 'total': 0}

            data = rsp.json()
            results = data.get('results', [])
            videos = []
            for r in results:
                cat_id = str(r.get('cat_id', '1'))
                en_id = r.get('en_id', '')
                if not en_id:
                    continue
                title = self._clean_html(r.get('title', ''))
                cover = r.get('cover', '')
                year = str(r.get('year', ''))
                videos.append({
                    'vod_id': f"{cat_id}|{en_id}",
                    'vod_name': title,
                    'vod_pic': self._fix_url(cover),
                    'vod_remarks': year,
                })

            return {
                'list': videos,
                'page': str(page),
                'pagecount': 1,
                'limit': len(videos),
                'total': len(videos),
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': page, 'limit': 24, 'total': 0}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        raw_id = str(ids[0])
        # 解析 cat_id|en_id 或纯 en_id
        parts = raw_id.split("|")
        if len(parts) >= 2:
            cat_id = parts[0]
            en_id = parts[1]
        else:
            cat_id = "1"
            en_id = parts[0]

        # 请求详情页 HTML
        url = f'{SITE_URL}/detail/{cat_id}/{en_id}'
        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}
            html = rsp.text
        except Exception:
            return {'list': []}

        vod = {'vod_id': raw_id}

        # 标题 — 从 h1 提取
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        vod['vod_name'] = self._clean_html(title_match.group(1)) if title_match else ""

        # 封面 — 从 og:image 或 img 提取
        pic_match = re.search(r'<meta property="og:image" content="([^"]*)"', html)
        if not pic_match:
            pic_match = re.search(r'<img[^>]*alt="' + re.escape(vod['vod_name']) + r'"[^>]*src="([^"]*)"', html)
        vod['vod_pic'] = self._fix_url(pic_match.group(1)) if pic_match else ""

        # 类型
        cat_map = {'1': '电影', '2': '电视剧', '3': '综艺', '4': '动漫'}
        vod['type_name'] = cat_map.get(cat_id, '')

        # meta description — 包含年份、演员等
        meta_desc = ''
        desc_meta_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
        if not desc_meta_match:
            desc_meta_match = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
        if desc_meta_match:
            meta_desc = desc_meta_match.group(1)

        # 年份 — 从 meta description "上映于YYYY年" 或 "YYYY年" 提取
        year_match = re.search(r'上映于(\d{4})年', meta_desc)
        if not year_match:
            year_match = re.search(r'(\d{4})年', meta_desc)
        if not year_match:
            year_match = re.search(r'"year"\s*:\s*"?(\d{4})"?', html)
        vod['vod_year'] = year_match.group(1) if year_match else ""

        # 演员 — 从 meta description "由XXX主演" 或 meta keywords 提取
        actor_match = re.search(r'由([^。]+?)主演', meta_desc)
        if actor_match:
            vod['vod_actor'] = actor_match.group(1).strip()[:200]
        else:
            # 从 keywords 提取
            kw_match = re.search(r'<meta\s+name="keywords"\s+content="([^"]*)"', html)
            if kw_match:
                kws = kw_match.group(1).split(',')
                # 过滤掉标题类关键词，保留人名
                actors = [k.strip() for k in kws if len(k.strip()) <= 4 and k.strip() not in [vod['vod_name']]]
                vod['vod_actor'] = ' / '.join(actors[:8])
            else:
                vod['vod_actor'] = ""

        # 导演 — 从页面提取
        director_match = re.search(r'导演[：:]\s*(.*?)(?:<|$)', html, re.S)
        vod['vod_director'] = self._clean_html(director_match.group(1))[:100] if director_match else ""

        # 简介
        vod['vod_content'] = meta_desc[:300] if meta_desc else ""

        # ===== 播放列表 =====
        # 从详情页 HTML 提取播放链接
        # 格式: /play/{cat_id}/{en_id}/{episode}?s={source}
        play_links = re.findall(
            r'href="/play/' + cat_id + r'/' + re.escape(en_id) + r'/(\d+)\?s=(\w+)"[^>]*>(.*?)</a>',
            html, re.S
        )

        # 从 RSC chunks 提取 allepidetail（每集的 playUrl）
        episode_urls = {}
        next_f = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html)
        for chunk in next_f:
            if 'allepidetail' in chunk or 'playlink_num' in chunk:
                decoded = chunk.replace('\\"', '"').replace('\\u0026', '&')
                eps = re.findall(r'"playlink_num"\s*:\s*"(\d+)".*?"url"\s*:\s*"(http://[^"]+)"', decoded)
                for num, ep_url in eps:
                    episode_urls[num] = ep_url
                break

        # 也从 filter API 的 playlinks 获取第1集 URL 作为备用
        if not episode_urls:
            # 尝试从详情页 HTML 中找 playlinks
            playlinks_match = re.search(r'"playlinks"\s*:\s*\{[^}]*"qiyi"\s*:\s*"(http://[^"\\]+)', html)
            if playlinks_match:
                episode_urls['1'] = playlinks_match.group(1)

        # 电影类型备用：调用 filter API 获取 playlinks
        if not episode_urls:
            try:
                filter_url = f'{SITE_URL}/api/filter?catId={cat_id}&sort=ranklatest&page=1&size=24'
                f_rsp = self._request(filter_url)
                if f_rsp and f_rsp.status_code == 200:
                    f_data = f_rsp.json()
                    for m in f_data.get('movies', []):
                        if m.get('id') == en_id:
                            playlinks = m.get('playlinks', {})
                            for site, pl_url in playlinks.items():
                                episode_urls['1'] = pl_url
                                break
                            break
            except Exception:
                pass

        play_from_list = []
        play_url_list = []

        if play_links:
            # 按播放源分组
            from collections import defaultdict
            source_eps = defaultdict(list)
            source_order = []
            seen_eps = set()
            for ep_num, source, label in play_links:
                label_clean = self._clean_html(label)
                if not label_clean or label_clean == '立即播放':
                    label_clean = f"第{int(ep_num):02d}集"
                ep_key = f"{source}_{ep_num}"
                if ep_key not in seen_eps:
                    seen_eps.add(ep_key)
                    if source not in source_order:
                        source_order.append(source)
                    source_eps[source].append((ep_num, label_clean))

            for source in source_order:
                source_name = SOURCE_NAMES.get(source, source)
                ep_list = []
                for ep_num, label in source_eps[source]:
                    # 播放ID: cat_id|en_id|ep_num|source|playUrl
                    play_url = episode_urls.get(ep_num, '')
                    play_key = f"{cat_id}|{en_id}|{ep_num}|{source}|{play_url}"
                    ep_list.append(f"{label}${play_key}")

                play_from_list.append(source_name)
                play_url_list.append("#".join(ep_list))
        else:
            # 备用：用 episode_urls 构造播放列表
            if episode_urls:
                ep_list = []
                for ep_num in sorted(episode_urls.keys(), key=int):
                    label = f"第{int(ep_num):02d}集"
                    play_url = episode_urls[ep_num]
                    play_key = f"{cat_id}|{en_id}|{ep_num}|qiyi|{play_url}"
                    ep_list.append(f"{label}${play_key}")
                play_from_list.append("星河影视")
                play_url_list.append("#".join(ep_list))

        vod['vod_play_from'] = "$$$".join(play_from_list)
        vod['vod_play_url'] = "$$$".join(play_url_list)

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        """
        通过 /api/player/resolve 获取 m3u8 直链
        播放ID格式: cat_id|en_id|ep_num|source|playUrl
        """
        parts = str(id).split("|")
        if len(parts) < 4:
            return {'parse': 0, 'url': '', 'header': {}}

        cat_id = parts[0]
        en_id = parts[1]
        ep_num = parts[2]
        source = parts[3]
        play_url = parts[4] if len(parts) > 4 else ''

        # 如果有 playUrl，直接调用 resolve API
        if play_url:
            resolve_data = {
                'playUrl': play_url,
                'statVodId': en_id,
                'statSource': cat_id,
                'statVodName': '',
            }

            play_page_url = f'{SITE_URL}/play/{cat_id}/{en_id}/{ep_num}?s={source}'
            rsp = self._post_json(
                f'{SITE_URL}/api/player/resolve',
                resolve_data,
                referer=play_page_url
            )

            if rsp and rsp.status_code == 200:
                try:
                    data = rsp.json()
                    if data.get('success') and data.get('url'):
                        return {
                            'parse': 0,
                            'url': data['url'],
                            'header': {
                                'User-Agent': UA,
                            },
                        }
                except Exception:
                    pass

        # 降级：返回播放页 URL 走嗅探
        play_page_url = f'{SITE_URL}/play/{cat_id}/{en_id}/{ep_num}?s={source}'
        return {
            'parse': 1,
            'url': play_page_url,
            'header': {
                'User-Agent': UA,
                'Referer': SITE_URL + '/',
            },
        }

    # ========== 列表解析 ==========

    def _parse_movie(self, m):
        """解析 filter API 返回的电影数据"""
        cat_id = str(m.get('cat_id', 1)) if 'cat_id' in m else '1'
        en_id = m.get('id', '') or m.get('en_id', '')
        title = m.get('title', '')
        # 去除 HTML 标签
        title = self._clean_html(title)
        
        cover = m.get('cdncover', '') or m.get('cover', '')
        cover = self._fix_url(cover)
        
        # 备注
        remarks = ''
        if m.get('doubanscore') and m.get('doubanscore') != 'None':
            remarks = f"豆瓣{m['doubanscore']}"
        elif m.get('score') and m.get('score') != 0:
            remarks = f"评分{m['score']}"
        elif m.get('pubdate'):
            remarks = str(m['pubdate'])[:4]
        
        if m.get('vip'):
            remarks = ('VIP ' if remarks else '') + 'VIP'
        
        return {
            'vod_id': f"{cat_id}|{en_id}",
            'vod_name': title,
            'vod_pic': cover,
            'vod_remarks': remarks,
        }


# ==================== 本地测试 ====================
if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings()

    spider = Spider()
    spider.init()

    print("=== 首页 ===")
    home = spider.homeContent(True)
    print("分类:", [c["type_name"] for c in home["class"]])

    print("\n=== 首页推荐 ===")
    homeVid = spider.homeVideoContent()
    print(f"推荐视频数: {len(homeVid['list'])}")
    for v in homeVid["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']} | 备注: {v['vod_remarks']}")

    print("\n=== 分类(电影) ===")
    cat = spider.categoryContent("1", "1", True, {})
    print(f"视频数: {len(cat['list'])}, 页数: {cat.get('page')}/{cat.get('pagecount')}, 总数: {cat.get('total')}")
    for v in cat["list"][:3]:
        print(f"  - {v['vod_name']} | id: {v['vod_id']} | 备注: {v['vod_remarks']}")

    print("\n=== 分类(电影) 第2页 ===")
    cat2 = spider.categoryContent("1", "2", True, {})
    print(f"视频数: {len(cat2['list'])}, 页数: {cat2.get('page')}/{cat2.get('pagecount')}")

    print("\n=== 搜索(变形金刚) ===")
    search = spider.searchContent("变形金刚", False)
    print(f"结果数: {len(search['list'])}")
    for v in search["list"][:5]:
        print(f"  - {v['vod_name']} (id: {v['vod_id']})")

    print("\n=== 详情(电影 特立独行) ===")
    detail = spider.detailContent(["1|ganmZRH8R0H2TB"])
    if detail["list"]:
        vod = detail["list"][0]
        print(f"标题: {vod.get('vod_name', '')}")
        print(f"类型: {vod.get('type_name', '')}")
        print(f"年份: {vod.get('vod_year', '')}")
        print(f"演员: {vod.get('vod_actor', '')[:80]}")
        print(f"播放线路: {vod.get('vod_play_from', '')}")
        play_url_raw = vod.get('vod_play_url', '')
        eps = play_url_raw.split("#") if play_url_raw else []
        print(f"集数: {len(eps)}")
        for ep in eps[:3]:
            ep_parts = ep.split("$")
            if len(ep_parts) >= 2:
                print(f"  - {ep_parts[0]} | id: {ep_parts[1][:60]}")

        print("\n=== 播放解析(电影) ===")
        if eps:
            first_ep = eps[0]
            ep_parts = first_ep.split("$")
            if len(ep_parts) >= 2:
                play = spider.playerContent("", ep_parts[1], [])
                print(f"播放URL: {play.get('url', '')[:100]}")
                print(f"parse: {play.get('parse', '')}")

    print("\n=== 详情(电视剧 生逢其时) ===")
    detail2 = spider.detailContent(["2|PrZwcX7nTGDrNH"])
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
                    print(f"    - {ep_parts[0]} | id: {ep_parts[1][:60]}")

            print(f"\n  === 播放解析(线路{li+1} 第2集) ===")
            if len(eps2) > 1:
                ep_parts2 = eps2[1].split("$")
                if len(ep_parts2) >= 2:
                    play2 = spider.playerContent("", ep_parts2[1], [])
                    print(f"  播放URL: {play2.get('url', '')[:100]}")
                    print(f"  parse: {play2.get('parse', '')}")
