# -*- coding: utf-8 -*-
"""
韩剧|秒播 (hanxiaoqu / 韩小圈) — 兼容 FongMi/TV (T3) 与 WebHomeTV/PeekPro (T4) 双壳子
站点: https://hxqapi.hiyun.tv
API: 自定义加密接口，AES-128-CBC 响应解密 + 多步骤播放解析
版本: 1.1.0
修复记录:
  1. [致命] 播放地址解密密钥错误 -> 正确为 md5(md5(uid) + "34F9Q53w/HJW8E6Q")，
     key 取 md5 前16字符、iv 取后16字符。旧版用 md5(uid+ts)+salt 导致 rslvV4 的
     datas[].data 永远解不出明文，表现为"有数据有封面但播放不了"。
  2. [次要] _fix_play_url 硬编码 piccc.cdn.51touxiang.com，实际 CDN 域名会变
     (voldn-ser01 / piccc.cdn 等)，会把正确地址改坏 -> 移除。
  3. [次要] localProxy 同样硬编码域名 -> 改为从 m3u8 自身 URL 推导 base。
  4. [优化] 详情页集数备注取自 conerMemo/detailMemo/lastSerialNo（count 字段是
     {"topic":xxx} 对象，旧版取不到值导致备注为空）。
  5. [优化] 播放返回 header 直接用解密结果里带的 header.User-Agent。
  6. [优化] 搜索分页兜底；首页推荐改为结构化提取；scid / ttk 缓存。
  7. [致命] 播放地址全部改为走本地代理（localProxy 递归代理 m3u8 + TS）。
     原因：CDN 只给 http 明文（且部分域名 https 直接握手失败），Android 9+
     的 cleartext 策略会拦截直连；同时 m3u8 里的 TS 是根相对路径。代理后
     播放器只访问 127.0.0.1，由 python 侧代拉并带正确 UA。
  8. [致命] homeContent 未返回 list，导致首页一片空白 -> 补上。
  9. [优化] _proxify 正确处理代理基址尾部的 & / ?，避免出现 && 双分隔符；
     localProxy 入参解析不再误切目标地址自带的 ?query；https 失败自动降级 http。
"""
import sys
import json
import re
import time
import random
import base64
import hashlib
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

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

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    HAS_CRYPTO = True
except ImportError:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
        HAS_CRYPTO = 'cryptography'
    except ImportError:
        HAS_CRYPTO = False


# ==================== 常量 ====================
HOST = "https://hxqapi.hiyun.tv"
UA = "HanjuTV/6.8 (V2238A; Android 12; Scale/2.00)"
PLAY_UA = "tdc.8260"            # 播放地址/CDN 需要的 UA（解密结果里也会带）
VN = "6.8"           # 版本号
VC = "a_8260"        # 版本码
CH = "vivo"          # 渠道
PKG = "com.babycloud.hanju"

SALT_SV0 = "34F9Q53w/HJW8E6Q"        # 通用 salt
SALT_L1T = "2E159Q/Z8979WckQ"        # 播放签名 salt
UK_KEY  = "f349wghhe784tqwh"          # uk 加密 key
UK_IV   = "d3w8hf94fidk38lk"          # uk 加密 iv
REWARD_SALT = "GIpxY0JPylRx"          # reward token salt
INSTALL_OFFSET = 1209600000           # 14天毫秒

# 播放地址解密预留key（历史版本，按顺序尝试）
LEGACY_PLAY_KEYS = ["FishHxq@Transit!", "HxqSpiderConfig!", "Hxqfish20260000!"]

DEFAULT_QUALITIES = [
    ["蓝光HDR", "11", "1"],
    ["蓝光1080P", "10", "1"],
    ["高清720P", "2", "0"],
    ["标清480P", "1", "0"],
]

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


