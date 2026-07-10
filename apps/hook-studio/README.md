# Hook Studio

面向跨境电商剪辑师的图片/视频钩子生成控制面。FastAPI 负责访问码鉴权、
服务端配额、事件留存和生成编排；浏览器不直连模型供应商，也不持有密钥。

## 本地开发

```powershell
Copy-Item .env.example .env
Copy-Item config/access_codes.example.yaml config/access_codes.yaml
python -m pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload --port 8010
```

真实 `config/access_codes.yaml`、`.env`、SQLite 和日志均不得提交。部署与完整操作
以仓库根目录的 `OPERATOR_MANUAL.md` 为准。

