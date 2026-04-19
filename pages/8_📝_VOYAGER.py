import streamlit as st
import pandas as pd
import os
import json
import datetime
import utils
import matplotlib.pyplot as plt
utils.configure_matplotlib_font()
from services.llm import create_client


# ==================================================================
# --- ページ設定 ---
# ==================================================================
st.set_page_config(page_title="APOLLO CAPCOM | VOYAGER", page_icon="📝", layout="wide")
utils.render_sidebar()

st.title("📝 VOYAGER")
st.markdown("スナップショットを収集し、Gemini AIが戦略レポートの骨格を自動生成します。")

st.markdown("""
**VOYAGER** は、分析結果を収集し戦略レポートを生成するためのモジュールです。
スナップショットを選択し、プロンプトをプレビューして外部AIに送信するか、
Gemini APIでレポートの骨格を自動生成できます。
""")


# ==================================================================
# --- 3. Snapshot Curator UI ---
# ==================================================================
st.markdown("---")
st.header("📸 Snapshot Collection")

if 'snapshots' not in st.session_state or not st.session_state['snapshots']:
    st.info("スナップショットがまだありません。ATLASなどの分析画面で「📸 Capture Snapshot」ボタンを押して、重要な発見をここに集めてください。")
    snapshots = []
else:
    snapshots = st.session_state['snapshots']
    
    # スナップショットのグリッド表示
    cols = st.columns(3)
    indices_to_remove = []
    
    for i, snap in enumerate(snapshots):
        with cols[i % 3]:
            with st.container(border=True):
                st.subheader(snap['title'])
                
                # 複数画像表示ロジック
                images = snap.get('images', [])
                main_image = snap.get('image')
                
                if images and len(images) > 1:
                    # 複数画像用タブ
                    tab_names = [f"Img {j+1}" for j in range(len(images))]
                    img_tabs = st.tabs(tab_names)
                    for j, tab in enumerate(img_tabs):
                        with tab:
                             try:
                                 st.image(images[j], caption=f"Evidence {i+1}-{j+1}", use_container_width=True)
                             except Exception as e:
                                 st.error(f"Img Error: {e}")
                
                # フォールバック / 単一画像
                elif main_image:
                    st.image(main_image, use_container_width=True)
                elif snap.get('image_error'):
                    st.error(f"Image Error: {snap['image_error']}")
                    st.caption("※ ターミナルで `pip install -U kaleido` を実行してください。")
                else:
                    st.warning("(No Image)")
                    
                st.caption(f"Source: {snap.get('module', 'Unknown')} | {snap.get('timestamp')}")
                with st.expander("Memo / Data"):
                    st.write(snap.get('description', ''))
                    ds_preview = snap.get('data_summary', '')
                    if isinstance(ds_preview, dict):
                         ds_preview = str(ds_preview)
                    st.code(str(ds_preview)[:200] + "...")
                
                if st.button("🗑️ 削除", key=f"del_{snap['id']}_{i}"):
                    indices_to_remove.append(i)
                
                # ダウンロードボタン
                if snap.get('image'):
                    file_name = f"Evidence {i+1}.png"
                    st.download_button(
                        label="💾 Download Evidence",
                        data=snap['image'],
                        file_name=file_name,
                        mime="image/png",
                        key=f"dl_{snap['id']}_{i}"
                    )

    if indices_to_remove:
        for i in sorted(indices_to_remove, reverse=True):
            del st.session_state['snapshots'][i]
        st.rerun()

# ==================================================================
# --- 4. Mission Control (Prompt) ---
# ==================================================================
st.markdown("---")
st.header("📡 Mission Objective")

col_obj, col_act = st.columns([3, 1])

with col_obj:
    mission_objective = st.text_area(
        "今回の分析レポートの目的 (問い) を設定してください:",
        height=100,
        placeholder="例: 競合A社の直近3年の出願傾向から、彼らが注力している新規事業領域を特定し、自社の対抗策を提案してください。",
        value=st.session_state.get('voyager_objective', '')
    )
    st.session_state['voyager_objective'] = mission_objective

# ==================================================================
# --- 5. Report Generation ---
# ==================================================================
report_placeholder = st.empty()
generated_report = ""


