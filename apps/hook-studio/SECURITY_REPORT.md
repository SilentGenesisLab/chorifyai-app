# Hook Studio 安检报告

状态：本地与公网门禁通过
日期：2026-07-10

| 检查 | 本地结果 | 证据 |
| --- | --- | --- |
| Provider 密钥不进前端 | PASS | 前端只调用同源 `/hook-studio/api`；Kernel key 仅来自服务端环境变量 |
| 明文秘密扫描 | PASS | `python scripts/security_check.py` -> `SECRET_SCAN_PASS` |
| 无码 API | PASS | 集成测试与 Playwright 均验证 401 |
| 访问码即时停用 | PASS | 每次请求重新读取服务端 YAML 状态 |
| 客户隔离 | PASS | job/gallery 查询按 session code ID 强制过滤 |
| 视频全局/客户配额 | PASS | SQLite `BEGIN IMMEDIATE` 原子预留，失败释放，成功结算 |
| 图片/视频并发隔离 | PASS | 两个独立 Queue 与 worker pool |
| 输入基础过滤 | PASS | 模式、预设、描述、图片 MIME、10MB、视频时长、比例、skill policy |
| Provider 重试 | PASS | 最多两次尝试，即首次加一次重试；视频保存同一 submit ID 后只轮询 |
| 视频结果验证 | PASS | URL、视频流、4-5 秒、9:16、音轨均为硬门 |
| 事件完整性 | PASS | SQLite 先写，JSONL fsync 双写；写失败向调用方暴露 |
| 软删除 | PASS | 只写 `deleted_at`，不物理删除 OSS 产物 |
| 备份包安全 | PASS | 固定文件白名单、常规文件限制、checksum、SQLite integrity check |
| Session cookie | PASS | HttpOnly、SameSite=Lax；生产启用 Secure |

## 公网复核

- HTTPS 证书校验通过，公网入口返回 200。
- 无码访问受保护 API 返回 401。
- systemd 服务仅监听 `127.0.0.1:8011`，由现有 HTTPS Nginx 路径代理。
- `/etc/hook-studio` 与秘密文件不进 Git；前端生产 bundle 二次扫描无密钥。
- OSS 备份上传成功且本地包校验通过；恢复到隔离临时目录后 SQLite `PRAGMA integrity_check=ok`。
- 维护 timer 处于 active，每日执行健康、备份、Insights。
