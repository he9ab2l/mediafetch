"""命令行入口。

三种用法，互不干扰：

    # 1. 只看不存：列出一个帖子/账号有什么
    python -m mediafetch list <url|@handle>

    # 2. 单帖下载到平铺目录（老用法）
    python -m mediafetch get <url> --dl --out DIR

    # 3. 规范存档（推荐）：按场景 + 内容类型分目录
    python -m mediafetch archive <url...> --scene full --only sticker

场景 --scene：
    posts     只抓帖子本身
    threads   帖子 + 回复
    full      帖子 + 作者主页 + 回复 + 回复者主页（默认）
    profiles  只抓账号主页

内容 --only：
    sticker   只要表情（图片视频不下载）
    media     只要图片视频
    all       全都要（默认）
"""
import argparse
import json
import sys

from .collect import SCENES, Task
from .media import guess_ext
from .net import get_bytes
from .registry import PLATFORMS, detect
from .select import Select


# ---------- 子命令：list ----------

def cmd_list(a):
    name = _platform(a.target)
    spec = PLATFORMS[name]
    if _is_post(a.target):
        rec = spec['post'](a.target, reply_media=a.replies,
                           max_pages=a.reply_pages)
        print(_fmt(rec))
        for r in rec.get('replies') or []:
            if r['media'] or r['stickers'] or r.get('quoted'):
                print('  ' + _fmt(r).replace('\n', '\n  '))
    else:
        for rec in spec['profile'](a.target.lstrip('@'), a.limit):
            print(_fmt(rec))


def _fmt(rec):
    head = (f"{rec['code']} @{rec['author']} "
            f"media={len(rec['media'])} stickers={len(rec['stickers'])} "
            f"quoted={len(rec.get('quoted') or [])}  {rec['caption'][:50]}")
    lines = [head]
    for m in rec['media']:
        lines.append(f"  {m['type']}\t{m['width']}x{m['height']}\t{m['url'][:90]}")
    for s in rec['stickers']:
        lines.append(f"  sticker\t{s['id']}")
    return '\n'.join(lines)


# ---------- 子命令：get（平铺下载） ----------

def cmd_get(a):
    name = _platform(a.target)
    spec = PLATFORMS[name]
    if _is_post(a.target):
        records = [spec['post'](a.target, reply_media=a.replies,
                                max_pages=a.reply_pages)]
    else:
        records = spec['profile'](a.target.lstrip('@'), a.limit)

    if a.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return

    sel = _select(a)
    seen = set()
    for rec in records:
        print(_fmt(rec))
        _flat(rec, a.out if a.dl else None, sel, seen)
        for r in (rec.get('replies') or []) if a.replies else []:
            _flat(r, a.out if a.dl else None, sel, seen)


def _flat(rec, outdir, sel, seen):
    from .store import Store
    if not outdir:
        return
    store = Store(outdir)
    for item in sel.pick_media(rec):
        if item['url'] in seen:
            continue
        seen.add(item['url'])
        rel, _ = store.save_media(item, '', f"{rec['code']}_{guess_ext(item['url'])}",
                                  f"get:{rec['url']}")
        if rel:
            print(f'   saved\t{rel}')
    for s in sel.pick_stickers(rec):
        if s['id'] in seen:
            continue
        seen.add(s['id'])
        rel, _ = store.save_sticker(s, f"get:{rec['url']}")
        if rel:
            print(f'   saved\t{rel}')


# ---------- 子命令：archive ----------

def cmd_archive(a):
    for t in a.targets:
        _platform(t)
    sel = _select(a)
    task = Task(a.targets, a.archive, scene=a.scene, select=sel,
                reply_pages=a.reply_pages, limit=a.limit)
    rep = task.finish() if a.dry_run else task.run()
    print(f"\n场景 {rep['scene']}  筛选 {rep['select']}")
    print(f"帖子={rep['posts']} 回复={rep['replies']} 主页={rep['profiles']}  "
          f"表情={rep['stickers']} 图={rep['images']} 视频={rep['videos']}")
    print(f"新文件={rep['files']} 去重跳过={rep['dupes']} "
          f"唯一内容={rep['unique']} 失败={rep['failures']}")
    if rep['failed_keys']:
        for k in rep['failed_keys'][:10]:
            print(f"  FAILED {k}")
    print(f"目录 {a.archive}")


# ---------- 公共 ----------

def _select(a):
    if a.only == 'all':
        return Select.all()
    if a.only == 'sticker':
        return Select.stickers_only(follow_replies=a.scene in ('threads', 'full'),
                                    follow_profiles=a.scene == 'full')
    return Select.only(*a.only.split(','))


def _is_post(target):
    return any(seg in target for seg in ('/post/', '/t/', '/share/'))


def _platform(target):
    name = detect(target) if '//' in target else None
    if name is None and target.startswith('@'):
        name = 'threads'
    if name is None:
        sys.exit(f'不支持的链接：{target}（已支持：{", ".join(PLATFORMS)}）')
    return name


def build_parser():
    ap = argparse.ArgumentParser(
        prog='mediafetch', description='公开社媒页面媒体抓取')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--only', default='all',
                       help='sticker | media | all，或逗号组合 image,video')
        p.add_argument('--limit', type=int, default=50, help='主页最多取多少帖')
        p.add_argument('--reply-pages', type=int, default=10, help='回复翻页上限')
        p.add_argument('--json', action='store_true', help='输出 JSON')

    p = sub.add_parser('list', help='只列出内容，不下载')
    p.add_argument('target')
    p.add_argument('--replies', action='store_true', help='连回复一起列')
    common(p)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('get', help='平铺下载到 --out')
    p.add_argument('target')
    p.add_argument('--out', default='downloads')
    p.add_argument('--dl', action='store_true')
    p.add_argument('--replies', action='store_true')
    common(p)
    p.set_defaults(func=cmd_get)

    p = sub.add_parser('archive', help='规范存档：按场景与类型分目录')
    p.add_argument('targets', nargs='+')
    p.add_argument('--archive', required=True, metavar='DIR', help='输出根目录')
    p.add_argument('--scene', default='full', choices=SCENES)
    p.add_argument('--dry-run', action='store_true', help='只抓元数据不下载')
    common(p)
    p.set_defaults(func=cmd_archive)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.func(a)


if __name__ == '__main__':
    main()
