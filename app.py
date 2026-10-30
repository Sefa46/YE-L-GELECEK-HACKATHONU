from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from siper.actions import synergy_delta
from siper.evaluation import compare_policies
from siper.hydraulics import ProxyHydraulicModel
from siper.network import network_diagnostics
from siper.observations import (
    link_assets_to_vision_samples,
    obstruction_class_for_fraction,
)
from siper.optimizer import optimize_plan
from siper.risk import asset_risk_scores, intervention_benefits
from siper.schemas import ObservationClass, WorkOrderStatus
from siper.storage import (
    load_actions,
    load_assets,
    load_teams,
    load_vision_samples,
    load_weather,
    project_root,
)
from siper.vision import assess_obstruction, mark_obstruction_regions
from siper.weather import (
    WeatherProviderError,
    fetch_open_meteo_forecast,
    forecast_to_weather_event,
    next_rain_hour,
)
from siper.workflow import (
    create_work_orders,
    mark_completed,
    replan_after_verification,
    verify_order,
)


st.set_page_config(page_title="SİPER AI", layout="wide")


@st.cache_data(ttl=900, show_spinner=False)
def load_live_forecast():
    return fetch_open_meteo_forecast()


weather_mode = st.sidebar.radio(
    "Yağış veri kaynağı",
    ["Canlı Open-Meteo", "Çevrimdışı senaryo"],
)
if st.sidebar.button("Canlı tahmini yenile", disabled=weather_mode != "Canlı Open-Meteo"):
    load_live_forecast.clear()
    st.rerun()

base_assets = load_assets()
actions = load_actions()
teams = load_teams()
vision_samples = load_vision_samples()
asset_vision_links = link_assets_to_vision_samples(base_assets, vision_samples)
if "asset_observations" not in st.session_state:
    st.session_state.asset_observations = {
        asset.id: {
            "class": obstruction_class_for_fraction(
                asset.blockage_visual_fraction
            ).value,
            "visual_fraction": asset.blockage_visual_fraction,
            "sample_id": asset_vision_links[asset.id]["id"],
            "image_bytes": None,
        }
        for asset in base_assets
    }
assets = [
    asset.model_copy(
        update={
            "blockage_visual_fraction": st.session_state.asset_observations[
                asset.id
            ]["visual_fraction"]
        }
    )
    for asset in base_assets
]
offline_event = load_weather()
live_forecast = None
live_forecast_error = None
if weather_mode == "Canlı Open-Meteo":
    try:
        live_forecast = load_live_forecast()
    except WeatherProviderError as exc:
        live_forecast_error = str(exc)