with col_act:
    st.write("")

    # バリデーション
    missing_items_common = []
    if len(snapshots) == 0:
        missing_items_common.append("Snapshots (分析の証拠画像)")
    if len(mission_objective) <= 5:
        missing_items_common.append("Mission Objective (5文字以上の目的記述)")

    is_ready_preview = len(missing_items_common) == 0

    if not is_ready_preview:
        st.warning(f"⚠️ 以下が必要です: {', '.join(missing_items_common)}")

    # --- プロンプト構築ヘルパー ---
    def build_voyager_prompts(objective, current_snapshots):
        # 1. コンテキスト構築
        c_str = f"## Mission Objective\n{objective}\n\n## Collected Evidence (Snapshots)\n"
        for i, snap in enumerate(current_snapshots):
            c_str += f"\n### Evidence {i+1}: {snap['title']}\n"
            c_str += f"- Description: {snap.get('description', '')}\n" # Safeguard get
            c_str += f"- Source Module: {snap.get('module', 'Unknown')}\n"
            
            # 複数画像のヒント
            if snap.get('images') and len(snap['images']) > 1:
                c_str += f"- [Visual Reference Note]: This evidence consists of multiple images. Refer to [Evidence {i+1}-1] for the first chart (e.g. Growth/Ranking) and [Evidence {i+1}-2] for the second (e.g. Network).\n"

            # --- 構造化データ処理 ---
            
            # リストアーティファクトの再帰的クリーナー (['a', 'b'] -> "a, b")
            def clean_data_for_prompt(data, key=None):
                # カスタムフォーマットが必要な特別なリストは平滑化しない
                if key in ['representatives', 'items', 'top_growing_keywords',
                           'emerging_keywords', 'declining_keywords',
                           'hubs_ranked', 'edges_ranked', 'communities', 'bridge_edges'] and isinstance(data, list):
                     return data
                     
                if isinstance(data, dict):
                    return {k: clean_data_for_prompt(v, k) for k, v in data.items()}
                elif isinstance(data, list):
                    # リストを文字列に結合
                    return ", ".join([str(x) for x in data if x is not None])
                elif isinstance(data, (int, float)):
                    return data
                elif isinstance(data, str):
                    return data
                else:
                    return str(data)

            raw_data_sum = snap.get('data_summary', '')
            data_sum = clean_data_for_prompt(raw_data_sum) if isinstance(raw_data_sum, dict) else raw_data_sum
            
            if isinstance(data_sum, dict):
                # 統計情報
                if 'stats' in data_sum:
                    s = data_sum['stats']
                    c_str += f"- [Statistics]\n"
                    if 'cagr' in s: c_str += f"  - CAGR: {s['cagr']} (Trend: {s.get('trend', 'N/A')})\n"
                    if 'hhi' in s: c_str += f"  - HHI: {s['hhi']:.3f} ({s.get('hhi_status', 'N/A')})\n"
                
                # NEBULA: トレンドチャート (ハイプサイクル) 処理
                if data_sum.get('type') == 'trend_chart' and 'stats' in data_sum:
                    c_str += f"- [Trend Analysis Data (Hype Cycle)]\n"
                    t_stats = data_sum['stats']
                    if 'patent_trend' in t_stats and t_stats['patent_trend']:
                        c_str += f"  - Patent Trend: {t_stats['patent_trend']}\n"
                    if 'academic_trend' in t_stats and t_stats['academic_trend']:
                        c_str += f"  - Academic Trend: {t_stats['academic_trend']}\n"
                    if 'news_trend' in t_stats and t_stats['news_trend']:
                        c_str += f"  - News Trend: {t_stats['news_trend']}\n"
                
                # 代表特許
                if 'representatives' in data_sum and data_sum['representatives']:
                     c_str += f"- [Representative Patents (Top {len(data_sum['representatives'])})]\n"
                     for rep in data_sum['representatives']:
                         c_str += f"  {rep}\n"
                
                # マクロリスト項目 (政策/市場)
                if 'items' in data_sum and isinstance(data_sum['items'], list) and data_sum['items']:
                     c_str += f"- [Macro List Content (Policy/Market/Academic)]\n"
                     for item in data_sum['items']:
                         if isinstance(item, dict):
                            yr = item.get('year', '-')
                            dt = item.get('date', yr) # Use detailed date if available, else year
                            tp = item.get('type', 'Unknown')
                            ti = item.get('title', 'No Title')
                            src = item.get('source', '')
                            c_str += f"  - [{dt}] [{tp}] {ti} ({src})\n"
                         else:
                            c_str += f"  - {item}\n"
                
                # チャートデータ (数値)
                if 'chart_data' in data_sum:
                    c_str += f"- [Chart Data]\n{data_sum['chart_data']}\n"

                # ネットワーク統計 (グラフ分析)
                if 'network_stats' in data_sum:
                    ns = data_sum['network_stats']
                    c_str += f"- [Network Structure Analysis]\n"

                    def clean_join(val):
                        if isinstance(val, list):
                            # 構造化リスト対応: dictの場合はキー情報を抽出
                            parts = []
                            for x in val:
                                if isinstance(x, dict):
                                    # hubs_ranked形式: keyword + centrality
                                    if 'keyword' in x:
                                        parts.append(f"{x['keyword']}({x.get('degree_centrality', '')})")
                                    # edges_ranked形式: source-target + jaccard
                                    elif 'source' in x and 'target' in x:
                                        parts.append(f"{x['source']}-{x['target']}(J={x.get('jaccard', '')})")
                                    # communities形式: id + members
                                    elif 'members' in x:
                                        members_str = ', '.join(x['members'][:5])
                                        parts.append(f"Group {x.get('id', '?')+1}: {members_str}")
                                    else:
                                        parts.append(str(x))
                                elif x is not None:
                                    parts.append(str(x))
                            return ", ".join(parts)
                        return str(val)

                    # ノード数・エッジ数・密度
                    if 'nodes' in ns:
                        c_str += f"  - Nodes: {ns['nodes']}, Edges: {ns.get('edges', 'N/A')}"
                        if 'density' in ns:
                            c_str += f", Density: {ns['density']}"
                        c_str += "\n"
                    # ハブ
                    if 'hubs_ranked' in ns:
                        top_hubs = ns['hubs_ranked'][:10] if isinstance(ns['hubs_ranked'], list) else ns['hubs_ranked']
                        c_str += f"  - Top Hubs (Centrality): {clean_join(top_hubs)}\n"
                    elif 'hubs' in ns:
                        c_str += f"  - Top Hubs (Centrality): {clean_join(ns['hubs'])}\n"
                    # エッジ
                    if 'edges_ranked' in ns:
                        top_edges = ns['edges_ranked'][:10] if isinstance(ns['edges_ranked'], list) else ns['edges_ranked']
                        c_str += f"  - Strongest Connections: {clean_join(top_edges)}\n"
                    elif 'edges' in ns:
                        c_str += f"  - Strongest Connections: {clean_join(ns['edges'])}\n"
                    # コミュニティ
                    if 'communities' in ns:
                        c_str += f"  - Community Groups: {clean_join(ns['communities'])}\n"
                    # ブリッジエッジ
                    if 'bridge_edges' in ns and ns['bridge_edges']:
                        bridges = ns['bridge_edges'][:5] if isinstance(ns['bridge_edges'], list) else ns['bridge_edges']
                        c_str += f"  - Bridge Edges (Cross-Community): {clean_join(bridges)}\n"

                # トレンド分析データ（Explorer強化版）
                if 'trend_analysis' in data_sum:
                    ta = data_sum['trend_analysis']
                    c_str += f"- [Trend Analysis]\n"
                    c_str += f"  - Period: {ta.get('period_past', 'N/A')} vs {ta.get('period_recent', 'N/A')}\n"
                    if 'emerging_keywords' in ta:
                        top_emerging = ta['emerging_keywords'][:10]
                        for ek in top_emerging:
                            c_str += f"  - Emerging: {ek.get('keyword', '')} (Growth: {ek.get('growth_rate', '')}, Recent: {ek.get('recent_count', '')})\n"

                # 支配率分析データ（Explorer強化版）
                if 'dominance_analysis' in data_sum:
                    da = data_sum['dominance_analysis']
                    c_str += f"- [Dominance Analysis: {da.get('my_company', '')} vs {da.get('target_company', '')}]\n"
                    if da.get('my_exclusive'):
                        c_str += f"  - My Exclusive Keywords: {', '.join(da['my_exclusive'][:10])}\n"
                    if da.get('target_exclusive'):
                        c_str += f"  - Competitor Exclusive: {', '.join(da['target_exclusive'][:10])}\n"
                    if da.get('contested'):
                        c_str += f"  - Contested (0.4-0.6): {', '.join(da['contested'][:10])}\n"
                

                if 'cluster_summary' in data_sum:
                    c_str += f"- [Cluster Composition]\n{data_sum['cluster_summary']}\n"
                

                if 'matrix_context' in data_sum:
                    c_str += f"- [Context Note] {data_sum['matrix_context']}\n"
                
                # エラー情報など
                if 'error' in data_sum:
                     c_str += f"- [Note] Data extraction partial error: {data_sum['error']}\n"
                
                # --- NEBULA統合スナップショット処理 ---
                if data_sum.get('type') == 'trend_network_consolidated':
                    c_str += f"- [Consolidated Analysis Data]\n"
                    
                    # 1. 手法コンテキスト
                    if 'methodology' in data_sum:
                        c_str += f"  - [Methodology]: {data_sum['methodology']}\n"
                    
                    # 2. 急上昇キーワードランキング (成長率)
                    if 'ranking' in data_sum:
                        r = data_sum['ranking']
                        c_str += f"  - [Emerging Keywords (Growth Ranking)]\n"
                        c_str += f"    Period: {r.get('period_past', '')} vs {r.get('period_recent', '')}\n"
                        if 'top_growing_keywords' in r and isinstance(r['top_growing_keywords'], list):
                             c_str += f"    Top Growing:\n"
                             for k in r['top_growing_keywords']:
                                 c_str += f"      - {k.get('Keyword')} (Growth: {k.get('Growth Rate', 0):.2f}, Recent Count: {k.get('Recent')})\n"

                    # 3. ネットワーク統計
                    if 'network' in data_sum:
                        ns = data_sum['network']
                        c_str += f"  - [Network Structure Analysis]\n"
                        # 安全な結合のためのヘルパー
                        def clean_join_local(val):
                            if isinstance(val, list): return ", ".join([str(x) for x in val if x])
                            return str(val)

                        if 'nodes' in ns: c_str += f"    Nodes: {ns['nodes']}, Edges: {ns['edges']}\n"
                        if 'hubs' in ns: c_str += f"    Top Hubs (Centrality): {clean_join_local(ns['hubs'])}\n"
                        if 'strongest_edges' in ns: c_str += f"    Strongest Connections: {clean_join_local(ns['strongest_edges'])}\n"
                        if 'communities' in ns: c_str += f"    Community Groups: {clean_join_local(ns['communities'])}\n"

            else:
                # レガシー文字列
                c_str += f"- Data Summary: {data_sum}\n"
        
        # 2. システムプロンプト選択
        
        # --- 共通ルール ---
        common_evidence_rules = """
        ### 証拠引用の絶対ルール (Strict Evidence Rules)
        1. **形式 (Format):** 引用は **`[[Evidence X]]`** の形式（Xは番号）**のみ** を使用してください。
           - **絶対禁止 (Prohibited):** `[[NEBULA]]`, `[[Explorer]]`, `[[Saturn V]]` などのモジュール名タグは**決して使用しないでください**。
           - **禁止:** `[[Evidence 1, 2]]` のようなカンマ区切りも不可です。`[[Evidence 1]] [[Evidence 2]]` と記述してください。
        2. **配置 (Placement):** 必ず文末または段落末尾に `[[Evidence X]]` タグを配置してください。
        3. **根拠の明確化:** 「なぜそう言えるのか」を、必ず具体的な証拠データや数値を引用して説明してください。
        """
        
        # --- フェーズ1: 分析官 (証拠抽出) ---
        analyst_system_prompt = f"""
        あなたは熟練した **「特許・市場分析官 (Patent & Market Analyst)」** です。
        あなたの仕事は、与えられた複数の「証拠 (Evidence)」を含むデータグループを分析し、**構造化された洞察テキスト (Structured Insight)** を抽出することです。
        
        ### 目的
        視覚的なグラフと数値データを、後の工程で「戦略レポート」を執筆するCSOが使えるような、明確な事実と洞察に変換してください。
        
        ### 必須要件
        1. **Reference by Evidence ID:** 洞察を記述する際は、必ず **「Evidence X によれば〜」** や **「(Evidence X)」** のように、情報源となる **Evidence番号** を明記してください。モジュール名（NEBULAなど）で曖昧に参照しないでください。
        2. **Visual & Data Synthesis:** チャートの視覚的なトレンドと、「Data Summary」内の具体的な数値を組み合わせて分析してください。
        3. **Representative Citations (最重要):**
           - 提供された「代表特許/文献リスト」の中から、分析を裏付ける**具体的な事例を2〜3件**引用してください。
           - 記述形式: 「例えば、[出願人]の『[発明の名称]』(出願年) は、〜〜を示唆している。(Evidence X)」
        4. **出力フォーマット:**
           - **観測事実 (Observation):** 何が起きているか。
           - **データ裏付け (Data Backup):** 具体的な数値。
           - **情報源 (Source):** 該当する Evidence ID。
        
        ### 出力スタイル
        - 言語: 日本語
        - 箇条書きで簡潔に。
        """
        
        # --- フェーズ2: 戦略官 (レポート統合) ---
        strategist_sys_base = f"""
        あなたは **「最高戦略責任者 (Chief Strategy Officer: CSO)」** です。
        あなたは部下の分析官たちから「分析レポート（各証拠の洞察）」と、クライアントからの「Mission Objective（目的）」を受け取りました。
        あなたの任務は、これらバラバラの洞察を統合し、一つの首尾一貫した **「戦略インテリジェンス・レポート」** を執筆することです。
        
        ### Mission Objective
        {{objective}}
        
        ### Core Mandates (鉄則)
        1. **Storytelling:** 単に洞察を羅列するのではなく、Mission Objectiveに対する「答え」となるようなストーリーを構築してください。
        2. **Evidence Integration:** 主張の根拠として、必ず提供された `[[Evidence X]]` タグを文中に埋め込んでください。
        3. **Specific Citations:** 分析官のレポートに含まれている「具体的な特許事例（社名・技術名）」を、**最終レポートに必ず盛り込んでください**。具体性が説得力を生みます。
        4. **Gap Analysis (Market vs Patent):** 市場情報(NPL)のトレンドと、特許活動(Patent)の整合性・ギャップを必ず分析してください。「ニュース等の市場情報からはトレンドを読み取り、特許情報とのギャップ（市場は拡大しているが特許出願は減少している、等）を導く」ことで、リスクや機会を浮き彫りにしてください。
        
        {common_evidence_rules}
        
        ### Report Structure
        1. **Executive Strategy Brief:** 問いに対する直截的な回答・結論 (Verdict)。
        2. **Strategic Drivers (Synthesis):** 複数の証拠を掛け合わせた要因分析。
        3. **Detailed Findings:**
           - 具体的な特許・市場の事例を引用。
           - `[[Evidence X]]` タグを使用。
        4. **Future Scenarios:** リスクと機会のシナリオ分析。
        
        **言語:** 日本語 (経営層を唸らせる、格調高く論理的なビジネス文書スタイル)
        **Output Volume:** Extremely Detailed (Minimum 4000 characters). 各セクションにおいて、表面的な要約ではなく、徹底的な深掘り分析を行ってください。
        """
        
        # Phase 1タスクをモジュールごとにグループ化するヘルパー関数
        def build_phase1_tasks_grouped(all_snapshots):
            grouped_tasks = {}
            tasks = []
            
            # データ文字列を安全に抽出するヘルパー
            def get_data_str(d):
                return clean_data_for_prompt(d)
            
            # 1. スナップショットのグループ化
            for i, snap in enumerate(all_snapshots):
                 module = snap.get('module', 'General')
                 if module not in grouped_tasks: grouped_tasks[module] = []
                 grouped_tasks[module].append((i, snap))
            
            # 2. モジュールごとに1つのタスクを作成
            for module_name, snaps in grouped_tasks.items():
                
                module_content = f"### Analysis Target: {module_name} Data Group\n"
                module_content += "以下の証拠グループを統合的に分析し、このモジュール（視点）からの包括的なインサイトを抽出してください。\n\n"
                module_images = []
                
                for (index, snap) in snaps:
                    raw_data = snap.get('data_summary', {})
                    domain = raw_data.get('domain', 'Patent') if isinstance(raw_data, dict) else 'Patent'
                    
                    ref_label = "引用・参照用特許リスト"
                    if domain == 'Academic': ref_label = "引用・参照用文献リスト (Literature)"
                    elif domain == 'News': ref_label = "引用・参照用ニュース/レポートリスト (News/Market)"
                    elif domain == 'Policy/Market': ref_label = "引用・参照用 ポリシー/市場レポートリスト"

                    # --- コンテンツ構築 ---
                    module_content += f"#### Evidence {index+1}: {snap['title']}\n"
                    module_content += f"- Context/Description: {snap.get('description', '')}\n"
                    
                    # データサマリーと統合データのロジック
                    if isinstance(raw_data, dict) and raw_data.get('type') == 'trend_network_consolidated':
                         # 統合データ（ランキング + ネットワーク）
                         if 'ranking' in raw_data: 
                             module_content += f"- [Growth Data]:\n{get_data_str(raw_data['ranking'])}\n"
                         if 'network' in raw_data:
                             module_content += f"- [Network Data]:\n{get_data_str(raw_data['network'])}\n"
                    else:
                         start_data = raw_data
                        
                         if isinstance(start_data, dict):
                             # 標準処理 - 重複したキーを除外してサマリーを作成
                             exclude_keys = ['ai_insight_context', 'representatives_raw', 'representatives', 'chart_data', 'cluster_summary', 'network_stats']
                             filtered_data = {k: v for k, v in start_data.items() if k not in exclude_keys}
                             module_content += f"- [Data Summary]:\n{get_data_str(filtered_data)}\n"
                            
                             # リッチコンテンツの明示的な処理
                             if 'cluster_summary' in raw_data:
                                  module_content += f"\n- [Cluster/Group Composition]:\n{raw_data['cluster_summary']}\n"
                            
                             if 'network_stats' in raw_data:
                                  module_content += f"\n- [Network Statistics]:\n{get_data_str(raw_data['network_stats'])}\n"

                             # チャートデータ (CSV)
                             if 'chart_data' in raw_data:
                                  module_content += f"- [Chart Table (Top 30)]:\n{raw_data['chart_data']}\n"
                         else:
                             # レガシーストリングデータ
                             module_content += f"- [Data Summary]:\n{start_data}\n"

                    
                    # AI Insight コンテキスト（Saturn V / EAGLE用）
                    if isinstance(raw_data, dict) and 'ai_insight_context' in raw_data:
                        module_content += f"\n- [Advanced Landscape Context (Spatial/Method)]:\n{raw_data['ai_insight_context']}\n"

                    
                    # 代表特許/文献（整形済みリストを優先、無ければRawデータを使用）
                    if isinstance(raw_data, dict):
                        if 'representatives' in raw_data and raw_data['representatives']:
                            module_content += f"- [{ref_label} (Must Cite)]:\n"
                            for rep in raw_data['representatives']:
                                module_content += f"  {rep}\n"
                        elif 'representatives_raw' in raw_data and raw_data['representatives_raw']:
                            module_content += f"- [{ref_label} (Must Cite)]:\n"
                            for r in raw_data['representatives_raw'][:5]:
                                module_content += f"  * 【{r['title']}】 ({r['applicant']}, {r['year']}): {r['abstract'][:100]}...\n"

                    
                    module_content += "\n---\n"
                    
                    # 画像の収集
                    if snap.get('images'): module_images.extend(snap['images'])
                    elif snap.get('image'): module_images.append(snap['image'])

                tasks.append({
                    'id_label': f"Module Analysis: {module_name}",
                    'content': module_content,
                    'images': module_images,
                    'system_prompt_add': f"Focus on insights specific to {module_name}. (ATLAS=Macro/Landscape, NEBULA=Trends/Future, CORE=Companies)." 
                })

            return tasks

        # ラッパー: (Phase 2システムプロンプト, Phase 1タスクリスト, Phase 1システムプロンプトベース) を返す
        # グループ化されたタスクを使用
        phase1_tasks = build_phase1_tasks_grouped(current_snapshots)
        
        return strategist_sys_base, phase1_tasks, analyst_system_prompt

    if st.button("📜 Preview Prompts", help="AIに送るプロンプト構成を確認します。コピーして外部AIに送信できます。", disabled=not is_ready_preview):
        strat_sys, p1_tasks, analyst_sys = build_voyager_prompts(mission_objective, snapshots)

        # 手動利用用にフォーマットされたデータを準備

        # Phase 2 テンプレート
        p2_template = f"""【System Instructions】
{strat_sys.format(objective=mission_objective)}

【User Request】
以下は、各証拠に関する分析官からの報告書 (Analyst Reports) です。これらを統合し、最終レポートを作成してください。

[ここにPhase 1で得られた分析結果（インサイト）を全て貼り付けてください...]
"""

        # Phase 1 フルプロンプト (タスク反復)
        p1_full_prompts = []
        for task in p1_tasks:
            # タスク固有の指示があれば追加
            sys_combined = analyst_sys
            if task['system_prompt_add']:
                sys_combined += f"\n\n(Specific Focus: {task['system_prompt_add']})"

            p1_full = f"""【System Instructions】
{sys_combined}

【User Request】
{task['content']}"""
            p1_full_prompts.append({'label': task['id_label'], 'text': p1_full})

        st.session_state['voyager_prompt_preview_data'] = {
            'p2_template': p2_template,
            'p1_full_prompts': p1_full_prompts
        }
        st.toast("プロンプトを生成しました！下の画面で確認してください。", icon="📋")

