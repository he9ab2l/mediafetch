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

# 连回复一起（页面首屏可见的那部分）
python3 -m mediafetch "<url>" --replies --dl --out ./out

# 抓账号时间线里带媒体的帖子
python3 -m mediafetch "@zhongjie397" --dl --out ./out --limit 20

# 机器可读
python3 -m mediafetch "https://www.threads.com/@natgeo/post/DerqevDDeVV" --json
```

链接形式都认：`/@user/post/CODE`、`/t/CODE`、`/share/XXXX/`。

输出文件名：`{code}_{n}.{jpg|mp4|webp}`、`{code}_sticker_{n}_{giphyId}.gif`。

## 原理

1. 普通浏览器 UA 访问 Threads 只会拿到 JS 登录墙，HTML 里 0 个媒体 URL。
2. 换成爬虫 UA（`Googlebot`）后，Meta 会把整篇帖子服务端渲染进
   `<script type="application/json" data-sjs>`。
3. 递归找出带 `code` + `image_versions2`/`video_versions`/`carousel_media` 的节点，
   **用短码匹配目标帖**——不能取「页面第一个视频」，那通常是推荐内容。
4. inline 贴图不在媒体字段里：走 `text_post_app_info.text_fragments[].inline_sticker_fragment`
   拿 `sticker_id`，下载用 `https://i.giphy.com/{id}.gif`。
5. 图片取 `candidates` 里 `width` 最大的一项，跳过头像和 `s150x150` 缩略图
   （第三方站有直接返回 150×150 的 bug）。

## 已知限制

1. **回复只有页面首屏**：Meta 只把前十几条回复渲染进载荷，其余要 GraphQL 翻页
   （`BarcelonaPostPageDownwardQuery` 的 `doc_id` 频繁更换）。`--replies` 会打印
   `已取/声称总数`，例如 `11/26`，别把 11 当全部。
2. 账号模式同样只到首屏（约 18 帖），原因相同。
3. 只能抓公开帖子；私号即使爬虫 UA 也拿不到。
4. 唯一脆弱点：Meta 若停止给爬虫 UA 全量渲染，抓取会失效。

## 加新平台

1. 写 `mediafetch/platforms/<name>.py`，导出 `post(url)` 和 `profile(handle, limit)`，
   返回记录结构见 `mediafetch/platforms/threads.py::_record`。
2. 在 `mediafetch/registry.py` 的 `PLATFORMS` 里登记域名与两个函数。

## 许可

MIT
