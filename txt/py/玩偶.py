# -*- coding: utf-8 -*-
"""
玩偶|4K (https://wogg.xxooo.cf) — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
站点: https://wogg.xxooo.cf
CMS: 苹果CMS(MacCMS)
特点: 网盘资源聚合站，支持4K高清资源
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
            # 注意：不要提前设置 encoding，让 requests 自动处理 gzip/br 解压
            # 只在最后通过 .text 获取时自动解码
            return r

        def post(self, url, data=None, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.post(url, data=data, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ==================== 常量 ====================
SITE_URL = "https://wogg.xxooo.cf"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
PAGE_SIZE = 72

# 首页分类
CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "剧集"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "4", "type_name": "综艺"},
    {"type_id": "44", "type_name": "臻彩视界"},
    {"type_id": "6", "type_name": "短剧"},
    {"type_id": "5", "type_name": "音乐"},
]

# 筛选配置 — 每个分类带地区/年份/字母/排序等筛选
FILTERS = {
    "1": {
        "地区": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "泰国", "v": "泰国"},
            {"n": "新加坡", "v": "新加坡"},
            {"n": "马来西亚", "v": "马来西亚"},
            {"n": "印度", "v": "印度"},
            {"n": "英国", "v": "英国"},
            {"n": "法国", "v": "法国"},
            {"n": "加拿大", "v": "加拿大"},
            {"n": "西班牙", "v": "西班牙"},
            {"n": "德国", "v": "德国"},
            {"n": "俄罗斯", "v": "俄罗斯"},
            {"n": "澳大利亚", "v": "澳大利亚"},
            {"n": "巴西", "v": "巴西"},
            {"n": "意大利", "v": "意大利"},
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
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
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
    "2": {
        "地区": [
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
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
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
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
    "3": {
        "地区": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "日本", "v": "日本"},
            {"n": "美国", "v": "美国"},
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
    "4": {
        "地区": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
    "44": {
        "地区": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
    "6": {
        "地区": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
    "5": {
        "地区": [
            {"n": "全部", "v": ""},
            {"n": "中国大陆", "v": "中国大陆"},
            {"n": "中国香港", "v": "中国香港"},
            {"n": "中国台湾", "v": "中国台湾"},
            {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"},
            {"n": "日本", "v": "日本"},
            {"n": "其他", "v": "其他"},
        ],
        "年份": [
            {"n": "全部", "v": ""},
            {"n": "2025", "v": "2025"},
            {"n": "2024", "v": "2024"},
            {"n": "2023", "v": "2023"},
            {"n": "2022", "v": "2022"},
            {"n": "2021", "v": "2021"},
            {"n": "2020", "v": "2020"},
            {"n": "更早", "v": "更早"},
        ],
        "字母": [
            {"n": "全部", "v": ""},
            {"n": "A", "v": "A"}, {"n": "B", "v": "B"}, {"n": "C", "v": "C"},
            {"n": "D", "v": "D"}, {"n": "E", "v": "E"}, {"n": "F", "v": "F"},
            {"n": "G", "v": "G"}, {"n": "H", "v": "H"}, {"n": "I", "v": "I"},
            {"n": "J", "v": "J"}, {"n": "K", "v": "K"}, {"n": "L", "v": "L"},
            {"n": "M", "v": "M"}, {"n": "N", "v": "N"}, {"n": "O", "v": "O"},
            {"n": "P", "v": "P"}, {"n": "Q", "v": "Q"}, {"n": "R", "v": "R"},
            {"n": "S", "v": "S"}, {"n": "T", "v": "T"}, {"n": "U", "v": "U"},
            {"n": "V", "v": "V"}, {"n": "W", "v": "W"}, {"n": "X", "v": "X"},
            {"n": "Y", "v": "Y"}, {"n": "Z", "v": "Z"}, {"n": "0-9", "v": "0-9"},
        ],
        "排序": [
            {"n": "按时间", "v": "time"},
            {"n": "按人气", "v": "hits"},
            {"n": "按评分", "v": "score"},
        ],
    },
}


class Spider(Spider):
    """玩偶|4K Spider — 网盘资源聚合站，苹果CMS"""

    def getName(self):
        return "玩偶|4K"

    def init(self, extend=""):
        """初始化，支持代理配置"""
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.siteUrl = SITE_URL

        # 支持从extend解析代理配置
        self.proxy = None
        if self.extend:
            if self.extend.startswith('http://') or self.extend.startswith('https://') or self.extend.startswith('socks'):
                self.proxy = self.extend
            elif self.extend.startswith('proxy='):
                self.proxy = self.extend.split('=', 1)[1]

        self.headers = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Referer': SITE_URL + '/',
            'Upgrade-Insecure-Requests': '1',
        }

    def isVideoFormat(self, url):
        """判断是否为视频格式链接"""
        video_formats = ['.mp4', '.m3u8', '.ts', '.mkv', '.avi', '.webm', '.flv']
        if url and str(url).startswith('http'):
            for fmt in video_formats:
                if fmt in str(url).lower():
                    return True
        return False

    def manualVideoCheck(self):
        """手动视频检查，返回False表示不启用"""
        return False

    # ========== 工具函数 ==========

    @staticmethod
    def _safe_str(val, default=''):
        """安全获取字符串"""
        if val is None or val == '' or val == 'None':
            return default
        return str(val).strip()

    @staticmethod
    def _safe_page(pg, default=1):
        """安全获取页码，确保为正整数"""
        try:
            p = int(pg)
            return p if p > 0 else default
        except Exception:
            return default

    @staticmethod
    def _fix_url(url):
        """修复URL，补全协议或域名"""
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

    def _fetch_html(self, url):
        """获取页面HTML — 带重试和SSL容错

        关键修复: 不发送 Accept-Encoding 头, 避免服务器返回 brotli 压缩数据
        而 requests 库无法自动解压 brotli (除非安装了 brotli 包)
        """
        last_err = None
        # 构造请求头, 去掉 Accept-Encoding, 让 requests 自动协商
        req_headers = {k: v for k, v in self.headers.items() if k.lower() != 'accept-encoding'}
        for attempt in range(3):
            try:
                kw = {}
                if self.proxy:
                    kw['proxies'] = {'http': self.proxy, 'https': self.proxy}
                try:
                    rsp = self.fetch(url, headers=req_headers, timeout=20, verify=False, **kw)
                except TypeError:
                    rsp = self.fetch(url, headers=req_headers, timeout=20, **kw)
                if hasattr(rsp, 'status_code') and rsp.status_code == 404:
                    return ''
                html = rsp.text if hasattr(rsp, 'text') else str(rsp.content, 'utf-8', errors='replace')
                # 去除反爬 display:none
                html = re.sub(r'body\s*\{\s*display\s*:\s*none\s*;?\s*\}', '', html)
                # 去除反爬js
                html = re.sub(r'<script[^>]*nmgb\.[^>]*>.*?</script>', '', html, flags=re.DOTALL)
                return html
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if any(x in err_str for x in ['timeout', 'connection', 'ssl', 'reset', 'closed']):
                    import time
                    time.sleep(1 + attempt)
                    continue
                break
        return ''

    def _parse_list_html(self, html):
        """用BeautifulSoup解析列表页HTML，返回视频列表"""
        videos = []
        if not html:
            return videos

        # 优先使用BeautifulSoup解析
        if BeautifulSoup:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                items = soup.select('.module-item')
                for item in items:
                    # 标题链接: 优先 .module-item-cover .module-item-pic a 的 title，回退 .module-item-content .video-name a
                    vod_name = ''
                    vod_id = ''
                    name_tag = item.select_one('.module-item-cover .module-item-pic a')
                    if not name_tag:
                        name_tag = item.select_one('.module-item-content .video-name a')
                    if name_tag:
                        vod_name = self._safe_str(name_tag.get('title', '') or name_tag.get_text())
                        href = name_tag.get('href', '')
                        if href:
                            # 从href中提取ID: /voddetail/128045.html -> 128045
                            id_match = re.search(r'voddetail/(\d+)', href)
                            if id_match:
                                vod_id = id_match.group(1)
                            else:
                                vod_id = href

                    # 封面图: data-src优先，src回退
                    vod_pic = ''
                    pic_tag = item.select_one('.module-item-pic img')
                    if pic_tag:
                        vod_pic = self._fix_url(
                            pic_tag.get('data-src', '') or pic_tag.get('src', '')
                        )

                    # 备注
                    vod_remarks = ''
                    remark_tag = item.select_one('.module-item-text')
                    if remark_tag:
                        vod_remarks = self._safe_str(remark_tag.get_text())

                    if vod_id:
                        videos.append({
                            'vod_id': vod_id,
                            'vod_name': vod_name,
                            'vod_pic': vod_pic,
                            'vod_remarks': vod_remarks,
                            'type_name': '',
                        })
                return videos
            except Exception:
                pass

        # BeautifulSoup不可用或解析失败时，使用正则回退
        pattern = r'<a[^>]*class="[^"]*video-name[^"]*"[^>]*href="([^"]*voddetail/(\d+)\.html)"[^>]*(?:title="([^"]*)")?[^>]*>'
        matches = re.findall(pattern, html)
        for match in matches:
            href, vod_id, title = match
            videos.append({
                'vod_id': vod_id,
                'vod_name': self._safe_str(title),
                'vod_pic': '',
                'vod_remarks': '',
                'type_name': '',
            })

        return videos

    def _parse_detail_html(self, html):
        """用BeautifulSoup解析详情页HTML，返回影片详情"""
        result = {}
        if not html:
            return result

        if BeautifulSoup:
            try:
                soup = BeautifulSoup(html, 'html.parser')

                # 标题
                title_tag = soup.select_one('.video-info-header > .page-title') or soup.select_one('.page-title')
                if title_tag:
                    result['vod_name'] = self._safe_str(title_tag.get_text())
                else:
                    result['vod_name'] = ''

                # 封面
                pic_tag = soup.select_one('.module-item-pic img')
                if pic_tag:
                    result['vod_pic'] = self._fix_url(
                        pic_tag.get('data-src', '') or pic_tag.get('data-original', '') or pic_tag.get('src', '')
                    )
                else:
                    result['vod_pic'] = ''

                # 地区: .video-info-header a.tag-link 最后一个
                tag_links = soup.select('.video-info-header a.tag-link')
                if tag_links:
                    result['vod_area'] = self._safe_str(tag_links[-1].get_text())
                else:
                    result['vod_area'] = ''

                # 类型: .video-info-header div.tag-link a 拼接
                type_links = soup.select('.video-info-header div.tag-link a')
                if type_links:
                    result['type_name'] = '/'.join([self._safe_str(a.get_text()) for a in type_links])
                else:
                    result['type_name'] = ''

                # 遍历 .video-info-item 提取详细信息
                info_items = soup.select('.video-info-item')
                for item in info_items:
                    # 获取前导标签文本（如"导演"、"主演"等）
                    label_tag = item.select_one('.video-info-itemlabel, .video-info-title')
                    content_tag = item.select_one('.video-info-content, .video-info-itemcontent, a')
                    if not label_tag:
                        # 尝试用 item 内的 span/text 作为标签
                        spans = item.find_all('span')
                        if spans:
                            label_tag = spans[0]
                        else:
                            first_text = item.get_text(strip=True)
                            if not first_text:
                                continue

                    label_text = self._safe_str(label_tag.get_text() if label_tag else '')

                    # 获取内容
                    if content_tag:
                        content_text = self._safe_str(content_tag.get_text())
                    else:
                        # 获取item中除标签外的文本
                        if label_tag:
                            label_tag.extract()
                        content_text = self._safe_str(item.get_text())
                        # 把多余的冒号去除
                        content_text = content_text.lstrip('：:')

                    if '导演' in label_text:
                        result['vod_director'] = content_text
                    elif '主演' in label_text:
                        result['vod_actor'] = content_text
                    elif '年代' in label_text or '年份' in label_text:
                        result['vod_year'] = content_text
                    elif '备注' in label_text or '更新' in label_text:
                        result['vod_remarks'] = content_text
                    elif '剧情' in label_text or '简介' in label_text or '介绍' in label_text:
                        result['vod_content'] = content_text

                # 如果某些字段没提取到，尝试用正则补充
                if 'vod_director' not in result:
                    director_match = re.search(r'导演[：:]\s*([^<\n]+)', html)
                    if director_match:
                        result['vod_director'] = self._safe_str(director_match.group(1))

                if 'vod_actor' not in result:
                    actor_match = re.search(r'主演[：:]\s*([^<\n]+)', html)
                    if actor_match:
                        result['vod_actor'] = self._safe_str(actor_match.group(1))

                if 'vod_year' not in result:
                    year_match = re.search(r'(\d{4})', html[:3000])
                    if year_match:
                        result['vod_year'] = year_match.group(1)

                if 'vod_content' not in result:
                    # 尝试从meta description获取
                    desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.IGNORECASE)
                    if desc_match:
                        result['vod_content'] = self._safe_str(desc_match.group(1))

                # 提取网盘分享链接作为播放源
                share_links = self._extract_share_links(soup, html)
                if share_links:
                    play_names = []
                    play_urls = []
                    for link_info in share_links:
                        play_names.append('网盘分享')
                        play_urls.append(link_info)

                    result['vod_play_from'] = '$$$'.join(play_names)
                    result['vod_play_url'] = '$$$'.join(play_urls)
                else:
                    result['vod_play_from'] = ''
                    result['vod_play_url'] = ''

                return result
            except Exception:
                pass

        # BeautifulSoup不可用时，使用正则回退解析
        result = self._parse_detail_html_regex(html)
        return result

    def _parse_detail_html_regex(self, html):
        """正则回退方式解析详情页"""
        result = {}

        # 标题
        title_match = re.search(r'<h1[^>]*class="[^"]*page-title[^"]*"[^>]*>([^<]+)</h1>', html)
        if not title_match:
            title_match = re.search(r'<title>([^<]+)</title>', html)
        result['vod_name'] = self._safe_str(title_match.group(1) if title_match else '')

        # 封面
        pic_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html, re.IGNORECASE)
        if pic_match:
            result['vod_pic'] = self._fix_url(pic_match.group(1))
        else:
            result['vod_pic'] = ''

        # 年份
        year_match = re.search(r'(\d{4})', html[:3000])
        result['vod_year'] = year_match.group(1) if year_match else ''

        # 描述
        desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html, re.IGNORECASE)
        result['vod_content'] = self._safe_str(desc_match.group(1) if desc_match else '')

        # 提取分享链接
        share_links = self._extract_share_links(None, html)
        if share_links:
            result['vod_play_from'] = '$$$'.join(['网盘分享'] * len(share_links))
            result['vod_play_url'] = '$$$'.join(share_links)
        else:
            result['vod_play_from'] = ''
            result['vod_play_url'] = ''

        return result

    def _extract_share_links(self, soup, html):
        """提取网盘分享链接，返回格式为 '标题$URL' 的列表"""
        links = []
        seen = set()

        if soup and BeautifulSoup:
            try:
                # 方式1: 从 .module-row-text 的 data-clipboard-text 属性提取
                row_texts = soup.select('.module-row-text')
                for row in row_texts:
                    clip_text = row.get('data-clipboard-text', '')
                    if clip_text:
                        clip_text = clip_text.strip()
                        # 提取http(s)链接
                        url_match = re.search(r'(https?://[^\s<>"\']+)', clip_text)
                        if url_match:
                            link_url = url_match.group(1)
                            if link_url not in seen:
                                seen.add(link_url)
                                # 取文本标题
                                title = re.sub(r'<[^>]+>', '', row.get_text()).strip()
                                if not title:
                                    title = clip_text[:30].strip()
                                links.append(f"{title}${link_url}")

                # 方式2: 从 .module-row-info p 提取
                row_infos = soup.select('.module-row-info p')
                for p in row_infos:
                    text = p.get_text()
                    url_match = re.search(r'(https?://[^\s<>"\']+)', text)
                    if url_match:
                        link_url = url_match.group(1)
                        if link_url not in seen:
                            seen.add(link_url)
                            title = text.strip()[:50]
                            links.append(f"{title}${link_url}")

                # 方式3: 从所有 [data-clipboard-text] 提取
                all_clips = soup.select('[data-clipboard-text]')
                for clip in all_clips:
                    clip_text = clip.get('data-clipboard-text', '')
                    if clip_text:
                        clip_text = clip_text.strip()
                        url_match = re.search(r'(https?://[^\s<>"\']+)', clip_text)
                        if url_match:
                            link_url = url_match.group(1)
                            if link_url not in seen:
                                seen.add(link_url)
                                title = re.sub(r'<[^>]+>', '', clip.get_text()).strip()
                                if not title:
                                    title = clip_text[:30].strip()
                                links.append(f"{title}${link_url}")
            except Exception:
                pass

        # 正则回退：从整个HTML中提取所有 http(s) 链接
        if not links:
            # 查找 data-clipboard-text 中的链接
            clip_pattern = r'data-clipboard-text="([^"]*)"'
            clip_matches = re.findall(clip_pattern, html)
            for clip_text in clip_matches:
                url_match = re.search(r'(https?://[^\s<>"\']+)', clip_text)
                if url_match:
                    link_url = url_match.group(1)
                    if link_url not in seen:
                        seen.add(link_url)
                        links.append(f"分享链接${link_url}")

        return links

    def _extract_total_and_pages(self, html):
        """从HTML中提取总数和计算总页数"""
        total = 0
        pagecount = 1

        # 正则匹配总数: $\(".mac_total"\)\.text\('(\d+)'\);
        total_match = re.search(r'\$\("\.mac_total"\)\.text\(\'(\d+)\'\)', html)
        if not total_match:
            # 备用: 直接查找 .mac_total 元素
            total_match = re.search(r'class="mac_total"[^>]*>(\d+)', html)
        if not total_match:
            # 再备用: 纯数字
            total_match = re.search(r'mac_total.*?(\d+)', html)

        if total_match:
            try:
                total = int(total_match.group(1))
                if total > 0:
                    pagecount = (total + PAGE_SIZE - 1) // PAGE_SIZE
            except (ValueError, IndexError):
                pass

        return total, pagecount

    # ========== 核心接口 ==========

    def homeContent(self, filter):
        """首页内容 — 返回分类和推荐"""
        result = {}
        result['class'] = CLASSES
        if filter:
            result['filters'] = FILTERS

        # 获取首页推荐
        html = self._fetch_html(SITE_URL)
        videos = self._parse_list_html(html)
        result['list'] = videos[:24]
        return result

    def homeVideoContent(self):
        """首页视频推荐"""
        html = self._fetch_html(SITE_URL)
        videos = self._parse_list_html(html)
        return {'list': videos[:24]}

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容 — 返回指定分类的视频列表，支持筛选"""
        result = {}
        page = self._safe_page(pg, 1)

        # 解析筛选参数
        area = ''
        by = 'time'
        year = ''
        letter = ''

        if isinstance(extend, dict):
            area = self._safe_str(extend.get('地区', ''))
            year = self._safe_str(extend.get('年份', ''))
            letter = self._safe_str(extend.get('字母', ''))
            by = self._safe_str(extend.get('排序', 'time'))
            if not by:
                by = 'time'
        elif isinstance(extend, str):
            try:
                ext = json.loads(extend)
                area = self._safe_str(ext.get('地区', ''))
                year = self._safe_str(ext.get('年份', ''))
                letter = self._safe_str(ext.get('字母', ''))
                by = self._safe_str(ext.get('排序', 'time'))
                if not by:
                    by = 'time'
            except Exception:
                pass

        # 对各段用encodeURIComponent编码
        cate_id_enc = urllib.parse.quote(str(tid))
        area_enc = urllib.parse.quote(area)
        by_enc = urllib.parse.quote(by)
        class_enc = ''  # 子分类，此处为空
        lang_enc = ''  # 语言，此处为空
        year_enc = urllib.parse.quote(year)
        page_enc = str(page)

        # 构建分类页URL
        # 无筛选: {siteUrl}/vodshow/{cateId}-----------.html
        # 有筛选: {siteUrl}/vodshow/{cateId}-{area}-{by}-{class}-{lang}----{page}---{year}.html
        if not area and not year and not letter and by == 'time':
            url = f"{SITE_URL}/vodshow/{cate_id_enc}-----------.html"
        else:
            url = (f"{SITE_URL}/vodshow/{cate_id_enc}-{area_enc}-{by_enc}-"
                   f"{class_enc}-{lang_enc}----{page_enc}---{year_enc}.html")

        html = self._fetch_html(url)
        videos = self._parse_list_html(html)

        # 提取总数和页码
        total, pagecount = self._extract_total_and_pages(html)

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = pagecount
        result['limit'] = PAGE_SIZE
        result['total'] = total
        return result

    def detailContent(self, array):
        """详情内容 — 返回影片详情和播放源"""
        vod_id = array[0] if array else ''
        if not vod_id:
            return {'list': []}

        # 根据ID格式构建URL
        if vod_id.startswith('http'):
            url = vod_id
        elif vod_id.startswith('/'):
            url = f"{SITE_URL}{vod_id}"
        elif re.match(r'\d+\.html', vod_id):
            url = f"{SITE_URL}/voddetail/{vod_id}"
        elif re.match(r'\d+$', vod_id):
            url = f"{SITE_URL}/voddetail/{vod_id}.html"
        else:
            url = f"{SITE_URL}/{vod_id}"

        html = self._fetch_html(url)
        result = self._parse_detail_html(html)
        result['vod_id'] = vod_id
        return {'list': [result]}

    def playerContent(self, flag, id, vipFlags):
        """播放内容 — 返回播放URL
        如果播放ID是 http(s):// 直链，直接返回 {parse:0, url:id}
        否则返回 {parse:1, url:id} 让壳子解析
        """
        if not id:
            return {'parse': 0, 'playUrl': '', 'url': '', 'header': ''}

        if id.startswith('http://') or id.startswith('https://'):
            # 判断是否为视频直链
            if self.isVideoFormat(id):
                return {
                    'parse': 0,
                    'playUrl': '',
                    'url': id,
                    'header': json.dumps(self.headers) if self.headers else '',
                }
            else:
                # 网盘链接等非视频直链，让壳子解析
                return {
                    'parse': 1,
                    'playUrl': '',
                    'url': id,
                    'header': json.dumps(self.headers) if self.headers else '',
                }
        else:
            # 非http链接，拼成站内URL让壳子解析
            url = id if id.startswith('/') else f"{SITE_URL}/vodplay/{id}.html"
            return {
                'parse': 1,
                'playUrl': '',
                'url': url,
                'header': json.dumps(self.headers) if self.headers else '',
            }

    def searchContent(self, key, quick):
        """搜索内容"""
        result = {}
        if not key:
            return {'list': []}

        search_word = urllib.parse.quote(key)
        page = 1

        # URL1: {siteUrl}/vodsearch/-{wd}------------{page}---.html
        url1 = f"{SITE_URL}/vodsearch/-{search_word}------------{page}---.html"
        html = self._fetch_html(url1)

        # 如果第一种方式无结果，尝试第二种
        videos = self._parse_search_html(html)
        if not videos:
            # URL2: {siteUrl}/vodsearch/-------------.html?wd={wd}
            url2 = f"{SITE_URL}/vodsearch/-------------.html?wd={search_word}"
            html2 = self._fetch_html(url2)
            videos = self._parse_search_html(html2)

        result['list'] = videos
        return result

    def _parse_search_html(self, html):
        """用BeautifulSoup解析搜索结果页"""
        videos = []
        if not html:
            return videos

        if BeautifulSoup:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                items = soup.select('.module-search-item')
                if not items:
                    # 回退到列表解析
                    return self._parse_list_html(html)
                for item in items:
                    vod_name = ''
                    vod_id = ''
                    vod_pic = ''
                    vod_remarks = ''

                    # 标题链接: 无 .video-serial，改用 .module-item-cover .module-item-pic a 或 .video-name a
                    name_tag = item.select_one('.module-item-cover .module-item-pic a')
                    if not name_tag:
                        name_tag = item.select_one('.video-name a')
                    if name_tag:
                        vod_name = self._safe_str(name_tag.get('title', '') or name_tag.get_text())
                        href = name_tag.get('href', '')
                        if href:
                            id_match = re.search(r'voddetail/(\d+)', href)
                            if id_match:
                                vod_id = id_match.group(1)
                            else:
                                vod_id = href

                    # 封面
                    pic_tag = item.select_one('.module-item-pic img')
                    if pic_tag:
                        vod_pic = self._fix_url(
                            pic_tag.get('data-src', '') or pic_tag.get('src', '')
                        )

                    # 备注
                    remark_tag = item.select_one('.module-item-text')
                    if remark_tag:
                        vod_remarks = self._safe_str(remark_tag.get_text())

                    if vod_id:
                        videos.append({
                            'vod_id': vod_id,
                            'vod_name': vod_name,
                            'vod_pic': vod_pic,
                            'vod_remarks': vod_remarks,
                            'type_name': '',
                        })
                return videos
            except Exception:
                pass

        # 正则回退
        pattern = r'<a[^>]*href="([^"]*voddetail/(\d+)\.html)"[^>]*(?:title="([^"]*)")?[^>]*>'
        matches = re.findall(pattern, html)
        for match in matches:
            href, vod_id, title = match
            videos.append({
                'vod_id': vod_id,
                'vod_name': self._safe_str(title),
                'vod_pic': '',
                'vod_remarks': '',
                'type_name': '',
            })

        return videos

    def searchContentPage(self, key, quick, pg):
        """搜索内容(分页)"""
        result = {}
        if not key:
            return {'list': []}

        page = self._safe_page(pg, 1)
        search_word = urllib.parse.quote(key)

        url = f"{SITE_URL}/vodsearch/-{search_word}------------{page}---.html"
        html = self._fetch_html(url)

        if not html:
            url2 = f"{SITE_URL}/vodsearch/-------------.html?wd={search_word}"
            html = self._fetch_html(url2)

        videos = self._parse_search_html(html)
        result['list'] = videos
        return result

    def localProxy(self, param):
        """本地代理"""
        return [200, "video/MP2T", "", ""]


# 独立运行时用于测试
if __name__ == '__main__':
    spider = Spider()
    spider.init()
    print(f"Spider名称: {spider.getName()}")
    print(f"站点URL: {SITE_URL}")
    print("初始化成功，可进行功能测试。")
