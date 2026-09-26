# -*- coding: utf-8 -*-
"""
配置中心 — 兼容 FongMi/TV (T3) 与 OK影视/PyramidStore (T4) 双壳子
功能: 聚合网盘二维码扫码配置入口
支持网盘: 夸克、UC、百度、阿里、115、天翼、移动
版本: 2.5.0

方案:
  - 列表页: 网盘图标 + vod_tag='fork' 走详情页
  - 详情页: 显示说明 + 一个"查看二维码"播放线路
  - 点击线路 → playerContent 返回本地代理URL → 壳子webview打开
  - localProxy 返回完整HTML页面(含网盘图标/名称/二维码/扫码提示)
"""

import sys
import json
import re
import urllib.parse
import base64

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


def _qr_url(text, size=400):
    """生成二维码图片HTTP URL"""
    encoded = urllib.parse.quote(text, safe='')
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}&margin=2&bgcolor=ffffff&color=000000"


def _build_qr_html(pan_id):
    """生成包含二维码的完整HTML页面字符串"""
    cfg = PAN_CONFIG.get(pan_id, {})
    if not cfg:
        return ''

    pan_name = cfg.get('name', '')
    login_url = cfg.get('login_url', '')
    bind_tip = cfg.get('bind_tip', '')
    qr_pic = _qr_url(login_url, 500)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{pan_name} 扫码配置</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
    background:#0f0f1a;
    color:#fff;
    font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    min-height:100vh;
    padding:24px 16px;
}}
.card{{
    background:#1a1a2e;
    border-radius:20px;
    padding:28px 24px;
    max-width:380px;
    width:100%;
    text-align:center;
    box-shadow:0 8px 32px rgba(0,0,0,0.4);
}}
.icon{{
    width:48px;
    height:48px;
    margin:0 auto 12px;
    border-radius:12px;
}}
.title{{
    font-size:20px;
    font-weight:bold;
    margin-bottom:8px;
    color:#fff;
}}
.subtitle{{
    font-size:13px;
    color:#888;
    margin-bottom:20px;
    line-height:1.5;
}}
.qr-wrap{{
    background:#fff;
    border-radius:16px;
    padding:16px;
    margin-bottom:16px;
    display:inline-block;
}}
.qr-wrap img{{
    width:260px;
    height:260px;
    display:block;
}}
.tip-box{{
    background:rgba(76,175,80,0.12);
    border:1px solid rgba(76,175,80,0.25);
    border-radius:12px;
    padding:14px;
    margin-bottom:12px;
}}
.tip-box .tip-title{{
    font-size:15px;
    font-weight:bold;
    color:#4caf50;
    margin-bottom:6px;
}}
.tip-box .tip-text{{
    font-size:13px;
    color:#a5d6a7;
    line-height:1.6;
}}
.url-box{{
    font-size:11px;
    color:#555;
    word-break:break-all;
    padding-top:8px;
    border-top:1px solid #2a2a3e;
}}
</style>
</head>
<body>
<div class="card">
    <img class="icon" src="{cfg.get('icon','')}" alt="">
    <div class="title">{pan_name}</div>
    <div class="subtitle">{bind_tip}</div>
    <div class="qr-wrap">
        <img src="{qr_pic}" alt="二维码">
    </div>
    <div class="tip-box">
        <div class="tip-title">请用手机App扫码</div>
        <div class="tip-text">打开对应网盘App → 点击「扫一扫」<br>扫描上方二维码即可登录绑定</div>
    </div>
    <div class="url-box">{login_url}</div>
</div>
</body>
</html>'''
    return html


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
                'vod_remarks': '点击查看二维码',
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
            'vod_remarks': '点击查看二维码',
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
        """详情页 — 说明 + 一个"查看二维码"播放线路

        用户点击线路按钮 → 触发 playerContent → 返回HTML页面
        """
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

        content_lines = [
            f"【{pan_name} 扫码配置】",
            "",
            bind_tip,
            "",
            "点击下方「查看二维码」按钮",
            "用手机App扫描二维码即可绑定",
            "",
            f"网盘地址: {login_url}",
        ]

        # 设一个播放线路, 用户点击后 playerContent 返回HTML页面
        result = {
            'vod_id': vod_id,
            'vod_name': f'{pan_name} 扫码配置',
            'vod_pic': cfg["icon"],
            'vod_area': '',
            'vod_year': '',
            'vod_director': '',
            'vod_actor': '',
            'vod_content': '\n'.join(content_lines),
            'vod_remarks': desc,
            # 播放线路: 名字$$$选集URL
            # vod_id 作为选集ID, playerContent 用它生成HTML
            'vod_play_from': '查看二维码',
            'vod_play_url': f'点击查看二维码${vod_id}',
        }
        return {'list': [result]}

    def playerContent(self, flag, id, vipFlags):
        """播放器 — 返回本地代理URL, 壳子通过localProxy获取带提示的HTML页面"""
        pan_id = str(id)
        if '$' in pan_id:
            pan_id = pan_id.split('$')[-1]

        cfg = PAN_CONFIG.get(pan_id, {})
        if cfg:
            # 走本地代理，由 localProxy 返回完整的 HTML 提示页面
            proxy_url = f"http://127.0.0.1:9978/proxy?do=baseset&qr=1&id={pan_id}"
            return {
                'parse': 1,
                'playUrl': '',
                'url': proxy_url,
                'header': '',
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
                    'vod_remarks': '点击查看二维码',
                    'vod_tag': 'fork',
                    'type_name': cfg['name'],
                })

        result['list'] = videos
        return result

    def localProxy(self, param):
        """本地代理 — 壳子通过 /proxy?do=baseset&qr=1&id=x 获取二维码HTML页面"""
        try:
            pan_id = ''
            qr = ''

            if isinstance(param, dict):
                pan_id = str(param.get('id', ''))
                qr = str(param.get('qr', ''))
            elif isinstance(param, str):
                parsed = urllib.parse.urlparse(param)
                qs = urllib.parse.parse_qs(parsed.query)
                pan_id = qs.get('id', [''])[0]
                qr = qs.get('qr', [''])[0]

            if qr == '1' and pan_id in PAN_CONFIG:
                html = _build_qr_html(pan_id)
                return [200, "text/html; charset=utf-8", html, ""]
        except Exception:
            pass

        return [200, "video/MP2T", "", ""]


# ==================== 入口兼容 ====================
if __name__ == '__main__':
    spider = Spider()
    spider.init()
    print(f"Spider名称: {spider.getName()}")
    print(f"支持网盘数: {len(PAN_CONFIG)}")

    # 测试HTML生成
    html = _build_qr_html('1')
    print(f"\n夸克HTML长度: {len(html)}")
    print(f"前100字符: {html[:100]}...")

    # 测试详情
    detail = spider.detailContent(['1'])
    d = detail['list'][0]
    print(f"\n详情播放源: {d['vod_play_from']}")
    print(f"详情播放URL: {d['vod_play_url']}")

    # 测试playerContent
    pc = spider.playerContent('查看二维码', '1', [])
    print(f"\nplayerContent parse: {pc['parse']}")
    print(f"playerContent url: {pc['url']}")

    # 测试localProxy (字典参数)
    lp = spider.localProxy({'qr': '1', 'id': '1'})
    print(f"\nlocalProxy status: {lp[0]}")
    print(f"localProxy type: {lp[1]}")
    print(f"localProxy html长度: {len(lp[2])}")
