ARG PYTHON_BASE_IMAGE=python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7
FROM ${PYTHON_BASE_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_TRUSTED_HOST=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
    python -m pip install --upgrade pip \
    && PIP_INDEX_URL="${TORCH_INDEX_URL}" PIP_TRUSTED_HOST="${TORCH_TRUSTED_HOST}" \
    python -m pip install torch \
    && PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" \
    python -m pip install -r requirements.txt

COPY app ./app
COPY evaluation ./evaluation

RUN mkdir -p /app/data/uploads /app/logs

EXPOSE 8001 8000

CMD ["python", "-m", "app.api"]
