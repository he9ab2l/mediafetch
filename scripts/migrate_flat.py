#!/usr/bin/env python3
"""把 v1 的散放存档（<来源>/<code>/stickers/<code>_sticker_N_<id>.gif）迁移到
v2 布局（stickers/<id>.gif 单一表情池 + 元数据保留）。

用法：
    python3 scripts/migrate_flat.py SRC DST

不联网，只搬文件 + 重写 manifest。SRC 原样保留，不删东西。
"""
import hashlib
import json
import os
import re
import shutil
import sys

STICKER_RE = re.compile(r'.*_sticker_\d+_(.+)\.(gif|webp|jpg|png)$')


def sticker_id(path):
    m = STICKER_RE.match(os.path.basename(path))
    return m.group(1) if m else os.path.splitext(os.path.basename(path))[0]


def main(src, dst):
    os.makedirs(os.path.join(dst, 'stickers'), exist_ok=True)
    rows = [json.loads(l) for l in open(os.path.join(src, 'manifest.jsonl'))]

    uniq = {}
    for r in rows:
        if r.get('kind') == 'sticker' and r.get('sha256') and r.get('path'):
            uniq.setdefault(r['sha256'], r)

    moved = missing = 0
    with open(os.path.join(dst, 'manifest.jsonl'), 'w') as mf:
        for digest, r in uniq.items():
            sid = sticker_id(r['path'])
            ext = os.path.splitext(r['path'])[1].lstrip('.') or 'gif'
            srcpath = os.path.join(src, r['path'])
            if not os.path.exists(srcpath):
                missing += 1
                continue
            out = os.path.join(dst, 'stickers', f'{sid}.{ext}')
            shutil.copy2(srcpath, out)
            mf.write(json.dumps({
                'sha256': digest, 'path': f'stickers/{sid}.{ext}',
                'key': f'stickers/{sid}', 'kind': 'sticker', 'sticker_id': sid,
                'bytes': os.path.getsize(out), 'source': r.get('source', ''),
            }, ensure_ascii=False) + '\n')
            moved += 1

    print(f'迁移 {moved} 个表情，缺失 {missing} 个 → {dst}/stickers')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
