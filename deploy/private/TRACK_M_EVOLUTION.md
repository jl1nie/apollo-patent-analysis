# Track M — VL 分業アーキテクチャ進化記録 (v7.0-private.3)

**期間**: 2026-04-18 〜 2026-04-19 (1.5 日)
**対象**: VOYAGER レポート生成パイプラインの品質改善
**成果**: 「視覚 (VL-8B) × 推論 (80B) 分業」によるローカル完結・Evidence 根拠型・経営層向け戦略レポート

## 背景

Track E (a0b23ae, 2026-04-16) で multimodal 単段 VOYAGER (VL が Phase 1 で推論まで担当) を導入したが、以下の課題が残った:

- VL-8B が推論まで担当するため、文書の推論品質が VL 規模で律速 (8B 相当)
- 80B クラスの text 推論強モデル (Qwen3-Next-80B) が推論に活用されない
- 視覚観察が散文に溶けてしまい、後段の統合推論で活かされない

**仮説**: 視覚 (perception) と推論 (reasoning) を分業し、VL は構造化記述のみ・推論は text-only 強モデル、とすれば:
1. 推論モデルの知性を最大限活用
2. 視覚観察が構造化 JSON として次段に伝達され、見落としが減る
3. 同じ 24GB VRAM 制約でもモデル swap 運用で両方の恩恵を得られる

## 版別比較 (CNF 特許分析を題材)

| 版 | モデル構成 | サイズ | 核心変更 | 主な問題 |
|---|---|---|---|---|
| **545** (2026-04-19 07:25) | 30B multimodal 単段 | 18KB | 旧 Track E そのまま | 信州大学 CAGR=0.0 を「新興・高ポテンシャル」と分類する論理矛盾 |
| **729** (08:27) | 80B + VL multimodal | 26KB | chat_model を 80B に差替 | `[[Saturn V Data]]` 等の非正規引用混入、数値は一貫 |
| **610** (09:26) | **Track M v1**: VL 0.5 + 80B | 21KB | Phase 0.5 で VisualRecord (JSON) を焼付け | 信州大 CAGR=+0.41 等 VL 由来の数値ハルシネ |
| **338** (09:53) | **Track M v2** (P0+P1) | 28KB | VL スキーマから数値禁止 (P0)、Phase 1 に視覚記録活用ブロック追加 (P1) | 「機会とリスク」≒「推奨アクション」章間重複、「事実として」節マーカー過剰 |
| **945** (10:19) | **Track M v3** (P2+P3) | 19KB | 節マーカー化禁止、章区別ルール、語彙多様性ルール | 「2026 年までに 2 件」等の**未来予測数値 KPI を捏造** (4 項目全て) |
| **756** (10:57) | **Track M v3.1** (P5) | 20KB | 未来予測数値禁止、推奨アクションに Evidence 根拠必須 | 新出固有名詞 (伊藤忠 / ヤマハ発動機 / 日本大学) の実在検証のみ残る |

## 版別の核心変更 (プロンプト差分)

### Track M v1 (P0 前) — `services/vision_descriptor.py` 新規 + `pages/8_📝_VOYAGER.py` Phase 0.5 挿入

- VL-8B が snapshot PNG を pydantic `VisualRecord` (JSON) に焼付け
- `~/.apollo/cache/visual_records/{sha256}.json` で永続化
- Phase 1-3 は text-only、Reasoning モデル (80B) に差替 (サイドバー selectbox)
- VL プロンプトに初期は数値記述制限なし → **VL が座標から CAGR を推測し誤数値**

### Track M v2 — P0 (数値ハルシネ防止) + P1 (視覚記録活用)

**P0**: `_VL_SYSTEM_PROMPT` に「🚫 絶対禁止事項: あらゆる数値・座標・パーセンテージを一切書かない」を最上位原則として追加。`SpatialPoint.position_hint` は方向語のみ、`CurveObservations.peak` → `peak_year` (int のみ)、`WordcloudHierarchy` はカウント値禁止。cache dir を `v2/` にバージョニング。