class Spider(Spider):
    """韩剧|秒播 Spider — 加密API驱动"""

    def getName(self):
        return "韩剧|秒播"

    def init(self, extend=""):
        self.extend = '' if isinstance(extend, list) else (extend or '')

        self.host = HOST
        self.uid = self._random_str("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 20)
        self.said = self._random_str("0123456789abcdef", 16)
        self.oa = self._random_str("0123456789abcdef", 16)
        self.install_time = int(time.time() * 1000) - INSTALL_OFFSET
        self.device_id = self._random_str("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", 32)
        self._reward_cache = {}   # pid -> {token, expire_at}
        self._scid_cache = {}     # pid -> scid
        self._play_key = None     # 播放地址解密key缓存

    # ========== 工具函数 ==========

    @staticmethod
    def _random_str(chars, length):
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    def _md5(text):
        return hashlib.md5(str(text or '').encode('utf-8')).hexdigest()

    def _aes_encrypt(self, text, key, iv):
        """AES-128-CBC 加密，返回base64"""
        key = key.encode('utf-8')[:16]
        iv = iv.encode('utf-8')[:16]
        body = str(text).encode('utf-8')
        if HAS_CRYPTO == True:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            return base64.b64encode(cipher.encrypt(pad(body, AES.block_size))).decode('utf-8')
        elif HAS_CRYPTO == 'cryptography':
            p = sym_padding.PKCS7(128).padder()
            padded = p.update(body) + p.finalize()
            enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
            return base64.b64encode(enc.update(padded) + enc.finalize()).decode('utf-8')
        raise ImportError("需要 pycryptodome 或 cryptography 库")

    def _aes_decrypt_b64(self, b64text, key, iv):
        """AES-128-CBC 解密，输入base64，失败返回 ''"""
        try:
            data = base64.b64decode(str(b64text))
        except Exception:
            return ''
        if not data or len(data) % 16:
            return ''
        key = key.encode('utf-8')[:16] if isinstance(key, str) else key[:16]
        iv = iv.encode('utf-8')[:16] if isinstance(iv, str) else iv[:16]
        try:
            if HAS_CRYPTO == True:
                return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(data), AES.block_size).decode('utf-8')
            elif HAS_CRYPTO == 'cryptography':
                dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
                padded = dec.update(data) + dec.finalize()
                u = sym_padding.PKCS7(128).unpadder()
                return (u.update(padded) + u.finalize()).decode('utf-8')
            raise ImportError
        except Exception:
            return ''

    def _aes_decrypt_raw(self, data, key, iv):
        """解密原始bytes，去padding失败时返回未去padding的结果"""
        key = key.encode('utf-8')[:16] if isinstance(key, str) else key[:16]
        iv = iv.encode('utf-8')[:16] if isinstance(iv, str) else iv[:16]
        try:
            if HAS_CRYPTO == True:
                pt = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
                try:
                    return unpad(pt, AES.block_size)
                except Exception:
                    return pt
            elif HAS_CRYPTO == 'cryptography':
                dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
                pt = dec.update(data) + dec.finalize()
                try:
                    u = sym_padding.PKCS7(128).unpadder()
                    return u.update(pt) + u.finalize()
                except Exception:
                    return pt
            raise ImportError
        except Exception:
            return b''

    def _uk(self):
        return self._aes_encrypt(self.uid, UK_KEY, UK_IV)

    def _build_params(self):
        now = int(time.time() * 1000)
        return {
            "emu": 0, "ou": 0, "it": self.install_time, "iit": self.install_time,
            "bs": 0, "uid": self.uid, "pc": 0, "tm": 81,
            "d8m": "0,0,0,0,0,0,0,4", "md": "V2238A", "maker": "vivo",
            "osv": "12", "br": 95, "rpc": 0, "scc": 2, "plc": 6, "toc": 19, "tsc": 10,
            "ts": now, "pa": 1, "crec": 0, "nw": 2, "px": "0", "isp": "",
            "ai": self.said, "oa": self.oa, "dpc": 0, "dsc": 0, "qpc": 0, "apad": 0,
            "pk": PKG
        }

    def _build_headers(self):
        uid_md5 = self._md5(self.uid)
        return {
            "app": "hj",
            "ch": CH,
            "said": self.said,
            "uk": self._uk(),
            "vn": VN,
            "sign": self._aes_encrypt(json.dumps(self._build_params()), uid_md5[:16], uid_md5[16:32]),
            "User-Agent": UA,
            "vc": VC,
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
        }

    def _decrypt_response(self, data):
        """解密API响应（约定：key=md5(md5(uid+ts)+SALT_SV0)）"""
        try:
            data_str = str(data.get('data', ''))
            ts = str(data.get('ts', ''))
            if not data_str or len(data_str) <= 20:
                return data
            k = self._md5(self._md5(self.uid + ts) + SALT_SV0)
            pt = self._aes_decrypt_b64(data_str, k[:16], k[16:32])
            if not pt:
                return None
            return json.loads(self._trim_json(pt))
        except Exception:
            return None

    @staticmethod
    def _trim_json(text):
        text = str(text or '').strip()
        last_brace = max(text.rfind('}'), text.rfind(']'))
        return text[:last_brace + 1] if last_brace >= 0 else text

    def _api_get(self, path, params=None):
        url = self.host + path
        if params:
            url += '?' + urlencode(params)
        try:
            rsp = self.fetch(url, headers=self._build_headers(), timeout=15)
            data = json.loads(rsp.text)
            if str(data.get('rescode', -1)) != '0':
                return None
            return self._decrypt_response(data)
        except Exception:
            return None

    def _api_post(self, path, body, extra_headers=None):
        headers = self._build_headers()
        headers['Content-Type'] = 'application/json'
        if extra_headers:
            headers.update(extra_headers)
        try:
            rsp = self.post(self.host + path, data=body, headers=headers, timeout=15)
            data = json.loads(rsp.text)
            if str(data.get('rescode', -1)) != '0':
                return None
            return self._decrypt_response(data)
        except Exception:
            return None

    # ========== 数据格式化 ==========

    @staticmethod
    def _fix_pic(pic_obj):
        if not pic_obj:
            return ''
        if isinstance(pic_obj, dict):
            for k in ('url', 'poster', 'thumb', 'posterThumb'):
                v = pic_obj.get(k)
                if v:
                    return str(v)
            return ''
        return str(pic_obj)

    @staticmethod
    def _format_remarks(item):
        for k in ('conerMemo', 'detailMemo', 'shorthand'):
            v = item.get(k)
            if v:
                return str(v)
        return ''

    def _format_vod(self, item):
        return {
            'vod_id': str(item.get('sid', '')),
            'vod_name': str(item.get('name', '')),
            'vod_pic': self._fix_pic(item.get('image')),
            'vod_remarks': self._format_remarks(item),
        }

    @staticmethod
    def _format_remarks_detail(series):
        """详情页集数备注（count 字段是 {"topic":xxx} 对象，取不到集数）"""
        for k in ('conerMemo', 'detailMemo'):
            v = series.get(k)
            if v:
                return str(v)
        try:
            last = int(series.get('lastSerialNo') or 0)
        except (TypeError, ValueError):
            last = 0
        if last:
            return f'{last}集全' if series.get('finished') else f'更新至{last}集'
        return ''

    @staticmethod
    def _type_name(category):
        return {'1': '韩剧', '2': '综艺', '3': '电影'}.get(str(category or ''), '')

    @staticmethod
    def _clean_html(text):
        text = str(text or '')
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
        text = re.sub(r'</?(p|div|h[1-6]|ul|li|ol|section|article)[^>]*>', '\n', text, flags=re.I)
        text = re.sub(r'<[^>]*>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        return re.sub(r'[ \t]+', ' ', text).strip()

    @staticmethod
    def _parse_qualities(series):
        qualities = []
        for q in series.get('scopeQualities', []) or []:
            name = f"{q.get('name', '')}{q.get('resolution', '')}".strip()
            value = str(q.get('value', ''))
            vtype = str(q.get('vtype', '0'))
            if name and value:
                qualities.append([name, value, vtype])
        return qualities or DEFAULT_QUALITIES

    @staticmethod
    def _year_from(series):
        y = series.get('year')
        if y:
            return str(y)
        pt = series.get('publishTime') or 0
        try:
            pt = int(pt)
        except (TypeError, ValueError):
            return ''
        return time.strftime('%Y', time.localtime(pt / 1000)) if pt > 0 else ''

    # ========== 首页 ==========

    def homeContent(self, filter):
        result = {}
        cate_data = self._api_get('/api/series2/arrange/cate', {'stype': '1', 'page': '1'})
        classes = []
        filters = {}

        if cate_data:
            sorts = self._build_filter_values(cate_data.get('sorts', []), False)
            years = self._build_filter_values(cate_data.get('years', []), False)
            for g in cate_data.get('groups', []) or []:
                tid = str(g.get('stype', ''))
                tname = str(g.get('name', ''))
                if not tid or not tname:
                    continue
                classes.append({'type_id': tid, 'type_name': tname})
                fl = []
                cates = self._build_filter_values(g.get('cates', []), True)
                if cates:
                    fl.append({'key': 'cid', 'name': '类型', 'value': cates})
                if sorts:
                    fl.append({'key': 'sort', 'name': '排序', 'value': sorts})
                if years:
                    fl.append({'key': 'year', 'name': '年份', 'value': years})
                if fl:
                    filters[tid] = fl

        if not classes:
            classes = [
                {'type_id': '1', 'type_name': '韩剧'},
                {'type_id': '2', 'type_name': '综艺'},
                {'type_id': '3', 'type_name': '电影'},
            ]

        result['class'] = classes
        if filter:
            result['filters'] = filters
        # 必须有 list，否则首页一片空白（此前遗漏）
        try:
            result['list'] = self.homeVideoContent().get('list', [])
        except Exception:
            result['list'] = []
        return result

    @staticmethod
    def _build_filter_values(items, with_all):
        result = [{'n': '全部', 'v': '-1'}] if with_all else []
        for item in items or []:
            n = str(item.get('name', ''))
            v = str(item.get('value', ''))
            if n and v and v != '-1':
                result.append({'n': n, 'v': v})
        return result

    def homeVideoContent(self):
        rec = self._api_get('/api/index/recommend_v5', {'page': '1'})
        videos = []
        seen = set()
        if rec:
            for item in rec.get('seriesList', []) or []:
                self._add_vod(videos, seen, item)
            for blk in rec.get('mediaBlocks', []) or []:
                for item in blk.get('seriesList', []) or []:
                    self._add_vod(videos, seen, item)
        if not videos:
            cate = self._api_get('/api/series2/arrange/cate', {'stype': '1', 'page': '1'})
            for item in (cate or {}).get('seriesList', []) or []:
                self._add_vod(videos, seen, item)
        return {'list': videos[:72]}

    def _add_vod(self, videos, seen, item):
        if not isinstance(item, dict):
            return
        sid = str(item.get('sid', ''))
        if sid and item.get('name') and sid not in seen:
            seen.add(sid)
            videos.append(self._format_vod(item))

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        pg = 1 if pg < 1 else pg
        params = {
            'stype': str(tid or '1'),
            'page': str(pg),
            'cid': str((extend or {}).get('cid') or '-1'),
            'year': str((extend or {}).get('year') or '-1'),
        }
        sort = (extend or {}).get('sort', '')
        if sort:
            params['sort'] = sort

        data = self._api_get('/api/series2/arrange/cate', params)
        videos = []
        pagecount = pg
        if data:
            seen = set()
            for item in data.get('seriesList', []) or []:
                self._add_vod(videos, seen, item)
            if int(data.get('more', 0) or 0) > 0 or len(videos) >= 20:
                pagecount = pg + 1

        return {
            'list': videos,
            'page': str(pg),
            'pagecount': pagecount,
            'limit': max(len(videos), 1),
            'total': 0,
        }

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        pg = 1 if pg < 1 else pg
        keyword = str(key or '').strip()
        if not keyword:
            return {'list': []}

        data = self._api_get('/api/search/s4', {
            'srefer': 'search', 'type': '0', 'page': str(pg), 'k': keyword,
        })
        videos = []
        has_more = False
        if data:
            seen = set()
            for item in data.get('seriesList', []) or []:
                self._add_vod(videos, seen, item)
            has_more = bool(data.get('more')) or len(videos) >= 18

        return {
            'list': videos,
            'page': str(pg),
            'pagecount': pg + 1 if has_more else pg,
            'limit': max(len(videos), 1),
            'total': 0,
        }

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    # ========== 详情页 ==========

    def detailContent(self, ids):
        ids = [ids] if isinstance(ids, str) else (ids or [])
        sid = str(ids[0]) if ids else ''

        vod = {
            'vod_id': sid, 'vod_name': '', 'vod_pic': '', 'type_name': '',
            'vod_year': '', 'vod_area': '韩国', 'vod_remarks': '',
            'vod_actor': '', 'vod_director': '', 'vod_content': '',
            'vod_play_from': '', 'vod_play_url': '',
        }

        data = self._api_get('/api/series2/detail/normal', {'sid': sid}) if sid else None
        if not data:
            vod['vod_play_from'] = '默认线路'
            vod['vod_play_url'] = f'正片${sid}|||||||10|||1'
            return {'list': [vod]}

        series = data.get('series', {}) or {}
        play_items = [p for p in (data.get('playItems', []) or []) if p.get('pid')]

        vod['vod_name'] = str(series.get('name', ''))
        vod['vod_pic'] = self._fix_pic(series.get('image'))
        vod['vod_remarks'] = self._format_remarks_detail(series)
        vod['type_name'] = self._type_name(series.get('category', 0))
        vod['vod_year'] = self._year_from(series)
        vod['vod_content'] = self._clean_html(series.get('intro', '') or series.get('shorthand', ''))

        crew = str(series.get('crew', '') or '')
        vod['vod_actor'] = re.sub(r'^主演[:：]\s*', '', crew).strip()
        m = re.search(r'导演[:：]\s*([^\n，,]+)', vod['vod_content'])
        if m:
            vod['vod_director'] = m.group(1).strip()

        if not play_items:
            vod['vod_play_from'] = '默认线路'
            vod['vod_play_url'] = f'正片${sid}|||||||10|||1'
            return {'list': [vod]}

        qualities = self._parse_qualities(series)
        play_from_list = []
        play_url_list = []

        for q_name, q_value, q_vtype in qualities:
            play_from_list.append(q_name)
            eps = []
            for idx, item in enumerate(play_items):
                pid = str(item.get('pid', ''))
                no = str(item.get('serialNo', idx + 1))
                title = str(item.get('title', '') or '')
                ep_name = f'【{no}】{title}' if title else f'第{no}集'
                # sid ||| pid ||| scid(留空,播放时获取) ||| sq ||| re(vtype)
                eps.append(f'{ep_name}$' + '|||'.join([sid, pid, '', q_value, q_vtype]))
            play_url_list.append('#'.join(eps))

        vod['vod_play_from'] = '$$$'.join(play_from_list)
        vod['vod_play_url'] = '$$$'.join(play_url_list)
        return {'list': [vod]}

    def _get_scid(self, pid):
        """获取集数的播放源 scid（带缓存）"""
        if not pid:
            return ''
        cached = self._scid_cache.get(pid)
        if cached:
            return cached
        data = self._api_get('/api/series2/episode/detail', {'pid': pid})
        try:
            sources = (data or {}).get('playItem', {}).get('sources', []) or []
            for s in sources:
                scid = str(s.get('scid', ''))
                if scid:
                    self._scid_cache[pid] = scid
                    return scid
        except Exception:
            pass
        return ''

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = str(id).split('|||')
            parts += [''] * (5 - len(parts))
            sid, pid, scid, sq, re_val = parts[0], parts[1], parts[2], parts[3] or '10', parts[4] or '0'

            if not pid:
                return {}

            if not scid:
                scid = self._get_scid(pid)
            if not scid:
                return {}

            header = {'User-Agent': PLAY_UA}
            result = self._resolve(sid, pid, scid, sq, re_val)
            if not result:
                # ttk 可能失效，清缓存重试一次
                self._reward_cache.pop(pid, None)
                result = self._resolve(sid, pid, scid, sq, re_val)
            if not result:
                return {}

            url = result.get('url', '')
            if not url:
                return {}
            hdr = result.get('header') or header

            # CDN 只提供 http 明文（https 握手直接失败），Android 9+ 的
            # cleartext 策略会拦截直连；且 m3u8 里的 TS 是根相对路径。
            # 统一改走本地代理，由 python 侧代拉。
            out = {'parse': 0, 'playUrl': '', 'url': self._proxify_multi(url), 'header': hdr}
            if '.m3u8' in url:
                out['format'] = 'application/x-mpegURL'
                out['contentType'] = 'application/x-mpegURL'
            return out
        except Exception:
            return {}

    def _resolve(self, sid, pid, scid, sq, re_val):
        """请求 rslvV4 并解密出播放地址"""
        ttk = self._get_reward_token(pid)
        if not ttk:
            return None

        t = str(int(time.time()))
        udid = self._md5(self.uid)
        sign = self._md5(
            f'&version={VN}&uuid={self.device_id}&udid={udid}&ttk={ttk}&t={t}'
            f'&sq={sq}&scid={scid}&re={re_val}&pid={pid}&dt=android&{SALT_L1T}'
        )
        play_data = self._api_get('/api/series/rslvV4', {
            'version': VN, 'uuid': self.device_id, 't': t, 'sq': sq, 'scid': scid,
            're': re_val, 'pid': pid, 'dt': 'android', 'ttk': ttk, 'sign': sign,
        })
        if not play_data:
            return None

        urls = []
        for item in play_data.get('datas', []) or []:
            info = self._decrypt_play_data(str(item.get('data', '')))
            if not info:
                continue
            u = self._fix_play_url(info.get('url', ''))
            if u:
                urls.append((u, info.get('header') or {}))

        if not urls:
            return None

        url, hdr = urls[0]
        if len(urls) > 1:
            url = '***'.join(u for u, _ in urls)
        return {'url': url, 'header': hdr or {'User-Agent': PLAY_UA}}

    def _play_key_candidates(self, ts=''):
        """播放数据解密密钥候选（第一个是已验证正确的）"""
        udid = self._md5(self.uid)
        c = []
        c.append((self._md5(udid + SALT_SV0), 'md5(md5(uid)+sV0)'))
        if ts:
            c.append((self._md5(udid + ts + SALT_SV0), 'md5(md5(uid)+ts+sV0)'))
            c.append((self._md5(self._md5(self.uid + ts) + SALT_SV0), 'md5(md5(uid+ts)+sV0)'))
        c.append((self._md5(self.uid + SALT_SV0), 'md5(uid+sV0)'))
        for k in LEGACY_PLAY_KEYS:
            c.append((None, k))
        return c

    def _decrypt_play_data(self, raw):
        """解密 rslvV4 的 datas[].data -> {url, header}"""
        if not raw:
            return None
        # 明文直传
        if raw.strip().startswith('{'):
            return self._parse_play_obj(raw.strip())

        try:
            data = base64.b64decode(raw)
        except Exception:
            return None
        if not data or len(data) % 16:
            return None

        ts = str(int(time.time() * 1000))
        for key_or_none, label in self._play_key_candidates(ts):
            if key_or_none is None:      # 固定字符串 key
                kb = label.encode('utf-8')[:16]
                pt = self._aes_decrypt_raw(data, kb, kb)
            else:
                pt = self._aes_decrypt_raw(data, key_or_none[:16], key_or_none[16:32])
            if not pt:
                continue
            try:
                text = pt.decode('utf-8', 'ignore').strip()
            except Exception:
                continue
            if 'http' not in text[:200] and '{' not in text[:5]:
                continue
            text = text.rstrip('\x00').strip()
            obj = self._parse_play_obj(text)
            if obj:
                return obj
        return None

    def _parse_play_obj(self, text):
        """从明文（URL 或 JSON）中提取播放地址与header"""
        text = str(text or '').strip()
        if not text:
            return None
        if text.startswith('{'):
            try:
                obj = json.loads(self._trim_json(text))
            except Exception:
                return None
            url = str(obj.get('playUrl') or obj.get('url') or '')
            hdr = obj.get('header') or {}
            if isinstance(hdr, dict):
                hdr = {str(k): str(v) for k, v in hdr.items()}
            else:
                hdr = {}
            if not url:
                return None
            return {'url': url, 'header': hdr or {'User-Agent': PLAY_UA}}
        if text.lower().startswith('http'):
            return {'url': text, 'header': {'User-Agent': PLAY_UA}}
        return None

    @staticmethod
    def _fix_play_url(url):
        """规范化播放URL。注意：CDN 域名会变(voldn-ser01 / piccc.cdn 等)，不要硬编码改写"""
        url = str(url or '').strip()
        if not url:
            return ''
        url = url.replace('&#38;', '&').replace('&amp;', '&').replace(' ', '%20')
        return url

    def _get_reward_token(self, pid):
        """获取播放凭证 (reward token)"""
        cached = self._reward_cache.get(pid)
        if cached and time.time() * 1000 < cached['expire_at']:
            return cached['token']

        reward = self._api_get('/api/carp/reward/v2', {'scene': 'ad_series_play'})
        trace_id = str((reward or {}).get('traceId', ''))
        if not trace_id:
            return ''

        uid_md5 = self._md5(self.uid)
        body = json.dumps({'pid': pid, 'scene': 'ad_series_play', 'traceId': trace_id})
        enc = self._aes_encrypt(body, uid_md5[:16], uid_md5[16:32])
        result = self._api_post('/api/carp/reward/rp/v2', json.dumps({'data': enc}),
                                {'aps': self._md5(enc + REWARD_SALT)})
        try:
            info = (result or {}).get('rewardTokenInfo', {}) or {}
            token = str(info.get('token', ''))
            if token:
                expire = int(info.get('expireTime') or info.get('expires') or 21600)
                self._reward_cache[pid] = {
                    'token': token,
                    'expire_at': time.time() * 1000 + max(60, expire - 60) * 1000,
                }
                return token
        except Exception:
            pass
        return ''

    # ========== 本地代理（把 http 明文流 + 相对路径TS 全部转为本地代理地址） ==========

    def _proxy_base(self):
        """取壳子提供的代理基址；取不到则返回空串（此时只能直连）"""
        cached = getattr(self, '_pb', None)
        if cached is not None:
            return cached
        base = ''
        for name in ('getProxyUrl', 'getProxy', 'getProxyURL'):
            try:
                fn = getattr(self, name, None)
                if fn is None:
                    continue
                val = fn() if callable(fn) else fn
                if isinstance(val, str) and val.strip():
                    base = val.strip()
                    break
            except Exception:
                continue
        self._pb = base
        return base

    def _proxify(self, url):
        """
        单个地址包一层本地代理。
        CDN 会随机返回 http / https，且部分域名(piccc.cdn)的 https 直接握手失败，
        所以两种协议统一走代理，由 python 侧按实际可用性代拉。
        """
        url = str(url or '').strip()
        if not url.lower().startswith(('http://', 'https://')):
            return url
        base = self._proxy_base()
        if not base:
            return url
        b = base.rstrip()
        if b.endswith('url='):
            return b + quote(url, safe='')
        b = b.rstrip('&').rstrip('?')
        sep = '&' if '?' in b else '?'
        return b + sep + 'url=' + quote(url, safe='')

    def _proxify_multi(self, url):
        """按 ***（多线路）拆分，逐条包代理"""
        return '***'.join(self._proxify(u) for u in str(url or '').split('***'))

    @staticmethod
    def _param_url(param):
        """从 localProxy 入参里取出真实地址"""
        import urllib.parse as up
        raw = ''
        if isinstance(param, dict):
            raw = param.get('url') or param.get('u') or ''
        elif isinstance(param, str):
            p = param.strip()
            # 只有传入的是完整 proxy url 时才需要剥掉 path，
            # 纯 query 里本身可能带 ?（目标地址的 query），不能乱切
            if p.lower().startswith('http'):
                p = p.split('?', 1)[1] if '?' in p else ''
            qs = up.parse_qs(p, keep_blank_values=True)
            raw = (qs.get('url') or qs.get('u') or [''])[0]
            if not raw and param.strip().lower().startswith('http'):
                raw = param.strip()
        raw = str(raw or '').strip()
        if raw.lower().startswith('http'):
            return raw
        return up.unquote(raw) if '%' in raw else raw

    @staticmethod
    def _guess_ctype(url, is_m3u8):
        low = str(url or '').lower()
        if is_m3u8:
            return 'application/vnd.apple.mpegurl; charset=utf-8'
        for ext, ct in (('.ts', 'video/mp2t'), ('.mp4', 'video/mp4'),
                        ('.m4s', 'video/iso.segment'), ('.aac', 'audio/aac'),
                        ('.m4a', 'audio/mp4'), ('.vtt', 'text/vtt'),
                        ('.srt', 'application/x-subrip')):
            if ext in low:
                return ct
        return 'application/octet-stream'

    def _fetch_media(self, url, timeout=30):
        """代拉远端媒体：https 失败时自动降级 http"""
        hdr = {'User-Agent': PLAY_UA}
        rsp = None
        try:
            rsp = self.fetch(url, headers=hdr, timeout=timeout)
        except Exception:
            rsp = None
        if rsp is not None:
            code = getattr(rsp, 'status_code', 200) or 200
            if code < 400:
                return rsp
        if url.startswith('https://'):
            try:
                alt = self.fetch('http://' + url[8:], headers=hdr, timeout=timeout)
                if alt is not None and (getattr(alt, 'status_code', 200) or 200) < 400:
                    return alt
            except Exception:
                pass
        return rsp

    def localProxy(self, param):
        """
        本地代理：
          - m3u8 -> 把根相对路径的 TS / KEY 全部改写成代理地址（递归代理）
          - 其它 -> 直接把远端内容透传回播放器
        """
        try:
            media_url = self._param_url(param)
            if not media_url.lower().startswith('http'):
                return [404, 'text/plain', b'']

            rsp = self._fetch_media(media_url)
            if rsp is None:
                return [502, 'text/plain', b'upstream error']
            content = rsp.content if hasattr(rsp, 'content') else str(getattr(rsp, 'text', '') or '').encode('utf-8')
            if content is None:
                return [502, 'text/plain', b'empty upstream']

            try:
                text = content.decode('utf-8')
            except Exception:
                return [200, self._guess_ctype(media_url, False), content]

            if '#EXTM3U' not in text[:400]:
                return [200, self._guess_ctype(media_url, False), content]

            sp = urlsplit(media_url)
            origin = urlunsplit((sp.scheme, sp.netloc, '', '', ''))
            query = ('?' + sp.query) if sp.query else ''

            def _abs(u):
                u = u.strip().strip('"')
                if u.startswith('//'):
                    return sp.scheme + ':' + u
                if u.startswith('/'):
                    return origin + u + query
                if u.lower().startswith(('http', 'data:', 'skd:')):
                    return u
                return urljoin(media_url, u)

            out = []
            for line in text.splitlines():
                s = line.strip()
                if not s:
                    out.append(line)
                    continue
                if s.startswith('#'):
                    if 'URI=' in s:
                        m = re.search(r'URI="([^"]+)"', line)
                        if m:
                            line = (line[:m.start(1)] + self._proxify(_abs(m.group(1)))
                                    + line[m.end(1):])
                    out.append(line)
                    continue
                out.append(self._proxify(_abs(s)))
            return [200, 'application/vnd.apple.mpegurl; charset=utf-8',
                    '\n'.join(out).encode('utf-8')]
        except Exception:
            return [500, 'text/plain', b'proxy error']

    # ========== 可选接口 ==========

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|mkv|avi)(\?|$)', url or '', re.I))

    def manualVideoCheck(self):
        return True

    def destroy(self):
        pass

    def close(self):
        self.destroy()


