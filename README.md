# FIT Analyzer - Tesi Gaia

Web app che sostituisce App4.3 di Gaia: carica file `.fit`, calcola in un colpo
tutte le soglie W/kg (3.5→8, step 0.5) per tutti i 4 tratti di ogni gara,
esporta un Excel pronto per la tesi + grafici.

## Login

L'app supporta login opzionale via `st.secrets`. Se non ci sono secrets
configurati, l'app è aperta a tutti (utile per test locale).

Per attivarlo su Streamlit Cloud → **App settings → Secrets** e incolla:

```toml
[users]
"Gaia.pagotto" = "schifidol2026!"
```

Aggiungi altri utenti nella stessa sezione se serve.

## Quick start (locale)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Streamlit Community Cloud: <https://share.streamlit.io> → New app → repo GitHub → `app.py`.

⚠️ Al deploy setta **App visibility: Public** altrimenti richiede login Streamlit
per accedere (indipendente dal login utente dell'app).

## Struttura

- `app.py` — UI Streamlit + login + grafici
- `analyzer.py` — logica core (refactor di App4.3)
- `presets_gare.json` — coordinate dei 4 tratti per le 5 monumento
- `requirements.txt`
