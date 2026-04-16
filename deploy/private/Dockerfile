# syntax=docker/dockerfile:1.6
# ==================================================================
# APOLLO Private v7 — Docker イメージ
# ==================================================================
# Multi-stage + BuildKit cache mount で rebuild を高速化する。
# - Stage 1 (builder): pip で requirements.txt + private extras を解決
# - Stage 2 (runtime): python:3.12-slim に日本語フォントと chromium のみ追加
#
# v6 と異なり patiroha[all] が torch / sentence-transformers を内部で引くため
# イメージサイズ削減目的の hosted/private 分離はできない。private モード固有の
# 追加依存は openai / streamlit-authenticator / bcrypt / PyYAML のみ。
#
# ビルド: `just build`
#   または: DOCKER_BUILDKIT=1 docker build -f deploy/private/Dockerfile \
#             -t jl1nie/apollo-private:VERSION .
# ==================================================================

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=0 \
    PYTHONUNBUFFERED=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends build-essential

WORKDIR /app

# 依存解決はプロジェクトコードより先にやってレイヤーキャッシュを効かせる。
# torch は CPU-only wheel を先に入れて約 1.8GB 削減する (private モードでは
# LM Studio がホスト側で GPU 推論を担当するため、コンテナ内 torch は
# Saturn V の死んだ import と patiroha の transitive load しか触れない。
# hosted モードでも HF Spaces 無料枠は CPU 実行なので CUDA wheels は元々不要)。
COPY requirements.txt /app/
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip && \
    /app/.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch && \
    /app/.venv/bin/pip install -r /app/requirements.txt && \
    /app/.venv/bin/pip install \
        "openai>=1.40.0" \
        "streamlit-authenticator>=0.3.2" \
        bcrypt \
        PyYAML

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim-bookworm AS runtime

# 日本語フォント (matplotlib / wordcloud) + chromium (Plotly→PNG) + curl (HEALTHCHECK)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-ipafont-gothic \
        chromium \
        curl

# 非 root ユーザー (固定 UID で volume 所有者を予測可能に)
RUN useradd -u 10001 -m -d /home/apollo -s /bin/bash apollo

COPY --from=builder --chown=apollo:apollo /app/.venv /app/.venv

WORKDIR /app
COPY --chown=apollo:apollo . /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APOLLO_MODE=private \
    APOLLO_DATA_ROOT=/var/lib/apollo \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_THEME_BASE=light \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1

RUN mkdir -p /var/lib/apollo && chown -R apollo:apollo /var/lib/apollo

USER apollo
EXPOSE 8501
VOLUME ["/var/lib/apollo"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "Home.py"]
