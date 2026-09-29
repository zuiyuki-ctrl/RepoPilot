# 这里不使用现有的 [backend/Dockerfile]
# 因为它是 RepoPilot API 的运行镜像，包含 FastAPI、数据库驱动和 LangGraph 等依赖；
# 测试沙箱应该保持独立、最小化。
FROM python:3.11-slim

# 防止 Python 缓冲日志，并禁止生成 .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1


# 创建 GID 10001 的 sandbox 组，以及 UID 10001 的低权限用户。
# 不创建 home，不初始化登录日志，并禁止交互登录。
RUN groupadd --gid 10001 sandbox \
    && useradd \
        --uid 10001 \
        --gid sandbox \
        --no-create-home \
        --no-log-init \
        --shell /usr/sbin/nologin \
        sandbox



# TODO 2：
# 只安装运行当前沙箱所必需的 pytest
RUN python -m pip install \
    --no-cache-dir \
    "pytest>=8,<9"


# 容器运行测试时的默认目录。
WORKDIR /workspace

# TODO 3：
# 切换到上面创建的非 root 用户。
# 使用固定数字 UID:GID 切换到非 root 用户。
USER 10001:10001

# 不写 CMD 或 ENTRYPOINT。
# 实际执行命令由 docker_test_service.py 固定传入。
