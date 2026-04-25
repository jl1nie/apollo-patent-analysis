"""VL (Vision-Language) モデルで snapshot 画像を構造化 JSON に変換する (Track M)。

VOYAGER の Phase 0.5 で使う。視覚と推論を分業するアーキテクチャの視覚側:
  Phase 0.5 (VL-8B)        : PNG → VisualRecord の JSON に焼き付け
  Phase 1/2/3 (Reasoning)  : VisualRecord を evidence_text に差し込んでテキスト推論

分業の狙い: VL-8B は視覚特徴の列挙に専念し、推論は text-only な大規模モデル
(例: Qwen3-Next-80B) に委ねる。multimodal 単段では VL 規模が推論品質を律速する
非対称性があるため、知覚 / 推論を分離すると後段の推論力を最大限活用できる。

## キャッシュ設計
snapshot の PNG バイト列 sha256 をキーに、JSON を永続化する
(``~/.apollo/cache/visual_records/{sha256}.json``)。Plotly/Matplotlib の
``to_image`` は入力が同じなら決定的にバイト一致するため、同じチャートを再描画
しても VL 再実行は不要。セッションまたぎで共有される。

## モジュール単位バッチ
VL は 1 モジュールの全 snapshot を 1 リクエストで処理する (現行 multimodal と
同じ粒度)。ただしキャッシュヒットした snapshot は VL 呼出から除外するので、
全ヒットならモジュール単位の VL 呼出自体がスキップされる。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

import apollo_config


# VL プロンプト / スキーマのバージョン。変更したらキャッシュを無効化したいので
# cache ディレクトリをバージョン配下に切る (旧バージョンのキャッシュが混ざらない)。
_VL_PROMPT_VERSION = "v2"


# ======================================================================
# pydantic スキーマ (VL が出力する JSON の構造)
# ======================================================================


class SpatialPoint(BaseModel):
    """散布図・4象限プロット上の 1 点。"""

    label: str = Field(..., description="ラベル (クラスタ名・出願人名等)")
    position_hint: str = Field(
        ...,
        description=(
            "位置の概略を**方向語のみ**で (例: 'upper_right', 'lower_left', "
            "'near_center', 'on_x_axis'). 数値・座標・CAGR などの値は絶対に書かない"
        ),
    )
    quadrant: str | None = Field(
        None, description="象限ラベル (growth_leader, emerging, mature, declining 等)"
    )
    notes: str | None = Field(
        None,
        description=(
            "隣接関係・孤立・密度などの**定性的な観察のみ**。"
            "数値 (CAGR、件数、パーセンテージ等) は絶対に書かない"
        ),
    )


class SpatialLayout(BaseModel):
    axes: dict[str, str] = Field(
        default_factory=dict, description="軸ラベル {'x': '...', 'y': '...'}"
    )
    points: list[SpatialPoint] = Field(default_factory=list)
    outliers: list[str] = Field(default_factory=list, description="主軸から外れた点の記述")
    density_observations: list[str] = Field(
        default_factory=list, description="象限/領域の密度や偏りの記述"
    )


class CurveObservations(BaseModel):
    shape: Literal[
        "exponential", "plateau", "declining", "double_peak",
        "S_curve", "linear", "volatile", "unknown"
    ] = "unknown"
    inflection_points: list[int] = Field(
        default_factory=list,
        description="変曲点の**年のみ** (x 軸ラベル由来)。値は書かない",
    )
    peak_year: int | None = Field(
        None, description="ピークの**年のみ**。ピーク値は書かない"
    )
    notes: str | None = Field(
        None,
        description="曲線の定性的特徴 (急峻 / なだらか / 周期的 等)。数値は書かない",
    )


class NetworkObservations(BaseModel):
    hubs: list[str] = Field(default_factory=list, description="中心性の高いノード名")
    bridges: list[str] = Field(default_factory=list, description="コミュニティ間の橋渡しノード")
    community_count: int | None = None
    isolation_notes: str | None = Field(
        None, description="孤立ノード・分断構造の記述"
    )


class WordcloudHierarchy(BaseModel):
    dominant: list[str] = Field(
        default_factory=list,
        description=(
            "最大フォントサイズの語 (上位 3-5 件)。**語のみ**を列挙し、"
            "カウント値 (例: '(4094)') は絶対に書かない"
        ),
    )
    secondary: list[str] = Field(
        default_factory=list,
        description="2 番目の層の語。**語のみ**。カウント値は書かない",
    )
    visual_weight_notes: str | None = Field(
        None,
        description=(
            "フォントサイズ比の定性的記述 (例: 'A 群は B 群の 2 倍近く大きい')。"
            "具体的な数値は書かない"
        ),
    )


class VisualRecord(BaseModel):
    """1 snapshot = 1 VisualRecord。"""

    evidence_id: int
    module: str
    chart_type: Literal[
        "scatter_umap", "cluster_dynamics_4quadrant", "timeseries",
        "network", "wordcloud", "quadrant_4", "hype_cycle",
        "bar", "tornado", "treemap", "heatmap", "other"
    ] = "other"
    title: str = ""

    # chart_type に応じて埋める (他は null)
    spatial_layout: SpatialLayout | None = None
    curve_observations: CurveObservations | None = None
    network_observations: NetworkObservations | None = None
    wordcloud_hierarchy: WordcloudHierarchy | None = None

    # スキーマに収まらない視覚的発見の受け皿 (1-3 件)
    raw_observations: list[str] = Field(default_factory=list)

    # 読めなかった場合のフォールバック
    failure_reason: str | None = None


class ModuleVisualBatch(BaseModel):
    """VL が 1 モジュール分を返すときの外側。"""

    module: str
    records: list[VisualRecord]


# ======================================================================
# キャッシュ I/O
# ======================================================================


def _cache_dir() -> Path:
    # プロンプト / スキーマを変えたらキャッシュを自動無効化したいので、バージョン配下に切る。
    # 旧バージョンのキャッシュは手動削除するか、そのまま disk に残して放置。
    d = apollo_config.DATA_ROOT / "cache" / "visual_records" / _VL_PROMPT_VERSION
    d.mkdir(parents=True, exist_ok=True)
    return d


def snapshot_hash(image_bytes: bytes) -> str:
    """PNG バイト列の sha256 (キャッシュキー)。"""
    return hashlib.sha256(image_bytes).hexdigest()


def load_cached(img_hash: str) -> VisualRecord | None:
    """キャッシュから VisualRecord を読む。不存在・破損時は None。"""
    path = _cache_dir() / f"{img_hash}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return VisualRecord.model_validate(data)
    except (json.JSONDecodeError, ValidationError, OSError):
        return None


def save_cache(img_hash: str, record: VisualRecord) -> None:
    """VisualRecord を JSON ファイルに書く。失敗は握り潰す (ベストエフォート)。"""
    try:
        path = _cache_dir() / f"{img_hash}.json"
        path.write_text(
            record.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
    except OSError:
        pass


# ======================================================================
# VL プロンプト構築
# ======================================================================


_MODULE_VISUAL_HINTS: dict[str, str] = {
    "ATLAS": (
        "時系列棒グラフ・出願人ランキング棒グラフ・IPC ヒートマップ・多様性指標の "
        "ゲージ等。時系列は変曲点・ピーク位置・曲線形状を重視。"
    ),
    "Saturn V": (
        "UMAP クラスタ散布図 (cluster_id のラベル付)・クラスタ動態 4 象限 "
        "(X=累積件数 Y=CAGR)・ワードクラウド・ノイズ分析チャート。空間的近接 / "
        "孤立 / 象限ポジションを重視。"
    ),
    "EAGLE": "手動クラスタのランドスケープ散布図・動態マップ。Saturn V と類似。",
    "MEGA": (
        "4 象限プロット (CAGR × 活動量)・出願人軌跡。境界付近のエンティティ名を必ず拾う。"
    ),
    "Explorer": (
        "共起ネットワーク図 (ノード=キーワード)・ワードクラウド・トルネードチャート・"
        "急上昇キーワードバーチャート。ハブキーワード / コミュニティ境界を重視。"
    ),
    "CREW": "共願ネットワーク図 (ノード=出願人)。媒介中心性上位・コミュニティ構造を読む。",
    "CORE": "分類クロス集計ヒートマップ。空白セルと高密度セルを拾う。",
    "NEBULA": (
        "Hype Cycle チャート (特許/論文/ニュースの時系列比較)・学術ランドスケープ "
        "UMAP・マクロイベント年表。3 系統の時系列ギャップを重視。"
    ),
}


_VL_SYSTEM_PROMPT = """あなたはチャート読取アシスタントです。与えられた画像から視覚的特徴を抽出し、
指定された JSON スキーマに厳密に従って記述してください。

