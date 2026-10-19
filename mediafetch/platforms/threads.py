"""Threads (threads.com / threads.net) 抓取器。

匿名访问时 Threads 返回 JS 登录墙，HTML 里没有媒体地址；换成爬虫 UA 后
Meta 会把整篇帖子服务端渲染进 <script type="application/json" data-sjs>，
媒体 URL 全在里面。

三类媒体来源：
1. 帖子自身 image_versions2 / video_versions / carousel_media
2. inline 贴图 text_post_app_info.text_fragments[].inline_sticker_fragment（giphy）
3. 引用/转发 text_post_app_info.share_info.quoted_post / reposted_post

回复翻页走 GraphQL：cursor 必须取
data.media.text_post_app_info.direct_replies.page_info.end_cursor，
sortOrder 用 RECENT（TOP 走不下去）。翻页返回的 node 媒体字段是空的，
要逐条打开 /t/{code} 才能取到媒体。
"""
import json
import re
import urllib.parse
import urllib.request

from ..core import biggest_image, fetch, unique_posts

POST_RE = re.compile(r'/post/([\w-]+)')
SHARE_RE = re.compile(r'/share/([\w-]+)')
HANDLE_RE = re.compile(r'@([\w.]+)')

GIPHY = 'https://i.giphy.com/{}.gif'
# giphy 原图比 i.giphy.com 的默认 480 宽清晰得多，按优先级尝试
GIPHY_SOURCES = (
    'https://media.giphy.com/media/{}/source.gif',
    'https://i.giphy.com/{}.gif',
)

GRAPHQL_URL = 'https://www.threads.com/api/graphql'
DOWNWARD_QUERY = 'BarcelonaPostPageDownwardQuery'
SHARE_INFO_KEYS = ('quoted_post', 'reposted_post')


# ---------- 单帖解析 ----------

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


def quoted_of(post):
    """引用/转发里嵌的那条帖子（自带完整媒体字段）。"""
    info = post.get('text_post_app_info') or {}
    share = info.get('share_info') or {}
    out = []
    for key in SHARE_INFO_KEYS:
        q = share.get(key)
        if not q or not q.get('code'):
            continue
        out.append({
            'kind': key,
            'code': q.get('code'),
            'media_type': q.get('media_type'),
            'caption': caption_of(q),
            'media': media_of(q),
            'stickers': stickers_of(q),
        })
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
        'quoted': quoted_of(post),
    }


def _has_media(rec):
    return bool(rec['media'] or rec['stickers'] or rec['quoted'])


# ---------- GraphQL 回复翻页 ----------

def _graphql_context(html):
    """从页面里取 lsd token、downward queryID、variables、postID。"""
    m = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', html)
    if not m:
        return None
    lsd = m.group(1)
    qid = None
    variables = None
    for m in re.finditer(
            r'"preloaderID":"adp_' + DOWNWARD_QUERY + r'RelayPreloader_\w+",'
            r'"queryID":"(\d+)","variables":(\{.*?\}),"', html):
        qid, variables = m.group(1), json.loads(m.group(2))
        break
    if not qid or not variables:
        return None
    # 页面里散落的 relay provider 开关要补齐，否则服务端可能拒绝
    for k, v in re.findall(r'"(__relay_internal__pv__\w+)":(\w+)', html)[:80]:
        variables.setdefault(k, v == 'true')
    return {'lsd': lsd, 'query_id': qid, 'variables': variables}


def _graphql(ctx, variables, referer):
    body = urllib.parse.urlencode({
        'lsd': ctx['lsd'],
        'doc_id': ctx['query_id'],
        'variables': json.dumps(variables),
        'server_timestamps': 'true',
    }).encode()
    req = urllib.request.Request(GRAPHQL_URL, data=body, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-FB-LSD': ctx['lsd'],
        'X-ASBD-ID': '129477',
        'Origin': 'https://www.threads.com',
        'Referer': referer,
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _next_cursor(payload):
    """只认 direct_replies 那一层的 cursor，其它层是 null。"""
    try:
        node = payload['data']['media']['text_post_app_info']['direct_replies']
        return (node.get('page_info') or {}).get('end_cursor')
    except (KeyError, TypeError):
        return None


def reply_codes(html, referer, max_pages=10):
    """翻页收集回复短码（不含主帖）。"""
    ctx = _graphql_context(html)
    if not ctx:
        return []
    variables = dict(ctx['variables'])
    variables['sortOrder'] = 'RECENT'  # TOP 的 cursor 走不下去
    codes, seen = [], set()
    cursor = None
    for _ in range(max_pages):
        v = dict(variables)
        if cursor:
            v['after'] = cursor
        try:
            payload = _graphql(ctx, v, referer)
        except Exception:
            break
        for c in re.findall(r'"code": "([\w-]{9,13})"', json.dumps(payload)):
            if c not in seen:
                seen.add(c)
                codes.append(c)
        nxt = _next_cursor(payload)
        if not nxt or nxt == cursor:
            break
        cursor = nxt
    return codes


# ---------- 对外接口 ----------

def post(url, reply_media=False, max_pages=10):
    """解析单帖。

    reply_media=True 时逐条打开回复页补媒体（每条一次请求，慢）。
    """
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
    root['reply_count_claimed'] = _claimed_replies(html)

    replies = _replies(nodes, code)
    if reply_media:
        have = {r['code'] for r in replies}
        for rc in reply_codes(html, final, max_pages):
            if rc == code or rc in have:
                continue
            try:
                _, rhtml = fetch(f'https://www.threads.com/t/{rc}')
            except Exception:
                continue
            hit = [p for p in unique_posts(rhtml) if p.get('code') == rc]
            if not hit:
                continue
            rec = _record(hit[0], f'https://www.threads.com/t/{rc}')
            if _has_media(rec):
                replies.append(rec)
                have.add(rc)
    root['replies'] = replies
    return root


def _replies(nodes, root_code):
    """页面首屏里能看到的回复。"""
    out = []
    for p in nodes:
        if p.get('code') == root_code:
            continue
        info = p.get('text_post_app_info') or {}
        if not info.get('is_reply'):
            continue
        out.append(_record(p, f'https://www.threads.com/t/{p.get("code")}'))
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
        if _has_media(rec):
            out.append(rec)
        if len(out) >= limit:
            break
    return out
