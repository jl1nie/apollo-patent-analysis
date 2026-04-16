# APOLLO v7.0-private.2 (上流 v7.0.0 派生) — プロジェクト階層 + レポート素材永続化 + Vision VOYAGER + ローカル AI サジェスト

## 命名規約について

**"v7.1" ではなく "v7.0-private.2"** と呼称する理由: "v7.1" は上流オリジナル作者 (しばやま氏) の
バージョン空間であり、派生ブランチが自称するのは不適切。本派生は v7.0.0 (upstream) + private-2
(派生第 2 版) という位置付けで、baseline の `v7.0-private.1` を継承・拡張する。

## Context

v7.0.0-private.1 では「ファイル × モデル」matrix の flat 構造で埋め込みキャッシュを管理していた。実装済みの機能は動作しているが、実運用の視点で以下の課題がある:

- **ベクトル空間の汚染リスク**: 同じプロジェクト内で異なるモデルを使うと UMAP/クラスタ比較が無効になるが、構造的にそれを防げない
- **レポート素材の揮発性**: VOYAGER/CAPCOM レポート生成の主要入力 (snapshot・各モジュールの CAPCOM data JSON・AI prompts・Mission Objective) が全て `st.session_state['capcom_store']` に保持されているだけで、ブラウザを閉じると消失する。分析実行 = 素材蓄積の自動連鎖が session 境界で切れる
- **ユーザーの頭の中のメンタルモデル不一致**: ユーザーは「特許フォルダ・マーケットフォルダ…」という**ドメイン単位の階層**で作業を整理したい (2026-04-16 のヒアリング結果)
- **Snapshot の vision 未活用**: VOYAGER は現状 Gemini にテキストしか送っておらず、ユーザーが選択的にキャプチャした PNG の視覚的構造 (外れ値位置・密度偏り) を LLM が読めていない

v7.0-private.2 ではこれらを**プロジェクト階層 + 固定モデル + レポート素材の自動永続化 + Vision 対応**で一括解決する。上流 V7 本体への変更はゼロを維持する。

---

## 要件

1. **V7 本体への変更: 原則ゼロ、例外は VOYAGER の 3 行のみ** (`Home.py`, `pages/*.py` の他ファイル, `utils.py`, `patiroha` は触らない)。既存の Home.py フック (`apollo_bootstrap.init()`, `render_patent_picker_section()`, `persist_analysis_state()`, `show_external_api_notice()`) を再利用。**唯一の例外**: `pages/8_📝_VOYAGER.py` の `client.generate_text()` 呼び出し 3 箇所 (L793, L840, L1019 相当) に `images=` 引数を追加する (Track E 参照、理由は案 1 の heuristics が Phase 3 strategist_prompt の evidence_catalog で破綻するため)
2. **hosted モードの挙動は完全に不変** (全変更が `apollo_config.IS_PRIVATE` ガード下)
3. **v7.0 既存データは自動移行** (default プロジェクトに編入、ユーザー操作不要)
4. **プロジェクト作成は明示 UI + default 存在** (初めて使うユーザーも default で何も意識せず使える)
5. **Vision VOYAGER は v7.0-private.2 スコープに含める** (Gemini と LM Studio 両方で multimodal 対応)
6. **active project は `projects/.active` ファイルが single source of truth**、`st.session_state` は optimistic cache のみ (session_state.clear() で active が失われる事故を防ぐ)

---

## 1. データモデル

