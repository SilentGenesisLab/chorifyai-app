# 独立部署 Hook Studio 模块化单体

## 日期

2026-07-10

## 状态

已采纳

## 背景

当前仓库根目录已有一条并行开发的 ChorifyAI Next.js 主线，工作树包含大量未提交改动。Hook Studio 需要独立访问码、配额、SQLite、事件飞轮、provider 队列和公网部署生命周期。

## 决策

- 在 `SilentGenesisLab/chorifyai-app` 的 `apps/hook-studio/` 建立独立可部署模块；不改动既有 backend/frontend。
- 使用 FastAPI 模块化单体，服务构建后的 React SPA。
- 图片与视频使用独立队列和并发器。
- 复用现有 Kernel capability API，不复制 Kernel 工作树或把 provider key 交给浏览器。
- 线上用一个 systemd service，并复用 `chorifyai.sligenai.cn` 的有效证书与 Nginx `/hook-studio/` location。
- 全站视频每日 100 条；图片不设日量上限。

## 备选方案与取舍

- 并入根 Next.js：拒绝，避免污染并行主线与共享故障域。
- 前后端分离部署：v1 拒绝，当前运维成本高于收益。
- 浏览器直连 provider：永久拒绝，违反密钥和配额铁律。

## 影响

- Hook Studio 可独立版本、部署、回滚和开源到组织私有仓库。
- 需要单独维护 Python/Node 构建链，但运行时只保留 Python 服务。
- 上游 provider 账号池共享，但调用必须按产品标签观测和归因。
