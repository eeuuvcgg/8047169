#coding=utf-8
#!/usr/bin/python
# ==================== 电影蜜蜂 https://www.dianyingmifeng.com/ ====================
# drpy 爬虫源 - MacCMS v10 + vfed 3.1.5 模板
# 站点特征：
#   列表/分类 : /vodtype/{tid}-{pg}/ （主分类聚合无分页, 子分类带分页, 如动作片共 107 页）
#   详情     : /voddetail/{id}/ （fed-deta-info 字段 + fed-play-data 播放块, 线路 fed-drop-btns / 集数 fed-play-item）
#   播放     : /vodplay/{id}-{sid}-{nid}/ 页内 iframe src="/static/player/dplayer.html?url={m3u8}"
#              m3u8 为红牛直链（hn.bfvvs.com 等, 实测无防盗链）, parse=0 直放
#   搜索     : /vodsearch/{keyword}-------------/ （MacCMS 标准 wd+11段筛选格式）
#              ⚠ 该路由有 nginx JS 挑战(403+Set-Cookie+JS刷新, 加速乐类指纹校验),
#                纯 HTTP 环境(含 TVBox drpy 运行时)无法通过, 浏览器可访问;
#                解析逻辑完整保留, 挑战策略变化时可正常使用, 拦截时返回空列表。
#   UA 策略  : 必须移动端 UA（桌面 UA 部分路由 403）
# 实测证据  : 2026-09-09 移动 UA 抓取验证（影片怨鬼网红/147384, 花落朝夕玉无声/147155）
import re
import sys
import json
import gzip
from urllib.parse import quote, unquote, urlparse, parse_qs

# ==================== 顶层常量 ====================
HOST = 'https://www.dianyingmifeng.com'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Referer': HOST + '/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

# 分类列表（主分类为聚合页, 子分类可分页; 与站点导航一致）
CATEGORIES = [
    {'type_name': '电影', 'type_id': 'dianying'},
    {'type_name': '连续剧', 'type_id': 'lianxuju'},
    {'type_name': '综艺', 'type_id': 'zongyi'},
    {'type_name': '动漫', 'type_id': 'dongman'},
    {'type_name': '动作片', 'type_id': 'dongzuopian'},
    {'type_name': '喜剧片', 'type_id': 'xijupian'},
    {'type_name': '爱情片', 'type_id': 'aiqingpian'},
    {'type_name': '科幻片', 'type_id': 'kehuanpian'},
    {'type_name': '恐怖片', 'type_id': 'kongbupian'},
    {'type_name': '剧情片', 'type_id': 'juqingpian'},
    {'type_name': '战争片', 'type_id': 'zhanzhengpian'},
    {'type_name': '国产剧', 'type_id': 'guochanju'},
    {'type_name': '港台剧', 'type_id': 'gangtaiju'},
    {'type_name': '日韩剧', 'type_id': 'rihanju'},
    {'type_name': '欧美剧', 'type_id': 'oumeiju'},
]

# 筛选器（站点筛选以子分类实现, 无 URL 筛选参数, 留空兼容）
CATEGORY_FILTERS = {}


# ====== 工具函数 ======

def _gzip_decode(resp):
    """手动解压 gzip 响应, 兼容 str/字节/带 headers 对象"""
    try:
        content = resp.content
    except Exception:
        content = resp
    if isinstance(content, bytes):
        try:
            encoding = ''
            if hasattr(resp, 'headers'):
                encoding = resp.headers.get('Content-Encoding', '') or resp.headers.get('content-encoding', '')
            if encoding == 'gzip' or (len(content) > 2 and content[0:2] == b'\x1f\x8b'):
                content = gzip.decompress(content).decode('utf-8', errors='ignore')
            else:
                content = content.decode('utf-8', errors='ignore')
        except Exception:
            try:
                content = gzip.decompress(content).decode('utf-8', errors='ignore')
            except Exception:
                content = content.decode('utf-8', errors='ignore')
    return content


