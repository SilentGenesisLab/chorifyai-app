# Image Edit V1 Module WorkOrder

```yaml
module_id: image-edit-v1
objective: 打通可追溯的图片直连编辑与确定性降级链，并让多客户生产队列公平可观测
visible_result: 用户可在对话中上传原图、可选PNG蒙版和可选定位图，提交后看到进度并获得可下载版本
source_truth:
  - 用户本轮已确认的编辑与队列要求
  - ai-video-kernel 已验证的 /v1/images/edits 中继能力
  - .agents/skills/hook-studio-image-router
in_scope:
  - 服务端图片编辑端点与原图外像素回填
  - 提示词参考重绘与mask像素合成降级
  - 按客户轮转的图片和视频队列
  - 批量视频逐版本执行，避免单任务占满全部Provider并发
  - 对话、素材、合同、版本、运行与事件的管理员导出
  - 局部修图前端入口、任务进度与成品预览
out_of_scope:
  - 安装第三方Skill或新增运行时依赖
  - 自动A/B测试
  - 把箭头、文字、九宫格或固定全局槽位设为硬条件
  - 宣称mask严格约束模型或AI概念图等同CAD/UI代码
done_when:
  - kernel局部编辑测试通过且真实探针留证
  - Hook Studio局部编辑纵向测试通过
  - 公平队列顺序测试与批量串行占槽测试通过
  - 管理员全量数据导出测试通过
  - 前端构建、Playwright关键流程与独立Inspector完成
time_budget: 原子动作不超过15分钟，失败两次立即换路
owner: /root
inspector: 复用独立子代理，只读取本文件、改动清单和验收证据
rollback: 保留旧生成端点；局部编辑失败自动转参考重绘，带mask时再做原像素合成
```

## 执行顺序

1. 固化直连编辑合同、版本表和图片路由 Skill。
2. 补局部编辑端到端测试并修正数据迁移。
3. 替换 FIFO 为按客户轮转队列，批量版本逐个占用 Provider 槽位。
4. 增加管理员完整数据包导出，并在后台显示编辑合同和资产版本数量。
5. 构建、Playwright、真实公网验收，最后部署与推送。
