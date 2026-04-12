---
title: APOLLO v6 Patent Analysis
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.42.0
app_file: Home.py
pinned: false
short_description: AI-Powered Patent Analysis Platform (JP/EN)
license: mit
---

# 🚀 APOLLO v6: Patent Analysis Platform

**APOLLO (Advanced Patent & Overall Landscape-analytics Logic Orbiter)** is an advanced, AI-powered patent analysis platform designed to visualize technology trends, competitor strategies, and inventor networks using state-of-the-art NLP techniques (SBERT, UMAP, HDBSCAN).

**APOLLO (Advanced Patent & Overall Landscape-analytics Logic Orbiter)** は、最先端の自然言語処理技術（SBERT, UMAP, HDBSCAN）を活用し、技術トレンド、競合戦略、発明者ネットワークを可視化・分析するための高度な特許分析プラットフォームです。

---

## 🛰️ Mission Control (Data Hub)

The entry point for all analyses.
全ての分析の出発点です。

1.  **Data Import**: Upload patent data (CSV/Excel).
    * *データインポート*: 特許データ（CSV/Excel）をアップロードします。
2.  **Smart Mapping**: Automatically maps columns (Title, Abstract, Claims, IPC, etc.) based on keywords.
    * *スマートマッピング*: キーワードに基づいてカラム（名称、要約、請求項、IPCなど）を自動的に紐付けます。
3.  **Analysis Engine**: Pre-calculates SBERT vectors, TF-IDF keywords, and normalizes metadata with a real-time progress bar.
    * *分析エンジン*: SBERTベクトル化、TF-IDF計算、メタデータ正規化をバックグラウンドで実行します（リアルタイム進捗表示付き）。
4.  **Stopword Management**: Manage and edit stopwords to refine analysis accuracy.
    * *ストップワード管理*: 分析精度を向上させるため、ストップワードの管理・編集が可能です。

---

## 🧩 Analysis Modules (分析モジュール)

### 1. 🌍 ATLAS (Basic Statistics / 基本統計)
Visualizes basic statistics of the dataset.
データセットの基礎統計を可視化します。
* **Time Series**: Application trends over time. (時系列推移)
* **Rankings**: Top Applicants and IPCs. (出願人・IPCランキング)
* **Tree Maps**: Hierarchical view of IPCs or Applicants. (構成比マップ)
* **Lifecycle Map**: Technology maturity assessment (Applicants vs Applications). (技術ライフサイクル分析)

### 2. 💡 CORE (Rule-based Classification / ルールベース分類)
Classifies patents using user-defined logical rules or AI-suggested topics.
ユーザー定義の論理式、またはAIによる提案に基づいて特許を分類します。
* **AI Assistant**: Suggests classification axes using K-Means. (AIによる分類軸提案)
* **Rule Engine**: Supports complex boolean logic (AND, OR, NEAR, ADJ). (高度な論理式検索)
* **Heatmaps**: Visualizes cross-tabulation (e.g., Problem vs Solution). (ヒートマップ・バブルチャートによるクロス分析)

### 3. 🚀 Saturn V (AI Landscape / AIランドスケープ)
Generates a semantic landscape map using SBERT vectors.
SBERTベクトルを用いた意味論的な技術ランドスケープマップを生成します。
* **TELESCOPE**: Global map using UMAP & HDBSCAN clustering. (UMAPとHDBSCANによる全体マップ)
* **PROBE**: Drill-down analysis into specific clusters. (特定クラスタへのドリルダウン)
* **Auto-Labeling**: Automatically generates labels for clusters using TF-IDF. (TF-IDFによるクラスタ自動ラベリング)

### 4. 📈 MEGA (Trend & Portfolio / 動態・ポートフォリオ分析)
Analyzes macro trends and micro portfolios.
マクロな技術動態とミクロなポートフォリオを分析します。
* **PULSE**: Momentum analysis (CAGR vs Volume) to identify Leaders and Emerging players. (成長率と規模による4象限分析・動態マップ)
* **Trajectory**: Visualize historical shifts of players. (プレイヤーの時系列軌跡)
* **TELESCOPE**: Detailed portfolio mapping for specific applicants/IPCs. (特定対象のポートフォリオ詳細マップ)

