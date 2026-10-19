"""平台无关的抓取骨架：HTTP、页面 JSON 抽取、媒体去重与下载。"""
import json
import os
import re
import urllib.request

CRAWLER_UA = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
BROWSER_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

# 头像 / 站点资源 / 明显缩略图，不该当正文媒体
JUNK_URL = re.compile(r'/rsrc\.php/|profile_pic|s150x150')

_SJS = re.compile(r'<script[^>]*type="application/json"[^>]*data-sjs>(.*?)</script>', re.S)


def fetch(url, ua=CRAWLER_UA, timeout=60):
    """返回 (最终 URL, 页面文本)。跟随重定向。"""
    req = urllib.request.Request(
        url, headers={'User-Agent': ua, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read().decode('utf-8', 'replace')


def sjs_objects(html):
    """页面内嵌的服务端渲染 JSON（Meta 系站点用 data-sjs 标记）。"""
    for blob in _SJS.findall(html):
        try:
            yield json.loads(blob)
        except ValueError:
            continue


def walk_media_nodes(obj, out):
    """递归收集带 code + 媒体字段的节点。"""
    if isinstance(obj, dict):
        if obj.get('code') and ({'image_versions2', 'video_versions', 'carousel_media'} & obj.keys()):
            out.append(obj)
        for v in obj.values():
            walk_media_nodes(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_media_nodes(v, out)


def unique_posts(html):
    """页面里所有帖子节点，按 code 去重保序。"""
    raw = []
    for j in sjs_objects(html):
        walk_media_nodes(j, raw)
    seen, out = set(), []
    for p in raw:
        c = p.get('code')
        if c and c not in seen:
            seen.add(c)
            out.append(p)
    return out


def biggest_image(node):
    """取分辨率最大的非缩略图候选。"""
    cands = (node.get('image_versions2') or {}).get('candidates') or []
    cands = [c for c in cands if c.get('url') and not JUNK_URL.search(c['url'])]
    return max(cands, key=lambda c: c.get('width', 0))['url'] if cands else None


def guess_ext(url):
    if '/o1/v/' in url or url.endswith('.mp4'):
        return 'mp4'
    if 'giphy' in url or url.endswith('.gif'):
        return 'gif'
    if url.endswith('.webp'):
        return 'webp'
    return 'jpg'


def fetch_first(urls, ua=BROWSER_UA, timeout=180):
    """按顺序尝试多个候选地址，返回第一个成功的 (url, bytes)。"""
    last = None
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={'User-Agent': ua})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return u, r.read()
        except Exception as e:
            last = e
    raise last


def merge_av(video, audio, outdir, prefix, timeout=300):
    """把 DASH 分轨的音视频合流成一个 mp4。缺 ffmpeg 就返回 None。"""
    import shutil
    import subprocess
    import tempfile
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return None
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f'{prefix}.mp4')
    with tempfile.TemporaryDirectory() as tmp:
        vpath = os.path.join(tmp, 'v.mp4')
        apath = os.path.join(tmp, 'a.m4a')
        for url, dest in ((video, vpath), (audio, apath)):
            req = urllib.request.Request(url, headers={'User-Agent': BROWSER_UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                with open(dest, 'wb') as f:
                    f.write(r.read())
        proc = subprocess.run(
            [ffmpeg, '-y', '-loglevel', 'error', '-i', vpath, '-i', apath,
             '-c', 'copy', '-movflags', '+faststart', path],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:300])
    return path, os.path.getsize(path)


def download(url, outdir, prefix, ua=BROWSER_UA, timeout=180):
    """url 可以是字符串，也可以是候选地址列表（按优先级尝试）。"""
    if isinstance(url, (list, tuple)):
        _, data = fetch_first(url, ua, timeout)
        primary = url[0]
    else:
        primary = url
        req = urllib.request.Request(url, headers={'User-Agent': ua})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f'{prefix}.{guess_ext(primary)}')
    with open(path, 'wb') as f:
        f.write(data)
    return path, len(data)