# --- プロンプトプレビュー表示 ---
if 'voyager_prompt_preview_data' in st.session_state:
    preview = st.session_state['voyager_prompt_preview_data']
    st.markdown("---")
    st.markdown("### 📜 Prompt Preview")
    st.markdown("以下のプロンプトをコピーして外部AI（ChatGPT/Claude等）に送信できます。")

    tab_p1, tab_p2 = st.tabs(["Phase 1: Analyst (モジュール別分析)", "Phase 2: Strategist (統合レポート)"])

    with tab_p1:
        for i, p in enumerate(preview.get('p1_full_prompts', [])):
            with st.expander(f"📄 {p['label']}", expanded=(i == 0)):
                st.code(p['text'], language=None)

    with tab_p2:
        st.code(preview.get('p2_template', ''), language=None)

# ==================================================================
# --- VOYAGER レポート生成 (LLM) — col_act の外に配置 ---
# ==================================================================
import apollo_config as _apollo_config
st.markdown("---")
if _apollo_config.IS_PRIVATE:
    # サイドバー selectbox / project config / env override を反映した現在値を表示
    from services import lm_studio_models as _lms_label
    _reasoning_label = _lms_label.current_reasoning_model()
    _vision_label = _lms_label.current_vision_model() if _apollo_config.USE_VISION_DESCRIPTOR else None
    if _apollo_config.USE_VISION_DESCRIPTOR and _vision_label:
        st.markdown(
            f"### 🤖 VOYAGER レポート生成 "
            f"(Vision: `{_vision_label}` / Reasoning: `{_reasoning_label}`)"
        )
        st.markdown(
            f"Phase 0.5 で VL モデル (`{_vision_label}`) が snapshot を構造化し、"
            f"Phase 1-3 で推論モデル (`{_reasoning_label}`) が戦略レポートを生成します。"
        )
    else:
        st.markdown(f"### 🤖 VOYAGER レポート生成 (Local LLM: `{_reasoning_label}`)")
        st.markdown(
            f"収集したエビデンスから LM Studio のローカル LLM (`{_reasoning_label}`) で"
            "レポートの骨格を自動生成します。"
        )
    gemini_key = ""  # private モードでは未使用 (factory が無視する)
    col_gem2, = st.columns(1)