if __name__ == '__main__':
    # 本地自测：python 韩剧秒播.py
    s = Spider()
    s.init()
    print('--- homeContent ---')
    print(json.dumps(s.homeContent(True), ensure_ascii=False)[:400])
    print('--- homeVideoContent ---')
    hv = s.homeVideoContent()
    print(f"{len(hv['list'])} 条, 样例: {json.dumps(hv['list'][0], ensure_ascii=False)[:200]}")
    print('--- categoryContent ---')
    print(json.dumps(s.categoryContent('1', '1', True, {}), ensure_ascii=False)[:400])
    print('--- searchContent ---')
    sr = s.searchContent('财阀', False, '1')
    print(json.dumps(sr, ensure_ascii=False)[:400])
    sid = hv['list'][0]['vod_id']
    print('--- detailContent ---')
    dt = s.detailContent([sid])['list'][0]
    print(json.dumps({k: v for k, v in dt.items() if k != 'vod_play_url'}, ensure_ascii=False))
    print('  线路:', dt['vod_play_from'], '| 首集:', dt['vod_play_url'].split('$$$')[0].split('#')[0])
    print('--- playerContent (模拟壳子提供代理) ---')
    s.getProxyUrl = lambda: 'http://127.0.0.1:9978/proxy?do=py&type=all&'
    flag = dt['vod_play_from'].split('$$$')[0]
    pid_full = dt['vod_play_url'].split('$$$')[0].split('#')[0].split('$', 1)[1]
    pc = s.playerContent(flag, pid_full, [])
    print(json.dumps(pc, ensure_ascii=False))

    print('--- 经代理取流 ---')
    code, ctype, body = s.localProxy(pc['url'].split('?', 1)[1])
    print(f'code={code} ctype={ctype} size={len(body)}')
    if b'#EXTM3U' in body[:400]:
        m3 = body.decode('utf-8', 'ignore')
        segs = [ln.strip() for ln in m3.splitlines() if ln.strip() and not ln.startswith('#')]
        print(f'm3u8 分片数={len(segs)} 全走代理={all(x.startswith("http://127.0.0.1") for x in segs)}')
        if segs:
            c2, t2, b2 = s.localProxy(segs[0].split('?', 1)[1])
            print(f'TS: code={c2} ctype={t2} size={len(b2)} 头={b2[:4]}')
    else:
        print(f'直链透传: {body[:16]}')
