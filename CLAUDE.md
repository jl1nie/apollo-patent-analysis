# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

APOLLO v6 is a Streamlit multi-page app for AI-powered patent landscape analysis (Japanese/English). It is deployed on Hugging Face Spaces (`app_file: Home.py`, see README frontmatter). User-facing labels and comments are primarily Japanese — keep that when editing UI strings.

## Commands

```bash
pip install -r requirements.txt          # Python deps
streamlit run Home.py                    # Run the app (entry point)
```

There are no tests, linters, or build steps configured. `packages.txt` lists OS-level deps for Hugging Face Spaces (Japanese font + Chromium for Kaleido PNG export).

## Architecture

### Entry point and page flow
- `Home.py` is Mission Control: the only place where raw CSV/Excel is ingested, columns are mapped (`col_map`), SBERT embeddings + TF-IDF are computed, and everything is stashed in `st.session_state`. No other page should re-ingest raw files (NPL is the one exception, handled inside Home).
- `pages/1_🌍_ATLAS.py` ... `pages/9_🌌_NEBULA.py` are Streamlit multipage modules. Streamlit uses the filename (with emoji prefix) for sidebar ordering and labels — **do not rename** without updating all cross-references.
- Each analysis page reads from `st.session_state` and bails out early if `preprocess_done` is False.

### Shared session-state contract (set in `Home.initialize_session_state`)
- `df_main` — the ingested patent DataFrame (everything is read as `dtype=str`; downstream code coerces).
- `df_npl` / `df_npl_accumulated` — optional non-patent-literature (papers, news, policy, market).
- `shared_df` — alias often used by older page code; kept in sync with `df_main`.
- `col_map` — result of the "フェーズ 2" mapping UI; keys are semantic names (title, abstract, claims, applicant, inventor, ipc, fterm, date, ...), values are actual column names.
- `delimiters` — per-field multi-value separator (default `;`).
- `sbert_model`, `sbert_embeddings` — from `paraphrase-multilingual-MiniLM-L12-v2`, cached via `@st.cache_resource`.
- `tfidf_matrix`, `feature_names` — from `advanced_tokenize` (Janome + noun compounding + dynamic stopwords).
- `stopwords` — editable at runtime; falls back to `utils.get_stopwords()`.
- `snapshots` — list of dicts collected by `utils.render_snapshot_button`; consumed by VOYAGER.

When adding a new page, treat this contract as read-mostly. Write back only to namespaced keys (e.g. `core_rules`, `saturnv_label_map`) so modules don't collide.

### Module responsibilities
- `utils.py` (~1100 lines) — fonts, stopwords (patent/NPL modes), sidebar, theme config, HHI/CAGR math, cluster summary + representatives, **`render_snapshot_button`** (the glue that serializes Plotly/Matplotlib figures to PNG via Kaleido for VOYAGER), AI label assistant, keyword/ngram tokenization.
- `utils_ai.py` — `generate_ai_insight_prompt` builds structured prompts (役割/コンテキスト/データ/指示) and `render_ai_insight_button` displays them for copy-paste to external LLMs. This is the path used by most modules; only VOYAGER calls an LLM directly.
- `utils_spatial.py` — spatial-cluster proximity summary used by Saturn V / EAGLE maps.
- `pdf_generator.py` — report assembly for VOYAGER (consumes `snapshots`).

### Snapshot → VOYAGER pipeline
`render_snapshot_button(title, description, key, fig=..., data_summary=..., figs=[...])` is the cross-module capture mechanism. It:
1. Renders Plotly figures with `to_image(format="png", ..., scale=3.0)` — Saturn V uses a computed aspect ratio from axis ranges; other modules use 16:9 at width 1600.
2. Persists PNG bytes + the `data_summary` dict into `st.session_state["snapshots"]`.
3. VOYAGER (`pages/8_📝_VOYAGER.py`) groups snapshots, labels them `Evidence N.png`, and feeds them to `LLMClient` (Google Gemini by default) together with the VOYAGER prompt to produce the strategic report. `pdf_generator.py` then builds the downloadable report.

When emitting a new chart that should be reportable, call `render_snapshot_button` right below it and populate `data_summary` — VOYAGER quality depends on that dict, not on the raw DataFrame.

### Text processing conventions
- Japanese tokenization goes through Janome with noun-noun compounding (`Home.advanced_tokenize`, mirrored by `utils.extract_keywords`). Stopwords are split into patent-specific and NPL-specific lists — pick the right mode via `utils.get_stopwords("patent"|"npl")`.
- Dates are parsed with `Home.robust_parse_date`, which probes ISO, `%Y%m%d`, `%Y`, and Excel serial (origin `1899-12-30`). Prefer this over ad-hoc `pd.to_datetime`.
- IPC codes use `Home.extract_ipc` — it NFKC-normalizes, strips parenthesized noise, and extracts both subgroup and main-class forms.

### External AI
- Most modules do **not** call an LLM — they generate a prompt via `utils_ai` for the user to paste into ChatGPT/Claude/Gemini.
- VOYAGER is the exception and uses `google.generativeai` directly (`LLMClient` in `pages/8_📝_VOYAGER.py`). API keys come from the user through the sidebar, never hard-coded.

### Performance caveats
- `OMP_NUM_THREADS=1` and `TOKENIZERS_PARALLELISM=false` are set at the top of `Home.py` to avoid SBERT/OpenMP deadlocks on Streamlit Cloud — keep these.
- SBERT model + Janome tokenizer are loaded through `@st.cache_resource`; do not instantiate them per-page.
- UMAP/HDBSCAN runs in Saturn V / EAGLE are expensive; results should be cached in session state, not recomputed on every rerender.
