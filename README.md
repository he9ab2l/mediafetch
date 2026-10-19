# mediafetch

公开社媒页面的媒体抓取工具。当前支持 **Threads**（图片 / 视频 / carousel / inline 贴图 GIF），
平台按插件组织，后续可加别的站点。

## 为什么不用现成工具

2026-10 在东京 VM 上对同一批帖子实测（详见 `docs/comparison.md`）：

| 工具 | 图片 | 视频 | carousel | inline 贴图 | 账号时间线 |
|---|---|---|---|---|---|
| **mediafetch** | ✅ 原图 | ✅ | ✅ | ✅ | ✅ |
| yt-dlp + yt-dlp-threads | ❌ | ✅ | ❌ | ❌ | ❌ |
| gallery-dl 1.32.17 | ❌ 不支持 Threads | ❌ | ❌ | ❌ | ❌ |
| tamnd/threads-cli | ❌ | ❌ | ❌ | ❌ | ⚠️ 只有 150×150 缩略图 |

gallery-dl 的 Threads 支持 issue（#4281）仍 open，yt-dlp 官方 extractor PR（#13512）被标 blocked。

## 安装

```bash
git clone https://github.com/he9ab2l/mediafetch.git
cd mediafetch
pip install -e .        # 可选，装了就有 mediafetch 命令
```

无第三方依赖，Python ≥ 3.9 即可。不装也能直接跑 `python3 -m mediafetch`。

## 用法

```bash
# 看媒体清单（不下载）
python3 -m mediafetch "https://www.threads.com/@natgeo/post/Dej74BIESJL"

# 下载单帖
python3 -m mediafetch "https://www.threads.com/share/BAHAMIdLaB/" --dl --out ./out

# 连回复一起（含 GraphQL 翻页 + 引用块，逐条取媒体，较慢）
python3 -m mediafetch "<url>" --replies --dl --out ./out
python3 -m mediafetch "<url>" --replies --reply-pages 10   # 控制翻页上限

# 抓账号时间线里带媒体的帖子
python3 -m mediafetch "@zhongjie397" --dl --out ./out --limit 20

# 机器可读
python3 -m mediafetch "https://www.threads.com/@natgeo/post/DerqevDDeVV" --json
```

链接形式都认：`/@user/post/CODE`、`/t/CODE`、`/share/XXXX/`。

输出文件名：`{code}_{n}.{jpg|mp4|webp}`、`{code}_sticker_{n}_{giphyId}.gif`。

同一媒体 URL 和同一 giphy 贴图 id 会跨记录去重（回复与它的引用块常指向同一条帖子），
重复项打印 `(重复，已跳过)`。

## 原理

1. 普通浏览器 UA 访问 Threads 只会拿到 JS 登录墙，HTML 里 0 个媒体 URL。
2. 换成爬虫 UA（`Googlebot`）后，Meta 会把整篇帖子服务端渲染进
   `<script type="application/json" data-sjs>`。
3. 递归找出带 `code` + `image_versions2`/`video_versions`/`carousel_media` 的节点，
   **用短码匹配目标帖**——不能取「页面第一个视频」，那通常是推荐内容。
4. inline 贴图不在媒体字段里：走 `text_post_app_info.text_fragments[].inline_sticker_fragment`
   拿 `sticker_id`，下载优先 `media.giphy.com/media/{id}/source.gif`（原图），
   回退 `i.giphy.com/{id}.gif`。
5. 引用/转发：`text_post_app_info.share_info.quoted_post` / `reposted_post`
   自带完整媒体字段，能拿到 4096×4096 原图。
6. 回复翻页：`POST https://www.threads.com/api/graphql`，`doc_id` 和 `LSD`
   从页面 preloader 里取。cursor 必须用
   `data.media.text_post_app_info.direct_replies.page_info.end_cursor`，
   `sortOrder` 设 `RECENT`（`TOP` 的 cursor 走不下去）。翻页返回的 node
   媒体字段是空的，要逐条打开 `/t/{code}` 才能取到。
7. 图片取 `candidates` 里 `width` 最大的一项，跳过头像和 `s150x150` 缩略图
   （第三方站有直接返回 150×150 的 bug）。
8. 视频优先 DASH 合流：从 `video_dash_manifest` 里取码率最高的视频轨 + 音频轨，
   分别下载后用 ffmpeg `-c copy` 合成 mp4。没有 ffmpeg 时回退 progressive mp4。
   实测 progressive 与 DASH 轨是同一份编码，字节数差 146B；但 DASH 能确认拿到最高码率轨，
   且视频帖的 `image_versions2` 只是封面帧（640 宽），不能当视频本体。

## 已知限制

1. **回复覆盖不全**：翻页实测只能走到第 2 页左右，一个 160 回复的串文能取到约 20 条。
   `--replies` 会打印 `已取/声称总数`，例如 `18/160`，别把 18 当全部。
2. **账号时间线翻不了**：`BarcelonaProfileThreadsTabDirectQuery` 返回
   `has_next_page: false`，`first=15/30/50` 都无效。只能拿首屏约 26 帖。
3. 只能抓公开帖子；私号即使爬虫 UA 也拿不到。
4. 唯一脆弱点：Meta 若停止给爬虫 UA 全量渲染，抓取会失效。

## 加新平台

1. 写 `mediafetch/platforms/<name>.py`，导出 `post(url)` 和 `profile(handle, limit)`，
   返回记录结构见 `mediafetch/platforms/threads.py::_record`。
2. 在 `mediafetch/registry.py` 的 `PLATFORMS` 里登记域名与两个函数。

## 许可

MIT
