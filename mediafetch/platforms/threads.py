"""Threads (threads.com / threads.net) 抓取器。

匿名访问时 Threads 返回 JS 登录墙，HTML 里没有媒体地址；换成爬虫 UA 后
Meta 会把整篇帖子服务端渲染进 <script type="application/json" data-sjs>，
媒体 URL 全在里面。inline 贴图（GIF）不在媒体字段里，而在
text_post_app_info.text_fragments[].inline_sticker_fragment，下载走 giphy。
"""
import re

from ..core import biggest_image, fetch, unique_posts

POST_RE = re.compile(r'/post/([\w-]+)')
SHORT_RE = re.compile(r'/t/([\w-]+)')
SHARE_RE = re.compile(r'/share/([\w-]+)')
HANDLE_RE = re.compile(r'@([\w.]+)')

GIPHY = 'https://i.giphy.com/{}.gif'
# giphy 原图比 i.giphy.com 的默认 480 宽清晰得多，按优先级尝试
GIPHY_SOURCES = (
    'https://media.giphy.com/media/{}/source.gif',
    'https://i.giphy.com/{}.gif',
)


def media_of(post):
    """帖子自身的媒体列表（carousel 展开成多项）。"""
    out = []
    for node in (post.get('carousel_media') or [post]):
        videos = node.get('video_versions') or []
        if videos:
            out.append({
                'type': 'video',
                'url': videos[0]['url'],
                'width': node.get('original_width'),
                'height': node.get('original_height'),
            })
            continue
        url = biggest_image(node)
        if url:
            out.append({
                'type': 'image',
                'url': url,
                'width': node.get('original_width'),
                'height': node.get('original_height'),
            })
    return out


def stickers_of(post):
    """帖子正文里插入的贴图（GIF）。"""
    info = post.get('text_post_app_info') or {}
    frags = (info.get('text_fragments') or {}).get('fragments') or []
    seen, out = set(), []
    for frag in frags:
        sticker = frag.get('inline_sticker_fragment') or {}
        sid = sticker.get('sticker_id')
        if sid and sid not in seen:
            seen.add(sid)
            out.append({'id': sid,
                        'url': sticker.get('sticker_url') or GIPHY.format(sid),
                        'sources': [u.format(sid) for u in GIPHY_SOURCES]})
    return out


def caption_of(post):
    return ((post.get('caption') or {}).get('text') or '').replace('\n', ' ').strip()


def _record(post, url):
    info = post.get('text_post_app_info') or {}
    return {
        'platform': 'threads',
        'code': post.get('code'),
        'url': url,
        'media_type': post.get('media_type'),
        'caption': caption_of(post),
        'is_reply': bool(info.get('is_reply')),
        'media': media_of(post),
        'stickers': stickers_of(post),
    }


def post(url):
    """解析单帖。支持 /@user/post/CODE、/t/CODE、/share/XXXX/。"""
    final, html = fetch(url)
    m = POST_RE.search(final) or POST_RE.search(url)
    if not m:
        raise SystemExit(f'不是帖子链接：{url}')
    code = m.group(1)
    nodes = unique_posts(html)
    hits = [p for p in nodes if p.get('code') == code]
    if not hits:
        raise SystemExit(f'帖子 {code} 不在页面载荷里')
    root = _record(hits[0], final)
    root['replies'] = _replies(nodes, code)
    root['reply_count_claimed'] = _claimed_replies(html)
    return root


def _replies(nodes, root_code):
    """页面首屏里能看到的回复（Threads 只给一小段，非全量）。"""
    out = []
    for p in nodes:
        if p.get('code') == root_code:
            continue
        info = p.get('text_post_app_info') or {}
        if not info.get('is_reply'):
            continue
        rec = _record(p, f'https://www.threads.com/t/{p.get("code")}')
        out.append(rec)
    return out


def _claimed_replies(html):
    m = re.search(r'"direct_reply_count":(\d+)', html)
    return int(m.group(1)) if m else None


def profile(handle, limit=50):
    """账号时间线里带媒体的帖子（只到首屏，Threads 无公开翻页接口）。"""
    handle = handle.lstrip('@')
    final, html = fetch(f'https://www.threads.com/@{handle}')
    out = []
    for p in unique_posts(html):
        rec = _record(p, f'https://www.threads.com/@{handle}/post/{p.get("code")}')
        if rec['media'] or rec['stickers']:
            out.append(rec)
        if len(out) >= limit:
            break
    return out
