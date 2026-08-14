# 📖 Guida FIT Analyzer

Web app per l'analisi delle soglie W/kg sui file `.fit` — sostituisce App4.3.

---

## Accesso

- Link: **https://gaia-fit-analyzer.streamlit.app**
- Login: nome utente e password che ti sono stati assegnati
- Funziona da qualsiasi browser (PC, Mac, telefono, tablet). Non serve installare nulla.

---

## Come si usa in 5 passi

### 1. Parametri globali (sidebar sinistra)

Setta una volta e valgono per tutti i file che caricherai:

- **Peso corridore (kg)** — il peso dell'atleta (usato per calcolare W/kg)
- **Media mobile (secondi)** — la finestra della media mobile sui watt. Default `3` (come App4.3)
- **Soglie W/kg** — scegli tra:
  - *Range*: min/max/step. Default `3.5 → 8` step `0.5` (fa tutte le soglie in un colpo)
  - *Custom*: le scrivi tu separate da virgola
- **Formato coordinate**: gradi decimali (es. `45.6789`) o semicircles (formato interno `.fit`)
- **Tolleranza GPS (semicircles)** — default `15` (come App4.3)
- **Durata minima superamento (sec)** — default `0` (comportamento identico ad App4.3, nessun filtro applicato). Se lo alzi a un valore N, sia `n_superamenti` sia `secondi_sopra` considerano solo i run consecutivi di durata >= N secondi. Utile per filtrare spike brevi (default fisiologicamente sensato: 3).

### 2. Metadata gara

- **Gara**: scegli dal menu una delle 5 monumento (Sanremo, Fiandre, Roubaix, Liegi, Lombardia) o "Nuova gara"
- **Anno**
- **Corridore (fallback)**: usato se il file `.fit` non ha il nome del corridore nel filename

### 3. Configura i 4 tratti

Ogni gara è divisa in 4 tratti. Nella scheda `Tratto 1`… `Tratto 4` inserisci per ciascuno:

- Nome (es. "Cipressa", "Poggio")
- Latitudine inizio + fine
- Longitudine inizio + fine

**Se hai scelto una gara preset**, le coordinate vengono già precompilate (placeholder — controllale e correggi se serve).

### 4. Carica i file `.fit`

Trascina uno o più file `.fit` nell'area upload (puoi metterne anche 30 insieme).

**Trucco per il nome del corridore**: se rinomini il file `qualsiasi__CognomeCorridore.fit` (doppio underscore prima del cognome), l'app usa quel nome invece del fallback. Utile per batch di più corridori insieme.

Poi click su **🚀 Analizza tutto**.

### 5. Risultati

Compaiono automaticamente:

- **Tabella** con una riga per (corridore × tratto × soglia): `n_superamenti`, `secondi_sopra`, `media_potenza_w`, `media_wkg`, `durata_tratto_s`, `campioni_tratto`
- **Download CSV** e **Excel** (con una sheet per corridore + master aggregata)
- **4 tab di grafici** (Superamenti per soglia, Secondi sopra, Confronto corridori, Confronto tratti)

---

## 📚 Archivio (permanente)

Se nella sidebar l'archivio è attivo (⚠️ verifica che si legga "**Salva automaticamente…**"), ogni analisi viene **salvata online per sempre** — non si perde chiudendo il browser.

- Ogni corridore ha il suo "file" nell'archivio
- Nella sezione **Cronologia archivio** (in fondo alla pagina) puoi:
  - Scegliere un corridore dal menu → vedi tutte le sue analisi con data e ora
  - Aprire ciascuna analisi → vedi la tabella completa
  - Scaricare il CSV di ogni analisi passata
  - Eliminare un'analisi se serve

L'archivio è indipendente dal browser: entri da un altro PC → trovi tutto.

---

## Differenze rispetto ad App4.3

| App4.3 (vecchia) | FIT Analyzer (nuova) |
|---|---|
| Windows only, exe da installare | Web, qualsiasi dispositivo |
| Una soglia alla volta (crei set × 10 soglie) | Tutte le soglie in un click |
| Un file alla volta | Multi-file (drag&drop N file) |
| Nessun archivio, ricalcoli sempre | Archivio permanente per corridore |
| Solo CSV | CSV + Excel + grafici |
| Nessun grafico | 4 tab di grafici comparativi |
| GUI Tkinter lenta | Interfaccia moderna |

**Cosa NON cambia**: la logica di calcolo è la stessa (rolling W/kg su bounding box GPS, count superamenti + secondi sopra soglia). Stessi input → stessi output.

---

## Domande frequenti

**Posso caricare file di corridori diversi insieme?**
Sì. Rinomina ognuno come `gara2025__Cognome.fit` (doppio underscore) e l'app li smista automaticamente.

**Se sbaglio le coordinate di un tratto?**
Cambi i valori nella scheda del tratto e ri-lanci l'analisi. I risultati vecchi restano in archivio.

**L'app è lenta**
Ogni file `.fit` da 5MB si processa in ~2 secondi. Se hai 30 file, aspetta ~1 minuto.

**Chi vede i miei dati?**
Solo chi ha login e password. L'archivio è privato del progetto.

---

## Problemi? Contatta Mauro
