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

中小企業の知財部門・競合他社分析・未公開発明の整理など、
**社外秘データを絶対に外に出せない**用途のために設計された配布版です。

### 💡 まず一番大事なこと（非エンジニアの方へ）

APOLLO Private は、**アップロードした特許データが 100% お手元の PC / サーバの中に閉じた状態**で
動きます。技術用語が多く見えるかもしれませんが、覚えていただきたいのはこの 4 点だけです。

#### 1. 📁 アップロードしたデータは「あなたの PC の中のフォルダ」に保存されます

- アップロードした CSV / Excel、計算された分析結果、AI が生成したレポートは
  **すべてあなたの PC 上の `apollo-data` というフォルダ**に保存されます
- このフォルダは **あなたの PC のハードディスクの一部**です。クラウドではありません
- バックアップを取りたいときは、このフォルダをまるごと USB メモリや NAS にコピーするだけです
- アンインストールしたいときは、このフォルダを削除すれば全データが消えます

#### 2. 🚫 インターネット経由でデータが「外」に出ることはありません

- AI 分析の処理も **あなたの PC（または社内 GPU マシン）の中だけで完結**します
- Google や OpenAI に特許文面が送信される経路は**コード上に存在しません**
- インターネット接続を切った状態でも動作します（エアギャップ運用）
- Wireshark などで通信を監視しても、特許データが外部に送信されないことを確認できます

#### 3. 💰 月額料金・API 利用料・アカウント登録は一切不要

- Gemini や ChatGPT のような従量課金はありません
- クラウドサービスへの登録も不要です
- かかるのは **PC の電気代のみ**

#### 4. 🐳 「Docker」は難しく考えなくて大丈夫

- Docker は「**このアプリを箱に詰めて配布する仕組み**」のことです
- エンジニアでなくても、セットアップ手順通りにコマンドを 3〜4 個打つだけで動きます
- 一度起動すれば、あとはブラウザで http://localhost:8501 を開くだけ
  （Web ブラウザを使えれば OK）
