# -*- coding: utf-8 -*-
# ============================================================
# 人人视频 drpy 爬虫（TVBox / CatVod）  type=3
# 目标站点：https://mh.yichengwlkj.com/  (PC 站, 品牌: 人人视频)
# 说明：
#   - 站点为 Next.js + 自有 API(api.rrmj.plus)，所有数据接口需
#     HMAC-SHA256 请求签名，响应体 AES-128-ECB 解密
#   - 纯标准库实现（urllib + hmac + hashlib + base64 + 纯 Python AES），
#     不依赖 requests / lxml / pycryptodome
#   - 播放：vod_play_url 使用协议串 rrmj://{dramaId}/{episodeSid}，
#     playerContent 时实时请求 /m-station/drama/play 换取带签名直链
#     （AES-128-CBC，key=newSign[4:20]，iv=b1da7878016e4e2b），
#     每次取链签名全新、无过期问题；受限内容回落播放页 parse=1
# ============================================================
import base64
import hashlib
import hmac
import json
import re
import time
import uuid

# === 站点常量 ===
HOST = "https://mh.yichengwlkj.com"
API_HOST = "https://api.rrmj.plus"
PLAY_PAGE = HOST + "/pc/drama/{drama_id}?episodeNo={ep}"

# 签名密钥与解密密钥（来自前端 JS 源码分析）
SIGN_SECRET = "ES513W0B1CsdUrR13Qk5EgDAKPeeKZY"
AES_KEY = "3b744389882a4067"  # 16 字节 -> AES-128
CLIENT_TYPE = "web_pc"
CLIENT_VERSION = "1.0.0"

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.7827.3 Safari/537.36"
REFERER = "https://mh.yichengwlkj.com/"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": REFERER,
    "Accept": "application/json, text/plain, */*",
}

# === 纯 Python AES-128 解密（FIPS-197）===
_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
_INV_SBOX = [0] * 256
for _i in range(256):
    _INV_SBOX[_SBOX[_i]] = _i
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]
_AES_TRY = []


def _xtime(a):
    return ((a << 1) ^ (0x1b if (a & 0x80) else 0)) & 0xff


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _expand_key(key_bytes):
    nk, nb, nr = 4, 4, 10
    w = list(key_bytes)
    i = nk
    while i < nb * (nr + 1):
        t = w[(i - 1) * 4:(i - 1) * 4 + 4]
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        for j in range(4):
            w.append(w[(i - nk) * 4 + j] ^ t[j])
        i += 1
    return w


def _inv_shift_rows(s):
    return [
        s[0], s[13], s[10], s[7],
        s[4], s[1], s[14], s[11],
        s[8], s[5], s[2], s[15],
        s[12], s[9], s[6], s[3],
    ]


def _add_round_key(s, k):
    return [s[i] ^ k[i] for i in range(16)]


def _inv_mix_columns(s):
    out = []
    for c in range(0, 16, 4):
        a0, a1, a2, a3 = s[c], s[c + 1], s[c + 2], s[c + 3]
        out += [
            _gmul(a0, 0x0e) ^ _gmul(a1, 0x0b) ^ _gmul(a2, 0x0d) ^ _gmul(a3, 0x09),
            _gmul(a0, 0x09) ^ _gmul(a1, 0x0e) ^ _gmul(a2, 0x0b) ^ _gmul(a3, 0x0d),
            _gmul(a0, 0x0d) ^ _gmul(a1, 0x09) ^ _gmul(a2, 0x0e) ^ _gmul(a3, 0x0b),
            _gmul(a0, 0x0b) ^ _gmul(a1, 0x0d) ^ _gmul(a2, 0x09) ^ _gmul(a3, 0x0e),
        ]
    return out


def _aes_ecb_decrypt_pure(data, key):
    """纯 Python AES-128 ECB 解密（标准 FIPS-197 流程）"""
    w = _expand_key(list(key))
    out = bytearray()
    for off in range(0, len(data) - 15, 16):
        s = list(data[off:off + 16])
        s = _add_round_key(s, w[160:176])
        for rnd in range(9, 0, -1):
            s = _inv_shift_rows(s)
            s = [_INV_SBOX[b] for b in s]
            s = _add_round_key(s, w[rnd * 16:rnd * 16 + 16])
            s = _inv_mix_columns(s)
        s = _inv_shift_rows(s)
        s = [_INV_SBOX[b] for b in s]
        s = _add_round_key(s, w[0:16])
        out.extend(s)
    return bytes(out)


