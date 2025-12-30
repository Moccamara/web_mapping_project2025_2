import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from folium.plugins import MeasureControl, Draw, MousePosition
import pandas as pd
import altair as alt
import matplotlib.pyplot as plt
from shapely.geometry import shape, Point

# =========================================================
# APP CONFIG
# =========================================================
st.set_page_config(layout="wide", page_title="Geospatial Enterprise Solution")
st.title("🌍 Geospatial Enterprise Solution")

# =========================================================
# USERS AND ROLES
# =========================================================
USERS = {
    "admin": {"password": "admin2025", "role": "Admin"},
    "customer": {"password": "cust2025", "role": "Customer"},
}

# =========================================================
# SESSION INIT
# =========================================================
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None

# =========================================================
# LOGOUT
# =========================================================
def logout():
    st.session_state.auth_ok = False
    st.session_state.username = None
    st.session_state.user_role = None
    st.session_state.points_gdf = None
    st.rerun()   # ✅ force clean rerun


# =========================================================
# LOGIN
# =========================================================
if not st.session_state.auth_ok:
    st.sidebar.header("🔐 Login")

    username = st.sidebar.selectbox("User", list(USERS.keys()))
    password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login", use_container_width=True):
        if password == USERS[username]["password"]:
            st.session_state.auth_ok = True
            st.session_state.username = username
            st.session_state.user_role = USERS[username]["role"]

            st.success("✅ Login successful")
            st.rerun()   # ✅ THIS is the key fix
        else:
            st.sidebar.error("❌ Incorrect password")

    st.stop()   # ⛔ stop rendering rest of app UNTIL logged in


# =========================================================
# LOAD SE POLYGONS
# =========================================================
SE_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/SE.geojson"

@st.cache_data(show_spinner=False)
def load_se_data(url):
    gdf = gpd.read_file(url).to_crs(epsg=4326)
    gdf.columns = gdf.columns.str.lower().str.strip()
    gdf = gdf.rename(columns={"lregion":"region","lcercle":"cercle","lcommune":"commune"})
    for col in ["region","cercle","commune","idse_new","pop_se","pop_se_ct"]:
        if col not in gdf.columns:
            gdf[col] = 0
    return gdf[gdf.is_valid & ~gdf.is_empty]

gdf = load_se_data(SE_URL)

# =========================================================
# LOAD POINTS
# =========================================================
POINTS_URL = "https://raw.githubusercontent.com/Moccamara/web_mapping/master/data/concession.csv"

@st.cache_data(show_spinner=False)
def load_points(url):
    df = pd.read_csv(url)
    df["LAT"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["LON"] = pd.to_numeric(df["LON"], errors="coerce")
    df = df.dropna(subset=["LAT","LON"])
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["LON"], df["LAT"]),
        crs="EPSG:4326"
    )

if st.session_state.points_gdf is None:
    st.session_state.points_gdf = load_points(POINTS_URL)

points_gdf = st.session_state.points_gdf

# =========================================================
# SAFE SPATIAL JOIN
# =========================================================
def safe_sjoin(points, polygons):
    if points is None or polygons is None or points.empty or polygons.empty:
        return gpd.GeoDataFrame(columns=points.columns, crs=points.crs)
    return gpd.sjoin(points, polygons, predicate="intersects")

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown(f"**User:** {st.session_state.username} ({st.session_state.user_role})")
    if st.button("Logout"):
        logout()

    st.markdown("### 🗂️ Attribute Query")
    region = st.selectbox("Region", sorted(gdf["region"].unique()))
    cercle = st.selectbox("Cercle", sorted(gdf[gdf.region==region]["cercle"].unique()))
    commune = st.selectbox("Commune", sorted(gdf[(gdf.region==region)&(gdf.cercle==cercle)]["commune"].unique()))

    gdf_sel = gdf[(gdf.region==region)&(gdf.cercle==cercle)&(gdf.commune==commune)]

    # =====================================================
    # ✅ ADD POINT BY COORDINATES
    # =====================================================
    st.markdown("### 📍 Add Point by Coordinates")
    lat = st.number_input("Latitude", format="%.6f")
    lon = st.number_input("Longitude", format="%.6f")

    if st.button("➕ Add Point"):
        new_point = gpd.GeoDataFrame(
            [{"LAT":lat,"LON":lon}],
            geometry=[Point(lon,lat)],
            crs="EPSG:4326"
        )
        st.session_state.points_gdf = pd.concat(
            [st.session_state.points_gdf, new_point],
            ignore_index=True
        )
        st.success("Point added successfully")

# =========================================================
# MAP
# =========================================================
minx, miny, maxx, maxy = gdf_sel.total_bounds
m = folium.Map(location=[(miny+maxy)/2,(minx+maxx)/2], zoom_start=17)

folium.TileLayer("OpenStreetMap").add_to(m)
folium.GeoJson(
    gdf_sel,
    name="SE",
    style_function=lambda x: {"color":"blue","weight":2,"fillOpacity":0.1},
    tooltip=folium.GeoJsonTooltip(fields=["idse_new","pop_se","pop_se_ct"])
).add_to(m)

for _, r in st.session_state.points_gdf.iterrows():
    folium.CircleMarker(
        location=[r.geometry.y, r.geometry.x],
        radius=4,
        color="red",
        fill=True
    ).add_to(m)

MeasureControl().add_to(m)
Draw(export=True).add_to(m)
MousePosition(prefix="Coordinates:").add_to(m)
folium.LayerControl().add_to(m)

# =========================================================
# LAYOUT
# =========================================================
col1, col2 = st.columns((3,1))
with col1:
    st_folium(m, height=520, use_container_width=True)

with col2:
    st.subheader("📊 Points statistics")
    pts_inside = safe_sjoin(st.session_state.points_gdf, gdf_sel)
    st.metric("Points in SE", len(pts_inside))
    st.dataframe(pts_inside.drop(columns="geometry"), height=300)

# =========================================================
# FOOTER
# =========================================================
st.markdown("""
---
**Geospatial Enterprise Web Mapping**  
**Dr. Mahamadou Camara, PhD – Geomatics Engineering** © 2025
""")