### 5. 🧭 Explorer (Keyword Strategy / キーワード戦略)
Explores strategic keywords and competitor differences.
戦略的キーワードと競合他社との差異を探索します。
* **Global Overview**: Keyword co-occurrence networks. (全体共起ネットワーク)
* **Trend Analysis**: Identifies fast-growing keywords. (急上昇キーワード分析)
* **Comparative Strategy**: Tornado charts comparing two companies. (2社間のキーワード比較・トルネードチャート)
* **KWIC**: Keyword-in-Context search. (文脈検索)

### 6. 🔗 CREW (Network Analysis / ネットワーク分析)
Analyzes co-occurrence networks of inventors or applicants.
発明者や出願人の共起ネットワーク（つながり）を分析します。
* **Co-occurrence Graph**: Interactive network visualization. (インタラクティブなネットワーク図)
* **Metrics**: Betweenness Centrality, Brokerage Score, Productivity Score. (媒介中心性、技術ブローカー、生産性スコアなどの指標算出)
* **Community Detection**: Identifies research groups/factions. (コミュニティ・派閥の検出)

### 7. 🦅 EAGLE (Exploratory Landscape / 探索的ランドスケープ)
An interactive exploration module based on Saturn V, featuring manual clustering.
Saturn Vをベースにした、手動クラスタリング可能な探索的分析モジュールです。
* **Lasso Clustering**: Manually select and cluster data points. (自由選択クラスタリング)
* **Drill-down**: Detailed analysis of selected areas. (ドリルダウン分析)
* **Visual Editing**: Edit clusters and labels interactively. (視覚的なクラスタ編集)

### 8. 📝 VOYAGER (Strategic Reporting / 戦略レポート)
Compiles snapshots from all modules into a cohesive strategic narrative.
全モジュールから収集したスナップショット（証拠）を統合し、戦略的なストーリーを構築します。
* **Snapshot Curator**: Collect important charts as "Evidence" across ATLAS, Saturn V, and Explorer. (モジュール横断的な証拠収集・スナップショット機能)
* **Strategic Deep Dive**: Generates CSO-level strategic reports with Scenario Planning (Probable/Best/Risk). (CSO視点の詳細戦略レポート・シナリオプランニング機能)
* **Evidence Download**: Download gathered evidence as images consistent with report references (`Evidence X.png`). (証拠画像のダウンロード)
* **AI-Powered Insight**: Context-aware generation using Gemini 2.5 Flash. (Gemini 2.5 Flashによる文脈認識型インサイト生成)

### 9. 🌌 NEBULA (Environmental Analysis / 環境分析)
Environmental Analysis module that integrates non-patent literature (papers, news, policy documents) with patent data. Visualize gaps and synergies between social trends and technological development.

特許情報だけでなく、論文・ニュース・政策文書までを含めた「環境分析」を行うモジュールです。社会トレンドや市場の期待を統合し、特許データとのギャップやシナジーを可視化します。

---

## 🛠️ Requirements (動作環境)

* Python 3.9+
* **Key Libraries**:
    * `streamlit`
    * `pandas`
    * `sentence-transformers` (AI Vectors)
    * `umap-learn`, `hdbscan` (Dimensionality Reduction & Clustering)
    * `google-generativeai` (Likely required for VOYAGER)
    * `kaleido` (Image Export)
    * `plotly` (Interactive Charts)

## 🚀 How to Run (実行方法)

### Hosted モード (Hugging Face Spaces / 個人利用)

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Run the application:
    ```bash
    streamlit run Home.py
    ```

ローカル SBERT (`paraphrase-multilingual-MiniLM-L12-v2`) と Google Gemini API を使用します。

---

## 🔒 APOLLO Private (オンプレ・完全エアギャップ版)