live_event = forecast_to_weather_event(live_forecast) if live_forecast else None
event = live_event or offline_event
model = ProxyHydraulicModel(assets, event)
baseline = model.run()
local_timezone = ZoneInfo("Europe/Istanbul")
current_time = datetime.now(local_timezone)
rain_start = event.starts_at.astimezone(local_timezone)
remaining_minutes = max(0, int((rain_start - current_time).total_seconds() // 60))
planning_deadline = min(event.horizon_minutes, remaining_minutes) if remaining_minutes else 1
plan = optimize_plan(model, actions, teams, deadline_minutes=planning_deadline)
asset_map = {asset.id: asset for asset in assets}
action_map = {action.id: action for action in actions}
team_map = {team.id: team for team in teams}

ASSET_STYLES = {
    "inlet": ("Su girişi", "#0284c7", 15),          # Canlı gök mavisi
    "grate": ("Mazgal", "#2563eb", 15),             # Belirgin kobalt mavi
    "culvert": ("Menfez", "#ea580c", 17),           # Keskin turuncu
    "pipe": ("Boru", "#64748b", 14),                # Koyu arduvaz gri
    "collector": ("Kolektör", "#9333ea", 17),       # Canlı mor
    "open_channel": ("Açık kanal", "#059669", 17),   # Zümrüt yeşili
    "pump_station": ("Pompa istasyonu", "#dc2626", 20), # Parlak kırmızı
    "storage": ("Depolama", "#0891b2", 19),         # Turkuaz
    "outfall": ("Deşarj noktası", "#16a34a", 18),    # Canlı çimen yeşili
}

OBSERVATION_LABELS = {
    "unblocked": "Açık",
    "partial": "Kısmi tıkalı",
    "severe": "Ciddi tıkalı",
    "unknown": "Belirsiz",
}

OBSERVATION_COLORS = {
    "severe": "#dc2626",
    "partial": "#eab308",
    "unblocked": "#16a34a",
    "unknown": "#64748b",
}

STATUS_LABELS = {
    "candidate": "Aday görev",
    "assigned": "Ekibe atandı",
    "en_route": "Ekip yolda",
    "in_progress": "Çalışma sürüyor",
    "completed_pending_verification": "Saha doğrulaması bekliyor",
    "verified": "Doğrulandı",
    "failed": "Tamamlanamadı",
    "inaccessible": "Erişilemiyor",
    "cancelled": "İptal edildi",
}

CRITICALITY_LABELS = {
    "alt_gecit": "alt geçit etkilenebilir",
    "hastane_erisimi": "hastane ulaşımı etkilenebilir",
    "ana_arter": "ana ulaşım hattını besliyor",
    "pompa": "ağın çıkış kapasitesini etkiliyor",
    "asagi_akim_kosulu": "aşağı akım koşullarını belirliyor",
}


def remaining_time_text(start_time: datetime, current_time: datetime) -> str:
    remaining_minutes = max(0, int((start_time - current_time).total_seconds() // 60))
    if remaining_minutes == 0:
        return "Yağış başladı"
    hours, minutes = divmod(remaining_minutes, 60)
    return f"{hours} sa {minutes} dk" if hours else f"{minutes} dk"


def condition_text(asset) -> str:
    if asset.blockage_visual_fraction is not None:
        if asset.blockage_visual_fraction >= 0.75:
            return "Ciddi görünür tıkanıklık"
        if asset.blockage_visual_fraction >= 0.4:
            return "Kısmi görünür tıkanıklık"
    if asset.hydraulic_capacity_factor is not None and asset.hydraulic_capacity_factor < 0.55:
        return "Kapasite düşüşü"
    return "İzleniyor"


def priority_reason(asset) -> str:
    reasons = [CRITICALITY_LABELS[tag] for tag in asset.criticality_tags if tag in CRITICALITY_LABELS]
    if asset.hydraulic_capacity_factor is not None and asset.hydraulic_capacity_factor < 0.6:
        reasons.append("mevcut kapasitesi düşük")
    if asset.blockage_visual_fraction is not None and asset.blockage_visual_fraction >= 0.6:
        reasons.append("görünür kapanma yüksek")
    return "; ".join(reasons).capitalize() if reasons else "Ağ akışı üzerinde etkili bir bağlantı noktası."


st.html(
    """
    <style>
        [data-testid="stMainBlockContainer"] {
            padding-top: 0.9rem;
        }

        .siper-hero {
            min-height: 92px;
            display: flex;
            align-items: flex-start;
            gap: 1.4rem;
            margin: 0 0 0.35rem 0;
        }

        .siper-hero__title {
            margin: 0;
            color: inherit;
            font-size: clamp(3.5rem, 5vw, 4.8rem);
            font-weight: 850;
            letter-spacing: -0.055em;
            line-height: 0.98;
            white-space: nowrap;
        }

        .siper-hero__tagline {
            max-width: 690px;
            margin-top: 1.15rem;
            color: inherit;
            opacity: 0.78;
            font-size: clamp(1rem, 1.35vw, 1.2rem);
            font-weight: 650;
            line-height: 1.35;
            transform: rotate(-2.4deg);
            transform-origin: left center;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.35rem;
        }

        .stTabs [data-baseweb="tab-list"] button p {
            font-size: 1.08rem;
            font-weight: 650;
        }

        @media (max-width: 900px) {
            .siper-hero {
                min-height: 118px;
                flex-direction: column;
                gap: 0.25rem;
            }

            .siper-hero__tagline {
                margin-top: 0;
                max-width: 95%;
            }
        }
    </style>
    <header class="siper-hero">
        <h1 class="siper-hero__title">SİPER AI</h1>
        <div class="siper-hero__tagline">
            Yapay Zekâ Destekli, Öngörülü Kentsel Yağmur Suyu ve Taşkın Müdahale Yönetim Sistemi
        </div>
    </header>
    """
)

tabs = st.tabs(
    [
        "Durum Merkezi",
        "Drenaj Ağı",
        "Gözlem & AI",
        "Risk & Senaryolar",
        "Ekip Planlama",
        "Operasyon Takibi",
        "Performans",
    ]
)

with tabs[0]:
    rain_end = rain_start + timedelta(hours=len(event.hourly_rain_mm))

    st.subheader("Trabzon yağış ve hazırlık durumu")
    st.write("**Konum:** Trabzon · Ortahisar ve sahil drenaj hattı")

    if live_event:
        st.caption(
            f"Veri kaynağı: Open-Meteo saatlik tahmin · Son alım: "
            f"{live_forecast.fetched_at:%d.%m.%Y %H:%M}"
        )
    elif live_forecast:
        st.caption(
            "Canlı Open-Meteo tahmininde önümüzdeki 48 saat için yağış olayı "
            "oluşmadı; operasyon modeli çevrimdışı senaryoyu kullanıyor."
        )
    elif live_forecast_error:
        st.caption(
            "Open-Meteo'ya erişilemedi; operasyon modeli çevrimdışı senaryoyu kullanıyor."
        )
    else:
        st.caption("Veri kaynağı: Çevrimdışı planlama senaryosu")

    cols = st.columns(5)
    cols[0].metric("Yerel saat", current_time.strftime("%H:%M"))
    cols[1].metric("Yağış başlangıcı", rain_start.strftime("%H:%M"))
    cols[2].metric("Kalan süre", remaining_time_text(rain_start, current_time))
    cols[3].metric("Yağışın bitişi", rain_end.strftime("%H:%M"))
    cols[4].metric("Toplam yağış", f"{sum(event.hourly_rain_mm):.1f} mm")

    st.info(
        f"Yağışın {rain_start.strftime('%H:%M')} civarında başlaması bekleniyor. "
        f"Hazırlanan planda {len(teams)} ekip için {len(plan.assignments)} görev bulunuyor; "
        f"ağda {len(assets)} altyapı noktası takip ediliyor."
    )

    if live_forecast:
        current_forecast = live_forecast.hours[0]
        upcoming_rain = next_rain_hour(live_forecast)
        live_cols = st.columns(4)
        live_cols[0].metric(
            "Sıcaklık",
            f"{current_forecast.temperature_c:.1f} °C"
            if current_forecast.temperature_c is not None
            else "—",
        )
        live_cols[1].metric(
            "Yağış olasılığı",
            f"%{current_forecast.precipitation_probability_pct:.0f}"
            if current_forecast.precipitation_probability_pct is not None
            else "—",
        )
        live_cols[2].metric(
            "Rüzgâr",
            f"{current_forecast.wind_speed_kmh:.1f} km/sa"
            if current_forecast.wind_speed_kmh is not None
            else "—",
        )
        live_cols[3].metric(
            "Sıradaki yağış",
            upcoming_rain.time.strftime("%d.%m %H:%M") if upcoming_rain else "Beklenmiyor",
        )

    weather_rows = []
    for hour_index, rain_mm in enumerate(event.hourly_rain_mm):
        hour_start = rain_start + timedelta(hours=hour_index)
        hour_end = hour_start + timedelta(hours=1)
        if rain_mm >= 30:
            intensity = "Çok kuvvetli"
        elif rain_mm >= 20:
            intensity = "Kuvvetli"
        elif rain_mm >= 10:
            intensity = "Orta"
        else:
            intensity = "Hafif"
        weather_rows.append(
            {
                "Saat aralığı": f"{hour_start:%H:%M}–{hour_end:%H:%M}",
                "Başlangıç": hour_start,
                "Yağış (mm)": rain_mm,
                "Şiddet": intensity,
            }
        )
    weather_df = pd.DataFrame(weather_rows)

    weather_figure = go.Figure(
        go.Bar(
            x=weather_df["Saat aralığı"],
            y=weather_df["Yağış (mm)"],
            marker_color=["#4f9bd8", "#2f6fa5", "#76add3"],
            text=[f"{value:.0f} mm" for value in weather_df["Yağış (mm)"]],
            textposition="outside",
            hovertemplate="%{x}<br>Yağış: %{y:.1f} mm<extra></extra>",
        )
    )
    weather_figure.update_layout(
        title="Saatlik yağış beklentisi",
        xaxis_title="Saat",
        yaxis_title="Yağış (mm)",
        height=380,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    st.plotly_chart(weather_figure, width="stretch", config={"displayModeBar": False})
    st.dataframe(
        weather_df[["Saat aralığı", "Yağış (mm)", "Şiddet"]],
        width="stretch",
        hide_index=True,
    )

    if live_forecast:
        forecast_rows = [
            {
                "Saat": hour.time,
                "Yağış (mm)": hour.precipitation_mm,
                "Olasılık (%)": hour.precipitation_probability_pct,
                "Sıcaklık (°C)": hour.temperature_c,
            }
            for hour in live_forecast.hours[:24]
        ]
        with st.expander("24 saatlik canlı tahmini göster"):
            st.dataframe(pd.DataFrame(forecast_rows), width="stretch", hide_index=True)

with tabs[1]:
    st.subheader("Bağlantılı drenaj ağı")
    diagnostics = network_diagnostics(assets)
    map_risks = asset_risk_scores(assets, baseline.node_impact)
    maximum_risk = max(map_risks.values())
    severe_ids = {
        asset.id
        for asset in assets
        if st.session_state.asset_observations[asset.id]["class"] == "severe"
    }
    partial_ids = {
        asset.id
        for asset in assets
        if st.session_state.asset_observations[asset.id]["class"] == "partial"
    }

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Düğüm", diagnostics["node_count"])
    c2.metric("Bağlantı", diagnostics["edge_count"])
    c3.metric("Ciddi tıkalı", len(severe_ids))
    c4.metric("Kısmi tıkalı", len(partial_ids))

    map_view = st.radio(
        "Harita görünümü",
        ["Tıkanıklık durumu", "Altyapı türleri"],
        horizontal=True,
    )

    edge_lon: list[float | None] = []
    edge_lat: list[float | None] = []
    for source, target in model.graph.edges:
        upstream = asset_map[source]
        downstream = asset_map[target]
        edge_lon.extend([upstream.lon, downstream.lon, None])
        edge_lat.extend([upstream.lat, downstream.lat, None])

    map_figure = go.Figure()
    map_figure.add_trace(
        go.Scattermap(
            lon=edge_lon,
            lat=edge_lat,
            mode="lines",
            line={"width": 4, "color": "#40566b"},
            hoverinfo="skip",
            name="Akış bağlantısı",
            showlegend=True,
        )
    )

    if map_view == "Tıkanıklık durumu":
        hover_text = []
        for asset in assets:
            risk_ratio = map_risks[asset.id] / maximum_risk
            risk_label = "Yüksek" if risk_ratio >= 0.6 else "Orta" if risk_ratio >= 0.3 else "Düşük"
            observation = st.session_state.asset_observations[asset.id]
            observation_label = OBSERVATION_LABELS[observation["class"]]
            linked_sample_id = observation["sample_id"]
            visual_fraction = (
                f"%{observation['visual_fraction'] * 100:.0f}"
                if observation["visual_fraction"] is not None
                else "Veri yok"
            )
            water_level = f"{asset.water_level_m:.2f} m" if asset.water_level_m is not None else "Veri yok"
            downstream = ", ".join(asset.downstream_ids) if asset.downstream_ids else "Çıkış"
            hover_text.append(
                f"<b>{asset.name}</b><br>"
                f"Kimlik: {asset.id}<br>"
                f"Tür: {ASSET_STYLES[asset.type.value][0]}<br>"
                f"Bölge: {asset.drainage_zone_id}<br>"
                f"Görüntü durumu: {observation_label}<br>"
                f"Görüntü kaydı: {linked_sample_id}<br>"
                f"Risk seviyesi: {risk_label}<br>"
                f"Risk puanı: {map_risks[asset.id]:.2f}<br>"
                f"Görünür kapanma: {visual_fraction}<br>"
                f"Kapasite katsayısı: {asset.hydraulic_capacity_factor:.2f}<br>"
                f"Su seviyesi: {water_level}<br>"
                f"Etki indeksi: {baseline.node_impact[asset.id]:.2f}<br>"
                f"Aşağı akım: {downstream}"
            )
        map_figure.add_trace(
            go.Scattermap(
                lon=[asset.lon for asset in assets],
                lat=[asset.lat for asset in assets],
                mode="markers+text",
                text=[asset.id for asset in assets],
                textposition="top center",
                hovertext=hover_text,
                hovertemplate="%{hovertext}<extra></extra>",
                marker={
                    "size": [
                        18
                        + 12
                        * (
                            1
                            if st.session_state.asset_observations[asset.id]["class"]
                            == "severe"
                            else 0.5
                            if st.session_state.asset_observations[asset.id]["class"]
                            == "partial"
                            else 0
                        )
                        for asset in assets
                    ],
                    "color": [
                        OBSERVATION_COLORS[
                            st.session_state.asset_observations[asset.id]["class"]
                        ]
                        for asset in assets
                    ],
                    "opacity": 0.96,
                },
                name="Görüntü tıkanıklık durumu",
            )
        )
    else:
        for asset_type, (label, color, marker_size) in ASSET_STYLES.items():
            type_assets = [asset for asset in assets if asset.type.value == asset_type]
            if not type_assets:
                continue
            hover_text = []
            for asset in type_assets:
                visual_fraction = (
                    f"%{asset.blockage_visual_fraction * 100:.0f}"
                    if asset.blockage_visual_fraction is not None
                    else "Veri yok"
                )
                water_level = (
                    f"{asset.water_level_m:.2f} m" if asset.water_level_m is not None else "Veri yok"
                )
                downstream = ", ".join(asset.downstream_ids) if asset.downstream_ids else "Çıkış"
                hover_text.append(
                    f"<b>{asset.name}</b><br>"
                    f"Kimlik: {asset.id}<br>"
                    f"Tür: {label}<br>"
                    f"Bölge: {asset.drainage_zone_id}<br>"
                    f"Risk puanı: {map_risks[asset.id]:.2f}<br>"
                    f"Görünür kapanma: {visual_fraction}<br>"
                    f"Kapasite katsayısı: {asset.hydraulic_capacity_factor:.2f}<br>"
                    f"Su seviyesi: {water_level}<br>"
                    f"Etki indeksi: {baseline.node_impact[asset.id]:.2f}<br>"
                    f"Aşağı akım: {downstream}"
                )
            map_figure.add_trace(
                go.Scattermap(
                    lon=[asset.lon for asset in type_assets],
                    lat=[asset.lat for asset in type_assets],
                    mode="markers+text",
                    text=[asset.id for asset in type_assets],
                    textposition="top center",
                    hovertext=hover_text,
                    hovertemplate="%{hovertext}<extra></extra>",
                    marker={
                        "size": marker_size,
                        "color": color,
                        "opacity": 0.95,
                    },
                    name=label,
                )
            )

    map_figure.update_layout(
        map={
            "style": "open-street-map",
            "center": {
                "lat": 41.0040,
                "lon": 39.7420,
            },
            "zoom": 13.4,
        },
        height=620,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.01,
            "xanchor": "left",
            "x": 0,
            "bgcolor": "rgba(255,255,255,0.9)",
        },
    )
    if map_view == "Tıkanıklık durumu":
        base_sizes = [
            30
            if st.session_state.asset_observations[asset.id]["class"] == "severe"
            else 24
            if st.session_state.asset_observations[asset.id]["class"] == "partial"
            else 18
            for asset in assets
        ]
        pulse_sizes = [size + 8 for size in base_sizes]
        pulse_script = f"""
        const graph = document.getElementById('{{plot_id}}');
        let pulseOn = false;
        window.setInterval(() => {{
            pulseOn = !pulseOn;
            Plotly.restyle(
                graph,
                {{
                    'marker.size': [pulseOn ? {json.dumps(pulse_sizes)} : {json.dumps(base_sizes)}],
                    'marker.opacity': pulseOn ? 0.58 : 0.98
                }},
                [1]
            );
        }}, 750);
        """
        st.html(
            map_figure.to_html(
                full_html=False,
                include_plotlyjs="cdn",
                config={"displayModeBar": True, "scrollZoom": True},
                post_script=pulse_script,
            ),
            unsafe_allow_javascript=True,
        )
        st.caption(
            "Yanıp sönen durum işaretleri: kırmızı ciddi tıkalı, sarı kısmi tıkalı, "
            "yeşil açık. Noktanın üzerine gelince bağlı görüntü kaydı ve risk bilgisi görünür."
        )
    else:
        st.plotly_chart(
            map_figure,
            width="stretch",
            config={"displayModeBar": True, "scrollZoom": True},
        )

    network_table = pd.DataFrame(
            [
                {
                    "ID": asset.id,
                    "Ad": asset.name,
                    "Tür": ASSET_STYLES[asset.type.value][0],
                    "Bölge": asset.drainage_zone_id,
                    "Tıkanıklık (%)": (
                        round(asset.blockage_visual_fraction * 100)
                        if asset.blockage_visual_fraction is not None
                        else None
                    ),
                    "Görüntü durumu": OBSERVATION_LABELS[
                        st.session_state.asset_observations[asset.id]["class"]
                    ],
                    "Görüntü kaydı": st.session_state.asset_observations[
                        asset.id
                    ]["sample_id"],
                    "Risk seviyesi": (
                        "Yüksek"
                        if map_risks[asset.id] / maximum_risk >= 0.6
                        else "Orta"
                        if map_risks[asset.id] / maximum_risk >= 0.3
                        else "Düşük"
                    ),
                    "Risk puanı": round(map_risks[asset.id], 2),
                    "Kapasite katsayısı": asset.hydraulic_capacity_factor,
                    "Su seviyesi (m)": asset.water_level_m,
                    "Etki indeksi": baseline.node_impact[asset.id],
                    "Aşağı akım": ", ".join(asset.downstream_ids) if asset.downstream_ids else "Çıkış",
                }
                for asset in assets
            ]
        ).sort_values("Risk puanı", ascending=False)
    st.dataframe(
        network_table,
        width="stretch",
        hide_index=True,
    )

with tabs[2]:
    st.subheader("Gözlem & Yapay Zekâ Analiz Merkezi")
    st.caption(
        "Her görüntü bir altyapı noktasına bağlıdır. Buradaki sonuç, "
        "Drenaj Ağı haritasındaki aynı noktanın durumunu belirler."
    )

    observations = st.session_state.asset_observations
    severe_count = sum(1 for item in observations.values() if item["class"] == "severe")
    partial_count = sum(1 for item in observations.values() if item["class"] == "partial")
    unblocked_count = sum(1 for item in observations.values() if item["class"] == "unblocked")

    stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
    stat_c1.metric("Görüntüye bağlı altyapı", len(assets))
    stat_c2.metric("Ciddi tıkalı", severe_count)
    stat_c3.metric("Kısmi tıkalı", partial_count)
    stat_c4.metric("Açık / normal", unblocked_count)

    if "observation_saved_message" in st.session_state:
        st.success(st.session_state.pop("observation_saved_message"))

    # 2. SEÇİM VE YÜKLEME PANELİ
    with st.container(border=True):
        st.markdown("##### İncelenecek altyapı noktasını seçin")
        c_sel, c_up = st.columns([1.3, 1])
        with c_sel:
            selected_asset_id = st.selectbox(
                "Altyapı noktası ve bağlı görüntü",
                [asset.id for asset in assets],
                format_func=lambda item_id: (
                    f"{item_id} · {asset_map[item_id].name} · "
                    f"{OBSERVATION_LABELS[observations[item_id]['class']]}"
                ),
            )
        with c_up:
            uploaded_image = st.file_uploader(
                "Veya Yeni Saha Fotoğrafı Yükle",
                type=["jpg", "jpeg", "png"],
                help="Saha ekibinden gelen yeni fotoğrafı yükleyip anında analiz ettirebilirsiniz.",
            )

    selected_asset = asset_map[selected_asset_id]
    selected_sample = asset_vision_links[selected_asset_id]
    saved_image_bytes = observations[selected_asset_id].get("image_bytes")
    if uploaded_image is not None:
        image_bytes = uploaded_image.getvalue()
        image_source = image_bytes
        image_caption = f"Yüklenen: {uploaded_image.name}"
    elif saved_image_bytes:
        image_source = saved_image_bytes
        image_caption = (
            f"{selected_asset.id} · {selected_asset.name} · "
            f"{observations[selected_asset_id]['sample_id']}"
        )
    else:
        image_source = project_root() / selected_sample["path"]
        image_caption = (
            f"{selected_asset.id} · {selected_asset.name} · "
            f"{selected_sample['id']}"
        )

    # AI Analizi çalıştır
    detection = mark_obstruction_regions(image_source)
    marked_percent = float(detection["marked_fraction"]) * 100
    
    # Modelin tek sınıf sonucunu belirleme
    clip_scores = detection.get("clip_scores")
    if clip_scores:
        model_class = max(clip_scores, key=clip_scores.get)
    elif marked_percent >= 30.0:
        model_class = "severe"
    elif marked_percent >= 10.0:
        model_class = "partial"
    else:
        model_class = "unblocked"

    is_severe_alert = model_class == "severe"
    is_partial_alert = model_class == "partial"

    # 3. OKUNABİLİR ANALİZ ÖZETİ
    if is_severe_alert:
        status_text = "Ciddi tıkalı"
    elif is_partial_alert:
        status_text = "Kısmi tıkalı"
    else:
        status_text = "Açık / normal"

    with st.container(border=True):
        st.markdown(f"#### {selected_asset.id} · {selected_asset.name}")
        st.caption("Altyapıya bağlı son görüntü kaydı ve model incelemesi")

        analysis_summary = pd.DataFrame(
            [
                {
                    "Görüntü kaydı": observations[selected_asset_id]["sample_id"]
                    if uploaded_image is None
                    else uploaded_image.name,
                    "Model sonucu": status_text,
                    "İşaretlenen alan": marked_percent,
                    "Bulunan bölge": int(detection["region_count"]),
                }
            ]
        )
        st.dataframe(
            analysis_summary,
            width="stretch",
            hide_index=True,
            column_config={
                "İşaretlenen alan": st.column_config.ProgressColumn(
                    "İşaretlenen alan (%)",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%",
                ),
                "Bulunan bölge": st.column_config.NumberColumn(
                    "Bulunan bölge", format="%d"
                ),
            },
        )

        st.caption(
            f"Kullanılan analiz: {detection.get('method', 'YOLOE-26n-seg + MobileCLIP2')}"
        )

    if is_severe_alert:
        st.error(
            "Model ciddi tıkanıklık belirledi: yağış öncesi saha kontrolüne öncelik verin."
        )
    elif is_partial_alert:
        st.warning(
            "Model kısmi tıkanıklık belirledi: yağış öncesi kontrol planına ekleyin."
        )
    else:
        st.success("Model su giriş kesitini açık olarak sınıflandırdı.")

    # 4. GÖRSEL KARŞILAŞTIRMA (ÖNCE/SONRA)
    vis_left, vis_right = st.columns(2)
    with vis_left:
        with st.container(border=True):
            st.markdown("📸 **Orijinal Saha Görüntüsü**")
            st.image(image_source, caption=image_caption, width="stretch")
    with vis_right:
        with st.container(border=True):
            st.markdown("🤖 **Yapay Zekâ Tıkanıklık Tespiti & Maske**")
            st.image(
                detection["annotated_image"],
                caption=f"AI Tespit: {detection['region_count']} bölge sınırlandı (%{marked_percent:.1f} alan)",
                width="stretch",
            )

    # 5. ALTYAPI İLE EŞLEŞEN GÖRSEL ARŞİVİ
    st.markdown("##### Altyapı noktaları ve bağlı görüntüleri")
    for row_start in range(0, len(assets), 4):
        gallery_cols = st.columns(4)
        for col, asset in zip(gallery_cols, assets[row_start : row_start + 4]):
            sample = asset_vision_links[asset.id]
            observation = observations[asset.id]
            with col:
                with st.container(border=True):
                    gallery_image = observation.get("image_bytes") or str(
                        project_root() / sample["path"]
                    )
                    st.image(gallery_image, width="stretch")
                    st.markdown(f"**{asset.id} · {asset.name}**")
                    st.caption(
                        f"{OBSERVATION_LABELS[observation['class']]} · "
                        f"Görüntü: {observation['sample_id']}"
                    )

    # 6. OPERATÖR DOĞRULAMA & ENTEGRASYON
    with st.expander("🛠️ Operatör Doğrulama ve Altyapı Kaydı", expanded=False):
        st.write(
            f"**Kayıt hedefi:** {selected_asset.id} · {selected_asset.name} "
            f"({ASSET_STYLES[selected_asset.type.value][0]})"
        )
        class_values = [item.value for item in ObservationClass]
        suggested_class = model_class
        suggested_fraction = (
            float(detection["marked_fraction"])
            if uploaded_image is not None
            else observations[selected_asset_id]["visual_fraction"]
            if observations[selected_asset_id]["visual_fraction"] is not None
            else float(detection["marked_fraction"])
        )
        label_col, fraction_col = st.columns(2)
        with label_col:
            label = st.selectbox(
                "Nihai Operatör Sınıfı",
                class_values,
                index=class_values.index(suggested_class),
                format_func=lambda value: OBSERVATION_LABELS[value],
            )
        with fraction_col:
            fraction_ranges = {
                "unblocked": (0.0, 0.39),
                "partial": (0.40, 0.69),
                "severe": (0.70, 1.0),
                "unknown": (0.0, 1.0),
            }
            fraction_min, fraction_max = fraction_ranges[label]
            fraction_default = max(
                fraction_min, min(fraction_max, suggested_fraction)
            )
            fraction = st.slider(
                "Görünür Kapanma Oranı",
                fraction_min,
                fraction_max,
                fraction_default,
                0.01,
            )
        if st.button("Gözlemi Onayla ve Ağa Kaydet", type="primary"):
            verification_source = (
                image_source
                if uploaded_image is None
                else None
            )
            result = assess_obstruction(
                str(verification_source) if verification_source else None,
                ObservationClass(label),
                fraction,
            )
            st.session_state.asset_observations[selected_asset_id] = {
                "class": result["class"].value,
                "visual_fraction": fraction,
                "sample_id": (
                    uploaded_image.name
                    if uploaded_image is not None
                    else observations[selected_asset_id]["sample_id"]
                ),
                "image_bytes": (
                    uploaded_image.getvalue() if uploaded_image is not None else saved_image_bytes
                ),
            }
            st.session_state.observation_saved_message = (
                f"{selected_asset.name} için gözlem kaydedildi: "
                f"{OBSERVATION_LABELS[result['class'].value]} (%{fraction * 100:.0f}). "
                "Drenaj Ağı haritası güncellendi."
            )
            st.rerun()
        st.caption("Not: Görsel tıkanıklık oranı doğrudan hidrolik kapasiteye eşitlenmez; ağ modelinde hidrolik faktör olarak ayrıca hesaplanır.")

    st.caption(
        "Görüntü kaynağı: Visual Hydraulics Lab Blockage Dataset · "
        "Iqbal ve ark. · CC BY 4.0 · DOI 10.5281/zenodo.7623641"
    )

with tabs[3]:
    st.subheader("Önce nerelere müdahale etmeliyiz?")
    st.write(
        "Bu bölüm yalnız tıkanıklık oranına bakmaz. Bir noktaya müdahale edildiğinde "
        "drenaj ağının tamamında oluşan değişimi de dikkate alır."
    )
    risks = asset_risk_scores(assets, baseline.node_impact)
    benefits = intervention_benefits(model, actions)

    highest_risk_asset = max(assets, key=lambda asset: risks[asset.id])
    highest_benefit_action = max(actions, key=lambda action: benefits[action.id])
    summary_a, summary_b, summary_c = st.columns(3)
    summary_a.metric("En yüksek yerel risk", highest_risk_asset.name)
    summary_b.metric("En etkili tek müdahale", asset_map[highest_benefit_action.asset_id].name)
    summary_c.metric("Müdahalesiz ağ etkisi", f"{baseline.total_impact_index:.2f}")

    ordered_actions = sorted(actions, key=lambda action: benefits[action.id], reverse=True)
    priority_rows = []
    for priority, action in enumerate(ordered_actions, start=1):
        asset = asset_map[action.asset_id]
        priority_rows.append(
            {
                "Öncelik": priority,
                "Altyapı noktası": asset.name,
                "Mevcut durum": condition_text(asset),
                "Önerilen işlem": action.name,
                "Neden önemli?": priority_reason(asset),
                "Ağ geneli fayda": round(benefits[action.id], 2),
            }
        )

    st.markdown("**Müdahale öncelikleri**")
    st.dataframe(
        pd.DataFrame(priority_rows),
        width="stretch",
        hide_index=True,
    )

    action_a, action_b = action_map["A1"], action_map["A3"]
    delta = synergy_delta(model, action_a, action_b)
    with st.expander("Bağlantılı iki müdahalenin birlikte etkisi"):
        st.write(
            f"**{action_a.name}** ve **{action_b.name}** birlikte uygulandığında, ağ bağlantıları "
            f"nedeniyle tek tek hesaplanan faydaların toplamına göre {delta:+.2f} puanlık ek fark oluşuyor. "
            "Bu nedenle görevler birbirinden bağımsız seçilmiyor."
        )

with tabs[4]:
    st.subheader("Yağış öncesi ekip görev planı")
    st.write(
        f"Ekiplerin yağış başlangıcına kadar kullanabileceği **{planning_deadline} dakika** bulunuyor. "
        "Aşağıdaki görevler ekip yetkinliği, gerekli araç ve ulaşım süresi birlikte değerlendirilerek seçildi."
    )

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Kullanılabilir süre", f"{planning_deadline} dk")
    p2.metric("Aktif ekip", len(teams))
    p3.metric("Planlanan görev", len(plan.assignments))
    p4.metric("Beklenen etki azalımı", f"{plan.simulated_benefit:.2f}")

    team_columns = st.columns(len(teams))
    for team_column, team in zip(team_columns, teams):
        team_assignments = sorted(
            [item for item in plan.assignments if item.team_id == team.id],
            key=lambda item: item.start_minute,
        )
        with team_column:
            with st.container(border=True):
                st.markdown(f"### {team.name}")
                st.caption(f"Başlangıç noktası: {asset_map[team.start_asset_id].name}")
                if not team_assignments:
                    st.write("Bu süre içinde ekibe uygun görev bulunamadı.")
                for task_number, assignment in enumerate(team_assignments, start=1):
                    action = action_map[assignment.action_id]
                    asset = asset_map[action.asset_id]
                    clock_start = current_time + timedelta(minutes=assignment.start_minute)
                    clock_end = current_time + timedelta(minutes=assignment.end_minute)
                    st.markdown(
                        f"**{task_number}. {action.name}**  \n"
                        f"{asset.name} · {clock_start:%H:%M}–{clock_end:%H:%M}  \n"
                        f"Ulaşım: {assignment.travel_minutes} dk · Çalışma: {action.duration_minutes} dk"
                    )

    selected_action_names = [action_map[action_id].name for action_id in plan.selected_action_ids]
    if selected_action_names:
        st.success("Planlanan görevler yağış başlangıcından önce tamamlanabiliyor.")

    with st.expander(f"Bu plana alınamayan görevler ({len(plan.rejected)})"):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Görev": action_map[action_id].name,
                        "Konum": asset_map[action_map[action_id].asset_id].name,
                        "Neden seçilmedi?": reason,
                    }
                    for action_id, reason in plan.rejected.items()
                ]
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[5]:
    st.subheader("Sahadaki görevleri adım adım takip edin")
    step_a, step_b, step_c = st.columns(3)
    step_a.info("**1. Görevi seçin**\n\nTakip etmek istediğiniz iş emrini açın.")
    step_b.info("**2. Tamamlanmayı bildirin**\n\nEkip çalışmayı bitirdiğinde saha bildirimini girin.")
    step_c.info("**3. Sonucu doğrulayın**\n\nYeni gözlemden sonra kalan görevler güncellensin.")

    if "orders" not in st.session_state:
        st.session_state.orders = create_work_orders(plan)
    order_ids = [order.id for order in st.session_state.orders]
    if not order_ids:
        st.info("Yağış başlangıcına kadar tamamlanabilecek bir iş emri bulunmuyor.")
    else:
        selected_order_id = st.selectbox(
            "Takip edilecek iş emri",
            order_ids,
            format_func=lambda order_id: (
                f"{order_id} · {action_map[order_id.removeprefix('WO-')].name}"
            ),
        )
        index = order_ids.index(selected_order_id)
        order = st.session_state.orders[index]
        action = action_map[order.action_id]
        asset = asset_map[action.asset_id]

        with st.container(border=True):
            detail_a, detail_b, detail_c = st.columns(3)
            detail_a.metric("Görev", action.name)
            detail_b.metric("Konum", asset.name)
            detail_c.metric("Durum", STATUS_LABELS.get(order.status.value, order.status.value))
            st.write(f"**Sorumlu ekip:** {team_map[order.team_id].name}")

            button_a, button_b = st.columns(2)
            if button_a.button(
                "Çalışma tamamlandı",
                disabled=order.status != WorkOrderStatus.ASSIGNED,
                width="stretch",
            ):
                st.session_state.orders[index] = mark_completed(order)
                st.rerun()
            if button_b.button(
                "Yeni gözlemle doğrula ve planı güncelle",
                disabled=order.status != WorkOrderStatus.COMPLETED_PENDING_VERIFICATION,
                type="primary",
                width="stretch",
            ):
                st.session_state.orders[index] = verify_order(
                    order,
                    {"class": "unblocked", "source": "operator_input", "note": "Saha doğrulaması"},
                )
                st.session_state.replanned = replan_after_verification(
                    assets,
                    event,
                    actions,
                    teams,
                    st.session_state.orders,
                    deadline_minutes=planning_deadline,
                )
                st.rerun()

        with st.expander("İş emri geçmişi"):
            event_log_df = pd.DataFrame(order.event_log).rename(
                columns={"time": "Zaman", "status": "Durum", "reason": "Açıklama", "source": "Kaynak"}
            )
            event_log_df["Durum"] = event_log_df["Durum"].map(
                lambda value: STATUS_LABELS.get(value, value)
            )
            st.dataframe(event_log_df[["Zaman", "Durum", "Açıklama"]], width="stretch", hide_index=True)

        if "replanned" in st.session_state:
            new_plan = st.session_state.replanned
            remaining_names = [action_map[action_id].name for action_id in new_plan.selected_action_ids]
            st.success("Saha doğrulaması kaydedildi ve kalan görev planı güncellendi.")
            st.write("**Sıradaki görevler:**", ", ".join(remaining_names) if remaining_names else "Görev kalmadı")

with tabs[6]:
    st.subheader("Bu plan bize ne kazandırıyor?")
    comparison = compare_policies(
        assets,
        actions,
        teams,
        model,
        deadline_minutes=planning_deadline,
    )
    comparison_df = pd.DataFrame(comparison)
    baseline_impact = float(comparison_df.iloc[0]["impact_index"])
    if baseline_impact > 0:
        comparison_df["improvement_percent"] = comparison_df["impact_index"].map(
            lambda impact: 100 * (baseline_impact - impact) / baseline_impact
        )
    else:
        comparison_df["improvement_percent"] = 0.0
    recommended = comparison_df.iloc[-1]
    improvement_percent = float(recommended["improvement_percent"])
    remaining_pressure = max(0.0, 100.0 - improvement_percent)
    used_team_count = len({assignment.team_id for assignment in plan.assignments})
    latest_finish_minute = max(
        (assignment.end_minute for assignment in plan.assignments),
        default=0,
    )
    latest_finish_clock = current_time + timedelta(minutes=latest_finish_minute)
    selected_assets = [asset_map[action_map[action_id].asset_id] for action_id in plan.selected_action_ids]
    critical_location_count = sum(bool(asset.criticality_tags) for asset in selected_assets)
    addressed_blockage_count = sum(
        asset.blockage_visual_fraction is not None and asset.blockage_visual_fraction >= 0.6
        for asset in selected_assets
    )

    result_a, result_b, result_c, result_d = st.columns(4)
    result_a.metric("Tamamlanacak görev", len(plan.assignments))
    result_b.metric("Görev alacak ekip", used_team_count)
    result_c.metric("Öncelik verilen kritik nokta", critical_location_count)
    result_d.metric(
        "Son görevin bitişi",
        latest_finish_clock.strftime("%H:%M") if plan.assignments else "Görev yok",
    )

    st.success(
        f"Plan uygulandığında ağ üzerindeki beklenen baskı yaklaşık %{improvement_percent:.1f} azalıyor. "
        f"Yağış başlamadan önce {len(plan.assignments)} görev tamamlanabiliyor."
    )
    st.progress(
        min(100, max(0, int(round(improvement_percent)))),
        text=f"Planla azaltılan ağ baskısı: %{improvement_percent:.1f}",
    )

    benefit_left, benefit_right = st.columns(2)
    with benefit_left:
        st.markdown("**Planın doğrudan faydaları**")
        st.markdown(
            f"""
            - {addressed_blockage_count} belirgin tıkanıklık noktasına müdahale ediliyor.
            - {critical_location_count} kritik ulaşım veya altyapı bağlantısına öncelik veriliyor.
            - {used_team_count} ekip aynı zaman aralığında paralel çalışıyor.
            - Görevler yağıştan önce en geç {latest_finish_clock:%H:%M} saatinde tamamlanıyor.
            """
        )
    with benefit_right:
        st.markdown("**Plan sonrasında beklenen durum**")
        st.markdown(
            f"""
            - Başlangıçtaki ağ baskısının yaklaşık **%{remaining_pressure:.1f}** kadarı kalıyor.
            - Ekip veya araç yetkinliği dışında görev ataması yapılmıyor.
            - Aynı görev iki farklı ekibe verilmiyor.
            - Süre sınırını aşan işler plana alınmıyor.
            """
        )

    friendly_policy_names = {
        "B0 — Müdahale yok": "Müdahale yapılmazsa",
        "B1 — Görünür tıkanıklık": "Sadece tıkanıklığa göre",
        "B2 — Yerel risk": "Sadece nokta önceliğine göre",
        "P — SİPER AI portföyü": "SİPER planı",
    }
    comparison_df["friendly_policy"] = comparison_df["policy"].map(friendly_policy_names)

    result_figure = go.Figure(
        go.Bar(
            x=comparison_df["improvement_percent"],
            y=comparison_df["friendly_policy"],
            orientation="h",
            marker_color=["#aeb6ba", "#d8a24a", "#5e91b8", "#2f7d5c"],
            text=[f"%{value:.1f}" for value in comparison_df["improvement_percent"]],
            textposition="outside",
            hovertemplate="%{y}<br>Sağlanan azalma: %{x:.1f}%<extra></extra>",
        )
    )
    result_figure.update_layout(
        title="Aynı sürede hangi yöntem daha fazla fayda sağlıyor?",
        xaxis_title="Ağ baskısında sağlanan azalma (%)",
        yaxis_title="",
        height=390,
        margin={"l": 20, "r": 50, "t": 60, "b": 20},
    )
    st.plotly_chart(result_figure, width="stretch", config={"displayModeBar": False})

    validation_path = project_root() / "data" / "swmm" / "validation_results.json"
    if validation_path.exists():
        swmm_results = json.loads(validation_path.read_text(encoding="utf-8"))
        swmm_baseline = float(swmm_results["baseline"]["overflow_volume_m3"])
        swmm_culvert = float(swmm_results["culvert_restored"]["overflow_volume_m3"])
        swmm_portfolio = float(
            swmm_results["three_upstream_restorations"]["overflow_volume_m3"]
        )
        with st.expander("SWMM hidrolik doğrulamasını göster"):
            st.write(
                "Aynı yağış altında küçük fiziksel drenaj modelinde hesaplanan "
                "yüzey taşma hacimleri:"
            )
            swmm_a, swmm_b, swmm_c = st.columns(3)
            swmm_a.metric("Müdahale yok", f"{swmm_baseline:.2f} m³")
            swmm_b.metric(
                "Menfez kapasitesi geri kazanılırsa",
                f"{swmm_culvert:.2f} m³",
                delta=f"-{100 * (swmm_baseline - swmm_culvert) / swmm_baseline:.1f}%",
                delta_color="normal",
            )
            swmm_c.metric(
                "Üç üst-hat múhalesi",
                f"{swmm_portfolio:.2f} m³",
                delta=f"-{100 * (swmm_baseline - swmm_portfolio) / swmm_baseline:.1f}%",
                delta_color="normal",
            )
            st.caption(
                "EPA SWMM 5.2.4 · Sentetik geometri ve yağış · Saha kalibrasyonu yapılmadı"
            )

    with st.expander("Yöntemlerin görev karşılaştırmasını göster"):
        result_rows = []
        for _, row in comparison_df.iterrows():
            selected_names = [action_map[action_id].name for action_id in row["action_ids"]]
            result_rows.append(
                {
                    "Yöntem": row["friendly_policy"],
                    "Seçilen görevler": ", ".join(selected_names) if selected_names else "Görev yok",
                    "Sağlanan fayda": f"%{row['improvement_percent']:.1f}",
                    "Kalan ağ baskısı": f"%{100 - row['improvement_percent']:.1f}",
                    "Tamamlanabilir görev": int(row["completed_actions"]),
                }
            )
        st.dataframe(pd.DataFrame(result_rows), width="stretch", hide_index=True)
