"""
FIT Analyzer per tesi Gaia - Streamlit UI.

Uso locale:
    streamlit run app.py

Deploy: Streamlit Community Cloud (share.streamlit.io) da repo GitHub pubblico.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from analyzer import (
    Tratto,
    analyze_fit,
    default_soglie,
    deg_to_semi,
    extract_route,
    points_in_tratto,
    semi_to_deg,
)
import storage

st.set_page_config(page_title="FIT Analyzer V2 X Fiandre - Tesi Gaia", page_icon="🚴", layout="wide")

# ────────────────────────── MANUTENZIONE PROGRAMMATA ──────────────────────────
# L'app resta offline fino a questo istante (Europe/Rome), poi si riattiva da sola.
# Per anticipare/posticipare basta cambiare la data qui sotto e fare push.
MAINTENANCE_UNTIL = datetime(2026, 8, 8, 17, 0, tzinfo=ZoneInfo("Europe/Rome"))

_now_rome = datetime.now(tz=ZoneInfo("Europe/Rome"))
if _now_rome < MAINTENANCE_UNTIL:
    st.markdown(
        """
        <div style="max-width: 640px; margin: 6rem auto; padding: 3rem;
                    background: #12121a; border: 1px solid rgba(212, 255, 58, 0.25);
                    border-radius: 20px; text-align: center; font-family: 'Inter', sans-serif;">
            <div style="color: #d4ff3a; font-family: 'JetBrains Mono', monospace;
                        font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.15em;
                        margin-bottom: 1.5rem;">→ Manutenzione in corso</div>
            <h1 style="color: #f5f5f7; font-size: 2.4rem; margin-bottom: 0;
                       line-height: 1.15; font-weight: 700;">
                Il tool è temporaneamente <span style="color: #d4ff3a;">offline</span>.
            </h1>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


def _check_login() -> bool:
    """Login semplice via st.secrets['users']. Se non ci sono secrets, l'app è aperta."""
    try:
        users = st.secrets.get("users", {})
    except Exception:
        users = {}
    if not users:
        return True
    if st.session_state.get("auth_ok"):
        return True
    st.title("🚴 FIT Analyzer")
    st.write("Login richiesto.")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Entra")
    if ok:
        if users.get(u) == p:
            st.session_state["auth_ok"] = True
            st.session_state["auth_user"] = u
            st.rerun()
        else:
            st.error("Credenziali non valide.")
    return False


if not _check_login():
    st.stop()

# ────────────────────────── TIER & DELIVERABLES ──────────────────────────
# I tier disponibili (in ordine crescente di accesso).
# Deliverable unlocked per tier: definito nella mappa qui sotto.
DELIVERABLES_BY_TIER = {
    # tesi (una tantum)
    "base":        set(),
    "plus":        {"manuale_pdf"},
    "premium":     {"manuale_pdf", "report_metodologico"},
    # accademico (annuale)
    "starter":     set(),
    "team":        {"manuale_pdf"},
    "dipartimento": {"manuale_pdf", "report_metodologico"},
}

def _user_tier() -> str:
    """Ritorna il tier dell'utente loggato (default 'premium' per l'utente originale Gaia)."""
    try:
        tiers = st.secrets.get("tiers", {})
    except Exception:
        tiers = {}
    user = st.session_state.get("auth_user", "")
    return tiers.get(user, "premium")

def _has_deliverable(name: str) -> bool:
    return name in DELIVERABLES_BY_TIER.get(_user_tier(), set())


st.title("🚴 FIT Analyzer - Tesi Gaia")
st.caption("Carica uno o più file .fit, calcola in un colpo TUTTE le soglie W/kg per TUTTI i tratti.")

