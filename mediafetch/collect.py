"""编排：把 抓取 → 筛选 → 存档 串成一次任务。不做解析、不做落盘细节。

场景（scene）决定顺序与范围，都通过 Select 表达：

    posts     只抓给定帖子本身（不抓回复、不抓主页）
    threads   帖子 + 它的回复（不抓主页）
    full      帖子 + 作者主页 + 回复 + 回复者主页（默认，最全）
    profiles  只抓给定账号的主页
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from .platforms import threads
from .select import Select
from .store import Store, safe_name

WORKERS = 16
SCENES = ('posts', 'threads', 'full', 'profiles')


class Task:
    """一次抓取任务：目标列表 + 场景 + 筛选 + 输出目录。"""

    def __init__(self, targets, root, scene='full', select=None,
                 reply_pages=10, limit=50, workers=WORKERS, log=print):
        if scene not in SCENES:
            raise ValueError(f'未知场景 {scene}，可选 {SCENES}')
        self.targets = list(targets)
        self.log = log
        self.scene = scene
        self.sel = select or Select.all()
        self.reply_pages = reply_pages
        self.limit = limit
        self.workers = workers
        self.store = Store(root)
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.lock = threading.Lock()
        self.profiles_done = set()
        self.failures = []
        self.report = {'scene': scene, 'select': repr(self.sel),
                       'posts': 0, 'replies': 0, 'profiles': 0,
                       'stickers': 0, 'images': 0, 'videos': 0}

    # ---------- 输出 ----------

    def _say(self, line):
        with self.lock:
            self.log(line, flush=True)

    def _fail(self, prefix, exc):
        self._say(f"   FAIL\t{prefix}\t{type(exc).__name__}: {exc}")
        with self.lock:
            self.failures.append(prefix)

    # ---------- 计划 ----------

    def _plan(self, rec, base, source, jobs):
        """把一条记录展开成下载任务。筛选在这里生效。"""
        code = safe_name(rec['code'])
        for i, item in enumerate(self.sel.pick_media(rec), 1):
            sub = 'videos' if item['type'] == 'video' else 'images'
            jobs.append(('media', item, os.path.join(base, sub),
                         f'{code}_{i}', source))
        for sticker in self.sel.pick_stickers(rec):
            jobs.append(('sticker', sticker, None, None, source))
        for q in self.sel.pick_quoted(rec):
            self._plan(q, os.path.join(base, 'quoted', safe_name(q['code'])),
                       f"{source}/quoted:{q['code']}", jobs)

    def _run(self, job):
        kind, payload, dest, prefix, src = job
        try:
            if kind == 'sticker':
                rel, new = self.store.save_sticker(payload, src)
                if rel:
                    with self.lock:
                        self.report['stickers'] += 1
            else:
                rel, new = self.store.save_media(payload, dest, prefix, src)
                if rel:
                    with self.lock:
                        self.report['videos' if payload['type'] == 'video'
                                    else 'images'] += 1
        except Exception as e:
            self._fail(prefix or (payload.get('id') if isinstance(payload, dict) else '?'), e)
            return
        if rel is None:      # 任务级去重命中，没发请求
            return
        self._say(f"   {'saved' if new else 'dupe '}\t{rel}")

    def _drain(self, jobs):
        for f in [self.pool.submit(self._run, j) for j in jobs]:
            f.result()

    # ---------- 三个抓取动作 ----------

    def do_post(self, url):
        """抓一帖：落元数据 + 它自身的内容（不含回复、不含主页）。"""
        rec = threads.post(url, reply_media=False)
        code = safe_name(rec['code'])
        base = os.path.join('posts', code)
        jobs = []
        self._plan(rec, base, f"post:{rec['url']}", jobs)
        self._drain(jobs)
        self.store.save_json(rec, os.path.join(base, 'post.json'),
                             f'posts/{code}/post.json', f"post:{rec['url']}")
        with self.lock:
            self.report['posts'] += 1
        self._say(f"post {rec['code']} @{rec['author']} "
                  f"stickers={len(self.sel.pick_stickers(rec))} "
                  f"media={len(self.sel.pick_media(rec))}")
        return rec

    def do_replies(self, rec):
        """补抓回复。单独一步，因为回复翻页要额外请求。"""
        full = threads.post(rec['url'], reply_media=True,
                            max_pages=self.reply_pages, workers=self.workers)
        code = safe_name(full['code'])
        todo = [r for r in full.get('replies') or [] if self.sel.useful(r)]
        jobs = []
        for r in todo:
            base = os.path.join('posts', code, 'replies', safe_name(r['code']))
            self._plan(r, base, f"reply:{r['url']}", jobs)
            self.store.save_json(r, os.path.join(base, 'reply.json'),
                                 f'posts/{code}/replies/{safe_name(r["code"])}/reply.json',
                                 f"reply:{r['url']}")
        self._drain(jobs)
        with self.lock:
            self.report['replies'] += len(todo)
        self._say(f"replies {rec['code']} {len(todo)} 条带内容")
        return todo

    def do_profile(self, handle):
        """抓一个账号的主页时间线。"""
        handle = (handle or '').lstrip('@')
        with self.lock:
            if not handle or handle in self.profiles_done:
                return
            self.profiles_done.add(handle)
        try:
            recs = threads.profile(handle, self.limit)
        except Exception as e:
            self._say(f"profile @{handle} failed: {e}")
            return
        base = os.path.join('profiles', safe_name(handle))
        self.store.save_json({'handle': handle, 'posts': recs},
                             os.path.join(base, 'profile.json'),
                             f'profiles/{safe_name(handle)}/profile.json',
                             f'profile:@{handle}')
        jobs = []
        for rec in recs:
            if not self.sel.useful(rec):
                continue
            self._plan(rec, os.path.join(base, 'posts', safe_name(rec['code'])),
                       f"profile:@{handle}/{rec['code']}", jobs)
        self._drain(jobs)
        with self.lock:
            self.report['profiles'] += 1
        self._say(f"profile @{handle} posts={len(recs)}")

    # ---------- 主流程 ----------

    def run(self):
        for target in self.targets:
            if is_post_url(target):
                self._run_post_scene(target)
            else:
                self.do_profile(target)
        return self.finish()

    def _run_post_scene(self, url):
        rec = self.do_post(url)
        if self.scene == 'posts':
            return
        if self.scene in ('full',) and self.sel.follow_profiles:
            self.do_profile(rec.get('author'))
        if not self.sel.follow_replies:
            return
        todo = self.do_replies(rec)
        if self.scene != 'full' or not self.sel.follow_profiles:
            return
        handles = [r.get('author') for r in todo]
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(self.do_profile, handles))

    def finish(self):
        self.pool.shutdown()
        self.report.update(self.store.stats())
        self.report['failures'] = len(self.failures)
        self.report['failed_keys'] = self.failures[:50]
        self.store.write_index(self.report)
        return self.report


def is_post_url(target):
    """判断一个目标是不是帖子链接（否则当账号处理）。"""
    return any(seg in target for seg in ('/post/', '/t/', '/share/'))
