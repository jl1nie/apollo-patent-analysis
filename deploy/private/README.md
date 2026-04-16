# APOLLO Private v7.0-private.2 — Docker Desktop で起動する

Windows / macOS の **Docker Desktop** で APOLLO Private を起動するためのマニュアルです。
基本は Docker Desktop の GUI だけで完結します。ターミナル操作は不要。

> **v7.0-private.2 の主な拡張 (v7.0-private.1 からの差分):**
> - 📂 **プロジェクト階層**: 分析対象ドメイン (CNF / バッテリー…) 毎にベクトル空間と成果物を分離
> - 🖼️ **Vision VOYAGER**: レポート生成に snapshot 画像を送れる。vision 専用モデル選択可
> - 🤖 **ローカル AI サジェスト**: 各モジュールの AI Insight / ラベルサジェストが LM Studio 直接実行対応
> - 🔁 **Streaming**: 長文レポート生成中の進捗表示 (文字数 / 速度 / 末尾プレビュー)
> - 💾 **自動永続化**: CAPCOM セッションが自動開始、全分析成果物がプロジェクト配下に自動保存・再起動後に自動復元
> - 🎨 **UI 改善**: アクティブプロジェクトの banner 常時表示、サイドバー強化

## 1. 前提ソフトウェア

| ソフト | 用途 | 入手先 |
|---|---|---|
| **Docker Desktop** | コンテナ実行 | <https://www.docker.com/products/docker-desktop/> |
| **LM Studio** | ローカル LLM サーバ (埋め込み + チャット + Vision) | <https://lmstudio.ai/> |

GPU 推奨 (NVIDIA / Apple Silicon)。

## 2. LM Studio の準備

LM Studio を起動し、以下のモデルをダウンロード:

| 用途 | モデル ID (LM Studio の検索欄に貼る) | 備考 |
|---|---|---|
| **埋め込み** | `text-embedding-qwen3-embedding-4b` (Qwen3-Embedding-4B) | VRAM 少なければ `-0.6b` 版も可 |
| **チャット (VOYAGER)** | `qwen/qwen3-30b-a3b-2507` | text-only、日本語レポート品質高 |
| **Vision (任意)** | `qwen/qwen3-vl-8b` | VOYAGER Phase 1 で snapshot 画像を送る時のみ使用 |

ダウンロード後、**Developer タブ → Server を Start** し、全てのモデルを Load。
`http://localhost:1234` で OpenAI 互換 API が立ち上がります。

> **疎通確認**: ブラウザで <http://localhost:1234/v1/models> を開いて JSON が返れば OK。
> 複数モデルを Load した状態でも動作します (VOYAGER 呼び出し時にモデル ID で切替)。

## 3. APOLLO Private イメージを取得 (GUI)

1. Docker Desktop を開く → 左メニュー **Images**
2. 上部の検索バーに `jl1nie/apollo-private` と入力
3. **Pull** をクリック (約 2〜3 GB、初回のみ)

> イメージが見つからない場合は、まだ Docker Hub に push されていない可能性があります。
> その場合はメンテナに連絡するか、後述の「ソースからビルド」を参照してください。

## 4. データ永続化用 Volume を作成 (GUI)

プロジェクト階層・埋め込みキャッシュ・分析成果物を残すための名前付き volume を先に作っておきます。

1. 左メニュー **Volumes** → **Create**
2. **Volume name**: `apollo-private-data`
3. **Create** クリック

> このステップを飛ばしてもアプリは動きますが、コンテナを削除するとキャッシュとプロジェクトデータが消えます。

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

### 初回の使い方 (5 分で動作確認)

1. **左サイドバー**: `📂 アクティブプロジェクト` が `default` になっているのを確認
2. **🛰️ Mission Control 直下の banner** に `📂 アクティブプロジェクト: default | 🔒 埋め込み: qwen3-embedding-4b` が表示される
3. 特許 CSV をアップロード → プレビュー → 「分析エンジン起動」(前処理が走る、数分)
4. 各分析モジュール (Saturn V / MEGA / etc) を開く → 📸 Snapshot ボタンで保存 → 自動でディスクに永続化
5. VOYAGER でレポート生成 → ストリーミング進捗 (「生成中 N 文字 · 3 文字/秒 · 123 chunks」) が表示される

### プロジェクトを追加する場合

1. サイドバーの **➕ 新規** → 名前・埋め込みモデル・推論モデル・Vision モデル (任意) を入力
2. 作成後、自動でそのプロジェクトに切替わる
3. 別ドメイン (例: バッテリー特許) の CSV をアップロードすれば独立したベクトル空間で分析可能

## 7. 停止 / 再起動 / 削除 (GUI)

Docker Desktop の **Containers** タブから:

- **Stop** ボタン: コンテナ停止 (データは残る)
- **Start** ボタン: 再開 (サイドバーに戻ると直前の snapshot / データが自動復元される)
- **Delete** (ゴミ箱): コンテナ削除 (volume はそのまま、データは残る)
- **Volumes** タブで `apollo-private-data` を削除するとプロジェクトデータも完全削除

> **v7.0-private.2 での新機能**: 再起動後もプロジェクト配下の snapshot / CAPCOM データ / プロンプトは
> `st.toast` で通知された上で自動的に session_state に復元されます (再起動前の分析状態を継続可能)。

