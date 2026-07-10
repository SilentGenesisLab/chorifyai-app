# Hook Studio 测试计划

日期：2026-07-10  
目标网址：`https://chorifyai.sligenai.cn/hook-studio/`

## 测试层级

| 层级 | 目标 | 通过标准 |
| --- | --- | --- |
| 单元测试 | 配置、鉴权、配额、事件、skill gate、provider、QC、队列、备份、insights | 全部通过，无跳过 |
| 集成测试 | FastAPI 生命周期、无码 401、登录、图片/视频生成、管理后台、双队列 | fake provider 模式全绿 |
| 构建检查 | Python compile、TypeScript、Vite、secret scan | 全部退出码 0 |
| Playwright 本地 | 桌面与手机客户流、管理流、截图 | 4/4 通过，无布局遮挡或白屏 |
| 公网安检 | HTTPS、401、cookie、隔离、健康、管理、备份 | 全部通过 |
| 真实生成 | GPT Image 2 和 Seedance 2.0 | 两种模式各至少 3 次成功；视频均通过音轨/时长/比例 QC |

## Playwright 用例

1. 未登录访问 `/api/studio/bootstrap` 返回 401。
2. 客户码登录并进入三步工作台。
3. 图片模式显示不限日量，提交后进入图片队列并落入画廊。
4. 视频模式显示全站今日用量，提交前经过 skill gate，完成后落入画廊。
5. `/api/health` 同时返回独立 `image`、`video` 队列和各自并发。
6. 画廊包含预览、下载、重生成、删除控件。
7. 管理码登录后显示客户、用量、健康、备份和全站上限。
8. 1440x1000 与 390x844 两个视口截图无重叠、溢出或不可读按钮。

## 配额与时间

- 全站视频上限：100/UTC+8 日。
- 客户子配额：由访问码配置。
- 图片：无日量上限。
- 真实验收预算：3 张图片 + 3 条 5 秒视频。
- 单个真实任务等待上限：15 分钟；超时记录原 provider job ID，不重复提交。

## 当前结果

| 检查 | 结果 |
| --- | --- |
| Pytest | `32 passed` |
| Python compileall | PASS |
| Secret scan | PASS |
| TypeScript | PASS |
| Vite build | PASS |
| Playwright 本地 | `4 passed` |
| 公网 Playwright | 管理后台桌面/手机 `2 passed`；真实模型工作流已执行 |
| 真实图片 3 次 | PASS，累计 `5 succeeded`；另有一次上游重试后超时被诚实标记失败 |
| 真实视频 3 次 | PASS，`3 succeeded`；3/3 skill gate 与成片 QC 通过 |
| 备份恢复演练 | PASS，OSS 上传成功；临时目录恢复后 SQLite `integrity=ok`、18 jobs、事件日志 51658 bytes |

## 公网实测记录

- 发布时间：2026-07-10（UTC+8）。
- 发布版本：`10ec56673162`。
- HTTPS、无码 401、健康探针、客户登录、管理后台均通过。
- 首轮真实请求暴露 Kernel capability 不能复用内部 `run_id`，已改为 `external_ref` 并回归。
- Seedance 要求至少一个参考素材；无上传图时现在自动生成 9:16 首帧，再提交视频，过程写入 `auto_first_frame` 可观测字段。
- 真实视频用时较长但均在 15 分钟门限内完成；没有重复提交相同 provider job。
