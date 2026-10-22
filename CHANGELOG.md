# 更新日志

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