def _full_url(url):
    """相对路径补全为完整 URL"""
    if not url:
        return ''
    url = url.strip()
    if url.startswith('http'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return HOST + url
    return HOST + '/' + url


def _clean_extend(extend):
    """extend 清洗: dict / JSON 字符串 / 脏值 -> dict"""
    ext = {}
    if extend:
        if isinstance(extend, str):
            try:
                ext = json.loads(extend)
                if not isinstance(ext, dict):
                    ext = {}
            except Exception:
                ext = {}
        elif isinstance(extend, dict):
            ext = extend
    return ext


def _parse_vod_list(html):
    """解析列表页卡片: li.fed-list-item（首页/分类页/搜索页共用）"""
    items = []
    # 卡片块
    pattern = re.compile(
        r'<li[^>]*class="[^"]*fed-list-item[^"]*"[^>]*>(.*?)</li>',
        re.DOTALL
    )
    for block in pattern.findall(html):
        try:
            # 视频链接与封面
            a_match = re.search(
                r'<a[^>]*class="[^"]*fed-list-pics[^"]*"[^>]*href="([^"]*)"[^>]*data-original="([^"]*)"',
                block
            )
            if not a_match:
                a_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*(?:data-original|src)="([^"]*)"', block)
            if not a_match:
                continue
            vod_url = a_match.group(1).strip()
            pic = a_match.group(2).strip()
            vod_id = _full_url(vod_url)

            # 标题
            title_match = re.search(
                r'<a[^>]*class="[^"]*fed-list-title[^"]*"[^>]*href="[^"]*"[^>]*>(.*?)</a>',
                block, re.DOTALL
            )
            if not title_match:
                title_match = re.search(r'<a[^>]*href="[^"]*"[^>]*title="([^"]*)"', block)
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''

            # 备注（更新状态）
            remarks_match = re.search(
                r'<span[^>]*class="[^"]*fed-list-remarks[^"]*"[^>]*>(.*?)</span>',
                block, re.DOTALL
            )
            remarks = re.sub(r'<[^>]+>', '', remarks_match.group(1)).strip() if remarks_match else ''

            items.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        except Exception:
            continue
    return items


def _parse_rss_search(rss_html, key):
    """降级搜索: /vodsearch/ 被 JS 挑战拦截时, 用 rss.xml 最新 100 条本地匹配标题"""
    items = []
    if not rss_html or not key:
        return items
    key_l = key.lower()
    for block in re.findall(r'<item>(.*?)</item>', rss_html, re.DOTALL):
        try:
            title_match = re.search(r'<title>\s*<!\[CDATA\[(.*?)\]\]>\s*</title>', block, re.DOTALL)
            if not title_match:
                continue
            title = title_match.group(1).strip()
            if key_l not in title.lower():
                continue
            link_match = re.search(r'<link>(.*?)</link>', block, re.DOTALL)
            link = link_match.group(1).strip() if link_match else ''
            if not link:
                continue
            items.append({
                'vod_id': link,
                'vod_name': title,
                'vod_pic': '',
                'vod_remarks': '',
            })
        except Exception:
            continue
    return items[:50]


