# Hook Studio 运维手册

## 网址和入口

- 公网网址：`https://chorifyai.sligenai.cn/hook-studio/`
- 客户码登录后进入生产工作台；管理码登录后自动进入管理后台。
- 健康探针：`https://chorifyai.sligenai.cn/hook-studio/healthz`
- GitHub：`https://github.com/SilentGenesisLab/chorifyai-app/tree/feature/hook-studio-chat-os/apps/hook-studio`

访问码不要写进聊天、截图或文档。真实码只在服务器 `/etc/hook-studio/access_codes.yaml` 和本地 secret 文件中。

## 剪辑师怎么用

1. 输入访问码。左下角会显示账号名、今日图片额度和视频额度。
2. 在输入框左下选择工具：视频生产、图片生产、局部修图、参控复刻、批量生产、逆向分析或定向替换。
3. 在中间像聊天一样描述需求，可同时上传文本、PDF、DOCX、XLSX、PPTX、图片、视频、音频或网页/平台链接。
4. 视频任务如果没填时长，系统会回问。可直接填 4-60 秒；系统自动拆成若干 4-15 秒镜头，超过 60 秒会明确拒绝。
5. 视频镜头会按复杂度返回 1 张关键结果、2 张动作起止或 3 张动作序列。镜头表和分镜带同步；需要核对节奏时再生成动态预演。
6. 不满意时可只重生当前画格、重生当前整镜或切换历史候选；修改后必须重新批准对应画格和镜头。动态预演若已生成，也必须重新确认。
7. 必需画格、全部镜头和整板确认后会显示最终额度确认；动态预演不是硬条件，但已生成而未确认时会阻止生产。
8. 中间执行卡分别显示图片与视频的等待、执行、成功、失败数量；右侧只放资产库、选中预览和成品库。
9. 在成品库勾选多个结果后点“批量下载”，系统会打成 ZIP。

局部修图至少上传一张未标注原图并说明要改什么。PNG 蒙版和带箭头/文字的定位图都是可选的：蒙版透明区域表示允许修改；定位图只帮助说明位置，不会作为最终成品。系统先尝试原生编辑，失败时自动降级为参考重绘；有蒙版时会再把蒙版外像素从原图回填。

参控复刻只复刻镜头结构、动作因果和节奏，产品身份由参考图片锁定，不复制原人物、品牌、字幕或音乐。定向替换需要源视频和替换参考图；在文字里写清楚时间段和要替换的场景、商品、人物或物品。只上传源视频并明确写“替换声音/口播”，会走真实 TTS 和 FFmpeg 换声链路。

## 额度规则

- 全站视频每日硬上限默认 100 条，UTC+8 零点重置。
- 每个客户的视频子额度在管理后台设置，不能超过 100。
- 每个客户图片每日上限 1000 张。
- 故事板和重生画格计入图片额度；最终确认后，实际生产镜头数计入视频额度。
- 图片生产队列和视频生产队列分开；同一队列按客户轮转，批量任务不会一次占满全部 Provider 槽。服务端原子预留额度，失败自动释放。

## 管理后台

管理码登录后可完成：

- 看各客户图片/视频用量；
- 直接修改客户图片或视频日额度；
- 启用、停用访问码；
- 修改全站视频日上限；
- 查看对话、消息、素材、任务和训练样本数量；
- 导出完整数据 ZIP、训练 JSONL 与事件 JSONL。完整包包含对话、素材、任务、镜头、审批、Skill 运行、图片编辑合同、资产版本、事件和训练样本，不包含访问码或服务端密钥。

发码时只把某一个 `code` 单独发给对应客户。收码时在后台切成“已停用”，该客户已有登录会在下一次 API 请求立即失效。手工新增客户时，在 `/etc/hook-studio/access_codes.yaml` 的 `codes` 下添加唯一 `id`、随机 `code`、客户名和额度，然后重启 `hook-studio` 让新码生效。

## 日常检查

```bash
sudo systemctl status hook-studio --no-pager
curl --fail http://127.0.0.1:8011/healthz
sudo journalctl -u hook-studio -n 200 --no-pager
sudo systemctl status hook-studio-maintenance.timer --no-pager
```

正常标准：服务是 `active`、healthz 返回 `{"status":"ok"}`、维护 timer 是 `active (waiting)`。

## 重启服务

```bash
sudo systemctl restart hook-studio
sleep 4
curl --fail http://127.0.0.1:8011/healthz
```

服务重启后会从 SQLite 恢复未完成任务；浏览器提交带幂等标识，刷新和 SSE 重连不会新建同一任务，但操作者仍不要重复创建同一需求。

## 备份和恢复

每天 03:15（UTC+8）自动备份 SQLite 与 `events.jsonl`，上传 OSS，本机保留最近 30 份。

```bash
sudo systemctl start hook-studio-maintenance.service
sudo journalctl -u hook-studio-maintenance -n 100 --no-pager
ls -lh /var/lib/hook-studio/backups
```

恢复前先验证。真正覆盖生产数据时必须先停服务：

```bash
cd /opt/hook-studio/current
source .venv/bin/activate
python scripts/restore_backup.py /var/lib/hook-studio/backups/备份文件.tar.gz --verify-only
sudo systemctl stop hook-studio
python scripts/restore_backup.py /var/lib/hook-studio/backups/备份文件.tar.gz
sudo systemctl start hook-studio
curl --fail http://127.0.0.1:8011/healthz
```

2026-07-10 已做隔离恢复演练：最新备份恢复到 `/tmp/hook-studio-restore-drill-20260710`，SQLite `integrity_check=ok`，对话、消息、素材、任务、训练样本和额度账本均可读取。

## 三步排障

1. **网页打不开**：先查 `healthz` 和 systemd；本机正常再查 `sudo nginx -t` 与 Nginx 日志。
2. **登录或额度异常**：看访问码是否启用、客户子额度、全站视频用量和 UTC+8 重置时间，不要直接改 SQLite。
3. **生成失败**：先看右侧失败信息和任务阶段，再查 service 日志。Kernel 会在超时或 5xx 时自动重试一次；仍失败就保留原任务记录，确认 provider 恢复后再从对话重发，不要连续点按钮。

## 服务器位置

- 当前版本：`/opt/hook-studio/current`
- 历史版本：`/opt/hook-studio/releases/`
- 数据：`/var/lib/hook-studio`
- 服务端环境和访问码：`/etc/hook-studio/`
- systemd：`hook-studio.service`、`hook-studio-maintenance.timer`

环境文件中的 Kernel、TTS、Crawler 等密钥只允许服务端读取，前端 bundle 不得出现任何 provider 密钥。
