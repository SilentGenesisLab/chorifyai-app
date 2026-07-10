# Hook Studio

面向跨境电商剪辑师的 Codex 式多模态图片/视频生产工作台。支持多对话、
多格式素材与链接解析、故事板确认、60 秒以上分段生产、参控复刻、批量生产、
逆向分析、定向替换、换声、任务可观测和训练数据导出。

FastAPI 负责访问码鉴权、服务端配额、SQLite/JSONL 留存和 Kernel 编排；
浏览器不直连模型供应商，也不持有密钥。公网入口见 [运维手册](OPERATOR_MANUAL.md)。

## 本地开发

```powershell
Copy-Item .env.example .env
Copy-Item config/access_codes.example.yaml config/access_codes.yaml
python -m pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload --port 8010

cd frontend
npm ci
npm run dev
```

真实 `config/access_codes.yaml`、`.env`、SQLite 和日志均不得提交。部署与完整操作
以仓库根目录的 `OPERATOR_MANUAL.md` 为准。