def _decrypt_aes(data, key):
    """解密密文（多级降级）：pycryptodome -> 纯 Python"""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        return unpad(AES.new(key, AES.MODE_ECB).decrypt(data), 16)
    except Exception:
        pass
    try:
        from Cryptodome.Cipher import AES as A2
        from Cryptodome.Util.Padding import unpad as u2
        return u2(A2.new(key, A2.MODE_ECB).decrypt(data), 16)
    except Exception:
        pass
    return _aes_ecb_decrypt_pure(data, key)


# === HTTP 请求 ===
try:
    import urllib.request as _urq
    import urllib.error as _ure
    import urllib.parse as _urp
    _HAS_URLLIB = True
except Exception:
    _HAS_URLLIB = False

try:
    import ssl as _ssl_mod
    _SSL_CTX = _ssl_mod._create_unverified_context()
except Exception:
    _SSL_CTX = None

try:
    import gzip as _gzip_mod
except Exception:
    _gzip_mod = None

_DEVICE_ID = None
_last_ts = 0


def _device_id():
    global _DEVICE_ID
    if _DEVICE_ID is None:
        _DEVICE_ID = str(uuid.uuid4()).upper()
    return _DEVICE_ID


def _throttle(interval=0.4):
    """轻量请求节流，避免触发站点 429 限流"""
    global _last_ts
    now = time.time()
    gap = interval - (now - _last_ts)
    if gap > 0:
        time.sleep(gap)
    _last_ts = time.time()


