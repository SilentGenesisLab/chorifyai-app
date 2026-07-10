# Hook Studio 运维手册

## 网址

- 客户与管理入口：`https://chorifyai.sligenai.cn/hook-studio/`
- 管理码登录后自动进入管理后台。
- 健康探针：服务器本机 `http://127.0.0.1:8011/healthz`

## 客户怎么用

1. 打开网址，输入分配的客户访问码。
2. 选择图片钩子或视频钩子。
3. 选择拍法预设，填写一句产品描述，可选上传清晰参考图。
4. 点击开始生成，在右侧或下方查看队列位置与预计时间。
5. 完成后在最近生成中预览、下载、重新生成或删除。

视频固定 4-5 秒、9:16，并在服务端检查动作因果、原生声音意图、成片音轨、时长和比例。图片不限日量；视频全站每日 100 条，UTC+8 重置。

## 发码与收码

真实访问码只在服务器：`/etc/hook-studio/access_codes.yaml`。

- 发码：把对应客户的 `code` 单独发给客户，不要发送整个 YAML。
- 收码：管理后台把客户状态切到“已停用”；已有 session 会在下一次 API 请求立即失效。
- 改配额：管理后台修改客户日配额；0 表示该客户不能生成视频，但仍可生成图片。
- 新增客户：在 YAML 的 `codes` 下复制一个 client 记录，使用新的 `id` 和随机 `code`，然后刷新管理后台；无需重启。

## 全站上限和并发

- 管理后台可立即修改全站视频日上限。
- 图片并发与视频并发分别由环境变量控制；修改后重启生效。
- 环境文件：`/etc/hook-studio/hook-studio.env`

## 服务命令

```bash
sudo systemctl status hook-studio --no-pager
sudo systemctl restart hook-studio
sudo journalctl -u hook-studio -n 200 --no-pager
curl --fail http://127.0.0.1:8011/healthz
```

## 备份

每日 03:15（UTC+8）自动运行健康检查、SQLite/事件日志备份、OSS 上传与 Insights。

```bash
sudo systemctl status hook-studio-maintenance.timer --no-pager
sudo systemctl start hook-studio-maintenance.service
sudo journalctl -u hook-studio-maintenance -n 100 --no-pager
ls -lh /var/lib/hook-studio/backups
```

本地保留最近 30 份；OSS URL 和校验状态显示在管理后台。

## 恢复

先验证，再停服务恢复：

```bash
cd /opt/hook-studio/current
source .venv/bin/activate
python scripts/restore_backup.py /var/lib/hook-studio/backups/备份文件.tar.gz --verify-only
sudo systemctl stop hook-studio
python scripts/restore_backup.py /var/lib/hook-studio/backups/备份文件.tar.gz
sudo systemctl start hook-studio
curl --fail http://127.0.0.1:8011/healthz
```

## 三步排障

1. **网页打不开**：运行 `systemctl status` 和本机 `healthz`；若本机正常，检查 `sudo nginx -t` 与 Nginx 日志。
2. **登录或额度异常**：检查访问码是否启用、客户日配额、全站今日用量；不要直接改 SQLite。
3. **生成失败**：在管理后台看错误码和请求 ID，再查 service 日志。`SKILL_GATE_BLOCKED` 先改描述或参考图；`PROVIDER_TIMEOUT` 用原 job ID 继续观察，不要手工重复提交。

## 代码与发布

- GitHub：`https://github.com/SilentGenesisLab/chorifyai-app/tree/main/apps/hook-studio`
- 发布顺序：`feature/hook-studio-v1` -> `uat` -> `main`
- 运行目录：`/opt/hook-studio/current`
- 数据目录：`/var/lib/hook-studio`
- 服务端秘密：`/etc/hook-studio/`，权限必须为 600，不得提交 Git。

