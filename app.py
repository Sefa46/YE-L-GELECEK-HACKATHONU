from __future__ import annotations

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
from siper.storage import load_actions, load_assets, load_teams, load_weather, project_root
from siper.vision import assess_obstruction
from siper.workflow import (
    create_work_orders,
    mark_completed,
    replan_after_verification,
    verify_order,
)


st.set_page_config(page_title="SİPER AI", page_icon="🛡️", layout="wide")

assets = load_assets()
actions = load_actions()
teams = load_teams()
event = load_weather()
model = ProxyHydraulicModel(assets, event)
baseline = model.run()
plan = optimize_plan(model, actions, teams)
asset_map = {asset.id: asset for asset in assets}
action_map = {action.id: action for action in actions}
team_map = {team.id: team for team in teams}

st.title("🛡️ SİPER AI")
st.caption("Sel İçin Proaktif Erken Risk Yönetimi — karar destek ve operasyon simülasyon prototipi")
st.warning(
    "DEMO SINIRI: Tüm olay ve saha verileri sentetiktir. Sonuçlar "
    "**HEURISTIC / NOT HYDRAULICALLY VALIDATED** proxy modelinden gelir; m³ taşma tahmini değildir."
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
    st.subheader(event.name)
    cols = st.columns(4)
    cols[0].metric("Yağışa kalan temsili süre", f"{event.horizon_minutes} dk")
    cols[1].metric("Toplam senaryo yağışı", f"{sum(event.hourly_rain_mm):.1f} mm")
    cols[2].metric("Ağ varlığı", len(assets))
    cols[3].metric("Veri kaynağı", event.source.value)
    st.info(event.reliability_note)
    weather_df = pd.DataFrame(
        {"Saat": list(range(1, len(event.hourly_rain_mm) + 1)), "Yağış (mm)": event.hourly_rain_mm}
    )
    st.bar_chart(weather_df.set_index("Saat"))

with tabs[1]:
    st.subheader("Bağlantılı sentetik drenaj ağı")
    diagnostics = network_diagnostics(assets)
    c1, c2, c3 = st.columns(3)
    c1.metric("Düğüm", diagnostics["node_count"])
    c2.metric("Bağlantı", diagnostics["edge_count"])
    c3.metric("Çıkışa ulaşamayan", len(diagnostics["unreachable_to_outfall"]))

    edge_traces = []
    for source, target in model.graph.edges:
        a, b = asset_map[source], asset_map[target]
        edge_traces.append(
            go.Scattergeo(
                lon=[a.lon, b.lon], lat=[a.lat, b.lat], mode="lines",
                line={"width": 2, "color": "#4f6b66"}, hoverinfo="skip", showlegend=False
            )
        )
    node_trace = go.Scattergeo(
        lon=[asset.lon for asset in assets],
        lat=[asset.lat for asset in assets],
        text=[f"{asset.name}<br>{asset.type.value}<br>Kaynak: {asset.observation_source.value}" for asset in assets],
        mode="markers+text",
        textposition="top center",
        marker={"size": 13, "color": [baseline.node_impact[asset.id] for asset in assets], "colorscale": "YlOrRd", "showscale": True},
    )
    fig = go.Figure(edge_traces + [node_trace])
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(height=520, margin={"l": 0, "r": 0, "t": 10, "b": 0})
    st.plotly_chart(fig, width="stretch")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": asset.id,
                    "Ad": asset.name,
                    "Tür": asset.type.value,
                    "Bölge": asset.drainage_zone_id,
                    "Kaynak": asset.observation_source.value,
                    "Görünür kapanma": asset.blockage_visual_fraction,
                    "Hidrolik kapasite katsayısı": asset.hydraulic_capacity_factor,
                }
                for asset in assets
            ]
        ),
        width="stretch",
        hide_index=True,
    )

with tabs[2]:
    st.subheader("Manuel doğrulamalı görsel gözlem")
    st.info("P0 sürümünde otomatik CV doğruluğu iddiası yoktur. Görsel etiket operatör tarafından doğrulanır.")
    visual_assets = [asset for asset in assets if asset.image_path]
    selected_asset_id = st.selectbox(
        "Görsel fixture",
        [asset.id for asset in visual_assets],
        format_func=lambda item: asset_map[item].name,
    )
    selected_asset = asset_map[selected_asset_id]
    left, right = st.columns([1.4, 1])
    with left:
        st.image(str(project_root() / selected_asset.image_path), caption="Yapay üretilmiş sentetik demo görüntüsü")
    with right:
        label = st.selectbox("Operatör sınıfı", [item.value for item in ObservationClass])
        fraction = st.slider("Görünür kapanma oranı", 0.0, 1.0, float(selected_asset.blockage_visual_fraction or 0), 0.01)
        if st.button("Gözlemi doğrula"):
            result = assess_obstruction(
                str(project_root() / selected_asset.image_path), ObservationClass(label), fraction
            )
            st.success(f"Kayıt: {result['class'].value} — kaynak: {result['source'].value}")
    st.error("Görünür kapanma oranı, hidrolik kapasite katsayısına otomatik kopyalanmaz.")

