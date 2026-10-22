# 场景手册

按「我想干什么」组织，每条给可直接复制的命令。

---

## 只要表情

```bash
python3 -m mediafetch archive URL... --archive ~/stickers --scene full --only sticker
```

`--scene full` 会连帖子作者、回复、回复者主页一起扫，表情来源最全。
`--only sticker` 保证图片视频一律不下载。

只要帖子和回复里的（不碰主页）：

```bash
python3 -m mediafetch archive URL... --archive ~/stickers --scene threads --only sticker
```

只要帖子正文的（最快，一次请求一帖）：

```bash
python3 -m mediafetch archive URL... --archive ~/stickers --scene posts --only sticker
```

**时间估计**：`posts` 约 3 秒/帖；`threads` 约 10 秒/帖；`full` 约 30-60 秒/帖
（取决于回复数和评论者主页数量）。

---

## 只要图片和视频

```bash
python3 -m mediafetch archive URL... --archive ~/media --scene threads --only media
```

`--only media` 等价于 `--only image,video`。

---

## 全都要

```bash
python3 -m mediafetch archive URL... --archive ~/all
```

不写 `--only` 就是 `all`。

---

## 先看一眼再决定

不下载，只列清单：

```bash
python3 -m mediafetch list "https://www.threads.com/share/XXXX/" --replies
```

输出每帖的 code、作者、媒体数、贴图数，以及每个媒体/贴图的 URL 或 id。

---

## 抓某个账号的主页

```bash
python3 -m mediafetch archive @handle --archive ~/profiles --scene profiles --only sticker
```

或直接 `list` 看有什么：

```bash
python3 -m mediafetch list @handle --limit 100
```

Threads 没有公开的主页翻页接口，只到首屏（约 50 帖，`--limit` 控制上限）。

---

## 追加抓取（续跑）

同一批链接再跑一次，或者加了新链接：

```bash
python3 -m mediafetch archive OLD_URL... NEW_URL... --archive ~/stickers --scene full --only sticker
```

已下载过的内容按 manifest 里的 key 跳过，不发请求。只抓新增部分。

**不要换 `--archive` 目录**，否则 manifest 不共享，会重复下载。

---

## 平铺下载（老用法）

不要分目录结构，全放一个文件夹：

```bash
python3 -m mediafetch get "URL" --dl --out ./out --only sticker
```

---

## 清理与维护

**看当前存档状态**：

```bash
cat ~/stickers/index.json          # 上次任务的摘要
wc -l ~/stickers/manifest.jsonl    # 记录总数
ls ~/stickers/stickers | wc -l     # 表情总数
du -sh ~/stickers                  # 磁盘占用
```

**检查完整性**（manifest 记录是否都指向存在的文件）：

```bash
cd ~/stickers && python3 -c "
import json, os
rows = [json.loads(l) for l in open('manifest.jsonl')]
miss = [r['path'] for r in rows if r.get('path') and not os.path.exists(r['path'])]
print('失效引用:', len(miss))
"
```

**只删某类内容**（比如只留表情）：

```bash
cd ~/stickers && python3 -c "
import json, os
rows = [json.loads(l) for l in open('manifest.jsonl')]
keep = [r for r in rows if r.get('kind') == 'sticker']
drop = {r['path'] for r in rows if r.get('kind') in ('image', 'video') and r.get('path')}
keep_paths = {r['path'] for r in keep if r.get('path')}
for p in drop - keep_paths:
    os.path.exists(p) and os.remove(p)
with open('manifest.jsonl', 'w') as f:
    for r in keep:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
"
```

---

## 从 v1 散放结构迁移

老版本把文件放在 `<来源>/<code>/stickers/<code>_sticker_N_<id>.gif`，散在几十个目录里。
迁移到单一表情池：

```bash
python3 scripts/migrate_flat.py ~/old-archive ~/new-archive
```

不联网，只搬文件 + 重写 manifest。源目录原样保留。

---

## 已知限制

| 限制 | 原因 |
|---|---|
| 主页只到首屏（约 50 帖） | Threads 无公开的主页翻页接口 |
| 回复翻页上限 `--reply-pages`（默认 10） | 每页一次 GraphQL 请求，太多会慢 |
| 无代理支持 | 当前走直连；`net.py` 是唯一改点 |
| 视频需要 ffmpeg 才能合 DASH 分轨 | 缺 ffmpeg 时退回 progressive mp4（较低码率） |
| 依赖爬虫 UA | 换普通 UA 会拿到 JS 登录墙 |
