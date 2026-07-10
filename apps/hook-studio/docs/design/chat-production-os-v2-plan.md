# Hook Studio Chat Production OS v2 Implementation Plan

> **For agentic workers:** 按任务边界实现并在每个任务后运行对应测试；只有主代理合并跨模块契约。

**Goal:** 交付真实可执行的 Codex 式多模态视频生产工作台。

**Architecture:** 在现有 FastAPI + SQLite + React 模块化单体上增量增加会话域、资产解析域和生产任务域，继续通过服务端 Kernel provider 使用图片、视频、理解、媒体和 OSS 能力。所有长任务以可恢复状态机执行，前端只消费同源 API。

**Tech Stack:** FastAPI、SQLite、httpx、PyYAML、pypdf、python-docx、React、TypeScript、Vite、Playwright、Kernel capability API、ffmpeg。

## Global Constraints

- 前端零密钥、零 provider 直连。
- 访问码隔离所有会话、资产、任务和导出。
- 图片全站每日 1000；视频全站每日 100 个生成分段。
- 故事板确认前不生成视频。
- 所有可见生产模块必须真实执行。
- 旧 API 和旧 job 数据继续可读。

### Task 1: 数据迁移与会话仓储

**Files:** `app/db.py`、`app/models.py`、`app/repositories/workspace.py`、`tests/test_db_migrations.py`、`tests/test_workspace_repository.py`

- [ ] 增加版本化、幂等、只增不删的 v2 迁移。
- [ ] 实现会话、消息、资产、任务、故事板、配额和训练投影仓储。
- [ ] 回填旧 job 到“历史生成”会话并验证二次执行不重复。
- [ ] 运行迁移、客户隔离、FK 和 `PRAGMA integrity_check` 测试。
- [ ] 提交 `feat(hook-studio): add conversation data model`。

### Task 2: 多模态资产与安全链接解析

**Files:** `app/services/ingestion.py`、`app/api/workspace.py`、`app/providers/kernel.py`、`tests/test_ingestion.py`、`tests/test_workspace_api.py`

- [ ] 实现流式上传与图片/视频/音频/文本/PDF/DOCX 解析。
- [ ] 实现 DNS 与重定向双重 SSRF 检查的链接解析。
- [ ] 将媒体上传 OSS，调用 Kernel probe/understand，保存 extraction 与 segment。
- [ ] 实现 `POST /api/workspace/assets` 和 `/assets/links`。
- [ ] 运行 MIME、大小、SSRF、解析状态和客户隔离测试。
- [ ] 提交 `feat(hook-studio): ingest multimodal assets`。

### Task 3: 对话 API 与意图/缺口回问

**Files:** `app/services/chat.py`、`app/api/workspace.py`、`tests/test_chat.py`

- [ ] 实现多对话 CRUD、顺序消息和附件绑定。
- [ ] 实现六类工具契约，不使用拍法预设。
- [ ] 视频任务缺少总时长时返回 `needs_duration` 助手消息。
- [ ] 有时长时创建可恢复 `task_run` 并加入规划队列。
- [ ] 提交 `feat(hook-studio): add production chat api`。

### Task 4: 故事板规划与确认门

**Files:** `app/services/planning.py`、`app/services/production.py`、`app/api/workspace.py`、`tests/test_storyboard_flow.py`

- [ ] 实现 4-15 秒精确求和的无限总时长分段器。
- [ ] 调用 Kernel understand 生成结构化镜头计划并做 schema 校验。
- [ ] 为每镜头生成故事板图片并保存版本化 shot。
- [ ] 返回故事板助手消息和预计图片/视频额度。
- [ ] 实现带 `expected_version` 的 confirm/revise API。
- [ ] 证明确认前视频 ledger 为零，确认后按分段数预留。
- [ ] 提交 `feat(hook-studio): gate video generation on storyboard approval`。

### Task 5: 长视频、复刻与批量执行

**Files:** `app/services/production.py`、`app/providers/kernel.py`、`app/services/generation.py`、`tests/test_production_pipeline.py`

- [ ] 扩展 provider 支持 `video_urls`、Kernel transcode、extract-frame 和 understand。
- [ ] 逐镜头提交 Seedance，保存 submit/poll/retry/交接证据。
- [ ] 实现参考槽位 `controls/must_not_control` 和复刻矛盾审计。
- [ ] 实现受控并发 variant 批量执行与局部失败重试。
- [ ] 拼接成片并在对话中创建媒体消息。
- [ ] 提交 `feat(hook-studio): orchestrate long replica and batch videos`。

### Task 6: 逆向分析与定向替换

**Files:** `app/services/analysis.py`、`app/services/replacement.py`、`tests/test_analysis_replacement.py`

- [ ] 媒体 probe、关键帧、视频理解和 ASR 形成逐镜头分析表。
- [ ] 生成可迁移复刻方案和不可复制边界。
- [ ] 场景/商品/人物替换只重生成目标区间并拼回原片。
- [ ] 保存保持项、变化项、源区间和 QC 证据。
- [ ] 提交 `feat(hook-studio): analyze and replace targeted video elements`。

### Task 7: 声音替换、ZIP 与训练导出

**Files:** `app/services/audio.py`、`app/services/export.py`、`app/api/admin.py`、`tests/test_audio_export.py`、`tests/test_training.py`

- [ ] 服务端调用 TTS 生成有来源记录的音频。
- [ ] 使用 ffmpeg 替换/混合目标音轨并 probe 验证。
- [ ] 实现当前客户多选产物 ZIP 流式下载。
- [ ] 构建可重建训练投影与 CSV/JSONL 管理导出。
- [ ] 提交 `feat(hook-studio): add audio replacement and structured exports`。

### Task 8: Codex 式三栏前端

**Files:** `frontend/src/App.tsx`、`frontend/src/api.ts`、`frontend/src/types.ts`、`frontend/src/components/*`、`frontend/src/styles.css`

- [ ] 左栏实现历史对话与左下账号/双额度。
- [ ] 中栏实现消息、附件、故事板确认和对话内媒体。
- [ ] 底部输入器实现六个工具、多附件、链接、时长和发送。
- [ ] 右栏实现媒体预览、队列阶段、任务数字和批量下载。
- [ ] 手机端实现左右抽屉与固定输入器。
- [ ] 提交 `feat(hook-studio): build codex style production workspace`。

### Task 9: 登录轮播与来源账本

**Files:** `frontend/public/login/*`、`frontend/public/login/ATTRIBUTION.md`、`frontend/src/components/Login.tsx`

- [ ] 从允许复用的公开素材源下载并本地托管三项素材。
- [ ] 记录作者、来源页、许可和获取日期。
- [ ] 实现自动轮播、手动切换、首帧 fallback 和 reduced-motion。
- [ ] 提交 `feat(hook-studio): add licensed login media carousel`。

### Task 10: 验收、备份与发布

**Files:** `frontend/e2e/chat-production.spec.ts`、`TEST_PLAN.md`、`SECURITY_REPORT.md`、`OPERATOR_MANUAL.md`

- [ ] 后端全量测试、compile、secret scan、前端构建。
- [ ] Playwright 桌面/手机覆盖多对话、附件、时长回问、故事板、媒体消息、右栏和额度。
- [ ] 使用已有真实视频做逆向、复刻和替换 smoke；执行至少两段真实生成并拼接。
- [ ] 备份生产数据，部署 feature，验证后晋级 uat/main 并打版本标签。
- [ ] 公网复核 200/401/健康/客户隔离/管理导出和恢复演练。

