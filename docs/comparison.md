# 方案对比（2026-10，东京 VM 实测）

测试集：5 个真实帖子，覆盖所有媒体类型。

| 编号 | 帖子 | 类型 |
|---|---|---|
| P1 | `@zhongjie397/post/Der57TeE20g` | 纯 inline 贴图 ×37 |
| P2 | `@natgeo/post/Dej74BIESJL` | carousel ×6 图 |
| P3 | `@natgeo/post/Dej70-sEaDp` | 单图 |
| P4 | `@natgeo/post/DerqevDDeVV` | 单视频 |
| P5 | `@threads/post/DOOf4LNgJhs` | 文字 + 1 图 |

## 结果

| 工具 | P1 | P2 | P3 | P4 | P5 | 账号时间线 |
|---|---|---|---|---|---|---|
| mediafetch | 37/37 贴图 | 6/6 图 1440×960 | 1/1 | 1/1 视频 | 1/1 | ✅ |
| yt-dlp + yt-dlp-threads 0.1.0 | 报错 no video | 报错 no videos | 报错 image post | ✅ 3 码流 | 报错 | ❌ |
| gallery-dl 1.32.17 | Unsupported URL | 同左 | 同左 | 同左 | 同左 | ❌ |
| tamnd/threads-cli 0.1.1 | Not found | Not found | Not found | Not found | Not found | ⚠️ 150×150 |

## 各工具细节

**yt-dlp-threads**（本机 pip 已装，`Extractor Plugins: ThreadsIE`）
- 与 mediafetch 同源的 Googlebot 思路，但只解析 `video_versions`，明确不支持图片
- 视频确实能出 3 个 DASH 码流（含音轨分离），比 mediafetch 的单 mp4 更细
- `th post` 类命令对图片/carousel 直接报错退出

**gallery-dl 1.32.17**
- 完全没有 Threads extractor，`--list-extractors` 里只有 4chan 系的 Thread
- 上游 issue mikf/gallery-dl#4281 自 2023-07 起 open

**tamnd/threads-cli 0.1.1**（Go，单二进制）
- `th profile` / `th feed` 可用，但 `media_urls` 带 `stp=...s150x150`，是缩略图
- `th post` 对测试的 5 个帖子全部 `Not found`
- `th search` 报 `Graphql returned an unexpected shape (doc_id may be stale)`
- 价值在元数据（作者、互动数、时间），不在媒体

**threadssticker.com**（第三方在线站，作为接口参考）
- `GET /api/parse?url=<threads链接>` → `{media:[{url,type}], post:{title,desc}, parser:"self_http_v4"}`
- `GET /api/media?url=<CDN|giphy>&download=1&name=x` → 代理下载，白名单限 ig CDN + giphy
- 无鉴权、无 rate limit（连发 6 次全 200）
- **坑**：部分图片帖它返回 150×150 缩略图；mediafetch 取 `width` 最大的候选，同帖拿到 1440×960

## 结论

没有现成项目能覆盖 Threads 的全部媒体类型。图片和 inline 贴图必须自己解析页面载荷，
故 mediafetch 自建；视频场景若需要 DASH 分轨，可另外调 yt-dlp 补充。

## 2026-10 追加：回复 / 引用 / 翻页

用 `share/_mh6deE_V/`（串文，声称 160 条回复）实测。

| 能力 | 结果 |
|---|---|
| 首屏回复 | 13 条，其中 3 条带媒体 |
| GraphQL 翻页 | 能翻到第 2 页，累计约 20 条 |
| 翻页 node 的媒体 | `image_versions2.candidates` 为空，需逐条打开 `/t/{code}` |
| 引用块媒体 | ✅ 完整，实测 4096×4096 原图 |
| 回复里的贴图 | ✅ 正常 |

关键参数：
- cursor 取 `data.media.text_post_app_info.direct_replies.page_info.end_cursor`
- `sortOrder` 必须 `RECENT`（`TOP` 只有 6 条且 cursor 走不下去）
- `doc_id` 和 `LSD` 从页面 `data-sjs` 的 preloader 里取，每个帖子可能不同

第三方站 `threadsdownloader.com` 已停服：`api-tp.threadsdownloader.com/threads/post/media`
对任何 id 都返回 `threadsdownloader-nolongerworks.png`。
