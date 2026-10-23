"""存档布局与落盘。只管「文件放哪、怎么去重」，不管抓取和筛选。

## 目录结构

    <root>/
      manifest.jsonl              全局索引：每份内容一行（sha256 / 路径 / 出处）
      index.json                  任务摘要：跑了哪些帖、哪些主页、各多少
      stickers/                   表情池：全部 gif 集中一处，按 id 命名
        <sticker_id>.gif
      posts/
        <code>/
          post.json               帖子元数据（含 caption、作者、媒体清单）
          images/<code>_<n>.jpg
          videos/<code>_<n>.mp4
          replies/<reply_code>/
            reply.json
            images/ videos/
      profiles/
        <handle>/
          profile.json            该账号时间线里的帖子元数据
          posts/<code>/
            images/ videos/

表情单独成池的理由：同一个 giphy 贴图会被帖子、回复、多个主页反复引用，
按来源放会散成一堆同名副本；集中后一个 id 一个文件，一眼能数清有多少个。

## 两级去重

1. 任务级（省网络）：manifest 记着每个 (目录, 前缀)。续跑直接跳过，不发请求。
2. 内容级（省磁盘）：同一 sha256 只落一份，后续只在 manifest 追加 duplicate_of。
"""
import hashlib
import json
import os
import re
import threading

from . import media
from .net import get_first

MANIFEST = 'manifest.jsonl'
INDEX = 'index.json'

_SAFE = re.compile(r'[^\w.-]+')


def safe_name(text, fallback='x'):
    """把任意字符串变成安全的文件名片段。"""
    return _SAFE.sub('_', str(text or '')).strip('._') or fallback


class Store:
    """下载 + 两级去重 + manifest 记账。线程安全。"""

    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.manifest = os.path.join(root, MANIFEST)
        self.by_hash = {}   # sha256 -> 已落盘相对路径
        self.done = set()   # 已完成的任务 key
        self.count = 0      # 新写文件数
        self.skipped = 0    # 去重跳过数
        self._lock = threading.RLock()
        self._load()

    # ---------- manifest ----------

    def _load(self):
        if not os.path.exists(self.manifest):
            return
        with open(self.manifest, encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get('sha256') and row.get('path'):
                    self.by_hash.setdefault(row['sha256'], row['path'])
                if row.get('key'):
                    self.done.add(row['key'])

    def _record(self, **row):
        with self._lock:
            with open(self.manifest, 'a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')

    def is_done(self, key):
        return key in self.done

    # ---------- 写入 ----------

    def _write(self, data, dest, key, **meta):
        """返回 (相对路径, 是否新文件)；内容已存在则只记一条 duplicate_of。"""
        digest = hashlib.sha256(data).hexdigest()
        rel = os.path.relpath(dest, self.root)
        with self._lock:
            known = self.by_hash.get(digest)
            if known and os.path.exists(os.path.join(self.root, known)):
                self._record(sha256=digest, path=known, key=key,
                             duplicate_of=rel, **meta)
                self.skipped += 1
                return known, False
            os.makedirs(os.path.dirname(dest) or self.root, exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(data)
            self.by_hash[digest] = rel
            self.done.add(key)
            self._record(sha256=digest, path=rel, key=key, bytes=len(data), **meta)
            self.count += 1
            return rel, True

    # ---------- 对外：三类内容 ----------

    def save_sticker(self, sticker, source, data=None):
        """贴图进表情池，文件名就是 sticker id，天然不重复。

        data 给了就直接落盘（调用方自己下载），没给就自己下。
        """
        sid = safe_name(sticker['id'])
        key = os.path.join('stickers', sid)
        if key in self.done:
            self.skipped += 1
            return None, False
        cands = list(sticker.get('sources') or [sticker['url']])
        if data is None:
            _, data = get_first(cands)
        dest = os.path.join(self.root, 'stickers',
                            f'{sid}.{media.guess_ext(cands[0])}')
        return self._write(data, dest, key, kind='sticker', sticker_id=sid,
                           source=source)

    def save_media(self, item, dest_dir, prefix, source):
        """图片或视频。DASH 双轨能合流就合流成单文件。"""
        key = os.path.join(dest_dir, prefix)
        if key in self.done:
            self.skipped += 1
            return None, False
        if item['type'] == 'video' and item.get('dash_video') and item.get('dash_audio'):
            data = media.merge_av(item['dash_video'], item['dash_audio'], None)
            if data:
                dest = os.path.join(self.root, dest_dir, f'{prefix}.mp4')
                return self._write(data, dest, key, kind='video', source=source)
        _, data = get_first(_as_list(item['url']))
        ext = media.guess_ext(_as_list(item['url'])[0])
        dest = os.path.join(self.root, dest_dir, f'{prefix}.{ext}')
        return self._write(data, dest, key, kind=item['type'], source=source)

    def save_json(self, obj, relpath, key, source):
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode()
        dest = os.path.join(self.root, relpath)
        return self._write(data, dest, key, kind='json', source=source)

    def write_index(self, summary):
        path = os.path.join(self.root, INDEX)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return path

    # ---------- 汇总 ----------

    def stats(self):
        return {'files': self.count, 'dupes': self.skipped,
                'unique': len(self.by_hash)}


def _as_list(url):
    return list(url) if isinstance(url, (list, tuple)) else [url]
