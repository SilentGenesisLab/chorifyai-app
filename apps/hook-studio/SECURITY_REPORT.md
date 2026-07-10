# Hook Studio 安检报告

状态：本地与公网门禁通过
日期：2026-07-10

| 检查 | 本地结果 | 证据 |
| --- | --- | --- |
| Provider 密钥不进前端 | PASS | 前端只调用同源 `/hook-studio/api`；Kernel key 仅来自服务端环境变量 |
| 明文秘密扫描 | PASS | `python scripts/security_check.py` -> `SECRET_SCAN_PASS` |
| 无码 API | PASS | 集成测试与 Playwright 均验证 401 |
| 访问码即时停用 | PASS | 每次请求重新读取服务端 YAML 状态 |
| 客户隔离 | PASS | 对话、消息、素材、任务和下载均按 session code ID 强制过滤 |
| 图片/视频配额 | PASS | v2 quota ledger + `BEGIN IMMEDIATE` 原子预留，失败释放，成功结算 |
| 图片/视频并发隔离 | PASS | 两个独立 Queue 与 worker pool；批量变体受共享信号量约束 |
| 输入基础过滤 | PASS | 类型白名单、512MB 上限、文件名清洗、SSRF/DNS/IP/重定向防护 |
| Provider 重试 | PASS | 最多两次尝试，即首次加一次重试；视频保存同一 submit ID 后只轮询 |
| 视频结果验证 | PASS | 每个 Seedance 片段与最终拼接结果均检查有效视频轨和时长；换声检查音轨 |
| 事件完整性 | PASS | SQLite 先写，JSONL fsync 双写；写失败向调用方暴露 |
| 软删除 | PASS | 对话、任务与素材索引保留，删除不物理清理 OSS 产物 |
| 备份包安全 | PASS | 固定文件白名单、常规文件限制、checksum、SQLite integrity check |
| Session cookie | PASS | HttpOnly、SameSite=Lax；生产启用 Secure |

## 公网复核

- HTTPS 证书校验通过，公网入口返回 200。
- 无码访问受保护 API 返回 401。
- systemd 服务仅监听 `127.0.0.1:8011`，由现有 HTTPS Nginx 路径代理。
- `/etc/hook-studio` 与秘密文件不进 Git；前端生产 bundle 二次扫描无密钥。
- OSS 备份上传成功且本地包校验通过；`hook-studio-20260710T112324Z.tar.gz` 恢复到隔离目录后 SQLite `PRAGMA integrity_check=ok`。
- 维护 timer 处于 active，每日执行健康、备份、Insights。