## 🚫 絶対禁止事項 (最上位原則)
**あらゆる数値・座標・パーセンテージ・件数・比率を一切書かないこと。**
- CAGR 値 (例: "+31.9%", "0.28"), 件数 (例: "261件"), パーセンテージ (例: "22.2%"),
  座標値 (例: "x=0.3 y=0.7"), フォントサイズ比 (例: "3 倍"), ピーク値 (例: "180件"),
  シェア (例: "35.6%"), これら**すべて**禁止。
- 理由: 数値は data_summary (後段のテキスト推論モデルが直接参照する正確な情報源) に
  既に含まれている。あなたが画像から数値を読み取ると、読み取り誤差 (例: 軸目盛りの
  誤読) により **ハルシネーションを誘発する** ため。
- **年 (x 軸ラベルの一部として明示されている場合のみ)** は例外的に許可。それ以外は一切不可。
- 数値を書くべきか迷った場合は、書かないこと。定性的な方向語 (upper_right, dense,
  isolated, adjacent, 急峻, なだらか 等) で代用せよ。

## 役割
- 推論・解釈・戦略提言は一切しない。**観察事実の構造化のみ**が仕事。
- 数値の意味づけ・データ分析・提言は後段の 80B 推論モデルが行う。
  あなたの仕事は「チャート上に何が見えているか」を**数値なしの構造化テキスト**に焼き付けること。

