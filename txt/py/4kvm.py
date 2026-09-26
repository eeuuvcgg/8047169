# -*- coding: utf-8 -*-
"""
4kvm.tv (https://www.4kvm.tv) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://www.4kvm.tv
播放: WASM 签名 (需 Node.js + wasm_files/)
版本: 2.0.0
"""
import sys
import json
import re
import os
import subprocess
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
SITE_URL = "https://www.4kvm.tv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "4", "type_name": "综艺"},
]

FILTERS = {
    "1": [
        {"key": "types", "name": "类型", "value": [
            {"n": "全部", "v": ""}, {"n": "剧情", "v": "1"}, {"n": "喜剧", "v": "5"},
            {"n": "爱情", "v": "6"}, {"n": "动作", "v": "10"}, {"n": "科幻", "v": "14"},
            {"n": "恐怖", "v": "3"}, {"n": "惊悚", "v": "4"}, {"n": "悬疑", "v": "2"},
            {"n": "犯罪", "v": "9"}, {"n": "动画", "v": "11"}, {"n": "奇幻", "v": "12"},
            {"n": "冒险", "v": "18"}, {"n": "战争", "v": "16"}, {"n": "历史", "v": "15"},
        ]},
        {"key": "areas", "name": "地区", "value": [
            {"n": "全部", "v": ""}, {"n": "中国大陆", "v": "52"}, {"n": "中国香港", "v": "14"},
            {"n": "中国台湾", "v": "21"}, {"n": "美国", "v": "5"}, {"n": "日本", "v": "11"},
            {"n": "韩国", "v": "12"}, {"n": "英国", "v": "30"}, {"n": "法国", "v": "6"},
            {"n": "德国", "v": "18"}, {"n": "泰国", "v": "33"}, {"n": "印度", "v": "34"},
        ]},
        {"key": "years", "name": "年份", "value": [
            {"n": "全部", "v": ""}, {"n": "2026", "v": "1"}, {"n": "2025", "v": "3"},
            {"n": "2024", "v": "4"}, {"n": "2023", "v": "56"}, {"n": "2022", "v": "13"},
            {"n": "2021", "v": "2"}, {"n": "2020", "v": "6"}, {"n": "2019", "v": "8"},
        ]},
    ],
    "2": [
        {"key": "types", "name": "类型", "value": [
            {"n": "全部", "v": ""}, {"n": "剧情", "v": "1"}, {"n": "喜剧", "v": "5"},
            {"n": "爱情", "v": "6"}, {"n": "动作", "v": "10"}, {"n": "科幻", "v": "14"},
            {"n": "悬疑", "v": "2"}, {"n": "犯罪", "v": "9"}, {"n": "动画", "v": "11"},
            {"n": "奇幻", "v": "12"}, {"n": "战争", "v": "16"},
        ]},
        {"key": "areas", "name": "地区", "value": [
            {"n": "全部", "v": ""}, {"n": "中国大陆", "v": "52"}, {"n": "中国香港", "v": "14"},
            {"n": "美国", "v": "5"}, {"n": "日本", "v": "11"}, {"n": "韩国", "v": "12"},
            {"n": "英国", "v": "30"},
        ]},
        {"key": "years", "name": "年份", "value": [
            {"n": "全部", "v": ""}, {"n": "2026", "v": "1"}, {"n": "2025", "v": "3"},
            {"n": "2024", "v": "4"}, {"n": "2023", "v": "56"}, {"n": "2022", "v": "13"},
        ]},
    ],
    "3": [
        {"key": "types", "name": "类型", "value": [
            {"n": "全部", "v": ""}, {"n": "动画", "v": "11"}, {"n": "奇幻", "v": "12"},
            {"n": "冒险", "v": "18"}, {"n": "喜剧", "v": "5"}, {"n": "动作", "v": "10"},
        ]},
        {"key": "areas", "name": "地区", "value": [
            {"n": "全部", "v": ""}, {"n": "日本", "v": "11"},
            {"n": "中国大陆", "v": "52"}, {"n": "美国", "v": "5"},
        ]},
    ],
    "4": [
        {"key": "years", "name": "年份", "value": [
            {"n": "全部", "v": ""}, {"n": "2026", "v": "1"}, {"n": "2025", "v": "3"},
            {"n": "2024", "v": "4"}, {"n": "2023", "v": "56"},
        ]},
    ],
}


