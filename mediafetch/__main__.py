"""命令行入口：python -m mediafetch <url|@handle> [--dl] [--out DIR] [--replies]"""
import argparse
import json
import os
import re
import sys

from .core import download, merge_av
from .registry import PLATFORMS, detect


class Seen:
    """跨记录去重：同一媒体 URL / 同一贴图 id 只处理一次。

    回复和它的引用块常指向同一条帖子，媒体 URL 完全相同；
    giphy 贴图也可能被多条回复共用。
    """

    def __init__(self):
        self.urls = set()
        self.stickers = set()

    def media(self, item):
        url = item['url']
        if url in self.urls:
            return False
        self.urls.add(url)
        return True

    def sticker(self, sticker):
        sid = sticker['id']
        if sid in self.stickers:
            return False
        self.stickers.add(sid)
        return True


def _emit(rec, outdir, seen):
    """打印并（可选）下载一条记录自身的媒体、贴图、引用块。"""
    for i, item in enumerate(rec['media']):
        if not seen.media(item):
            print(f"   {item['type']}\t{item['width']}x{item['height']}\t(重复，已跳过)")
            continue
        print(f"   {item['type']}\t{item['width']}x{item['height']}\t{item['url'][:100]}")
        if not outdir:
            continue
        prefix = f"{rec['code']}_{i + 1}"
        merged = None
        if item['type'] == 'video' and item.get('dash_video') and item.get('dash_audio'):
            try:
                merged = merge_av(item['dash_video'], item['dash_audio'], outdir, prefix)
            except Exception as e:
                print(f'   merge failed: {e}')
        if merged:
            print(f'   saved\t{merged[0]}\t{merged[1]}\t(DASH 合流)')
        else:
            path, size = download(item['url'], outdir, prefix)
            print(f'   saved\t{path}\t{size}')

    for i, sticker in enumerate(rec['stickers']):
        if not seen.sticker(sticker):
            print(f"   sticker\t{sticker['id']}\t(重复，已跳过)")
            continue
        if outdir:
            candidates = sticker.get('sources') or [sticker['url']]
            path, size = download(candidates, outdir,
                                  f"{rec['code']}_sticker_{i + 1}_{sticker['id']}")
            print(f'   saved\t{path}\t{size}')
        else:
            print(f"   sticker\t{sticker['id']}")

    for quoted in rec.get('quoted') or []:
        print(f"   quoted[{quoted['kind']}] {quoted['code']}\t"
              f"media={len(quoted['media'])}\tstickers={len(quoted['stickers'])}"
              f"\t{quoted['caption'][:40]}")
        _emit(quoted, outdir, seen)


def render(records, outdir=None, with_replies=False):
    seen = Seen()
    for rec in records:
        print(f"{rec['code']}\t{rec['media_type']}\t"
              f"media={len(rec['media'])}\tstickers={len(rec['stickers'])}\t"
              f"quoted={len(rec.get('quoted') or [])}\t{rec['caption'][:60]}")
        _emit(rec, outdir, seen)

        if not with_replies:
            continue
        replies = rec.get('replies') or []
        claimed = rec.get('reply_count_claimed')
        with_media = [r for r in replies if r['media'] or r['stickers'] or r.get('quoted')]
        print(f"   replies: {len(replies)}/{claimed if claimed is not None else '?'} "
              f"（{len(with_media)} 条带媒体）")
        for r in replies:
            if not (r['media'] or r['stickers'] or r.get('quoted')):
                continue
            print(f"   reply {r['code']}\tmedia={len(r['media'])}\t"
                  f"stickers={len(r['stickers'])}\t{r['caption'][:40]}")
            _emit(r, outdir, seen)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='mediafetch', description='公开社媒页面媒体抓取')
    ap.add_argument('target', help='帖子链接，或 @账号')
    ap.add_argument('--out', help='下载目录（不给则只打印 URL）')
    ap.add_argument('--dl', action='store_true', help='下载媒体文件到 --out')
    ap.add_argument('--limit', type=int, default=50, help='账号模式下最多取多少帖')
    ap.add_argument('--json', action='store_true', help='输出 JSON 而非文本')
    ap.add_argument('--replies', action='store_true',
                    help='列出回复里的媒体（含 GraphQL 翻页，需逐条取媒体，较慢）')
    ap.add_argument('--reply-pages', type=int, default=10, help='回复翻页上限，默认 10')
    a = ap.parse_args(argv)

    name = detect(a.target) if '//' in a.target else None
    if name is None and a.target.startswith('@'):
        name = 'threads'
    if name is None:
        sys.exit(f'不支持的链接：{a.target}（已支持：{", ".join(PLATFORMS)}）')

    spec = PLATFORMS[name]
    if re.search(r'/post/|/t/|/share/', a.target):
        records = [spec['post'](a.target, reply_media=a.replies,
                                max_pages=a.reply_pages)]
    else:
        handle = a.target.lstrip('@')
        records = spec['profile'](handle, a.limit)

    if a.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return
    outdir = (a.out or 'downloads') if a.dl else None
    if outdir:
        os.makedirs(outdir, exist_ok=True)
    render(records, outdir, with_replies=a.replies)


if __name__ == '__main__':
    main()
