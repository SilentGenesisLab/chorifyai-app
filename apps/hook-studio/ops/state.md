# Hook Studio MVP State

## 当前目标

交付可直接使用的多模态生产 MVP：图片支持生成与局部编辑；视频拥有完整镜头合同和按复杂度选择的确认表现；所有任务可观测、按客户公平排队并可完整导出数据。

## 当前里程碑

- 里程碑：Image Edit + Adaptive Confirmation MVP
- 轮次：`ops/rounds/image-edit-v1`
- 分支：`feature/hook-studio-chat-os`
- 公网目标：`https://chorifyai.sligenai.cn/hook-studio/`
- 当前状态：READY_FOR_INSPECTOR
- Inspector：独立子代理，只接收 Gate、改动清单与本轮证据

## 已冻结决策

- 所有视频镜头均有完整镜头合同和至少一个可确认关键画面；按动作复杂度返回 1 张关键帧、2 张起止帧或 3 张动作序列，不把九宫格当硬条件。
- 动态预演是可选确认层；一旦生成则必须确认。定位文字、箭头和框线是可选说明，不是蒙版。
- 带标注板只供人审阅；只有批准的干净参考帧可进入视频 Provider 请求。
- Hook Studio 是客户控制面；密钥和 Provider 调用全部留在服务端。
- REST 负责命令，SQLite durable outbox + SSE 负责实时状态与断线重放。
- 图片/视频队列分开；图片日上限 1000，视频全站日上限 100。
- 队列按客户轮转；批量任务每次只占一个 Provider 槽。并发值是可调运行参数，不是前台硬规则。
- 局部编辑优先走服务端 `/v1/images/edits`；失败降级为参考重绘，存在蒙版时用源像素确定性回填蒙版外区域。
- 对话、素材、任务、镜头、Skill 运行、编辑合同、资产版本、事件和训练样本均可由管理后台导出。
- 客户前台只显示中文能力阶段，不显示模型或 Provider 名称。

## 已完成

- Kernel 图片编辑端点、原图外像素回填和本地 capability 测试已通过。
- Hook Studio 局部修图纵切、编辑合同、资产版本和训练留存已通过。
- 图片/视频独立队列已改为按客户轮转；批量视频不再一次并发全部版本。
- 管理后台完整数据 ZIP、训练 JSONL 和事件 JSONL 均可导出。
- Pytest 全量、前端 production build 和 Playwright 图片编辑流程已通过。

## 下一动作

完成独立 Inspector，部署 Hook Studio 与 Kernel 同一兼容版本，再做公网鉴权、局部编辑和数据导出验收。
