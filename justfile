set dotenv-load := true
set shell := ["bash", "-cu"]

DOCKER_NAMESPACE := env_var_or_default("DOCKER_NAMESPACE", "jl1nie")
IMAGE_NAME := "apollo-private"
VERSION := `grep '^version' pyproject.toml | head -1 | sed -E 's/version\s*=\s*"([^"]+)"/\1/'`

default:
    @just --list

# 依存解決 (core のみ)
sync:
    uv sync

# private 開発用 (LM Studio + 認証 extras を含める)
sync-private:
    uv sync --extra private

# ローカルで hosted モード起動 (HF Spaces 相当 / Gemini API)
dev:
    APOLLO_MODE=hosted uv run streamlit run Home.py

# ローカルで private モード起動 (LM Studio 必須)
dev-private:
    APOLLO_MODE=private uv run --extra private streamlit run Home.py

# Docker イメージビルド
build:
    docker build -f deploy/private/Dockerfile -t {{DOCKER_NAMESPACE}}/{{IMAGE_NAME}}:{{VERSION}} .
    docker tag {{DOCKER_NAMESPACE}}/{{IMAGE_NAME}}:{{VERSION}} {{DOCKER_NAMESPACE}}/{{IMAGE_NAME}}:latest

# Docker Hub へ push (build 依存)
push: build
    docker push {{DOCKER_NAMESPACE}}/{{IMAGE_NAME}}:{{VERSION}}
    docker push {{DOCKER_NAMESPACE}}/{{IMAGE_NAME}}:latest

# compose で起動
up:
    docker compose -f deploy/private/docker-compose.yml up -d

down:
    docker compose -f deploy/private/docker-compose.yml down

logs:
    docker compose -f deploy/private/docker-compose.yml logs -f

# Lint / Format
lint:
    uv run ruff check .

fmt:
    uv run ruff format .
    uv run ruff check --fix .

# LM Studio 疎通確認
check-lm-studio:
    curl -s "${LM_STUDIO_BASE_URL:-http://localhost:1234/v1}/models" | python3 -m json.tool
