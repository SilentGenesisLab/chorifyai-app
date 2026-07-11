# Hook Studio Full Storyboard MVP Gate

日期：2026-07-11  
范围：`apps/hook-studio` 新 MVP  
Inspector：独立只读 Agent

## N1 数据合同

- `Storyboard -> Shot -> Panel` 为显式 1:N 结构。
- 每个 Shot 至少一个 required Panel 和一个 selected clean frame。
- SkillRun、ApprovalDecision、WorkflowEvent、Animatic 均持久化。
- 老库执行增量迁移后数据仍可读取；SQLite integrity check 为 `ok`。

## N2 Skill 与门禁

- 全部视频 Shot 具备完整的人话与结构化描述。
- 缺 Panel、clean frame、逐镜批准、Animatic 确认、合法时长或引用清单时，服务端返回 422/409 且不预留视频额度。
- Skill trace 包含版本、状态、耗时、输入输出数量、阻塞原因；客户投影不含模型或 Provider 名称。

## N3 通信与进度

- 任务事件 SSE 无码 401、跨客户 404、支持 Last-Event-ID 重放与心跳。
- 图片队列和视频队列分别显示真实等待/执行/成功/失败数量。
- 生成等待没有真实百分比时必须显示 indeterminate、已等待时间和最后心跳。
- 刷新或 SSE 断线后可从快照与事件恢复，不重复提交。

## N4 故事板闭环

- 8 镜任务必须显示 8/8 Shot、8/8 以上 Panel 组、8/8 clean frame。
- 单独修改 S04 只生成 S04 新修订，不重做其他镜头。
- 每镜支持批准/退回/反馈/候选切换；老版本审批返回 409。
- Animatic 使用真实镜头时长并可播放；未确认时真实视频生产保持锁定。

## N5 前端体验

- 中央区包含镜头表、分镜带、动态预演三个同步视图。
- 对话内有需求、执行、覆盖、审批、交付卡和持续动画/心跳。
- 右侧只包含资产库、选中预览和成品库，可批量下载。
- 左下角账号名、图片额度、视频额度保持可见。
- 1440x1000 与 390x844 无重叠、横向溢出、截断按钮或不可达控件。

## N6 内核与可靠性

- 浏览器零 Provider 直连与零密钥；Hook 只调用 Kernel。
- Provider submit 获得任务 ID 后绝不重复提交；超时、一次重试、失败释放额度均有测试。
- 仅 approved clean frame 可进入视频请求；annotated board 不进入 Provider。
- 每个成片经过视频轨、时长、9:16、音轨和结构化 QC，失败镜头可单独回炉。

## N7 安全、测试、上线

- Python 全量测试、前端 build、Playwright、secret scan、无码 401、越权 404、非法输入 422、版本冲突 409 全绿。
- `/healthz` 返回 `status/build_sha/schema_version/skill_pack_version`。
- 公网首页、登录、客户工作台、管理后台、SSE 与下载均可访问。
- systemd active+enabled，Nginx HTTPS 正常，备份恢复校验通过。
- 两种模式各完成至少 3 次真实成功；视频必须包含多镜任务和拼接。

## Inspector 证据格式

每个节点必须写：`结论 | 证据 | 复现方法 | 缺口`。无证据即 FAIL。最终 `review.md` 必须列出最差 3 处；总判定只有 PASS 或 FAIL。

