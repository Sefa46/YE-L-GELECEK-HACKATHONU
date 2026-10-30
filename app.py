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
from siper.workflow import (
    create_work_orders,
    mark_completed,
    replan_after_verification,
    verify_order,
)


st.set_page_config(page_title="SİPER AI", layout="wide")

assets = load_assets()
actions = load_actions()
teams = load_teams()
event = load_weather()
vision_samples = load_vision_samples()
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


st.title("SİPER AI")
st.caption("Sel İçin Proaktif Erken Risk Yönetimi — Yağış öncesi drenaj risk ve operasyon planlama sistemi")

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

with tabs[1]:
    st.subheader("Bağlantılı drenaj ağı")
    diagnostics = network_diagnostics(assets)
    map_risks = asset_risk_scores(assets, baseline.node_impact)
    maximum_risk = max(map_risks.values())
    high_risk_ids = {
        asset_id for asset_id, score in map_risks.items() if score / maximum_risk >= 0.6
    }
    blocked_ids = {
        asset.id
        for asset in assets
        if asset.blockage_visual_fraction is not None and asset.blockage_visual_fraction >= 0.6
    }

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Düğüm", diagnostics["node_count"])
    c2.metric("Bağlantı", diagnostics["edge_count"])
    c3.metric("Yüksek riskli nokta", len(high_risk_ids))
    c4.metric("Belirgin tıkanıklık", len(blocked_ids))

    map_view = st.radio(
        "Harita görünümü",
        ["Risk ve tıkanıklık", "Altyapı türleri"],
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

    if map_view == "Risk ve tıkanıklık":
        hover_text = []
        risk_labels = []
        for asset in assets:
            risk_ratio = map_risks[asset.id] / maximum_risk
            risk_label = "Yüksek" if risk_ratio >= 0.6 else "Orta" if risk_ratio >= 0.3 else "Düşük"
            risk_labels.append(risk_label)
            visual_fraction = (
                f"%{asset.blockage_visual_fraction * 100:.0f}"
                if asset.blockage_visual_fraction is not None
                else "Veri yok"
            )
            water_level = f"{asset.water_level_m:.2f} m" if asset.water_level_m is not None else "Veri yok"
            downstream = ", ".join(asset.downstream_ids) if asset.downstream_ids else "Çıkış"
            hover_text.append(
                f"<b>{asset.name}</b><br>"
                f"Kimlik: {asset.id}<br>"
                f"Tür: {ASSET_STYLES[asset.type.value][0]}<br>"
                f"Bölge: {asset.drainage_zone_id}<br>"
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
                        14 + 24 * (asset.blockage_visual_fraction or 0)
                        for asset in assets
                    ],
                    "color": [map_risks[asset.id] for asset in assets],
                    "colorscale": [[0, "#4f9bd8"], [0.5, "#f2c14e"], [1, "#c43d3d"]],
                    "cmin": 0,
                    "cmax": maximum_risk,
                    "showscale": True,
                    "colorbar": {"title": "Risk puanı"},
                    "opacity": 0.92,
                },
                name="Risk noktaları",
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
    st.plotly_chart(map_figure, width="stretch", config={"displayModeBar": True, "scrollZoom": True})

    if map_view == "Risk ve tıkanıklık":
        st.caption(
            "Renk risk seviyesini gösterir: mavi düşük, sarı orta, kırmızı yüksek. "
            "Nokta büyüklüğü görünür tıkanıklık oranına göre artar."
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
    st.caption("Saha kameralarından ve ekiplerden gelen görseller taranarak tıkanıklık bölgeleri tespit edilir.")

    # 1. ÖZET & UYARI ÇUBUĞU (Kırmızı / Sarı / Yeşil uyarı kartları)
    flagged_samples = [s for s in vision_samples if s["dataset_class"] in {"severe", "partial"}]
    severe_count = sum(1 for s in vision_samples if s["dataset_class"] == "severe")
    partial_count = sum(1 for s in vision_samples if s["dataset_class"] == "partial")
    unblocked_count = sum(1 for s in vision_samples if s["dataset_class"] == "unblocked")

    stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
    stat_c1.metric("Toplam Görsel Kaydı", len(vision_samples))
    stat_c2.metric("🚨 Acil / Ciddi Tıkalı", severe_count)
    stat_c3.metric("⚠️ Kısmi Tıkanma", partial_count)
    stat_c4.metric("✅ Açık / Normal", unblocked_count)

    if severe_count > 0:
        st.error(
            f"🚨 **KRİTİK UYARI:** {severe_count} noktada menfez/mazgal su girişinin ciddi derecede tıkandığı tespit edildi! "
            "Taşkın riskini önlemek için acil müdahale ekibi yönlendirilmelidir."
        )

    # 2. SEÇİM VE YÜKLEME PANELİ
    sample_map = {sample["id"]: sample for sample in vision_samples}
    
    with st.container(border=True):
        st.markdown("##### 🔍 İncelenecek Görüntüyü Seçin veya Yeni Fotoğraf Yükleyin")
        c_sel, c_up = st.columns([1.3, 1])
        with c_sel:
            def _format_sample_choice(item_id: str) -> str:
                s = sample_map[item_id]
                cls = s["dataset_class"]
                icon = "🚨" if cls == "severe" else "⚠️" if cls == "partial" else "✅"
                return f"{icon} {s['id']} · {s['name']} [{OBSERVATION_LABELS[cls]}]"

            selected_sample_id = st.selectbox(
                "Mevcut Saha Görseli",
                list(sample_map),
                format_func=_format_sample_choice,
            )
        with c_up:
            uploaded_image = st.file_uploader(
                "Veya Yeni Saha Fotoğrafı Yükle",
                type=["jpg", "jpeg", "png"],
                help="Saha ekibinden gelen yeni fotoğrafı yükleyip anında analiz ettirebilirsiniz.",
            )

    selected_sample = sample_map[selected_sample_id]
    if uploaded_image is not None:
        image_bytes = uploaded_image.getvalue()
        image_source = image_bytes
        image_caption = f"Yüklenen: {uploaded_image.name}"
        dataset_class = None
    else:
        image_source = project_root() / selected_sample["path"]
        image_caption = f"{selected_sample['id']} · {selected_sample['name']}"
        dataset_class = selected_sample["dataset_class"]

    # AI Analizi çalıştır
    detection = mark_obstruction_regions(image_source)
    marked_percent = float(detection["marked_fraction"]) * 100
    
    # Uyarı durumu belirleme
    is_severe_alert = (dataset_class == "severe") or (marked_percent >= 30.0)
    is_partial_alert = (dataset_class == "partial") or (10.0 <= marked_percent < 30.0)

    # 3. ANALİZ ÖZET KARTI
    with st.container(border=True):
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Kayıt ID / Adı", image_caption.split(" · ")[-1] if " · " in image_caption else image_caption)
        
        if is_severe_alert:
            col_m2.metric("Tespit Durumu", "🚨 Ciddi Tıkanıklık")
        elif is_partial_alert:
            col_m2.metric("Tespit Durumu", "⚠️ Kısmi Tıkanıklık")
        else:
            col_m2.metric("Tespit Durumu", "✅ Normal / Açık")

        col_m3.metric("İşaretlenen Tıkanıklık Alanı", f"%{marked_percent:.1f}")
        col_m4.metric("Tespit Edilen Bölge Sayısı", detection["region_count"])

        st.caption(f"🧠 **Çalışan AI Modeli:** `{detection.get('method', 'YOLOE-26n-seg + MobileCLIP2')}`")

        # MobileCLIP2 Güven Skorları Gösterimi
        clip_scores = detection.get("clip_scores")
        if clip_scores:
            cl1, cl2, cl3 = st.columns(3)
            cl1.metric("MobileCLIP2 Açık Güveni", f"%{clip_scores.get('unblocked', 0)*100:.1f}")
            cl2.metric("MobileCLIP2 Kısmi Tıkalı", f"%{clip_scores.get('partial', 0)*100:.1f}")
            cl3.metric("MobileCLIP2 Ciddi Tıkalı", f"%{clip_scores.get('severe', 0)*100:.1f}")

        if is_severe_alert:
            st.error("🚨 **DİKKAT:** Bu yapıda yüksek oranda tıkanıklık tespit edildi! Hidrolik kapasite düşüşü risk teşkil ediyor.")
        elif is_partial_alert:
            st.warning("⚠️ **UYARI:** Kısmi çöp/tortu birikmesi mevcut. Yağış öncesi kontrol önerilir.")
        else:
            st.success("✅ **BİLGİ:** Su giriş kesiti açık, tıkanıklık engeli görünmüyor.")

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

    # 5. GÖRSEL AKIŞI / GALERİ (DÜZENLİ KARTLAR)
    st.markdown("##### 📂 Tüm Saha Görüntüleri Arşivi")
    gallery_cols = st.columns(len(vision_samples))
    for col, sample in zip(gallery_cols, vision_samples):
        cls = sample["dataset_class"]
        icon = "🚨" if cls == "severe" else "⚠️" if cls == "partial" else "✅"
        with col:
            with st.container(border=True):
                st.image(str(project_root() / sample["path"]), width="stretch")
                st.caption(f"**{sample['id']}**\n\n{icon} {OBSERVATION_LABELS[cls]}")

    # 6. OPERATÖR DOĞRULAMA & ENTEGRASYON
    with st.expander("🛠️ Operatör Doğrulama ve Altyapı Kaydı", expanded=False):
        inspection_assets = [
            asset
            for asset in assets
            if asset.inspection_accessible
            and asset.type.value in {"inlet", "grate", "culvert", "open_channel"}
        ]
        linked_asset_id = st.selectbox(
            "Bağlanacak Altyapı Noktası",
            [asset.id for asset in inspection_assets],
            index=next(
                (
                    index
                    for index, asset in enumerate(inspection_assets)
                    if asset.id == "C1"
                ),
                0,
            ),
            format_func=lambda item: f"{item} · {asset_map[item].name} ({ASSET_STYLES[asset_map[item].type.value][0]})",
        )
        class_values = [item.value for item in ObservationClass]
        suggested_class = dataset_class or (
            "severe" if marked_percent >= 30 else "partial" if marked_percent >= 10 else "unblocked"
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
            fraction = st.slider(
                "Görünür Kapanma Oranı",
                0.0,
                1.0,
                min(1.0, float(detection["marked_fraction"])),
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
            st.success(
                f"✅ {asset_map[linked_asset_id].name} için gözlem onaylandı: "
                f"**{OBSERVATION_LABELS[result['class'].value]}** (Görünür Kapanma: %{fraction*100:.0f})"
            )
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
    comparison_df["improvement_percent"] = comparison_df["impact_index"].map(
        lambda impact: 100 * (baseline_impact - impact) / baseline_impact
    )
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
