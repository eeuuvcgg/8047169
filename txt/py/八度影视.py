# -*- coding: utf-8 -*-
"""
TVBox Python Spider -- h.sdgtrl.com (八度影院)
Standard TVBox/FongMi interface, pure standard library.
"""

import re
import json
import gzip
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from urllib.parse import quote, unquote
from base64 import b64decode

# ============================================================
# 基类导入
# ============================================================
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        """仅用于本地测试的占位基类，TVBox 环境会自动忽略"""
        def init(self, extend=""):
            pass
        def getName(self):
            return ""
        def isVideoFormat(self, url):
            return False
        def manualVideoResolve(self, url):
            return url
        def localProxy(self, params):
            return None

# ============================================================
# 站点配置
# ============================================================
BASE_URL = "https://h.sdgtrl.com"
TIMEOUT = 15

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Mobile/15E148 Safari/604.1"
)
HEADERS = {
    "User-Agent": UA,
    "Referer": BASE_URL,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip",
}

CATEGORIES = [
    ("dianying", "电影"),
    ("dianshiju", "电视剧"),
    ("zongyi", "综艺"),
    ("dongman", "动漫"),
    ("dongzuopian", "动作片"),
    ("xijupian", "喜剧片"),
    ("aiqingpian", "爱情片"),
    ("kehuanpian", "科幻片"),
    ("kongbupian", "恐怖片"),
    ("juqingpian", "剧情片"),
    ("zhanzhengpian", "战争片"),
    ("jingsongpian", "惊悚片"),
    ("jiatingpian", "家庭片"),
    ("guzhangpian", "古装片"),
    ("lishipian", "历史片"),
    ("xianyipian", "悬疑片"),
    ("zainanpian", "灾难片"),
    ("jilupian", "记录片"),
    ("donghuapian", "动画片"),
    ("fanzuipian", "犯罪片"),
    ("rihan", "日韩"),
    ("guochanju", "国产剧"),
    ("xianggangju", "香港剧"),
    ("hanguoju", "韩国剧"),
    ("oumeiju", "欧美剧"),
    ("taiwanju", "台湾剧"),
    ("ribenju", "日本剧"),
    ("haiwaiju", "海外剧"),
    ("taiguoju", "泰国剧"),
    ("duanju", "短剧"),
]

# ============================================================
# 工具函数
# ============================================================
def _get(url):
    """标准库 GET 请求，支持 gzip，返回 HTML 字符串或空字符串"""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
            return raw.decode(charset, errors="ignore")
    except Exception:
        return ""

def _abs(url):
    if url and not url.startswith("http"):
        return BASE_URL + url if url.startswith("/") else BASE_URL + "/" + url
    return url

def _strip_tags(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _parse_extend(extend):
    if isinstance(extend, str) and extend:
        try:
            extend = json.loads(extend)
        except Exception:
            extend = {}
    if not isinstance(extend, dict):
        extend = {}
    return extend

def _parse_cards(html):
    videos = []
    seen = set()
    for m in re.finditer(
        r'<a\s+[^>]*?href="/films/(\d+)\.html"[^>]*?title="([^"]*)"[^>]*?data-original="([^"]*)"',
        html, re.DOTALL
    ):
        vid = m.group(1)
        if vid in seen:
            continue
        seen.add(vid)
        title = m.group(2)
        pic = _abs(m.group(3))
        tail = html[m.end():m.end() + 300]
        rm = re.search(r'pic-tag[^>]*>([^<]*)<', tail)
        remarks = rm.group(1).strip() if rm else ""
        videos.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remarks,
        })
    return videos

def _get_pagecount(html):
    m = re.search(r'href="[^"]*?page=(\d+)"[^>]*>尾页', html)
    if m:
        return int(m.group(1))
    nums = re.findall(r'page=(\d+)', html)
    return max(int(n) for n in nums) if nums else 1

def _parse_playlists(html):
    episodes = re.findall(
        r'<a[^>]*href="/vodlist/(\d+)-(\d+)-(\d+)\.html"[^>]*>([^<]*)</a>',
        html
    )
    if not episodes:
        return "", ""

    sources = {}
    for vid, sid, eid, name in episodes:
        sid = int(sid)
        if sid not in sources:
            sources[sid] = []
        play_url = "{}/vodlist/{}-{}-{}.html".format(BASE_URL, vid, sid, eid)
        sources[sid].append("{}${}".format(name.strip(), play_url))

    play_from_parts = []
    play_url_parts = []
    for sid in sorted(sources.keys()):
        play_from_parts.append("线路{}".format(sid))
        play_url_parts.append("#".join(sources[sid]))

    return "$$$".join(play_from_parts), "$$$".join(play_url_parts)