else:
    st.markdown("### 🤖 VOYAGER レポート生成 (Gemini API)")
    st.markdown("収集したエビデンスからGemini APIでレポートの骨格を自動生成します。")
    col_gem1, col_gem2 = st.columns([2, 1])
    with col_gem1:
        gemini_key = st.text_input("Gemini API Key:", type="password", key="voyager_gemini_key",
                                   help="Google AI Studio で取得できます: https://aistudio.google.com/apikey")
with col_gem2:
    report_mode = st.selectbox("レポートモード:",
        ["標準分析 (Standard)", "詳細戦略 (Strategic Deep Dive)", "市場統合分析 (Market Intelligence)"],
        key="voyager_report_mode")

_llm_ready = _apollo_config.IS_PRIVATE or bool(gemini_key)
if st.button("📝 レポート生成", type="primary", key="voyager_generate_report",
             disabled=not _llm_ready or not snapshots or len(mission_objective) <= 5):
    try:
        client = create_client(api_key=gemini_key)

        progress = st.progress(0.0)
        status = st.empty()

        # =============================================
        # Phase 0: CAPCOMセッションJSONからデータ自動収集
        # =============================================
        status.markdown("🔄 **データ収集中...**")
        capcom_data_context = ""
        try:
            import capcom as _capcom_mod
            if _capcom_mod.is_active():
                data_summaries = []
                for fname in sorted(_capcom_mod.list_data_files()):
                    if not fname.endswith('.json'):
                        continue
                    jdata = _capcom_mod.get_data(fname)
                    if jdata is None:
                        continue
                    try:
                        # 主要フィールドを抽出（全体を送ると巨大すぎるので要約）
                        summary_parts = [f"\n### {fname}"]
                        if isinstance(jdata, dict):
                            for key in ['metadata', 'cagr', 'trend_direction', 'hhi', 'hhi_status',
                                        'entropy', 'gini', 'quadrant_summary', 'noise_analysis',
                                        'cluster_dynamics', 'spatial_context', 'type',
                                        'total_papers', 'n_clusters', 'noise_count',
                                        'patent_trend', 'academic_trend', 'news_trend']:
                                if key in jdata:
                                    val = jdata[key]
                                    if isinstance(val, (dict, list)):
                                        val_str = json.dumps(val, ensure_ascii=False, default=str)[:800]
                                    else:
                                        val_str = str(val)[:200]
                                    summary_parts.append(f"- {key}: {val_str}")
                            # クラスタ一覧（ラベルと件数のみ）
                            if 'clusters' in jdata and isinstance(jdata['clusters'], list):
                                cluster_summary = []
                                for cl in jdata['clusters'][:30]:
                                    if isinstance(cl, dict):
                                        lbl = cl.get('label', cl.get('auto_label', f"Cluster {cl.get('cluster_id', '?')}"))
                                        cnt = cl.get('count', cl.get('size', '?'))
                                        cluster_summary.append(f"{lbl}({cnt}件)")
                                if cluster_summary:
                                    summary_parts.append(f"- clusters: {', '.join(cluster_summary)}")
                            # 出願人ランキング（上位10）
                            if 'applicant_ranking' in jdata:
                                ar = jdata['applicant_ranking']
                                if isinstance(ar, dict):
                                    top10 = list(ar.items())[:10]
                                    summary_parts.append(f"- top_applicants: {top10}")
                                elif isinstance(ar, list):
                                    summary_parts.append(f"- top_applicants: {ar[:10]}")
                            # マクロイベント
                            if 'items' in jdata and fname.startswith('nebula_macro'):
                                items = jdata['items'][:10]
                                for item in items:
                                    if isinstance(item, dict):
                                        summary_parts.append(f"  - {item.get('year','?')}: {item.get('title', item.get('unified_title',''))[:80]}")
                        data_summaries.append('\n'.join(summary_parts))
                    except Exception:
                        pass

                if data_summaries:
                    capcom_data_context = "\n".join(data_summaries)
                    capcom_data_context = capcom_data_context[:30000]  # データは惜しまず送る
        except Exception:
            pass

        # --- モジュール別分析ガイド ---
        MODULE_ANALYSIS_GUIDE = {
            'ATLAS': """ATLASは基本統計モジュール。以下を分析せよ:
- 出願件数の時系列トレンド（成長/停滞/衰退期の特定、変曲点の理由）
- 出願人ランキング（上位集中度 vs 分散、新規参入者の有無）
- 市場集中度指標（HHI/Entropy/Giniの3指標を組み合わせた構造分析）
- IPC分布（技術領域の広がり、ニッチ vs 汎用技術の判別）
- ライフサイクル（出願人数 vs 出願件数の相関から成長段階を判定）""",

            'Saturn V': """Saturn Vは意味的クラスタリングモジュール。以下を分析せよ:
- クラスタ全体構造（何個のクラスタに分かれたか、それぞれの技術テーマ）
- 空間配置（近接クラスタ＝類似技術、孤立クラスタ＝独自技術の解釈）
- クラスタ動態マップ（X:累積件数×Y:CAGR の4象限—成長リーダー/新興/成熟/ニッチ衰退）
- ノイズ分析（ノイズ率の解釈、萌芽テーマの候補、時系列集中度、出願人集中度）
- ドリルダウン結果があればサブクラスタ構造""",

            'EAGLE': """EAGLEは探索的ランドスケープモジュール。以下を分析せよ:
- 手動クラスタの構成と、Saturn Vの自動クラスタとの差異
- クラスタ動態マップ（成長/衰退ポジション）
- 分析者の仮説がデータでどう検証されたか""",

            'MEGA': """MEGAは動態分析モジュール。以下を分析せよ:
- 4象限分析（CAGR×活動量）: リーダー/新興/成熟/衰退の各象限に誰がいるか
- 象限間の移動（軌跡追跡があれば）: 過去→現在のポジション変化
- 境界付近のエンティティ（象限転換の可能性がある注目対象）""",

            'Explorer': """Explorerはキーワード戦略モジュール。以下を分析せよ:
- 共起ネットワークのコミュニティ構造（技術クラスタとの対応）
- ハブキーワード（中心性が高い＝技術の中核概念）
- 急上昇キーワード（成長率が高い＝新興テーマのシグナル）
- 衰退キーワード（かつての主流技術の退潮）
- トルネードチャート（競合比較のキーワード優位性）""",

            'CREW': """CREWはネットワーク分析モジュール。以下を分析せよ:
- 共願ネットワークの密度（協業が活発か孤立的か）
- 媒介中心性上位者（技術ブローカー＝異分野を橋渡しするキーパーソン）
- コミュニティ構造（組織間アライアンスの実態）
- 急上昇スコア（新規参入者 or 活動再開者）""",

            'CORE': """COREはルールベース分類モジュール。以下を分析せよ:
- 分類軸間のクロス集計結果（どの技術×どの課題の組合せが多い/少ないか）
- 空白セル（＝ホワイトスペース候補）の戦略的意味
- 各分類カテゴリの件数分布の偏り""",

            'NEBULA': """NEBULAは環境分析モジュール。以下を分析せよ:
- Hype Cycle分析（特許・論文・ニュースの時系列ギャップ）
- 学術ランドスケープ（論文のクラスタ構造と特許クラスタとの対応/乖離）
- 学術クラスタ動態マップ（研究テーマの成長/成熟ポジション）
- マクロ環境（政策・市場レポートからの外部要因）
- 特許-NPLギャップ（研究は盛んだが特許化が遅い領域、またはその逆）
- 急上昇キーワード比較（特許/論文/ニュースで異なるトレンド）""",
        }

        # =============================================
        # Phase 1: Analyst（モジュール別深掘り分析）
        # =============================================
        module_groups = {}
        for snap_idx, snap in enumerate(snapshots):
            mod = snap.get('module', 'Unknown')
            if mod not in module_groups:
                module_groups[mod] = []
            module_groups[mod].append((snap_idx + 1, snap))  # 1-based index

        _mod_total = len(module_groups)

        # =============================================
        # Phase 0.5: Visual Descriptor (Track M)
        # VL-8B が snapshot PNG を構造化 JSON に焼き付け、Phase 1/2/3 は text-only 推論に専念する。
        # USE_VISION_DESCRIPTOR=false のときは従来の multimodal 単段経路にフォールバック。
        # =============================================
        use_vd = _apollo_config.USE_VISION_DESCRIPTOR and _apollo_config.IS_PRIVATE
        module_visual_records = {}
        if use_vd:
            status.markdown("🔄 **Phase 0.5/3: 画像の構造化記述中 (VL)...**")
            try:
                from services import vision_descriptor as _vd
                from services import lm_studio_models as _lms
                # Phase 1-3 は Reasoning モデルに切替 (Phase 0.5 の VL 呼出は model= で上書き)
                _reasoning_model = _lms.current_reasoning_model()
                if hasattr(client, "model_name") and _reasoning_model:
                    client.model_name = _reasoning_model
                for idx, (mod, snaps_group) in enumerate(module_groups.items()):
                    status.markdown(
                        f"🔄 **Phase 0.5/3: {mod} 視覚記述中 "
                        f"({idx + 1}/{_mod_total})...**"
                    )
                    module_visual_records[mod] = _vd.describe_module(
                        mod, snaps_group, client
                    )
            except Exception as _vd_exc:  # noqa: BLE001
                st.warning(
                    f"⚠️ Phase 0.5 (視覚記述) が失敗しました: "
                    f"{type(_vd_exc).__name__}: {_vd_exc}. "
                    f"従来の multimodal 経路にフォールバックします。"
                )
                use_vd = False
                module_visual_records = {}

        status.markdown("🔄 **Phase 1/3: モジュール別深掘り分析中...**")
        analyst_results = {}
        for idx, (mod, snaps_group) in enumerate(module_groups.items()):
            progress.progress((idx + 1) / (_mod_total + 2))
            # v7.0-private.2 Track K: モジュール単位の細粒度ステータス
            status.markdown(f"🔄 **Phase 1/3: {mod} モジュール分析中 ({idx + 1}/{_mod_total})...**")

            # Track M: 視覚記録を evidence_text に差し込むためのヘルパ
            _vd_records_by_eid = {}
            if use_vd and mod in module_visual_records:
                _vd_records_by_eid = {
                    r.evidence_id: r for r in module_visual_records[mod]
                }

            evidence_text = ""
            for eid, s in snaps_group:
                title = s.get('title', '')
                desc = s.get('description', '')
                data = s.get('data_summary', '')
                if isinstance(data, dict):
                    data = json.dumps(data, ensure_ascii=False, indent=2, default=str)[:10000]
                evidence_text += f"\n[[Evidence {eid}]] {title}\n説明: {desc}\n"
                _rec = _vd_records_by_eid.get(eid)
                if _rec is not None:
                    from services import vision_descriptor as _vd_fmt
                    evidence_text += _vd_fmt.format_record_for_prompt(_rec) + "\n"
                evidence_text += f"データ:\n{str(data)[:5000]}\n"

            guide = MODULE_ANALYSIS_GUIDE.get(mod, "提供されたエビデンスを詳細に分析してください。")

            _vd_activation_block = ""
            if use_vd:
                _vd_activation_block = """

## 視覚記録の活用
evidence_text 内の各 Evidence には「### 視覚記録 [[Evidence X]]」ブロックが含まれている。
これは VL モデル (Vision-Language) が画像から抽出した**視覚的事実**であり、data_summary に
記載される**数値的事実**とは独立した情報源である。以下の定性的事実は、Layer 1 (事実) の
記述の一部として**本文に自然に織り込む**こと (「視覚記録によれば」「視覚的には」のような
節マーカー的前置きは不要、散文の一要素として統合する):
- 象限ポジション (右上 / 左下 / 中央等)
- 空間的近接・隣接関係
- 孤立・外れ値の分布
- 時系列曲線の形状 (S 字 / プラトー / 変曲点)
- ネットワーク中心性 (ハブ・ブリッジ)
- ワードクラウドの視覚的階層 (支配的語彙)

### 散文化の例
- ○ 良い例: 「クラスタ [13] 環境親和性 CNF 複合体は右上象限に位置し、累積 20 件ながら
  CAGR 31.95% と急成長を示す [[Evidence 5]]」— 視覚要素 (象限) が文中に溶け込んでいる
- × 悪い例: 「**視覚記録によれば**、クラスタ [13] は右上象限に位置。**事実として**、CAGR
  は 31.95%」— 節マーカー化された機械的書き方

## 数値の扱いに関する注意
視覚記録には**数値は一切含まれない**（VL が意図的に数値を書かない設計）。
CAGR 値・件数・パーセンテージ等の**全ての数値は必ず data_summary / CAPCOM データから引用**
すること。視覚記録から推測で数値を書いてはならない。
"""

            analyst_system = f"""あなたは特許情報分析の専門家（{mod}モジュール担当）です。

## 分析の4層モデル（必ず全層を含めること）
Layer 1 — 事実 (Fact): データから直接読み取れる数値・集計結果のみ。「〜件」「〜%」など定量表現を使う。
Layer 2 — 解釈 (Interpretation): 事実に対する技術的・市場的な意味づけ。「〜を示唆する」「〜と解釈できる」。
Layer 3 — 洞察 (Insight): 複数の事実・解釈を組み合わせた高次の知見。「〜にもかかわらず」「〜と合わせて考えると」。
Layer 4 — 提言 (Recommendation): 洞察に基づく具体的アクション提案。「〜を検討すべき」「〜への参入を推奨」。
{_vd_activation_block}
## 出力ルール
- 4 層の視点を本文に織り込む。「**事実として**」「**解釈として**」「**洞察として**」「**提言として**」等の**節マーカーは使わない**（文意で層が読者に伝わる散文で書く）
- 必ず [[Evidence X]] 形式でエビデンスを引用する（本文中に自然に埋め込む）
- 具体的な特許タイトル・出願人名・数値を含める
- **全てのエビデンス（チャート・マップ）を必ず [[Evidence X]] で引用すること**。引用されないエビデンスがあってはならない
- 2,000〜3,000文字程度で記述する
- 箇条書きは要点整理の場合のみ使用し、分析本体は段落で記述する (戦略ペーパーとしての格調を保つ)"""

            # CAPCOMデータから該当モジュールのJSONデータを抽出
            mod_data_section = ""
            if capcom_data_context:
                mod_keywords = {
                    'ATLAS': ['atlas_'],
                    'Saturn V': ['saturnv_'],
                    'MEGA': ['mega_'],
                    'Explorer': ['explorer_'],
                    'CREW': ['crew_'],
                    'CORE': ['core_'],
                    'NEBULA': ['nebula_'],
                    'EAGLE': ['eagle_'],
                }
                kws = mod_keywords.get(mod, [mod.lower()])
                relevant_lines = []
                current_file_relevant = False
                for line in capcom_data_context.split('\n'):
                    if line.startswith('### '):
                        current_file_relevant = any(kw in line.lower() for kw in kws)
                    if current_file_relevant:
                        relevant_lines.append(line)
                if relevant_lines:
                    mod_data_section = f"\n# CAPCOMセッションの分析データ（{mod}関連）\n" + '\n'.join(relevant_lines)

            analyst_prompt = f"""# Mission Objective
{mission_objective}

# {mod}モジュール 分析ガイド
{guide}

# エビデンス（{len(snaps_group)}件）
{evidence_text}
{mod_data_section}

上記のエビデンスとCAPCOMデータに基づき、{mod}モジュールの分析結果を4層モデルで詳細に記述してください。
CAPCOMデータにクラスタ動態マップ（cluster_dynamics）、ノイズ分析（noise_analysis）、多様性指標（entropy/gini）、学術クラスタ（nebula_academic_clusters）、空間配置（spatial_context）等がある場合は必ず言及すること。"""

            # Track M: USE_VISION_DESCRIPTOR=true の場合は Phase 0.5 で視覚記録を
            # evidence_text に焼き付け済みなので、画像は送らず text-only で推論する。
            # false の場合は従来通り multimodal (VL が直接推論する旧経路)。
            if use_vd:
                module_images = None
            else:
                module_images = []
                for _eid, _s in snaps_group:
                    if _s.get('images'):
                        module_images.extend(_s['images'])
                    elif _s.get('image'):
                        module_images.append(_s['image'])
                module_images = module_images if module_images else None

            result = client.generate_text(
                system_prompt=analyst_system,
                user_prompt=analyst_prompt,
                images=module_images,
            )
            analyst_results[mod] = result

        # =============================================
        # Phase 2: Cross-Module Analysis（クロスモジュール分析）
        # =============================================
        status.markdown("🔄 **Phase 2/3: クロスモジュール分析中...**")
        progress.progress(0.8)

        modules_list = list(analyst_results.keys())
        all_analyst_text = "\n\n".join([f"### {mod}\n{text}" for mod, text in analyst_results.items()])

        cross_system = """あなたは特許情報分析のシニアアナリストです。複数モジュールの分析結果を横断的に照合し、単一モジュールでは見えない知見を導出してください。

## クロスモジュール分析パターン（利用可能なものから最低3つ選択）
- Saturn Vクラスタ構造 × MEGA成長率 → 高成長・低参入クラスタの特定
- Explorerバーストキーワード × Saturn Vクラスタラベル → 急上昇テーマの所在特定
- CREWネットワーク × Saturn Vクラスタ → 誰がどの技術を研究しているか
- ATLASの時系列ピーク × NEBULAマクロイベント → 政策・市場要因の照合
- Saturn Vノイズ × NEBULAの学術トレンド → 萌芽技術の学術的裏付け
- クラスタ動態マップ × MEGA PULSE → クラスタレベルとエンティティレベルの成長対比
- NEBULA学術クラスタ × Saturn V特許クラスタ → 研究→特許パイプライン分析

## 出力ルール
- 各パターンごとに「仮説→検証→結論」の構造で記述
- 必ず [[Evidence X]] で引用
- 各パターン 300〜500文字
- 最低3パターン、最大5パターン"""

        cross_prompt = f"""# Mission Objective
{mission_objective}

# 利用可能モジュール
{', '.join(modules_list)}

# モジュール別分析結果
{all_analyst_text[:12000]}

# CAPCOMセッションのデータ要約（全モジュール横断）
{capcom_data_context[:8000]}

上記のモジュール分析結果とCAPCOMデータに基づき、クロスモジュール分析を実施してください。
特にクラスタ動態マップ（cluster_dynamics）とノイズ分析（noise_analysis）、学術-特許クロス分析のデータがある場合は必ず使用すること。"""

        cross_result = client.generate_text(
            system_prompt=cross_system,
            user_prompt=cross_prompt,
        )

        # =============================================
        # Phase 3: Strategic Report（統合戦略レポート）
        # =============================================
        status.markdown("🔄 **Phase 3/3: 統合戦略レポート生成中...**")
        progress.progress(0.9)

        # レポートモード別の構成指示
        mode_key = st.session_state.get('voyager_report_mode', '標準分析')
        if '詳細' in mode_key or 'Deep' in mode_key:
            report_structure = """
## レポート構成（詳細戦略モード）
# エグゼクティブサマリー
Mission Objectiveに対する直接回答。結論→根拠→推奨アクションの順で800文字以内。

# 技術ランドスケープ分析
- クラスタ全体構造の概観（いくつの技術クラスタがあるか）
- クラスタ動態マップの解読（成長リーダー/新興/成熟/ニッチ衰退の各象限）
- ノイズ（萌芽技術）の分析と将来予測
- ワードクラウド・キーワード構造から見た技術トレンド

# 競争環境分析
- 主要プレイヤーのポジショニング（MEGA 4象限）
- 市場集中度の構造（HHI/Entropy/Giniの3指標統合解釈）
- 発明者・出願人ネットワークのキープレイヤー
- 新規参入者・急成長者の特定

# 環境分析（NEBULAデータがある場合）
- Hype Cycle上の現在位置
- 学術研究と特許のギャップ分析
- 学術ランドスケープの研究テーマ構造
- 政策・市場動向との照合

# クロスモジュール統合分析
Phase 2のクロス分析結果を統合し、複眼的な知見を提示。

# 戦略的示唆と提言
- 短期アクション（1年以内）
- 中期戦略（3年）
- リスクと不確実性

# シナリオプランニング
- Probableシナリオ（最も可能性が高い）
- Bestシナリオ（最善の場合）
- Riskシナリオ（最悪の場合）
"""
        elif '市場' in mode_key or 'Market' in mode_key:
            report_structure = """
## レポート構成（市場統合分析モード）
# エグゼクティブサマリー
Mission Objectiveに対する市場視点での直接回答。

# 市場・技術環境の全体像
- 特許出願トレンドと市場動向の対比
- Hype Cycle分析（技術成熟度の判定）
- 政策・規制環境の影響評価

# 技術ポートフォリオ分析
- 技術クラスタの市場ポテンシャル評価
- クラスタ動態マップによる投資対象の優先順位
- 学術研究からの技術シーズ特定

# 競争インテリジェンス
- 主要プレイヤーの戦略ポジション
- 新規参入の脅威評価
- アライアンス・オープンイノベーション機会

# ギャップ分析と機会特定
- 特許-論文ギャップ（研究は盛んだが特許化が遅い領域）
- ホワイトスペース（出願が少ないが市場ニーズがある領域）
- 萌芽技術のビジネス化可能性

# 戦略提言
"""
        else:
            report_structure = """
## レポート構成（標準分析モード）
# エグゼクティブサマリー
Mission Objectiveに対する直接回答。

# 技術トレンド分析
- クラスタ構造と主要技術テーマ
- 成長領域とクラスタ動態
- 萌芽技術（ノイズ分析）

# 競争環境分析
- 主要プレイヤーと市場集中度
- キーワード戦略のポジション

# 戦略的示唆と提言
- 機会とリスク
- 推奨アクション
"""

        strategist_system = f"""あなたは特許情報分析のシニアストラテジストです。経営層・知財戦略部門向けの本格的な戦略レポートを執筆してください。

## 品質基準
1. **4層分析の視点**: 事実(数値) / 解釈(意味) / 洞察(統合知見) / 提言(アクション) の視点を各章の論述に織り込む。ただし「**事実として**」「**解釈として**」「**洞察として**」「**提言として**」等の**節マーカーは使わない** — 散文で書き、文意で層が読者に伝わる書き方を優先する
2. **定量的裏付け (範囲限定)**: Layer 1 (事実) および Layer 2 (解釈) の主張には Evidence / data_summary / CAPCOM データ由来の具体的数値を付記（「128件（全体の23.4%）」のような形式）。ただし **Layer 4 (提言) で数値を書く場合は、必ず Evidence に明示された値のみを引用し、出典 ([[Evidence X]]) を伴う**。未来予測的な数値 (年限付き出願件数目標・商業化時期・売上予測・KPI 等) は Evidence に根拠が無いため禁止
3. **Evidence引用**: 必ず [[Evidence X]] 形式で本文中に自然に引用する（段落末に添える）
4. **具体性**: 出願人名・特許タイトル・キーワード・IPC分類を具体的に記載 (ただし Evidence / data_summary に登場するもののみ — 架空の固有名詞は禁止)
5. **レポートはMarkdown形式**: # でH1（章）、## でH2（節）、### でH3（小節）
6. **各章は最低500文字以上**: 薄い記述は不可。深掘りした分析を求める
7. **数値は件数と割合の両方**: 「152件」ではなく「152件（全体の23.4%）」(ただし Evidence 由来の値のみ)

## チャート・マップの必須掲載ルール
- **全ての章（# 見出し）に最低1つの [[Evidence X]] 引用を含めること**。チャートやマップが無い章は不完全とみなす
- 引用は段落の末尾ではなく、分析の根拠を示す自然な文脈に埋め込む
- 特に以下のチャートは必ず引用すること:
  - 技術ランドスケープ（Saturn Vクラスタマップ）
  - クラスタ動態マップ（4象限）
  - 出願トレンド（ATLAS時系列）
  - 共起ネットワーク（Explorerネットワーク図）
  - MEGA 4象限プロット
- NEBULAデータがある場合: Hype Cycle、学術ランドスケープも必ず引用
- 1つのEvidenceを複数章から引用してもよい（異なる分析視点で言及する）

## 禁止事項
- Layer 1（事実列挙）だけで終わるセクションは不可
- 根拠なき推測や一般論は不可
- Evidence引用なしの段落が3段落以上続くのは不可
- **チャート/マップへの言及がない章は不可**（全章に視覚的根拠を含めること）
- **「事実として」「解釈として」「洞察として」「提言として」の節マーカー化は禁止** (散文で書く)
- **Evidence に根拠のない未来予測的数値は絶対に禁止**:
  - 年限付き出願件数目標 (「2026年までに 2 件の特許出願」等)
  - 商業化時期の断定 (「2027年までに商業化」等)
  - 未来の登録数・市場規模・売上目標等の予測値
  - 架空の KPI・ROI 数値
  → これらは Evidence データに存在しないため書いてはならない。提言は「現状分析から
    導かれる行動方向」のみ記述し、具体的な数値目標設定は読者 (経営層) の裁量に委ねる
- **架空の固有名詞・イベント・規格名も禁止** (実在しない規格番号、実在しない共同事業名、
  実在しない企業提携の断定等)。固有名詞は Evidence / data_summary / CAPCOM データに
  登場するもののみ引用可

## 章ごとの役割差別化 (厳守)
「機会とリスク」章と「推奨アクション」章は**本質的に役割が異なる**。両章の内容が
重複する (同じ事実・同じ提言を 2 回書く) のは品質不合格。

### 「機会とリスク」章の役割
- 機会 (upside) を 2-3 件、リスク (downside) を 2-3 件、それぞれ小見出し (### レベル)
  を切って列挙する
- 各項目は「なぜ機会か / なぜリスクか」を原因・背景・影響の軸で 3-5 行説明する
- **具体的なアクション提案は書かない** (アクションは次章「推奨アクション」が担当)
- 機会とリスクは対立構造として提示 (「〜は機会である一方、〜が同時にリスク」)

### 「推奨アクション」章の役割
- 具体的な行動計画を番号付きリスト 4-5 件で記述
- 各項目は以下の 4 要素を含む:
  - **誰が**: 社内の責任部門 (例: 知財戦略部門、技術開発部門、新規事業開発チーム)
  - **何を**: 具体的な行動対象 (例: ○○クラスタの特許出願、○○との共同研究)
  - **どうやって**: 実行手段・アプローチ (例: 学術機関との連携、既存特許の棚卸し)
  - **根拠となる Evidence**: この提言を正当化する Evidence ID と、そこから読み取れる
    事実・現状分析 (例: 「[[Evidence 5]] のクラスタ [13] は CAGR 31.95% かつ大手未参入」)
- **年限付き数値目標・未来予測的数値は書かない** (「2026 年までに 2 件」「2027 年までに
  商業化」等は Evidence に根拠が無く禁止。もし「期待成果」を書きたければ、Evidence に
  既存の数値を引用した**質的変化**として表現する:
  - ○ 許可: 「CAGR 31.95% (Evidence 5) の高成長領域で先行出願ポジションを確立」
  - ○ 許可: 「現状ノイズ率 19.64% (Evidence 5) の領域を、特許化パイプラインに転換」
  - × 禁止: 「2026 年までに 2 件の特許出願」「2027 年までに 1 件の商業化」
  - × 禁止: 「市場規模 64 億ドル獲得」(Evidence に明示された将来予測値のみ引用可))
- 前章「機会とリスク」で既出のファクトの羅列を繰り返さない
- 機会を捉える / リスクを回避する、の**行動に落とし込む新しい切り口**で述べる
- 箇条書き項目内で 4 層 (事実/解釈/洞察/提言) を機械的に反復しない — action 文体で
  短く鋭く書く

## 語彙と概念化の多様性
- 同一の概念キーフレーズ (例: 「再発見」「再定義」「成熟の終わり」「二重構造」等) を
  全章合計で **3 回以上は使用しない**。3 回目以降は類義の別表現に切り替える
- 各章で**異なる概念ラベル**を提示することを推奨 (例: ある章では「寡占的分散」、
  別章では「ホワイトスペースの三重交差」のように)
- 戦略レポートとして経営層・知財戦略部門を唸らせる格調高い日本語を優先する。
  固有の概念化フレーズ (例: 「水平分業型エコシステム」「学術の壁」「製造→成形→製品の
  パイプライン」等) を積極的に創出する"""

        # Evidence ID 対応表 (Phase 3 で文脈と無関係な Evidence 引用が起きないよう必ず渡す)
        evidence_catalog_lines = []
        for snap_idx, snap in enumerate(snapshots):
            ev_id = snap_idx + 1
            ev_module = snap.get('module', 'Unknown')
            ev_title = snap.get('title', '')
            ev_desc = snap.get('description', '')[:80]
            line = f"- [[Evidence {ev_id}]] ({ev_module}) {ev_title}"
            if ev_desc:
                line += f" — {ev_desc}"
            evidence_catalog_lines.append(line)
        evidence_catalog = '\n'.join(evidence_catalog_lines)

        strategist_prompt = f"""# Mission Objective
{mission_objective}

{report_structure}

# Evidence ID 対応表 (引用ルール厳守)
以下が利用可能な全エビデンス(チャート・マップ・図表)の一覧です。
**[[Evidence X]] を引用する際は、必ず以下の対応表を確認し、引用内容と文脈が一致することを保証してください。**
たとえばワードクラウドのEvidenceをHype Cycleの章で引用するような文脈ミスマッチは厳禁です。

{evidence_catalog}

# モジュール別分析結果（Phase 1）
{all_analyst_text[:12000]}

# クロスモジュール分析結果（Phase 2）
{cross_result[:5000]}

# CAPCOMセッションのデータ要約（定量的根拠として使用すること）
{capcom_data_context[:8000]}

上記の全分析結果とデータを統合し、レポート構成に従って戦略レポートを執筆してください。
各章は # で始め、節は ## で始めてください。
CAPCOMデータに含まれるクラスタ動態、ノイズ分析、多様性指標、学術ランドスケープ、Hype Cycle等の全データを分析に活用すること。
「データがない」「アクセスできない」という記述は禁止。CAPCOMデータ要約に情報が含まれている。

## Evidence 引用の必須ルール (再強調)
- 各 [[Evidence X]] 引用時、Evidence ID 対応表を確認し、その章のテーマと一致するエビデンスを選ぶこと
- 例: 「Hype Cycle 分析」の章では Hype Cycle 関連の Evidence のみ引用、ワードクラウドや無関係なマップは引用しない
- 引用しないエビデンスがあっても問題ない (該当文脈の章がなければ無理に引用しない)
- 全章で最低1つ以上の Evidence を引用するが、必ず文脈に合うものを選ぶ

## Markdown 見出し階層の絶対ルール (厳守)
- **「エグゼクティブサマリー」は必ず `#` 1個 (H1) で書く。`##` (H2) で書いてはならない**
- 各章のメイン見出し (NEBULA / ATLAS / Saturn V / MEGA / Explorer / 戦略提言 等) も `#` 1個 (H1)
- サブセクションは `##` (H2)、その下の項目は `###` (H3)
- レポートは必ず `# エグゼクティブサマリー` から始める (`## エグゼクティブサマリー` は禁止)
- `###` (H3) を使うときは、必ず先に `##` (H2) を書く (H2 を飛ばして H3 を書かない)"""

        final_report = client.generate_text(
            system_prompt=strategist_system,
            user_prompt=strategist_prompt,
        )

        progress.progress(1.0)
        status.success("✅ レポート生成完了（3フェーズ）")

        st.session_state['voyager_generated_report'] = final_report

    except Exception as e:
        # v7.0-private.2: 例外型 + cause chain を表示 (タイムアウト原因の layer 特定用)
        import traceback as _tb
        _chain = []
        _cur = e
        while _cur is not None and len(_chain) < 5:
            _chain.append(f"`{type(_cur).__module__}.{type(_cur).__name__}`: {_cur}")
            _cur = _cur.__cause__ or _cur.__context__
        st.error("レポート生成エラー:\n\n" + "\n\n↑ caused by ↑\n\n".join(_chain))
        with st.expander("詳細トレースバック (private 診断用)", expanded=False):
            st.code(_tb.format_exc(), language="text")

