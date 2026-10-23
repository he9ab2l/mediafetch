"""帖子发现：从搜索页和作者主页收集候选帖子。

Threads 的搜索 GraphQL 需要登录（匿名发请求返回 HTML 登录墙），但搜索
**页面本身**是服务端渲染的，里面带 20-55 条帖子。主页同理。所以发现
只能靠「翻页面前端渲染」，不能靠接口。

发现链路：

    SEED_QUERIES（多语言关键词）
        ↓ 搜索页，每词 ~20-55 帖
    候选帖子（带 taken_at，可筛最近 N 天）
        ↓ 抽出作者
    作者主页（每人 ~15-50 帖）
        ↓ 再抽作者
    第二轮扩散（可选）

每轮都按时间窗过滤，只留最近 N 天的帖子。
"""
import datetime
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from .net import fetch
from .page import unique_nodes
from .platforms.threads import _is_post_node, author_of, stickers_of

# 多语言关键词。英文为主（Threads 英文内容最多），中日韩补充。
SEED_QUERIES = (
    # 英文
    'sticker', 'stickers', 'cute sticker', 'cat sticker', 'dog sticker',
    'funny sticker', 'love sticker', 'meme sticker', 'animated sticker',
    'sticker pack', 'kawaii sticker', 'emoji sticker', 'aesthetic sticker',
    'sticker collection', 'sticker sharing', 'giphy sticker', 'cute gif',
    'reaction sticker', 'sticker drop', 'pink sticker', 'bear sticker',
    'bunny sticker', 'sanrio sticker', 'line sticker', 'telegram sticker',
    # 中文
    '表情包', '表情', '貼圖', '小表情', '表情包分享', '可爱表情包',
    '猫猫表情包', '狗狗表情包', '表情包存图',
    # 日韩
    'スタンプ', '스티커', '이모티콘',
)

SEARCH_URL = 'https://www.threads.com/search?q='
PROFILE_URL = 'https://www.threads.com/@'


def _age_days(post, now):
    ts = post.get('taken_at')
    if not ts:
        return None
    return (now - ts) / 86400


def search(query, min_stickers=1):
    """跑一次搜索，返回页面里的帖子节点。"""
    final, html = fetch(SEARCH_URL + urllib.parse.quote(query))
    return unique_nodes(html, _is_post_node)


def profile_posts(handle):
    """抓一个账号主页的帖子节点（首屏）。"""
    final, html = fetch(PROFILE_URL + handle)
    return unique_nodes(html, _is_post_node)


class Discoverer:
    """收集候选帖子，按时间窗和贴图数过滤，并记住见过的作者。"""

    def __init__(self, days=30, min_stickers=1, workers=12):
        self.days = days
        self.min_stickers = min_stickers
        self.workers = workers
        self.now = datetime.datetime.now().timestamp()
        self.posts = {}      # code -> post node
        self.authors = set()  # 见过的 handle
        self.stats = {'queries': 0, 'profiles': 0, 'seen': 0,
                      'kept': 0, 'too_old': 0, 'no_sticker': 0}

    def _consider(self, post):
        """一条帖子值不值得收。返回 True 表示收下。"""
        code = post.get('code')
        if not code or code in self.posts:
            return False
        self.stats['seen'] += 1
        handle = author_of(post)
        if handle:
            self.authors.add(handle)
        if len(stickers_of(post)) < self.min_stickers:
            self.stats['no_sticker'] += 1
            return False
        age = _age_days(post, self.now)
        if age is not None and age > self.days:
            self.stats['too_old'] += 1
            return False
        self.posts[code] = {
            'code': code,
            'author': handle,
            'taken_at': post.get('taken_at'),
            'caption': ((post.get('caption') or {}).get('text') or '')[:200],
            'stickers': stickers_of(post),
        }
        self.stats['kept'] += 1
        return True

    def run_queries(self, queries=SEED_QUERIES):
        """并发跑一批搜索词。"""
        def one(q):
            try:
                return search(q)
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for nodes in ex.map(one, queries):
                self.stats['queries'] += 1
                for p in nodes:
                    self._consider(p)
        return len(self.posts)

    def run_profiles(self, handles):
        """并发抓一批主页。"""
        def one(h):
            try:
                return profile_posts(h)
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for nodes in ex.map(one, sorted(handles)):
                self.stats['profiles'] += 1
                for p in nodes:
                    self._consider(p)
        return len(self.posts)

    def expand(self, rounds=1):
        """从已收作者出发，抓他们主页，再收新作者。"""
        for _ in range(rounds):
            before = len(self.authors)
            self.run_profiles(set(self.authors))
            if len(self.authors) == before:
                break
        return len(self.posts)

    def sticker_count(self):
        return sum(len(p.get('stickers') or []) for p in self.posts.values())
