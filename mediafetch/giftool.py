"""GIF 处理：探测、去重、优化、转格式、拼图预览。

外部依赖（服务器上有，本地 Termux 需 pkg install）：
- `gifsicle`  GIF 专用：重压缩、改帧延迟、裁尺寸，比 ffmpeg 省一半体积
- `ffmpeg`   转 webp/mp4，抽帧
- Pillow     元数据、逐帧分析、拼图

设计原则：所有函数都能单独调用，不联网，不改原文件（除 `optimize` 显式指定）。
"""
import hashlib
import os
import shutil
import subprocess

from PIL import Image

SURVEY_SAMPLE = 200   # survey 里最多对这么多个 GIF 做逐帧差异检查


# ---------- 探测 ----------

def have(tool):
    return shutil.which(tool) is not None


def probe(path, duration_sample=8):
    """读一个 GIF 的基本信息。不依赖外部工具。

    不遍历全部帧：大 GIF 有 300+ 帧，逐帧 seek 会把 CPU 吃满。帧延迟按
    均匀采样估算，对统计用途足够。
    """
    im = Image.open(path)
    frames = getattr(im, 'n_frames', 1)
    if frames <= duration_sample:
        idxs = range(frames)
    else:
        idxs = sorted({(frames * i) // duration_sample
                       for i in range(duration_sample)})
    durations = []
    for i in idxs:
        im.seek(i)
        durations.append(im.info.get('duration', 0))
    avg = (sum(durations) / len(durations)) if durations else 0
    total = round(avg * frames)
    return {
        'path': path,
        'bytes': os.path.getsize(path),
        'width': im.size[0],
        'height': im.size[1],
        'frames': frames,
        'duration_ms': total,
        'loop': im.info.get('loop', 0),
        'avg_frame_ms': round(total / frames) if frames else 0,
        'animated': frames > 1,
    }


def first_frame_hash(path):
    """首帧内容指纹，用于抓「同一动画不同编码」。"""
    im = Image.open(path)
    im.seek(0)
    return hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()


def frame_hashes(path):
    """全部帧的内容指纹列表。同列表 = 逐帧完全相同。"""
    im = Image.open(path)
    out = []
    for i in range(getattr(im, 'n_frames', 1)):
        im.seek(i)
        out.append(hashlib.md5(im.convert('RGB').tobytes()).hexdigest())
    return out


# ---------- 逐帧差异（判断是否真动画） ----------

def frame_deltas(path, sample=6):
    """相邻采样帧的像素差比例，判断「看着像动图其实静止」。"""
    im = Image.open(path)
    n = getattr(im, 'n_frames', 1)
    if n <= 1:
        return []
    idxs = sorted({(n * i) // sample for i in range(sample)} | {n - 1})
    small = []
    for i in idxs:
        im.seek(i)
        small.append(im.convert('L').resize((32, 32)))
    out = []
    for a, b in zip(small, small[1:]):
        pa, pb = list(a.getdata()), list(b.getdata())
        diff = sum(1 for x, y in zip(pa, pb) if abs(x - y) > 8)
        out.append(round(diff / len(pa), 3))
    return out


# ---------- 优化 ----------

def optimize(src, dst, colors=128, lossy=60, max_width=None):
    """用 gifsicle 重压缩。返回 (dst, 原大小, 新大小)。

    colors 降到 128 通常肉眼无差别但省 30-50%；
    lossy 60 是 gifsicle 的平衡点，再高会出现色块。
    """
    if not have('gifsicle'):
        raise RuntimeError('缺 gifsicle：apt install gifsicle')
    cmd = ['gifsicle', '-O3', '--colors', str(colors),
           '--lossy=' + str(lossy)]
    if max_width:
        cmd += ['--resize-width', str(max_width)]
    cmd += [src, '-o', dst]
    subprocess.run(cmd, check=True, capture_output=True)
    return dst, os.path.getsize(src), os.path.getsize(dst)


def to_webp(src, dst, quality=80):
    """转 webp 动图，通常比 gif 小 60-80%。"""
    if not have('ffmpeg'):
        raise RuntimeError('缺 ffmpeg')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
                    '-loop', '0', '-q:v', str(quality), dst],
                   check=True, capture_output=True)
    return dst, os.path.getsize(src), os.path.getsize(dst)


def to_mp4(src, dst, crf=23):
    """转 mp4（H.264），体积最小但失去透明度。"""
    if not have('ffmpeg'):
        raise RuntimeError('缺 ffmpeg')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
                    '-movflags', '+faststart', '-pix_fmt', 'yuv420p',
                    '-crf', str(crf), dst], check=True, capture_output=True)
    return dst, os.path.getsize(src), os.path.getsize(dst)


# ---------- 拼图预览 ----------

def contact_sheet(paths, dst, cols=8, cell=120, label=True):
    """把一堆 GIF 的首帧拼成一张网格图，用来快速目视检查。"""
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * cell), 'white')
    for i, p in enumerate(paths):
        try:
            im = Image.open(p)
            im.seek(0)
            im = im.convert('RGB')
            im.thumbnail((cell - 4, cell - 4))
            x = (i % cols) * cell + (cell - im.width) // 2
            y = (i // cols) * cell + (cell - im.height) // 2
            sheet.paste(im, (x, y))
        except Exception:
            continue
    sheet.save(dst, quality=85)
    return dst, len(paths)


# ---------- 批量报告 ----------

def survey(root, subdir='stickers', limit=None):
    """扫一个目录，返回统计 + 异常项。"""
    base = os.path.join(root, subdir)
    names = sorted(os.listdir(base))[:limit] if limit else sorted(os.listdir(base))
    items, errors = [], []
    for name in names:
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            continue
        try:
            items.append(probe(path))
        except Exception as e:
            errors.append((name, str(e)))
    if not items:
        return {'count': 0, 'items': [], 'errors': errors}
    total = sum(i['bytes'] for i in items)
    animated = [i for i in items if i['animated']]
    big = sorted(items, key=lambda i: -i['bytes'])[:10]
    # 只抽样检查「静止动画」，全量跑会 OOM（每个 GIF 要解全部帧）
    sample = animated[:SURVEY_SAMPLE]
    static_anim = [i for i in sample
                   if not any(d > 0.01 for d in frame_deltas(i['path']))]
    static_anim_note = (f'（抽样 {len(sample)} 个）'
                        if len(animated) > len(sample) else '')
    return {
        'count': len(items),
        'bytes': total,
        'animated': len(animated),
        'static_animation': len(static_anim),
        'static_animation_note': static_anim_note,
        'avg_bytes': total // len(items),
        'avg_frames': round(sum(i['frames'] for i in items) / len(items), 1),
        'biggest': [{'name': os.path.basename(i['path']), 'bytes': i['bytes'],
                     'frames': i['frames'], 'size': f"{i['width']}x{i['height']}"}
                    for i in big],
        'errors': errors,
    }
