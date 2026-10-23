"""按发现结果批量下载贴图。

与 discover/pipeline 解耦：读 `discover.json` 里的帖子清单，逐条下载贴图，
写进 store 的 manifest。已经下过的按 sticker id 跳过。

为什么单独一层：发现很慢（要翻几百个主页），下载很快（并发 24 路）。
分开后可以「先发现一大票，再一次性下载」，中途断了也不丢发现成果。
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from .store import Store, safe_name

WORKERS = 24


class Downloader:
    def __init__(self, root, workers=WORKERS):
        self.store = Store(root)
        self.workers = workers
        self.lock = threading.Lock()
        self.failed = []
        self.done = 0

    def _fetch_one(self, sticker, source):
        """下一个贴图，返回 (rel, new) 或 None。"""
        sid = safe_name(sticker['id'])
        if self.store.is_done(os.path.join('stickers', sid)):
            with self.lock:
                self.store.skipped += 1
            return None
        try:
            return self.store.save_sticker(sticker, source)
        except Exception as e:
            with self.lock:
                self.failed.append((sid, f'{type(e).__name__}: {e}'))
            return None

    def run(self, posts, log=print):
        """posts: {code: {code, author, taken_at, stickers: [...]}}"""
        jobs = []
        for code, rec in posts.items():
            author = rec.get('author') or ''
            url = (f'https://www.threads.com/@{author}/post/{code}'
                   if author else f'https://www.threads.com/t/{code}')
            for s in rec.get('stickers') or []:
                jobs.append((s, f'post:{url}'))
        log(f'待下载 {len(jobs)} 个贴图（帖子 {len(posts)} 条）')

        seen = set()
        uniq = []
        for s, src in jobs:
            sid = s.get('id')
            if sid in seen:
                continue
            seen.add(sid)
            uniq.append((s, src))
        log(f'去重后 {len(uniq)} 个唯一贴图 id')

        n = 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = [ex.submit(self._fetch_one, s, src) for s, src in uniq]
            for f in futs:
                r = f.result()
                if r and r[1]:
                    n += 1
                if n and n % 200 == 0:
                    log(f'  已存 {n} 个新文件')
        stats = self.store.stats()
        log(f'下载完成：新文件 {n}，去重跳过 {stats["dupes"]}，'
            f'失败 {len(self.failed)}，唯一内容 {stats["unique"]}')
        return {'new': n, 'failed': len(self.failed), **stats}