with tabs[3]:
    st.subheader("Müdahalesiz risk ve müdahale portföyleri")
    risks = asset_risk_scores(assets, baseline.node_impact)
    benefits = intervention_benefits(model, actions)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Varlık": asset_map[action.asset_id].name,
                    "Eylem": action.name,
                    "Yerel risk indeksi": risks[action.asset_id],
                    "Tekli sistem faydası": benefits[action.id],
                }
                for action in actions
            ]
        ).sort_values("Tekli sistem faydası", ascending=False),
        width="stretch",
        hide_index=True,
    )
    action_a, action_b = action_map["A1"], action_map["A3"]
    delta = synergy_delta(model, action_a, action_b)
    st.metric("A1 + A3 etkileşim farkı", f"{delta:+.2f} indeks puanı")
    st.caption("Sıfır olmayan değer, birleşik faydanın tekli faydaların kör toplamı olmadığını gösterir.")

with tabs[4]:
    st.subheader("120 dakikalık iki ekipli uygulanabilir plan")
    p1, p2, p3 = st.columns(3)
    p1.metric("Başlangıç etki indeksi", f"{plan.baseline_impact_index:.2f}")
    p2.metric("Planlı etki indeksi", f"{plan.planned_impact_index:.2f}")
    p3.metric("Modellenen fayda", f"{plan.simulated_benefit:.2f}")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Ekip": team_map[item.team_id].name,
                    "Görev": action_map[item.action_id].name,
                    "Yol (dk)": item.travel_minutes,
                    "Başlangıç": item.start_minute,
                    "Bitiş": item.end_minute,
                }
                for item in plan.assignments
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    st.markdown("**Seçilmeyen görevlerin gerekçesi**")
    st.dataframe(
        pd.DataFrame([{"Görev": action_map[key].name, "Gerekçe": value} for key, value in plan.rejected.items()]),
        width="stretch",
        hide_index=True,
    )

with tabs[5]:
    st.subheader("İş emri → tamamlanma → doğrulama → yeniden planlama")
    if "orders" not in st.session_state:
        st.session_state.orders = create_work_orders(plan)
    order_ids = [order.id for order in st.session_state.orders]
    selected_order_id = st.selectbox("İş emri", order_ids)
    index = order_ids.index(selected_order_id)
    order = st.session_state.orders[index]
    st.write(f"**Durum:** `{order.status.value}` — **Görev:** {action_map[order.action_id].name}")
    col_a, col_b = st.columns(2)
    if col_a.button("Tamamlandı bildir", disabled=order.status != WorkOrderStatus.ASSIGNED):
        st.session_state.orders[index] = mark_completed(order)
        st.rerun()
    if col_b.button(
        "Yeni gözlemle doğrula ve yeniden planla",
        disabled=order.status != WorkOrderStatus.COMPLETED_PENDING_VERIFICATION,
    ):
        st.session_state.orders[index] = verify_order(
            order, {"class": "unblocked", "source": "operator_input", "note": "Demo doğrulaması"}
        )
        st.session_state.replanned = replan_after_verification(
            assets, event, actions, teams, st.session_state.orders
        )
        st.rerun()
    st.dataframe(pd.DataFrame(order.event_log), width="stretch", hide_index=True)
    if "replanned" in st.session_state:
        new_plan = st.session_state.replanned
        st.success(f"Yeni plan üretildi: {new_plan.plan_id}")
        st.write("Kalan görevler:", ", ".join(new_plan.selected_action_ids))

with tabs[6]:
    st.subheader("Aynı koşullarda politika karşılaştırması")
    comparison = compare_policies(assets, actions, teams, model)
    comparison_df = pd.DataFrame(comparison)
    st.dataframe(comparison_df, width="stretch", hide_index=True)
    st.bar_chart(comparison_df.set_index("policy")[["impact_index"]])
    st.caption("Daha düşük etki indeksi daha iyidir. Bu, kalibre edilmiş taşma hacmi veya gerçek sel azaltımı değildir.")
    st.markdown(
        """
        **Gerçek durum:** Ağ/veri sözleşmeleri, proxy senaryo, kısıtlı planlama ve yeniden planlama çalışıyor.
        **Simülasyon:** Yağış, sensörler, görüntüler, saha eylemleri ve bütün etki indeksleri.
        **Yapılmadı:** SWMM kalibrasyonu, otomatik CV modeli, canlı MGM/Open-Meteo ve gerçek belediye entegrasyonu.
        """
    )