```
/var/lib/apollo/
├── projects/
│   ├── .active                              # 現在アクティブな project_id (テキスト 1 行)
│   ├── .migrated_from_v7.0                  # マイグレーション sentinel
│   ├── default/                             # 自動作成される既定プロジェクト
│   │   ├── config.json
│   │   ├── files/
│   │   ├── state/
│   │   ├── store/
│   │   └── reports/
│   └── cnf/                                 # ユーザーが作成するプロジェクト
│       ├── config.json                      # name, embedding_model, chat_model, created_at, mission_objective
│       ├── files/
│       │   ├── patents/
│       │   │   ├── cnf_jp_2024.csv
│       │   │   └── cnf_us_2024.csv
│       │   ├── academic/
│       │   ├── news/
│       │   ├── market/
│       │   └── policy/
│       ├── state/
│       │   └── {content_key}.pkl            # 前処理結果 (既存 analysis_state.py の pickle フォーマット)
│       ├── store/                           # VOYAGER/CAPCOM レポート素材 (自動蓄積)
│       │   ├── snapshots/
│       │   │   ├── metadata.json
│       │   │   └── {snap_id}_{index}.png
│       │   ├── data/                        # capcom.save_data の出力
│       │   │   ├── atlas_statistics.json
│       │   │   ├── saturnv_clusters.json
│       │   │   ├── mega_momentum.json
│       │   │   └── ... (計 18+ ファイル)
│       │   ├── prompts/
│       │   │   └── *.md
│       │   ├── voyager/
│       │   │   ├── mission.json
│       │   │   ├── context.json
│       │   │   └── evidence/*.json
│       │   └── patents.csv                  # capcom.save_patents_csv の出力
│       └── reports/
│           ├── voyager_2026-04-20T10-30.md
│           ├── voyager_2026-04-20T10-30.pdf
│           └── capcom_session_20260420_1030.zip
├── sessions/                                # 旧 v7.0 データ (read-only、マイグレーション後に残すが参照しない)
│   └── index.json
├── cache/embeddings/*.npy                   # npy キャッシュは project を跨いで共有 (content_key が model_id 込みなので衝突しない)
└── uploads/                                 # 旧 v7.0 の server_files (同上)
```

**config.json の構造:**
```json
{
  "project_id": "cnf",
  "name": "CNF 特許分析",
  "embedding_model": "text-embedding-qwen3-embedding-4b",
  "chat_model": "qwen/qwen3-30b-a3b-2507",
  "created_at": "2026-04-20T10:30:00",
  "updated_at": "2026-04-20T14:15:00",
  "description": "CNF 関連特許の競争環境分析",
  "mission_objective": "CNF の量産技術で優位に立つ出願人を特定する"
}
```

**重要: プロジェクト = 固定ベクトル空間**
- `embedding_model` はプロジェクト作成時に決まり、以降変更不可
- モデルを変えたい場合は新プロジェクトを作る (データはコピー可能)
- これにより UMAP / クラスタ比較が常に同じベクトル空間で行われる

---

## 2. 変更ファイル一覧 (すべて `services/` 配下 + bootstrap + config)

| ファイル | 種類 | 概要 |
|---|---|---|
| `services/projects.py` | **新規** | プロジェクト CRUD。`create_project`, `list_projects`, `get_active`, `set_active`, `get_config`, `update_config`, `delete_project`, `project_root` |
| `services/project_hooks.py` | **新規** | capcom / utils / analysis_state のモンキーパッチ用ラッパー群。`install_all_hooks()` が `apollo_bootstrap.init()` から呼ばれる |
| `services/llm_vision.py` | **新規** | multimodal LLM クライアント。`GeminiMultimodalClient`, `LMStudioMultimodalClient`, 共通基底 `MultimodalLLMClient`。`generate_multimodal(system, user, images: list[bytes]) -> str` を提供 |
| `services/migration_v7_0.py` | **新規** | v7.0 → v7.0-private.2 自動マイグレーション。apollo_bootstrap.init() が 1 度だけ呼ぶ冪等関数 |
| `services/private_ui.py` | 改修 | `render_sidebar_extras` にプロジェクト selector 追加。`render_patent_picker_section` をプロジェクトダッシュボードに差し替え (既存 hook 点は維持)。`render_project_create_modal` 新設 |
| `services/analysis_state.py` | 改修 | `save_state` / `load_state` のパス解決を `projects/<active>/state/` に変更。content_key ベースは維持 |
| `services/server_files.py` | 改修 | flat `uploads/patent/` を `projects/<active>/files/patents|academic|...` に切り替え。`list_files(kind)` / `save_file(kind, name, bytes)` の API は維持 (path 解決のみ変更) |
| `services/storage.py` | 改修 | `project_root()`, `project_state_dir()`, `project_store_dir()`, `project_files_dir(kind)` など project パス解決ヘルパー追加 |
| `services/lm_studio_models.py` | 改修 | `current_embed_model()` / `current_chat_model()` はアクティブプロジェクトの `config.json` を最優先 (session_state override より強い) |
| `services/embeddings.py` | 改修 | `_refresh_model_id` がプロジェクト config を参照。**モデル不一致検知**: プロジェクトモデルと異なる encode 要求を検知したら拒否 or 警告 |
| `services/llm.py` | 改修 | `create_client()` が multimodal 対応クライアントを返すよう拡張。既存 `generate_text` API は維持 |
| `apollo_bootstrap.py` | 改修 | マイグレーション呼び出し + 新しいモンキーパッチ (`project_hooks.install_all_hooks()` で一括適用) |
| `apollo_config.py` | 改修 | `PROJECT_ROOT = DATA_ROOT / "projects"` 追加。`project_config()` ヘルパー |

