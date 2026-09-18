import os
from pathlib import Path

from dotenv import load_dotenv

# 以项目根目录 .env 补充配置；已有进程环境变量默认优先，配置在模块导入时读取。
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

APP_NAME = os.getenv("APP_NAME", "RepoPilot")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
# 系统工作副本的父目录，与用户提供的 source_path 分开；每次注册创建一个子目录。
WORKSPACE_ROOT = Path(
    os.getenv("WORKSPACE_ROOT", "D:/RepoPilot-workspaces")
).resolve()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
EMBEDDING_ENDPOINT = os.getenv("EMBEDDING_ENDPOINT", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))


