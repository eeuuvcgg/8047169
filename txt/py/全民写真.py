# -*- coding: utf-8 -*-
"""
全民写真网爬虫
站点: https://mm.gi-my.net
基于苹果CMS系统
"""

import json
import re
import urllib.parse

import requests
from lxml import etree

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass


class Spider(BaseSpider):
    """全民写真网爬虫"""

    BASE_URL = 'https://mm.gi-my.net'

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Referer': 'https://mm.gi-my.net/',
    }

    def __init__(self):
        super().__init__()
        self.name = ""
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ==================== 标准接口 ====================

    def init(self, extend="{}"):
        """初始化"""
        if extend:
            try:
                self.extend = json.loads(extend)
                if 'name' in self.extend:
                    self.name = self.extend['name']
                if 'base_url' in self.extend:
                    self.BASE_URL = self.extend['base_url']
            except Exception as e:
                print(e)
        return None

    def getName(self):
        """获取爬虫名称"""
        return "全民写真网"

    def homeContent(self, filter):
        """首页"""
        result = {
            "class": [],
            "filters": {},
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            # 获取首页内容
            rsp = self._get('/')
            if rsp:
                doc = etree.HTML(rsp)

                # 提取分类
                classes = self._extract_classes(doc)
                result["class"] = classes

                # 提取视频列表
                videos = self._parse_video_list(doc)
                result["list"] = videos[:20]

        except Exception as e:
            print(f"homeContent error: {e}")

        return result

    def categoryContent(self, tid, pg, filter, extend):
        """分类页"""
        result = {
            "page": int(pg),
            "pagecount": 999,
            "limit": 20,
            "total": 99999,
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            # 苹果CMS分类页URL格式
            if pg and int(pg) > 1:
                url = f'/index.php/vod/type/id/{tid}/page/{pg}.html'
            else:
                url = f'/index.php/vod/type/id/{tid}.html'

            rsp = self._get(url)
            if rsp:
                doc = etree.HTML(rsp)
                videos = self._parse_video_list(doc)
                result["list"] = videos

        except Exception as e:
            print(f"categoryContent error: {e}")

        return result

    def detailContent(self, ids):
        """详情页"""
        result = {
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            vid = ids[0]
            url = f'/index.php/vod/detail/id/{vid}.html'
            rsp = self._get(url)

            if rsp:
                doc = etree.HTML(rsp)

                # 标题
                title = self._get_text(doc, [
                    '//h1/text()',
                    '//h2/text()',
                    '//title/text()',
                ])
                if title:
                    title = title.split('-')[0].strip()

                # 海报 - 从data-original属性获取
                pic = self._get_text(doc, [
                    '//img[contains(@class,"hl-lazy")]/@data-original',
                    '//div[contains(@class,"pic")]//img/@data-original',
                    '//div[contains(@class,"pic")]//img/@src',
                    '//meta[@property="og:image"]/@content',
                ])
                if pic and pic.startswith('/'):
                    pic = self.BASE_URL + pic

                # 主演
                actor = self._get_text(doc, [
                    '//span[contains(text(),"主演")]/following-sibling::*//text()',
                ])

                # 导演
                director = self._get_text(doc, [
                    '//span[contains(text(),"导演")]/following-sibling::*//text()',
                ])

                # 类型
                type_name = self._get_text(doc, [
                    '//span[contains(text(),"类型")]/following-sibling::*//text()',
                ])

                # 简介
                desc = self._get_text(doc, [
                    '//div[contains(@class,"content")]/text()',
                    '//div[contains(@class,"desc")]/text()',
                ])

                # 播放链接 - 全民写真网结构
                play_from = []
                play_urls = []

                # 提取播放源名称 - 从 hl-plays-from 获取
                source_tabs = doc.xpath('//div[contains(@class,"hl-plays-from")]//a')
                source_names = []
                for tab in source_tabs:
                    name = tab.xpath('./@alt | .//text()')
                    if name:
                        source_names.append(name[0].strip())

                # 提取播放列表 - 从 hl-plays-list 获取
                playlist_ul = doc.xpath('//ul[contains(@class,"hl-plays-list")]')

                if playlist_ul:
                    for idx, playlist in enumerate(playlist_ul):
                        source_name = source_names[idx] if idx < len(source_names) else "默认播放源"
                        episode_links = playlist.xpath('.//a')
                        if episode_links:
                            play_from.append(source_name)
                            episodes = []
                            for ep in episode_links:
                                ep_title = ep.xpath('.//text()')
                                ep_title = ep_title[0].strip() if ep_title else "播放"
                                ep_url = ep.xpath('./@href')
                                if ep_url:
                                    full_url = ep_url[0] if ep_url[0].startswith('http') else self.BASE_URL + ep_url[0]
                                    episodes.append(f"{ep_title}${full_url}")
                            play_urls.append('#'.join(episodes))

                if not play_from:
                    play_links = doc.xpath('//a[contains(@href,"/play/")]')
                    if play_links:
                        play_from.append("默认播放源")
                        episodes = []
                        for link in play_links:
                            ep_title = link.xpath('.//text()')
                            ep_title = ep_title[0].strip() if ep_title else "播放"
                            ep_url = link.xpath('./@href')
                            if ep_url:
                                full_url = ep_url[0] if ep_url[0].startswith('http') else self.BASE_URL + ep_url[0]
                                episodes.append(f"{ep_title}${full_url}")
                        play_urls.append('#'.join(episodes))

                vod = {
                    "vod_id": vid,
                    "vod_name": title,
                    "vod_pic": pic,
                    "type_name": type_name,
                    "vod_year": "",
                    "vod_area": "",
                    "vod_remarks": "",
                    "vod_actor": actor,
                    "vod_director": director,
                    "vod_content": desc,
                    "vod_play_from": '$$'.join(play_from) if play_from else "默认播放源",
                    "vod_play_url": '$$$$$'.join(play_urls) if play_urls else "",
                }
                result["list"].append(vod)

        except Exception as e:
            print(f"detailContent error: {e}")

        return result

    def searchContent(self, key, quick, pg="1"):
        """搜索"""
        result = {
            "page": int(pg),
            "pagecount": 999,
            "limit": 20,
            "total": 99999,
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            # 搜索URL格式: /index.php/vod/search/wd/{keyword}.html
            encoded_key = urllib.parse.quote(key)
            url = f'/index.php/vod/search/wd/{encoded_key}.html'

            rsp = self._get(url)
            if rsp:
                doc = etree.HTML(rsp)
                videos = self._parse_video_list(doc)
                result["list"] = videos

        except Exception as e:
            print(f"searchContent error: {e}")

        return result

    def playerContent(self, flag, id, vipFlags):
        """播放页"""
        result = {
            "parse": 0,
            "playUrl": "",
            "url": "",
            "jx": 0,
            "header": "",
        }

        try:
            if id.startswith('http'):
                if '.m3u8' in id or '.mp4' in id:
                    result["url"] = id
                    result["parse"] = 0
                    return result

                rsp = self._get_page(id)
                if rsp:
                    video_url = self._extract_video_url(rsp)
                    if video_url:
                        result["url"] = video_url
                        result["parse"] = 0
                        return result

                result["url"] = id
                result["parse"] = 1
                return result

            # 如果是相对路径
            if id.startswith('/'):
                full_url = self.BASE_URL + id
            else:
                full_url = self.BASE_URL + f'/index.php/vod/play/id/{id}.html'

            rsp = self._get_page(full_url)
            if rsp:
                video_url = self._extract_video_url(rsp)
                if video_url:
                    result["url"] = video_url
                    result["parse"] = 0
                    return result

            result["url"] = full_url
            result["parse"] = 1

        except Exception as e:
            print(f"playerContent error: {e}")
            result["url"] = id
            result["parse"] = 1

        return result

    # ==================== 内部方法 ====================

    def _get(self, path, encoding='utf-8'):
        """发送GET请求"""
        url = self.BASE_URL + path
        try:
            r = self.session.get(url, timeout=15, verify=False)
            r.encoding = encoding
            return r.text
        except Exception as e:
            print(f"Request error: {url}, {e}")
            return None

    def _get_page(self, url, encoding='utf-8'):
        """请求完整URL"""
        try:
            r = self.session.get(url, timeout=15, verify=False)
            r.encoding = encoding
            return r.text
        except Exception as e:
            print(f"Request error: {url}, {e}")
            return None

    def _extract_classes(self, doc):
        """提取分类"""
        classes = []
        try:
            nav_links = doc.xpath('//a[contains(@href,"/type/id/")]')
            seen = set()

            for link in nav_links:
                href = link.xpath('./@href')
                if not href:
                    continue
                href = href[0]

                match = re.search(r'/type/id/(\d+)', href)
                if not match:
                    continue
                tid = match.group(1)

                if tid in seen:
                    continue
                seen.add(tid)

                name = link.xpath('.//text()')
                name = name[0].strip() if name else ""
                if not name:
                    continue

                classes.append({
                    "type_id": tid,
                    "type_name": name,
                })

        except Exception as e:
            print(f"Extract classes error: {e}")

        return classes

    def _parse_video_list(self, doc):
        """解析视频列表"""
        videos = []
        try:
            # 查找所有视频项 - 全民写真网使用 hl-list-item
            items = doc.xpath('//li[contains(@class,"hl-list-item")]')

            if not items:
                items = doc.xpath('//a[contains(@href,"/detail/id/")]//..')

            seen = set()

            for item in items:
                try:
                    link = item.xpath('.//a[contains(@href,"/detail/id/")]')
                    if not link:
                        continue
                    link = link[0]

                    href = link.xpath('./@href')
                    if not href:
                        continue
                    href = href[0]

                    match = re.search(r'/id/(\d+)', href)
                    if not match:
                        continue
                    vid = match.group(1)

                    if vid in seen:
                        continue
                    seen.add(vid)

                    # 标题 - 从title属性获取
                    title = link.xpath('./@title')
                    if not title:
                        title = item.xpath('.//div[contains(@class,"hl-item-title")]//a/@title')
                    if not title:
                        title = item.xpath('.//div[contains(@class,"hl-item-title")]//a/text()')
                    if isinstance(title, list):
                        title = title[0].strip() if title else ""
                    if not title:
                        continue

                    # 图片 - 从data-original属性获取
                    pic = link.xpath('./@data-original')
                    if not pic:
                        pic = link.xpath('.//img/@data-original')
                    if not pic:
                        pic = link.xpath('.//img/@src')
                    if isinstance(pic, list):
                        pic = pic[0] if pic else ""
                    if pic and pic.startswith('/'):
                        pic = self.BASE_URL + pic

                    # 备注
                    remarks = item.xpath('.//span[contains(@class,"remarks")]/text()')
                    if not remarks:
                        remarks = item.xpath('.//div[contains(@class,"hl-item-sub")]/text()')
                    remarks = remarks[0].strip() if remarks else ""

                    videos.append({
                        "vod_id": vid,
                        "vod_name": title,
                        "vod_pic": pic,
                        "vod_remarks": remarks,
                    })
                except Exception:
                    continue

        except Exception as e:
            print(f"Parse video list error: {e}")

        return videos

    def _extract_video_url(self, html_content):
        """从HTML中提取视频URL"""
        try:
            # 全民写真网使用 player_aaaa 变量存储播放信息
            player_match = re.search(r'var\s+player_aaaa\s*=\s*(\{[^}]+\})', html_content)
            if player_match:
                try:
                    player_data = json.loads(player_match.group(1))
                    video_url = player_data.get('url', '')
                    if video_url:
                        video_url = video_url.replace('\\/', '/')
                        return video_url
                except Exception:
                    pass

            # 通用 player_data 变量
            player_match = re.search(r'var\s+player_data\s*=\s*["\']([^"\']+)["\']', html_content)
            if player_match:
                return player_match.group(1)

            # 查找m3u8链接
            m3u8_match = re.search(r'(https?://[^\s"\'\\]+\.m3u8[^\s"\'\\]*)', html_content)
            if m3u8_match:
                return m3u8_match.group(1)

            # 查找mp4链接
            mp4_match = re.search(r'(https?://[^\s"\'\\]+\.mp4[^\s"\'\\]*)', html_content)
            if mp4_match:
                return mp4_match.group(1)

        except Exception as e:
            print(f"Extract video URL error: {e}")

        return None

    def _get_text(self, doc, selectors):
        """通用文本提取"""
        for selector in selectors:
            try:
                texts = doc.xpath(selector)
                for text in texts:
                    if text and str(text).strip():
                        return str(text).strip()
            except Exception:
                continue
        return ''


# 调试用
if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    s = Spider()
    s.init()

    print('=== 首页 ===')
    home = s.homeContent(True)
    print(f'分类: {len(home["class"])}个')
    for c in home['class'][:10]:
        print(f'  {c["type_id"]}: {c["type_name"]}')
    print(f'推荐: {len(home["list"])}个')
    for v in home['list'][:5]:
        print(f'  {v["vod_id"]}: {v["vod_name"]}')