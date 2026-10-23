# mediafetch

公开社媒页面的媒体抓取工具。当前支持 **Threads**（图片 / 视频 / carousel /
inline 贴图 GIF），平台按插件组织，后续可加别的站点。

无第三方依赖，Python ≥ 3.9。

## 安装

```bash
git clone <repo> && cd mediafetch
pip install -e .        # 可选，装了就有 mediafetch 命令
```

不装也能直接跑 `python3 -m mediafetch`。

## 六种用法

```bash
# 1. 只看不存
python3 -m mediafetch list "https://www.threads.com/share/XXXX/" --replies

# 2. 平铺下载（老用法）
python3 -m mediafetch get "https://www.threads.com/share/XXXX/" --dl --out ./out

# 3. 规范存档（推荐）
python3 -m mediafetch archive URL [URL...] --archive ~/my-archive \
    --scene full --only sticker

# 4. 自动发现最近 N 天带贴图的帖子（不需要给链接）
python3 -m mediafetch discover ~/work --days 30 --target 9000

# 5. 按发现结果下载
python3 -m mediafetch fetch ~/work --archive ~/stickers

# 6. GIF 体检
python3 -m mediafetch gif ~/stickers
```

## 自动发现

不给链接，自己去找。搜索页 → 抽作者 → 作者主页 → 再抽作者，多轮扩散，
按时间窗过滤。

实测：37 个关键词 + 9 轮扩散（3.7 万个主页）→ 7608 帖 / 16764 个贴图引用
→ 去重后 **7604 个唯一贴图**，99.9% 在 30 天内。

详见 `docs/discovery.md`。

## 两个正交的维度

任务范围由 **--scene** 决定，内容种类由 **--only** 决定，两者自由组合。

### --scene：抓多大范围

| 场景 | 帖子 | 回复 | 作者主页 | 评论者主页 |
|---|---|---|---|---|
| `posts` | ✅ | ❌ | ❌ | ❌ |
| `threads` | ✅ | ✅ | ❌ | ❌ |
| `full`（默认） | ✅ | ✅ | ✅ | ✅ |
| `profiles` | ❌ | ❌ | ✅ | ❌ |

### --only：要哪些内容

| 值 | 说明 |
|---|---|
| `sticker` | 只要表情 gif，图片视频一律不下载 |
| `media` | 只要图片和视频 |
| `all`（默认） | 全都要 |
| `image,video` | 逗号组合任意子集 |

## 目录结构

```
<root>/
  manifest.jsonl        每份内容一行：sha256 / 路径 / 出处
  index.json            本次任务摘要：场景、筛选、各项数量、失败数
  stickers/             表情池，文件名就是 giphy id
    <sticker_id>.gif
  posts/<code>/
    post.json           帖子元数据
    images/  videos/
    replies/<code>/
      reply.json
      images/  videos/
  profiles/<handle>/
    profile.json        该账号时间线元数据
    posts/<code>/
      images/  videos/
```

**为什么表情单独成池**：同一个 giphy 贴图会被帖子、回复、多个主页反复引用。
按来源放会散成一堆同名副本；集中后一个 id 一个文件，一眼能数清总数。

## 去重

两级，都在 `manifest.jsonl` 里记账：

1. **任务级**（省网络）：每个任务有唯一 key（如 `posts/ABC/sticker_1`）。
   续跑时命中 key 直接跳过，不发请求。
2. **内容级**（省磁盘）：同一 sha256 只落一份，后续出现只追加一条
   `duplicate_of` 记录，指向已有文件。

跑第二遍同一批链接是秒级，且不会产生新文件。

## 模块划分

```
mediafetch/
  net.py        HTTP：重试、UA、取字节。不含平台知识
  page.py       从 HTML 挖服务端渲染 JSON。平台无关
  media.py      URL 分类、扩展名、DASH 合流。不碰网络
  select.py     筛选规则：这次任务要哪些类型。纯函数
  store.py      落盘布局 + 两级去重 + manifest
  collect.py    编排：抓取 → 筛选 → 存档（给链接的场景）
  discover.py   发现：搜索页 + 主页扩散，按时间窗过滤
  pipeline.py   发现流水线：状态持久化、多轮扩散、续跑
  download.py   批量下载：按发现结果下贴图，24 路并发
  giftool.py    GIF 体检 / 优化 / 转 webp / 拼图
  optimize.py   批量优化：断点续跑、收益门槛、内存保护
  __main__.py   CLI：list / get / archive / discover / fetch / gif
  platforms/    平台解析器，每个平台一个文件
```

依赖方向单向无循环：

```
__main__ → {collect, pipeline, download, giftool}
collect  → {store, select, platforms}
pipeline → discover
download → store
platforms → {net, page, media}
```

每个模块都能单独 import 和单测。

## 测试

```bash
python3 tests/run.py
```

61 个用例，不联网，用固定页面片段和合成 GIF 验证逻辑：

```bash
python3 tests/run.py
```

覆盖：解析（threads）、筛选（select）、落盘去重（store）、媒体工具（media）、
发现过滤（discover）、流水线状态（pipeline）、下载（download）、
GIF 处理（giftool）、优化器（optimize）。

## 文档

| 文件 | 内容 |
|---|---|
| `docs/usage.md` | 场景手册：按「我想干什么」组织的命令清单 |
| `docs/architecture.md` | 架构：模块职责、依赖方向、去重机制、扩展新平台 |
| `docs/discovery.md` | 自动发现：为什么不能调接口、扩散曲线、状态文件 |
| `docs/gif.md` | GIF 处理：体检、优化、转 webp、内存陷阱 |
| `docs/comparison.md` | 与 yt-dlp / gallery-dl / threads-cli 的实测对比 |
| `CHANGELOG.md` | 版本变更记录 |

## 已知限制

| 限制 | 原因 |
|---|---|
| 主页只到首屏（约 50 帖） | Threads 无公开的主页翻页接口 |
| 回复翻页上限默认 10 页 | 每页一次 GraphQL 请求 |
| 搜索/主页不可翻页 | 匿名 GraphQL 被拦，只能解析页面 | 每词一页、每人 ~50 帖 |
| 扩散效率递减 | 97% 的作者主页没贴图 | 到 5000 贴图后每轮只增 500-1000 |
| 无代理支持 | 当前走直连，`net.py` 是唯一改点 |
| 视频合流需 ffmpeg | 缺 ffmpeg 时退回 progressive mp4（较低码率） |
| 大目录体检慢 | `survey()` 要逐文件解码首帧，7604 个约 3 分钟 |
| 依赖爬虫 UA | 换普通 UA 会拿到 JS 登录墙 |

## 许可

MIT