## 環境変数一覧 (Run ダイアログで設定可能)

必要になったら追加:

| 変数 | デフォルト | 用途 |
|---|---|---|
| `APOLLO_ADMIN_PASSWORD` | 空 (= 認証無効) | 管理者パスワード。共有 PC で使うなら必須 |
| `APOLLO_ADMIN_USER` | `admin` | 管理者ユーザ名 |
| `LM_STUDIO_BASE_URL` | `http://host.docker.internal:1234/v1` | LAN の別 PC の LM Studio を使う場合は IP に変更 |
| `APOLLO_EMBEDDING_MODEL` | `text-embedding-qwen3-embedding-4b` | default プロジェクトの埋め込みモデル (プロジェクト作成時に個別指定可) |
| `APOLLO_CHAT_MODEL` | `qwen/qwen3-30b-a3b-2507` | default プロジェクトの推論モデル (サイドバーで変更可) |
| `LM_STUDIO_TIMEOUT` | `7200` (秒) | 1 LLM 呼び出しあたりのタイムアウト。30B で VOYAGER Phase 3 (Strategist) は 30-60 分級。`0` で無制限 |
| `LM_STUDIO_MAX_TOKENS` | `65536` | 1 レスポンスの最大トークン数 (Gemini 互換) |
| `APOLLO_COOKIE_SECRET` | コンテナ毎にランダム生成 | 32 文字以上を指定すると Docker Desktop の再起動後もログイン状態を保持 |

## プロジェクトデータの構造 (/var/lib/apollo 配下)

```
projects/
├── .active                       # 現在アクティブな project_id
├── default/
│   ├── config.json               # 埋め込みモデル・推論モデル・Vision モデル・Mission
│   ├── files/{patents,academic,news,market,policy}/   # アップロード済 CSV
│   ├── state/{content_key}.pkl   # 前処理結果 (df_main + 埋め込み + TF-IDF)
│   ├── store/                    # 分析成果物の自動永続化先
│   │   ├── snapshots/*.png       # モジュール別のキャプチャ画像
│   │   ├── data/*.json           # CAPCOM データ (クラスタ/多様性指標等)
│   │   ├── prompts/*.md          # AI Insight プロンプト履歴
│   │   └── voyager/              # Mission / Context / Evidence
│   └── reports/                  # 生成レポート (MD/PDF/ZIP)
└── cnf/                          # 新規作成したプロジェクト
    └── ...
cache/embeddings/*.npy            # 全プロジェクト共有のベクトルキャッシュ
```

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| ログイン画面が出ず、サイドバーに赤い警告 | `APOLLO_ADMIN_PASSWORD` が空。コンテナを Stop → Run ダイアログで env を追加 → 再 Run |
| 「LM Studio に接続できません」エラー | LM Studio が起動していない / Server を Start し忘れ。<http://localhost:1234/v1/models> で疎通確認 |
| サイドバーに `⚠️ LM Studio 接続失敗` | 同上。失敗時は 60 秒キャッシュされるので、復旧後は「🔄 モデル一覧を再取得」で即時更新 |
| 埋め込みが途中で止まる | LM Studio 側で埋め込みモデルが Load されていない |
| Vision モデルに切替えたのに画像が反映されない | LM Studio でそのモデルが Load されているか確認。vision 非対応モデルを選ぶと警告が出てテキストのみで fallback |
| レポート生成が長すぎて timeout | 既定は `7200` (2 時間)。それでも足りなければ `LM_STUDIO_TIMEOUT=0` で無制限 (Streaming の進捗 UI で目視監視)。途中 timeout すると max_tokens 到達前でも生成途中の出力がすべて破棄される |
| OpenALEX タブで「エアギャップ環境」警告 | 想定通り。Private モードでは外部 API は使えません |
| 再起動でログインを毎回求められる | 環境変数 `APOLLO_COOKIE_SECRET` に 32 文字以上の固定値を設定 |
| ポート 8501 が使われている | Run ダイアログの Host port を `18501` 等に変更 → <http://localhost:18501> でアクセス |
| プロジェクト切替後に古いデータが見える | サイドバー切替時に session_state は自動クリアされるが、キャッシュが残っている場合はブラウザをハードリロード |

## v7.0-private.1 からの移行

v7.0-private.1 の `apollo-private-data` volume をそのまま使い回せます。初回起動時に
自動マイグレーションが走り、以下を `projects/default/` 配下にハードリンクで移行します:

- `sessions/patent/*.pkl` → `projects/default/state/*.pkl`
- `inputs/{label}/*.csv` → `projects/default/files/{kind}/*.csv`
- `sessions/index.json` → `projects/default/state/.index.json`

ハードリンクなので disk 使用量は増えず、旧パスも残ります (安全のため削除は手動)。
マイグレーション完了後は `projects/.migrated_from_v7.0` sentinel が作られ、再実行されません。

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
just build             # or: docker build -f deploy/private/Dockerfile -t jl1nie/apollo-private:latest .
```

## モード切替 (上級者向け)

同じイメージで `APOLLO_MODE=hosted` を環境変数で上書きすると、Gemini API +
ローカル SBERT の hosted モード (HF Spaces 相当) に切り替わります。Private モード
固有の認証・LM Studio 接続は無効化されます。