**V7 本体ファイルへの変更**: VOYAGER の 3 行 (Track E、`images=` 引数追加) のみ。他 (`Home.py`, `pages/*.py` の他ファイル, `utils.py`, `patiroha`) は touch ゼロ。

---

## 3. 実装トラック

### Track A — プロジェクト管理の基盤 (`services/projects.py`)

**重要な設計原則: active project の single source of truth は `projects/.active` ファイル**。`st.session_state["apollo_active_project"]` は optimistic cache であり、session_state.clear() / プロセス再起動でも値が失われない。`get_active()` はまず `projects/.active` を読み、無ければ `default` を返す。`set_active()` はファイルと session_state 両方を更新。

```python
def create_project(name: str, embedding_model: str, chat_model: str, description: str = "") -> str:
    """project_id を返す (name を sanitize)。config.json と files/ state/ store/ reports/ を作成"""

def list_projects() -> list[dict]:
    """[{project_id, name, embedding_model, file_count, last_used}, ...]"""

def get_active() -> str:
    """projects/.active から読む (primary)。無ければ 'default' を返す。session_state は touch しない (bootstrap 順序問題を避けるため)"""

def set_active(project_id: str) -> None:
    """projects/.active を書き換える + st.session_state["apollo_active_project"] を更新 (cache)"""

def get_config(project_id: str) -> dict:
    """projects/<id>/config.json を読む"""

def update_config(project_id: str, **kwargs) -> None:
    """config.json を更新 (name, description, mission_objective, chat_model 等を変更可能。embedding_model は例外で不可)"""

def delete_project(project_id: str, purge_cache: bool = False) -> None:
    """projects/<id>/ を削除。purge_cache=True なら関連 npy も削除"""

def project_root(project_id: str | None = None) -> Path:
    """project_id 省略時はアクティブプロジェクト"""
```

### Track B — 既存 API のモンキーパッチ (`services/project_hooks.py`)

既存の capcom / utils / analysis_state の関数を wrap し、元の session_state 書き込みに加えてプロジェクト配下にミラー書き込みする。

```python
def install_all_hooks() -> None:
    _install_capcom_hooks()
    _install_analysis_state_hooks()
    # utils.render_snapshot_button は capcom.save_snapshot_image を既に呼んでいるので、
    # capcom 側の hook だけで snapshot PNG も project 配下に落ちる

def _install_capcom_hooks() -> None:
    import capcom
    _orig_save_data = capcom.save_data
    def save_data_with_project(filename, data):
        _orig_save_data(filename, data)
        _mirror_to_project_store("data", filename, data)
    capcom.save_data = save_data_with_project

    _orig_save_snapshot_image = capcom.save_snapshot_image
    def save_snapshot_image_with_project(snap_id, image_bytes, index=None):
        result = _orig_save_snapshot_image(snap_id, image_bytes, index)
        _mirror_to_project_store("snapshots", f"{snap_id}_{index or 0}.png", image_bytes)
        return result
    capcom.save_snapshot_image = save_snapshot_image_with_project

    # save_prompt, save_metadata, save_voyager_mission/context/evidence, save_patents_csv も同様
```

`_mirror_to_project_store(subdir, filename, data)` はアクティブプロジェクトがあればそこへ書き込み、なければ default に書き込む。書き込み失敗は分析をブロックしない。

### Track C — 前処理結果のパス解決 (`services/analysis_state.py` 改修)

現在: `sessions/patent/<content_key>.pkl`
v7.0-private.2: `projects/<active>/state/<content_key>.pkl`

`save_state_by_key` / `load_state_by_key` / `update_state` / `list_sessions` すべてを project-aware に変更。session_index.json の代わりに、プロジェクト内の pkl 一覧を直接スキャンして index を構築 (軽量なのでインメモリ OK)。

下位互換 API (`save_state(filename)` 等) は引き続きアクティブプロジェクト配下に書き込む。V7 本体の `persist_analysis_state()` 呼び出しはそのまま動く。