class Spider(Spider):
    """4k影视 Spider — 正则采集 + WASM签名播放"""

    def getName(self):
        return "4k影视"

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
    def _clean(text):
        if not text:
            return ''
        return text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

    @staticmethod
    def _extract_meta(html, name):
        m = re.search(r'<meta\s+name="' + name + r'"\s+content="([^"]*)"', html)
        return m.group(1) if m else ''

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        result['class'] = list(CLASSES)
        if filter:
            result['filters'] = dict(FILTERS)
        return result

    def homeVideoContent(self):
        try:
            rsp = self._request(SITE_URL)
            if rsp and rsp.status_code == 200:
                videos = self._parse_list(rsp.text)
                return {'list': videos[:24]}
        except Exception:
            pass
        return {'list': []}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        tid = self._safe_str(tid, '1')
        page = self._safe_page(pg, 1)
        extend = extend or {}

        params = {'classify': tid, 'page': str(page)}
        for key in ['areas', 'types', 'years', 'tags', 'sort_by', 'order']:
            if key in extend:
                params[key] = extend[key]

        url = SITE_URL + '/filter?' + urllib.parse.urlencode(params)

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': 24, 'total': 0}

            html = rsp.text
            videos = self._parse_list(html)

            pagecount = 9999
            total = 999999
            m = re.search(r'共\s*(\d+)\s*页.*?共\s*(\d+)\s*个', html)
            if m:
                pagecount = int(m.group(1))
                total = int(m.group(2))

            return {
                'list': videos,
                'page': str(page),
                'pagecount': pagecount,
                'limit': len(videos),
                'total': total,
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': 24, 'total': 0}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        page = self._safe_page(pg, 1)
        keyword = self._safe_str(key).strip()
        if not keyword:
            return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': 30, 'total': 0}

        url = SITE_URL + '/filter?keyword=' + urllib.parse.quote(keyword)

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': 30, 'total': 0}

            videos = self._parse_list(rsp.text)
            return {
                'list': videos,
                'page': str(page),
                'pagecount': page,
                'limit': len(videos),
                'total': len(videos),
            }
        except Exception:
            return {'list': [], 'page': str(page), 'pagecount': 1, 'limit': 30, 'total': 0}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情页 ==========

    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = str(ids[0])
        url = SITE_URL + '/play/' + vod_id

        try:
            rsp = self._request(url)
            if not rsp or rsp.status_code != 200:
                return {'list': []}
            html = rsp.text
        except Exception:
            return {'list': []}

        vod = {'vod_id': vod_id}

        # 标题
        title_match = re.search(r'<h1[^>]*class="[^"]*"[^>]*>([^<]*)</h1>', html)
        if not title_match:
            title_match = re.search(r'<h1[^>]*>([^<]*)</h1>', html)
        vod['vod_name'] = title_match.group(1).strip() if title_match else vod_id

        # 封面 — 从 video-player 的 data-poster
        pic_match = re.search(r'data-poster="([^"]*)"', html)
        vod['vod_pic'] = self._clean(pic_match.group(1)) if pic_match else ''

        # 从 keywords 提取: [4k,]title,year,[types...],area,[langs...],director
        keywords = self._extract_meta(html, 'keywords')
        description = self._extract_meta(html, 'description')

        year = ''
        type_name = ''
        area = ''
        director = ''

        if keywords:
            parts = [p.strip() for p in keywords.split(',') if p.strip()]
            start = 0
            if parts and parts[0].lower() in ('4k', 'tc', 'vip'):
                start = 1
            if start + 1 < len(parts) and re.match(r'^\d{4}$', parts[start + 1]):
                year = parts[start + 1]
            rest = parts[start + 2:] if start + 2 < len(parts) else []
            type_set = {'剧情', '喜剧', '爱情', '动作', '科幻', '恐怖', '惊悚',
                        '悬疑', '动画', '奇幻', '冒险', '犯罪', '战争', '历史',
                        '家庭', '纪录', '传记', '音乐', '歌舞', '武侠', '古装',
                        '情色', '西部', '短片', '灾难', '运动', '同性'}
            for r in rest:
                if r in type_set:
                    type_name = (type_name + ' ' + r).strip() if type_name else r
                elif any(p in r for p in ('大陆', '美国', '日本', '韩国', '香港',
                                           '台湾', '英国', '法国', '泰国', '印度',
                                           '俄罗斯', '德国', '中国', '意大利')):
                    area = r
                elif '/' in r and not director:
                    director = r

        vod['type_name'] = type_name
        vod['vod_year'] = year
        vod['vod_area'] = area
        vod['vod_director'] = director
        vod['vod_actor'] = ''
        vod['vod_content'] = description or ''
        vod['vod_remarks'] = '4K' if '4k' in (keywords or '').lower() else ''

        # 选集 — 格式: 集名$dataid|video_id
        # 从 <a> 标签属性提取 data-episode, dataid, href
        ep_pattern = re.compile(
            r'<a[^>]*href="/play/([a-z0-9]+)"[^>]*'
            r'data-episode="(\d+)"[^>]*'
            r'dataid="(\d+)"'
        )
        ep_matches = ep_pattern.findall(html)

        play_from = '4k影视'
        play_url = ''

        if ep_matches:
            episodes = []
            for ep_vid, ep_num, dataid in ep_matches:
                ep_text = '第{0}集'.format(ep_num) if ep_num else '播放'
                episodes.append('{0}${1}|{2}'.format(ep_text, dataid, ep_vid))
            play_url = '#'.join(episodes)
        else:
            # 电影只有一集
            dataid_match = re.search(r'dataid="(\d+)"', html)
            dataid = dataid_match.group(1) if dataid_match else ''
            play_url = '正片${0}|{1}'.format(dataid, vod_id)

        vod['vod_play_from'] = play_from
        vod['vod_play_url'] = play_url

        return {'list': [vod]}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        # id 格式: "dataid|video_id"
        parts = str(id).split('|')
        dataid = parts[0] if parts else ''
        video_id = parts[1] if len(parts) > 1 else ''

        header = {
            'User-Agent': UA,
            'Referer': SITE_URL + '/',
        }

        if not video_id:
            return {'parse': 0, 'url': '', 'header': header}

        # 方案1: 尝试 WASM 签名获取直链（需要 Node.js）
        play_url = self._get_play_url(dataid, video_id)
        if play_url and self.isVideoFormat(play_url):
            return {'parse': 0, 'url': play_url, 'header': header}

        # 方案2: 嗅探模式 — 让 App WebView 打开播放页自动抓取 m3u8
        # 页面 JS 会自动运行 WASM 签名并加载视频
        sniff_url = SITE_URL + '/play/' + video_id
        return {'parse': 1, 'url': sniff_url, 'header': header}

    def _get_play_url(self, dataid, video_id):
        """WASM 签名 → API → m3u8"""
        try:
            # 1. 请求详情页获取 userlink / nb-st / nb-plt
            detail_url = SITE_URL + '/play/' + video_id
            rsp = self._request(detail_url)
            if not rsp or rsp.status_code != 200:
                return ''
            html = rsp.text

            userlink = '0'
            m = re.search(r"userlink:'([^']*)'", html)
            if m:
                userlink = m.group(1)

            nb_st = ''
            m = re.search(r'id="nb-st"[^>]*content="([^"]*)"', html)
            if m:
                nb_st = m.group(1)

            nb_plt = ''
            m = re.search(r'id="nb-plt"[^>]*content="([^"]*)"', html)
            if m:
                nb_plt = m.group(1)

            # 2. WASM 签名
            signed_path = self._wasm_sign(
                nb_st, nb_plt, dataid, video_id, '1080', userlink
            )
            if not signed_path:
                return ''

            # 3. 请求 API 获取 m3u8
            api_url = SITE_URL + signed_path
            api_rsp = self._request(api_url, referer=detail_url)
            if not api_rsp or api_rsp.status_code != 200:
                return ''

            data = json.loads(api_rsp.text)
            if data.get('code') == 200 and data.get('data'):
                quality_urls = data['data'].get('quality_urls', [])
                for q in quality_urls:
                    if not q.get('locked', True) and q.get('url') and q['url'] != '1':
                        return q['url']
                for q in quality_urls:
                    if q.get('url') and q['url'] != '1':
                        return q['url']
        except Exception:
            pass
        return ''

    def _wasm_sign(self, nb_st, nb_plt, dataid, video_id, quality, play_key):
        """调用 Node.js 运行 WASM 生成签名 URL"""
        try:
            import shutil
            base_dir = os.path.dirname(os.path.abspath(
                __file__)) if '__file__' in globals() else os.getcwd()

            # 在同级目录和 wasm_files/ 子目录中查找
            run_js = None
            for candidate in [
                os.path.join(base_dir, 'run_wasm.js'),
                os.path.join(base_dir, 'wasm_files', 'run_wasm.js'),
            ]:
                if os.path.exists(candidate):
                    run_js = os.path.abspath(candidate)
                    break
            if not run_js:
                return ''

            wasm_dir = os.path.dirname(run_js)
            wasm_bin = os.path.join(wasm_dir, 'nbmovie_wasm_bg.wasm')
            if not os.path.exists(wasm_bin):
                return ''

            node = shutil.which('node') or shutil.which('nodejs')
            if not node:
                for c in ('/usr/bin/node', '/usr/local/bin/node'):
                    if os.path.exists(c):
                        node = c
                        break
            if not node:
                return ''

            cmd = [node, run_js, nb_st or '', nb_plt or '',
                   str(dataid), str(video_id),
                   str(quality), str(play_key)]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                cwd=wasm_dir, encoding='utf-8', errors='replace'
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return ''

    # ========== 列表解析 ==========

    def _parse_list(self, html):
        """解析列表页/首页/搜索结果 — 纯正则"""
        videos = []

        # 主解析: 匹配含 data-src + h3 + /play/ 链接的卡片
        # 结构: <a href="/play/xxx" ...><div><img data-src="url" ... alt="title">
        #        ...<span class="...bottom...">remark</span></div><h3>title</h3></a>
        pattern = re.compile(
            r'<a[^>]*href="/play/([a-z0-9]+)"[^>]*>.*?'
            r'data-src="([^"]*)"[^>]*>.*?'
            r'<span[^>]*class="[^"]*bottom[^"]*"[^>]*>\s*([^<]*)\s*</span>.*?'
            r'<h3[^>]*>([^<]*)</h3>.*?</a>',
            re.S
        )
        matches = pattern.findall(html)
        seen = set()
        for vid, pic, remark, title in matches:
            if vid in seen:
                continue
            seen.add(vid)
            title = title.strip()
            if not title:
                continue
            videos.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': self._clean(pic),
                'vod_remarks': remark.strip(),
            })

        # 备用解析1: 无 span remark 的情况
        if not videos:
            pattern2 = re.compile(
                r'<a[^>]*href="/play/([a-z0-9]+)"[^>]*>.*?'
                r'data-src="([^"]*)"[^>]*alt="([^"]*)"[^>]*>.*?'
                r'<h3[^>]*>([^<]*)</h3>',
                re.S
            )
            for vid, pic, alt, title in pattern2.findall(html):
                if vid in seen:
                    continue
                seen.add(vid)
                title = title.strip()
                if not title:
                    continue
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': self._clean(pic),
                    'vod_remarks': '',
                })

        # 备用解析2: 只取 play 链接 + alt
        if not videos:
            items = re.findall(
                r'<a[^>]*href="/play/([a-z0-9]+)"[^>]*>.*?'
                r'<h3[^>]*>([^<]*)</h3>',
                html, re.S
            )
            for vid, title in items:
                if vid in seen:
                    continue
                seen.add(vid)
                title = title.strip()
                if not title:
                    continue
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': '',
                    'vod_remarks': '',
                })

        return videos

    # ========== 本地代理 ==========

    def localProxy(self, param):
        return [200, 'text/plain; charset=UTF-8', '']


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
    for v in homeVid["list"][:5]:
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')} | {v['vod_id']}")

    print("\n=== 分类(电影) ===")
    cat = spider.categoryContent("1", "1", True, {})
    print(f"视频数: {len(cat['list'])}")
    for v in cat["list"][:5]:
        print(f"  - {v['vod_name']} | {v.get('vod_remarks', '')} | {v['vod_id']}")

    print("\n=== 搜索(凡人) ===")
    search = spider.searchContent("凡人", False)
    print(f"结果数: {len(search['list'])}")
    for v in search["list"][:5]:
        print(f"  - {v['vod_name']} | {v['vod_id']}")

    print("\n=== 详情 ===")
    if search["list"]:
        detail = spider.detailContent([search["list"][0]["vod_id"]])
        if detail["list"]:
            vod = detail["list"][0]
            print(f"标题: {vod.get('vod_name', '')}")
            print(f"年份: {vod.get('vod_year', '')}")
            print(f"地区: {vod.get('vod_area', '')}")
            print(f"导演: {vod.get('vod_director', '')}")
            print(f"播放线路: {vod.get('vod_play_from', '')}")
            play_urls = vod.get("vod_play_url", "").split("#")
            print(f"选集数: {len(play_urls)}")
            if play_urls:
                print(f"第一集: {play_urls[0]}")
