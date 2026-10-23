"""批量优化贴图池：gifsicle 重压缩 / 转 webp，带断点续跑。

优化是破坏性操作，所以规则明确：

1. **永不覆盖原文件**。结果写到 `optimized/`，原图留在 `stickers/`。
2. 只有明显收益（省 >15%）才保留结果，否则记录 skip。
3. 状态写 `optimize.json`，中断可续跑。
4. 大文件优先：按体积降序处理，先拿收益最大的。
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from . import giftool

STATE = 'optimize.json'
MAX_BYTES = 20 * 1024 * 1024   # 单文件上限，超了跳过（内存限制）


class Optimizer:
    def __init__(self, root, workers=4, log=print):
        self.root = root
        self.log = log
        self.src_dir = os.path.join(root, 'stickers')
        self.out_dir = os.path.join(root, 'optimized')
        self.state_path = os.path.join(root, STATE)
        self.workers = workers
        self.done = {}
        self._load()

    def _load(self):
        if os.path.exists(self.state_path):
            with open(self.state_path, encoding='utf-8') as f:
                self.done = json.load(f).get('done', {})

    def save(self):
        tmp = self.state_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'done': self.done,
                       'updated': time.strftime('%Y-%m-%d %H:%M:%S')}, f)
        os.replace(tmp, self.state_path)

    def candidates(self, min_bytes=100 * 1024, max_bytes=MAX_BYTES):
        """按体积降序返回待优化文件。太小的没收益，跳过。"""
        out = []
        for name in os.listdir(self.src_dir):
            if not name.endswith('.gif'):
                continue
            path = os.path.join(self.src_dir, name)
            size = os.path.getsize(path)
            if size < min_bytes or size > max_bytes or name in self.done:
                continue
            out.append((size, name))
        out.sort(reverse=True)
        return out

    def _one(self, args):
        size, name = args
        src = os.path.join(self.src_dir, name)
        out = os.path.join(self.out_dir, name)
        # 超大 GIF（>20MB）gifsicle 要吃掉同等内存，898MB 机器会 OOM
        if size > MAX_BYTES:
            return name, {'status': 'skip', 'before': size, 'saved': 0,
                          'reason': 'too_large'}
        try:
            _, before, after = giftool.optimize(
                src, out, colors=128, lossy=60, max_width=1024)
        except Exception as e:
            return name, {'status': 'error', 'error': f'{type(e).__name__}: {e}'}
        saved = 1 - after / before if before else 0
        if saved < 0.15:
            # 收益太小，删掉结果，原图更保真
            os.remove(out)
            return name, {'status': 'skip', 'before': before, 'saved': round(saved, 3)}
        return name, {'status': 'ok', 'before': before, 'after': after,
                      'saved': round(saved, 3)}

    def run(self, limit=None, min_bytes=100 * 1024, log=None):
        log = log or self.log or (lambda *a, **k: None)
        os.makedirs(self.out_dir, exist_ok=True)
        todo = self.candidates(min_bytes)
        if limit:
            todo = todo[:limit]
        if not todo:
            log('没有待优化文件')
            return {}
        log(f'待优化 {len(todo)} 个，共 {sum(s for s, _ in todo)//1048576} MB')

        stats = {'ok': 0, 'skip': 0, 'error': 0, 'saved_bytes': 0}
        n = 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for name, r in ex.map(self._one, todo):
                self.done[name] = r
                stats[r['status']] += 1
                if r['status'] == 'ok':
                    stats['saved_bytes'] += r['before'] - r['after']
                n += 1
                if n % 50 == 0:
                    self.save()
                    log(f'  {n}/{len(todo)}  已省 {stats["saved_bytes"]//1048576} MB')
        self.save()
        log(f'完成：成功 {stats["ok"]} 跳过 {stats["skip"]} 失败 {stats["error"]}，'
            f'共省 {stats["saved_bytes"]//1048576} MB')
        return stats

    def summary(self):
        ok = [r for r in self.done.values() if r.get('status') == 'ok']
        if not ok:
            return {'count': 0}
        before = sum(r['before'] for r in ok)
        after = sum(r['after'] for r in ok)
        return {'count': len(ok), 'before': before, 'after': after,
                'saved': before - after,
                'ratio': round(1 - after / before, 3)}
