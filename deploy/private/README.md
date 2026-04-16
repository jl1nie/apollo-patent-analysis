# APOLLO Private v7 — Docker Desktop で起動する

Windows / macOS の **Docker Desktop** で APOLLO Private を起動するためのマニュアルです。
基本は Docker Desktop の GUI だけで完結します。ターミナル操作は不要。

## 1. 前提ソフトウェア

| ソフト | 用途 | 入手先 |
|---|---|---|
| **Docker Desktop** | コンテナ実行 | <https://www.docker.com/products/docker-desktop/> |
| **LM Studio** | ローカル LLM サーバ (埋め込み + チャット) | <https://lmstudio.ai/> |

GPU 推奨 (NVIDIA / Apple Silicon)。

## 2. LM Studio の準備

LM Studio を起動し、以下の 2 モデルをダウンロード:

| 用途 | モデル ID (LM Studio の検索欄に貼る) |
|---|---|
| 埋め込み | `text-embedding-qwen3-embedding-4b` (Qwen3-Embedding-4B) |
| チャット | `qwen/qwen3-30b-a3b-2507` など任意 (VOYAGER 用) |

ダウンロード後、**Developer タブ → Server を Start** し、両モデルを Load。
`http://localhost:1234` で OpenAI 互換 API が立ち上がります。

> **疎通確認**: ブラウザで <http://localhost:1234/v1/models> を開いて JSON が返れば OK。

## 3. APOLLO Private イメージを取得 (GUI)

1. Docker Desktop を開く → 左メニュー **Images**
2. 上部の検索バーに `jl1nie/apollo-private` と入力
3. **Pull** をクリック (約 2〜3 GB、初回のみ)

> イメージが見つからない場合は、まだ Docker Hub に push されていない可能性があります。
> その場合はメンテナに連絡するか、後述の「ソースからビルド」を参照してください。

## 4. データ永続化用 Volume を作成 (GUI)

埋め込みキャッシュ等を残すための名前付き volume を先に作っておきます。

1. 左メニュー **Volumes** → **Create**
2. **Volume name**: `apollo-private-data`
3. **Create** クリック

> このステップを飛ばしてもアプリは動きますが、コンテナを削除するとキャッシュが消えます。

## 5. コンテナを起動 (GUI)

1. 左メニュー **Images** に戻る → `jl1nie/apollo-private` の **Run** ボタン (▶) をクリック
2. **Optional settings** を展開し、以下を入力:

   | 項目 | 値 |
   |---|---|
   | **Container name** | `apollo-private` |
   | **Ports** → Host port | `8501` |
   | **Volumes** → Host path | `apollo-private-data` (Step 4 で作った volume 名) |
   | **Volumes** → Container path | `/var/lib/apollo` |
   | **Environment variables** → Variable | `APOLLO_ADMIN_PASSWORD` |
   | **Environment variables** → Value | お好きなパスワード |

3. **Run** をクリック

> **LAN の別 PC で LM Studio を動かしている場合**は、もう 1 つ環境変数を追加:
> `LM_STUDIO_BASE_URL` = `http://192.168.1.22:1234/v1` (IP は環境に合わせて)

## 6. アクセス

ブラウザで <http://localhost:8501> を開く → ログイン画面 → ユーザ名 `admin` +
Step 5 で設定したパスワードでログイン → APOLLO の画面が出れば成功。

## 7. 停止 / 再起動 / 削除 (GUI)

Docker Desktop の **Containers** タブから:

- **Stop** ボタン: コンテナ停止 (データは残る)
- **Start** ボタン: 再開
- **Delete** (ゴミ箱): コンテナ削除 (volume はそのまま、データは残る)
- **Volumes** タブで `apollo-private-data` を削除すると埋め込みキャッシュも完全削除

## 環境変数一覧 (Run ダイアログで設定可能)

必要になったら追加:

| 変数 | デフォルト | 用途 |
|---|---|---|
| `APOLLO_ADMIN_PASSWORD` | 空 (= 認証無効) | 管理者パスワード。共有 PC で使うなら必須 |
| `APOLLO_ADMIN_USER` | `admin` | 管理者ユーザ名 |
| `LM_STUDIO_BASE_URL` | `http://host.docker.internal:1234/v1` | LAN の別 PC の LM Studio を使う場合は IP に変更 |
| `APOLLO_EMBEDDING_MODEL` | `text-embedding-qwen3-embedding-4b` | 別の埋め込みモデルを使う場合 |
| `APOLLO_CHAT_MODEL` | `qwen/qwen3-30b-a3b-2507` | VOYAGER 用 chat model |
| `APOLLO_COOKIE_SECRET` | コンテナ毎にランダム生成 | 32 文字以上を指定すると Docker Desktop の再起動後もログイン状態を保持 |

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| ログイン画面が出ず、サイドバーに赤い警告 | `APOLLO_ADMIN_PASSWORD` が空。コンテナを Stop → Run ダイアログで env を追加 → 再 Run |
| 「LM Studio に接続できません」エラー | LM Studio が起動していない / Server を Start し忘れ。<http://localhost:1234/v1/models> で疎通確認 |
| 埋め込みが途中で止まる | LM Studio 側で埋め込みモデルが Load されていない |
| OpenALEX タブで「エアギャップ環境」警告 | 想定通り。Private モードでは外部 API は使えません |
| 再起動でログインを毎回求められる | 環境変数 `APOLLO_COOKIE_SECRET` に 32 文字以上の固定値を設定 |
| ポート 8501 が使われている | Run ダイアログの Host port を `18501` 等に変更 → <http://localhost:18501> でアクセス |

---

## 補足: docker compose / CLI で起動する

繰り返し設定を再現したい / チームで共有したい場合は compose ファイル経由が便利です。

```
git clone https://github.com/jl1nie/apollo-patent-analysis.git
cd apollo-patent-analysis
git checkout apollo-private-v7
cp deploy/private/.env.example deploy/private/.env
# .env を編集して APOLLO_ADMIN_PASSWORD= に値を入れる
docker compose -f deploy/private/docker-compose.yml up -d
```

停止 / 削除:

```
docker compose -f deploy/private/docker-compose.yml stop      # 停止 (データ保持)
docker compose -f deploy/private/docker-compose.yml down      # 削除 (volume 残る)
docker compose -f deploy/private/docker-compose.yml down -v   # 完全削除
```

データ取り出し:

```
docker compose -f deploy/private/docker-compose.yml cp apollo:/var/lib/apollo ./apollo-data-backup
```

## 補足: ソースからビルド

Docker Hub にイメージが無い、または最新コードでビルドしたい場合:

```
git clone https://github.com/jl1nie/apollo-patent-analysis.git
cd apollo-patent-analysis
git checkout apollo-private-v7
docker build -f deploy/private/Dockerfile -t jl1nie/apollo-private:latest .
```

## モード切替 (上級者向け)

同じイメージで `APOLLO_MODE=hosted` を環境変数で上書きすると、Gemini API +
ローカル SBERT の hosted モード (HF Spaces 相当) に切り替わります。Private モード
固有の認証・LM Studio 接続は無効化されます。
