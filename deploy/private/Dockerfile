# syntax=docker/dockerfile:1.6
# ==================================================================
# APOLLO Private — Docker イメージ
# ==================================================================
# Multi-stage + BuildKit cache mount で rebuild を高速化する。
# - Stage 1 (builder): uv で依存解決（torch / sentence-transformers を
#   含む hosted 依存は引かない → 約 2GB 削減）
# - Stage 2 (runtime): python:3.12-slim に日本語フォントと chromium のみ
#   追加し、builder から .venv をコピー
#
# キャッシュ戦略:
# - `/var/cache/apt`, `/var/lib/apt`: type=cache,sharing=locked で apt
#   ダウンロードキャッシュをレイヤー外に切り出し (rm -rf 不要)
# - `/root/.cache/uv`: type=cache で uv の wheel ダウンロードキャッシュ
# - 初回ビルド後、pyproject.toml / uv.lock / OS パッケージリストが
#   変わらない限り、rebuild は数秒で完了
#
# ビルド: `just build` もしくは以下と等価
#   DOCKER_BUILDKIT=1 docker build -f deploy/private/Dockerfile \
#     -t jl1nie/apollo-private:VERSION .
# ==================================================================

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim-bookworm AS builder

# uv バイナリを公式イメージからコピー（パッケージインストール不要）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# ビルド依存（numpy<2 などの一部パッケージが wheel でない場合に必要）。
# BuildKit cache mount で apt キャッシュをレイヤー外に保持する
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends build-essential

WORKDIR /app

# 依存解決はプロジェクトコードより先にやってレイヤーキャッシュを効かせる。
# さらに uv の wheel キャッシュも BuildKit cache mount に切り出す
COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra private

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim-bookworm AS runtime

# 日本語フォント (matplotlib / wordcloud 用) + chromium (Kaleido の
# Plotly → PNG 変換用) + curl (HEALTHCHECK 用)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-ipafont-gothic \
        chromium \
        curl

# 非 root ユーザーで実行する（volume 所有者の予測可能性のため固定 UID）
RUN useradd -u 10001 -m -d /home/apollo -s /bin/bash apollo

# builder から .venv をコピー（書き込み不要なので所有者は apollo で十分）
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
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# マウントされないケースに備えて空ディレクトリを準備
RUN mkdir -p /var/lib/apollo && chown -R apollo:apollo /var/lib/apollo

USER apollo
EXPOSE 8501
VOLUME ["/var/lib/apollo"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "Home.py"]
