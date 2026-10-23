# 架构

## 开发环境

代码在 instabox 沙箱 `srv` 上开发（4 vCPU / 8 GB / `/data/workspace`），
本地 Termux 只做小改和测试。

为什么不用东京 azure1：那台只有 898 MB 内存，gifsicle 处理大 GIF 会被
OOM killer 杀掉。`srv` 有 8 GB，跑批量优化不会 OOM。

## 依赖方向

```
__main__  (CLI：解析参数，分发 6 个子命令)
   │
   ├─> collect     (给链接的场景：抓取 → 筛选 → 存档)
   │      │
   │      ├─> store    (落盘布局 + 两级去重 + manifest)
   │      ├─> select   (筛选规则，纯函数)
   │      └─> platforms/threads  (平台解析器)
   │                   │
   │                   ├─> net    (HTTP：重试、UA、取字节)
   │                   ├─> page   (从 HTML 挖 SSR JSON)
   │                   └─> media  (URL 分类、扩展名、DASH 合流)
   │
   ├─> pipeline    (不给链接：发现流水线，状态持久化)
   │      └─> discover  (搜索页 + 主页扩散，按时间窗过滤)
   │
   ├─> download    (按发现结果批量下载)
   │      └─> store
   │
   ├─> giftool    (GIF 探测 / 优化 / 转换 / 拼图)
   ├─> optimize   (批量优化，断点续跑)
   │      └─> giftool
   │
   └─> registry    (域名 → 平台名)
```

单向，无循环。每一层都能单独 import 和单测。

## 各层职责

| 模块 | 管什么 | 不管什么 |
|---|---|---|
| `net.py` | 发请求、重试、UA、超时 | 解析、落盘 |
| `page.py` | 从 HTML 里挖 `<script data-sjs>` 的 JSON | 平台字段语义 |
| `media.py` | URL 是否垃圾、扩展名推断、DASH 合流 | 网络、存档 |
| `select.py` | 这次任务要哪些类型（sticker/image/video） | 抓取、落盘 |
| `store.py` | 文件放哪、sha256 去重、manifest 记账 | 抓取、筛选 |
| `collect.py` | 按场景串起三个动作 | 解析细节、落盘细节 |
| `discover.py` | 搜索页 + 主页扩散，按时间窗过滤 | 落盘、下载 |
| `pipeline.py` | 发现状态持久化、多轮扩散、续跑 | 具体抓取逻辑 |
| `download.py` | 按发现结果批量下载贴图 | 发现逻辑 |
| `giftool.py` | GIF 探测、优化、转换、拼图 | 批量调度 |
| `optimize.py` | 批量优化调度、状态、收益门槛 | GIF 具体处理 |
| `platforms/` | 某个站的字段怎么读 | HTTP、落盘 |
| `__main__.py` | 参数解析、子命令分发、输出格式 | 业务逻辑 |

## 输出与日志

库模块不直接 `print`。所有会产生输出的类都接受 `log` 回调：

```python
Pipeline(root, log=print)
Task(targets, root, log=print)
Downloader(root, log=print)
Optimizer(root, log=print)
```

不传就静默。这样测试里可以传 `log=lambda *_: None`，CLI 里传 `print`。

## 两个正交维度

任务范围（`--scene`）和内容种类（`--only`）互不影响。

`select.Select` 是两者的交汇点：scene 决定 `follow_replies` / `follow_profiles`
两个开关，`--only` 决定 `kinds` 集合。`collect.Task` 只读 `Select`，不关心它怎么来的。

```python
Select.stickers_only()          # kinds={'sticker'}, 其余开关默认 True
Select.only('image', 'video')   # kinds={'image','video'}
Select.all()                    # 全都要
```

`Select.useful(rec)` 是唯一的「这条记录值不值得处理」判定，`collect` 在三个地方调它，
保证空记录不会触发无意义的请求。

## 两级去重

都在 `manifest.jsonl` 里记账，每行一个 JSON。

**任务级**（省网络）：每个下载任务有唯一 key，形如 `posts/ABC/sticker_1` 或
`stickers/<giphy_id>`。`Store.done` 集合在启动时从 manifest 恢复，命中就跳过，
一个请求都不发。

**内容级**（省磁盘）：同一份字节（sha256）只落一份。后续出现时 manifest 追加一条
`duplicate_of` 记录指向已有路径。同一个 giphy 贴图被帖子、回复、5 个主页引用时，
磁盘上仍只有一个文件。

效果：同一批链接跑第二遍是秒级，且不产生新文件。

## 表情为什么单独成池

一个 giphy 贴图会被帖子正文、回复、多个主页时间线同时引用。按来源放会出现
`posts/ABC/stickers/ABC_sticker_3_xyz.gif` 和 `profiles/foo/XYZ/stickers/...` 这样的
同名副本散落在各处。

集中到 `stickers/<id>.gif` 后：一个 id 一个文件，文件名即身份，`ls stickers | wc -l`
就是表情总数。

## 并发模型

三层并发，都靠 `ThreadPoolExecutor`：

1. **回复页抓取**（`platforms/threads.py`）：`reply_codes()` 翻出短码后，16 路并发打开
   `/t/{code}`。单页约 3.7s，串行 100 条回复要十几分钟，并发后 2 秒内完成一批。
2. **文件下载**（`collect.Task`）：16 路共享线程池，所有记录的任务汇总后一次性提交。
3. **主页抓取**（`__main__._run_post_scene`）：4 路并发抓评论者主页。

写 manifest 和落盘走 `Store._lock`（RLock），保证 manifest 行不与文件路径错位。

## 为什么用爬虫 UA

匿名访问 Threads 会拿到 JS 登录墙，HTML 里没有媒体地址。换成
`Mozilla/5.0 (compatible; Googlebot/2.1; ...)` 后，Meta 会把整篇帖子服务端渲染进
`<script type="application/json" data-sjs>`，媒体 URL 全在里面。

这个 UA 也是回复页、主页能匿名读取的原因。

## 扩展新平台

1. 写 `mediafetch/platforms/<name>.py`，提供 `post(url)` 和 `profile(handle, limit)`，
   返回统一的记录结构（见下）
2. 在 `registry.PLATFORMS` 登记域名和两个函数
3. 如果该站的页面 JSON 也走 `<script data-sjs>`，直接复用 `page.unique_nodes()`

统一记录结构：

```python
{
  'platform': 'threads',
  'code': 'DduyhhvGWfl',
  'url': 'https://...',
  'author': 'clay_house_2021',
  'media_type': 19,
  'caption': '...',
  'is_reply': False,
  'media': [{'type': 'image'|'video', 'url': ..., 'width': ..., 'height': ...,
             'dash_video': ..., 'dash_audio': ...}],
  'stickers': [{'id': 'giphy_id', 'url': ..., 'sources': [候选地址...]}],
  'quoted': [同结构嵌套],
  'replies': [同结构嵌套],       # 仅 post(reply_media=True) 时有
}
```
