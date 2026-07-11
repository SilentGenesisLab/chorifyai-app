# Hook Studio Chat OS v2 测试计划

日期：2026-07-10  
公网：`https://chorifyai.sligenai.cn/hook-studio/`

## 验收范围

| 层级 | 目标 | 通过标准 |
| --- | --- | --- |
| 单元/集成 | 数据迁移、鉴权、配额、附件解析、Provider、故事板、长视频拆段、批量并发、训练数据 | Pytest 全绿 |
| 构建/安检 | TypeScript、Vite、明文密钥扫描、无码 API | 全部退出码 0；无码 401 |
| 公网 UI | 登录、对话、额度、真实媒体、右侧任务、管理后台、移动抽屉 | Playwright 桌面/手机全绿 |
| 真实模型 | GPT Image 2、Seedance、Kernel Understand、TTS、FFmpeg | 可见工具各有真实成功结果 |
| 数据可靠性 | SQLite/JSONL、备份、OSS、隔离恢复 | checksum 与 SQLite integrity 全绿 |

## 核心用例

1. 无码访问 `/api/studio/bootstrap` 返回 401。
2. 客户码登录后左下角显示账号、图片 `X/1000` 和视频 `X/客户额度`。
3. 多对话互相独立，附件和结果按访问码隔离。
4. 文本、PDF、DOCX、XLSX、PPTX、图片、视频、音频和 HTTP(S) 链接可安全接收、解析并持久化。
5. 图片生产进入独立图片队列，服务端扣图片额度并在对话返回图片。
6. 视频缺少时长时先回问；总时长可填 4-60 秒，再按 4-15 秒镜头拆分。
7. 所有视频生产先返回完整镜头合同；按复杂度使用关键帧、起止帧、动作序列或可选动态预演，确认后才预留视频额度。
8. 参控复刻明确绑定图片1、视频1和上一镜头连续性，不复制原品牌/人物/字幕/音乐。
9. 批量生产返回多个独立成片；同一批次逐版本占用 Provider 槽，单版本内镜头保持顺序，不挤占其他客户。
10. 逆向分析返回 probe、关键帧和结构化分析。
11. 定向替换通过 Seedance 重绘目标区间，再由 FFmpeg 回拼源视频。
12. 声音替换通过内部 TTS 生成音频并由 FFmpeg 替换音轨。
13. 右侧显示等待/执行/成功/失败数量、阶段、进度、媒体预览和批量 ZIP 下载。
14. 管理后台可改客户额度、停用码、改全站上限并导出完整数据 ZIP、训练 JSONL 与事件 JSONL。
15. 局部修图可接原图、可选 PNG 蒙版和可选定位图；直连失败自动降级，蒙版外像素合成后必须零变化。
16. 备份恢复到隔离目录后，所有表可读且 `PRAGMA integrity_check=ok`。

## 当前结果

### 2026-07-11 Image Edit V1 增量

| 检查 | 结果 |
| --- | --- |
| Hook Studio Pytest 全量 | PASS，138 tests |
| Kernel 图片编辑与 capability API | PASS，6 tests |
| TypeScript + Vite production build | PASS，1583 modules |
| Playwright 关键桌面/移动流程 | PASS，5 passed，5按项目视口预期跳过 |
| 真实图片编辑直连 | PASS，HTTP 200，最终结果已落盘 |
| 蒙版外像素 | PASS，849100 像素中 0 个变化 |
| 图片编辑合同、资产版本、训练样本 | PASS，SQLite 双向可追溯 |
| 完整数据 ZIP | PASS，含 25 张表 JSONL 与 manifest，排除访问码和密钥 |
| 公网部署 | PENDING，本增量尚未切换公网 release |

### 2026-07-10 Chat OS v2 基线

| 检查 | 结果 |
| --- | --- |
| Pytest | PASS，`71 tests` |
| Secret scan | PASS，`SECRET_SCAN_PASS` |
| TypeScript | PASS |
| Vite production build | PASS，1581 modules |
| 公网 HTTPS/health | PASS，200 / `status=ok` |
| 无码 API | PASS，401 |
| 公网 Playwright | PASS，`4 passed, 2 expected skipped` |
| 图片、视频、逆向、复刻、批量、定向替换、换声 | 全部真实成功 |
| 真实批量 | PASS，一次任务返回 3 个 QC 通过成片 |
| 备份上传/校验 | PASS，`hook-studio-20260710T112324Z.tar.gz` |
| 隔离恢复 | PASS，SQLite `integrity=ok`，事件日志 61431 bytes |

## 真实运行发现

- 首轮并发视频理解在 70 秒超时门限下失败。已把 Kernel 单请求超时调整为 240 秒，并把重型理解串行化；重试后的逆向、复刻、批量、替换全部成功。
- 2026-07-10 曾把批量改为“变体并行、镜头串行”。2026-07-11 为避免大批次饿死其他客户，改为客户公平轮转且单任务逐版本占槽；Provider 并发仍由实时运行参数控制。
- 前端公网首轮测试发现移动遮罩测试点击位置不合理和测试选择器歧义；修正测试后桌面/手机均通过，并保留截图证据。
- 真实 provider 可能需要数分钟。任务状态、失败原因和原始结果都写入 SQLite，不用白屏或假进度掩盖等待。

## 证据

- [真实验收记录](docs/evidence/2026-07-10-chat-os/REAL_ACCEPTANCE.md)
- [客户工作台截图](docs/evidence/2026-07-10-chat-os/customer-chat-os.png)
- [管理后台截图](docs/evidence/2026-07-10-chat-os/admin-data-assets.png)
- [移动端抽屉截图](docs/evidence/2026-07-10-chat-os/mobile-drawers.png)
- [移动端登录截图](docs/evidence/2026-07-10-chat-os/mobile-login.png)
