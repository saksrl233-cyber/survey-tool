import pandas as pd
import streamlit as st
import plotly.express as px

# =========================
# Page
# =========================
st.set_page_config(page_title="アンケート分析ツール", layout="wide")
st.title("📊 アンケート ローデータ自動集計（実務向け）")

uploaded = st.file_uploader("Excelローデータ(.xlsx)をアップロード", type=["xlsx"])

# =========================
# Helpers
# =========================
def is_binary_like(s: pd.Series) -> bool:
    x = s.dropna()
    if len(x) == 0:
        return False
    vals = set(pd.to_numeric(x, errors="coerce").dropna().unique().tolist())
    return vals.issubset({0, 1})

def split_ma_group(col: str):
    # "質問 - 選択肢" を想定
    if " - " in col:
        q, opt = col.split(" - ", 1)
        return q.strip(), opt.strip()
    return None, None

def build_ma_groups(df: pd.DataFrame):
    groups = {}
    for c in df.columns:
        q, opt = split_ma_group(c)
        if q and opt and is_binary_like(df[c]):
            groups.setdefault(q, []).append(c)
    # 2列以上のみをMAとして扱う
    return {q: cols for q, cols in groups.items() if len(cols) >= 2}

def shorten_label(s: str, max_len: int) -> str:
    s = str(s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"

def topn_with_other(df_counts: pd.DataFrame, label_col: str, value_col: str, top_n: int):
    if len(df_counts) <= top_n:
        return df_counts
    top = df_counts.head(top_n).copy()
    other_sum = df_counts.iloc[top_n:][value_col].sum()
    other_row = pd.DataFrame({label_col: ["その他"], value_col: [other_sum]})
    return pd.concat([top, other_row], ignore_index=True)

def safe_series(s: pd.Series):
    return s.fillna("無回答")

# =========================
# Main
# =========================
if not uploaded:
    st.info("まずExcelをアップロードしてください。")
    st.stop()

df = pd.read_excel(uploaded)
st.success(f"アップロード完了：{df.shape[0]}行 × {df.shape[1]}列")

ma_groups = build_ma_groups(df)
ma_option_cols = set([c for cols in ma_groups.values() for c in cols])
sa_cols = [c for c in df.columns if c not in ma_option_cols]

# =========================
# Sidebar (UI)
# =========================
st.sidebar.header("⚙️ 設定")

page = st.sidebar.radio("画面", ["単純集計（グラフ）", "クロス集計"], index=0)

label_max_len = st.sidebar.slider("ラベル表示の最大文字数（長文対策）", 8, 60, 22)
top_n = st.sidebar.slider("Top表示数（その他にまとめる）", 5, 30, 12)

st.sidebar.divider()
show_preview = st.sidebar.checkbox("データプレビューを表示", value=False)
if show_preview:
    st.subheader("データプレビュー")
    st.dataframe(df.head(50), use_container_width=True)

# =========================
# Page 1: Single question charts
# =========================
if page == "単純集計（グラフ）":
    st.subheader("単純集計（使いやすい形で出す）")

    qtype = st.radio("設問タイプ", ["SA（単一回答）", "MA（複数回答）"], horizontal=True)

    chart_type = st.radio("グラフ種類", ["棒グラフ", "円グラフ"], horizontal=True)

    if qtype.startswith("SA"):
        # Searchable select
        q = st.selectbox("SA設問を選択", sa_cols)
        s = safe_series(df[q])

        counts = s.value_counts(dropna=False).reset_index()
        counts.columns = ["回答（原文）", "件数"]
        counts["割合(%)"] = (counts["件数"] / counts["件数"].sum() * 100).round(1)
        counts = counts.sort_values("件数", ascending=False).reset_index(drop=True)

        # TopN + その他
        counts_top = topn_with_other(counts, "回答（原文）", "件数", top_n)
        counts_top["回答（表示）"] = counts_top["回答（原文）"].apply(lambda x: shorten_label(x, label_max_len))

        left, right = st.columns([1, 1])

        with left:
            st.write("### 件数・割合（原文あり）")
            st.dataframe(counts, use_container_width=True)

        with right:
            st.write("### グラフ")
            if chart_type == "棒グラフ":
                fig = px.bar(counts_top, x="回答（表示）", y="件数", text="件数")
                fig.update_layout(xaxis_title="", yaxis_title="件数")
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = px.pie(counts_top, names="回答（表示）", values="件数", hole=0.35)
                st.plotly_chart(fig, use_container_width=True)

    else:
        if not ma_groups:
            st.warning("MA（複数回答）グループを検出できませんでした。列名が『質問 - 選択肢』形式か確認してください。")
            st.stop()

        ma_q = st.selectbox("MA設問（グループ）を選択", list(ma_groups.keys()))
        cols = ma_groups[ma_q]

        sel = df[cols].fillna(0).apply(pd.to_numeric, errors="coerce").fillna(0)
        option_names = [split_ma_group(c)[1] for c in cols]

        counts = pd.DataFrame({
            "選択肢（原文）": option_names,
            "選択数": sel.sum(axis=0).astype(int).values
        }).sort_values("選択数", ascending=False).reset_index(drop=True)

        counts["割合(%)"] = (counts["選択数"] / len(df) * 100).round(1)

        counts_top = topn_with_other(counts, "選択肢（原文）", "選択数", top_n)
        counts_top["選択肢（表示）"] = counts_top["選択肢（原文）"].apply(lambda x: shorten_label(x, label_max_len))

        left, right = st.columns([1, 1])

        with left:
            st.write("### 選択数・割合（原文あり）")
            st.dataframe(counts, use_container_width=True)

        with right:
            st.write("### グラフ")
            if chart_type == "棒グラフ":
                fig = px.bar(counts_top, x="選択肢（表示）", y="選択数", text="選択数")
                fig.update_layout(xaxis_title="", yaxis_title="選択数")
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = px.pie(counts_top, names="選択肢（表示）", values="選択数", hole=0.35)
                st.plotly_chart(fig, use_container_width=True)

# =========================
# Page 2: Crosstab
# =========================
else:
    st.subheader("クロス集計（表 + 使えるグラフ）")

    cross_type = st.radio("クロスタイプ", ["SA × SA", "SA × MA（選択肢別）"], horizontal=True)

    metric = st.radio("表示指標", ["件数", "行％（Row%）", "列％（Col%）"], horizontal=True)

    # ------------- SA x SA
    if cross_type == "SA × SA":
        left_q = st.selectbox("行（基準）SA設問", sa_cols, key="c_sa_sa_left")
        right_q = st.selectbox("列（比較）SA設問", sa_cols, key="c_sa_sa_right")

        left = safe_series(df[left_q])
        right = safe_series(df[right_q])

        ct = pd.crosstab(left, right)

        if metric == "行％（Row%）":
            view = (ct.div(ct.sum(axis=1), axis=0) * 100).round(1)
        elif metric == "列％（Col%）":
            view = (ct.div(ct.sum(axis=0), axis=1) * 100).round(1)
        else:
            view = ct

        # 라벨 축약(표는 원문 유지)
        view_display = view.copy()
        view_display.index = [shorten_label(i, label_max_len) for i in view_display.index]
        view_display.columns = [shorten_label(c, label_max_len) for c in view_display.columns]

        c1, c2 = st.columns([1, 1])

        with c1:
            st.write("### クロステーブル（原文）")
            st.dataframe(view, use_container_width=True)

        with c2:
            st.write("### グラフ（積み上げ棒）")
            # stacked bar用にlong化
            long = view.reset_index().melt(id_vars=view.index.name or "index", var_name="列", value_name="値")
            long.columns = ["行", "列", "値"]
            long["行"] = long["行"].apply(lambda x: shorten_label(x, label_max_len))
            long["列"] = long["列"].apply(lambda x: shorten_label(x, label_max_len))

            fig = px.bar(long, x="行", y="値", color="列", barmode="stack")
            fig.update_layout(xaxis_title="", yaxis_title=metric)
            st.plotly_chart(fig, use_container_width=True)

    # ------------- SA x MA (option-wise)
    else:
        left_q = st.selectbox("行（基準）SA設問", sa_cols, key="c_sa_ma_left")

        if not ma_groups:
            st.warning("MAグループを検出できませんでした。")
            st.stop()

        ma_q = st.selectbox("列（比較）MA設問（グループ）", list(ma_groups.keys()), key="c_sa_ma_q")
        cols = ma_groups[ma_q]
        option_names = [split_ma_group(c)[1] for c in cols]

        # 선택할 옵션(=컬럼)을 하나 고르게 해서, 그 옵션을 선택한 사람만의 SA 분포를 보게 함
        opt_pick = st.selectbox("比較したい選択肢（1つ選択）", option_names)
        col_pick = cols[option_names.index(opt_pick)]

        mask = pd.to_numeric(df[col_pick].fillna(0), errors="coerce").fillna(0) == 1
        base = safe_series(df.loc[mask, left_q])

        counts = base.value_counts(dropna=False).reset_index()
        counts.columns = ["回答（原文）", "件数"]
        counts["割合(%)"] = (counts["件数"] / counts["件数"].sum() * 100).round(1)
        counts = counts.sort_values("件数", ascending=False).reset_index(drop=True)

        # 표시 지표 선택 반영
        if metric == "件数":
            show_df = counts[["回答（原文）", "件数"]].copy()
            value_col = "件数"
        else:
            show_df = counts[["回答（原文）", "割合(%)"]].copy()
            value_col = "割合(%)"

        show_df_top = topn_with_other(show_df, "回答（原文）", value_col, top_n)
        show_df_top["回答（表示）"] = show_df_top["回答（原文）"].apply(lambda x: shorten_label(x, label_max_len))

        c1, c2 = st.columns([1, 1])

        with c1:
            st.write(f"### 『{opt_pick}』を選んだ人の {left_q} 分布（原文）")
            st.dataframe(show_df, use_container_width=True)

        with c2:
            st.write("### グラフ")
            chart_type = st.radio("グラフ種類", ["棒グラフ", "円グラフ"], horizontal=True, key="sa_ma_chart")
            if chart_type == "棒グラフ":
                fig = px.bar(show_df_top, x="回答（表示）", y=value_col, text=value_col)
                fig.update_layout(xaxis_title="", yaxis_title=metric)
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = px.pie(show_df_top, names="回答（表示）", values=value_col, hole=0.35)
                st.plotly_chart(fig, use_container_width=True)