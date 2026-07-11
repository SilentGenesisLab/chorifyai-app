# Decision Needed

## D-001 Hook Studio 是否继承主站 18 路由视觉 Gate

- 状态：排队，不阻塞当前 Hook Studio 公网版本。
- 事实：`verify/SKILL.md` 要求 `/workspace`、`/create`、`/production` 等 18 个主站页面；Image Edit V1 WorkOrder 只修改 `/hook-studio/`。
- 当前证据：未登录时 18 路由因重定向登录页表现为 200；登录后 `/create?stage=1` 返回 404，无法由 Hook Studio 增量修复。
- 选项 A：为 Hook Studio 建立独立 Verify profile，只验 `/hook-studio/` 的客户、管理员、任务、编辑、导出和鉴权路由。
- 选项 B：保留统一主站 Verify，今后每个 Hook Studio 增量都必须同时验收并可能修复主站。
- 建议：选 A。共享安全、构建、密钥和响应式红线，分离不相关的页面清单。
