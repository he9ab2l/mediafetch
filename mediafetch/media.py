"""媒体处理：URL 分类、扩展名推断、DASH 合流。不碰网络，不碰存档。"""
import os
import re
import shutil
import subprocess
import tempfile

from .net import BROWSER_UA, get_bytes

# 头像 / 站点资源 / 明显缩略图，不该当正文媒体
JUNK_URL = re.compile(r'/rsrc\.php/|profile_pic|s150x150')


def is_junk(url):
    return bool(JUNK_URL.search(url or ''))


def biggest_image(node):
    """取 image_versions2 里分辨率最大的非缩略图候选。"""
    cands = (node.get('image_versions2') or {}).get('candidates') or []
    cands = [c for c in cands if c.get('url') and not is_junk(c['url'])]
    return max(cands, key=lambda c: c.get('width', 0))['url'] if cands else None


def guess_ext(url):
    if '/o1/v/' in url or url.endswith('.mp4'):
        return 'mp4'
    if 'giphy' in url or url.endswith('.gif'):
        return 'gif'
    if url.endswith('.webp'):
        return 'webp'
    return 'jpg'


def merge_av(video, audio, timeout=300):
    """把 DASH 分轨音视频合流成一个 mp4，返回字节；缺 ffmpeg 返回 None。"""
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        vpath = os.path.join(tmp, 'v.mp4')
        apath = os.path.join(tmp, 'a.m4a')
        out = os.path.join(tmp, 'out.mp4')
        with open(vpath, 'wb') as f:
            f.write(get_bytes(video, BROWSER_UA, timeout))
        with open(apath, 'wb') as f:
            f.write(get_bytes(audio, BROWSER_UA, timeout))
        proc = subprocess.run(
            [ffmpeg, '-y', '-loglevel', 'error', '-i', vpath, '-i', apath,
             '-c', 'copy', '-movflags', '+faststart', out],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[:300])
        with open(out, 'rb') as f:
            return f.read()