**ベクトル化発生点は 2 箇所あることに留意:**
1. `Home.py:862` — 特許本体 (`sbert_embeddings`)、入力列 `title + abstract + claim`
2. `pages/9_🌌_NEBULA.py:974` — 学術論文 (`nebula_academic_embeddings`)、入力列 `unified_title×2 + unified_content`

どちらも `patiroha.SBERTEmbedder` 経由 (= v7.0 で LMStudioEmbedderShim に差し替え済み)。入力列が違うので npy キャッシュは自動的に別キーに落ちる。v7.0-private.2 で「プロジェクト切替」を行ったら、両方の session_state キーを一貫してクリアすること (`sbert_embeddings` + `nebula_academic_embeddings` + `tfidf_matrix` + `feature_names` + `df_npl` + `df_npl_accumulated` など、`STATE_KEYS` 全部)。切替後の最初の分析で同じ content_key に対応する pkl があれば自動復元、なければ再計算 → プロジェクト config のモデルで埋め込み直し、という流れを担保する。

### Track D — モデル選択の project 化 (`services/lm_studio_models.py` / `embeddings.py`)

```python
def current_embed_model() -> str:
    # 1. アクティブプロジェクトの config.embedding_model (最優先)
    try:
        from services import projects
        active = projects.get_active()
        if active:
            cfg = projects.get_config(active)
            if cfg.get("embedding_model"):
                return cfg["embedding_model"]
    except Exception:
        pass
    # 2. session_state override (サイドバー UI)
    # 3. env 既定値
    # 4. LM Studio 先頭モデル
```

**重要な変更**: 埋め込みモデルをサイドバーの selectbox から変更しようとすると「プロジェクト単位で固定されています。新プロジェクトを作成してください」と警告が出る。推論モデル (VOYAGER 用) は selectbox で変更可能 (レポート生成のたびに別モデルを試したいのは自然な要求)。

### Track E — Vision VOYAGER (`services/llm_vision.py` + `services/llm.py` 改修)

現状の `LLMClient.generate_text(system, user) -> str` API に加えて、`generate_multimodal(system, user, images: list[bytes]) -> str` を追加。

**Gemini 版**:
```python
def generate_multimodal(self, system_prompt, user_prompt, images):
    parts = [f"{system_prompt}\n\n{user_prompt}"]
    for png_bytes in images:
        parts.append({"mime_type": "image/png", "data": png_bytes})
    response = self.model.generate_content(parts, generation_config=...)
    return response.text
```

**LM Studio 版** (OpenAI SDK の multimodal):
```python
def generate_multimodal(self, system_prompt, user_prompt, images):
    import base64
    content = [{"type": "text", "text": user_prompt}]
    for png_bytes in images:
        b64 = base64.b64encode(png_bytes).decode("ascii")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    resp = self._client.chat.completions.create(
        model=self.model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""
```

**VOYAGER 側の切替 (採用案: 案 2 — 明示的 images 引数)**:

`generate_text(system, user, images=None)` のシグネチャに `images: list[bytes] | None = None` を追加。VOYAGER ページの 3 箇所の呼び出しに `images=` を渡す形に改修する。

**案 1 (モンキーパッチで自動 vision 変換) を不採用にした理由**:
- Phase 3 strategist_prompt には `evidence_catalog` として全 Evidence ID が列挙される (`pages/8_📝_VOYAGER.py:978-990`)。prompt 内の `[[Evidence N]]` を機械的に抽出すると全 30+ 画像が送信され token 爆発 (Gemini / LM Studio とも失敗)
- Phase 判定 heuristics (Evidence 本文パターン検出) を入れると脆弱で、将来 VOYAGER プロンプトが変わるたびに壊れる
- 案 2 の実質改修量は 3 行 (`client.generate_text(sys, user)` → `client.generate_text(sys, user, images=imgs)`) で上流マージコンフリクトは軽微

**VOYAGER.py 改修箇所** (3 箇所のみ):
1. Phase 1 analyst (L793 相当): `images` はそのモジュールの snapshot 画像のみ送る
2. Phase 2 cross (L840 相当): `images=None` (テキストのみ。前段 analyst_text に視覚的言及が含まれるため再送不要)
3. Phase 3 strategist (L1019 相当): `images=None` (catalog のみで evidence 本文なし)