**特許データを外部 API に一切送信せず、ローカル LLM で全推論を完結させる Docker 配布版**です。
中小企業の知財部門・競合他社分析・未公開発明の整理など、**社外秘データを絶対に外に出せない**
用途のために設計されています。

### 🎯 なぜ Local LLM なのか

| 項目 | クラウド API (Gemini / OpenAI) | APOLLO Private (Local LLM) |
|---|---|---|
| **特許データの外部送信** | API 経由で送信される | **一切なし**（エアギャップ可能） |
| **月額費用** | 呼び出し回数 × 単価（青天井） | **ゼロ**（電気代のみ） |
| **レート制限** | 厳しい（分析中に止まる） | **なし**（GPU 性能の限界まで） |
| **オフライン運用** | 不可 | **可能**（インターネット不要） |
| **モデル選択** | プロバイダ提供のみ | **自由**（最新 OSS モデル即導入） |
| **データ主権** | ベンダー依存 | **完全自社管理** |
| **監査ログ** | ベンダー側 | 自社インフラ内で完結 |
| **カスタマイズ** | プロンプトのみ | モデル差替・微調整・蒸留など自由 |

### 📊 ベンチマーク（実機検証済み）

APOLLO Private が実際にどれだけの実力を出すかを、実機（GPU マシン + LM Studio）で検証した結果です。

#### 埋め込み性能: SBERT vs Qwen3-Embedding-4B

| 指標 | Hosted (SBERT) | **Private (Qwen3-Embedding-4B)** | 改善率 |
|---|---|---|---|
| モデル | `paraphrase-multilingual-MiniLM-L12-v2` | `text-embedding-qwen3-embedding-4b` | — |
| パラメータ数 | 118M | **4B** | 34× |
| **埋め込み次元** | 384 | **2560** | **6.7×** |
| 最大コンテキスト | 128 tokens | **32K tokens** | **256×** |
| 多言語 MTEB | 中位（枯れた 2023 モデル） | **トップクラス (2025)** | — |
| 日英クロスリンガル類似度（実測） | 未測定 | **0.9073**（同一特許 JA/EN 対） | — |
| 識別性（関係なしペア） | — | **0.5848**（差分 0.32、十分分離） | — |
| ランタイム | CPU (推論時) | GPU (バッチ推論) | — |

**特許分析での意義:**
- **6.7 倍の表現力**で、類似技術クラスタをより細かく分離できる
- **32K コンテキスト**で請求項をまるごと埋め込める（SBERT の 128 トークンでは冒頭しか読めなかった）
- **日英クロスリンガル** で多国籍出願ファミリーを同一空間にマッピング可能

#### チャット & マルチモーダル: Gemini vs Gemma 4 26B

| 指標 | Hosted (Gemini 2.5 Flash) | **Private (Gemma 4 26B)** |
|---|---|---|
| モデル | `gemini-2.5-flash` | `google/gemma-4-26b-a4b`（MoE A4B） |
| コンテキスト | 1M | **128K〜256K** |
| マルチモーダル | ✓ | ✓（ネイティブ Vision） |
| システムロール | ✗（プロンプト連結で代替） | **✓ ネイティブ対応** |
| Function calling | ✓ | **✓ ネイティブ対応** |
| 推論モード切替 | ✗ | **✓ 思考モード可変** |
| 外部送信 | あり | **なし** |

**マルチモーダル実測検証（Phase 2）:**

> matplotlib で生成した架空の特許出願トレンドチャート（Company A: 10→55 急増 / Company B: 2021 ピーク後微減）を
> PNG で Gemma 4 に渡して日本語分析を要求したところ、以下を**正確に読み取って**日本語で応答：
>
> - Company A の急成長（2020 年 10 件 → 2024 年 55 件）
> - Company B の 2021 年ピーク後の緩やかな減少
> - **2022〜2023 年のクロスオーバー年を正確に特定**
>
> → VOYAGER の Evidence 駆動レポート生成（`[[Evidence N]]` 引用タグ付きプロンプト）が
>   Gemini なしで完全動作することを確認済み。

#### 非同期ジョブ & キャッシュ（Phase 3）

