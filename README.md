```text
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload
```

在项目根目录执行：
```text
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

验证接口：
```text
curl.exe -i http://127.0.0.1:8000/health
```