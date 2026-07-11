# Image Edit V1 Inspector Review

日期：2026-07-11

## 最终判定

Inspector 按项目级 `verify/SKILL.md` 判定：`FAIL`。

Hook Studio 本模块的功能 Gate 全部通过；剩余失败项是主站 18 路由的登录后视觉证据。该路由清单不属于本 WorkOrder，且当前主站在已登录状态下访问 `/create?stage=1` 实际返回 404，因此不能用 Hook Studio 增量修复或伪造为通过。

本轮按用户“先推进可用结果”的明确要求保留这项范围例外，Hook Studio 与 Kernel 已部署；不把项目级主站视觉 Gate 误报为绿色。

## Gate 结果

| Gate | 结论 | 证据 | 复现方法 | 缺口 |
| --- | --- | --- | --- | --- |
| 图片直连编辑与强制 mask 合成 | PASS | `evidence/direct-probe.json`、`evidence/pixel-verification.json`、138 项 Pytest | 运行 `tests/test_workspace_api.py` 与 Kernel capability 测试 | 无 |
| fallback 语义顺序 | PASS | `tests/test_image_router.py` 含逆序上传回归 | 运行 `pytest tests/test_image_router.py` | 无 |
| 多客户公平队列与批量单槽 | PASS | `tests/test_queues.py` | 运行队列并发测试 | 无 |
| 完整数据导出 | PASS | `public-data-export.json`，25 张表、manifest、客户 403、管理员 200 | 管理码请求 `/api/admin/data/export` | 无 |
| UI、进度、预览与成品库 | PASS | `evidence/image-edit-complete.png`、`playwright.log` | 运行 `e2e/image-edit.spec.ts` | 无 |
| 密钥、A/B、依赖与浏览器直连红线 | PASS | `redline-scan.log` | 按日志命令重跑 | 无 |
| 公网部署一致性 | PASS | `public-health.json`，build `7361c7a`、schema `6` | GET 公网 `/healthz` | 无 |
| 主站 18 路由状态码 | PASS | `routes.json` | 未登录并跟随登录重定向探测 | 状态码 200 由登录页产生 |
| 主站 18 路由登录后视觉 | FAIL | `shots/`；独立 Inspector 哈希检查；登录后 `/create?stage=1` 为 404 | 使用主站测试账号登录后逐路由截图 | 属于主站应用，不在 Hook Studio WorkOrder；当前主站路由本身缺失 |

## Inspector 三轮收敛

1. 第一轮发现 mask 合成未在 Hook 边界强制、fallback 槽位漂移、文件名误判与并发证据缺口。
2. 第二轮确认合成、文件名和并发已关闭，继续发现逆序上传仍会使 fallback 语义漂移。
3. 第三轮确认全部功能代码 Gate 通过，仅保留主站 18 路由视觉与部署证据问题；部署证据随后由 `public-health.json` 补齐。

## 本轮最差的 3 处

1. 初版把 Provider trace 当成 mask 外像素已保持的事实，未在 Hook 边界强制合成。
2. fallback 图片编号曾依赖上传顺序，而不是 `edit_target`、`annotation` 的语义顺序。
3. 项目级 Verify 的 18 路由清单与 Hook Studio WorkOrder 不同域，导致大量登录页截图产生了假证据；本轮最终保留 FAIL，而不是粉饰为 PASS。