**実装のポイント**: `create_client()` は従来通り `GeminiLLMClient` / `LMStudioLLMClient` を返す。両者の `generate_text` が `images` 引数を受け取り、`images` が non-empty なら自動で multimodal 呼び出しに切り替える (`generate_multimodal` の内部呼び出し)。images が空/None なら従来の text-only 呼び出し。これで hosted モードでも 1 行で対応できる。

### Track F — v7.0 → v7.0-private.2 マイグレーション (`services/migration_v7_0.py`)

`apollo_bootstrap.init()` が private モードで起動時に 1 度だけ実行する冪等関数:

```python
def migrate_if_needed() -> None:
    sentinel = apollo_config.DATA_ROOT / "projects" / ".migrated_from_v7.0"
    if sentinel.exists():
        return
    old_index = apollo_config.DATA_ROOT / "sessions" / "index.json"
    if not old_index.exists():
        # 新規インストール、マイグレーション対象なし。default プロジェクトだけ作る
        _ensure_default_project()
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
        return

    # default プロジェクトを作成 (既にあれば流用)
    default_id = _ensure_default_project()

    # sessions/patent/*.pkl を projects/default/state/ にハードリンク (データ非複製)
    old_dir = apollo_config.DATA_ROOT / "sessions" / "patent"
    new_dir = apollo_config.DATA_ROOT / "projects" / default_id / "state"
    new_dir.mkdir(parents=True, exist_ok=True)
    for pkl in old_dir.glob("*.pkl"):
        target = new_dir / pkl.name
        if not target.exists():
            try:
                os.link(pkl, target)   # ハードリンク (failed なら copy2)
            except OSError:
                shutil.copy2(pkl, target)

    # server_files/patent/*.csv は projects/default/files/patents/ にハードリンク
    old_files = apollo_config.DATA_ROOT / "uploads" / "patent"
    if old_files.exists():
        new_files = apollo_config.DATA_ROOT / "projects" / default_id / "files" / "patents"
        new_files.mkdir(parents=True, exist_ok=True)
        for f in old_files.iterdir():
            target = new_files / f.name
            if f.is_file() and not target.exists():
                try:
                    os.link(f, target)
                except OSError:
                    shutil.copy2(f, target)

    sentinel.touch()
```

**ハードリンク戦略**: 既存データを複製せずに新階層に参照を作る。同一 inode なので disk 使用量は増えない。ファイルシステムが対応していなければ `shutil.copy2` フォールバック。

**npy キャッシュは移動しない**: content_key が model_id 込みで計算されているので、プロジェクトを跨いでも衝突しない。cache/embeddings/ は全プロジェクト共通のまま。

### Track G — UI 変更 (`services/private_ui.py`)

**サイドバー (拡張)**:
```
🔒 Private Edition
─────────────────
📂 プロジェクト: [CNF特許分析 ▼]   ← selectbox
  [➕ 新規]  [⚙️ 編集]  [🗑️ 削除]

推論モデル (VOYAGER): [qwen3-30b-a3b-2507 ▼]   ← 推論のみ変更可
ℹ️ 埋め込みモデル: qwen3-embedding-4b (固定)

📦 埋め込みキャッシュ: 3 件 / 125 MB
🔒 エアギャップ維持中
```

**サイドバーが single source of truth**:
サイドバーに「プロジェクト名 + 固定埋め込みモデル + 推論モデル」が常時表示されるので、以下のページ内静的ラベルは v7.0-private.2 では**重複情報**になる:
- `Home.py:733` 「分析エンジン起動 ({EMBEDDER_LABEL}/TF-IDF)」ボタンラベル — v7.0 で動的化した PEP 562 ハックが v7.0-private.2 では不要に思える
- `pages/8_📝_VOYAGER.py:571` 「### 🤖 VOYAGER レポート生成 (Local LLM: {CHAT_MODEL})」見出し — 同じく静的でサイドバーと冗長

**v7 本体 touch ゼロ原則により、これらの静的ラベル自体は削除できない** (ページファイルを編集することになるため)。ただし:
1. v7.0 で仕掛けた `apollo_config.__getattr__("EMBEDDER_LABEL")` の動的化は、動作上必要不可欠ではなくなる (ユーザーはサイドバーを見る)
2. VOYAGER の `CHAT_MODEL` 静的ラベルは、実際の LLM 呼び出しモデルと乖離しても致命的ではない (サイドバーが正しい値を出すため、ユーザーは混乱しない)
3. 将来上流 V7 がこれらのラベルを削除するなら、そのタイミングで v7.0-private.2 プラグイン側も PEP 562 ハックを撤去できる