| 項目 | 測定値 |
|---|---|
| 埋め込み 15 件（Qwen3-4B, GPU） | 約 4 秒 |
| 2 回目実行（同じ CSV）| **即時ヒット** |
| status.json atomic rename | 読み取り競合なし |
| daemon スレッド | ブラウザ閉じても継続 |
| ディスクキャッシュ永続化 | ✓（`/var/lib/apollo/cache/embeddings/`） |

### 📦 特徴サマリ

- **完全ローカル推論** — 埋め込み・チャット・マルチモーダルすべてローカル GPU で
- **非同期埋め込みジョブ** — 大量特許の埋め込みをバックグラウンド実行、ブラウザを閉じても継続
- **ディスクキャッシュ** — 同じ CSV の 2 回目以降は即時利用
- **マルチユーザー認証** — `streamlit-authenticator` + bcrypt（YAML ユーザーストア）
- **Docker 配布** — `docker compose up` 一発で起動、永続化はマウントボリューム
- **BuildKit キャッシュ** — Dockerfile 再ビルドが 1.7 秒
- **~2GB 軽量イメージ** — torch / sentence-transformers 排除済み（LM Studio 側で推論）

---

## 📖 APOLLO Private — エンドユーザーマニュアル

### ステップ 0: 動作要件の確認

| 項目 | 最低要件 |
|---|---|
| OS | Linux / macOS / Windows (Docker Desktop) |
| Docker | Engine 20.10+、Compose v2.0+ |
| GPU | 推奨: NVIDIA RTX 3060 以上（VRAM 8GB+）※埋め込み 4B + チャット 26B 同時運用時 |
| ディスク | 50GB+（モデル + 埋め込みキャッシュ） |
| LLM ランタイム | LM Studio（GUI）または Ollama（CLI） |

### ステップ 1: ローカル LLM のセットアップ

**LM Studio (推奨、GUI で簡単):**
1. https://lmstudio.ai からダウンロード・インストール
2. 「Discover」タブで以下をダウンロード:
   - `text-embedding-qwen3-embedding-4b`（埋め込み、~2.5GB）
   - `google/gemma-4-26b-a4b`（チャット + Vision、~15GB）
3. 「Local Server」タブで **Start Server**（デフォルトポート: 1234）
4. 「Serve on Local Network」を ON にすると LAN からもアクセス可能

**Ollama (CLI 派向け):**
```bash
ollama serve &
ollama pull bge-m3              # 埋め込み（代替: 1GB 程度の軽量版）
ollama pull qwen2.5vl           # チャット + Vision
```

### ステップ 2: APOLLO Private の起動

```bash
git clone https://github.com/jl1nie/apollo-patent-analysis.git
cd apollo-patent-analysis
git checkout apollo-private

# 設定ファイルを準備
cp deploy/private/.env.example deploy/private/.env
# deploy/private/.env をエディタで開いて以下を編集:
#   LM_STUDIO_BASE_URL=http://host.docker.internal:1234/v1  (LM Studio の場合)
#   APOLLO_EMBEDDING_MODEL=text-embedding-qwen3-embedding-4b
#   APOLLO_CHAT_MODEL=google/gemma-4-26b-a4b
#   APOLLO_COOKIE_SECRET=<openssl rand -hex 32 で生成した値>

# 管理者パスワードハッシュを生成
just hash-password
# → プロンプトでパスワード入力 → bcrypt ハッシュが出力される

# ユーザー設定を配置
mkdir -p ./apollo-data/users
cp deploy/private/users.example.yml ./apollo-data/users/users.yml
# users.yml をエディタで開いて password の値を上で生成したハッシュに差し替え
# また cookie.key を .env の APOLLO_COOKIE_SECRET と同じ値にする

# コンテナ起動
just up
# または: docker compose -f deploy/private/docker-compose.yml up -d
```

### ステップ 3: ブラウザでアクセス

http://localhost:8501 を開く

