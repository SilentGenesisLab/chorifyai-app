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
| 公网 Playwright | 待部署后执行 |
| 真实图片 3 次 | 待部署后执行 |
| 真实视频 3 次 | 待部署后执行 |
| 备份恢复演练 | 本地单元与校验通过；公网 OSS 待部署后执行 |

