# Hook Studio 本地与线上资源清单

勘察日期：2026-07-10

| 资源 | 状态 | 接入方式 |
| --- | --- | --- |
| AI Video Kernel | 已复用 | FastAPI capability API；图片生成/编辑、视频、理解、上传、probe、抽帧、转码 |
| GPT Image 2 | 真实通过 | Kernel `/capabilities/v1/images/generate` 与 `/capabilities/v1/images/edit`；编辑端点可接原图、可选PNG蒙版和定位图 |
| Seedance / JMAPI | 真实通过 | Kernel `/capabilities/v1/videos/generate`；支持 `image_urls`、`video_urls` 与轮询 |
| 长视频 | 已实现 | Hook Studio 把任意总时长拆成 4-15 秒镜头，逐镜头生成后 Kernel 转码拼接 |
| 内部声音中继 | 真实通过 | `chorify-ai-service` 的 `/v1/tts/speech`，服务端 `X-Internal-Key` |
| OSS | 真实通过 | `oss-imgai.sligenai.cn` / `chorify-imgai` 上传链路；产物与备份使用稳定 URL |
| 公网服务器 | 已部署 | `8.217.134.141`，systemd + Nginx HTTPS，应用监听 `127.0.0.1:8011` |
| 视频平台 Crawler | 已接入 | YouTube、TikTok、Douyin、Bilibili gateway；服务端 key，解析后重新持久化到 OSS |
| FFmpeg | 已验证 | 公网服务器 FFmpeg 5.1.9；用于音轨替换与区间回拼 |
| 规则/skill 资产 | 已蒸馏 | 首帧导演、故事板、Seedance 引用对齐、长提示词、参控锁定、编辑循环 |
| 图片路由 Skill | 已部署 | 项目自有 `hook-studio-image-router`；吸收已审计官方/社区经验，不安装第三方运行时依赖 |
| 登录封面 | 已本地化 | 3 张 Unsplash 合法来源图片，本地静态托管，见 `frontend/public/login/ATTRIBUTION.md` |

## Kernel 可复用能力

- `POST /capabilities/v1/images/generate`
- `POST /capabilities/v1/images/edit`
- `POST /capabilities/v1/videos/generate`
- `GET /capabilities/v1/videos/jobs/{id}`
- `POST /capabilities/v1/media/probe`
- `POST /capabilities/v1/media/extract-frame`
- `POST /capabilities/v1/media/transcode`
- `POST /capabilities/v1/storage/upload`
- `POST /capabilities/v1/understand/evaluate`

所有调用均由服务端 adapter 发起，带 request ID、幂等键、超时和一次自动重试。前端没有 Kernel、JMAPI、TTS、Crawler 或 OSS 密钥。

## 已知边界

- Seedance 单次片段仍受 provider 4-15 秒能力约束；Hook Studio 通过分段和拼接支持 60 秒及更长总片长。
- 图片原生蒙版编辑是 best effort；严格保持蒙版外内容依靠服务端把源图像素回填到最终结果。
- 定位文字、箭头、矩形和圈选仅用于解释位置，既不是必填项，也不等价于蒙版。
- Kernel 当前没有统一的 `audio_urls` 生成槽位；换声改走内部 TTS + FFmpeg，已经真实通过。
- 定向替换不是像素级遮罩编辑：先让 Seedance 参考源视频和替换图重绘目标区间，再回拼源视频。
- 平台链接解析依赖 Crawler 可用性；普通公开 HTTP(S) 文件链接仍可直接安全下载并持久化。
- 5090 长文本服务曾出现超时，本项目不把它作为关键依赖；规划和逆向使用 Kernel Understand。
