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

from .collect import SCENES, Task, is_post_url
from .download import Downloader
from .giftool import survey
from .pipeline import Pipeline
from .media import guess_ext
from .registry import PLATFORMS, detect
from .select import Select
from .store import Store


# ---------- 子命令：list ----------

def cmd_list(a):
    name = _platform(a.target)
    spec = PLATFORMS[name]
    if is_post_url(a.target):
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
    if is_post_url(a.target):
        records = [spec['post'](a.target, reply_media=a.replies,
                                max_pages=a.reply_pages)]
    else:
        records = spec['profile'](a.target.lstrip('@'), a.limit)

    if a.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return

    sel = _select(a)
    seen = set()
    store = Store(a.out) if a.dl else None
    for rec in records:
        print(_fmt(rec))
        _flat(rec, store, sel, seen)
        for r in (rec.get('replies') or []) if a.replies else []:
            _flat(r, store, sel, seen)


def _flat(rec, store, sel, seen):
    """平铺下载一条记录的媒体和贴图。store 由调用方复用，避免重读 manifest。"""
    if store is None:
        return
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

    p = sub.add_parser('discover', help='自动发现最近 N 天带贴图的帖子')
    p.add_argument('root', help='工作目录（存 discover.json 状态）')
    p.add_argument('--days', type=int, default=30, help='时间窗，默认 30 天')
    p.add_argument('--target', type=int, default=9000, help='目标贴图数')
    p.add_argument('--rounds', type=int, default=80, help='最多扩散几轮')
    p.add_argument('--workers', type=int, default=16)
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser('fetch', help='按发现结果下载贴图')
    p.add_argument('root', help='工作目录（读 discover.json）')
    p.add_argument('--archive', required=True, help='贴图输出目录')
    p.add_argument('--workers', type=int, default=24)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser('gif', help='GIF 体检与转换')
    p.add_argument('root', help='存档根目录')
    p.add_argument('--dir', default='stickers')
    p.add_argument('--limit', type=int)
    p.add_argument('--json', action='store_true')
    p.set_defaults(func=cmd_gif)
    return ap


def cmd_discover(a):
    pipe = Pipeline(a.root, days=a.days, workers=a.workers)
    n = pipe.run(target_stickers=a.target, max_rounds=a.rounds)
    print(f'\n发现完成：{len(pipe.d.posts)} 帖 / {n} 贴图 / '
          f'{len(pipe.d.authors)} 作者')
    print(f'状态：{pipe.path}')


def cmd_fetch(a):
    import json as _json
    pipe = Pipeline(a.root, workers=a.workers)
    dl = Downloader(a.archive, workers=a.workers)
    r = dl.run(pipe.d.posts)
    print(_json.dumps(r, ensure_ascii=False))


def cmd_gif(a):
    import json as _json
    rep = survey(a.root, a.dir, a.limit)
    if a.json:
        print(_json.dumps(rep, ensure_ascii=False, indent=2))
        return
    print(f"文件 {rep['count']} 个，共 {rep['bytes']//1048576} MB，"
          f"平均 {rep['avg_bytes']//1024} KB / {rep['avg_frames']} 帧")
    note = rep.get('static_animation_note', '')
    print(f"动图 {rep['animated']}，看着像动图其实静止 {rep['static_animation']}{note}")
    print('\n最大的 10 个：')
    for b in rep['biggest']:
        print(f"  {b['bytes']//1024:5d} KB  {b['frames']:3d} 帧  "
              f"{b['size']:>10s}  {b['name']}")
    if rep['errors']:
        print(f"\n{len(rep['errors'])} 个读取失败")


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.func(a)


if __name__ == '__main__':
    main()