## その他のルール
- 読めない情報は無理に埋めず、null または空配列を返す。嘘は書かない。
- chart_type に応じて該当する layout/observations だけを埋め、関係ないフィールドは null。
- raw_observations には、スキーマに収まらない視覚的発見 (1-3 件) を短文で書く (ここも数値禁止)。
- 必ず日本語で記述する (ただし英字のラベル・固有名詞は原文のまま)。
- 出力は必ず `{"module": "<module>", "records": [<VisualRecord>, ...]}` 形式の JSON オブジェクト。
"""


def _build_vl_user_prompt(
    module: str,
    snaps: list[tuple[int, dict]],
) -> str:
    """VL に投げる user prompt を組み立てる。スキーマを明示的に添付する。"""
    # スキーマ定義を JSON schema 形式で渡す
    schema_json = json.dumps(
        ModuleVisualBatch.model_json_schema(), ensure_ascii=False, indent=2
    )

    hint = _MODULE_VISUAL_HINTS.get(
        module,
        "このモジュール固有のチャート特性は未知。スキーマの全フィールドから適切に選ぶ。",
    )

    # 各画像の対応表
    lines = []
    for eid, snap in snaps:
        title = snap.get("title", "")
        desc = (snap.get("description", "") or "")[:200]
        lines.append(f"- Evidence {eid}: {title}" + (f" — {desc}" if desc else ""))
    evidence_map = "\n".join(lines)

    return f"""以下の {len(snaps)} 枚のチャートは、APOLLO 特許分析プラットフォームの
**{module}** モジュールで生成された可視化です。各チャートから視覚的特徴を抽出し、
JSON スキーマに従って構造化記述を返してください。

## モジュール視覚特性のヒント
{hint}

## 各画像の対応 (画像の順序と一致)
{evidence_map}

## 出力 JSON スキーマ
以下の pydantic スキーマに厳密に従うこと:

```json
{schema_json}
```

## 出力の最低条件
- `module` フィールドは "{module}" とする
- `records` 配列の要素数は {len(snaps)} (画像枚数と一致)
- 各 record の `evidence_id` は提供された順序の Evidence 番号と一致させる
- `chart_type` は enum の中から画像の種類に最も近いものを 1 つ選ぶ
- 該当する layout/observations の構造体のみ埋め、他は null
- 解釈・推論・戦略提言は書かない (観察のみ)

