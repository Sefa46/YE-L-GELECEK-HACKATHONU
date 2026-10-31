from __future__ import annotations

import json
from datetime import datetime, timedelta
from html import escape
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
from siper.schemas import ObservationClass, WorkOrder, WorkOrderStatus
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

# Sayfa yenilendiğinde (F5 / Cmd+R) veya sıfırlama parametresi geldiğinde görev durumlarını sıfırla
if st.query_params.get("reload_reset") == "1":
    st.session_state.pop("orders", None)
    st.session_state.pop("replanned", None)
    st.session_state.pop("asset_observations", None)
    del st.query_params["reload_reset"]


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

if st.sidebar.button("🔄 Senaryo ve Görevleri Baştan Başlat"):
    st.session_state.pop("orders", None)
    st.session_state.pop("replanned", None)
    st.session_state.pop("asset_observations", None)
    st.rerun()

if "tracked_weather_mode" not in st.session_state:
    st.session_state.tracked_weather_mode = weather_mode
elif st.session_state.tracked_weather_mode != weather_mode:
    st.session_state.tracked_weather_mode = weather_mode
    st.session_state.pop("orders", None)
    st.session_state.pop("replanned", None)
    st.session_state.pop("asset_observations", None)


@st.cache_data(show_spinner=False)
def get_cached_fixtures():
    return load_assets(), load_actions(), load_teams(), load_vision_samples()


@st.cache_data(show_spinner=False)
def cached_mark_obstruction_regions(cache_key: str, image_bytes: bytes | None = None):
    """YOLO ve MobileCLIP derin öğrenme tespitini önbelleğe alarak anında (<1ms) yanıt üretir."""
    if image_bytes is not None:
        return mark_obstruction_regions(image_bytes)
    return mark_obstruction_regions(cache_key)


base_assets, actions, teams, vision_samples = get_cached_fixtures()
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
event = live_event if weather_mode == "Canlı Open-Meteo" and live_event else offline_event
model = ProxyHydraulicModel(assets, event)
baseline = model.run()
local_timezone = ZoneInfo("Europe/Istanbul")
rain_start = event.starts_at.astimezone(local_timezone)

