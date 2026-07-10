# Hook Studio 架构设计 v1.0

状态：执行批准  
日期：2026-07-10

## 方案比较

### 方案一：独立模块化单体（采用）

FastAPI 提供 API、鉴权、SQLite、队列、管理和静态 SPA；React/Vite 构建产物由同一进程服务。图片和视频各有独立 worker pool。优点是单进程部署、边界清楚、易备份、易在 Nginx 子路径运行。

### 方案二：并入现有根 Next.js

可复用现有组件，但根工作树属于另一条 ChorifyAI/QC 主线且大量未提交；会混淆发布、配额、鉴权和故障域。拒绝。

### 方案三：前后端双服务

React 与 FastAPI 分开部署，扩展性强，但当前只增加 systemd、CORS、版本和运维复杂度。v1 拒绝，后续达到多实例需求再拆。

## 部署边界

- GitHub 仓库：`SilentGenesisLab/chorifyai-app`，独立模块目录 `apps/hook-studio/`
- 本地代码：`apps/hook-studio/`
- 分支：`feature/hook-studio-v1` -> `uat` -> `main`
- 远端目录：`/opt/hook-studio`
- 服务监听：`127.0.0.1:8011`（8010 已被现有 Chorify backend 占用）
- 公网网址：`https://chorifyai.sligenai.cn/hook-studio/`
- 管理路径：`/hook-studio/admin`
- 进程：一个 systemd service；Nginx 反代并保留子路径前缀。

## 模块

| 模块 | 职责 |
| --- | --- |
| `app/auth.py` | 访问码加载、登录、签名 session、客户/管理员授权 |
| `app/db.py` | SQLite 初始化、事务、查询与迁移 |
| `app/models.py` | API 与内部数据模型 |
| `app/presets.py` | 版本化预设加载、排序和模板灰度 |
| `app/skill_policy.py` | 生成前 policy gate 与可观测 trace |
| `app/providers/kernel.py` | Kernel capability API 上传、图片、视频提交与轮询 |
| `app/queues.py` | 图片/视频独立队列、worker、恢复和 ETA |
| `app/quota.py` | 全站视频日顶、客户子配额、预扣与失败补偿 |
| `app/events.py` | SQLite 与 JSONL 双写、导出和偏好信号 |
| `app/qc.py` | 视频 metadata、音轨、时长、比例与可播放检查 |
| `app/backup.py` | SQLite/log 打包、OSS 上传、保留 30 份、恢复 |
| `app/insights.py` | 下载率、重排、灰度统计、Markdown 周报 |
| `app/api/*` | auth、studio、admin、health 路由 |
| `frontend/` | 中文 SPA、管理后台、队列与画廊 |

## 鉴权与秘密

- `access_codes.yaml` 只存在服务端 secret 目录，仓库只提交 example。
- Provider URL、Bearer、session signing key、OSS 信息只从环境变量读取。
- 浏览器不接触 provider key、Kernel key 或 OSS key。
- `/api/health/live` 可匿名；其余 `/api/*` 无码返回 401。
- session 使用 HttpOnly、SameSite=Lax、Secure cookie；复用现有有效 HTTPS 证书。
- 事件中的 `access_code` 存稳定 code ID，不存真实登录码。

## 数据模型

### `jobs`

`id, client_id, mode, preset_id, template_version, prompt_user, prompt_final, params_json, model, status, queue_name, provider_job_id, result_url, result_meta_json, skill_trace_json, error_code, error_message, retry_count, queued_at, started_at, finished_at, deleted_at, parent_job_id`

### `events`

按宪章字段保存，并增加 `job_id, client_id, queue_name, queue_wait_ms, provider_attempt, skill_trace, error_code`。`access_code` 字段写 code ID。

### `daily_usage`

`day_cn, client_id, video_reserved, video_succeeded, video_failed, updated_at`。同一事务内先预留，再提交 provider；失败释放预留，成功转为 succeeded。

### `settings`

保存 `global_video_daily_limit=100`、图片/视频并发、模板流量和维护开关。

## 队列与恢复

- `image` 与 `video` 两个 `asyncio.Queue`，分别读取 `IMAGE_CONCURRENCY` 与 `VIDEO_CONCURRENCY`。
- 默认图片并发 2、视频并发 2；管理后台可调整持久值，进程重启生效。
- 提交先落 SQLite，再入队。服务启动时重新入队 `queued`；遗留 `running` 标记为 `queued` 并增加恢复事件。
- 队列位置按同 queue 的 `queued_at` 计算；ETA 使用最近 20 个同模式成功任务的中位耗时，样本不足时返回配置区间。

## Skill Policy

每个视频 job 生成以下 trace：

```json
{
  "policy_pack": "hook-video-reliability",
  "version": "1.0.0",
  "checks": [
    {"id": "slot-order", "status": "pass"},
    {"id": "reference-role", "status": "pass"},
    {"id": "action-causality", "status": "pass"},
    {"id": "duration-ratio", "status": "pass"},
    {"id": "native-audio-intent", "status": "pass"},
    {"id": "privacy-prohibited-elements", "status": "pass"}
  ]
}
```

任一 hard check 失败时不扣视频额度、不调用 provider，并返回中文可修正错误。参考图存在时必须建立 request-local slot manifest；无参考图时显式记录 `slot_manifest=[]`，不能伪造绑定。

## Provider 与错误

- 图片：Kernel `/capabilities/v1/images/generate`，请求超时后最多重试一次。
- 视频：Kernel `/capabilities/v1/videos/generate`，提交最多两次；保存 `submit_id` 后只轮询同一任务，不因空响应重复提交。
- 所有成功 URL 立即写入 SQLite；视频完成后做媒体探测。
- 错误码稳定为：`AUTH_REQUIRED, CODE_DISABLED, QUOTA_EXHAUSTED, INPUT_INVALID, SKILL_GATE_BLOCKED, PROVIDER_TIMEOUT, PROVIDER_REJECTED, RESULT_INVALID, INTERNAL_ERROR`。
- 前端永不白屏；所有错误显示请求 ID 和可操作下一步。

## 测试

- 单元：auth、quota、UTC+8、双队列、skill gate、事件双写、软删除、备份清单。
- 集成：fake Kernel 完整生成；真实 Kernel 小探针；无码 401；超额拒绝；重启恢复。
- Playwright：客户登录、图片/视频任务、队列、画廊、重生成、删除、管理员登录与配额修改。
- 安检：secret scan、前端 bundle scan、HTTP header、访问隔离、日志完整性、备份恢复。
