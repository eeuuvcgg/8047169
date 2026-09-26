#coding=utf-8
#!/usr/bin/python
# TVBox 双壳兼容 Python 爬虫
# 兼容: FongMi/TV (T3) + OK影视/PyramidStore (T4)
# 目标: https://mm.gi-my.net 全民VIP写真网

import sys
import json
import re
import html
from urllib import request, parse

# 兼容 T3/T4 路径
sys.path.append('..')
try:
    from base.spider import Spider
except:
    pass

class Spider(Spider):
    def __init__(self):
        self.siteUrl = "https://mm.gi-my.net"
        self.header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://mm.gi-my.net/"
        }

    def getName(self):
        return "全民VIP写真"

    def init(self, extend=""):
        # extend 可传入额外配置
        if extend and extend.startswith("http"):
            self.siteUrl = extend.rstrip("/")
        pass

    def isVideoFormat(self, url):
        # 判断是否为视频格式
        video_formats = ['.m3u8', '.mp4', '.flv', '.avi', '.mkv', '.ts', '.wmv']
        for fmt in video_formats:
            if fmt in url.lower():
                return True
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        # 首页分类
        classes = [
            {"type_id": "rosi", "type_name": "ROSI视频"},
            {"type_id": "xiuren", "type_name": "秀人VIP"},
            {"type_id": "108tv", "type_name": "108TV酱"},
            {"type_id": "ligui", "type_name": "Ligui丽柜"},
            {"type_id": "other", "type_name": "其他写真"}
        ]

        result = {
            "class": classes,
            "filters": {
                "rosi": [
                    {"key": "sort", "name": "排序", "value": [
                        {"n": "最新", "v": "new"},
                        {"n": "最热", "v": "hot"}
                    ]}
                ],
                "xiuren": [
                    {"key": "sort", "name": "排序", "value": [
                        {"n": "最新", "v": "new"},
                        {"n": "最热", "v": "hot"}
                    ]}
                ],
                "108tv": [
                    {"key": "sort", "name": "排序", "value": [
                        {"n": "最新", "v": "new"},
                        {"n": "最热", "v": "hot"}
                    ]}
                ],
                "ligui": [
                    {"key": "sort", "name": "排序", "value": [
                        {"n": "最新", "v": "new"},
                        {"n": "最热", "v": "hot"}
                    ]}
                ],
                "other": [
                    {"key": "sort", "name": "排序", "value": [
                        {"n": "最新", "v": "new"},
                        {"n": "最热", "v": "hot"}
                    ]}
                ]
            }
        }
        return json.dumps(result, ensure_ascii=False)

    def homeVideoContent(self):
        # 首页推荐视频
        result = {"list": []}
        try:
            url = self.siteUrl
            html_content = self.fetch(url)
            videos = self.parseList(html_content)
            result["list"] = videos[:12]  # 取前12个
        except Exception as e:
            print(f"homeVideoContent error: {e}")
        return json.dumps(result, ensure_ascii=False)

    def categoryContent(self, tid, pg, filter, extend):
        # 分类列表
        result = {"list": [], "pagecount": 999}
        try:
            # 构造分类URL，根据实际网站结构调整
            url = f"{self.siteUrl}/category/{tid}/page/{pg}"
            if tid == "rosi":
                url = f"{self.siteUrl}/rosi/page/{pg}"
            elif tid == "xiuren":
                url = f"{self.siteUrl}/xiuren/page/{pg}"
            elif tid == "108tv":
                url = f"{self.siteUrl}/108tv/page/{pg}"
            elif tid == "ligui":
                url = f"{self.siteUrl}/ligui/page/{pg}"
            elif tid == "other":
                url = f"{self.siteUrl}/other/page/{pg}"

            html_content = self.fetch(url)
            videos = self.parseList(html_content)
            result["list"] = videos
        except Exception as e:
            print(f"categoryContent error: {e}")
        return json.dumps(result, ensure_ascii=False)

    def detailContent(self, ids):
        # 详情页
        result = {"list": []}
        try:
            vid = ids[0]
            url = f"{self.siteUrl}/video/{vid}"
            if vid.startswith("http"):
                url = vid

            html_content = self.fetch(url)
            vod = self.parseDetail(html_content, vid)
            result["list"] = [vod]
        except Exception as e:
            print(f"detailContent error: {e}")
        return json.dumps(result, ensure_ascii=False)

    def searchContent(self, key, quick, pg="1"):
        # 搜索
        result = {"list": [], "pagecount": 999}
        try:
            search_url = f"{self.siteUrl}/search/{parse.quote(key)}/page/{pg}"
            html_content = self.fetch(search_url)
            videos = self.parseList(html_content)
            result["list"] = videos
        except Exception as e:
            print(f"searchContent error: {e}")
        return json.dumps(result, ensure_ascii=False)

    def playerContent(self, flag, id, vipFlags):
        # 播放解析
        result = {}
        try:
            if id.startswith("http"):
                # 直接是视频链接
                if self.isVideoFormat(id):
                    result = {
                        "parse": 0,
                        "url": id,
                        "header": self.header
                    }
                else:
                    # 需要进一步解析
                    result = {
                        "parse": 1,
                        "url": id,
                        "header": self.header
                    }
            else:
                # 是相对路径或ID
                result = {
                    "parse": 1,
                    "url": f"{self.siteUrl}{id}",
                    "header": self.header
                }
        except Exception as e:
            print(f"playerContent error: {e}")
            result = {"parse": 0, "url": id}
        return json.dumps(result, ensure_ascii=False)

    def liveContent(self, url):
        return ""

    def action(self, action):
        return ""

    def destroy(self):
        pass

    # ========== T3 (FongMi) 代理方法 ==========
    def proxy(self, param):
        # T3 使用 proxy
        return self.localProxy(param)

    # ========== T4 (PyramidStore) 代理方法 ==========
    def localProxy(self, param):
        action = {
            'url': '',
            'header': '',
            'param': '',
            'type': 'string',
            'after': ''
        }
        return [200, "video/MP2T", action, ""]

    # ========== 工具方法 ==========
    def fetch(self, url):
        req = request.Request(url, headers=self.header)
        with request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')

    def parseList(self, html):
        """
        解析视频列表
        需要根据实际网站HTML结构调整正则/解析逻辑
        """
        videos = []

        # 示例解析逻辑 - 根据实际网站结构调整
        # 匹配视频卡片
        patterns = [
            # 常见的视频列表匹配模式
            r'<a[^>]*href=["']([^"']*video[^"']*|[^"']*watch[^"']*)["'][^>]*>.*?<img[^>]*src=["']([^"']*)["'][^>]*>.*?<h[1-6][^>]*>(.*?)</h[1-6]>',
            r'<div[^>]*class=["'][^"']*video[^"']*["'][^>]*>.*?<a[^>]*href=["']([^"']*)["'][^>]*>.*?<img[^>]*src=["']([^"']*)["'][^>]*>.*?<[^>]*class=["'][^"']*title[^"']*["'][^>]*>(.*?)</[^>]*>',
            r'<article[^>]*>.*?<a[^>]*href=["']([^"']*)["'][^>]*>.*?<img[^>]*src=["']([^"']*)["'][^>]*>.*?<[^>]*class=["'][^"']*entry-title[^"']*["'][^>]*>(.*?)</[^>]*>.*?</article>',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    if len(match) >= 3:
                        href = html.unescape(match[0].strip())
                        pic = html.unescape(match[1].strip())
                        title = re.sub(r'<[^>]+>', '', match[2]).strip()

                        # 提取视频ID
                        vid = href
                        if "/" in href:
                            vid = href.rstrip("/").split("/")[-1]

                        videos.append({
                            "vod_id": vid,
                            "vod_name": title,
                            "vod_pic": pic,
                            "vod_remarks": "",
                            "type_name": "写真"
                        })
                except Exception:
                    continue
            if videos:
                break

        # 如果正则没有匹配到，尝试备用解析
        if not videos:
            videos = self.parseListFallback(html)

        return videos

    def parseListFallback(self, html):
        """备用解析方法"""
        videos = []

        # 尝试匹配所有包含图片和链接的标签
        img_pattern = r'<img[^>]*src=["']([^"']*)["'][^>]*>'
        link_pattern = r'<a[^>]*href=["']([^"']*)["'][^>]*>(.*?)</a>'

        imgs = re.findall(img_pattern, html)
        links = re.findall(link_pattern, html, re.DOTALL)

        for i, link in enumerate(links[:20]):
            href = link[0].strip()
            text = re.sub(r'<[^>]+>', '', link[1]).strip()
            if text and len(text) > 2 and ("video" in href or "watch" in href or "/" in href):
                pic = imgs[i] if i < len(imgs) else ""
                vid = href.rstrip("/").split("/")[-1] if "/" in href else href
                videos.append({
                    "vod_id": vid,
                    "vod_name": text,
                    "vod_pic": pic,
                    "vod_remarks": "",
                    "type_name": "写真"
                })

        return videos

    def parseDetail(self, html, vid):
        """
        解析详情页
        需要根据实际网站HTML结构调整
        """
        vod = {
            "vod_id": vid,
            "vod_name": "",
            "vod_pic": "",
            "vod_remarks": "",
            "vod_year": "",
            "vod_area": "",
            "vod_director": "",
            "vod_actor": "",
            "vod_content": "",
            "vod_play_from": "写真线路",
            "vod_play_url": ""
        }

        try:
            # 提取标题
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if title_match:
                vod["vod_name"] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            # 提取封面
            pic_match = re.search(r'<img[^>]*src=["']([^"']*)["'][^>]*class=["'][^"']*poster[^"']*["']', html) or                          re.search(r'<meta[^>]*property=["']og:image["'][^>]*content=["']([^"']*)["']', html)
            if pic_match:
                vod["vod_pic"] = html.unescape(pic_match.group(1))

            # 提取描述
            desc_match = re.search(r'<div[^>]*class=["'][^"']*desc[^"']*["'][^>]*>(.*?)</div>', html, re.DOTALL) or                         re.search(r'<meta[^>]*property=["']og:description["'][^>]*content=["']([^"']*)["']', html)
            if desc_match:
                vod["vod_content"] = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()

            # 提取视频链接
            video_urls = []

            # 匹配 m3u8/mp4 直接链接
            video_pattern = r'(https?://[^"'\s<>]*\.m3u8[^"'\s<>]*)|(https?://[^"'\s<>]*\.mp4[^"'\s<>]*)'
            video_matches = re.findall(video_pattern, html)
            for vm in video_matches:
                url = vm[0] or vm[1]
                if url:
                    video_urls.append(("播放", url))

            # 匹配 iframe 嵌入视频
            iframe_pattern = r'<iframe[^>]*src=["']([^"']*)["'][^>]*>'
            iframe_matches = re.findall(iframe_pattern, html)
            for i, iframe_url in enumerate(iframe_matches):
                video_urls.append((f"线路{i+1}", iframe_url))

            # 匹配 video 标签
            video_tag_pattern = r'<video[^>]*>.*?<source[^>]*src=["']([^"']*)["'][^>]*>.*?</video>'
            video_tag_matches = re.findall(video_tag_pattern, html, re.DOTALL)
            for i, vurl in enumerate(video_tag_matches):
                video_urls.append((f"视频{i+1}", vurl))

            # 如果没有找到视频，使用当前页面URL
            if not video_urls:
                video_urls.append(("默认线路", f"{self.siteUrl}/video/{vid}"))

            # 构建播放URL格式: 名称$URL#名称$URL
            play_urls = "#".join([f"{name}${url}" for name, url in video_urls])
            vod["vod_play_url"] = play_urls

        except Exception as e:
            print(f"parseDetail error: {e}")

        return vod


# ========== 配置 ==========
config = {
    "player": {},
    "filter": {}
}

header = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://mm.gi-my.net/"
}