**設計方針**: v7.0-private.2 ではページ内ラベルを気にせず、サイドバーを唯一の真実とする。`apollo_config.EMBEDDER_LABEL` の PEP 562 動的化は v7.0 からの継続で残すが、新たな動的化は追加しない。

**Home.py のメインエリア (既存 `render_patent_picker_section()` フックを拡張)**:

情報密度対策として **tab 化** する (`st.tabs(["📁 ファイル", "📸 Snapshots", "📊 CAPCOM Data", "📝 Reports"])`)。縦に展開すると特許アップロード UI との距離が遠くなりユーザーが混乱するため、ダッシュボード自体はコンパクトに畳み、各タブ内で詳細表示する。

NPL データの「追加済/未追加/前処理済/埋め込み済」バッジはプロジェクトダッシュボード内の **ファイル一覧** の行単位バッジで表現する (Home.py の NPL UI 本体は変更不要、hook point が無いためそもそも触れない)。

現状の cache index テーブル (ファイル × モデル matrix) を、**プロジェクトダッシュボード** に置き換える:

```
📂 プロジェクト: CNF 特許分析
埋め込みモデル: qwen3-embedding-4b  |  作成: 2026-04-20  |  最終更新: 2h ago

### Mission Objective
[テキストエリア: CNF の量産技術で優位に立つ出願人を特定する]

### 📁 ファイル一覧
  特許 (2)
  ├── cnf_jp_2024.csv         [✅ 前処理済 3,200件] [開く] [削除]
  └── cnf_us_2024.csv         [📄 未前処理 1,500件]     [前処理] [開く] [削除]
  学術論文 (1)
  └── cnf_wos_2024.csv        [✅ 前処理済 800件]    [開く] [削除]
  マーケット (0)
  ニュース (0)
  政策 (0)

### 📸 Snapshot Collection (12 件)   [詳細 ▼]
  Saturn V: クラスタ動態マップ (2024-Q4)
  MEGA: 4象限分析
  ...

### 📊 CAPCOM データ (14 件)         [詳細 ▼]
  atlas_statistics.json
  saturnv_clusters.json
  mega_momentum.json
  ...

### 📝 Reports (3 件)
  voyager_2026-04-18.md
  voyager_2026-04-19.md
  capcom_session_20260420.zip
```

ファイルごとに **前処理済/未処理バッジ + 行数** が出る。`capcom_store['data']` が空でも projects/store/data/ に既に永続化されていれば表示される。

**NPL データの追加状態を明示**: 現状の Home.py UI は「CSV をアップロード → プレビュー表示 → 列マッピング → ➕ データセットに追加」の 4 段階で、「追加ボタンを押さないと `df_npl_accumulated` に入らない」という仕様がユーザーには分かりにくく、実際のバグ報告につながった (2026-04-16)。v7.0-private.2 のプロジェクトダッシュボードでは、ファイルリスト表示時に明示的にバッジを使い分ける:
- `[📄 未追加]`: アップロードされたが追加ボタン未押下 (プレビューだけ)
- `[✅ 追加済 / 前処理待ち]`: データセットに追加されたが preprocess 未実行
- `[🔄 前処理済 / 埋め込み未]`: preprocess 完了、NEBULA で埋め込みボタンを押せば分析可能
- `[✨ 埋め込み済]`: SBERT ベクトル化完了、すべての分析モジュールで使用可能 (Academic のみ該当)

この状態遷移を UI 上で明示することで、「なぜデータが見えないのか分からない」問題を防ぐ。

---

## 4. 重要な既存資産の再利用

| 既存資産 | 再利用先 | ファイルパス:行番号 |
|---|---|---|
| `services/storage.compute_content_key` | プロジェクト内の重複検出 / state ファイル名 | `services/storage.py:66` |
| `services/analysis_state.save_state_by_key` / `load_state_by_key` / `update_state` | そのまま使用。path 解決だけ project-aware 化 | `services/analysis_state.py:79-160` |
| `services/embeddings.LMStudioEmbedderShim` | 変更なし (current_embed_model の解決順序だけ変わる) | `services/embeddings.py:60` |
| `capcom.save_data` / `save_snapshot_image` / `save_prompt` / `save_metadata` / `save_voyager_*` / `save_patents_csv` | モンキーパッチで wrap | `capcom.py:176/89/152/118/225-249/268-374` |
| `capcom.build_zip_bytes` / `capcom.export_session_zip` | プロジェクト階層が整えば「projects/<active>/store/ を zip するだけ」に簡略化できる | `capcom.py:411-470` |
| `utils.render_snapshot_button` | 変更不要 (`capcom.save_snapshot_image` を既に呼んでいるので、そちらの hook で捕捉される) | `utils.py:483-626` |
| `services/private_ui.render_sidebar_extras` | プロジェクト selector を追加する形で拡張 | `services/private_ui.py` |
| `services/lm_studio_models.current_embed_model` / `current_chat_model` | 解決順序の先頭にプロジェクト config を追加 | `services/lm_studio_models.py:117-157` |

