# coding=utf-8
#!/usr/bin/python
"""
影视影院 (qddzgm.com) dr_py 爬虫源
==================================
站点：https://www.qddzgm.com
CMS：MacCMS（苹果CMS）
特点：需移动端UA访问（桌面UA返回404）；播放页 player_aaaa JSON 含 m3u8 直链
依赖：仅 Python 标准库（urllib）
"""
import sys
import os
import re
import json
import ssl
import urllib.request
import urllib.error
import http.cookiejar
from urllib.parse import unquote, quote
from html import unescape

# dr_py 基类兼容（独立运行时用空基类兜底）
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass


# ============================================================
#  urllib 响应包装（模拟 requests.Response 的基本用法）
# ============================================================
class _Response:
    def __init__(self, resp):
        self.status_code = resp.getcode()
        self._raw = resp.read()
        self.headers = resp.headers
        ct = resp.headers.get("Content-Type", "") if resp.headers else ""
        self.encoding = "utf-8"
        if "charset=" in ct:
            try:
                self.encoding = ct.split("charset=")[-1].split(";")[0].strip()
            except Exception:
                pass

    @property
    def text(self):
        try:
            return self._raw.decode(self.encoding)
        except Exception:
            return self._raw.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


# ============================================================
#  爬虫主类
# ============================================================
class Spider(BaseSpider):

    def getName(self):
        return "影视影院"

    def init(self, extend=""):
        self.host = "https://www.qddzgm.com"
        # 移动端UA（桌面UA返回404）
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': self.host + '/',
        }
        # 分类（站点 /news/{pinyin}.html 导航对应）
        self.categories = [
            {'type_id': 'dianying', 'type_name': '电影'},
            {'type_id': 'dianshiju', 'type_name': '电视剧'},
            {'type_id': 'zongyi', 'type_name': '综艺'},
            {'type_id': 'dongman', 'type_name': '动漫'},
            {'type_id': 'duanjudaquan', 'type_name': '短剧大全'},
        ]
        self.timeout = 15

        # urllib opener（带 cookie + 忽略 SSL 验证）
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
            urllib.request.HTTPSHandler(context=self._ctx),
        )

        self.log("影视影院爬虫初始化完成，Host: %s" % self.host)

    # ---------- 六接口 ----------
    def homeContent(self, filter):
        """获取首页内容和分类"""
        result = {}
        result['class'] = self.categories
        try:
            videos = self._scrape_home()
            result['list'] = videos
        except Exception as e:
            self.log("首页获取出错: %s" % str(e))
            result['list'] = []
        return result

    def homeVideoContent(self):
        """首页视频列表（不含分类）"""
        try:
            videos = self._scrape_home()
            return {'list': videos}
        except Exception as e:
            self.log("首页视频获取出错: %s" % str(e))
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容 - 通过 /news/{pinyin}/page/{n}.html 获取"""
        try:
            page = int(pg) if pg else 1
            if page < 1:
                page = 1
            videos = self._scrape_list(tid=tid, page=page)
            has_more = len(videos) >= 10
            return {
                'list': videos,
                'page': page,
                'pagecount': page + 1 if has_more else page,
                'limit': 20,
                'total': 99999 if has_more else len(videos)
            }
        except Exception as e:
            self.log("分类内容获取出错: %s" % str(e))
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        """搜索功能 - 通过 /vodsearch/{keyword}/ 获取"""
        try:
            page = int(pg) if pg else 1
            videos = self._scrape_search(keyword=key)
            return {
                'list': videos,
                'page': page,
                'pagecount': 999 if len(videos) >= 20 else page,
                'limit': 20,
                'total': 99999 if len(videos) >= 20 else len(videos)
            }
        except Exception as e:
            self.log("搜索出错: %s" % str(e))
            return {'list': []}

    def detailContent(self, ids):
        """详情页面 - 抓取 /article/{id}.html 并解析"""
        try:
            vod_id = ids[0]
            url = "%s/article/%s.html" % (self.host, vod_id)
            self.log("访问详情页: %s" % url)

            rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
            if not rsp or rsp.status_code != 200:
                # 尝试 /case/{id}.html
                url = "%s/case/%s.html" % (self.host, vod_id)
                self.log("尝试备用URL: %s" % url)
                rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
                if not rsp or rsp.status_code != 200:
                    self.log("详情页请求失败")
                    return {'list': []}

            html_text = rsp.text

            # 解析影片元信息
            info = self._parse_detail_info(html_text)

            # 解析播放列表（MacCMS con_playlist 结构）
            play_from_list = []
            play_url_list = []
            source_pattern = re.compile(r'id="#con_playlist_(\d+)"[^>]*>(.*?)</a>', re.S)
            sources = source_pattern.findall(html_text)
            seen_sids = set()
            for sid, src_name in sources:
                if sid in seen_sids:
                    continue
                seen_sids.add(sid)
                src_name = self._clean(src_name)
                if not src_name:
                    src_name = "播放源" + str(sid)
                # 查找对应的剧集列表
                ep_pattern = re.compile(
                    r'id="con_playlist_%s"[^>]*>(.*?)</ul>' % re.escape(sid), re.S
                )
                ep_match = ep_pattern.search(html_text)
                if ep_match:
                    ep_html = ep_match.group(1)
                    ep_links = re.findall(
                        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', ep_html, re.S
                    )
                    episodes = []
                    for ep_url, ep_name in ep_links:
                        ep_name = self._clean(ep_name)
                        if not ep_name or not ep_url:
                            continue
                        if "javascript" in ep_url:
                            continue
                        ep_url = self._full_url(ep_url)
                        episodes.append("%s$%s" % (ep_name, ep_url))
                    if episodes:
                        # 站点HTML剧集为倒序（第N集→第1集），反转成正序
                        episodes.reverse()
                        play_from_list.append(src_name)
                        play_url_list.append("#".join(episodes))

            return {
                'list': [{
                    'vod_id': vod_id,
                    'vod_name': info.get('vod_name', '') or vod_id,
                    'vod_pic': info.get('vod_pic', ''),
                    'type_name': info.get('type_name', ''),
                    'vod_year': info.get('vod_year', ''),
                    'vod_area': info.get('vod_area', ''),
                    'vod_remarks': info.get('vod_remarks', ''),
                    'vod_actor': info.get('vod_actor', ''),
                    'vod_director': info.get('vod_director', ''),
                    'vod_lang': info.get('vod_lang', ''),
                    'vod_content': info.get('vod_content', ''),
                    'vod_play_from': '$$$'.join(play_from_list),
                    'vod_play_url': '$$$'.join(play_url_list),
                }]
            }
        except Exception as e:
            self.log("详情获取出错: %s" % str(e))
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        """播放链接 - 从播放页 player_aaaa JSON 提取 m3u8 直链"""
        try:
            self.log("获取播放链接: flag=%s, id=%s" % (flag, id[:50] if id else ''))

            # 如果已经是视频直链，直接返回
            if self._is_video_format(id):
                return {
                    'parse': 0,
                    'playUrl': '',
                    'url': id,
                    'header': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.host + '/'
                    }
                }

            play_url = self._full_url(id)
            rsp = self.fetch(play_url, headers=self.headers, timeout=self.timeout)
            if not rsp or rsp.status_code != 200:
                return {'parse': 0, 'playUrl': '', 'url': '', 'msg': '播放页请求失败'}

            html_text = rsp.text
            video_url = ''

            # 策略1: player_aaaa JSON（MacCMS 标准方式）
            m = re.search(r'player_aaaa\s*=\s*(\{.*?\})', html_text, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, dict):
                        for k in ('url', 'src', 'source', 'playUrl', 'videoUrl'):
                            if k in data and data[k]:
                                video_url = data[k]
                                break
                except (json.JSONDecodeError, ValueError):
                    pass

            # 策略2: iframe src
            if not video_url:
                m = re.search(r'<iframe[^>]*src="([^"]*)"', html_text, re.I)
                if m:
                    candidate = m.group(1)
                    if self._is_video_format(candidate) or "player" in candidate.lower():
                        video_url = candidate

            # 策略3: video/source src
            if not video_url:
                m = re.search(r'<(?:video|source)[^>]*src="([^"]*)"', html_text, re.I)
                if m:
                    video_url = m.group(1)

            # 策略4: 直接匹配 m3u8
            if not video_url:
                m = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html_text, re.I)
                if m:
                    video_url = m.group(1)

            # 策略5: 直接匹配 mp4
            if not video_url:
                m = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html_text, re.I)
                if m:
                    video_url = m.group(1)

            # 策略6: JavaScript 变量
            if not video_url:
                m = re.search(
                    r'(?:url|src|source|playUrl|videoUrl)\s*[:=]\s*["\']([^"\']+)["\']',
                    html_text, re.I
                )
                if m:
                    video_url = m.group(1)

            if video_url:
                if not video_url.startswith("http"):
                    video_url = self._full_url(video_url)
                parse_flag = 0 if self._is_video_format(video_url) else 1
                self.log("获取到视频地址: %s" % video_url[:80])
                return {
                    'parse': parse_flag,
                    'playUrl': '',
                    'url': video_url,
                    'header': {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.host + '/'
                    }
                }
            else:
                self.log("未找到可用播放地址")
                return {'parse': 0, 'playUrl': '', 'url': '', 'msg': '无可用播放地址'}
        except Exception as e:
            self.log("播放链接获取出错: %s" % str(e))
            return {'parse': 0, 'playUrl': '', 'url': ''}

    # ---------- 私有抓取方法 ----------
    def _scrape_home(self):
        """抓取首页推荐影片"""
        url = self.host + "/"
        self.log("抓取首页: %s" % url)
        rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
        if not rsp or rsp.status_code != 200:
            self.log("首页请求失败")
            return []
        videos = self._parse_vod_cards(rsp.text)
        self.log("首页解析到 %d 个影片" % len(videos))
        return videos

    def _scrape_list(self, tid='dianying', page=1):
        """抓取 /news/{pinyin}/page/{n}.html 分类列表页"""
        if page > 1:
            url = "%s/news/%s/page/%d.html" % (self.host, tid, page)
        else:
            url = "%s/news/%s.html" % (self.host, tid)
        self.log("抓取分类页: %s" % url)
        rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
        if not rsp or rsp.status_code != 200:
            self.log("分类页请求失败")
            return []
        videos = self._parse_vod_cards(rsp.text)
        self.log("分类页解析到 %d 个影片" % len(videos))
        return videos

    def _scrape_search(self, keyword=''):
        """抓取 /vodsearch/{keyword}/ 搜索页"""
        url = "%s/vodsearch/%s/" % (self.host, quote(keyword))
        self.log("抓取搜索页: %s" % url)
        rsp = self.fetch(url, headers=self.headers, timeout=self.timeout)
        if not rsp or rsp.status_code != 200:
            self.log("搜索页请求失败")
            return []
        videos = self._parse_vod_cards(rsp.text)
        # 搜索页可能返回详情页结构，尝试 fallback 提取单个视频
        if not videos:
            html_text = rsp.text
            m = re.search(r'data-id="(\d+)"', html_text)
            if m:
                vid = m.group(1)
                title = ''
                title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html_text, re.S)
                if title_m:
                    title = self._clean(title_m.group(1))
                if not title:
                    title = keyword
                pic = ''
                img_m = re.search(
                    r'<div[^>]*class="[^"]*video-pic[^"]*"[^>]*>\s*<img[^>]*src="([^"]*)"',
                    html_text, re.S
                )
                if img_m:
                    pic = self._full_url(img_m.group(1))
                videos.append({
                    'vod_id': vid,
                    'vod_name': title,
                    'vod_pic': pic,
                    'vod_remarks': '',
                    'vod_year': ''
                })
        self.log("搜索页解析到 %d 个影片" % len(videos))
        return videos

    # ---------- 私有解析方法 ----------
    def _parse_vod_cards(self, html_text):
        """从分类/首页/搜索 HTML 解析影片卡片
        支持 /article/{id}.html（首页）和 /case/{id}.html（分类页）两种链接格式
        """
        videos = []
        try:
            # 模式1: <a class="pic-img" href=".../(article|case)/{id}.html" title="{title}">
            pattern = re.compile(
                r'<a\s+class="pic-img"\s+href="[^"]*/(?:article|case)/(\d+)\.html"[^>]*?title="([^"]*)"',
                re.S
            )
            seen = set()
            for m in pattern.finditer(html_text):
                vid = m.group(1)
                title = m.group(2).strip()
                if vid and vid not in seen:
                    seen.add(vid)
                    videos.append({
                        'vod_id': vid,
                        'vod_name': title,
                        'vod_pic': '',
                        'vod_remarks': '',
                        'vod_year': ''
                    })

            # 模式2: <h3 class="name..."><a href=".../(article|case)/{id}.html">{title}</a></h3>
            if not videos:
                pattern2 = re.compile(
                    r'<h3[^>]*class="[^"]*name[^"]*"[^>]*>\s*<a\s+href="[^"]*/(?:article|case)/(\d+)\.html"[^>]*>(.*?)</a>',
                    re.S
                )
                seen2 = set()
                for m in pattern2.finditer(html_text):
                    vid = m.group(1)
                    title = self._clean(m.group(2))
                    if vid and vid not in seen2:
                        seen2.add(vid)
                        videos.append({
                            'vod_id': vid,
                            'vod_name': title,
                            'vod_pic': '',
                            'vod_remarks': '',
                            'vod_year': ''
                        })

            # 模式3: 宽泛匹配所有 /article/ 或 /case/ 数字链接
            if not videos:
                pattern3 = re.compile(r'href="[^"]*/(?:article|case)/(\d+)\.html"')
                seen3 = set()
                for m in pattern3.finditer(html_text):
                    vid = m.group(1)
                    if vid not in seen3:
                        seen3.add(vid)
                        videos.append({
                            'vod_id': vid,
                            'vod_name': '',
                            'vod_pic': '',
                            'vod_remarks': '',
                            'vod_year': ''
                        })

            # 提取封面图和标题补充
            for v in videos:
                vid = v['vod_id']
                if not v['vod_pic'] or not v['vod_name']:
                    pos_pattern = re.compile(
                        r'href="[^"]*/(?:article|case)/%s\.html"' % re.escape(vid)
                    )
                    pos_match = pos_pattern.search(html_text)
                    if pos_match:
                        start = max(0, pos_match.start() - 500)
                        end = min(len(html_text), pos_match.end() + 500)
                        context = html_text[start:end]
                        # 封面图：优先 data-original（懒加载），其次 src
                        if not v['vod_pic']:
                            img_m = re.search(r'data-original="([^"]*)"', context)
                            if img_m and img_m.group(1):
                                v['vod_pic'] = self._full_url(img_m.group(1))
                            else:
                                img_m = re.search(r'<img[^>]*src="([^"]*)"[^>]*>', context)
                                if img_m and "pic.png" not in img_m.group(1):
                                    v['vod_pic'] = self._full_url(img_m.group(1))
                        # 标题补充
                        if not v['vod_name']:
                            title_m = re.search(r'title="([^"]*)"', context)
                            if title_m:
                                v['vod_name'] = title_m.group(1)
                            else:
                                alt_m = re.search(r'alt="([^"]*)"', context)
                                if alt_m:
                                    v['vod_name'] = alt_m.group(1)

            return videos
        except Exception as e:
            self.log("解析影片卡片出错: %s" % str(e))
            return videos

    def _parse_detail_info(self, html_text):
        """从详情页 HTML 提取影片元信息（MacCMS 标签格式）"""
        info = {}
        # 标题：先 h1，再 title
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html_text, re.S)
        info['vod_name'] = self._clean(m.group(1)) if m else ''
        if not info['vod_name']:
            m = re.search(r'<title>(.*?)</title>', html_text, re.S)
            info['vod_name'] = m.group(1).split("-")[0].strip() if m else ''

        # 封面: <div class="pic-img video-pic"><img src="{cover}" ...>
        pic = ''
        m = re.search(
            r'<div[^>]*class="[^"]*video-pic[^"]*"[^>]*>\s*<img[^>]*src="([^"]*)"',
            html_text, re.S
        )
        if m:
            pic = m.group(1)
        if not pic:
            m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html_text, re.I)
            if m:
                pic = m.group(1)
        info['vod_pic'] = self._full_url(pic) if pic else ''

        # 各字段（MacCMS 格式: <span class="text-muted">状态：</span>值）
        info['vod_remarks'] = self._extract_field(html_text, "状态")
        info['type_name'] = self._extract_field(html_text, "类型")
        info['vod_actor'] = self._extract_field(html_text, "主演")
        info['vod_director'] = self._extract_field(html_text, "导演")
        info['vod_year'] = self._extract_field(html_text, "年代")
        info['vod_area'] = self._extract_field(html_text, "国家地区")
        info['vod_lang'] = self._extract_field(html_text, "语言字幕")
        info['vod_content'] = self._extract_field(html_text, "简介")

        return info

    # ---------- 辅助方法 ----------
    def _clean(self, text):
        """清理HTML标签、解码HTML实体、合并空白"""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()
        try:
            text = unescape(text)
        except Exception:
            pass
        return text

    def _extract_field(self, html_text, label):
        """从HTML中提取带标签的字段值（如 状态：xxx）
        非贪婪匹配，遇到下一个"中文词:"或行尾时停止
        """
        # 替换标签为换行，合并空白
        text = re.sub(r"<[^>]+>", "\n", html_text)
        text = re.sub(r"[ \t]+", " ", text)
        field_re = r"%s\s*[:：]\s*(.+?)(?=\s+[\u4e00-\u9fff]{1,6}\s*[:：]|\n|$)" % re.escape(label)
        m = re.search(field_re, text)
        if m:
            return self._clean(m.group(1))
        # 回退：整段文本中匹配
        text2 = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text))
        m = re.search(field_re, text2)
        if m:
            return self._clean(m.group(1))
        return ""

    def _is_video_format(self, url):
        """判断URL是否为直接视频格式"""
        if not url:
            return False
        return re.search(
            r'\.(m3u8|mp4|flv|avi|mkv|ts|mov|wmv|rm|rmvb|mpg|mpeg|webm|f4v|3gp)(\?|#|$)',
            url, re.IGNORECASE
        ) is not None

    def _full_url(self, url):
        """将相对URL转换为绝对URL"""
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.host + url
        return self.host + "/" + url

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def log(self, message):
        print("[影视影院] %s" % message)

    def fetch(self, url, headers=None, method='GET', data=None, timeout=10):
        """统一网络请求（urllib 实现，零第三方依赖）"""
        try:
            if headers is None:
                headers = self.headers
            req = urllib.request.Request(url, headers=headers, method=method)
            if data:
                req.data = data.encode() if isinstance(data, str) else data
            resp = self._opener.open(req, timeout=timeout)
            return _Response(resp)
        except Exception as e:
            self.log("网络请求失败: %s, 错误: %s" % (url, str(e)))
            return None


# ============================================================
#  独立测试入口
# ============================================================
if __name__ == '__main__':
    spider = Spider()
    spider.init()

    print("=" * 60)
    print("测试1: 首页内容")
    print("=" * 60)
    home = spider.homeContent(False)
    print("分类数: %d" % len(home.get('class', [])))
    print("影片数: %d" % len(home.get('list', [])))
    if home.get('list'):
        v = home['list'][0]
        print("第一个影片: id=%s, name=%s" % (v['vod_id'], v['vod_name'][:40]))

    print("\n" + "=" * 60)
    print("测试2: 分类（电影）")
    print("=" * 60)
    cat = spider.categoryContent('dianying', '1', False, {})
    print("影片数: %d" % len(cat.get('list', [])))

    print("\n" + "=" * 60)
    print("测试3: 搜索（斗士）")
    print("=" * 60)
    search = spider.searchContent('斗士', False, '1')
    print("搜索结果数: %d" % len(search.get('list', [])))

    print("\n" + "=" * 60)
    print("测试4: 详情页")
    print("=" * 60)
    if home.get('list'):
        test_id = home['list'][0]['vod_id']
        detail = spider.detailContent([test_id])
        if detail.get('list'):
            d = detail['list'][0]
            print("标题: %s" % d.get('vod_name', ''))
            print("导演: %s" % d.get('vod_director', ''))
            print("年份: %s | 地区: %s | 类型: %s" % (
                d.get('vod_year', ''), d.get('vod_area', ''), d.get('type_name', '')))
            print("播放源: %s" % d.get('vod_play_from', ''))
            print("播放链接: %s" % d.get('vod_play_url', '')[:80])

            if d.get('vod_play_url'):
                print("\n" + "=" * 60)
                print("测试5: 播放链接")
                print("=" * 60)
                first_ep = d['vod_play_url'].split("$$$")[0].split("#")[0]
                play_id = first_ep.split("$", 1)[1] if "$" in first_ep else ""
                if play_id:
                    play = spider.playerContent('test', play_id, '')
                    print("parse: %s" % play.get('parse', ''))
                    print("url: %s" % play.get('url', '')[:100])
                    if play.get('url', '').endswith('.m3u8'):
                        print("✓ 播放地址获取成功 (m3u8)")
        else:
            print("无详情数据")