## 🚫 再掲: 数値は一切書かない
CAGR 値・件数・パーセンテージ・座標値・フォントサイズ比・比率等を文字列フィールドに
埋めてはならない。数値は data_summary (後段モデルが直接参照する) に含まれている。
あなたが数値を書くと視覚記録と data_summary の数値が競合し、後段モデルのハルシネーションを
誘発する。方向語 (upper_right, dense, isolated, adjacent) と定性的修飾 (急峻, なだらか,
孤立, 近接) のみを使用せよ。
"""


# ======================================================================
# メイン API
# ======================================================================


def describe_module(
    module: str,
    snaps_group: list[tuple[int, dict]],
    llm_client,
    vl_model: str | None = None,
) -> list[VisualRecord]:
    """モジュール単位で snapshot 群を VL に投げて VisualRecord リストを返す。

    Args:
        module: モジュール名 (例: "Saturn V")。
        snaps_group: ``[(evidence_id, snapshot_dict), ...]`` 形式。
            snapshot_dict は少なくとも ``images`` または ``image`` のいずれかを持つ。
        llm_client: ``LMStudioLLMClient`` (``generate_json`` を持つ)。
        vl_model: VL モデル ID (未指定なら ``lm_studio_models.current_vision_model()``)。

    Returns:
        evidence_id 順の VisualRecord リスト。VL 失敗分は
        ``failure_reason`` 付きの空 record で返す (処理全体は止めない)。
    """
    if not snaps_group:
        return []

    # VL モデルの解決
    if vl_model is None:
        try:
            from services import lm_studio_models

            vl_model = lm_studio_models.current_vision_model()
        except Exception:  # noqa: BLE001
            vl_model = None
    if not vl_model:
        # VL モデルが見つからない → 全 snapshot を failure で埋める
        return [
            _failure_record(eid, module, "VL モデルが解決できません")
            for eid, _ in snaps_group
        ]

    # キャッシュ参照 + 呼び出し対象の確定
    flat_snaps: list[tuple[int, bytes]] = []  # 代表画像 1 枚ずつ
    for eid, snap in snaps_group:
        img = _pick_primary_image(snap)
        if img:
            flat_snaps.append((eid, img))
        else:
            flat_snaps.append((eid, b""))

    cached: dict[int, VisualRecord] = {}
    to_call: list[tuple[int, bytes]] = []
    for eid, img_bytes in flat_snaps:
        if not img_bytes:
            cached[eid] = _failure_record(eid, module, "snapshot に画像が含まれていない")
            continue
        h = snapshot_hash(img_bytes)
        rec = load_cached(h)
        if rec:
            # evidence_id を現セッションのものに書き換える (キャッシュは画像単位)
            rec.evidence_id = eid
            rec.module = module
            cached[eid] = rec
        else:
            to_call.append((eid, img_bytes))

    # 全キャッシュヒット → VL 呼出スキップ
    if not to_call:
        return [cached[eid] for eid, _ in snaps_group]

    # VL 呼出 (未キャッシュ分のみ)
    call_snaps = [(eid, _pick_snap_dict(snaps_group, eid)) for eid, _ in to_call]
    user_prompt = _build_vl_user_prompt(module, call_snaps)
    images = [img for _, img in to_call]

    try:
        raw = llm_client.generate_json(
            system_prompt=_VL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            images=images,
            model=vl_model,
            max_retries=2,
            temperature=0.2,
        )
        batch = ModuleVisualBatch.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        # バッチごと失敗 → 個別 failure record で埋める
        for eid, _ in to_call:
            cached[eid] = _failure_record(
                eid, module, f"VL 呼出失敗 ({type(e).__name__}): {e!s:.200}"
            )
        return [cached[eid] for eid, _ in snaps_group]

    # batch.records を evidence_id で引ける dict に
    by_eid: dict[int, VisualRecord] = {r.evidence_id: r for r in batch.records}

    # キャッシュ保存 + cached に合流
    for eid, img_bytes in to_call:
        rec = by_eid.get(eid)
        if rec is None:
            cached[eid] = _failure_record(
                eid, module, "VL 応答に該当 evidence_id の record が含まれない"
            )
            continue
        # モデルが evidence_id を誤って別番号で返した場合の補正
        rec.evidence_id = eid
        rec.module = module
        cached[eid] = rec
        save_cache(snapshot_hash(img_bytes), rec)

    return [cached[eid] for eid, _ in snaps_group]


# ======================================================================
# 内部ヘルパ
# ======================================================================


def _pick_primary_image(snap: dict) -> bytes | None:
    """snapshot dict から代表画像を 1 枚取り出す。

    複数画像 (``images``) があっても最初の 1 枚だけを使う (VL の token 爆発防止)。
    レガシー ``image`` キーもフォールバックで見る。
    """
    imgs = snap.get("images")
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, (bytes, bytearray)):
            return bytes(first)
    img = snap.get("image")
    if isinstance(img, (bytes, bytearray)):
        return bytes(img)
    return None


def _pick_snap_dict(
    snaps_group: list[tuple[int, dict]], target_eid: int
) -> dict:
    for eid, snap in snaps_group:
        if eid == target_eid:
            return snap
    return {}


def _failure_record(eid: int, module: str, reason: str) -> VisualRecord:
    return VisualRecord(
        evidence_id=eid,
        module=module,
        chart_type="other",
        title="",
        failure_reason=reason,
    )


# ======================================================================
# Phase 1 への注入用フォーマット
# ======================================================================


def format_record_for_prompt(record: VisualRecord) -> str:
    """Phase 1 analyst_prompt の evidence_text に差し込む文字列を作る。

    JSON をそのまま流すのではなく、人間可読な「視覚記録」セクションに整形する
    (後段の推論モデルは text として受け取る)。null / 空フィールドは省略。
    """
    lines = [
        f"### 視覚記録 [[Evidence {record.evidence_id}]]",
        f"- chart_type: {record.chart_type}",
    ]
    if record.title:
        lines.append(f"- title: {record.title}")
    if record.failure_reason:
        lines.append(f"- ⚠️ 画像解析失敗: {record.failure_reason}")
        return "\n".join(lines)

    if record.spatial_layout:
        sl = record.spatial_layout
        if sl.axes:
            lines.append(
                f"- 軸: x={sl.axes.get('x', '?')}, y={sl.axes.get('y', '?')}"
            )
        if sl.points:
            lines.append("- 配置:")
            for p in sl.points[:20]:
                seg = f"  - {p.label} @ {p.position_hint}"
                if p.quadrant:
                    seg += f" [{p.quadrant}]"
                if p.notes:
                    seg += f" — {p.notes}"
                lines.append(seg)
        if sl.outliers:
            lines.append("- 外れ値: " + "; ".join(sl.outliers[:5]))
        if sl.density_observations:
            lines.append(
                "- 密度観察: " + "; ".join(sl.density_observations[:5])
            )

    if record.curve_observations:
        co = record.curve_observations
        parts = [f"shape={co.shape}"]
        if co.inflection_points:
            parts.append(f"変曲点={co.inflection_points}")
        if co.peak_year is not None:
            parts.append(f"peak_year={co.peak_year}")
        if co.notes:
            parts.append(co.notes)
        lines.append("- 曲線: " + ", ".join(parts))

    if record.network_observations:
        no = record.network_observations
        if no.hubs:
            lines.append("- ハブ: " + ", ".join(no.hubs[:10]))
        if no.bridges:
            lines.append("- ブリッジ: " + ", ".join(no.bridges[:5]))
        if no.community_count is not None:
            lines.append(f"- コミュニティ数: {no.community_count}")
        if no.isolation_notes:
            lines.append(f"- 孤立構造: {no.isolation_notes}")

    if record.wordcloud_hierarchy:
        wh = record.wordcloud_hierarchy
        if wh.dominant:
            lines.append("- 支配的キーワード: " + ", ".join(wh.dominant[:8]))
        if wh.secondary:
            lines.append("- 二次キーワード: " + ", ".join(wh.secondary[:8]))
        if wh.visual_weight_notes:
            lines.append(f"- 視覚階層: {wh.visual_weight_notes}")

    if record.raw_observations:
        lines.append("- その他の視覚的発見:")
        for obs in record.raw_observations[:5]:
            lines.append(f"  - {obs}")

    return "\n".join(lines)
