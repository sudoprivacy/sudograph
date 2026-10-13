FROM python:3.12-slim
WORKDIR /opt/sudograph
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY compiler ./compiler
COPY app ./app
COPY infra/gitlab/worker.py ./infra/gitlab/worker.py
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
CMD ["python", "-m", "compiler.managed", "/state/policy.json", "--wait-config", "--bind", "0.0.0.0"]