# ==================================================================
# --- レポート表示（APOLLO SPACE レベル）---
# ==================================================================
if 'voyager_generated_report' in st.session_state and st.session_state['voyager_generated_report']:
    st.markdown("---")

    report_text = st.session_state['voyager_generated_report']
    current_snapshots = st.session_state.get('snapshots', [])

    # --- Design System ---
    DS = {
        'navy': '#003366',
        'navy_light': '#004080',
        'accent': '#0066cc',
        'bg': '#ffffff',
        'bg_secondary': '#f8f9fa',
        'text': '#1a1a1a',
        'text_light': '#666666',
        'border': '#e0e0e0',
    }

    # Build snapshot lookup: evidence_id -> snapshot with image
    snap_lookup = {}
    for i, snap in enumerate(current_snapshots):
        snap_lookup[i + 1] = snap

    # --- KPI Summary Bar ---
    df_main = st.session_state.get('df_main')
    total_patents = len(df_main) if df_main is not None else 0
    modules_used = sorted(set(s.get('module', '') for s in current_snapshots))

    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        st.metric("特許件数", f"{total_patents:,}")
    with kpi_cols[1]:
        st.metric("分析モジュール", f"{len(modules_used)}")
    with kpi_cols[2]:
        st.metric("エビデンス", f"{len(current_snapshots)}")
    with kpi_cols[3]:
        st.metric("レポートモード", st.session_state.get('voyager_report_mode', '標準').split('(')[0].strip())

    # --- Rich CSS ---
    st.markdown("""<style>
    .report-container { background:#fff; border:1px solid #e0e0e0; border-radius:0 0 12px 12px; padding:40px 48px; margin:0 0 24px 0; box-shadow:0 2px 8px rgba(0,0,0,0.06); font-family:'Hiragino Kaku Gothic ProN','Noto Sans JP','Meiryo',sans-serif; line-height:1.9; color:#1a1a1a; }
    .report-container h1 { color:#003366; font-size:1.7rem; border-bottom:3px solid #003366; padding-bottom:8px; margin-top:36px; }
    .report-container h2 { color:#004080; font-size:1.3rem; border-bottom:2px solid #e0e0e0; padding-bottom:6px; margin-top:28px; }
    .report-container h3 { color:#333; font-size:1.1rem; margin-top:20px; }
    .report-container p { margin:10px 0; text-align:justify; }
    .report-container ul, .report-container ol { margin:8px 0 8px 24px; }
    .report-container li { margin:4px 0; }
    .report-container blockquote { border-left:4px solid #003366; background:#f0f4f8; padding:12px 16px; margin:12px 0; border-radius:0 8px 8px 0; }
    .report-container table { border-collapse:collapse; width:100%; margin:16px 0; }
    .report-container th { background:#003366; color:#fff; padding:10px 14px; text-align:left; font-weight:600; }
    .report-container td { border:1px solid #ddd; padding:8px 14px; }
    .report-container tr:nth-child(even) { background:#f8f9fa; }
    .report-container strong { color:#003366; }
    .report-container .evidence-badge { background:#e8f0fe; color:#1a73e8; padding:2px 8px; border-radius:4px; font-weight:600; font-size:0.9em; }
    .report-container .evidence-img { border:1px solid #e0e0e0; border-radius:8px; margin:12px 0; max-width:100%; }
    .report-header { background:linear-gradient(135deg,#003366 0%,#004080 100%); color:#fff; padding:32px 48px; border-radius:12px 12px 0 0; margin:16px 0 0 0; }
    .report-header h2 { color:#fff !important; border:none !important; font-size:1.5rem; margin:0; }
    .report-header p { color:rgba(255,255,255,0.8); margin:6px 0 0; font-size:0.9rem; }
    </style>""", unsafe_allow_html=True)

    # --- Header ---
    st.markdown(f"""<div class="report-header">
        <h2>📝 VOYAGER Strategic Report</h2>
        <p>{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} | {len(modules_used)} Modules | {len(current_snapshots)} Evidence</p>
    </div>""", unsafe_allow_html=True)

    # --- Render report with Evidence image inline ---
    import re as _re
    import base64

    def _render_report_html(md_text, snap_lookup):
        """Markdownテキストを処理し、Evidence引用に画像をインライン展開する（各画像は初回のみ表示）"""
        inserted_images = set()  # 既に画像を挿入済みのEvidence ID

        def _replace_evidence(match):
            ev_id = int(match.group(1))
            badge = f'<span class="evidence-badge">📌 Evidence {ev_id}</span>'

            # 2回目以降の引用はバッジのみ（画像重複を防止）
            if ev_id in inserted_images:
                return badge

            snap = snap_lookup.get(ev_id)
            if snap:
                img_bytes = snap.get('image')
                if not img_bytes and snap.get('images') and len(snap['images']) > 0:
                    img_bytes = snap['images'][0]

                if img_bytes:
                    inserted_images.add(ev_id)
                    b64 = base64.b64encode(img_bytes).decode()
                    title = snap.get('title', '')
                    img_tag = f'<br><img class="evidence-img" src="data:image/png;base64,{b64}" alt="Evidence {ev_id}: {title}">'
                    caption = f'<div style="text-align:center; color:#666; font-size:0.85em; margin-bottom:16px;">Fig.{ev_id}: {title}</div>'
                    return badge + img_tag + caption
            return badge

        html = _re.sub(r'\[\[Evidence\s*(\d+)\]\]', _replace_evidence, md_text)
        return html

    rendered_html = _render_report_html(report_text, snap_lookup)
    st.markdown(f'<div class="report-container">{rendered_html}</div>', unsafe_allow_html=True)

    # --- Download Buttons ---
    st.markdown("#### 📥 レポートダウンロード")
    col_dl1, col_dl2 = st.columns([1, 2])

    with col_dl1:
        st.download_button(
            "📥 Markdown (.md)",
            data=report_text,
            file_name=f"voyager_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            key="voyager_download_md"
        )

    with col_dl2:
        with st.expander("📋 Markdownソース"):
            st.code(report_text, language="markdown")

