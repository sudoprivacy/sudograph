FROM python:3.12-slim AS compiler-build
WORKDIR /build
COPY pyproject.toml README.md ./
COPY compiler ./compiler
COPY app ./app
COPY nexus-client ./nexus-client
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels .

FROM python:3.12-slim
WORKDIR /opt/sudograph
COPY --from=compiler-build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY infra/gitlab/worker.py ./infra/gitlab/worker.py
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
CMD ["python", "-m", "compiler.managed", "/state/policy.json", "--wait-config", "--bind", "0.0.0.0"]
