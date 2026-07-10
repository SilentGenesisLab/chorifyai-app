# Hook Studio Chat OS v2 真实验收

时间：2026-07-10（UTC+8）  
环境：公网 HTTPS + 生产 Kernel + GPT Image 2 + Seedance + TTS + FFmpeg

## 公网和安全

- 公网页面：HTTP 200。
- 健康探针：`status=ok`。
- 无码访问工作区 API：HTTP 401。
- systemd：`active`、`enabled`，仅监听服务器回环地址，由 Nginx HTTPS 路径代理。
- 前端密钥扫描：PASS；Provider、TTS、Crawler 密钥仅在 `/etc/hook-studio/hook-studio.env`。

## 真实模块结果

| 工具 | 结果 | 证据摘要 |
| --- | --- | --- |
| 图片生产 | PASS | GPT Image 2 返回稳定 OSS PNG |
| 视频生产 | PASS | 故事板确认后 Seedance 生成，拼接并通过视频轨/时长 QC |
| 逆向分析 | PASS | 视频 probe、关键帧、Kernel Understand 结构化结果入库 |
| 参控复刻 | PASS | 源视频结构参考 + 产品图片身份锁定，成片 QC 通过 |
| 批量生产 | PASS | 同一任务返回 3 个独立 MP4，3/3 QC 通过 |
| 定向替换 | PASS | Seedance 定向重绘 + FFmpeg 回拼，成片 QC 通过 |
| 声音替换 | PASS | 内部 TTS + FFmpeg 换轨，结果检测到音轨 |

代表性结果：

- 图片：`https://oss-imgai.sligenai.cn/ai-video-kernel/20260710/6227f9c912cf4a60b7818862da29c839.png`
- 视频：`https://oss-imgai.sligenai.cn/ai-video-kernel/20260710/485e95fcd6d84f458a322994fbbf45cd.mp4`
- 复刻：`https://oss-imgai.sligenai.cn/ai-video-kernel/20260710/b7a82ec6a8d243ceb7966da95b9e4854.mp4`
- 定向替换：`https://oss-imgai.sligenai.cn/ai-video-kernel/20260710/0c32df22b0d94527a75c989708d0751e.mp4`

## 数据和备份

最新备份：`hook-studio-20260710T112324Z.tar.gz`，本地 checksum/SQLite 校验通过并上传 OSS。

隔离恢复目录：`/tmp/hook-studio-restore-drill-20260710`。

| 数据 | 恢复后数量 |
| --- | ---: |
| conversations | 12 |
| messages | 66 |
| assets | 33 |
| task_runs | 29 |
| training_examples | 25 |
| quota_ledger | 12 |
| events.jsonl | 61431 bytes |

恢复库 `PRAGMA integrity_check=ok`。生产库未被覆盖。

## Playwright

公网生产环境、Chrome 桌面 1440x1000 与移动 390x844：`4 passed, 2 expected skipped`。

覆盖无码 401、真实视频元数据可读、账号与额度、任务计数、预览、批量下载选择、180 秒自定义时长、管理数据导出、登录封面、左右移动抽屉和无水平溢出。