def _sign(path, method="GET"):
    """生成 x-ca-sign 请求签名（HMAC-SHA256 -> Base64）"""
    ts = int(time.time() * 1000)
    raw = "{}\naliId:{}\nct:{}\ncv:{}\nt:{}\n{}".format(
        method, _device_id(), CLIENT_TYPE, CLIENT_VERSION, ts, path)
    sig = base64.b64encode(
        hmac.new(SIGN_SECRET.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return sig, str(ts)


def _build_path(path, params):
    """按 URLSearchParams 语义排序并拼接 query（与前端签名串一致）"""
    if not params:
        return path
    qs = _urp.urlencode(sorted(params.items()))
    return path + "?" + qs


def _request(path, params=None, method="GET", timeout=12):
    """请求加密 API 并解密为 dict；失败返回 None"""
    _throttle()
    url_path = _build_path(path, params)
    sig, ts = _sign(url_path, method)
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": REFERER,
        "Accept": "application/json, text/plain, */*",
        "clientversion": CLIENT_VERSION,
        "cv": CLIENT_VERSION,
        "ct": CLIENT_TYPE,
        "clienttype": CLIENT_TYPE,
        "deviceid": _device_id(),
        "umid": _device_id(),
        "aliId": _device_id(),
        "token": "",
        "t": ts,
        "x-ca-sign": sig,
        "uet": "9",
    }
    data = None
    if method == "POST" and params is not None:
        body = {}
        for k, v in params.items():
            body[k] = v
            if isinstance(v, (dict, list)):
                body[k] = json.dumps(v, ensure_ascii=False)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        url_path = _build_path(path, None)
        sig, ts = _sign(url_path, method)
        headers["t"] = ts
        headers["x-ca-sign"] = sig
    url = API_HOST + url_path
    for attempt in range(2):
        try:
            req = _urq.Request(url, data=data, headers=headers, method=method)
            if _SSL_CTX is not None:
                # TVBox 环境通常无 CA 证书，跳过校验
                resp = _urq.urlopen(req, timeout=timeout, context=_SSL_CTX)
            else:
                resp = _urq.urlopen(req, timeout=timeout)
            try:
                raw = resp.read()
                enc = ""
                try:
                    enc = (resp.headers.get("Content-Encoding") or "").lower()
                except Exception:
                    pass
                if "gzip" in enc and _gzip_mod is not None:
                    try:
                        raw = _gzip_mod.decompress(raw)
                    except Exception:
                        pass
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            return _parse_response(raw)
        except Exception as e:
            if attempt == 0 and getattr(e, "code", None) == 429:
                time.sleep(2.0)
                continue
            try:
                if getattr(e, "code", None) and str(getattr(e, "code", None)) != "200":
                    pass
            except Exception:
                pass
    return None


def _parse_response(raw):
    """响应可能是明文 JSON（错误）或 AES-ECB 加密 base64（成功）"""
    try:
        text = raw.decode("utf-8", errors="replace").strip()
        if text.startswith("{"):
            return json.loads(text)
        ct = base64.b64decode(text)
        plain = _decrypt_aes(ct, AES_KEY.encode("utf-8"))
        # PKCS7 unpad
        pad = plain[-1]
        if 0 < pad <= 16:
            plain = plain[:-pad]
        return json.loads(plain.decode("utf-8"))
    except Exception:
        return None


# === 数据接口 ===
def _get_category():
    """分类列表：id / name / target（CHANNEL_XXX）"""
    r = _request("/m-station/app/category")
    lst = []
    if r and r.get("data"):
        for idx, item in enumerate(r["data"] or []):
            name = item.get("name") or ""
            target = item.get("target") or ""
            if not name:
                continue
            lst.append({
                "type_id": str(idx + 1),
                "type_name": name,
                "target": target,
            })
    return lst


def _get_list(target, page_num=1):
    """频道列表：sections 内全部 sectionContents 合并去重"""
    r = _request("/m-station/app/page", {
        "position": target,
        "pageNum": page_num,
        "personalRecommend": 0,
    })
    out = []
    is_end = True
    if r and r.get("data"):
        d = r["data"]
        is_end = bool(d.get("isEnd", True))
        for sec in (d.get("sections") or []):
            for item in (sec.get("sectionContents") or []):
                if not item or not item.get("dramaId"):
                    continue
                out.append(item)
    return out, is_end


def _fmt_vod(item):
    """列表条目 -> TVBox vod dict"""
    pic = _norm_pic(item.get("coverUrl") or item.get("cover3Url") or "")
    year = item.get("year") or ""
    ep_n = item.get("episodeCount")
    remarks = ""
    if ep_n:
        remarks = "共{}集".format(ep_n) if int(ep_n) > 1 else "电影"
    vod = {
        "vod_id": str(item.get("dramaId")),
        "vod_name": item.get("title") or "",
        "vod_pic": pic,
        "vod_remarks": remarks,
        "vod_year": str(year),
    }
    score = item.get("score")
    if score:
        vod["vod_score"] = str(score)
    return vod


def _get_detail(drama_id):
    """详情：intro（简介/演职员）+ page（剧集/播放）"""
    intro = {}
    r1 = _request("/m-station/drama/intro", {"dramaId": drama_id})
    if r1 and r1.get("data"):
        d1 = r1["data"]
        actors = []
        directors = []
        for a in (d1.get("actorList") or []):
            cn = (a.get("chineseName") or "").strip()
            role = (a.get("roleName") or "").strip()
            if not cn:
                continue
            if "导演" in role:
                directors.append(cn)
            else:
                actors.append(cn)
        intro = {
            "intro": d1.get("intro") or "",
            "title": d1.get("title") or "",
            "subTitle": d1.get("subTitle") or "",
            "year": d1.get("year") or "",
            "area": d1.get("area") or "",
            "plotType": d1.get("plotType") or "",
            "actors": ",".join(actors),
            "directors": ",".join(directors),
        }
    page = {}
    play_url = None  # 已解密的第 1 集直链（若可用）
    r2 = _request("/m-station/drama/page", {
        "dramaId": drama_id,
        "quality": "AI4K",
        "hevcOpen": 0,
        "hsdrOpen": 0,
        "isAgeLimit": 0,
        "tria4k": 1,
    })
    if r2 and r2.get("data"):
        d2 = r2["data"]
        page = d2
        watch = d2.get("watchInfo") or {}
        if watch and watch.get("m3u8") and watch["m3u8"].get("url"):
            enc = watch["m3u8"]["url"]
            play_url = _decrypt_play_url(enc, d2.get("newSign"))
    return intro, page, play_url


def _get_search(keywords, page_num=1):
    """搜索：综合精确/模糊搜索，取 fuzzySeasonList 与 seasonList"""
    r = _request("/search/comprehensive/precise-mixed", {
        "keywords": keywords,
        "pageNum": page_num,
        "pageSize": 20,
    })
    out = []
    if r and r.get("data"):
        d = r["data"]
        for grp in (d.get("seasonList") or [], d.get("fuzzySeasonList") or []):
            for item in grp or []:
                vid = item.get("id")
                if not vid:
                    continue
                pic = _norm_pic(item.get("cover") or "")
                vod = {
                    "vod_id": str(vid),
                    "vod_name": item.get("title") or "",
                    "vod_pic": pic,
                    "vod_year": str(item.get("year") or ""),
                    "vod_remarks": (item.get("classify") or "") if item.get("classify") else "",
                }
                if item.get("score"):
                    vod["vod_score"] = str(item["score"])
                out.append(vod)
    return out


def _decrypt_play_url(enc_url, new_sign):
    """解密播放直链：AES-128-CBC, key=newSign[4:20], iv=b1da7878016e4e2b"""
    if not enc_url or not new_sign:
        return None
    try:
        key = (new_sign[4:20]).encode("utf-8")
        if len(key) != 16:
            return None
        ct = base64.b64decode(enc_url)
        iv = b"b1da7878016e4e2b"
        prev = iv
        out = b""
        for off in range(0, len(ct), 16):
            blk = _aes_ecb_decrypt_pure(ct[off:off + 16], key)
            out += bytes(a ^ b for a, b in zip(blk, prev))
            prev = ct[off:off + 16]
        pad = out[-1]
        if 0 < pad <= 16:
            out = out[:-pad]
        return out.decode("utf-8", errors="replace")
    except Exception:
        return None


def _fetch_play_url(drama_id, sid=None, quality="AI4K"):
    """请求 /m-station/drama/play 换取解密直链；失败返回 None"""
    params = {
        "dramaId": drama_id,
        "quality": quality,
        "hsdrOpen": 0,
        "hevcOpen": 0,
        "tria4k": 0,
    }
    if sid:
        params["episodeSid"] = sid
    r = _request("/m-station/drama/play", params, timeout=15)
    if not r:
        return None
    d = r.get("data") or {}
    m3u8 = d.get("m3u8") or {}
    enc = m3u8.get("url")
    if not enc:
        return None
    return _decrypt_play_url(enc, d.get("newSign"))


def _build_play_url(page, drama_id):
    """构造 vod_play_url：全部使用协议串 rrmj://{dramaId}/{sid}/{episodeNo}，
    playerContent 时实时请求 play 接口取链（签名每次新鲜、永不过期）"""
    eps = page.get("episodeList") or []
    if eps:
        parts = []
        for ep in eps:
            n = ep.get("episodeNo")
            sid = ep.get("sid") or ep.get("id") or n
            parts.append("第{}集$rrmj://{}/{}/{}".format(n, drama_id, sid, n))
        return "#".join(parts)
    return "正片$rrmj://{}".format(drama_id)


def _parse_play_token(ids):
    """解析 rrmj://{dramaId}/{sid}/{episodeNo} 协议串 -> (drama_id, sid|None, ep|None)"""
    s = (ids or "").strip()
    if not s.startswith("rrmj://"):
        return None, None, None
    rest = s[len("rrmj://"):]
    seg = rest.split("/")
    did = seg[0] or None
    sid = seg[1] if len(seg) > 1 and seg[1] else None
    ep = seg[2] if len(seg) > 2 and seg[2] else None
    return did, sid, ep


_IS_VIDEO_RE = re.compile(r"\.(m3u8|mp4|flv|mp3|aac|ts|mkv|m4a|ogg|wmv|avi)(\?|#|$)", re.I)


def _is_video_format(url):
    return bool(_IS_VIDEO_RE.search(url or ""))


def _norm_pic(url):
    """规范化图片 URL：替换防盗链域 img.bwcgee.cn -> img.rrmj.plus（无防盗链，同图同路径）"""
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("http://"):
        url = "https://" + url[7:]
    return url.replace("img.bwcgee.cn", "img.rrmj.plus")


# === 模块级接口（drpy 双入口之一）===
def homeContent(filterable=False, filters=None):
    """首页：分类 + 推荐列表"""
    classes = _get_category()
    if not classes:
        return {"class": [], "filters": None, "list": []}
    items, _ = _get_list("CHANNEL_INDEX", 1)
    lst = [_fmt_vod(it) for it in items]
    # 合并去重
    seen = set()
    uniq = []
    for v in lst:
        if v["vod_id"] in seen:
            continue
        seen.add(v["vod_id"])
        uniq.append(v)
    return {
        "class": [{"type_id": c["type_id"], "type_name": c["type_name"]} for c in classes],
        "filters": None,
        "list": uniq,
    }


def categoryContent(tid, pg, filter=None, extend=None):
    """分类页：按分类 position 分页拉取列表"""
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    classes = _get_category()
    target = ""
    if classes:
        try:
            idx = int(str(tid).strip()) - 1
            if 0 <= idx < len(classes):
                target = classes[idx].get("target") or ""
        except Exception:
            for c in classes:
                if str(c.get("type_id")) == str(tid).strip():
                    target = c.get("target") or ""
                    break
    if not target:
        if not classes:
            return {"list": [], "page": pg, "pagecount": 1}
        # tid 兜底：按名称匹配
        for c in classes:
            if str(tid) in (c["type_name"], c["type_id"]):
                target = c.get("target") or ""
                break
    if not target:
        return {"list": [], "page": pg, "pagecount": 1}
    items, is_end = _get_list(target, pg)
    return {
        "list": [_fmt_vod(it) for it in items],
        "page": pg,
        "pagecount": pg if is_end else pg + 1,
    }


def detailContent(ids, flags=None):
    """详情：元数据 + 剧集播放列表"""
    vid = ""
    raw = str(ids)
    m2 = re.search(r"\d+", raw)
    if m2:
        vid = m2.group()
    if not vid:
        return {"list": []}
    intro, page, play_url = _get_detail(vid)
    vod = {"vod_id": vid}
    if page:
        di = page.get("dramaInfo") or {}
        vod["vod_name"] = intro.get("title") or di.get("title") or ""
        vod["vod_pic"] = _norm_pic(di.get("cover") or di.get("cover3Url") or "")
        vod["vod_year"] = str(intro.get("year") or di.get("year") or "")
        vod["vod_area"] = intro.get("area") or di.get("area") or ""
        vod["vod_director"] = intro.get("directors") or ""
        vod["vod_actor"] = intro.get("actors") or ""
        vod["vod_score"] = str(di.get("score") or "") if di.get("score") else ""
        vod["vod_content"] = intro.get("intro") or ""
        vod["vod_play_from"] = "人人视频"
        vod["vod_play_url"] = _build_play_url(page, vid)
    else:
        vod["vod_name"] = intro.get("title") or str(vid)
        vod["vod_pic"] = ""
        vod["vod_content"] = intro.get("intro") or ""
        vod["vod_play_from"] = "人人视频"
        vod["vod_play_url"] = "正片$rrmj://{}".format(vid)
    return {"list": [vod]}


def searchContent(keyword, pg="1", quick=False):
    """搜索：综合搜索接口（pg/quick 兼容 TVBox 调用约定）"""
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    lst = _get_search(keyword, pg)
    if not lst:
        return {"list": []}
    return {"list": lst, "page": pg, "pagecount": pg + 1}


def playerContent(flag, ids, vipFlags=None):
    """播放：协议串实时取直链 parse=0；受限内容回落播放页 parse=1"""
    vipFlags = vipFlags if vipFlags else []
    url = (ids or "").strip()
    did, sid, ep = _parse_play_token(url)
    if did:
        # rrmj 协议串 -> play 接口实时取链
        real = _fetch_play_url(did, sid)
        if real:
            return {
                "parse": 0,
                "url": real,
                "header": json.dumps(HEADERS),
            }
        # 受限内容（playRestricted=3 等）无直链 -> 播放页嗅探兜底
        try:
            ep_n = int(ep or 1) or 1
        except Exception:
            ep_n = 1
        page_url = PLAY_PAGE.format(drama_id=did, ep=ep_n)
        return {
            "parse": 1,
            "url": page_url,
            "header": json.dumps(HEADERS),
        }
    if _is_video_format(url):
        return {
            "parse": 0,
            "url": url,
            "header": json.dumps(HEADERS),
        }
    return {
        "parse": 1,
        "url": url,
        "header": json.dumps(HEADERS),
    }


def localProxy(param):
    return ""


# === 旧版接口别名（兼容不同 TVBox 内核）===
categoryContentContent = categoryContent
detailContentContent = detailContent
searchContentContent = searchContent
playerContentContent = playerContent


# === drpy class Spider 包装 ===
try:
    from base.spider import Spider
except Exception:
    Spider = object


class Spider(Spider):
    def init(self, extend=""):
        """TVBox 基类抽象方法；本爬虫无状态初始化，无需 extend"""
        pass

    def __init__(self):
        pass

    def homeContent(self, filterable=False, filters=None):
        return homeContent(filterable, filters)

    def categoryContent(self, tid, pg, filter=None, extend=None):
        return categoryContent(tid, pg, filter, extend)

    def detailContent(self, ids, flags=None):
        return detailContent(ids)

    def searchContent(self, key, quick=False, pg="1"):
        return searchContent(key, pg)

    def playerContent(self, flag, ids, vipFlags=None):
        return playerContent(flag, ids, vipFlags)

    def localProxy(self, param):
        return ""