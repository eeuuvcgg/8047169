# -*- coding: utf-8 -*-
"""
配置中心 — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
功能: 聚合网盘二维码扫码配置入口
支持网盘: 夸克、UC、百度、阿里、115、天翼、移动
版本: 4.0.0

方案 (v4.0):
  - 列表页: 网盘图标列表
  - 详情页: 二维码 + 提示文字 (双保险)
    * 保险A: vod_pic = 二维码图片 (壳子详情页顶部大图)
    * 保险B: vod_content = 含<img>标签的HTML (壳子简介区域渲染)
  - 播放线路: 虚拟线路 → playerContent 返回二维码页面URL
    (兼容不支持 vod_tag 的壳子版本)
  - localProxy: 提供 /qr.html 本地二维码页面
"""

import sys
import json
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

PAN_CONFIG = {
    "1": {"name": "夸克网盘", "icon": "https://image.quark.cn/images/logo/new_icon_48.png", "login_url": "https://pan.quark.cn/", "desc": "夸克App扫码登录", "bind_tip": "打开夸克App → 扫一扫 → 确认登录"},
    "2": {"name": "UC网盘", "icon": "https://img.uc123.com/newweb/img/favicon.ico", "login_url": "https://drive.uc.cn/", "desc": "UC浏览器扫码登录", "bind_tip": "打开UC浏览器 → 扫一扫 → 确认登录"},
    "3": {"name": "百度网盘", "icon": "https://ndstatic.bdstatic.com/static/ndstatic/img/favicon_1a2eb4c.png", "login_url": "https://pan.baidu.com/", "desc": "百度网盘App扫码", "bind_tip": "打开百度网盘App → 扫一扫 → 确认登录"},
    "4": {"name": "阿里云盘", "icon": "https://img.alicdn.com/imgextra/i3/O1CN01ebK5mP1Z6mQJr0J5j_!!6000000003248-2-tps-64-64.png", "login_url": "https://www.alipan.com/", "desc": "阿里云盘App扫码", "bind_tip": "打开阿里云盘App → 我的 → 扫一扫"},
    "5": {"name": "115网盘", "icon": "https://115.com/favicon.ico", "login_url": "https://115.com/", "desc": "115App扫码登录", "bind_tip": "打开115App → 扫一扫 → 确认登录"},
    "6": {"name": "天翼云盘", "icon": "https://cloud.189.cn/favicon.ico", "login_url": "https://cloud.189.cn/", "desc": "天翼云盘App扫码", "bind_tip": "打开天翼云盘App → 扫一扫 → 确认登录"},
    "7": {"name": "移动云盘", "icon": "https://yun.139.com/favicon.ico", "login_url": "https://yun.139.com/", "desc": "移动云盘App扫码", "bind_tip": "打开移动云盘App或微信 → 扫一扫"},
}

CLASSES = [{"type_id": k, "type_name": v["name"]} for k, v in PAN_CONFIG.items()]
FILTERS = {k: {} for k in PAN_CONFIG}


def _qr_url(text, size=200):
    """生成二维码图片 HTTP URL (200x200, margin=4)"""
    encoded = urllib.parse.quote(text, safe='')
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}&margin=4&bgcolor=ffffff&color=000000"


def _qr_html(pan_name, login_url, bind_tip, desc):
    """生成二维码HTML页面内容"""
    qr = _qr_url(login_url, 200)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>{pan_name} 扫码配置</title>