**P1**: `analyst_system` に `_vd_activation_block` を追加し「Layer 1 (事実) には視覚記録に記された象限ポジション・空間的近接・曲線形状・ネットワーク中心性を**明示的に引用**」と指示。

**副作用**: 「明示」という語彙が strategist_system 既存の「各セクションで明示」と共鳴し、Phase 3 が全章を「**事実として** / **解釈として** / **洞察として** / **提言として**」の節マーカー 4 層で機械的に埋め始める。「機会とリスク」と「推奨アクション」が同一内容のコピペ状態に。

### Track M v3 — P2 (節マーカー緩和 + 章区別 + 語彙多様性)

- `_vd_activation_block` の「明示的に引用」→「本文に自然に織り込む」、例文を散文型に
- `analyst_system` 出力ルール: 「各段落がどの層に該当するか区別できるよう」→「節マーカー使わず散文」
- `strategist_system` 品質基準 #1: 「各セクションで明示」→「論述に織り込む、節マーカー不使用」
- `strategist_system` に新設セクション:
  - **章区別ルール**: 機会とリスク章 (アクション提案書かない) vs 推奨アクション章 (「誰が / 何を / どうやって / 期待成果」の 4 要素)
  - **語彙多様性ルール**: 同一キーフレーズ 3 回以上禁止、固有概念化フレーズ (「水平分業」「学術の壁」等) を奨励

**副作用**: 「期待成果」の要請が既存品質基準 #2「全ての主張に具体的数値」「件数と割合の両方」と合流し、80B が**未来予測 KPI を捏造** (「2026 年までに 2 件の特許出願」「2027 年までに 1 件の商業化」等) する新しいハルシネ vector を開いた。

### Track M v3.1 — P5 (未来予測数値の排除)

- `strategist_system` 品質基準 #2 を範囲限定: 「Layer 1/2 の主張には数値、Layer 4 (提言) は Evidence に明示された値のみ、出典引用を伴う」
- `strategist_system` 禁止事項に追加: 「Evidence に根拠のない未来予測的数値 (年限付き出願件数目標・商業化時期・売上目標・KPI) は絶対禁止」「架空の固有名詞・イベント・規格名も禁止」
- 推奨アクション章の 4 要素を「誰が / 何を / どうやって / **根拠となる Evidence**」に変更 (「期待成果」を削除)
- 期待成果を書く場合は「Evidence 既存値を参照した**質的変化**」のみ許可 (○×例示を付記)

**結果**: 未来予測 KPI が完全消失、すべての提言に Evidence 引用が付くようになった。経営層の KPI 設定裁量を侵害しない健全な分業構造に。

## 最終アーキテクチャ (Track M v3.1)

```
VOYAGER 実行フロー
 ├─ Phase 0: CAPCOM JSON 収集
 │
 ├─ Phase 0.5: Visual Descriptor (NEW)
 │    VL-8B が snapshot PNG を VisualRecord (JSON) に焼付け
 │    - 数値・座標を書かない (P0)
 │    - 方向語 / 定性的観察のみ
 │    - sha256 キャッシュで再実行時スキップ
 │
 │  ── VL-8B アンロード → 80B ロード ──
 │
 ├─ Phase 1: Module Analyst (text-only, 80B)
 │    視覚記録 + data_summary + CAPCOM JSON で 4 層分析
 │    - 節マーカー (「事実として」等) 禁止、散文で書く (P2)
 │    - 視覚記録の象限・近接を本文に織り込む (P1)
 │
 ├─ Phase 2: Cross-Module (text-only, 80B)
 │    Phase 1 結果を横断、定番 13 パターンから選択
 │
 └─ Phase 3: Strategist (text-only, 80B)
      Phase 1/2 結果を統合、戦略レポート執筆
      - 章区別厳守 (機会とリスク vs 推奨アクション)
      - 数値は Evidence 由来のみ、未来予測 KPI 禁止 (P5)
      - 語彙多様性 (同一フレーズ 3 回以上禁止)
      - 推奨アクション 4 要素: 誰が / 何を / どうやって / 根拠 Evidence
```

## 実装の場所

