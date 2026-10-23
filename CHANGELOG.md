# 更新日志

## 0.3.0 — 2026-10-23

自动发现 + 批量抓取 + GIF 处理。在东京服务器（Debian 13，2 vCPU / 898 MB）上
开发验证。

### 新增

- **`discover` 子命令**：不给链接也能抓。37 个多语言关键词搜索 → 抽作者 →
  作者主页扩散 → 再抽作者，多轮直到贴图数达标或作者池耗尽
- **`fetch` 子命令**：按发现结果批量下载贴图，24 路并发
- **`gif` 子命令**：贴图池体检（体积、帧数、尺寸、静止动画占比）
- **`pipeline.py`**：发现状态持久化到 `discover.json`，中断可续跑
- **`giftool.py`**：探测、逐帧差异、gifsicle 优化、转 webp/mp4、拼图预览
- **`optimize.py`**：批量优化，断点续跑，收益 <15% 自动回滚，20MB 上限防 OOM
- `docs/discovery.md`、`docs/gif.md`

### 实测数据

在东京服务器上跑出的真实结果：

| 项 | 值 |
|---|---|
| 关键词 | 37 个（英中日韩） |
| 扩散轮次 | 9 轮 |
| 抓过的主页 | 36,998 个 |
| 发现帖子 | 7,608 帖 |
| 贴图引用 | 16,764 个 |
| **去重后唯一贴图** | **7,604 个** |
| 总大小 | 13.6 GB |
| 时间窗合规 | 99.9% 在 30 天内，71% 在 7 天内 |
| 耗时 | 约 70 分钟 |

GIF 优化实测：100 个大文件（1.5 GB）→ 成功 67 个，省 568 MB（56%）。
转 webp 省 64%，但失去 GIF 通用性。

### 关键技术发现

1. **搜索和主页的 GraphQL 匿名调用返回 HTML 登录墙**，只有回复翻页
   （`BarcelonaPostPageDownwardQuery`）在部分 IP 上可用。发现只能靠解析
   服务端渲染的页面。
2. **搜索页 `page_info.has_next_page` 恒为 false**，无法翻页。每个关键词
   只有一页（20-55 帖）。
3. **扩散效率随轮次递减**：第 1 轮 +3801 贴图，第 7 轮只 +837。因为
   97% 的作者主页没有贴图。
4. **`probe()` 不能遍历全部帧**：3923 个文件逐帧 seek 跑 10 分钟不结束。
   帧延迟改 8 帧采样估算。
5. **gifsicle 吃等量内存**：898 MB 机器上处理 84 MB 的 GIF 会被 OOM killer
   杀掉。加 20 MB 上限 + 3 路并发。

### 修复

- `Discoverer.lock_guard()` 是假锁（`nullcontext`），并发下 `stats` 竞态。
  计数移到主线程的 `ex.map` 消费端。
- `download.py` 调 `store._write` 私有方法，重复实现下载逻辑。
  改为 `store.save_sticker(sticker, source)`。
- `_is_post()` 在 `__main__` 和 `collect` 里重复定义，合并为
  `collect.is_post_url()`。
- `_flat()` 每次循环都 `Store(outdir)`，重读整个 manifest。改为调用方复用。

---

## 0.2.0 — 2026-10-23

模块拆分 + 规范存档 + 两级去重。

### 新增

- **三个子命令**：`list`（只看）、`get`（平铺下载）、`archive`（规范存档）
- **`--scene`**：`posts` / `threads` / `full` / `profiles`，控制抓取范围
- **`--only`**：`sticker` / `media` / `all` / 任意逗号组合，控制内容种类
- **表情池**：所有 gif 集中到 `stickers/<giphy_id>.gif`，一个 id 一个文件
- **两级去重**：任务级（省网络，命中 key 不发请求）+ 内容级（省磁盘，sha256 去重）
- **`index.json`**：每次任务摘要，场景、筛选、各项数量、失败数
- **`manifest.jsonl`**：每份内容一行，含 sha256、路径、出处、duplicate_of
- `scripts/migrate_flat.py`：从 v1 散放结构迁移
- `scripts/run-stickers.sh`：常用组合的包装脚本
- `docs/architecture.md`、`docs/usage.md`

### 重构

原 `core.py` 混了 HTTP、解析、下载、合流四件事，拆成四个模块：

| 原位置 | 新位置 |
|---|---|
| `core.fetch` / `core.download` | `net.py` |
| `core.sjs_objects` / `walk_media_nodes` / `unique_posts` | `page.py` |
| `core.biggest_image` / `guess_ext` / `merge_av` | `media.py` |
| `archive.py`（v1 内部实现） | `store.py` |
| `collect.py`（v1 混了筛选） | `collect.py` + `select.py` |

依赖方向单向无循环：`__main__` → `collect` → {`store`, `select`, `platforms`}，
`platforms` → {`net`, `page`, `media`}。

### 性能

- 回复页抓取并发（16 路）：单帖 100+ 回复从 26s 降到 11s
- 所有下载共用一个线程池：1 帖 + 15 主页从 120s 降到 46s
- 任务级去重：同一批链接重跑从 46s 降到 16s
- 实测 10 帖 + 74 主页 + 2063 文件共 7 分钟，0 失败

### 修复

- `Store._write` 写成功时没把 key 加进 `done` 集合，导致续跑时重下
- `merge_av` 先把合流结果写到磁盘再读回来删掉，改成直接返回字节
- `net.fetch` 无重试，并发下 SSL EOF 会断掉整条回复链
- 单个下载失败会中断整个任务，改成记录到 `failures` 继续

### 移除

- `mediafetch/core.py`（拆分）
- `tests/test_cli.py`（`Seen` 类已随 v1 存档逻辑一起移除）

---

## 0.1.0 — 2026-10-20

首个版本。

- Threads 单帖解析：图片、视频、carousel、inline 贴图、引用块
- 回复首屏 + GraphQL 翻页
- 账号时间线（首屏）
- 爬虫 UA 绕登录墙
- DASH 分轨合流（需 ffmpeg）
- 18 个离线单测