---

## 5. Verification

### 5-1. hosted モード不変性
```bash
APOLLO_MODE=hosted streamlit run Home.py
```
- プロジェクト selector が出ないこと
- `projects/` ディレクトリが作られないこと
- 既存 v7 と完全に同一挙動

### 5-2. v7.0 → v7.0-private.2 自動マイグレーション
```bash
# v7.0.0-private.1 で作業したデータが残った volume で起動
docker compose -f deploy/private/docker-compose.yml -f deploy/private/docker-compose.override.yml up -d
docker exec apollo-private-v7 ls -la /var/lib/apollo/projects/default/state/
```
- `projects/default/state/<content_key>.pkl` が v7.0 の pkl と同じファイル (ハードリンク) になっていること
- `projects/default/files/patents/` に旧 uploads の CSV がハードリンクされていること
- サイドバーに default プロジェクトが選択状態で表示されること
- 既存の分析モジュールがそのまま動く (復元不要で進める)
- `projects/.migrated_from_v7.0` sentinel が作られていること

### 5-3. プロジェクト作成と埋め込みモデル固定
- サイドバー「➕ 新規」で "CNF" プロジェクトを作成、`qwen3-embedding-0.6b` を選択
- Home にアクティブプロジェクトが CNF に切り替わったことを確認
- サイドバーの推論モデル selectbox は変更可能、**埋め込みモデルは「固定」表記で変更不可**
- CSV をアップロード → 前処理実行 → `projects/cnf/state/<ck>.pkl` ができる
- `projects/cnf/config.json` に `embedding_model: "text-embedding-qwen3-embedding-0.6b"` が記録されていること

### 5-4. レポート素材の自動永続化
- CNF プロジェクトで Saturn V を実行 → `projects/cnf/store/data/saturnv_clusters.json` ができる
- Snapshot を 3 件キャプチャ → `projects/cnf/store/snapshots/*.png` ができる
- MEGA, Explorer, EAGLE も順次実行 → それぞれの JSON が保存される
- ブラウザを閉じて再ログイン → プロジェクト選択で CNF に戻ると、分析結果の素材が session_state に復元される (= 再計算不要)

### 5-5. プロジェクト切替でベクトル空間独立性
- CNF プロジェクト (qwen3-embedding-0.6b) と Battery プロジェクト (qwen3-embedding-4b) を作成
- 同じ CSV を両方にアップロード・前処理
- それぞれの npy キャッシュが別 content_key で保存されていること (`ls /var/lib/apollo/cache/embeddings/ | wc -l` が 2 以上)
- Saturn V のクラスタ配置が両プロジェクトで独立していること

### 5-6. Vision VOYAGER
- CNF プロジェクトで Saturn V の散布図を 2 枚キャプチャ
- VOYAGER でレポート生成
- LLM のレスポンスに、data_summary だけでは表現できない視覚的言及 ("左下の孤立クラスタ", "密度の偏り" 等) が含まれること
- **Gemini (hosted)** と **LM Studio (private)** の両方で動作確認
- 画像を送らない場合との A/B 比較でレポート品質の差が出ること

### 5-7. CAPCOM ZIP エクスポート
- CAPCOM ページで ZIP ダウンロード
- 内容物が `projects/cnf/store/` の構造と一致していること
- ZIP を展開して Claude Code で Deep Dive レポート生成まで走らせる

### 5-8. 旧来のテストセット
- v7.0 の検証シナリオ (`/home/minoru/.claude/plans/snappy-kindling-curry.md` の前バージョンにあった手動チェックリスト) も全て通ること

---

## 6. 実装順序 (推奨)