- 詳しい手順は[「エンドユーザーマニュアル」](#-apollo-private--エンドユーザーマニュアル)で説明します

---

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

#### 共通要件

| 項目 | 要件 |
|---|---|
| OS | Linux / macOS / Windows (WSL2 + Docker Desktop) |
| Docker | Engine 20.10+、Compose v2.0+ |
| LLM ランタイム | LM Studio (GUI 推奨) または Ollama (CLI) |
| CPU | x86_64 with AVX2（近年の Intel Core / AMD Ryzen ならすべて対応） |

#### ハードウェアスペック階層（3 段階）

用途とデータ量に応じて 3 つの構成を用意しました。APOLLO 本体（コンテナ）は軽量ですが、
**LLM ランタイム側の GPU / RAM が性能を決めます**。

##### 🥉 最小構成 — 個人検証・小規模 PoC（〜1,000 件の特許）

| 項目 | スペック | コスト目安 |
|---|---|---|
| **GPU** | NVIDIA RTX 3060 12GB / RTX 4060 Ti 16GB | 5〜8 万円 |
| **VRAM** | 12GB 以上 | — |
| **CPU** | Intel Core i5 / AMD Ryzen 5 (6 コア以上) | — |
| **RAM** | 32GB | 1.5 万円 |
| **ディスク** | SSD 500GB（OS 含む） | 1 万円 |
| 推奨モデル | 埋め込み: `qwen3-embedding-0.6b`、チャット: `gemma-3-12b` or `qwen3-8b` | — |
| 想定処理速度 | 埋め込み 1,000 件: 約 1〜2 分 / レポート生成: 10〜30 秒 | — |
| 同時ユーザー | 1 名 | — |

> 💡 RTX 3060 12GB は**現行のコスパ最強枠**。ゲーミング PC 流用でも十分動きます。

##### 🥈 推奨構成 — 日常業務・中規模（〜10,000 件、1 社の全特許ポートフォリオ）

| 項目 | スペック | コスト目安 |
|---|---|---|
| **GPU** | NVIDIA RTX 3090 24GB / RTX 4090 24GB | 20〜30 万円 |
| **VRAM** | 24GB 以上 | — |
| **CPU** | Intel Core i7 / AMD Ryzen 7 (8 コア以上) | — |
| **RAM** | 64GB | 3 万円 |
| **ディスク** | NVMe SSD 1TB | 1.5 万円 |
| 推奨モデル | 埋め込み: `qwen3-embedding-4b` (2560 次元)、チャット: `gemma-4-26b-a4b` (MoE) | — |
| 想定処理速度 | 埋め込み 10,000 件: 約 3〜5 分 / VOYAGER レポート: 1〜2 分 | — |
| 同時ユーザー | 2〜3 名 | — |

> 💡 **このクラスから APOLLO Private の本領が発揮される**。Gemma 4 26B の Vision 機能で
> VOYAGER のマルチモーダルレポートが実用速度で動きます。ベンチマーク値（2560 次元 / 0.9073 日英クロスリンガル）
> はこの構成で実測したものです。

##### 🥇 理想構成 — チーム運用・大規模（10,000 件以上 / 複数テーマ並行分析）

| 項目 | スペック | コスト目安 |
|---|---|---|
| **GPU** | NVIDIA RTX 6000 Ada 48GB / dual RTX 3090 / H100 | 60〜300 万円 |
| **VRAM** | 48GB 以上 | — |
| **CPU** | Intel Xeon / AMD Threadripper (16 コア以上) | — |
| **RAM** | 128GB | 6 万円 |
| **ディスク** | NVMe SSD 2TB + HDD 8TB（バックアップ用） | 3 万円 |
| 推奨モデル | 埋め込み: `qwen3-embedding-8b`、チャット: `qwen3-next-80b` / `llama-3.3-70b` | — |
| 想定処理速度 | 埋め込み 100,000 件: 約 30〜60 分 / レポート: 30 秒 | — |
| 同時ユーザー | 5〜10 名（認証分離で並行利用） | — |

> 💡 企業 IP 部門向け。50〜70B クラスのチャットモデルが動くと VOYAGER の戦略レポート品質が
> フロンティアモデルに肉薄します。

#### CPU-only 運用（GPU なし、検証用途）

GPU がない環境でも動作はしますが、**実用速度ではありません**：

| 項目 | 目安 |
|---|---|
| RAM | 64GB 以上必須 |
| CPU | 高クロック 16 コア以上（Ryzen 9 / i9 クラス） |
| 埋め込み 1,000 件 | 10〜30 分（Qwen3-0.6B）/ 数時間（4B） |
| チャット応答 | 1〜5 tok/s（実用下限）|

> ⚠️ **CPU-only は非推奨**。技術検証・デモ用途まで。本番では最小構成以上の GPU を用意してください。

#### ディスク容量の内訳

| 項目 | 容量 |
|---|---|
| APOLLO Docker イメージ | 2.05 GB |
| Qwen3-Embedding-4B (Q5 量子化) | 3 GB |
| Gemma 4 26B (Q5 量子化) | 18 GB |
| 埋め込みキャッシュ | 約 100 MB / 10,000 件 |
| バックアップ用余裕 | データ量 × 2 |

**合計目安:** 最小 50GB / 推奨 100GB / 大規模 500GB+

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

初めての方は下記の順番通りに進めてください。コマンド（黒い画面に打ち込む文字）は
そのままコピー＆ペーストすれば動きます。

#### 2-1. プログラム一式をダウンロード

```bash
git clone https://github.com/jl1nie/apollo-patent-analysis.git
cd apollo-patent-analysis
git checkout apollo-private
```

> 📦 **これは何をしているの？** — GitHub から APOLLO のソースコード一式を
> 自分の PC にコピーしています。`cd` で作業フォルダに入り、`checkout` で
> Private 版を選んでいます。

#### 2-2. 設定ファイルを作成

```bash
cp deploy/private/.env.example deploy/private/.env
```

次に `deploy/private/.env` をテキストエディタ（メモ帳、VS Code、vim 等）で開き、
以下の 4 箇所を編集してください:

| 設定名 | 値 | 説明 |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://host.docker.internal:1234/v1` | LM Studio の場合そのまま |
| `APOLLO_EMBEDDING_MODEL` | `text-embedding-qwen3-embedding-4b` | ステップ 1 でロードしたモデル名 |
| `APOLLO_CHAT_MODEL` | `google/gemma-4-26b-a4b` | ステップ 1 でロードしたモデル名 |
| `APOLLO_COOKIE_SECRET` | ランダムな 64 文字 | 下記コマンドで生成 |

ランダム文字列の生成:
```bash
openssl rand -hex 32
# → 64 文字のランダム文字列が出力される。それを .env にコピペ
```

#### 2-3. 管理者パスワードを設定

```bash
just hash-password
```

パスワードを聞かれるので、**好きなパスワードを入力**してください（画面には表示されません）。
`$2b$12$...` で始まる長い文字列が出力されます。**この文字列をあとで使うので覚えておいてください**。

> 🔑 **これは何をしているの？** — 入力したパスワードを暗号化（ハッシュ化）して、
> 安全な形で保存できるようにしています。元のパスワードは `apollo-data` フォルダには
> 保存されません。

#### 2-4. ユーザー登録ファイルを作成

```bash
mkdir -p ./apollo-data/users
cp deploy/private/users.example.yml ./apollo-data/users/users.yml
```

続けて `./apollo-data/users/users.yml` をテキストエディタで開き、以下 2 箇所を編集:

1. `password:` の欄 → ステップ 2-3 で生成したハッシュ文字列に差し替え
2. `cookie.key:` の欄 → ステップ 2-2 で生成したランダム文字列（.env と同じ値）に差し替え

#### 2-5. APOLLO Private を起動

```bash
just up
```

> 🚀 **これは何をしているの？** — APOLLO Private を起動しています。初回は少し時間が
> かかります（Docker という仕組みでパッケージ化されたプログラムが動き始めます）。
> 画面が止まったように見えても焦らないでください。

`just` がインストールされていない場合は、代わりに以下のコマンドでも OK:
```bash
docker compose -f deploy/private/docker-compose.yml up -d
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

### ステップ 6: データはどこに保存されているのか（重要）

**アップロードした CSV や分析結果は、あなたの PC の `apollo-data` フォルダに保存されます。**

```
apollo-data/                 ← このフォルダ全体があなたの PC 上にあります
├── cache/embeddings/         ← 特許文面の AI 表現（ベクトル）キャッシュ
├── jobs/                      ← 進行中・完了ジョブの状態ファイル
└── users/users.yml            ← ログインアカウント情報（パスワードは暗号化済み）
```

#### データの流れ（通信経路図）

```
┌───────────────────────────────────────────────────────────────┐
│  あなたの PC（または社内 GPU マシン）                          │
│                                                                │
│  ┌──────────────┐   ①CSV     ┌────────────────┐              │
│  │              │ ──────────▶ │                │              │
│  │ Web ブラウザ │              │  APOLLO        │              │
│  │              │ ◀────────── │  (Docker)      │              │
│  └──────────────┘   ③分析結果  └─┬──────────┬──┘              │
│                                   │          │                 │
│                           ②埋め込み│          │④保存           │
│                                   ▼          ▼                 │
│                            ┌──────────┐  ┌────────────┐       │
│                            │ LM Studio│  │ apollo-data│       │
│                            │ (GPU)    │  │  フォルダ  │       │
│                            └──────────┘  └────────────┘       │
│                                                                │
└───────────────────────────────────────────────────────────────┘

                            ╳  ← インターネットには一切出ない
```

**重要ポイント:**
- ① CSV アップロード時は「あなたの PC → あなたの PC」の通信のみ（ネット不要）
- ② AI 処理もあなたの PC の中だけで完結
- ③ 分析結果表示もローカル Web ブラウザとローカルサーバ間のみ
- ④ データは `apollo-data` フォルダに保存（あなたの PC のハードディスク上）

#### バックアップ・削除・移行

**バックアップしたいとき:**
- `apollo-data` フォルダを USB メモリや NAS にコピーするだけ
- コマンド例: `cp -r apollo-data /mnt/usb/apollo-backup-2026-04-13`

**別の PC に移行したいとき:**
- `apollo-data` フォルダを新しい PC にコピーし、同じ手順で APOLLO Private をセットアップ

**アンインストールしたいとき:**
- `docker compose down` でコンテナ停止
- `apollo-data` フォルダを削除 → **完全消去完了**
- クラウドにデータが残る心配はありません

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