# coding = utf-8
#!/usr/bin/python
"""
瓜子影视 — TVBox / FongMi TV 爬虫
站点: 瓜子影视 (多线路聚合)
特点: 设备注册 + Token自动刷新 + RSA+AES双重加密
播放: 直连模式 (parse: 0)，非推广44秒
版本: 2.0.0 (从 index.js 提取，完整认证流程)
"""
import re
import sys
import json
import time
import base64
import hashlib
import random
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

        def post(self, url, data=None, headers=None, **kw):
            kw.pop('timeout', None)
            r = requests.post(url, data=data, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    """瓜子影视 Spider — 完整认证流程版"""

    # ─── API 配置 ───
    WE = [
        "https://api.h27sq4f.com",
        "https://api.wbhxjjv.com",
        "https://sdapi.e2wu4ht.com",
        "https://sdapi.7wstgq6.com",
        "https://apinew.uozvr.com",
    ]

    # ─── 加密参数 ───
    AES_KEY = "OITxa5OqAYjhswxx"        # Pc0
    AES_IV = "rCMNwZASNBKZ8mXV"          # Lc0
    OLD_KEY = "aLFBMWpxBrIDAD1Si/KVvm41"  # $c0
    SIGN_SALT = "*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"  # VLt

    # ─── 应用配置 ───
    VER = "3.0.3.2"                      # Mc0
    VERSION = "2604028"                   # jLt
    PACKAGE_NAME = "com.ae06aebdbb.y286327f5a.ofe849883320260517"  # HLt
    CODE = "GZ0369"                       # qLt
    PAGE_SIZE = 30                        # Fj
    TOKEN_REFRESH_INTERVAL = 1800         # YLt (秒)

    # ─── RSA 公钥 (base64 DER) ───
    RSA_PUBLIC_KEY_DER = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259EUwxFXFE5HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsChTEFIR9qUkwrs3/MVUMxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR6ewR5E2kL52yAAD4yQIDAQAB"

    # ─── RSA 私钥 (PEM) ───
    RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1
ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU
1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcK
ZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7
HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcW
V9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdI
DblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34
saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVM
iMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUM
WBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8
jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZ
K7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1b
L3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oa
t5lYKFpe8k83ZA==
-----END RSA PRIVATE KEY-----"""

    # ─── 认证状态 ───
    auth = {
        "device_key": "",
        "device_id": "",
        "token": "",
        "token_id": "",
        "registered": False,
        "token_refreshed_at": 0,
    }
    host_index = 0
    site_url = ""
    loaded = False

    def __init__(self):
        self.name = "瓜子影视"
        self.site_url = self.WE[0]
        self.session = requests.Session()
        self._init_auth()

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        return any(url.lower().endswith(f) for f in ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts'])

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

    def init(self, extend=''):
        pass

    # ═══════════════════════════════════════
    #  认证流程
    # ═══════════════════════════════════════

    def _init_auth(self):
        """初始化认证状态 (QE 函数)"""
        if self.loaded:
            return
        self.loaded = True
        if not self.auth.get("device_key"):
            self.auth["device_key"] = self._random_hex(20)
            self.auth["token"] = ""
            self.auth["token_id"] = ""
            self.auth["registered"] = False
            self.auth["token_refreshed_at"] = 0
        if not self.auth.get("device_id"):
            self.auth["device_id"] = str(86415006000000 + random.randint(0, 9999))

    def _random_hex(self, length):
        """生成随机 hex 字符串 (dMt 函数)"""
        return ''.join(random.choices('0123456789ABCDEF', k=length * 2))

    def _ensure_auth(self, force_refresh=False):
        """确保认证有效 (MA 函数)

        关键: force_refresh=True 时强制刷新 token (播放时使用)
        """
        now = int(time.time())
        if self.auth.get("token") and not force_refresh:
            if now - int(self.auth.get("token_refreshed_at", 0)) < self.TOKEN_REFRESH_INTERVAL:
                return True

        if not self.auth.get("token"):
            try:
                if self.auth.get("registered"):
                    return self._sign_in()
                else:
                    return self._sign_up()
            except Exception as e:
                if self.auth.get("registered"):
                    self.auth["registered"] = False
                    return self._sign_up()
                raise e

        # Token 存在但需要刷新
        if self._refresh_token():
            return True
        try:
            return self._sign_in()
        except Exception:
            self.auth["registered"] = False
            return self._sign_up()

    def _sign_up(self):
        """设备注册 (Wj 函数)"""
        try:
            data = self._api_request("/App/Authentication/Device/signUp", {
                "new_key": self.auth["device_key"],
                "old_key": self.OLD_KEY,
                "phone_type": "1",
                "code": ""
            })
            return self._process_auth_response(data)
        except Exception as e:
            err_msg = str(e)
            if "用户已经存在" in err_msg or "设备号登入" in err_msg:
                self.auth["registered"] = True
                self._refresh_token()
                return self._sign_in()
            raise e

    def _sign_in(self):
        """设备登录 (Gj 函数)"""
        data = self._api_request("/App/Authentication/Device/signIn", {
            "new_key": self.auth["device_key"],
            "old_key": self.OLD_KEY
        })
        return self._process_auth_response(data)

    def _refresh_token(self):
        """刷新 Token (ZLt 函数)"""
        try:
            data = self._api_request("/App/Authentication/Authenticator/refresh", {})
            self._process_auth_response(data)
            return True
        except Exception as e:
            return False

    def _process_auth_response(self, data):
        """处理认证响应 (Vj 函数)"""
        if not data or not data.get("token"):
            raise Exception(f"瓜子认证未返回 token: {json.dumps(data or {}, ensure_ascii=False)[:200]}")
        self.auth["token"] = str(data.get("token", ""))
        self.auth["token_id"] = str(data.get("app_user_id", self.auth.get("token_id", "")))
        self.auth["registered"] = True
        self.auth["token_refreshed_at"] = int(time.time())
        return True

    # ═══════════════════════════════════════
    #  加密 / 解密
    # ═══════════════════════════════════════

    def _aes_encrypt(self, text, key, iv):
        """AES-128-CBC 加密 → hex 大写 (xMt 函数)"""
        cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
        return encrypted.hex().upper()

    def _aes_decrypt(self, hex_text, key, iv):
        """AES-128-CBC 解密 ← hex (cMt 函数)"""
        cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
        decrypted = unpad(cipher.decrypt(bytes.fromhex(hex_text)), AES.block_size)
        return decrypted.decode('utf-8')

    def _rsa_encrypt(self, text):
        """RSA 公钥加密 → base64 (uMt 函数)"""
        der_bytes = base64.b64decode(self.RSA_PUBLIC_KEY_DER)
        public_key = RSA.import_key(der_bytes)
        cipher = PKCS1_v1_5.new(public_key)
        encrypted = cipher.encrypt(text.encode('utf-8'))
        return base64.b64encode(encrypted).decode('utf-8')

    def _rsa_decrypt(self, base64_text):
        """RSA 私钥解密 ← base64 (fMt 函数)"""
        private_key = RSA.import_key(self.RSA_PRIVATE_KEY)
        cipher = PKCS1_v1_5.new(private_key)
        decrypted = cipher.decrypt(base64.b64decode(base64_text), None)
        return decrypted.decode('utf-8') if decrypted else ""

    def _md5_upper(self, text):
        """MD5 → hex 大写 (lMt 函数)"""
        return hashlib.md5(str(text or "").encode()).hexdigest().upper()

    def _gen_signature(self, params):
        """生成签名 (eMt 函数)

        MD5("token_id=...,token=...,phone_type=...,request_key=...,app_id=...,time=...,keys=...SALT")
        """
        sign_str = (
            f"token_id={params.get('token_id', '')},"
            f"token={params.get('token', '')},"
            f"phone_type={params.get('phone_type', '')},"
            f"request_key={params.get('request_key', '')},"
            f"app_id={params.get('app_id', '')},"
            f"time={params.get('time', '')},"
            f"keys={params.get('keys', '')}"
            f"{self.SIGN_SALT}"
        )
        return self._md5_upper(sign_str)

    def _build_request_params(self, token, data):
        """构建请求参数 (hR 函数)

        1. AES 加密 data → request_key (hex)
        2. RSA 加密 {iv, key} → keys (base64)
        3. 构建参数并添加签名
        """
        timestamp = str(int(time.time()))
        request_key = self._aes_encrypt(json.dumps(data or {}), self.AES_KEY, self.AES_IV)
        keys = self._rsa_encrypt(json.dumps({"iv": self.AES_IV, "key": self.AES_KEY}))

        params = {
            "token_id": "",
            "token": str(token or ""),
            "phone_type": "1",
            "request_key": request_key,
            "app_id": "1",
            "time": timestamp,
            "keys": keys,
            "phone_model": "xiaomi-22081212c",
            "ad_version": "1",
        }
        params["signature"] = self._gen_signature(params)
        return params

    def _decrypt_response(self, resp_data):
        """解密响应 (tMt 函数)

        1. RSA 解密 keys → {key, iv}
        2. AES 解密 response_key → JSON
        """
        if not resp_data or not resp_data.get("keys") or not resp_data.get("response_key"):
            raise Exception("瓜子接口无数据")
        key_info = json.loads(self._rsa_decrypt(resp_data["keys"]))
        return json.loads(self._aes_decrypt(resp_data["response_key"], key_info["key"], key_info["iv"]))

    def _get_headers(self):
        """构建请求头 (aMt 函数)"""
        return {
            "User-Agent": "Lavf/57.83.100",
            "content-type": "application/x-www-form-urlencoded",
            "Ver": self.VER,
            "Version": self.VERSION,
            "api-ver": self.VER,
            "PackageName": self.PACKAGE_NAME,
            "code": self.CODE,
            "deviceId": self.auth.get("device_id", ""),
            "lang": "zh_cn",
            "Cache-Control": "no-cache",
            "Referer": self.site_url,
        }

    # ═══════════════════════════════════════
    #  API 请求
    # ═══════════════════════════════════════

    def _raw_api_request(self, path, data, token=""):
        """单次 API 请求 (mR 函数)"""
        params = self._build_request_params(token, data)
        url = f"{self.site_url}{path}"
        resp = self.session.post(url, data=params, headers=self._get_headers(), timeout=15)
        result = resp.json() if isinstance(resp.text, str) else resp.json()

        if "code" in result and int(result.get("code", 0)) != 200:
            raise Exception(f"瓜子接口失败 {path}: {result.get('msg', resp.status_code)}")

        f = result.get("data")
        if not f or not f.get("keys") or not f.get("response_key"):
            raise Exception(f"瓜子接口无数据: {path}")

        return self._decrypt_response(f)

    def _api_request(self, path, data):
        """主 API 请求 (GE 函数)

        1. 非认证接口先确保认证
        2. 多线路轮询，失败自动切换
        3. 全部失败后清除 token 重新认证
        """
        if not path.startswith("/App/Authentication/"):
            self._ensure_auth()

        last_error = None
        for round_num in range(3):
            start_host = self.host_index
            for i in range(len(self.WE)):
                self.host_index = (start_host + i) % len(self.WE)
                self.site_url = self.WE[self.host_index]
                try:
                    return self._raw_api_request(path, data, self.auth.get("token", ""))
                except Exception as e:
                    last_error = e

            # 所有线路失败，清除 token 重新认证
            self.auth["token"] = ""
            self.auth["token_id"] = ""
            reauthed = False
            for i in range(len(self.WE)):
                self.host_index = i
                self.site_url = self.WE[i]
                try:
                    self._ensure_auth(force_refresh=True)
                    reauthed = True
                    break
                except Exception as e:
                    last_error = e
                    self.auth["token"] = ""
                    self.auth["token_id"] = ""

            if reauthed:
                self.host_index = 0

        raise Exception(f"瓜子接口请求失败: {last_error}")

    # ═══════════════════════════════════════
    #  TVBox 接口
    # ═══════════════════════════════════════

    def homeContent(self, filter):
        """首页分类"""
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "电视剧", "type_id": "2"},
            {"type_name": "动漫", "type_id": "3"},
            {"type_name": "综艺", "type_id": "4"},
            {"type_name": "短剧", "type_id": "64"},
            {"type_name": "音乐", "type_id": "72"},
            {"type_name": "AI漫画", "type_id": "74"},
            {"type_name": "电影解说", "type_id": "73"},
            {"type_name": "体育解说", "type_id": "71"},
            {"type_name": "电竞解说", "type_id": "70"},
        ]

        filters = {
            "1": [{"key": "sub", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "动作片", "v": "5"},
                {"n": "悬疑片", "v": "29"}, {"n": "喜剧片", "v": "6"},
                {"n": "爱情片", "v": "7"}, {"n": "科幻片", "v": "8"},
                {"n": "恐怖片", "v": "9"}, {"n": "剧情片", "v": "10"},
                {"n": "战争片", "v": "11"}, {"n": "动画片", "v": "36"},
                {"n": "纪录片", "v": "20"}, {"n": "灾难片", "v": "38"},
                {"n": "犯罪片", "v": "61"}]}],
            "2": [{"key": "sub", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "国产剧", "v": "12"},
                {"n": "香港剧", "v": "13"}, {"n": "台湾剧", "v": "14"},
                {"n": "欧美剧", "v": "15"}, {"n": "日本剧", "v": "16"},
                {"n": "韩国剧", "v": "17"}, {"n": "海外剧", "v": "18"},
                {"n": "泰国剧", "v": "19"}, {"n": "新加坡剧", "v": "69"}]}],
            "3": [{"key": "sub", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "中国动漫", "v": "30"},
                {"n": "日本动漫", "v": "31"}, {"n": "欧美动漫", "v": "33"}]}],
            "4": [{"key": "sub", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "大陆综艺", "v": "22"},
                {"n": "港台综艺", "v": "23"}, {"n": "日韩综艺", "v": "24"},
                {"n": "欧美综艺", "v": "25"}]}],
        }

        # 尝试获取首页推荐
        list_data = []
        try:
            data = self._api_request("/App/IndexList/index", {
                "ns": "", "nt": int(time.time()), "pid": "1"
            })
            if data and isinstance(data.get("list"), list):
                for item in data["list"][1:] if len(data["list"]) > 1 else []:
                    if isinstance(item, dict) and isinstance(item.get("list"), list):
                        for v in item["list"]:
                            if v.get("vod_id") and v.get("vod_name"):
                                list_data.append({
                                    "vod_id": str(v["vod_id"]),
                                    "vod_name": v.get("vod_name", ""),
                                    "vod_pic": v.get("vod_pic", ""),
                                    "vod_remarks": str(v.get("vod_continu", "")) or str(v.get("vod_score", "")),
                                })
        except Exception:
            pass

        return {"class": classes, "filters": filters, "list": list_data}

    def homeVideoContent(self):
        """首页推荐视频"""
        try:
            data = self._api_request("/App/IndexList/index", {
                "ns": "", "nt": int(time.time()), "pid": "1"
            })
            videos = []
            if data and isinstance(data.get("list"), list):
                for item in data["list"][1:] if len(data["list"]) > 1 else []:
                    if isinstance(item, dict) and isinstance(item.get("list"), list):
                        for v in item["list"]:
                            if v.get("vod_id") and v.get("vod_name"):
                                videos.append({
                                    "vod_id": str(v["vod_id"]),
                                    "vod_name": v.get("vod_name", ""),
                                    "vod_pic": v.get("vod_pic", ""),
                                    "vod_remarks": str(v.get("vod_continu", "")) or str(v.get("vod_score", "")),
                                })
            return {"list": videos}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        """分类列表"""
        page = int(pg) if pg else 1
        extend = extend or {}
        try:
            sub = extend.get("sub", extend.get("class", self._get_default_sub(tid)))
            data = self._api_request("/App/IndexList/indexList", {
                "area": extend.get("area", "0") or "0",
                "sub": str(sub or ""),
                "year": extend.get("year", "0") or "0",
                "pageSize": str(self.PAGE_SIZE),
                "sort": extend.get("sort", "d_id") or "d_id",
                "page": str(page),
                "tid": str(tid),
            })

            videos = []
            if data and isinstance(data.get("list"), list):
                for item in data["list"]:
                    if item.get("vod_id") and item.get("vod_name"):
                        videos.append({
                            "vod_id": str(item["vod_id"]),
                            "vod_name": item.get("vod_name", ""),
                            "vod_pic": item.get("vod_pic", ""),
                            "vod_remarks": str(item.get("vod_continu", "")) or str(item.get("vod_score", "")),
                        })

            pagecount = page + 1 if len(videos) >= self.PAGE_SIZE else page
            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": self.PAGE_SIZE,
                "total": 999999,
            }
        except Exception as e:
            return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

    def _get_default_sub(self, tid):
        """获取默认子分类 (sMt 函数)"""
        mapping = {"1": "5", "2": "12", "3": "30", "4": "22"}
        return mapping.get(str(tid), "")

    def detailContent(self, ids):
        """视频详情"""
        try:
            vod_id = str(ids[0]).split("|")[0].split("/")[0]

            # 获取详情
            detail_data = self._api_request("/App/IndexPlay/playInfo", {
                "token_id": self.auth.get("token_id", ""),
                "vod_id": vod_id,
                "mobile_time": int(time.time()),
                "token": self.auth.get("token", ""),
            })

            vod_info = detail_data.get("vodInfo", {}) if detail_data else {}
            if not vod_info.get("vod_name"):
                return {"list": []}

            # 获取播放列表
            vurl_data = self._api_request("/App/Resource/Vurl/show", {
                "vurl_cloud_id": "2",
                "vod_d_id": vod_id,
            })

            # 构建播放源
            play_from = []
            play_url = []
            if vurl_data and isinstance(vurl_data.get("list"), list):
                source_map = {}
                for idx, item in enumerate(vurl_data["list"]):
                    play = item.get("play", {})
                    title = str(item.get("title", "")) or f"第{idx+1}集"
                    for res_key, res_val in play.items():
                        if not res_val or str(res_val.get("show_type", "")) == "2":
                            continue
                        param = str(res_val.get("param", ""))
                        if param:
                            if res_key not in source_map:
                                source_map[res_key] = []
                            source_map[res_key].append(f"{title}${param}")

                for source_name, episodes in source_map.items():
                    play_from.append(f"瓜子-{source_name}")
                    play_url.append("#".join(episodes))

            vod = {
                "vod_id": vod_id,
                "vod_name": vod_info.get("vod_name", ""),
                "vod_pic": vod_info.get("vod_pic", ""),
                "vod_year": vod_info.get("vod_year", ""),
                "vod_area": vod_info.get("vod_area", ""),
                "vod_actor": vod_info.get("vod_actor", ""),
                "vod_director": vod_info.get("vod_director", ""),
                "vod_content": vod_info.get("vod_use_content", "").strip(),
                "vod_play_from": "$$$".join(play_from) if play_from else "瓜子",
                "vod_play_url": "$$$".join(play_url) if play_url else "",
            }
            return {"list": [vod]}
        except Exception as e:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        """搜索"""
        page = int(pg) if pg else 1
        try:
            data = self._api_request("/App/Index/findMoreVod", {
                "keywords": str(key).strip(),
                "ns": "",
                "nt": int(time.time()),
                "order_val": "1",
            })

            videos = []
            if data and isinstance(data.get("list"), list):
                for item in data["list"]:
                    if item.get("vod_id") and item.get("vod_name"):
                        videos.append({
                            "vod_id": str(item["vod_id"]),
                            "vod_name": item.get("vod_name", ""),
                            "vod_pic": item.get("vod_pic", ""),
                            "vod_remarks": str(item.get("vod_continu", "")) or str(item.get("vod_score", "")),
                        })
            return {"list": videos, "page": page, "pagecount": 1, "limit": 30, "total": len(videos)}
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 30, "total": 0}

    def playerContent(self, flag, id, vipFlags):
        """播放解析

        关键: 强制刷新 token 确保获取真实视频地址 (非推广44秒)
        """
        try:
            # 强制刷新 token — 这是解决44秒推广的关键!
            self._ensure_auth(force_refresh=True)

            # 解析播放参数
            param_str = str(id).split("||")[0]
            params = {}
            for pair in param_str.split("&"):
                idx = pair.find("=")
                if idx > 0:
                    params[pair[:idx]] = pair[idx + 1:]

            if not params:
                return {"parse": 0, "playUrl": "", "url": ""}

            # 请求播放地址
            data = self._api_request("/App/Resource/VurlDetail/showOne", params)
            url = str(data.get("url", "")).strip() if data else ""

            if not url:
                return {"parse": 0, "playUrl": "", "url": ""}

            # 检测推广视频
            if "wanglaoshi" in url.lower():
                # 推广视频 — 重新认证后重试一次
                self.auth["token"] = ""
                self.auth["token_id"] = ""
                self._ensure_auth(force_refresh=True)
                data = self._api_request("/App/Resource/VurlDetail/showOne", params)
                url = str(data.get("url", "")).strip() if data else ""
                if not url or "wanglaoshi" in url.lower():
                    return {"parse": 0, "playUrl": "", "url": ""}

            header = {
                "User-Agent": "Lavf/57.83.100",
                "Referer": "http://WJiZxLXA2.com/",
            }

            result = {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": json.dumps(header),
            }

            # 设置格式
            if ".m3u8" in url.lower():
                result["format"] = "application/vnd.apple.mpegurl"

            return result
        except Exception as e:
            return {"parse": 0, "playUrl": "", "url": ""}
