# Explicit operator build only; no platform auto-build/pull or dependency install.
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}
COPY demo.py /agent/demo.py
USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["python", "-I", "/agent/demo.py"]
