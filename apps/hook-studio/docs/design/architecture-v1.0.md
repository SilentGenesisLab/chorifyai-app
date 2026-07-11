# Hook Studio 全镜头 MVP 架构 v2.0

状态：已实现并进入上线验收
日期：2026-07-11

## 系统边界

Hook Studio 是独立模块化单体：React/Vite 提供中文客户工作台与管理后台，FastAPI 提供鉴权、命令、状态查询、SSE、Skill 编排、配额、训练数据和静态资源，SQLite 是任务状态事实源。公网由 Nginx 以 `/hook-studio/` 子路径反代，systemd 守护一个应用进程。

浏览器只访问 Hook Studio。所有生成、媒体探测、上传、理解和转码请求都由服务端转交视频 Kernel；访问码、Kernel 凭据和内部能力名称不会进入前端 bundle、DOM 或客户 API。

## 分层

| 层 | 组件 | 职责 |
| --- | --- | --- |
| 交互层 | `frontend/src/components/FullStoryboardWorkspace.tsx` | 对话、素材上传、4-60 秒时长确认、镜头表、分镜带、动态预演、审批、资产库、预览板、成品库 |
| 命令层 | `app/api/workspace.py` | REST 命令、401/404/409/422 边界、Idempotency-Key、租户投影、批量下载 |
| 通信层 | `app/services/workflow_events.py` | SQLite durable event、SSE、Last-Event-ID 重放、心跳与断线恢复 |
| 编排层 | `app/services/production.py` | 图片/视频独立队列、全流程状态机、配额预留、逐镜并发、拼接与失败补偿 |
| Skill 层 | `app/skill_runtime.py` | Brief、完整镜头合同、Panel 计划、引用清单、提示词编译、生产前门禁、审批策略和可观测 SkillRun |
| 工具层 | `app/providers/kernel.py`、`app/services/media_ops.py` | 只调用已验证的 Kernel 多模态合同；本地 FFmpeg 负责动态预演和确定性媒体操作 |
| 数据层 | `app/repositories/workspace.py`、`app/db.py` | Storyboard/Shot/Panel、候选历史、审批、事件、资产、对话、任务、配额和训练表 |
| 运维层 | `deploy/`、`scripts/` | Nginx/systemd、健康探针、备份、恢复、安检、周报与洞察 |

## 视频生产状态机

1. 客户输入文本、文件、图片、视频、音频或链接；视频总时长必须为 4-60 秒。
2. 服务端先落消息和任务，重复提交使用同一 Idempotency-Key 时返回原任务，不重复生产。
3. Skill Runtime 依次完成人话需求、商业节拍、完整镜头合同、三画格计划、连续性与引用清单。
4. 每个 Shot 固定至少包含 `start/action/result` 三个 required Panel；每个 Panel 同时保留带标注审阅图和独立 clean frame。
5. 客户可只重生一个 Panel、重生整镜、切换历史候选、退回或批准；任何修订都会使旧审批和旧 Animatic 失效。
6. 所有镜头、所有 required Panel、整板和动态预演均确认后，服务端严格门禁再次校验租户、资产 URI、状态、引用清单和 4-15 秒单镜时长。
7. 门禁通过后才原子预留视频额度。每镜只把批准的 clean frame 传入 Kernel，带标注故事板永不进入生成请求。
8. 单镜按 4-15 秒真实生成；同一变体内按镜头顺序保持连续，不同变体可在独立视频信号量内并发。
9. 每个生成任务取得 submit ID 后只轮询该 ID，不重新提交。等待阶段返回不伪造百分比的心跳、已等待时间与最后心跳。
10. 单镜和最终拼接都检查视频轨、时长、9:16 和音轨；通过后进入成品库，失败释放额度并保留可回炉的镜头与事件证据。

## 数据合同

`Storyboard 1:N Shot 1:N Panel` 是持久化硬约束。一个可保存的 Shot 必须有三个角色完整、含可用 clean frame 的 Panel。Panel 修订采用 append-only 历史：当前版本被 supersede，候选列表仍可审计和切回；选择旧候选会创建新的当前修订，而不是倒改历史行。

关键可观测表：

- `skill_runs`：skill/version/status/duration/input/output/blocking reason 与私有 trace。
- `workflow_events`：SSE 重放和任务恢复事实源。
- `approval_decisions`：scope、目标 revision、反馈与幂等键。
- `quota_ledger`：图片与视频的 reserved/committed/released。
- `training_examples`、`messages`、`assets`：对话、素材、输出与训练处理索引。

## 能力边界

- 当前真实视频提交只启用已探针验证的 `multimodal` 合同；未验证的首尾帧、延长或编辑模式在网络请求前拒绝。
- 60 秒是 MVP 成片上限，不代表单次模型调用能力。系统把长成片拆成多个 4-15 秒镜头再拼接。
- “故事板 Skill”不是给生成 API 增加一个神秘参数，而是服务端的可版本化编译、门禁、资产和审批链；生成 API 只接收门禁后确定的 clean frame、引用槽位和镜头提示词。
- 动态预演用于节奏与构图确认，不冒充最终模型成片。
- 替换、复刻和批量能力共用相同 Storyboard/Panel/Approval/QC 合同，不能绕过确认链。

## 部署

- 仓库：`SilentGenesisLab/chorifyai-app`，分支 `feature/hook-studio-chat-os`
- 模块：`apps/hook-studio/`
- 公网：`https://chorifyai.sligenai.cn/hook-studio/`
- 应用监听：`127.0.0.1:8011`
- 发布目录：`/opt/hook-studio/releases/<commit>`，`/opt/hook-studio/current` 原子切换
- 数据与秘密：`/var/lib/hook-studio`、`/etc/hook-studio`
