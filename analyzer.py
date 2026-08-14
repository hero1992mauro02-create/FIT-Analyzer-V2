"""
Analyzer core - refactor di App4.3.
Legge un file .fit, calcola in UN colpo tutte le soglie W/kg per tutti i tratti.

Uso:
    from analyzer import analyze_fit
    df = analyze_fit(fit_bytes, corridore="Pogacar", gara="Sanremo", anno=2025,
                     peso_kg=66, tratti=[...], soglie_wkg=[3.5, 4.0, ..., 8.0])
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from fitparse import FitFile


@dataclass
class Tratto:
    nome: str
    lat_start: float
    lat_end: float
    long_start: float
    long_end: float
    gps_tolerance: int = 100  # semicircles
    passaggio: int = 1  # 1=primo passaggio, 2=secondo, ecc. per circuiti/lap


SEMI_PER_DEG = 2**31 / 180.0


def deg_to_semi(deg: float) -> int:
    return int(round(deg * SEMI_PER_DEG))


def semi_to_deg(semi: int | float) -> float:
    return float(semi) / SEMI_PER_DEG


def _nearest_point_index(
    df: pd.DataFrame,
    lat_target: float,
    lon_target: float
) -> int | None:
    """
    Trova l'indice del record GPS più vicino alla coordinata target.
    Coordinate target e FIT sono in semicircles.
    """
    gps = df.dropna(subset=["position_lat", "position_long"])

    if gps.empty:
        return None

    dist2 = (
        (gps["position_lat"].astype(float) - float(lat_target)) ** 2
        + (gps["position_long"].astype(float) - float(lon_target)) ** 2
    )

    return int(dist2.idxmin())


def _swap(a, b):
    return (a, b) if a <= b else (b, a)


def _fit_to_records_df(fit_bytes: bytes) -> pd.DataFrame:
    """Estrae i record 'record' del .fit in DataFrame con timestamp/lat/long/power/heart_rate/cadence."""
    fit = FitFile(io.BytesIO(fit_bytes))
    rows = []

    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg.fields}
        rows.append(d)

    df = pd.DataFrame(rows)

    for col in (
        "timestamp",
        "position_lat",
        "position_long",
        "power",
        "heart_rate",
        "cadence",
        "altitude",
        "speed",
        "distance",
    ):
        if col not in df.columns:
            df[col] = np.nan

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)

    return df


def _mark_inside(df: pd.DataFrame, tratto: Tratto) -> pd.Series:
    """
    Vecchio metodo bounding box.
    Rimane nel file per compatibilità, ma l'analisi principale non lo usa più.
    """
    lat_lo, lat_hi = _swap(tratto.lat_start, tratto.lat_end)
    lon_lo, lon_hi = _swap(tratto.long_start, tratto.long_end)
    tol = tratto.gps_tolerance

    lat_ok = df["position_lat"].between(lat_lo - tol, lat_hi + tol)
    lon_ok = df["position_long"].between(lon_lo - tol, lon_hi + tol)

    return lat_ok & lon_ok


def _extract_segment(df: pd.DataFrame, tratto: Tratto) -> pd.DataFrame:
    """
    Estrae il tratto START → END seguendo l'ordine reale del file FIT.

    Nei circuiti, se più tratti hanno le stesse coordinate, ``passaggio``
    permette di selezionare 1°, 2°, 3°, 4° attraversamento della stessa
    coppia START/END senza sovrapporli temporalmente.
    """
    gps = df.dropna(subset=["position_lat", "position_long"]).copy()
    if gps.empty:
        return df.iloc[0:0].copy()

    gps["_dist_start"] = (
        (gps["position_lat"].astype(float) - float(tratto.lat_start)) ** 2
        + (gps["position_long"].astype(float) - float(tratto.long_start)) ** 2
    )
    gps["_dist_end"] = (
        (gps["position_lat"].astype(float) - float(tratto.lat_end)) ** 2
        + (gps["position_long"].astype(float) - float(tratto.long_end)) ** 2
    )

    # Usiamo solo circa l'1% dei punti GPS più vicini alla coordinata.
    # È abbastanza per prendere più campioni dello stesso attraversamento,
    # ma non così tanto da collegare porzioni lontane del circuito.
    n_near = min(200, max(20, int(round(len(gps) * 0.01))))
    raw_start = gps.nsmallest(n_near, "_dist_start").index.tolist()
    raw_end = gps.nsmallest(n_near, "_dist_end").index.tolist()

    def distinct_passes(indices, min_gap=30):
        if not indices:
            return []
        indices = sorted(int(i) for i in indices)
        groups = [[indices[0]]]
        for idx in indices[1:]:
            if idx - groups[-1][-1] <= min_gap:
                groups[-1].append(idx)
            else:
                groups.append([idx])
        return groups

    start_groups = distinct_passes(raw_start)
    end_groups = distinct_passes(raw_end)

    start_candidates = sorted(
        int(gps.loc[group, "_dist_start"].idxmin()) for group in start_groups
    )
    end_candidates = sorted(
        int(gps.loc[group, "_dist_end"].idxmin()) for group in end_groups
    )

    # Un segmento per passaggio START. L'END deve essere prima dello START
    # successivo, così ogni lap rimane indipendente dagli altri.
    segments = []
    for pos, start_idx in enumerate(start_candidates):
        next_start = start_candidates[pos + 1] if pos + 1 < len(start_candidates) else None
        compatible_ends = [
            end_idx for end_idx in end_candidates
            if end_idx > start_idx and (next_start is None or end_idx < next_start)
        ]
        if not compatible_ends:
            continue
        end_idx = min(
            compatible_ends,
            key=lambda idx: (float(gps.loc[idx, "_dist_end"]), idx - start_idx),
        )
        segments.append((start_idx, end_idx))

    segments.sort(key=lambda x: x[0])
    requested = max(1, int(getattr(tratto, "passaggio", 1)))
    if requested > len(segments):
        return df.iloc[0:0].copy()

    start_idx, end_idx = segments[requested - 1]
    return df.loc[start_idx:end_idx].copy()


def analyze_fit(
    fit_bytes: bytes,
    corridore: str,
    gara: str,
    anno: int,
    peso_kg: float,
    tratti: list[Tratto],
    soglie_wkg: Iterable[float],
    rolling_window_s: int = 30,
    min_run_seconds: int = 3,
) -> pd.DataFrame:
    """
    Ritorna un DataFrame con una riga per (tratto, soglia_wkg):
        corridore, gara, anno, tratto, soglia_wkg,
        n_superamenti, secondi_sopra, media_potenza_w, media_wkg,
        durata_tratto_s, campioni_tratto

    min_run_seconds:
        solo i run consecutivi sopra soglia di durata >= min_run_seconds
        vengono contati. Spike più brevi vengono ignorati.
    """
    df = _fit_to_records_df(fit_bytes)

    if df.empty:
        return pd.DataFrame()

    # Rolling mean sui watt (assumendo campionamento standard 1 Hz)
    df["power"] = pd.to_numeric(df["power"], errors="coerce").fillna(0)
    df["power_rolling"] = df["power"].rolling(
        window=rolling_window_s,
        min_periods=1
    ).mean()
    df["wkg_rolling"] = df["power_rolling"] / peso_kg

    soglie = sorted(set(round(float(s), 2) for s in soglie_wkg))
    out_rows = []

    for t in tratti:
        sub = _extract_segment(df, t)

        if sub.empty:
            for s in soglie:
                out_rows.append({
                    "corridore": corridore,
                    "gara": gara,
                    "anno": anno,
                    "tratto": t.nome,
                    "soglia_wkg": s,
                    "n_superamenti": 0,
                    "secondi_sopra": 0,
                    "media_potenza_w": np.nan,
                    "media_wkg": np.nan,
                    "durata_tratto_s": 0,
                    "campioni_tratto": 0,
                })
            continue

        durata_s = (
            sub["timestamp"].iloc[-1] - sub["timestamp"].iloc[0]
        ).total_seconds()

        media_pw = float(sub["power_rolling"].mean())
        media_wkg = media_pw / peso_kg

        wkg = sub["wkg_rolling"].to_numpy()

        for s in soglie:
            over = (wkg > s).astype(int)

            # Trova i run consecutivi sopra soglia
            edges = np.diff(over, prepend=0, append=0)
            starts = np.where(edges == 1)[0]
            ends = np.where(edges == -1)[0]

            run_lengths = ends - starts
            valid = run_lengths >= int(min_run_seconds)

            n_sup = int(valid.sum())
            sec_sopra = int(run_lengths[valid].sum())

            out_rows.append({
                "corridore": corridore,
                "gara": gara,
                "anno": anno,
                "tratto": t.nome,
                "soglia_wkg": s,
                "n_superamenti": n_sup,
                "secondi_sopra": sec_sopra,
                "media_potenza_w": round(media_pw, 1),
                "media_wkg": round(media_wkg, 2),
                "durata_tratto_s": int(durata_s),
                "campioni_tratto": len(sub),
            })

    return pd.DataFrame(out_rows)


def default_soglie() -> list[float]:
    """3.5, 4.0, 4.5, ..., 8.0 W/kg"""
    return [round(x, 2) for x in np.arange(3.5, 8.5, 0.5)]


def extract_route(fit_bytes: bytes) -> pd.DataFrame:
    """
    Estrae il percorso GPS dal .fit.

    Ritorna DataFrame con colonne:
    timestamp, position_lat, position_long (semicircles),
    lat_deg, lon_deg (gradi decimali).
    Solo record con GPS valido.
    """
    df = _fit_to_records_df(fit_bytes)
    df = df.dropna(subset=["position_lat", "position_long"]).copy()

    if df.empty:
        return df

    df["lat_deg"] = df["position_lat"].astype(float) / SEMI_PER_DEG
    df["lon_deg"] = df["position_long"].astype(float) / SEMI_PER_DEG

    return df[
        ["timestamp", "position_lat", "position_long", "lat_deg", "lon_deg"]
    ].reset_index(drop=True)


def points_in_tratto(
    route_df: pd.DataFrame,
    tratto: Tratto
) -> pd.DataFrame:
    """
    Ritorna tutti i record del percorso compresi tra START e END,
    usando la stessa logica dell'analisi principale.
    """
    if route_df.empty:
        return route_df

    return _extract_segment(
        route_df,
        tratto
    ).reset_index(drop=True)