<style>
body{{margin:0;padding:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f5f5;text-align:center;}}
.card{{background:#fff;border-radius:16px;padding:24px;max-width:360px;margin:0 auto;box-shadow:0 4px 20px rgba(0,0,0,0.08);}}
h2{{margin:0 0 16px;color:#333;font-size:20px;}}
.qr-wrap{{background:#fff;padding:16px;border-radius:12px;display:inline-block;margin-bottom:16px;}}
.qr-wrap img{{width:200px;height:200px;display:block;}}
.tip{{color:#666;font-size:15px;line-height:1.6;margin-bottom:12px;}}
.url{{color:#999;font-size:13px;word-break:break-all;background:#f9f9f9;padding:10px;border-radius:8px;}}
.badge{{display:inline-block;background:#07c160;color:#fff;padding:4px 12px;border-radius:20px;font-size:13px;margin-bottom:12px;}}
</style>
</head>
<body>
<div class="card">
<div class="badge">扫码绑定</div>
<h2>{pan_name}</h2>
<div class="qr-wrap">
<img src="{qr}" alt="二维码">
</div>
<div class="tip"><b>步骤:</b> {bind_tip}</div>
<div class="tip">用手机扫描上方二维码即可完成登录绑定</div>
<div class="url">{login_url}</div>
</div>
</body>
</html>"""


# ==================== 爬虫主体 ====================

class Spider(Spider):
    """配置中心爬虫 — 网盘二维码聚合入口"""

    def getName(self):
        return "配置中心"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ========== 核心接口 ==========

    def homeContent(self, filter):
        """首页 — 网盘图标列表"""
        result = {}
        result['class'] = CLASSES
        if filter:
            result['filters'] = FILTERS

        videos = []
        for key, cfg in PAN_CONFIG.items():
            videos.append({
                'vod_id': key,
                'vod_name': cfg["name"],
                'vod_pic': cfg["icon"],
                'vod_remarks': '点击进入扫码',
                'vod_tag': 'fork',
                'type_name': cfg["name"],
            })

        result['list'] = videos
        return result

    def homeVideoContent(self):
        return self.homeContent(True)

    def categoryContent(self, tid, pg, filter, extend):
        """分类 — 同首页"""
        result = {}
        cfg = PAN_CONFIG.get(tid)
        if not cfg:
            return self.homeContent(True)

        item = {
            'vod_id': tid,
            'vod_name': cfg["name"],
            'vod_pic': cfg["icon"],
            'vod_remarks': '点击进入扫码',
            'vod_tag': 'fork',
            'type_name': cfg["name"],
        }

        result['list'] = [item]
        result['page'] = 1
        result['pagecount'] = 1
        result['limit'] = 1
        result['total'] = 1
        return result

    def detailContent(self, array):
        """详情页 — 二维码 + 提示文字 + 虚拟播放线路(双保险)"""

        vod_id = str(array[0]) if array else ''
        if not vod_id:
            return {'list': []}

        cfg = PAN_CONFIG.get(vod_id, {})
        if not cfg:
            result = {
                'vod_id': vod_id,
                'vod_name': '配置中心',
                'vod_pic': '',
                'vod_content': '请选择具体的网盘进行扫码配置',
                'vod_play_from': '',
                'vod_play_url': '',
            }
            return {'list': [result]}

        pan_name = cfg.get('name', '')
        login_url = cfg.get('login_url', '')
        desc = cfg.get('desc', '')
        bind_tip = cfg.get('bind_tip', '')

        # 保险A: 二维码图片 URL (详情页顶部大图)
        qr_img = _qr_url(login_url, 200)

        # 保险B: HTML 简介 (部分壳子支持渲染HTML)
        html_content = (
            f"【{pan_name} 扫码绑定】\\n\\n"
            f"<img src='{qr_img}' width='200' style='display:block;margin:10px auto;'>\\n\\n"
            f"步骤: {bind_tip}\\n"
            f"用手机扫描上方二维码完成登录绑定\\n\\n"
            f"网盘地址: {login_url}"
        )

        # 保险C: 虚拟播放线路
        # 万一壳子不支持 vod_tag='fork'，用户可通过播放线路查看二维码
        play_from = '扫码配置'
        play_url = f'查看二维码${_qr_url(login_url, 200)}'

        result = {
            'vod_id': vod_id,
            'vod_name': f'{pan_name} 扫码配置',
            'vod_pic': qr_img,
            'vod_area': '',
            'vod_year': '',
            'vod_director': '',
            'vod_actor': '',
            'vod_content': html_content,
            'vod_remarks': desc,
            'vod_play_from': play_from,
            'vod_play_url': play_url,
        }
        return {'list': [result]}

    def playerContent(self, flag, id, vipFlags):
        """播放器 — 返回二维码图片URL(parse=1让壳子用WebView打开)"""
        # id 可能是二维码URL
        if id and ('qrserver' in id or 'create-qr-code' in id):
            return {
                'parse': 1,
                'playUrl': '',
                'url': id,
                'header': {'User-Agent': 'Mozilla/5.0'}
            }
        return {'parse': 0, 'playUrl': '', 'url': '', 'header': ''}

    def searchContent(self, key, quick):
        """搜索 — 按网盘名搜索"""
        result = {}
        if not key:
            return {'list': []}

        videos = []
        key_lower = key.lower()
        for pan_key, cfg in PAN_CONFIG.items():
            if key_lower in cfg['name'].lower() or key_lower in pan_key.lower():
                videos.append({
                    'vod_id': pan_key,
                    'vod_name': cfg["name"],
                    'vod_pic': cfg["icon"],
                    'vod_remarks': '点击进入扫码',
                    'vod_tag': 'fork',
                    'type_name': cfg['name'],
                })

        result['list'] = videos
        return result

    def localProxy(self, param):
        """本地代理 — 提供二维码HTML页面"""
        try:
            qs = urllib.parse.parse_qs(param)
            ptype = qs.get('ptype', [''])[0]

            if ptype == 'qr':
                pan_type = qs.get('type', [''])[0]
                cfg = PAN_CONFIG.get(pan_type, {})
                if cfg:
                    html = _qr_html(
                        cfg.get('name', ''),
                        cfg.get('login_url', ''),
                        cfg.get('bind_tip', ''),
                        cfg.get('desc', '')
                    )
                    return [200, "text/html", html, ""]
        except Exception:
            pass

        return [200, "video/MP2T", "", ""]


# ==================== 入口兼容 ====================
if __name__ == '__main__':
    spider = Spider()
    spider.init()
    print(f"Spider名称: {spider.getName()}")
    print(f"支持网盘数: {len(PAN_CONFIG)}")

    # 测试详情
    detail = spider.detailContent(['1'])
    d = detail['list'][0]
    print(f"\n详情名称: {d['vod_name']}")
    print(f"vod_pic: {d['vod_pic']}")
    print(f"vod_play_from: '{d['vod_play_from']}'")
    print(f"vod_play_url: '{d['vod_play_url']}'")
    print(f"\n简介内容:\n{d['vod_content']}")