def _parse_search_results(html):
    """解析搜索结果页: 每条结果为一个 dl.fed-deta-info（详情式卡片）"""
    items = []
    pattern = re.compile(
        r'<dl[^>]*class="[^"]*fed-deta-info[^"]*"[^>]*>(.*?)</dl>',
        re.DOTALL
    )
    for block in pattern.findall(html):
        try:
            a_match = re.search(
                r'<a[^>]*href="(/voddetail/\d+/)"[^>]*data-original="([^"]*)"', block
            )
            if not a_match:
                a_match = re.search(r'<a[^>]*href="(/voddetail/\d+/)"', block)
            if not a_match:
                continue
            vod_url = a_match.group(1).strip()
            pic = a_match.group(2).strip() if a_match.lastindex and a_match.lastindex >= 2 else ''
            vod_id = _full_url(vod_url)

            title_match = re.search(r'<h1[^>]*>.*?<a[^>]*>(.*?)</a>', block, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''

            remarks_match = re.search(
                r'class="[^"]*fed-list-remarks[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL
            )
            remarks = re.sub(r'<[^>]+>', '', remarks_match.group(1)).strip() if remarks_match else ''

            items.append({
                'vod_id': vod_id,
                'vod_name': title,
                'vod_pic': pic,
                'vod_remarks': remarks,
            })
        except Exception:
            continue
    return items


def _parse_detail(html):
    """解析详情页: fed-deta-info 字段 + fed-play-data 播放块"""
    info = {}

    # 标题: <h1>...<a>标题</a></h1>
    title_match = re.search(r'<h1[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
    if title_match:
        info['vod_name'] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

    # 封面: fed-deta-images 下 fed-list-pics 的 data-original
    pic_match = re.search(r'fed-deta-images.*?data-original="([^"]*)"', html, re.DOTALL)
    if pic_match:
        info['vod_pic'] = pic_match.group(1).strip()

    # 主演 / 导演 / 分类 / 地区 / 年份 / 更新: <span class="fed-text-muted">XX：</span>...
    fields = {
        'vod_actor': '主演',
        'vod_director': '导演',
        'type_name': '分类',
        'vod_area': '地区',
        'vod_year': '年份',
        'vod_pubdate': '更新',
        'vod_remarks': '状态',
    }
    for key, label in fields.items():
        m = re.search(
            label + '：</span>(.*?)</li>', html, re.DOTALL
        )
        if m:
            seg = m.group(1)
            if key in ('vod_actor', 'vod_director'):
                names = re.findall(r'<a[^>]*>(.*?)</a>', seg, re.DOTALL)
                if names:
                    info[key] = '&'.join(re.sub(r'<[^>]+>', '', n).strip() for n in names if n.strip())
            else:
                names = re.findall(r'<a[^>]*>(.*?)</a>', seg, re.DOTALL)
                if names:
                    info[key] = re.sub(r'<[^>]+>', '', names[0]).strip()
                else:
                    val = re.sub(r'<[^>]+>', '', seg).strip()
                    if val:
                        info[key] = val

    # 简介: <span ...>简介：</span>文本
    desc_match = re.search(r'简介：</span>(.*?)(?:</li>|</div>)', html, re.DOTALL)
    if desc_match:
        desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
        for suffix in ['展开', '收起', '... 展开', '...展开', '… 展开', '…展开']:
            if desc.endswith(suffix):
                desc = desc[:-len(suffix)].strip()
        info['vod_content'] = desc

    # 播放线路与集数
    play_from_list = []
    play_url_list = []
    try:
        # 播放块 fed-play-data
        block_match = re.search(r'fed-play-data.*?(?=<div class="fed-part-layout|</div>\s*</div>\s*</div>\s*</body>)', html, re.DOTALL)
        play_html = block_match.group(0) if block_match else html

        # 线路: div.fed-drop-tops 内 li.fed-drop-btns > a
        lines = []
        tops_match = re.search(r'fed-drop-tops(.*?)fed-drop-btms', play_html, re.DOTALL)
        tops = tops_match.group(1) if tops_match else ''
        for lm in re.finditer(r'<a[^>]*class="[^"]*fed-btns-info[^"]*"[^>]*href="(/vodplay/[^"]+)"[^>]*>(.*?)</a>', tops, re.DOTALL):
            name = re.sub(r'<[^>]+>', '', lm.group(2)).strip()
            if name:
                lines.append(name)

        # 集数: 每个 div.fed-play-item 对应一条线路
        play_items = re.findall(r'<div[^>]*class="[^"]*fed-play-item[^"]*"[^>]*>(.*?)</div>', play_html, re.DOTALL)
        for idx, item in enumerate(play_items):
            episodes = []
            seen = set()
            for em in re.finditer(r'<a[^>]*class="[^"]*fed-btns-info[^"]*"[^>]*href="(/vodplay/[^"]+)"[^>]*>(.*?)</a>', item, re.DOTALL):
                ep_url = em.group(1).strip()
                ep_title = re.sub(r'<[^>]+>', '', em.group(2)).strip()
                if not ep_title or ep_url in seen:
                    continue
                seen.add(ep_url)
                episodes.append(ep_title + '$' + _full_url(ep_url))
            if episodes:
                line_name = lines[idx] if idx < len(lines) else ('线路' + str(idx + 1))
                play_from_list.append(line_name)
                play_url_list.append('#'.join(episodes))
    except Exception:
        pass

    info['vod_play_from'] = '$$$'.join(play_from_list)
    info['vod_play_url'] = '$$$'.join(play_url_list)

    return info


def _extract_play_url(html):
    """从播放页 HTML 提取实际播放地址:
    优先 iframe src 中 dplayer.html?url= 参数（m3u8 直链）"""
    # iframe src -> /static/player/dplayer.html?url=xxx
    iframe_match = re.search(r'<iframe[^>]*src="([^"]*)"', html, re.DOTALL)
    if iframe_match:
        src = iframe_match.group(1).strip()
        if 'url=' in src:
            if src.startswith('/'):
                src = _full_url(src)
            try:
                q = parse_qs(urlparse(src).query)
                if q.get('url'):
                    return unquote(q.get('url')[0])
            except Exception:
                pass
            # 兜底正则
            m = re.search(r'[?&]url=([^&"\']+)', src)
            if m:
                return unquote(m.group(1))
    # 页面内直接搜 m3u8
    m3u8 = re.search(r'(https?://[^\s"\'<>]+?\.m3u8[^\s"\'<>]*)', html)
    if m3u8:
        return m3u8.group(1)
    return ''


IS_VIDEO_RE = re.compile(
    r'\.(m3u8|mp4|flv|avi|mkv|wmv|mov|rmvb|webm|ts)(\?|$)',
    re.IGNORECASE
)


def is_video_format(url):
    return bool(IS_VIDEO_RE.search(url))


# ====== Spider 类 ======

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class _FetchResult(object):
        def __init__(self, content=b'', text='', headers=None):
            self.content = content
            self.text = text
            self.headers = headers or {}

    class BaseSpider(object):
        def fetch(self, url, headers=None, timeout=10):
            import urllib.request
            req = urllib.request.Request(url, headers=headers or {})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    return _FetchResult(raw, raw.decode('utf-8', errors='ignore'), resp.headers)
            except Exception:
                return _FetchResult()


class Spider(BaseSpider):
    """电影蜜蜂 drpy 爬虫"""

    HOST = HOST
    HEADERS = HEADERS

    def init(self, extend=''):
        try:
            if extend:
                if isinstance(extend, str):
                    ext = json.loads(extend)
                    if isinstance(ext, dict) and ext.get('host'):
                        self.HOST = ext['host'].rstrip('/')
        except Exception:
            pass

    def getName(self):
        return '电影蜜蜂'

    def isVideoFormat(self, url):
        return is_video_format(url)

    def manualVideoEncoder(self):
        pass

    def fetch(self, url, headers=None):
        if headers is None:
            headers = self.HEADERS
        try:
            resp = super(Spider, self).fetch(url, headers=headers)
            return _gzip_decode(resp)
        except Exception:
            try:
                resp = super(Spider, self).fetch(url, headers=headers, timeout=10)
                return _gzip_decode(resp)
            except Exception:
                return ''

    def homeContent(self, filter=''):
        """首页: 返回 class, filters, list"""
        result = {}
        result['class'] = [{'type_name': c['type_name'], 'type_id': c['type_id']} for c in CATEGORIES]
        result['filters'] = CATEGORY_FILTERS
        try:
            html = self.fetch(self.HOST + '/')
            result['list'] = _parse_vod_list(html) if html else []
        except Exception:
            result['list'] = []
        return result

    def homeVideoContent(self):
        try:
            html = self.fetch(self.HOST + '/')
            if html:
                return {'list': _parse_vod_list(html)}
        except Exception:
            pass
        return {}

    def categoryContent(self, tid, pg='1', filter='', extend=''):
        """分类页: /vodtype/{tid}-{pg}/（主分类聚合页无分页, 子分类分页）"""
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result = {'list': []}
        try:
            url = self.HOST + '/vodtype/' + quote(str(tid)) + '-' + str(pg) + '/'
            html = self.fetch(url)
            if html:
                result['list'] = _parse_vod_list(html)

            if result['list']:
                # 分页数: 取分页控件最大页码; 无页码链接(主分类聚合页)视为单页
                pagecount = 1
                page_matches = re.findall(
                    r'/vodtype/[^"\']*?-(\d+)/', html
                )
                nums = [int(p) for p in page_matches if p.isdigit()]
                if nums:
                    pagecount = max(nums)
                result['page'] = pg
                result['pagecount'] = pagecount
                result['limit'] = len(result['list'])
                result['total'] = 9999
            else:
                result['page'] = pg
                result['pagecount'] = pg
                result['limit'] = 0
                result['total'] = 0
        except Exception:
            result['page'] = pg
            result['pagecount'] = pg
            result['limit'] = 0
            result['total'] = 0
        return result

    def detailContent(self, ids):
        """详情页: ids[0] 为 vod_id（完整 URL 或相对路径）"""
        result = {}
        try:
            vod_id = ids[0]
            detail_url = _full_url(vod_id)
            html = self.fetch(detail_url)
            if html:
                vod_info = _parse_detail(html)
                vod_info['vod_id'] = vod_id
                result['list'] = [vod_info]
            else:
                result['list'] = []
        except Exception:
            result['list'] = []
        return result

    def _fetch_detail_pic(self, vod_id):
        """从详情页提取海报(降级搜索无封面时为结果补图)"""
        try:
            html = self.fetch(vod_id)
            if html:
                m = re.search(r'fed-deta-images.*?data-original="([^"]*)"', html, re.DOTALL)
                if m:
                    return m.group(1).strip()
        except Exception:
            pass
        return ''

    def searchContent(self, key, quick, pg="1"):
        """搜索: /vodsearch/{keyword}-------------/
        注意: 该路由存在 nginx JS 挑战（403 + Set-Cookie + JS 刷新, 加速乐类指纹校验），
        纯 HTTP 环境（TVBox drpy 运行时）无法通过, 检测到挑战时返回空列表;
        解析逻辑完整, 若站点挑战策略放开可正常使用。"""
        try:
            pg = int(pg) if str(pg).isdigit() else 1
        except Exception:
            pg = 1
        result = {'list': []}
        try:
            url = self.HOST + '/vodsearch/' + quote(key) + '-------------/'
            html = self.fetch(url)
            # 挑战页特征: 纯HTTP返回403(空)或JS刷新页
            if not html or ('window.location.href' in html and 'vodsearch' in html):
                # JS 挑战拦截/请求失败: 降级用 rss.xml 最新条目本地匹配, 前 10 条补详情封面
                items = _parse_rss_search(self.fetch(self.HOST + '/rss.xml'), key)
                for it in items[:10]:
                    if not it.get('vod_pic'):
                        it['vod_pic'] = self._fetch_detail_pic(it['vod_id'])
                result['list'] = items
                return result
            result['list'] = _parse_search_results(html)
        except Exception:
            pass
        return result

    def playerContent(self, flag, id, vipFlags):
        """播放页: 解析 iframe 中 m3u8 直链, parse=0; 失败回退嗅探 parse=1"""
        result = {}
        try:
            play_url = _full_url(id)
            html = self.fetch(play_url)
            if html:
                url = _extract_play_url(html)
                if url:
                    result = {
                        'parse': 0 if is_video_format(url) else 1,
                        'playUrl': '',
                        'url': url,
                        'header': json.dumps(self.HEADERS),
                    }
                else:
                    result = {
                        'parse': 1,
                        'playUrl': '',
                        'url': play_url,
                        'header': json.dumps(self.HEADERS),
                    }
            else:
                result = {
                    'parse': 1,
                    'playUrl': '',
                    'url': play_url,
                    'header': json.dumps(self.HEADERS),
                }
        except Exception:
            result = {
                'parse': 1,
                'playUrl': '',
                'url': id,
                'header': json.dumps(self.HEADERS),
            }
        if vipFlags is None:
            vipFlags = []
        return result

    def localProxy(self, param):
        return {}


# ====== 模块级函数 (兼容不同 TVBox 版本调用方式) ======

def homeContent(filter=''):
    s = Spider()
    return s.homeContent(filter)


def homeVideoContent():
    try:
        s = Spider()
        return s.homeVideoContent()
    except Exception:
        return {}


def categoryContent(tid, pg='1', filter='', extend=''):
    s = Spider()
    return s.categoryContent(tid, pg, filter, extend)


def detailContent(ids):
    s = Spider()
    return s.detailContent(ids)


def searchContent(key, quick, pg="1"):
    s = Spider()
    return s.searchContent(key, quick, pg)


def playerContent(flag, id, vipFlags):
    s = Spider()
    return s.playerContent(flag, id, vipFlags)


# ====== Content 后缀别名兼容 (旧版 TVBox 接口名) ======

def homeContentContent(filter=''):
    return homeContent(filter)


def categoryContentContent(tid, pg, filter, extend):
    return categoryContent(tid, pg, filter, extend)


def detailContentContent(ids):
    return detailContent(ids)


def searchContentContent(key, quick, pg="1"):
    return searchContent(key, quick, pg)


def playerContentContent(flag, id, vipFlags):
    return playerContent(flag, id, vipFlags)