| ファイル | 追加 | 変更 |
|---|---|---|
| `services/vision_descriptor.py` | **新規 (+490 行)** | pydantic スキーマ + sha256 キャッシュ + describe_module |
| `services/llm.py` | +80 行 | `LMStudioLLMClient.generate_json()` (OpenAI 互換 json_object + per-call model 上書き) |
| `services/lm_studio_models.py` | +25 行 | `current_reasoning_model()` (session override → project config → env → chat fallback) |
| `services/private_ui.py` | +30 行 | サイドバーに Reasoning モデル selectbox |
| `apollo_config.py` | +20 行 | `USE_VISION_DESCRIPTOR` / `REASONING_MODEL` / `VISION_DESCRIPTOR_MODEL` env |
| `pages/8_📝_VOYAGER.py` | **±120 行** | Phase 0.5 ループ、`_vd_activation_block`、strategist_system の章区別/語彙多様性/未来予測禁止 |

**V7 本体 (上流) への変更は pages/8_📝_VOYAGER.py 内の 10 行以内** (上流マージ配慮方針を維持)。

## 設計の教訓

### 1. プロンプトの「明示」系語彙は共犯する
複数箇所の「明示」「区別」「具体化」語彙が合流すると、モデルが期待以上に過剰適合し、節マーカー化・章間重複・機械的テンプレ出力を引き起こす。1 箇所の緩和では治らず、**全箇所を同時に緩める**必要があった (P2)。

### 2. 品質基準の一律適用は危険
「全ての主張に数値」は Layer 1 (事実) では適切だが、Layer 4 (提言) に適用されると**未来予測の捏造を強制**する。Layer ごとの基準分離が必要 (P5c)。

### 3. 「期待成果」の無指定は KPI 捏造を呼ぶ
推奨アクションの 4 要素に「期待成果」を入れると、80B は既存の「定量的裏付け必須」ルールと合流して年限付き数値目標を生成する。代替として「根拠となる Evidence」を要素化すると、Evidence 外の捏造を抑制しつつ具体性を保てる (P5a)。

### 4. キャッシュのプロンプトバージョニング
プロンプト変更時は `_VL_PROMPT_VERSION` を bump し cache dir を切替えると、旧版の誤出力を引きずらない。sha256 ベースのキャッシュは同一画像の再実行を高速化するので、プロンプトだけ変える場合はバージョン据え置きで再利用できる。

### 5. 視覚 → 推論の分業は 24GB VRAM 制約下でも実装可能
LM Studio の JIT モデルロード + auto-unload で VL-8B (~5GB) と 80B (~45GB Q4, 一部 CPU offload) をセッション単位で swap。運用コストはモデル切替 1 回分の時間のみ。

## 動作検証 (2026-04-19 時点)

- LM Studio @ WSL gateway `172.17.176.1:1234` で稼働
- VL モデル: `qwen/qwen3-vl-8b` (自動検出では `google/gemma-4-26b-a4b` が選ばれる傾向、サイドバーで明示選択推奨)
- Reasoning モデル: `qwen/qwen3-next-80b` (CPU 一部 offload で ~5-15 t/s)
- 1 周目: ~16 分 (VL + 80B)
- 2 周目以降: Phase 0.5 はキャッシュヒット即完了、80B のみ実行で ~10-15 分

## 未対応 (P5d 以降の将来候補)

- 詳細モードの `シナリオプランニング` (Probable / Best / Risk) — 現状は未来予測を誘発する可能性あり、要検証
- 市場モードの `市場ポテンシャル評価` / `投資対象の優先順位` — 同上
- 新出固有名詞の自動検証 (`grep -l "..." ~/.apollo/sessions/*/data/*.json`) のワンショットツール化
- Phase 3 の `エグゼクティブサマリー` で重複する情報を検出する lint

詳細/市場モードで退行が見られた時点で P5d を実装する方針 (標準モードは 756 で完成)。

## 関連ドキュメント

- 上位計画: `deploy/private/V7_0_PRIVATE_NEXT_PLAN.md`
- コア手順書: `/CLAUDE.md` (APOLLO v7.0.0 全体仕様)
- 関連コミット: `a0b23ae` (v7.1 Track E: Vision VOYAGER multimodal 導入)
