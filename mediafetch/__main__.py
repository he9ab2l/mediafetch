"""命令行入口：python -m mediafetch <url|@handle> [--dl] [--out DIR] [--limit N]"""
import argparse
import json
import os
import re
import sys

from .core import download
from .registry import PLATFORMS, detect


def _emit(rec, outdir):
    for i, item in enumerate(rec['media']):
        print(f"   {item['type']}\t{item['width']}x{item['height']}\t{item['url'][:100]}")
        if outdir:
            path, size = download(item['url'], outdir, f"{rec['code']}_{i + 1}")
            print(f'   saved\t{path}\t{size}')
    for i, sticker in enumerate(rec['stickers']):
        if outdir:
            candidates = sticker.get('sources') or [sticker['url']]
            path, size = download(candidates, outdir,
                                  f"{rec['code']}_sticker_{i + 1}_{sticker['id']}")
            print(f'   saved\t{path}\t{size}')
        else:
            print(f"   sticker\t{sticker['id']}")


def render(records, outdir=None, with_replies=False):
    for rec in records:
        print(f"{rec['code']}\t{rec['media_type']}\t"
              f"media={len(rec['media'])}\tstickers={len(rec['stickers'])}\t{rec['caption'][:60]}")
        _emit(rec, outdir)
        if not with_replies:
            continue
        replies = rec.get('replies') or []
        claimed = rec.get('reply_count_claimed')
        with_media = [r for r in replies if r['media'] or r['stickers']]
        print(f"   replies: {len(replies)}/{claimed if claimed is not None else '?'} "
              f"（页面首屏，{len(with_media)} 条带媒体）")
        for r in replies:
            if not (r['media'] or r['stickers']):
                continue
            print(f"   reply {r['code']}\tmedia={len(r['media'])}\t{r['caption'][:40]}")
            _emit(r, outdir)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='mediafetch', description='公开社媒页面媒体抓取')
    ap.add_argument('target', help='帖子链接，或 @账号')
    ap.add_argument('--out', help='下载目录（不给则只打印 URL）')
    ap.add_argument('--dl', action='store_true', help='下载媒体文件到 --out')
    ap.add_argument('--limit', type=int, default=50, help='账号模式下最多取多少帖')
    ap.add_argument('--json', action='store_true', help='输出 JSON 而非文本')
    ap.add_argument('--replies', action='store_true', help='同时列出/下载页面首屏的回复媒体')
    a = ap.parse_args(argv)

    name = detect(a.target) if '//' in a.target else None
    if name is None and a.target.startswith('@'):
        name = 'threads'
    if name is None:
        sys.exit(f'不支持的链接：{a.target}（已支持：{", ".join(PLATFORMS)}）')

    spec = PLATFORMS[name]
    if re.search(r'/post/|/t/|/share/', a.target):
        records = [spec['post'](a.target)]
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
