"""
Storage persistente per l'archivio analisi.
Usa un repo GitHub separato come DB: legge/scrive JSON via REST API.

Config in st.secrets:
    [storage]
    github_token = "gho_..."
    repo         = "martinapasianbot/gaia-analyzer-data"
    branch       = "main"
"""
from __future__ import annotations

import base64
import io
import json
from typing import Optional

import pandas as pd
import requests
import streamlit as st

API = "https://api.github.com"


def _cfg() -> Optional[dict]:
    try:
        s = st.secrets.get("storage", {})
    except Exception:
        s = {}
    if not s.get("github_token") or not s.get("repo"):
        return None
    return {
        "token": s["github_token"],
        "repo": s["repo"],
        "branch": s.get("branch", "main"),
    }


def is_enabled() -> bool:
    return _cfg() is not None


def _headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _slug(name: str) -> str:
    """Normalizza nome corridore per usarlo come filename."""
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip())
    return keep or "senza_nome"


def _path(corridore: str) -> str:
    return f"archivio/{_slug(corridore)}.json"


def _get_file(cfg: dict, path: str) -> tuple[Optional[dict], Optional[str]]:
    """Ritorna (contenuto_json, sha) o (None, None) se il file non esiste."""
    r = requests.get(
        f"{API}/repos/{cfg['repo']}/contents/{path}",
        headers=_headers(cfg),
        params={"ref": cfg["branch"]},
        timeout=15,
    )
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content), data["sha"]


def _put_file(cfg: dict, path: str, content_obj: dict, sha: Optional[str], msg: str) -> None:
    body = {
        "message": msg,
        "content": base64.b64encode(json.dumps(content_obj, indent=2, default=str).encode()).decode(),
        "branch": cfg["branch"],
    }
    if sha:
        body["sha"] = sha
    r = requests.put(
        f"{API}/repos/{cfg['repo']}/contents/{path}",
        headers=_headers(cfg),
        json=body,
        timeout=20,
    )
    r.raise_for_status()


def save_analisi(corridore: str, df_result: pd.DataFrame, note: str = "") -> str:
    """
    Aggiunge una nuova analisi all'archivio del corridore.
    Ogni analisi è identificata da timestamp + gara + anno.
    Ritorna id dell'analisi.
    """
    cfg = _cfg()
    if not cfg:
        raise RuntimeError("Storage non configurato (mancano secrets 'storage').")
    path = _path(corridore)
    existing, sha = _get_file(cfg, path)
    if existing is None:
        existing = {"corridore": corridore, "analisi": []}

    from datetime import datetime
    analisi_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    entry = {
        "id": analisi_id,
        "creata_il": datetime.now().isoformat(timespec="seconds"),
        "note": note,
        "gara": df_result["gara"].iloc[0] if len(df_result) else None,
        "anno": int(df_result["anno"].iloc[0]) if len(df_result) else None,
        "righe": df_result.to_dict(orient="records"),
    }
    existing["analisi"].append(entry)
    _put_file(cfg, path, existing, sha, f"analisi {corridore} {analisi_id}")
    return analisi_id


def list_corridori() -> list[str]:
    cfg = _cfg()
    if not cfg:
        return []
    r = requests.get(
        f"{API}/repos/{cfg['repo']}/contents/archivio",
        headers=_headers(cfg),
        params={"ref": cfg["branch"]},
        timeout=15,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    out = []
    for f in r.json():
        if f["name"].endswith(".json"):
            out.append(f["name"].removesuffix(".json"))
    return sorted(out)


def load_corridore(corridore: str) -> Optional[dict]:
    cfg = _cfg()
    if not cfg:
        return None
    data, _ = _get_file(cfg, _path(corridore))
    return data


def delete_analisi(corridore: str, analisi_id: str) -> None:
    cfg = _cfg()
    if not cfg:
        return
    path = _path(corridore)
    data, sha = _get_file(cfg, path)
    if data is None:
        return
    data["analisi"] = [a for a in data.get("analisi", []) if a.get("id") != analisi_id]
    _put_file(cfg, path, data, sha, f"rimossa analisi {analisi_id}")


def analisi_as_df(entry: dict) -> pd.DataFrame:
    return pd.DataFrame(entry.get("righe", []))
