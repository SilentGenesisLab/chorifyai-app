# Hook Studio MVP State

## 当前目标

交付新的全镜头故事板 MVP：所有视频 Shot 必须拥有完整镜头合同、可审阅 Panel、干净参考帧、逐镜审批和 Animatic；服务端门禁通过后才可占用视频额度并提交 Kernel。

## 当前里程碑

- 里程碑：Full Storyboard MVP
- 轮次：`ops/rounds/full-storyboard-mvp`
- 分支：`feature/hook-studio-chat-os`
- 公网目标：`https://chorifyai.sligenai.cn/hook-studio/`
- 当前状态：BUILDING
- Inspector：独立 `/root/mvp_inspector`，只接收 Gate 与证据

## 已冻结决策

- 所有镜头均有 Storyboard Panel 和 clean frame，不保留轻量例外。
- 带标注板只供人审阅；只有批准的 clean frame 可进入 Provider 请求。
- Hook Studio 是客户控制面；密钥和 Provider 调用全部留在服务端。
- REST 负责命令，SQLite durable outbox + SSE 负责实时状态与断线重放。
- 图片/视频队列分开；图片日上限 1000，视频全站日上限 100。
- 客户前台只显示中文能力阶段，不显示模型或 Provider 名称。

## 已完成

- 计划与 N1-N7 Gate 已落盘并推送。
- Kernel 调用合同已限制为真实验证的 multimodal 路径和 4-15 秒单镜。
- 旧视频策略与 QC 已对齐 4-15 秒。
- Hook Studio 独立真实验证额度台账已建立。

## 下一动作

完成 N1-N6 建造，逐节点交 Inspector；全量自动化和真实生产证据通过后原子切换公网 release。

