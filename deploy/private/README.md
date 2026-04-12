# APOLLO Private — オンプレデプロイ手順

社外秘特許データを外部 API に出さず、**完全エアギャップ運用可能な** APOLLO の
配布版です。埋め込み・チャット・マルチモーダルは全てローカル LM Studio /
Ollama 等の OpenAI 互換エンドポイントで実行されます。

## 動作要件

| 項目 | 要件 |
|---|---|
| Docker Engine | 20.10+ |
| Docker Compose | v2.0+ |
| LM Studio / Ollama 等 | `/v1/embeddings` と `/v1/chat/completions` を提供する OpenAI 互換サーバ |
| 埋め込みモデル | 多言語対応推奨 (Qwen3-Embedding-4B / bge-m3 など) |
| チャット + Vision モデル | Gemma 4 / Qwen3-VL などのマルチモーダル対応モデル (VOYAGER のレポート生成で必須) |
| GPU | 4B クラスのモデルを稼働させるなら 8GB+ VRAM 推奨 |

## セットアップ

### 1. LM Studio / Ollama 側にモデルをロード

```bash
# Ollama の場合（例）
ollama pull bge-m3
ollama pull qwen2.5vl

# LM Studio の場合は GUI から「Local Server」を起動し、以下をロード:
#   - text-embedding-qwen3-embedding-4b
#   - google/gemma-4-26b-a4b
```

`http://localhost:1234/v1/models` (LM Studio) または
`http://localhost:11434/v1/models` (Ollama) で疎通確認:

```bash
curl http://localhost:1234/v1/models | jq
```

### 2. .env を作成

```bash
cd deploy/private
cp .env.example .env
```

エディタで `.env` を開き、以下を埋める:

- `LM_STUDIO_BASE_URL` — エンドポイント URL (デフォルト: `http://host.docker.internal:1234/v1`)
- `APOLLO_EMBEDDING_MODEL` — ロード済み埋め込みモデル ID
- `APOLLO_CHAT_MODEL` — ロード済みチャット (Vision 対応) モデル ID
- `APOLLO_COOKIE_SECRET` — `openssl rand -hex 32` で生成
- `APOLLO_DATA_DIR` — ホスト側のデータ永続化パス (例: `/srv/apollo-data`)

### 3. users.yml を準備

**パスワードハッシュを生成:**

```bash
just hash-password
# プロンプトで入力したパスワードの bcrypt ハッシュが出力される
```

`deploy/private/users.example.yml` をコピーして、ハッシュと cookie.key
（`.env` の `APOLLO_COOKIE_SECRET` と同じ値）を入れ、
`${APOLLO_DATA_DIR}/users/users.yml` に配置:

```bash
mkdir -p "${APOLLO_DATA_DIR:-./apollo-data}/users"
cp deploy/private/users.example.yml "${APOLLO_DATA_DIR:-./apollo-data}/users/users.yml"
# エディタでパスワードハッシュと cookie.key を貼り付け
```

### 4. コンテナ起動

```bash
just up
# or
docker compose -f deploy/private/docker-compose.yml up -d
```

### 5. ブラウザでアクセス

http://localhost:8501

ログイン画面が出るので、`users.yml` に登録した認証情報で入る。
サイドバーに `🔒 Private Edition` バッジが出れば成功。

## just コマンド早見表

| コマンド | 用途 |
|---|---|
| `just build` | Docker イメージをビルド |
| `just push` | Docker Hub に push (build 依存) |
| `just up` | compose でバックグラウンド起動 |
| `just down` | 停止・コンテナ削除 |
| `just logs` | コンテナログを追跡 |
| `just hash-password` | bcrypt パスワードハッシュ生成 |
| `just check-lm-studio` | LM Studio の `/v1/models` を確認 |
| `just dev-private` | Docker を使わずローカルで private モード起動（開発用） |

## トラブルシューティング

### `host.docker.internal` が解決できない (Linux)

`docker-compose.yml` で `extra_hosts: host.docker.internal:host-gateway`
を設定済みですが、古い Docker では効かないことがあります。その場合は
`.env` の `LM_STUDIO_BASE_URL` を **ホストの LAN IP** に直接書き換えてください:

```
LM_STUDIO_BASE_URL=http://192.168.1.22:1234/v1
```

また LM Studio 側で **Serve on Local Network** を ON にして 0.0.0.0 に
バインドさせる必要があります（デフォルトは 127.0.0.1 のみ）。

### 埋め込みジョブが長時間 `running` のまま

数万件で 4B モデルを使う場合は数十分かかることがあります。GPU 使用状況を
確認してください:

```bash
nvidia-smi    # LM Studio 側のホストで
```

それでも進まない場合は `just logs` でコンテナログを確認。LM Studio の
`/v1/embeddings` エンドポイントがエラーを返していないかチェック。

### ユーザー設定ファイルが見つかりません

`${APOLLO_DATA_DIR}/users/users.yml` のパスと、コンテナ内マウント先
`/var/lib/apollo/users/users.yml` が一致しているか確認してください。
権限問題の場合は以下でコンテナの UID (10001) に合わせます:

```bash
sudo chown -R 10001:10001 "${APOLLO_DATA_DIR:-./apollo-data}"
```

### VOYAGER のマルチモーダル呼び出しが失敗する

ロードされているチャットモデルが **Vision 非対応**の可能性があります。
`/v1/models` で確認し、`APOLLO_CHAT_MODEL` を Vision 対応モデル
（`google/gemma-4-26b-a4b` / `qwen/qwen3-vl-8b` など）に変更してください。

## セキュリティ注意事項

- `.env` と `users.yml` は**絶対に git にコミットしない**こと。
  `.gitignore` で除外済み
- `APOLLO_COOKIE_SECRET` は**共有しない**こと。漏洩したら全セッションが
  偽装できる
- `users.yml` のパスワードハッシュは bcrypt 済みのものだけを入れる。
  平文を置かないこと
- 本番運用では LM Studio のエンドポイントに**外部からアクセスできない**
  ネットワーク設定にすること（LAN 限定バインド推奨）