# ────────────────────────── MATERIALI DEL PACCHETTO ──────────────────────────
with st.sidebar:
    st.subheader("🎓 Materiali del tuo pacchetto")
    tier_attivo = _user_tier()
    st.caption(f"Pacchetto attivo: **{tier_attivo.capitalize()}**")

    if _has_deliverable("manuale_pdf"):
        try:
            with open("deliverables/manuale_fit_analyzer.pdf", "rb") as f:
                pdf_bytes = f.read()
            st.download_button(
                "📘 Scarica il manuale (PDF)",
                pdf_bytes,
                file_name="Manuale_FIT_Analyzer.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except FileNotFoundError:
            st.warning("Manuale non trovato. Contatta il supporto.")
    else:
        st.info("🔒 Il manuale PDF è incluso nei pacchetti Plus, Premium, Team, Dipartimento.")

# ────────────────────────── ARCHIVIO SIDEBAR ──────────────────────────
with st.sidebar:
    st.divider()
    if storage.is_enabled():
        st.subheader("📚 Archivio")
        try:
            corridori_in_archivio = storage.list_corridori()
            st.caption(f"{len(corridori_in_archivio)} corridori salvati")
            with st.expander("Vedi elenco"):
                for c in corridori_in_archivio:
                    st.write(f"• {c}")
            auto_save = st.checkbox("Salva automaticamente le analisi in archivio", value=True)
        except Exception as e:
            st.warning(f"Archivio non raggiungibile: {e}")
            auto_save = False
    else:
        st.info("Archivio non configurato (aggiungi `[storage]` nei secrets).")
        auto_save = False
    st.session_state["auto_save"] = auto_save

# ────────────────────────── SIDEBAR ──────────────────────────
with st.sidebar:
    st.header("Parametri globali")
    peso_kg = st.number_input("Peso corridore (kg)", 40.0, 100.0, 72.0, 0.5)
    rolling_s = st.number_input("Media mobile (secondi)", 1, 300, 3, 1,
                                help="Default 3 sec — è quello che Gaia usa in App4.3.")
    min_run_s = st.number_input("Durata minima superamento (sec)", 0, 60, 0, 1,
                                help="Un superamento viene contato solo se dura almeno "
                                     "questo numero di secondi consecutivi. "
                                     "Default 0 = nessun filtro. Alza a 3 per filtrare spike brevi.")

    st.subheader("Soglie W/kg")
    modo_soglie = st.radio(
        "Come definire le soglie",
        ["Range (default 3.5→8, step 0.5)", "Custom"],
        index=0,
    )
    if modo_soglie.startswith("Range"):
        c1, c2, c3 = st.columns(3)
        s_min = c1.number_input("Min", 1.0, 10.0, 3.5, 0.5)
        s_max = c2.number_input("Max", 1.0, 15.0, 8.0, 0.5)
        s_step = c3.number_input("Step", 0.1, 1.0, 0.5, 0.1)
        soglie = [round(x, 2) for x in
                  __import__("numpy").arange(s_min, s_max + 0.0001, s_step).tolist()]
    else:
        soglie_str = st.text_input("Soglie separate da virgola", "3.5,4,4.5,5,5.5,6,6.5,7,7.5,8")
        soglie = [float(x.strip()) for x in soglie_str.split(",") if x.strip()]

    st.write("Soglie attive:", soglie)

    st.divider()
    st.subheader("Formato coordinate")
    formato_coord = st.radio(
        "I lat/long nei tratti sono in:",
        ["Gradi decimali (es. 45.6789)", "Semicircles (formato .fit)"],
        index=0,
    )
    tol_semi = st.number_input("Tolleranza GPS (semicircles)", 10, 100000, 100, 10,
                               help="La soglia di App4.3 era 100. Aumenta se i tratti non 'agganciano' i record.")

# ────────────────────────── PRESET GARE ──────────────────────────
PRESET_PATH = "presets_gare.json"


@st.cache_data
def load_presets():
    try:
        with open(PRESET_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


presets = load_presets()

# ────────────────────────── METADATA & TRATTI ──────────────────────────
st.header("1. Metadata gara")

c1, c2, c3 = st.columns(3)
gara_default = list(presets.keys())[0] if presets else "Milano-Sanremo"
gara_names = list(presets.keys()) + ["-- Nuova gara --"]
gara_sel = c1.selectbox("Gara", gara_names, index=0)
if gara_sel == "-- Nuova gara --":
    gara = c1.text_input("Nome nuova gara")
else:
    gara = gara_sel
anno = c2.number_input("Anno", 2000, 2030, 2025, 1)
corridore_default = c3.text_input("Corridore (fallback)", "Corridore1",
                                  help="Usato se il nome file non finisce con '__nomecorridore.fit'")

st.header("2. Tratti (4 per gara)")

# recupera tratti dal preset selezionato
preset_tratti = presets.get(gara_sel, {}).get("tratti", []) if gara_sel in presets else []

tratti = []
tabs = st.tabs([f"Tratto {i+1}" for i in range(4)])
for i, tab in enumerate(tabs):
    with tab:
        default = preset_tratti[i] if i < len(preset_tratti) else {}
        nome = st.text_input(f"Nome tratto {i+1}", default.get("nome", f"Tratto {i+1}"), key=f"n{i}")
        cc = st.columns(4)
        lat_s = cc[0].number_input(f"lat start", value=float(default.get("lat_start", 0.0)),
                                   format="%.6f", key=f"la1{i}")
        lat_e = cc[1].number_input(f"lat end", value=float(default.get("lat_end", 0.0)),
                                   format="%.6f", key=f"la2{i}")
        lon_s = cc[2].number_input(f"long start", value=float(default.get("long_start", 0.0)),
                                   format="%.6f", key=f"lo1{i}")
        lon_e = cc[3].number_input(f"long end", value=float(default.get("long_end", 0.0)),
                                   format="%.6f", key=f"lo2{i}")

        if formato_coord.startswith("Gradi"):
            la_s, la_e = deg_to_semi(lat_s), deg_to_semi(lat_e)
            lo_s, lo_e = deg_to_semi(lon_s), deg_to_semi(lon_e)
        else:
            la_s, la_e = int(lat_s), int(lat_e)
            lo_s, lo_e = int(lon_s), int(lon_e)

        # Se più tratti hanno le stesse coordinate, li interpretiamo come
        # passaggi/lap successivi sulla stessa porzione di percorso.
        same_before = sum(
            1 for prev in tratti
            if (
                prev.lat_start == la_s
                and prev.lat_end == la_e
                and prev.long_start == lo_s
                and prev.long_end == lo_e
            )
        )
        passaggio = same_before + 1

        tratti.append(Tratto(
            nome=nome, lat_start=la_s, lat_end=la_e,
            long_start=lo_s, long_end=lo_e, gps_tolerance=int(tol_semi),
            passaggio=passaggio,
        ))

# ────────────────────────── UPLOAD & ANALISI ──────────────────────────
st.header("3. Upload file .fit")
st.caption("Puoi caricare più file insieme. Nome file consigliato: `qualsiasi__Cognome.fit` "
           "(il pezzo dopo `__` diventa il nome del corridore).")

uploads = st.file_uploader("Trascina qui i file .fit", type=["fit"], accept_multiple_files=True)

# ────────────────────────── ANTEPRIMA MAPPA TRATTI ──────────────────────────

if uploads:

    with st.expander("🗺️ Anteprima mappa tratti (verifica coordinate)", expanded=False):

        st.caption(

            "Mostra il percorso completo della gara (blu) e, per ogni tratto, "

            "la porzione di percorso compresa tra il punto GPS START e il punto GPS END "

            "inseriti. Il programma aggancia i punti del file .fit più coerenti con le "

            "coordinate impostate e segue il percorso nell'ordine temporale START → END."

        )

        file_names = [u.name for u in uploads]

        sel_idx = st.selectbox(

            "File da visualizzare",

            range(len(uploads)),

            format_func=lambda i: file_names[i],

            key="map_file_sel",

        )

        sel_bytes = uploads[sel_idx].getvalue()

        try:

            route_df = extract_route(sel_bytes)

        except Exception as e:

            st.error(f"Errore lettura .fit: {e}")

            route_df = None

        if route_df is None or route_df.empty:

            st.warning("Nessun dato GPS nel file selezionato.")

        else:

            # Subsample se troppo denso

            route_plot = route_df

            if len(route_plot) > 8000:

                step = len(route_plot) // 8000 + 1

                route_plot = route_plot.iloc[::step].reset_index(drop=True)

            import folium

            from streamlit_folium import st_folium

            center = [

                route_plot["lat_deg"].mean(),

                route_plot["lon_deg"].mean()

            ]

            fmap = folium.Map(

                location=center,

                zoom_start=10,

                tiles="OpenStreetMap"

            )

            # Percorso completo in blu

            folium.PolyLine(

                route_plot[["lat_deg", "lon_deg"]].values.tolist(),

                color="#1f77ff",

                weight=3,

                opacity=0.7,

                tooltip="Percorso gara",

            ).add_to(fmap)

            colori_tratti = [

                "#e6194B",

                "#f58231",

                "#3cb44b",

                "#911eb4"

            ]

            for i, t in enumerate(tratti):

                col = colori_tratti[i % len(colori_tratti)]

                matched = points_in_tratto(route_df, t)

                if not matched.empty:

                    matched_plot = matched

                    if len(matched_plot) > 3000:

                        step = len(matched_plot) // 3000 + 1

                        matched_plot = matched_plot.iloc[::step].reset_index(drop=True)

                    folium.PolyLine(

                        matched_plot[["lat_deg", "lon_deg"]].values.tolist(),

                        color=col,

                        weight=7,

                        opacity=0.9,

                        tooltip=f"{t.nome} — passaggio {t.passaggio} — {len(matched)} campioni START → END",

                    ).add_to(fmap)

                # Cerchietti sui GPS inseriti dall'utente

                lat_s_deg = semi_to_deg(t.lat_start)

                lon_s_deg = semi_to_deg(t.long_start)

                lat_e_deg = semi_to_deg(t.lat_end)

                lon_e_deg = semi_to_deg(t.long_end)

                if lat_s_deg or lon_s_deg:

                    folium.CircleMarker(

                        [lat_s_deg, lon_s_deg],

                        radius=9,

                        color=col,

                        weight=3,

                        fill=True,

                        fill_color="white",

                        fill_opacity=0.9,

                        tooltip=(

                            f"{t.nome} — START "

                            f"({lat_s_deg:.5f}, {lon_s_deg:.5f})"

                        ),

                    ).add_to(fmap)

                if lat_e_deg or lon_e_deg:

                    folium.CircleMarker(

                        [lat_e_deg, lon_e_deg],

                        radius=9,

                        color=col,

                        weight=3,

                        fill=True,

                        fill_color="black",

                        fill_opacity=0.9,

                        tooltip=(

                            f"{t.nome} — END "

                            f"({lat_e_deg:.5f}, {lon_e_deg:.5f})"

                        ),

                    ).add_to(fmap)

            # Legenda

            legenda = " · ".join(

                [

                    f"<span style='color:{colori_tratti[i % len(colori_tratti)]}'>■</span> {t.nome}"

                    for i, t in enumerate(tratti)

                ]

            )

            st.markdown(

                f"<small>🔵 percorso gara · {legenda} · ⚪ start · ⚫ end</small>",

                unsafe_allow_html=True,

            )

            st_folium(

                fmap,

                height=550,

                use_container_width=True,

                returned_objects=[]

            )

            # Riepilogo aggancio START → END

            riepilogo = []

            for t in tratti:

                n = len(points_in_tratto(route_df, t))

                matched = points_in_tratto(route_df, t)
                if not matched.empty:
                    ora_start = matched["timestamp"].iloc[0].strftime("%H:%M:%S")
                    ora_end = matched["timestamp"].iloc[-1].strftime("%H:%M:%S")
                else:
                    ora_start = "—"
                    ora_end = "—"

                riepilogo.append({

                    "tratto": t.nome,

                    "passaggio/lap": t.passaggio,

                    "campioni nel tratto": n,

                    "inizio": ora_start,

                    "fine": ora_end,

                    "stato": "✅" if n > 0 else "⚠️ passaggio non trovato",

                })

            st.dataframe(

                pd.DataFrame(riepilogo),

                use_container_width=True,

                hide_index=True

            )

if st.button("🚀 Analizza tutto", type="primary", disabled=not uploads):
    all_dfs = []
    prog = st.progress(0, text="Analisi in corso…")
    for i, up in enumerate(uploads, start=1):
        # inferisci nome corridore da filename: `qualsiasi__Cognome.fit`
        stem = up.name.rsplit(".", 1)[0]
        if "__" in stem:
            corridore_name = stem.split("__", 1)[1]
        else:
            corridore_name = corridore_default

        try:
            df = analyze_fit(
                fit_bytes=up.getvalue(),
                corridore=corridore_name,
                gara=gara or "N/A",
                anno=int(anno),
                peso_kg=float(peso_kg),
                tratti=tratti,
                soglie_wkg=soglie,
                rolling_window_s=int(rolling_s),
                min_run_seconds=int(min_run_s),
            )
            if df.empty:
                st.warning(f"⚠️ {up.name}: nessun record valido nel file.")
            else:
                all_dfs.append(df)
                st.success(f"✅ {up.name} → {corridore_name} ({len(df)} righe)")
        except Exception as e:
            st.error(f"❌ {up.name}: {e}")
        prog.progress(i / len(uploads), text=f"{i}/{len(uploads)}")

    if all_dfs:
        master = pd.concat(all_dfs, ignore_index=True)
        st.session_state["master"] = master

        # auto-save in archivio (una entry per corridore per analisi)
        if st.session_state.get("auto_save") and storage.is_enabled():
            saved = 0
            for cor, sub in master.groupby("corridore"):
                try:
                    storage.save_analisi(cor, sub, note=f"upload {datetime.now():%Y-%m-%d %H:%M}")
                    saved += 1
                except Exception as e:
                    st.warning(f"❌ archivio '{cor}': {e}")
            if saved:
                st.success(f"💾 Salvato in archivio: {saved} corridore/i")

if "master" in st.session_state:
    st.header("4. Risultati")
    df = st.session_state["master"]
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ───────── GRAFICI ─────────
    st.header("5. Grafici")
    tab_g1, tab_g2, tab_g3, tab_g4 = st.tabs([
        "Superamenti per soglia",
        "Secondi sopra soglia",
        "Confronto corridori",
        "Confronto tratti",
    ])

    with tab_g1:
        st.caption("Numero di superamenti soglia per ogni tratto, al variare della soglia W/kg.")
        # una serie per tratto, per corridore selezionato
        c1, c2 = st.columns(2)
        cor_sel = c1.selectbox("Corridore", sorted(df["corridore"].unique()), key="g1_cor")
        gara_sel_g = c2.selectbox("Gara-Anno", sorted(df.assign(g=df["gara"]+" "+df["anno"].astype(str))["g"].unique()), key="g1_g")
        gara_name, anno_name = gara_sel_g.rsplit(" ", 1)
        sub = df[(df["corridore"] == cor_sel) & (df["gara"] == gara_name) & (df["anno"] == int(anno_name))]
        if not sub.empty:
            pivot = sub.pivot_table(index="soglia_wkg", columns="tratto", values="n_superamenti", aggfunc="sum")
            st.line_chart(pivot, height=400)
            st.bar_chart(pivot, height=400)
        else:
            st.info("Nessun dato per la selezione.")

    with tab_g2:
        st.caption("Secondi totali sopra soglia per tratto.")
        c1, c2 = st.columns(2)
        cor_sel2 = c1.selectbox("Corridore", sorted(df["corridore"].unique()), key="g2_cor")
        gara_sel2 = c2.selectbox("Gara-Anno", sorted(df.assign(g=df["gara"]+" "+df["anno"].astype(str))["g"].unique()), key="g2_g")
        gara_name2, anno_name2 = gara_sel2.rsplit(" ", 1)
        sub2 = df[(df["corridore"] == cor_sel2) & (df["gara"] == gara_name2) & (df["anno"] == int(anno_name2))]
        if not sub2.empty:
            pivot2 = sub2.pivot_table(index="soglia_wkg", columns="tratto", values="secondi_sopra", aggfunc="sum")
            st.area_chart(pivot2, height=400)
        else:
            st.info("Nessun dato per la selezione.")

    with tab_g3:
        st.caption("Confronto tra corridori sulla stessa soglia W/kg.")
        c1, c2 = st.columns(2)
        soglia_sel = c1.selectbox("Soglia W/kg", sorted(df["soglia_wkg"].unique()), key="g3_s")
        metrica = c2.selectbox("Metrica", ["n_superamenti", "secondi_sopra", "media_wkg"], key="g3_m")
        sub3 = df[df["soglia_wkg"] == soglia_sel]
        if not sub3.empty:
            pivot3 = sub3.pivot_table(index="corridore", columns="tratto", values=metrica, aggfunc="sum")
            st.bar_chart(pivot3, height=400)
            st.dataframe(pivot3, use_container_width=True)
        else:
            st.info("Nessun dato per la selezione.")

    with tab_g4:
        st.caption("Confronto tra tratti (media dei corridori) per soglia.")
        metrica2 = st.selectbox("Metrica", ["n_superamenti", "secondi_sopra", "media_wkg"], key="g4_m")
        pivot4 = df.pivot_table(index="soglia_wkg", columns="tratto", values=metrica2, aggfunc="mean")
        st.line_chart(pivot4, height=400)
        st.dataframe(pivot4.round(2), use_container_width=True)

    # download CSV + Excel
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Scarica CSV",
        csv,
        file_name=f"analisi_{datetime.now():%Y%m%d_%H%M}.csv",
        mime="text/csv",
    )

    # Excel con una sheet per corridore-gara-anno + master
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="master", index=False)
        for (cor, ga, an), sub in df.groupby(["corridore", "gara", "anno"]):
            sheet = f"{cor}_{ga}_{an}"[:31]
            sub.to_excel(writer, sheet_name=sheet, index=False)
    st.download_button(
        "⬇️ Scarica Excel (con sheet per corridore)",
        buf.getvalue(),
        file_name=f"analisi_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ────────────────────────── ARCHIVIO ──────────────────────────
if storage.is_enabled():
    st.divider()
    st.header("📚 Cronologia archivio")
    st.caption("Tutte le analisi salvate. Filtro per corridore, apri per vedere i dati.")
    try:
        corridori = storage.list_corridori()
    except Exception as e:
        st.warning(f"Archivio non raggiungibile: {e}")
        corridori = []

    if not corridori:
        st.info("Archivio vuoto: fai una prima analisi con auto-save attivo.")
    else:
        cor_sel = st.selectbox("Corridore", corridori, key="arch_cor")
        data = storage.load_corridore(cor_sel)
        if data:
            analisi = data.get("analisi", [])
            st.caption(f"**{len(analisi)}** analisi archiviate per **{cor_sel}**")
            for entry in reversed(analisi):
                header = f"{entry.get('gara','?')} {entry.get('anno','?')} — {entry.get('creata_il','')} — id `{entry['id']}`"
                with st.expander(header):
                    df_e = storage.analisi_as_df(entry)
                    st.dataframe(df_e, use_container_width=True, hide_index=True)
                    csv_e = df_e.to_csv(index=False).encode("utf-8")
                    c1, c2 = st.columns([1, 1])
                    c1.download_button("⬇️ Scarica CSV", csv_e,
                                       file_name=f"{cor_sel}_{entry['id']}.csv",
                                       mime="text/csv", key=f"dl_{entry['id']}")
                    if c2.button("🗑️ Elimina", key=f"rm_{entry['id']}"):
                        storage.delete_analisi(cor_sel, entry["id"])
                        st.rerun()

# ────────────────────────── GUIDA ──────────────────────────
st.divider()
with st.expander("📖 Guida di utilizzo (clicca per aprire)", expanded=False):
    try:
        with open("guida.md", encoding="utf-8") as f:
            st.markdown(f.read())
    except FileNotFoundError:
        st.info("Guida non trovata (file guida.md).")