def _year_filter():
    now = datetime.now().year
    return [{"n": "全部", "v": ""}] + [
        {"n": str(y), "v": str(y)} for y in range(now, now - 12, -1)
    ]

def _common_filters():
    return [
        {
            "key": "year",
            "name": "年份",
            "value": _year_filter(),
        },
        {
            "key": "area",
            "name": "地区",
            "value": [
                {"n": "全部", "v": ""}, {"n": "中国", "v": "中国"},
                {"n": "美国", "v": "美国"}, {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "英国", "v": "英国"},
                {"n": "法国", "v": "法国"}, {"n": "德国", "v": "德国"},
                {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"},
                {"n": "其他", "v": "其他"},
            ],
        },
        {
            "key": "by",
            "name": "排序",
            "value": [
                {"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"},
                {"n": "评分", "v": "score"},
            ],
        },
    ]

# ============================================================
# Spider 类
# ============================================================
class Spider(BaseSpider):

    def init(self, extend=""):
        pass

    def getName(self):
        return "八度影院"

    def isVideoFormat(self, url):
        return re.search(
            r"\.(m3u8|mp4|flv|avi|mkv|wmv|mov|ts)(?:$|\?)",
            url or "",
            re.IGNORECASE,
        ) is not None

    def localProxy(self, params):
        return None

    # ---------- Home ----------
    def homeContent(self, filter):
        result = {"class": [], "filters": {}, "list": []}
        filters = _common_filters()
        for slug, name in CATEGORIES:
            result["class"].append({
                "type_id": slug,
                "type_name": name,
            })
            result["filters"][slug] = filters

        html = _get(BASE_URL + "/")
        if html:
            result["list"] = _parse_cards(html)

        return result

    def homeVideoContent(self):
        html = _get(BASE_URL + "/")
        return {"list": _parse_cards(html) if html else []}

    # ---------- Category ----------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        extend = _parse_extend(extend)

        url = "{}/vod/{}.html?page={}".format(BASE_URL, tid, page)
        for k in ("area", "year", "by"):
            v = extend.get(k, "")
            if v:
                url += "&{}={}".format(k, quote(v))

        html = _get(url)
        result = {
            "list": [],
            "page": page,
            "pagecount": 1,
            "limit": 20,
            "total": 0,
        }
        if html:
            result["list"] = _parse_cards(html)
            result["pagecount"] = _get_pagecount(html)
            result["limit"] = len(result["list"])

        return result

    # ---------- Search ----------
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        url = "{}/mosr?wd={}&page={}".format(BASE_URL, quote(key), page)
        html = _get(url)
        return {"list": _parse_cards(html) if html else []}

    # ---------- Detail ----------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        url = "{}/films/{}.html".format(BASE_URL, vid)
        html = _get(url)
        result = {"list": []}
        if not html:
            return result

        title = ""
        m = re.search(r'<h1[^>]*>\s*<a[^>]*title="([^"]*)"', html)
        if m:
            title = m.group(1)
        else:
            m = re.search(r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>\s*<a[^>]*>([^<]*)</a>', html)
            if m:
                title = m.group(1)

        pic = ""
        m = re.search(r'stui-content__thumb.*?<img[^>]*src="([^"]*)"', html, re.DOTALL)
        if m:
            pic = _abs(m.group(1))

        year = ""
        m = re.search(r'年代\s*[：:]\s*<a[^>]*>([^<]*)</a>', html)
        if m:
            year = m.group(1)

        area = ""
        m = re.search(r'地区\s*[：:]\s*<a[^>]*>([^<]*)</a>', html)
        if m:
            area = m.group(1)

        director = ""
        m = re.search(r'导演\s*[：:]\s*(.*?)</p>', html, re.DOTALL)
        if m:
            director = _strip_tags(m.group(1))

        actor = ""
        m = re.search(r'演员\s*[：:]\s*(.*?)</p>', html, re.DOTALL)
        if m:
            actor = _strip_tags(m.group(1))

        content = ""
        m = re.search(r'detail-sketch[^>]*>(.*?)</span>', html, re.DOTALL)
        if m:
            content = _strip_tags(m.group(1))

        play_from, play_url = _parse_playlists(html)

        result["list"].append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": "",
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": content,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        })
        return result

    # ---------- Player ----------
    def playerContent(self, flag, id, vipFlags):
        play_url = id if id.startswith("http") else _abs(id)
        html = _get(play_url)
        url = ""
        if html:
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})', html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    url = data.get("url", "")
                    encrypt = data.get("encrypt", 0)
                    if encrypt == 1:
                        url = unquote(url)
                    elif encrypt == 2:
                        url = b64decode(url).decode("utf-8")
                except Exception:
                    pass

        parse = 0 if (url and self.isVideoFormat(url)) else 1
        return {
            "parse": parse,
            "url": url,
            "header": json.dumps(HEADERS),
        }