1. **Track A** (projects.py) — 他トラックの土台
2. **Track F** (migration) — 既存データを壊さない保証を最初に
3. **Track C** (analysis_state path 解決) — 前処理結果の保存先を project 配下に
4. **Track D** (モデル選択 project 化) — 固定モデルの強制
5. **Track B** (capcom monkey-patch) — レポート素材の自動ミラー
6. **Track G** (UI) — プロジェクトダッシュボード
7. **Track E** (Vision VOYAGER) — レポート生成の最終段階
8. Docker build → 検証

各トラックでテストを書かず、Streamlit 手動検証で閉じる (既存の services/ テスト方針を継承)。

---

## 7. 非対象 / 今後の拡張

### 7.1 v7.0-private.3 候補 (実装確度高)

- **Track I: Vision 専用モデル選択の分離**
  - 現状: VOYAGER Phase 1 で `images=` ありの呼び出しは `current_chat_model()` が
    返す「推論モデル」を使う。推論モデルに `qwen/qwen3-30b-a3b-2507` のような
    text-only モデルを選んでいると multimodal 呼び出しが失敗 → テキスト fallback
    に落ちる (`LMStudioLLMClient.generate_text` の except 節で実装済み)
  - 狙い: 強力な text-only モデル (30B MoE 等) の text 生成品質を犠牲にせず、
    画像送信時だけ vision 専用モデル (`qwen/qwen3-vl-8b` 等) に自動スイッチ
  - 実装範囲:
    1. `projects/<id>/config.json` に `vision_model` (optional) フィールド追加
    2. `services/lm_studio_models.py` に `current_vision_model()` 追加
       (解決順: session_state `apollo_vision_model_select` → project config →
       モデル一覧から VL/vision/multimodal を含むモデル自動検出 → None)
    3. サイドバーに「Vision モデル」selectbox 追加 (推論モデルとは別枠)
    4. `services/llm.py` `_generate_multimodal` 内で vision_model を優先使用
       (あれば切替、なければ chat_model のまま試して失敗したら fallback)
  - 上流 v7 の状態: upstream は Gemini 2.5-flash のみ (multimodal 可) だが
    VOYAGER コードが `module_images` を収集するだけで `generate_content` に
    渡していないため、**実質 vision 非対応**。v7.0-private.2 Track E で初めて
    vision 活性化したが、モデル選択が推論モデルと共通なのが課題

### 7.2 v7.2 以降 (アイデア段階)

- **プロジェクト間のデータコピー / ファイル移動 UI**
- **マルチユーザー / プロジェクトの共有・権限管理** (今は admin 1 人想定)
- **CAPCOM ZIP のプロジェクト単位差分 export**
- **報告書履歴の diff 表示**
- **プロジェクトのテンプレート / prefab 構成**
- **旧 v7.0 sessions/ ディレクトリの削除 UI**: 安全のため v7.0-private.2 では
  残しておく (マイグレーション後に手動削除してもらう)
- **CORE ページ / VOYAGER 外部 LLM プロンプトタブのローカル LLM 対応**:
  Track H は共通関数 `utils.render_ai_label_assistant` / `utils_ai.render_ai_insight_button`
  だけカバー。ページ個別で共通関数化されていない AI プロンプト生成はページ本体
  の改修が必要 (V7 touch zero から外れる)

---

## 8. リスクと対策

| リスク | 対策 |
|---|---|
| マイグレーション失敗で既存データ喪失 | ハードリンク戦略で原本を残す。sentinel 作成前にエラーが出たら中断して次回起動時にリトライ |
| プロジェクト切替中に capcom_store が混ざる | プロジェクト切替時に `st.session_state.clear()` → reload の流れを強制 |
| Vision 呼び出しで LM Studio が画像対応モデルを持っていない | モデル一覧から vision 対応を判定し、非対応なら従来通りテキストで fallback + 警告 |
| プロジェクト数が増えてサイドバー selectbox が重くなる | `projects/*/config.json` の一覧キャッシュ (10s 程度) |
| 既存の `persist_analysis_state()` 呼び出しがアクティブプロジェクトを見失う | `apollo_bootstrap.init()` の最後に default プロジェクトを **必ず** active 化する。アクティブプロジェクトが None になる状況をゼロにする |
| V7 本体の VOYAGER ページが直接 `client.generate_text()` を呼ぶので vision を差し込めない | `create_client()` が返すクラスの `generate_text` を内部で multimodal 判定に分岐させる (V7 側は同じメソッドを呼ぶだけ) |
