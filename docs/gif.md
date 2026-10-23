# GIF 处理

三类操作：体检、优化、转换。实现在 `mediafetch/giftool.py`，
批量优化在 `mediafetch/optimize.py`。

## 依赖

| 工具 | 用途 | 装法 |
|---|---|---|
| Pillow | 读帧、元数据、拼图 | `pip install pillow` / `pkg install python-pillow` |
| gifsicle | GIF 专用重压缩 | `apt install gifsicle` / `pkg install gifsicle` |
| ffmpeg | 转 webp/mp4 | `apt install ffmpeg` / `pkg install ffmpeg` |

只有 `optimize()` 需要 gifsicle，`to_webp()` / `to_mp4()` 需要 ffmpeg，
其余全部只用 Pillow。

## 体检

```bash
python3 -m mediafetch gif ~/stickers
```

输出示例（7604 个真实贴图）：

```
文件 300 个，共 421 MB，平均 1438 KB / 27.1 帧
动图 300，看着像动图其实静止 7（抽样 200 个）

最大的 10 个：
  28110 KB  150 帧   1080x1080  1INcU18XaoLmd8pMJK.gif
  23557 KB  100 帧   2160x2160  3FQfBGTKXfiGItzySs.gif
  16898 KB   24 帧   3500x3500  1r6dnFTyiDjPUzwmzU.gif
  ...
```

**注意 `probe()` 不遍历全部帧**：大 GIF 有 300+ 帧，逐帧 seek 会把 CPU
吃满（实测 3923 个文件跑 10 分钟不结束）。帧延迟按 8 帧均匀采样估算。

## 优化（gifsicle）

```python
from mediafetch import giftool
giftool.optimize('in.gif', 'out.gif', colors=128, lossy=60, max_width=1024)
```

三个参数的作用：

| 参数 | 默认 | 效果 |
|---|---|---|
| `colors` | 128 | 降到 128 色通常肉眼无差别，省 30-50% |
| `lossy` | 60 | gifsicle 的平衡点，再高出现色块 |
| `max_width` | None | 限制宽度，巨型 GIF 最有效 |

**实测**（20 个真实贴图，61 MB）：

| 方案 | 结果 | 省 |
|---|---|---|
| gifsicle colors=128 lossy=60 | 61 MB → 45 MB | 25% |
| ffmpeg → webp q=80 | 61 MB → 21 MB | **64%** |

批量优化 100 个大文件（1.5 GB）：成功 67 个、跳过 33 个，省 568 MB（**56%**）。

## 批量优化

```bash
# 通过 Python API（CLI 未暴露，因为要控制并发和内存）
python3 -c "
import sys; sys.path.insert(0, '.')
from mediafetch.optimize import Optimizer
o = Optimizer('~/stickers', workers=3)
o.run()
print(o.summary())
"
```

规则：

1. **永不覆盖原文件**：结果写 `optimized/`，原图留 `stickers/`
2. 省不到 15% 就删掉结果（原图更保真）
3. 状态写 `optimize.json`，中断可续跑
4. 按体积降序处理，先拿收益最大的

### 内存陷阱

`MAX_BYTES = 20 MB`：gifsicle 处理一个 GIF 要吃掉同等量级的内存。

实测在 898 MB 的东京 VM 上处理 84 MB 的文件，进程被 OOM killer 杀掉。
现在开发机是 instabox `srv`（8 GB），`workers=4` 跑 84 MB 文件没问题。

在内存小的机器上：`MAX_BYTES` 降到 10 MB，`workers` 降到 3。

## 转 webp

```python
giftool.to_webp('in.gif', 'out.webp', quality=80)
```

省 64%，但**失去 GIF 的通用性**：微信、Telegram 等平台对 webp 动图的支持
不一致。贴图池建议保留 gif，只在需要发布到网页时转 webp。

## 逐帧分析

```python
giftool.frame_deltas(path)    # 相邻采样帧的像素差比例
giftool.frame_hashes(path)    # 每帧的内容 md5
giftool.first_frame_hash(path) # 首帧内容指纹
```

`frame_deltas` 用来识别「看着像动图其实静止」的文件（所有差值 < 0.01）。
实测 7604 个贴图里约 3.5% 是这种。

**警告**：这三个函数都会解码全部帧，对单个文件调用没问题，批量扫描会 OOM。
`survey()` 里只抽样 200 个。

## 拼图预览

```python
giftool.contact_sheet(paths, 'sheet.jpg', cols=8, cell=120)
```

把一堆 GIF 的首帧拼成网格，用来快速目视检查抓取质量。

## 为什么不用 imagehash

`imagehash` 的 4 种算法（ahash/dhash/phash/whash）都走灰度，看不见颜色。
实测「同一图案换配色」（橙花 vs 粉花）距离为 0，被判成重复。

装它也不容易：依赖 `numpy` + `scipy` + `PyWavelets`，Termux 上
`pip install imagehash` 因 PyWavelets 编译失败而失败（`--no-deps` 可绕过，
但那样只能用 ahash/dhash/phash，没有 whash）。

如果要做近重复检测，见 `docs/dedup.md`（待写）。
