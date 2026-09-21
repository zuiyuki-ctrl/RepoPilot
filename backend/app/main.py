from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

import logging

from .db.session import check_database_connection
from .core.config import APP_NAME
from .api.routes import repositories, tasks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title=APP_NAME)
app.include_router(repositories.router)
app.include_router(tasks.router)

# 增加 GET /health，响应为 {"status": "ok"}。本次先把它定义为进程存活检查；数据库就绪单独验证
# 进程存活检查：能处理请求即可返回成功，不依赖数据库连接状态。
@app.get("/health")
async def health():
    logger.info("Health check requested")
    return {"status": "ok"}

# 数据库连接就绪检查；不验证业务表是否已迁移，数据库异常时返回 503。
@app.get("/ready")
def ready():
    try:
        check_database_connection()
    except SQLAlchemyError:
        logger.warning("Database readiness check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {"status": "ready"}