1. ログイン画面が表示される → `users.yml` に登録したユーザー名・パスワードで入る
2. サイドバー左上に `🔒 Private Edition` バッジ + ユーザー名 + ログアウトボタンが表示されれば成功

### ステップ 4: 特許データ分析の日常ワークフロー

```
1. [🛰️ Mission Control] タブで CSV/Excel をアップロード
       ↓
2. カラム自動マッピング（発明の名称・要約・請求項・出願人・IPC 等）
       ↓ 確認して必要なら手動調整
3. [フェーズ 4: 分析エンジン起動] ボタンをクリック
       ↓
4. バックグラウンドで埋め込み計算ジョブが走る
   ・進捗バーが 2 秒ごとに更新される
   ・他のページ（ATLAS, Saturn V 等）へ移動しても継続
   ・ブラウザを閉じて再接続しても復元される
       ↓
5. 完了後、サイドバーから任意の分析モジュールを選択
       ↓
6. [📸 Snapshot] ボタンで重要な図を集め、最後に [📝 VOYAGER] で
   LLM が日本語戦略レポートを自動生成
```

### ステップ 5: 分析モジュール早見表

| モジュール | 用途 | 主な可視化 |
|---|---|---|
| 🌍 **ATLAS** | 基本統計 | 時系列・ランキング・ライフサイクル |
| 💡 **CORE** | ルールベース分類 | 論理式検索・ヒートマップ |
| 🚀 **Saturn V** | AI ランドスケープ | UMAP + HDBSCAN 自動クラスタ |
| 📈 **MEGA** | 動態・ポートフォリオ | 4 象限分析・軌跡 |
| 🧭 **Explorer** | キーワード戦略 | 共起ネット・トルネード・KWIC |
| 🔗 **CREW** | 発明者/出願人ネット | 技術ブローカー指標・コミュニティ検出 |
| 🦅 **EAGLE** | 手動クラスタリング | ラッソ選択・ドリルダウン |
| 📝 **VOYAGER** | 戦略レポート生成 | `[[Evidence N]]` 付き LLM レポート |
| 🌌 **NEBULA** | 環境分析（特許 + 論文） | Patent × NPL トレンド比較 |

### ステップ 6: データ永続化の仕組み

`${APOLLO_DATA_DIR}` (デフォルト `./apollo-data`) 配下に以下が保存されます:

```
apollo-data/
├── cache/embeddings/       ← SHA-256 キー付き埋め込みキャッシュ (.npy)
├── jobs/                    ← 非同期ジョブの status.json
├── users/users.yml          ← bcrypt 済みパスワード
└── sessions/                ← （将来拡張用）
```

バックアップは `rsync -a apollo-data/ /backup/apollo/` で OK。
全データをホスト側ファイルシステムで管理しているため、**ブラウザ側には秘密情報が一切保存されません**。

### よくあるトラブル

| 症状 | 対応 |
|---|---|
| ログイン画面が出ない / エラー | `users.yml` のパスと権限（UID 10001）を確認 |
| 埋め込みが始まらない | `just check-lm-studio` でエンドポイント疎通確認 |
| VOYAGER のマルチモーダルが失敗 | チャットモデルが Vision 非対応。Gemma 4 / Qwen3-VL 等に切替 |
| ジョブが数十分動き続ける | 正常（数万件を 4B で埋め込む場合）。 `nvidia-smi` で GPU 使用率確認 |
| `host.docker.internal` が解決できない | `docker-compose.yml` の `extra_hosts` 設定済み。古い Docker の場合は `.env` で直接 LAN IP を指定 |

より詳細なトラブルシューティングは [`deploy/private/README.md`](deploy/private/README.md) を参照。

### モード切替一覧

`APOLLO_MODE` 環境変数で hosted / private を切り替えます:

| 値 | 挙動 |
|---|---|
| `hosted` (default) | ローカル SBERT + Google Gemini API、session_state のみ、認証なし |
| `private` | LM Studio / Ollama 経由の推論、disk cache、非同期ジョブ、認証あり |

**既存の Hugging Face Spaces デプロイには一切影響しません。**

---
© 2025-2026 しばやま