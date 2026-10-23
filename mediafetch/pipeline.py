"""发现流水线：持久化状态，多轮扩散，直到贴图数达标或作者池耗尽。

状态存在 JSON 里，可以中断续跑：

    {
      "queries_done": ["sticker", ...],
      "profiles_done": ["handle", ...],
      "authors_pending": ["handle", ...],
      "posts": {"code": {code, author, taken_at, stickers: [...]}},
      "stats": {...}
    }

发现和下载解耦：先攒够帖子清单，再统一下载。这样中断不会丢进度。
"""
import json
import os
import time

from .discover import Discoverer, SEED_QUERIES

STATE = 'discover.json'


class Pipeline:
    def __init__(self, root, days=30, min_stickers=1, workers=16):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.path = os.path.join(root, STATE)
        self.d = Discoverer(days=days, min_stickers=min_stickers, workers=workers)
        self.queries_done = set()
        self.profiles_done = set()
        self._load()

    # ---------- 状态 ----------

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding='utf-8') as f:
            s = json.load(f)
        self.queries_done = set(s.get('queries_done', []))
        self.profiles_done = set(s.get('profiles_done', []))
        for code, rec in s.get('posts', {}).items():
            self.d.posts[code] = rec
        for h in s.get('authors_pending', []):
            self.d.authors.add(h)
        self.d.stats.update(s.get('stats', {}))
        print(f"续跑：已收 {len(self.d.posts)} 帖 / "
              f"{self.d.sticker_count()} 贴图 / {len(self.d.authors)} 作者")

    def save(self):
        s = {
            'queries_done': sorted(self.queries_done),
            'profiles_done': sorted(self.profiles_done),
            'authors_pending': sorted(self.d.authors),
            'posts': self.d.posts,
            'stats': self.d.stats,
            'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ---------- 两个阶段 ----------

    def search_round(self, queries=SEED_QUERIES):
        """跑没跑过的搜索词。"""
        todo = [q for q in queries if q not in self.queries_done]
        if not todo:
            return 0
        self.d.run_queries(todo)
        self.queries_done.update(todo)
        self.save()
        return len(todo)

    def profile_round(self):
        """抓一批没抓过的主页，返回新收的帖子数。"""
        todo = [h for h in sorted(self.d.authors) if h not in self.profiles_done]
        if not todo:
            return 0
        before = len(self.d.posts)
        self.d.run_profiles(todo)
        self.profiles_done.update(todo)
        self.save()
        return len(self.d.posts) - before

    def run(self, target_stickers, max_rounds=40, log=print):
        """一直扩散到贴图数达标或没有新作者。"""
        log(f"开始：目标 {target_stickers} 个贴图，时间窗 {self.d.days} 天")
        self.search_round()
        log(f"搜索后：{len(self.d.posts)} 帖 / {self.d.sticker_count()} 贴图")

        for r in range(1, max_rounds + 1):
            if self.d.sticker_count() >= target_stickers:
                log(f"达标：{self.d.sticker_count()} 个贴图")
                break
            pending = len([h for h in self.d.authors if h not in self.profiles_done])
            if pending == 0:
                log("作者池耗尽，停止扩散")
                break
            t = time.time()
            new = self.profile_round()
            log(f"轮 {r}: +{new} 帖，{time.time()-t:.0f}s，"
                f"累计 {len(self.d.posts)} 帖 / {self.d.sticker_count()} 贴图 / "
                f"{len(self.d.authors)} 作者（待抓 {pending}）")
        self.save()
        return self.d.sticker_count()

    # ---------- 导出 ----------

    def export_codes(self):
        """按贴图数降序返回 [(code, url, sticker_count)]。"""
        out = []
        for code, rec in self.d.posts.items():
            n = len(rec.get('stickers') or [])
            if n:
                author = rec.get('author') or ''
                url = (f'https://www.threads.com/@{author}/post/{code}'
                       if author else f'https://www.threads.com/t/{code}')
                out.append((code, url, n))
        out.sort(key=lambda x: -x[2])
        return out
