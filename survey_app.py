import streamlit as st
import pandas as pd
import geopandas as gpd
import leafmap.foliumap as leafmap
from streamlit_folium import st_folium
from streamlit_gsheets import GSheetsConnection
import datetime
import os
import folium

# --- アプリの設定 ---
st.set_page_config(page_title="農地調査システム・信大雑草研作成", layout="wide")

# --- カスタムCSS ---
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-size: 14px !important;
    }
    h1 {
        font-size: 22px !important;
        margin-top: -20px !important;
    }
    h3 {
        font-size: 16px !important;
    }
    .stSelectbox label, .stTextInput label, .stNumberInput label, .stDateInput label {
        font-size: 12px !important;
    }
    .stForm {
        padding: 15px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# 設定値
GEOJSON_FILE = 'kawashima2026p.geojson'
CONN_NAME = "gsheets"

# --- 色の設定 ---
def get_marker_color(status):
    color_map = {
        "水稲": "blue",
        "麦": "orange",
        "大豆": "green",
        "そば": "purple",
        "果樹": "darkred",
        "野菜類": "cadetblue",
        "作付なし": "gray",
        "耕作放棄": "black",
        "不明": "white",
        "宅地等": "beige"
    }
    return color_map.get(status, "red")

# --- データの読み込み関数 ---

@st.cache_data
def load_base_polygons():
    """筆ポリゴンの読み込み"""
    if os.path.exists(GEOJSON_FILE):
        try:
            gdf = gpd.read_file(GEOJSON_FILE)
            if gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs("EPSG:4326")
            if 'fid' in gdf.columns:
                gdf['fid'] = pd.to_numeric(gdf['fid'], errors='coerce')
            return gdf
        except Exception as e:
            st.error(f"GeoJSON読み込み失敗: {e}")
            return None
    return None

def load_survey_points(conn):
    """GSheetから調査済みデータを取得"""
    try:
        df = conn.read(ttl=0)
        if df is not None and not df.empty:
            df = df.dropna(subset=['point_lat', 'point_lng'])
            # 必須カラムの補完
            for col in ["備考", "作目"]:
                if col not in df.columns:
                    df[col] = ""
            return df
        return pd.DataFrame(columns=["fid", "point_lng", "point_lat", "調査日", "作付状況", "作目", "調査者", "備考", "タイムスタンプ"])
    except Exception as e:
        return pd.DataFrame()

# --- メイン処理 ---

def main():
    st.markdown("<h1>🗺️ 川島地区農地調査システム (信大作成)</h1>", unsafe_allow_html=True)

    conn = st.connection(CONN_NAME, type=GSheetsConnection)
    gdf_polygons = load_base_polygons()

    # セッション状態の初期化
    if "survey_df" not in st.session_state:
        st.session_state.survey_df = load_survey_points(conn)

    df_survey = st.session_state.survey_df

    if gdf_polygons is None:
        st.warning(f"GeoJSONファイル '{GEOJSON_FILE}' が見つかりません。")
        st.stop()

    # 手動リロード
    if st.button("🔄 最新データを再読み込み"):
        st.session_state.survey_df = load_survey_points(conn)
        st.rerun()

    col_map, col_form = st.columns([2, 1])

    with col_map:
        st.subheader("圃場マップ")
        m = leafmap.Map(locate_control=True)

        m.add_gdf(
            gdf_polygons,
            layer_name="農地筆ポリゴン",
            style={"color": "#3388ff", "weight": 1, "fillColor": "#3388ff", "fillOpacity": 0.1},
            fields=["fid"]
        )

        if not df_survey.empty:
            for _, row in df_survey.iterrows():
                p_color = get_marker_color(row["作付状況"])
                crop_text = f" ({row['作目']})" if row.get('作目') else ""
                memo_text = f" | 備考: {row['備考']}" if row['備考'] else ""
                
                folium.Marker(
                    location=[row["point_lat"], row["point_lng"]],
                    tooltip=f"FID:{row['fid']} | {row['作付状況']}{crop_text} ({row['調査者']}){memo_text}",
                    icon=folium.Icon(color=p_color, icon="info-sign")
                ).add_to(m)

        map_output = st_folium(m, width="100%", height=600, key="survey_map")

    # 地図クリック時の処理
    clicked_fid = None
    clicked_lat = None
    clicked_lng = None

    if map_output.get("last_active_drawing"):
        properties = map_output["last_active_drawing"].get("properties")
        if properties and "fid" in properties:
            clicked_fid = properties["fid"]
            target_poly = gdf_polygons[gdf_polygons["fid"] == clicked_fid]
            if not target_poly.empty:
                centroid = target_poly.geometry.centroid.iloc[0]
                clicked_lat = centroid.y
                clicked_lng = centroid.x

    with col_form:
        st.subheader("📝 調査情報入力")

        with st.form("survey_form", clear_on_submit=True):
            st.number_input("FID (地図から選択)", value=clicked_fid if clicked_fid is not None else 0, disabled=True)

            status_options = ["選択してください", "水稲", "麦", "大豆", "そば", "果樹", "野菜類", "作付なし", "耕作放棄", "不明", "宅地等"]
            entry_status = st.selectbox("作付状況", options=status_options)

            # --- 追加: 作目の入力 ---
            entry_crop = st.text_input("作目 (例: キャベツ、ブロッコリー等)", value="", help="具体的な作物を入力してください")

            entry_date = st.date_input("調査日", value=datetime.date.today())

            surveyor_options = ["選択してください", "A", "B", "C", "その他"]
            entry_surveyor = st.selectbox("調査者", options=surveyor_options)

            entry_memo = st.text_area("備考（特記事項など）", value="", help="雑草の繁茂状況や特記すべき点があれば記入してください")

            submit_button = st.form_submit_button("調査データを保存")

            if submit_button:
                if clicked_fid is None:
                    st.warning("地図上の圃場をクリックしてください。")
                elif entry_status == "選択してください":
                    st.warning("作付状況を選択してください。")
                elif entry_surveyor == "選択してください":
                    st.warning("調査者を選択してください。")
                else:
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    new_row = pd.DataFrame([{
                        "fid": clicked_fid,
                        "point_lng": clicked_lng,
                        "point_lat": clicked_lat,
                        "調査日": entry_date.strftime("%Y-%m-%d"),
                        "作付状況": entry_status,
                        "作目": entry_crop,
                        "調査者": entry_surveyor,
                        "備考": entry_memo,
                        "タイムスタンプ": now
                    }])

                    try:
                        # GSheetへの保存
                        existing_df = conn.read(ttl=0)
                        updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                        conn.update(data=updated_df)

                        # Session Stateの更新
                        st.session_state.survey_df = pd.concat(
                            [st.session_state.survey_df, new_row], ignore_index=True
                        )

                        st.success(f"FID {clicked_fid} ({entry_status}) を保存しました。")

                    except Exception as e:
                        st.error(f"保存失敗: {e}")

    # 履歴表示
    with st.expander("📊 現在の調査データ履歴"):
        if not st.session_state.survey_df.empty:
            try:
                df_display = st.session_state.survey_df
                if "タイムスタンプ" in df_display.columns:
                    df_display = df_display.sort_values("タイムスタンプ", ascending=False)
                st.dataframe(df_display, use_container_width=True)
            except:
                st.dataframe(st.session_state.survey_df, use_container_width=True)
        else:
            st.info("データがありません。")

if __name__ == "__main__":
    main()