# Planlama süresi ve zaman hesabı:
# Çevrimdışı senaryoda test gereği yerel saat yağış başlangıcından tam 24 saat öncesine sabitlenir (24 saatlik afet hazırlık fazı).
# Canlı Open-Meteo'da gerçek anlık saat ve yaklaşan yağış saatine kalan dakika veya operasyon penceresi (min 60, maks 180 dk) esas alınır.
if weather_mode == "Canlı Open-Meteo":
    current_time = datetime.now(local_timezone)
    remaining_minutes = int((rain_start - current_time).total_seconds() // 60)
    planning_deadline = max(30, min(180, remaining_minutes)) if remaining_minutes > 0 else 60
else:
    current_time = rain_start - timedelta(hours=24)
    planning_deadline = 1440  # 24 saat (1440 dakika) hazırlık ve müdahale süresi

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

OBSERVATION_SELECT_LABELS = {
    "severe": "🔴 Ciddi tıkalı",
    "partial": "🟠 Kısmi tıkalı",
    "unblocked": "🟢 Açık / normal",
    "unknown": "⚪ Belirsiz",
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


def render_status_cards(items: list[tuple[str, str]]) -> None:
    cards = "".join(
        (
            '<div class="status-card">'
            f'<div class="status-card__label">{escape(label)}</div>'
            f'<div class="status-card__value">{escape(value)}</div>'
            "</div>"
        )
        for label, value in items
    )
    st.html(f'<div class="status-grid">{cards}</div>')


def render_observation_status_cards(
    asset_count: int,
    severe_count: int,
    partial_count: int,
    unblocked_count: int,
) -> None:
    cards = [
        ("Görüntüye bağlı altyapı", str(asset_count), "neutral", ""),
        ("Ciddi tıkalı", str(severe_count), "severe", "⚠"),
        ("Kısmi tıkalı", str(partial_count), "partial", ""),
        ("Açık / normal", str(unblocked_count), "unblocked", ""),
    ]
    card_html = "".join(
        (
            f'<div class="status-card observation-card observation-card--{tone}">'
            f'<div class="status-card__label">{escape(label)}</div>'
            f'<div class="status-card__value observation-card__value">'
            f'{escape(value)}'
            f'<span class="observation-card__icon" aria-label="Uyarı">{icon}</span>'
            "</div></div>"
        )
        for label, value, tone, icon in cards
    )
    st.html(f'<div class="status-grid">{card_html}</div>')


def render_pulsing_drainage_map(
    figure: go.Figure,
    base_sizes: list[int] | None = None,
    legend_items: list[tuple[str, str]] | None = None,
    alt_text: str = "Trabzon drenaj ağı haritası",
) -> None:
    line_trace = figure.data[0]
    line_segments: list[list[list[float]]] = []
    current_segment: list[list[float]] = []
    for lon, lat in zip(line_trace.lon, line_trace.lat, strict=True):
        if lon is None or lat is None:
            if len(current_segment) > 1:
                line_segments.append(current_segment)
            current_segment = []
            continue
        current_segment.append([float(lat), float(lon)])
    if len(current_segment) > 1:
        line_segments.append(current_segment)

    def repeated_values(value, count: int) -> list:
        if isinstance(value, str) or not hasattr(value, "__iter__"):
            return [value] * count
        return list(value)

    pulse_markers = []
    size_offset = 0
    for marker_trace in figure.data[1:]:
        marker_count = len(marker_trace.lon)
        colors = repeated_values(marker_trace.marker.color, marker_count)
        if base_sizes is None:
            sizes = repeated_values(marker_trace.marker.size, marker_count)
        else:
            sizes = base_sizes[size_offset : size_offset + marker_count]
            size_offset += marker_count
        pulse_markers.extend(
            {
                "lon": float(lon),
                "lat": float(lat),
                "color": str(color),
                "size": int(size),
                "id": str(asset_id),
                "category": str(marker_trace.name),
                "details": str(details),
            }
            for lon, lat, color, size, asset_id, details in zip(
                marker_trace.lon,
                marker_trace.lat,
                colors,
                sizes,
                marker_trace.text,
                marker_trace.hovertext,
                strict=True,
            )
        )

    if legend_items is None:
        legend_items = [
            (str(trace.name), str(repeated_values(trace.marker.color, 1)[0]))
            for trace in figure.data[1:]
        ]
    legend_payload = [
        {"label": label, "color": color} for label, color in legend_items
    ]

    def json_for_script(value) -> str:
        return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")

    map_html = """
    <!doctype html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
        <style>
            html, body, #drainage-map {
                width: 100%;
                height: 100%;
                margin: 0;
                overflow: hidden;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            .siper-marker-shell {
                overflow: visible !important;
                background: transparent;
                border: 0;
            }
            .siper-marker {
                position: relative;
                width: var(--marker-size);
                height: var(--marker-size);
                border: 2px solid rgba(255, 255, 255, 0.98);
                border-radius: 999px;
                background: var(--marker-color);
                box-shadow: 0 2px 7px rgba(15, 23, 42, 0.55);
            }
            .siper-marker::before {
                position: absolute;
                inset: -3px;
                content: "";
                border: 3px solid var(--marker-color);
                border-radius: inherit;
                animation: siper-pulse 1.6s ease-out infinite;
                animation-delay: var(--pulse-delay);
            }
            .siper-marker__id {
                position: absolute;
                left: 50%;
                bottom: calc(100% + 5px);
                transform: translateX(-50%);
                padding: 1px 4px;
                border-radius: 4px;
                color: #172033;
                background: rgba(255, 255, 255, 0.9);
                font-size: 11px;
                font-weight: 750;
                line-height: 1.2;
                white-space: nowrap;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.2);
            }
            .siper-legend {
                padding: 9px 11px;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.94);
                box-shadow: 0 1px 6px rgba(15, 23, 42, 0.28);
                color: #172033;
                font-size: 12px;
                line-height: 1.65;
            }
            .siper-legend--dense {
                display: grid;
                grid-template-columns: repeat(2, max-content);
                column-gap: 13px;
            }
            .siper-legend__dot {
                display: inline-block;
                width: 10px;
                height: 10px;
                margin-right: 6px;
                border-radius: 50%;
            }
            .siper-info-card {
                width: 280px;
                max-height: 220px;
                overflow: auto;
                padding: 11px 13px;
                border-radius: 9px;
                background: rgba(255, 255, 255, 0.96);
                box-shadow: 0 2px 10px rgba(15, 23, 42, 0.32);
                color: #172033;
                font-size: 12px;
                line-height: 1.48;
            }
            .siper-info-card__hint {
                color: #526174;
                font-weight: 650;
            }
            .leaflet-popup-content {
                width: 280px !important;
                margin: 14px 17px;
                color: #172033;
                font-size: 12px;
                line-height: 1.48;
            }
            .leaflet-tooltip.siper-marker-tooltip {
                padding: 5px 8px;
                border: 0;
                border-radius: 6px;
                box-shadow: 0 1px 5px rgba(15, 23, 42, 0.25);
                font-weight: 700;
                white-space: nowrap;
            }
            @keyframes siper-pulse {
                0% { transform: scale(0.72); opacity: 0.95; }
                75%, 100% { transform: scale(2.1); opacity: 0; }
            }
        </style>
    </head>
    <body>
        <div id="drainage-map"></div>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <script>
            const lineSegments = __LINE_SEGMENTS__;
            const markers = __PULSE_MARKERS__;
            const legendItems = __LEGEND_ITEMS__;
            const map = L.map('drainage-map', {
                center: [41.0040, 39.7420],
                zoom: 13,
                zoomControl: true,
                preferCanvas: true
            });

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap katkıda bulunanlar'
            }).addTo(map);

            lineSegments.forEach((segment) => {
                L.polyline(segment, {
                    color: '#334e68',
                    weight: 4,
                    opacity: 0.86
                }).addTo(map);
            });

            const infoCard = L.control({ position: 'bottomleft' });
            let infoBox;
            infoCard.onAdd = () => {
                infoBox = L.DomUtil.create('div', 'siper-info-card');
                infoBox.innerHTML = '<div class="siper-info-card__hint">Detaylar için bir altyapı noktasının üzerine gelin veya noktaya tıklayın.</div>';
                L.DomEvent.disableClickPropagation(infoBox);
                return infoBox;
            };
            infoCard.addTo(map);

            markers.forEach((marker, index) => {
                const markerHtml = `
                    <div class="siper-marker" style="--marker-color:${marker.color}; --marker-size:${marker.size}px; --pulse-delay:-${(index % 5) * 0.18}s">
                        <span class="siper-marker__id">${marker.id}</span>
                    </div>`;
                const icon = L.divIcon({
                    className: 'siper-marker-shell',
                    html: markerHtml,
                    iconSize: [marker.size, marker.size],
                    iconAnchor: [marker.size / 2, marker.size / 2]
                });
                const mapMarker = L.marker([marker.lat, marker.lon], { icon }).addTo(map);
                mapMarker.bindTooltip(`<b>${marker.id}</b> · ${marker.category}`, {
                    direction: 'auto',
                    className: 'siper-marker-tooltip',
                    opacity: 0.98
                });
                mapMarker.bindPopup(marker.details, {
                    maxWidth: 330,
                    minWidth: 280,
                    autoPan: true,
                    autoPanPadding: [40, 40]
                });
                mapMarker.on('mouseover', () => {
                    infoBox.innerHTML = marker.details;
                });
            });

            if (markers.length) {
                const bounds = L.latLngBounds(markers.map((marker) => [marker.lat, marker.lon]));
                map.fitBounds(bounds, { padding: [42, 42], maxZoom: 14 });
            }

            const legend = L.control({ position: 'topright' });
            legend.onAdd = () => {
                const box = L.DomUtil.create('div', 'siper-legend');
                if (legendItems.length > 5) box.classList.add('siper-legend--dense');
                box.innerHTML = legendItems.map((item) =>
                    `<div><span class="siper-legend__dot" style="background:${item.color}"></span>${item.label}</div>`
                ).join('');
                return box;
            };
            legend.addTo(map);

            new ResizeObserver(() => map.invalidateSize(false)).observe(document.body);
            window.setTimeout(() => map.invalidateSize(false), 200);
        </script>
    </body>
    </html>
    """.replace(
        "__LINE_SEGMENTS__", json_for_script(line_segments)
    ).replace(
        "__PULSE_MARKERS__", json_for_script(pulse_markers)
    ).replace(
        "__LEGEND_ITEMS__", json_for_script(legend_payload)
    )
    st.iframe(
        map_html,
        width="stretch",
        height=640,
        alt=alt_text,
    )


st.html(
    """
    <style>
        .siper-title-line {
            transform: translateY(-12px);
            margin: 0 0 1rem 0;
            font-size: 2.75rem;
            font-weight: 700;
            line-height: 1.2;
            letter-spacing: -0.005em;
            white-space: nowrap;
        }

        .siper-title-line__description {
            margin-left: 0.55rem;
            font-size: 1.375rem;
            font-weight: 400;
            font-style: italic;
            letter-spacing: normal;
            opacity: 0.6;
            vertical-align: baseline;
        }

        .stTabs [data-baseweb="tab-list"] {
            width: 100%;
            gap: 0;
            justify-content: space-between;
        }

        .stTabs [data-baseweb="tab"] {
            min-height: 4rem;
            padding-left: 1.3rem;
            padding-right: 1.3rem;
        }

        .stTabs [data-baseweb="tab"] p {
            font-size: 1.25rem;
            font-weight: 650;
            white-space: nowrap;
        }

        .status-heading {
            margin: 0.65rem 0 0.2rem 0;
            font-size: 1.5rem;
            font-weight: 700;
            line-height: 1.25;
        }

        .status-location {
            margin-bottom: 0.8rem;
            font-size: 1rem;
            opacity: 0.78;
        }

        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
            gap: 0.75rem;
            margin: 0.65rem 0 1rem 0;
        }

        .status-card {
            min-height: 78px;
            padding: 0.8rem 0.95rem;
            border: 1px solid rgba(128, 128, 128, 0.24);
            border-radius: 0.7rem;
            background: rgba(128, 128, 128, 0.055);
        }

        .status-card__label {
            margin-bottom: 0.32rem;
            font-size: 1.05rem;
            font-weight: 650;
            line-height: 1.2;
            opacity: 0.78;
        }

        .status-card__value {
            font-size: 1.55rem;
            font-weight: 650;
            line-height: 1.2;
            overflow-wrap: anywhere;
        }

        .observation-card {
            border-left-width: 4px;
        }

        .observation-card--neutral {
            border-left-color: #64748b;
        }

        .observation-card--severe {
            border-left-color: #dc2626;
        }

        .observation-card--severe .observation-card__value {
            color: #dc2626;
        }

        .observation-card--partial {
            border-left-color: #d97706;
        }

        .observation-card--partial .observation-card__value {
            color: #d97706;
        }

        .observation-card--unblocked {
            border-left-color: #16a34a;
        }

        .observation-card--unblocked .observation-card__value {
            color: #16a34a;
        }

        .observation-card__icon {
            margin-left: 0.38rem;
            font-size: 1.25rem;
            vertical-align: 0.08rem;
        }

        @keyframes siper-pulse {
            0% {
                box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.75);
                border-color: #dc2626;
                background-color: rgba(220, 38, 38, 0.12);
            }
            50% {
                box-shadow: 0 0 25px 6px rgba(239, 68, 68, 0.55);
                border-color: #ef4444;
                background-color: rgba(220, 38, 38, 0.28);
            }
            100% {
                box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.75);
                border-color: #dc2626;
                background-color: rgba(220, 38, 38, 0.12);
            }
        }

        @keyframes siper-blink-text {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.88; transform: scale(1.02); }
        }

        .siper-blinking-alert {
            animation: siper-pulse 1.8s infinite ease-in-out;
            border: 2.5px solid #dc2626;
            border-radius: 0.85rem;
            padding: 1.1rem 1.4rem;
            margin: 0.6rem 0 1.3rem 0;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1.2rem;
            text-align: center;
            background-color: rgba(220, 38, 38, 0.15);
        }

        .siper-blinking-alert__title {
            color: #ef4444;
            font-size: 1.35rem;
            font-weight: 900;
            letter-spacing: 0.05em;
            line-height: 1.3;
            animation: siper-blink-text 1.8s infinite ease-in-out;
            text-transform: uppercase;
        }

        .siper-blinking-alert__desc {
            color: #fca5a5;
            font-size: 0.95rem;
            font-weight: 600;
            margin-top: 0.4rem;
            letter-spacing: 0.02em;
        }

        .siper-blinking-alert__icon {
            font-size: 2.3rem;
            user-select: none;
        }
    </style>
    <script>
    (function() {
        try {
            const nav = performance.getEntriesByType('navigation');
            if (nav.length > 0 && nav[0].type === 'reload') {
                if (!sessionStorage.getItem('siper_reloaded_once')) {
                    sessionStorage.setItem('siper_reloaded_once', '1');
                    const url = new URL(window.location.href);
                    url.searchParams.set('reload_reset', '1');
                    window.location.replace(url.href);
                }
            } else {
                sessionStorage.removeItem('siper_reloaded_once');
            }
        } catch(e) {}
    })();
    </script>
    <h1 class="siper-title-line">
        SİPER AI
        <span class="siper-title-line__description">Yapay Zekâ Destekli, Öngörülü Kentsel Yağmur Suyu ve Taşkın Müdahale Yönetim Sistemi</span>
    </h1>
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
    if weather_mode == "Çevrimdışı senaryo":
        st.html(
            """
            <div class="siper-blinking-alert">
                <div class="siper-blinking-alert__icon">⚠️</div>
                <div>
                    <div class="siper-blinking-alert__title">
                        ⚠️ DİKKAT: 1 GÜN SONRA ŞİDDETLİ SAĞANAK VE SEL RİSKİ BEKLENİYOR ⚠️
                    </div>
                    <div class="siper-blinking-alert__desc">
                        METEOROLOJİK ERKEN UYARI: TRABZON VE KIYI ŞERİDİNDE 24 SAAT SONRA ŞİDDETLİ AFET BOYUTUNDA YAĞIŞ (152 mm) ÖNGÖRÜLMEKTEDİR.<br>
                        TÜM KRİTİK DRENAJ NOKTALARI, MENFEZLER VE POMPA İSTASYONLARI İÇİN 24 SAAT ÖNCESİ TAŞKIN ÖNLEME PROTOKOLÜ VE SAHA EKİPLERİ TEYAKKUZDA!
                    </div>
                </div>
                <div class="siper-blinking-alert__icon">⚠️</div>
            </div>
            """
        )
    rain_end = rain_start + timedelta(hours=len(event.hourly_rain_mm))

    st.html(
        """
        <h2 class="status-heading">Trabzon yağış ve hazırlık durumu</h2>
        <div class="status-location"><strong>Konum:</strong> Trabzon · Ortahisar ve sahil drenaj hattı</div>
        """
    )

    if live_forecast and not live_event:
        st.caption(
            "Canlı Open-Meteo tahmininde önümüzdeki 48 saat için yağış olayı "
            "oluşmadı; operasyon modeli çevrimdışı senaryoyu kullanıyor."
        )
    elif live_forecast_error:
        st.caption(
            "Open-Meteo'ya erişilemedi; operasyon modeli çevrimdışı senaryoyu kullanıyor."
        )

    day_diff = (rain_start.date() - current_time.date()).days
    rain_start_text = (
        f"{rain_start.strftime('%H:%M')} (Yarın)"
        if day_diff > 0
        else rain_start.strftime("%H:%M")
    )
    local_time_text = current_time.strftime("%H:%M")
    render_status_cards(
        [
            ("Yerel saat", local_time_text),
            ("Yağış başlangıcı", rain_start_text),
            ("Kalan süre", remaining_time_text(rain_start, current_time)),
            ("Yağışın bitişi", rain_end.strftime("%H:%M")),
            ("Toplam yağış", f"{sum(event.hourly_rain_mm):.1f} mm"),
        ]
    )

    rain_message = (
        f"Yağışın başlamasına tam 24 saat (1 gün) bulunmaktadır; 24 saat öncesi hazırlık ve saha müdahale fazı yürütülüyor."
        if weather_mode != "Canlı Open-Meteo"
        else (
            f"Yağış {rain_start.strftime('%H:%M')} itibarıyla başladı."
            if current_time >= rain_start
            else f"Yağışın {rain_start.strftime('%H:%M')} civarında başlaması bekleniyor."
        )
    )
    st.info(
        f"{rain_message} "
        f"Hazırlanan planda {len(teams)} ekip için {len(plan.assignments)} görev bulunuyor; "
        f"ağda {len(assets)} altyapı noktası takip ediliyor."
    )

    if live_forecast:
        current_forecast = live_forecast.hours[0]
        upcoming_rain = next_rain_hour(live_forecast)
        render_status_cards(
            [
                (
                    "Sıcaklık",
                    f"{current_forecast.temperature_c:.1f} °C"
                    if current_forecast.temperature_c is not None
                    else "—",
                ),
                (
                    "Yağış olasılığı",
                    f"%{current_forecast.precipitation_probability_pct:.0f}"
                    if current_forecast.precipitation_probability_pct is not None
                    else "—",
                ),
                (
                    "Rüzgâr",
                    f"{current_forecast.wind_speed_kmh:.1f} km/sa"
                    if current_forecast.wind_speed_kmh is not None
                    else "—",
                ),
                (
                    "Sıradaki yağış",
                    upcoming_rain.time.strftime("%d.%m %H:%M")
                    if upcoming_rain
                    else "Beklenmiyor",
                ),
            ]
        )

    from plotly.subplots import make_subplots

    weather_rows = []
    cumulative_mm = 0.0
    intensity_color_map = {
        "Çok kuvvetli": "#dc2626",
        "Kuvvetli": "#ea580c",
        "Orta": "#0284c7",
        "Hafif": "#38bdf8",
    }
    for hour_index, rain_mm in enumerate(event.hourly_rain_mm):
        hour_start = rain_start + timedelta(hours=hour_index)
        hour_end = hour_start + timedelta(hours=1)
        cumulative_mm += rain_mm
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
                "Kümülatif (mm)": round(cumulative_mm, 1),
                "Şiddet": intensity,
                "Renk": intensity_color_map[intensity],
            }
        )
    weather_df = pd.DataFrame(weather_rows)

    weather_figure = make_subplots(specs=[[{"secondary_y": True}]])
    weather_figure.add_trace(
        go.Bar(
            name="Saatlik Yağış (mm)",
            x=weather_df["Saat aralığı"],
            y=weather_df["Yağış (mm)"],
            marker_color=weather_df["Renk"],
            text=[f"{value:.0f} mm" for value in weather_df["Yağış (mm)"]],
            textposition="outside",
            hovertemplate="%{x}<br>Saatlik Yağış: %{y:.1f} mm<br>Şiddet Seviyesi: "
            + weather_df["Şiddet"]
            + "<extra></extra>",
        ),
        secondary_y=False,
    )
    weather_figure.add_trace(
        go.Scatter(
            name="Kümülatif Toplam (mm)",
            x=weather_df["Saat aralığı"],
            y=weather_df["Kümülatif (mm)"],
            mode="lines+markers+text",
            line=dict(color="#f59e0b", width=3, dash="dash"),
            marker=dict(size=8, color="#d97706"),
            text=[f"{value:.0f} mm" for value in weather_df["Kümülatif (mm)"]],
            textposition="top left",
            hovertemplate="%{x}<br>Kümülatif Yağış: %{y:.1f} mm<extra></extra>",
        ),
        secondary_y=True,
    )
    chart_heading = (
        f"🌧️ Ertesi Gün ({rain_start:%d.%m.%Y}) Saatlik Yağış ve Kümülatif Su Yükü (Zirve: 10:00–11:00 / 48 mm)"
        if weather_mode != "Canlı Open-Meteo"
        else "🌧️ Saatlik Yağış ve Kümülatif Su Dağılımı"
    )
    weather_figure.update_layout(
        title=chart_heading,
        height=390,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    weather_figure.update_yaxes(title_text="Saatlik Yağış (mm)", secondary_y=False)
    weather_figure.update_yaxes(
        title_text="Kümülatif Toplam (mm)", secondary_y=True, showgrid=False
    )

    st.plotly_chart(weather_figure, width="stretch", config={"displayModeBar": False})
    st.dataframe(
        weather_df[["Saat aralığı", "Yağış (mm)", "Kümülatif (mm)", "Şiddet"]],
        width="stretch",
        hide_index=True,
        column_config={
            "Kümülatif (mm)": st.column_config.ProgressColumn(
                "Kümülatif (mm)",
                min_value=0,
                max_value=float(sum(event.hourly_rain_mm)),
                format="%.1f mm",
            ),
        },
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
    st.html('<h2 class="status-heading">Bağlantılı drenaj ağı</h2>')
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

    render_status_cards(
        [
            ("Düğüm", str(diagnostics["node_count"])),
            ("Bağlantı", str(diagnostics["edge_count"])),
            ("Ciddi tıkalı", str(len(severe_ids))),
            ("Kısmi tıkalı", str(len(partial_ids))),
        ]
    )

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
        uirevision="drainage-network-map",
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
        render_pulsing_drainage_map(
            map_figure,
            base_sizes,
            legend_items=[
                ("Ciddi tıkalı", OBSERVATION_COLORS["severe"]),
                ("Kısmi tıkalı", OBSERVATION_COLORS["partial"]),
                ("Açık / normal", OBSERVATION_COLORS["unblocked"]),
            ],
            alt_text="Tıkanıklık durumlarını gösteren Trabzon drenaj ağı haritası",
        )
        st.caption(
            "Yanıp sönen durum işaretleri: kırmızı ciddi tıkalı, sarı kısmi tıkalı, "
            "yeşil açık. Noktanın üzerine gelince bağlı görüntü kaydı ve risk bilgisi görünür."
        )
    else:
        render_pulsing_drainage_map(
            map_figure,
            legend_items=[
                (label, color) for label, color, _ in ASSET_STYLES.values()
            ],
            alt_text="Altyapı türlerini gösteren Trabzon drenaj ağı haritası",
        )
        st.caption(
            "Yanıp sönen renkler altyapı türlerini gösterir. Noktanın üzerine "
            "gelince bilgi kartı güncellenir; noktaya tıklayınca ayrıntı penceresi açılır."
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
    st.html('<h2 class="status-heading">Gözlem & Yapay Zekâ Analiz Merkezi</h2>')
    st.caption(
        "Her görüntü bir altyapı noktasına bağlıdır. Buradaki sonuç, "
        "Drenaj Ağı haritasındaki aynı noktanın durumunu belirler."
    )

    observations = st.session_state.asset_observations
    severe_count = sum(1 for item in observations.values() if item["class"] == "severe")
    partial_count = sum(1 for item in observations.values() if item["class"] == "partial")
    unblocked_count = sum(1 for item in observations.values() if item["class"] == "unblocked")

    render_observation_status_cards(
        len(assets),
        severe_count,
        partial_count,
        unblocked_count,
    )

    if "observation_saved_message" in st.session_state:
        st.success(st.session_state.pop("observation_saved_message"))

    # 2. SEÇİM VE YÜKLEME PANELİ
    observation_sort_order = {
        "severe": 0,
        "partial": 1,
        "unblocked": 2,
        "unknown": 3,
    }
    selectable_asset_ids = sorted(
        (asset.id for asset in assets),
        key=lambda item_id: (
            observation_sort_order[observations[item_id]["class"]],
            asset_map[item_id].name,
        ),
    )
    with st.container(border=True):
        st.markdown("##### İncelenecek altyapı noktasını seçin")
        c_sel, c_up = st.columns([1.3, 1])
        with c_sel:
            selected_asset_id = st.selectbox(
                "Altyapı noktası ve bağlı görüntü",
                selectable_asset_ids,
                format_func=lambda item_id: (
                    f"{item_id} · {asset_map[item_id].name} · "
                    f"{OBSERVATION_SELECT_LABELS[observations[item_id]['class']]}"
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

    # AI Analizi çalıştır (Önbellekli yüksek hızlı çıkarım)
    if uploaded_image is not None:
        detection = cached_mark_obstruction_regions(
            f"up_{uploaded_image.name}_{len(image_bytes)}", image_bytes
        )
    elif saved_image_bytes:
        detection = cached_mark_obstruction_regions(
            f"saved_{selected_asset_id}_{len(saved_image_bytes)}", saved_image_bytes
        )
    else:
        detection = cached_mark_obstruction_regions(str(image_source), None)
    marked_percent = float(detection["marked_fraction"]) * 100
    
    # Modelin sınıf sonucunu belirleme (Görsel segmentasyon ve alan oranı öncelikli)
    if marked_percent >= 19.0:
        model_class = "severe"
    elif marked_percent >= 8.0:
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
    st.html('<h2 class="status-heading">Önce nerelere müdahale etmeliyiz?</h2>')
    st.caption(
        "Bu bölüm yalnız tıkanıklık oranına bakmaz. Bir noktaya müdahale edildiğinde "
        "drenaj ağının tamamında oluşan değişimi de dikkate alır."
    )
    risks = asset_risk_scores(assets, baseline.node_impact)
    benefits = intervention_benefits(model, actions)

    highest_risk_asset = max(assets, key=lambda asset: risks[asset.id])
    highest_benefit_action = max(actions, key=lambda action: benefits[action.id])
    render_status_cards(
        [
            ("En yüksek yerel risk", highest_risk_asset.name),
            (
                "En etkili tek müdahale",
                asset_map[highest_benefit_action.asset_id].name,
            ),
            ("Kritik Müdahale Noktası", f"{len(actions)} Nokta"),
        ]
    )

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
                "Beklenen ağ faydası": round(benefits[action.id], 1),
            }
        )

    with st.container(border=True):
        st.markdown("#### Müdahale öncelik tablosu")
        st.caption("En üstteki görev, ağ genelinde en fazla beklenen faydayı sağlar.")
        st.dataframe(
            pd.DataFrame(priority_rows),
            width="stretch",
            hide_index=True,
            column_config={
                "Öncelik": st.column_config.NumberColumn("Öncelik", format="%d"),
                "Beklenen ağ faydası": st.column_config.NumberColumn(
                    "Beklenen ağ faydası", format="%.1f puan"
                ),
            },
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
    if weather_mode == "Çevrimdışı senaryo":
        st.html(
            """
            <div class="siper-blinking-alert">
                <div class="siper-blinking-alert__icon">⚠️</div>
                <div>
                    <div class="siper-blinking-alert__title">
                        ⚠️ DİKKAT: 1 GÜN SONRA ŞİDDETLİ SAĞANAK VE SEL RİSKİ BEKLENİYOR ⚠️
                    </div>
                    <div class="siper-blinking-alert__desc">
                        24 SAAT ÖNCESİ KRİTİK SEFERBERLİK PLANI: YAĞIŞ BAŞLAMADAN ÖNCE TÜM KRİTİK NOKTALARA MÜDAHALE EDİLMESİ İÇİN EKİP VE EKİPMANLAR EN YÜKSEK RİSK AZALTIMI SAĞLAYACAK ŞEKİLDE KONUŞLANDIRILMIŞTIR.
                    </div>
                </div>
                <div class="siper-blinking-alert__icon">⚠️</div>
            </div>
            """
        )
    st.html('<h2 class="status-heading">Yağış Öncesi Ekip ve Kaynak Operasyon Planı</h2>')
    st.caption(
        f"Seçili meteoroloji modu: **{weather_mode}** · Yağış başlangıcına kadar müdahale için kalan süre: **{planning_deadline} dakika**. "
        "Algoritma; ekiplerin araç kapasitesi, personel yetkinliği, yol süresi ve ağ hidrolik risk puanını birleştirerek en yüksek taşkın önleme faydasını optimize eder."
    )

    total_personnel = sum(getattr(team, "personnel_count", 3) for team in teams)
    total_vehicles = len(teams)
    prep_time_label = "24 Saat (1440 dk)" if weather_mode != "Canlı Open-Meteo" else f"{planning_deadline} dk"

    render_status_cards(
        [
            ("Kullanılabilir Hazırlık Süresi", prep_time_label),
            ("Aktif Ekip Sayısı", f"{len(teams)} Bölge Ekibi"),
            ("Müdahale Edecek Personel", f"{total_personnel} Uzman"),
            ("Müdahale Aracı", f"{total_vehicles} Özel Ekipmanlı Araç"),
            ("Atanan Kritik Görev", f"{len(plan.assignments)} Nokta"),
        ]
    )

    st.markdown("### 🚒 Saha Ekipleri, Araç Filosu ve Müdahale Güzergahları")
    team_columns = st.columns(len(teams))
    for team_column, team in zip(team_columns, teams):
        team_assignments = sorted(
            [item for item in plan.assignments if item.team_id == team.id],
            key=lambda item: item.start_minute,
        )
        with team_column:
            with st.container(border=True):
                st.markdown(f"#### 👷 {team.name}")
                personnel_count = getattr(team, "personnel_count", 3)
                vehicle_name = getattr(team, "vehicle", "Kombine Acil Müdahale Aracı")
                st.markdown(
                    f"""
                    - **Görevli Personel:** {personnel_count} Kişi
                    - **Tahsis Edilen Araç:** {vehicle_name}
                    - **Mevcut Ekipman:** {', '.join(team.equipment).replace('_', ' ').capitalize()}
                    - **Uzmanlık:** {', '.join(team.skills).replace('_', ' ').capitalize()}
                    - **Çıkış / Konuşlanma:** {asset_map[team.start_asset_id].name}
                    """
                )
                st.divider()
                st.markdown("##### 📍 Müdahale Sırası ve Zaman Çizelgesi")
                if not team_assignments:
                    st.info("Bu kısıtlı sürede ekibin araç/yetkinliğine uygun yeni görev atanmadı.")
                else:
                    team_rows = []
                    for task_number, assignment in enumerate(team_assignments, start=1):
                        action = action_map[assignment.action_id]
                        asset = asset_map[action.asset_id]
                        clock_start = current_time + timedelta(minutes=assignment.start_minute)
                        clock_end = current_time + timedelta(minutes=assignment.end_minute)
                        team_rows.append(
                            {
                                "Öncelik Sırası": f"#{task_number}",
                                "Hedef Altyapı": asset.name,
                                "Müdahale İşlemi": action.name,
                                "Zaman Aralığı": f"{clock_start:%H:%M} – {clock_end:%H:%M}",
                                "İntikal (Yol)": f"{assignment.travel_minutes} dk",
                                "İşlem Süresi": f"{action.duration_minutes} dk",
                            }
                        )
                    st.dataframe(
                        pd.DataFrame(team_rows),
                        width="stretch",
                        hide_index=True,
                    )

    st.markdown("### 🧭 Neden Bu Noktalara Öncelik Verildi?")
    priority_explanation_rows = []
    for assignment in plan.assignments:
        action = action_map[assignment.action_id]
        asset = asset_map[action.asset_id]
        team = team_map[assignment.team_id]
        team_veh = getattr(team, "vehicle", "Kombine Vidanjör").split("(")[0].strip()
        priority_explanation_rows.append(
            {
                "Hedef Nokta": asset.name,
                "Tür": ASSET_STYLES.get(asset.type.value, (asset.type.value,))[0],
                "Atanan Ekip & Araç": f"{team.name} ({team_veh})",
                "Önceliklendirme Gerekçesi": priority_reason(asset),
                "Beklenen Hidrolik Katkı": f"{action.capacity_factor_after*100:.0f}% Kapasiteye Çıkarılacak",
            }
        )
    if priority_explanation_rows:
        st.dataframe(
            pd.DataFrame(priority_explanation_rows),
            width="stretch",
            hide_index=True,
        )

    # Acil müdahale gerektirmeyen noktaların detaylı gerekçeleri (Rakım, Eğim ve Düşük Hasar Riski)
    st.markdown("### 🛡️ Acil Müdahale Gerektirmeyen Altyapı Noktaları ve Gerekçeleri")
    st.caption(
        "Ağdaki 22 noktanın 12'si acil temizlik/müdahale sırasına alınmıştır. Kalan 10 nokta ise "
        "**yüksek rakımda yer almaları (doğal eğimle cazibeli tahliye)**, **yerleşim yoğunluğunun veya can/mal hasar riskinin çok düşük olması** "
        "ve **mevcut hidrolik kapasitelerinin açık ve güvenli olması** nedeniyle acil operasyon gerektirmemekte, kaynak optimizasyonu doğrultusunda pasif izlemede tutulmaktadır."
    )
    unintervened_assets = [
        asset for asset in assets
        if asset.id not in {action_map[assignment.action_id].asset_id for assignment in plan.assignments}
    ]
    UNINTERVENED_DETAILS = {
        "I8": (
            "Yüksek Rakım & Dik Eğim Avantajı",
            "Boztepe yamaçlarında 185m yüksek kotta yer alır. Yüksek topoğrafik eğim sayesinde yüzey suyu yerçekimiyle hızla akar; yerleşim birimlerinde su birikintisi veya can/mal hasarı riski bulunmaz.",
            "🟢 Güvenli (Cazibeli Hızlı Akış)",
        ),
        "I5": (
            "Düşük Risk & Yaya Aksı Bağlantısı",
            "Geniş meydan yaya aksında yer alır; yağmur suyu menfez bağlantısı açık olup anlık taşkın tehlikesi ve araç trafiğini aksatma riski bulunmamaktadır.",
            "🟢 Açık / Güvenli Seviye",
        ),
        "I9": (
            "Düşük Hasar Riski & Doğal Eğim",
            "Uzun Sokak yaya bölgesinde yer alır; doğrudan kot düşüşüyle sahil ana kolektörüne bağlanır. Bölgede bodrum kat yerleşimi veya kritik tesis riski yoktur.",
            "🟢 Açık / Normal",
        ),
        "I10": (
            "Yüksek Kotlu Kampüs Ana Hattı",
            "KTÜ ana kampüs girişinde yüksek kotta yer alır; yerleşim ve can riski taşımayan geniş doğal vadi tahliye hattına sahiptir.",
            "🟢 Açık / Doğal Tahliye",
        ),
        "I11": (
            "İkincil Toplayıcı & Düşük Yoğunluk",
            "Öğrenci yolu ikincil drenaj hattıdır; ana vadi menfezinin hidrolik yükünü doğrudan zorlamaz, tıkanıklık riski önemsiz seviyededir.",
            "🟢 Açık / Normal",
        ),
        "I3": (
            "Yeterli Deşarj Kotu & Açık Hat",
            "Sanayi girişindeki deşarj kotu dere yatağına yakındır; suyun doğal akış yönünde hidrolik darboğaz veya geri tepme riski oluşmaz.",
            "🟢 Açık / Güvenli",
        ),
        "I6": (
            "Kritik Güzergâhtan Bağımsız Hat",
            "Otogar çevre hattı olup alt geçit, köprü veya acil hastane aksında değildir; taşkın riski alt kritik eşiğin altındadır.",
            "🟢 Açık / Normal",
        ),
        "C3": (
            "Geniş Kesitli Ana Menfez",
            "Değirmendere vadi tabanındaki geniş kesitli betonarme menfezdir; akış kapasitesi %95 üzerinde olup tortu/tıkanıklık riski taşımamaktadır.",
            "🟢 Güvenli Kapasite",
        ),
        "P2": (
            "Kapalı Derin İletim Hattı",
            "Cazibeli derin boru iletim hattı olup yüzey taşkınına neden olmaz; hidrolik basma yüksekliği güvenli çalışma sınırındadır.",
            "🟢 Kesintisiz Akış",
        ),
        "O1": (
            "Doğrudan Deniz Deşarjı (Karadeniz)",
            "Liman ana sahil tahliye çıkışıdır. Deniz seviyesinde serbest çıkış sağlar; tıkanma veya yüzeye geri taşma riski yoktur.",
            "🟢 Serbest Deşarj",
        ),
    }

    unintervened_rows = []
    for asset in unintervened_assets:
        info = UNINTERVENED_DETAILS.get(
            asset.id,
            (
                "Yüksek Kot / Düşük Hasar Riski",
                "Topoğrafik eğim avantajı ve yerleşim yoğunluğunun düşük olması sebebiyle acil risk teşkil etmemektedir.",
                "🟢 Güvenli",
            ),
        )
        unintervened_rows.append(
            {
                "Altyapı Noktası": asset.name,
                "Tür": ASSET_STYLES.get(asset.type.value, (asset.type.value,))[0],
                "Müdahale Gerektirmeme Sebebi": info[0],
                "Rakım & Risk Değerlendirmesi": info[1],
                "Mevcut Durum": info[2],
            }
        )
    st.dataframe(
        pd.DataFrame(unintervened_rows),
        width="stretch",
        hide_index=True,
    )

    with st.expander(f"⏳ Zaman veya Kaynak Kısıtı Nedeniyle Sıraya Alınamayan Noktalar ({len(plan.rejected)})"):
        st.caption("Bu noktalar yağış başlangıcına kadar intikal süresi yetmediği veya gerekli araç/ekip başka acil noktada olduğu için yedek plana bırakılmıştır.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Altyapı Noktası": asset_map[action_map[action_id].asset_id].name,
                        "Ertelenen İşlem": action_map[action_id].name,
                        "Gerekçe / Kısıt": reason,
                    }
                    for action_id, reason in plan.rejected.items()
                ]
            ),
            width="stretch",
            hide_index=True,
        )

with tabs[5]:
    col_head, col_quick, col_reset = st.columns([2.2, 1.4, 1.2])
    with col_head:
        st.html('<h2 class="status-heading">Sahadaki Görevleri Ekip Bazında Takip Edin ve Onaylayın</h2>')
        st.caption(
            "Her ekibin üzerine atanan görevleri sırayla inceleyin; çalışma bittiğinde 'Tamamlandı' ve 'Doğrulandı' olarak işaretleyin."
        )
    with col_quick:
        if st.button("⚡ Tüm 12 Görevi Toplu Onayla", key="btn_quick_all", type="primary", help="Tüm ekiplerin görevlerini tek tıkla sahada tamamlandı ve doğrulandı yapar"):
            for i, o in enumerate(st.session_state.orders):
                if o.status != WorkOrderStatus.VERIFIED:
                    if o.status == WorkOrderStatus.ASSIGNED:
                        o = mark_completed(o)
                    st.session_state.orders[i] = verify_order(
                        o,
                        {"class": "unblocked", "source": "operator_input", "note": "Toplu operatör saha onayı"}
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
    with col_reset:
        if st.button("🔄 Tüm Görevleri Baştan Başlat", key="btn_reset_orders_tab5", help="Tüm görev durumlarını sıfırlar"):
            st.session_state.pop("orders", None)
            st.session_state.pop("replanned", None)
            st.rerun()

    if "orders" not in st.session_state:
        st.session_state.orders = create_work_orders(plan)
    
    # Tüm 12 görevin atandığından emin ol
    existing_action_ids = {o.action_id for o in st.session_state.orders}
    new_orders = list(st.session_state.orders)
    for assignment in plan.assignments:
        if assignment.action_id not in existing_action_ids:
            new_orders.append(
                WorkOrder(
                    id=f"WO-{assignment.action_id}",
                    action_id=assignment.action_id,
                    team_id=assignment.team_id,
                    status=WorkOrderStatus.ASSIGNED,
                    event_log=[{"time": datetime.now().isoformat(), "status": "assigned", "reason": "Plana dahil edildi", "source": "operator_input"}],
                )
            )
    st.session_state.orders = new_orders

    total_orders = len(st.session_state.orders)
    verified_orders = sum(1 for o in st.session_state.orders if o.status == WorkOrderStatus.VERIFIED)
    pending_orders = sum(1 for o in st.session_state.orders if o.status == WorkOrderStatus.COMPLETED_PENDING_VERIFICATION)
    active_orders = sum(1 for o in st.session_state.orders if o.status == WorkOrderStatus.ASSIGNED)

    render_status_cards(
        [
            ("Toplam İş Emri", f"{total_orders} Görev"),
            ("Tamamlanan & Doğrulanan", f"{verified_orders} Nokta"),
            ("Onay Bekleyenler", f"{pending_orders} Görev"),
            ("Sahada Devam Eden", f"{active_orders} Görev"),
        ]
    )

    # Ekip bazında sekmeler / filtreler
    team_tabs = st.tabs([f"👷 {team.name}" for team in teams])
    for team_tab, team in zip(team_tabs, teams):
        with team_tab:
            team_orders = [o for o in st.session_state.orders if o.team_id == team.id]
            if not team_orders:
                st.info("Bu ekibe henüz görev atanmadı.")
                continue

            col_team_info, col_team_btn = st.columns([2.5, 1.5])
            with col_team_info:
                st.caption(f"**{team.name}** için toplam {len(team_orders)} kritik görev planlanmıştır.")
            with col_team_btn:
                if any(o.status != WorkOrderStatus.VERIFIED for o in team_orders):
                    if st.button(f"⚡ {team.name} Görevlerini Toplu Onayla", key=f"btn_quick_team_{team.id}"):
                        for i, o in enumerate(st.session_state.orders):
                            if o.team_id == team.id and o.status != WorkOrderStatus.VERIFIED:
                                if o.status == WorkOrderStatus.ASSIGNED:
                                    o = mark_completed(o)
                                st.session_state.orders[i] = verify_order(
                                    o,
                                    {"class": "unblocked", "source": "operator_input", "note": f"{team.name} saha incelemesi tamamlandı"}
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

            for idx, order in enumerate(team_orders, start=1):
                action = action_map[order.action_id]
                asset = asset_map[action.asset_id]
                
                status_icon = (
                    "✅" if order.status == WorkOrderStatus.VERIFIED
                    else "⏳" if order.status == WorkOrderStatus.COMPLETED_PENDING_VERIFICATION
                    else "📍"
                )
                
                with st.container(border=True):
                    col_info, col_act = st.columns([2.2, 1.8])
                    with col_info:
                        st.markdown(f"##### {status_icon} #{idx}. {action.name}")
                        st.caption(f"**Konum:** {asset.name} ({ASSET_STYLES.get(asset.type.value, (asset.type.value,))[0]}) · **Öncelik Sebebi:** {priority_reason(asset)}")
                        st.write(f"**Durum:** `{STATUS_LABELS.get(order.status.value, order.status.value)}` | **İşlem Süresi:** {action.duration_minutes} dk")
                    
                    with col_act:
                        all_indices = [i for i, o in enumerate(st.session_state.orders) if o.id == order.id]
                        if all_indices:
                            real_idx = all_indices[0]
                            if order.status == WorkOrderStatus.ASSIGNED:
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button("Tamamlandı Bildir", key=f"btn_comp_{order.id}", width="stretch"):
                                        st.session_state.orders[real_idx] = mark_completed(order)
                                        st.rerun()
                                with c2:
                                    if st.button("⚡ Hızlı Doğrula", key=f"btn_fast_ver_{order.id}", type="primary", width="stretch"):
                                        comp = mark_completed(order)
                                        st.session_state.orders[real_idx] = verify_order(
                                            comp,
                                            {"class": "unblocked", "source": "operator_input", "note": "Saha ekiplerince temizlik doğrulandı"}
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
                            elif order.status == WorkOrderStatus.COMPLETED_PENDING_VERIFICATION:
                                if st.button("✅ Saha Gözlemiyle Doğrula & Onayla", key=f"btn_ver_{order.id}", type="primary", width="stretch"):
                                    st.session_state.orders[real_idx] = verify_order(
                                        order,
                                        {"class": "unblocked", "source": "operator_input", "note": "Saha ekiplerince temizlik doğrulandı"}
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
                            else:
                                st.success("✅ Görev Tamamlandı ve Doğrulandı")

with tabs[6]:
    st.html('<h2 class="status-heading">Bu plan bize ne kazandırıyor?</h2>')
    st.caption(
        "Aynı süre ve ekip koşullarında planın sağladığı beklenen faydayı ve "
        "geleneksel seçim yöntemleriyle farkını görün."
    )
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

    # Operasyon takibinde doğrulanmış görev sayısı ve detayları
    verified_orders_list = [o for o in st.session_state.get("orders", []) if o.status == WorkOrderStatus.VERIFIED]
    verified_count = len(verified_orders_list)

    render_status_cards(
        [
            ("Planlanan Toplam Görev", f"{len(plan.assignments)} Müdahale"),
            ("Kurtarılan Tehlikeli Nokta", f"{critical_location_count} Kritik Alan"),
            ("Doğrulanan Saha Müdahalesi", f"{verified_count} Onaylı"),
            ("Kalan Ağ Riski Azalımı", f"%{improvement_percent:.1f}"),
        ]
    )

    if verified_orders_list:
        with st.container(border=True):
            st.markdown(f"#### 🏆 Doğrulanan ve Güvenceye Alınan Altyapı Noktaları ({verified_count} Nokta)")
            st.caption("Operasyon takibinde ekiplerce sahada tamamlanıp operatör incelemesiyle onaylanan ve taşkın riski önlenen noktalar:")
            verified_display_rows = []
            for v_order in verified_orders_list:
                v_action = action_map[v_order.action_id]
                v_asset = asset_map[v_action.asset_id]
                v_team = team_map[v_order.team_id]
                verified_display_rows.append(
                    {
                        "Kurtarılan / Güvenceye Alınan Nokta": v_asset.name,
                        "Tamamlanan Müdahale": v_action.name,
                        "Müdahale Eden Ekip": v_team.name,
                        "Ulaşılan Kapasite": f"%{v_action.capacity_factor_after*100:.0f}",
                        "Önlenen Risk / Tehlike": priority_reason(v_asset),
                        "Operasyon Onayı": "✅ Sahada Doğrulandı",
                    }
                )
            st.dataframe(pd.DataFrame(verified_display_rows), width="stretch", hide_index=True)

    st.success(
        f"Plan uygulandığında ağ üzerindeki beklenen baskı yaklaşık %{improvement_percent:.1f} azalıyor. "
        f"Yağış başlamadan önce {len(plan.assignments)} görev tamamlanabiliyor."
    )
    st.progress(
        min(100, max(0, int(round(improvement_percent)))),
        text=f"Planla azaltılan ağ baskısı: %{improvement_percent:.1f}",
    )

    with st.container(border=True):
        st.markdown("#### Planın somut faydaları")
        benefit_rows = [
            {
                "Başlık": "Belirgin tıkanıklıklar",
                "Sonuç": f"{addressed_blockage_count} noktaya müdahale ediliyor",
            },
            {
                "Başlık": "Kritik noktalar",
                "Sonuç": f"{critical_location_count} kritik bağlantıya öncelik veriliyor",
            },
            {
                "Başlık": "Paralel çalışma",
                "Sonuç": f"{used_team_count} ekip aynı zaman aralığında çalışıyor",
            },
            {
                "Başlık": "Plan sonu",
                "Sonuç": (
                    f"Son görev {latest_finish_clock:%H:%M} saatinde bitiyor"
                    if plan.assignments
                    else "Planlanmış görev bulunmuyor"
                ),
            },
            {
                "Başlık": "Kalan ağ baskısı",
                "Sonuç": f"Başlangıç seviyesinin %{remaining_pressure:.1f} kadarı",
            },
            {
                "Başlık": "Plan kısıtları",
                "Sonuç": "Ekip, araç ve süre sınırları korunuyor",
            },
        ]
        st.dataframe(
            pd.DataFrame(benefit_rows),
            width="stretch",
            hide_index=True,
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
            render_status_cards(
                [
                    ("Müdahale yok", f"{swmm_baseline:.2f} m³"),
                    ("Menfez kapasitesi geri kazanılırsa", f"{swmm_culvert:.2f} m³"),
                    ("Üç üst-hat müdahalesi", f"{swmm_portfolio:.2f} m³"),
                ]
            )
            st.caption(
                "EPA SWMM 5.2.4 · Sentetik geometri ve yağış · Saha kalibrasyonu yapılmadı"
            )

    with st.container(border=True):
        st.markdown("#### Yöntemlerin görev karşılaştırması")
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
