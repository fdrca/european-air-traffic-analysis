"""Confronta le frequenze del dataset (scraping FlightsFrom) con i voli ufficiali Eurostat.

Uso:
    python scripts/validazione_eurostat.py CARTELLA_TSV [data/europe_air_routes.csv] [data/eurostat_validazione_rotte.csv]

CARTELLA_TSV contiene le tabelle Eurostat `avia_par_XX` (una per paese dichiarante, formato TSV scaricato dal Data Browser:
"Air passenger transport routes between partner airports and main airports in ..."). Sono molto pesanti (circa 800 MB in totale),
per questo nel repository c'è solo il risultato (`data/eurostat_validazione_rotte.csv`), non le tabelle originali.

Per ogni rotta A->B del dataset che compare anche in Eurostat salva: voli 2024 (misura CAF_PAS), voli di agosto 2024, passeggeri 2024 (PAS_CRD).
Il codice dell'aeroporto è l'ICAO, presente in entrambe le fonti. La direzione A->B è presa dalle righe "DEP" del paese di A;
se mancano, dalle righe "ARR" del paese di B.
"""
import sys, glob
from pathlib import Path
import pandas as pd

src = Path(sys.argv[1])
raw_csv = sys.argv[2] if len(sys.argv) > 2 else "data/europe_air_routes.csv"
out_csv = sys.argv[3] if len(sys.argv) > 3 else "data/eurostat_validazione_rotte.csv"
KEEP = {"CAF_PAS_DEP", "CAF_PAS_ARR", "PAS_CRD_DEP", "PAS_CRD_ARR"}   # voli e passeggeri trasportati, per direzione

parts = []
for f in sorted(glob.glob(str(src / "*avia_par_*.tsv"))):
    cc = f[-6:-4]
    hdr = [c.strip() for c in open(f, encoding="utf-8").readline().rstrip("\r\n").split("\t")]
    # il Regno Unito non è più paese dichiarante dopo il 2019: i suoi aeroporti compaiono solo come partner negli altri file
    want = [hdr[0]] + [p for p in ("2024", "2024-08") if p in hdr]
    if len(want) == 1: continue
    d = pd.read_csv(f, sep="\t", dtype=str, usecols=lambda c: c.strip() in want)
    d.columns = [c.strip() for c in d.columns]
    k = d.columns[0]
    p = d[k].str.split(",", expand=True); p.columns = ["freq", "unit", "tra_meas", "airp_pr"]
    d = pd.concat([p, d.drop(columns=k)], axis=1)
    d = d[d.tra_meas.isin(KEEP) & d.freq.isin(["A", "M"])]
    for c in [c for c in d.columns if c[:4] == "2024"]:
        d[c] = pd.to_numeric(d[c].str.extract(r"^\s*([\d\.]+)")[0], errors="coerce")   # ": " = dato non disponibile, "e" = stima
    parts.append(d)
es = pd.concat(parts, ignore_index=True)
s = es.airp_pr.str.split("_", expand=True)
es["rep"], es["par"] = s[1], s[3]
es["dir"] = es.tra_meas.str[-3:]
es["misura"] = es.tra_meas.str[:-4]
es["o"] = es.rep.where(es.dir == "DEP", es.par)
es["d"] = es.par.where(es.dir == "DEP", es.rep)

def tab(misura, freq, col):
    t = es[(es.misura == misura) & (es.freq == freq)][["o", "d", col, "dir"]].dropna(subset=[col])
    return t.sort_values("dir").drop_duplicates(["o", "d"], keep="last").set_index(["o", "d"])[col]   # DEP prevale su ARR

raw = pd.read_csv(raw_csv, usecols=["iata_from", "iata_to", "flights_per_week", "departure_ICAO", "arrival_ICAO", "departure_country"])
NON_EUROPE = {"Kazakhstan", "Armenia", "Azerbaijan", "Georgia"}
eu = set(raw.loc[~raw.departure_country.isin(NON_EUROPE), "iata_from"])
raw = raw[raw.iata_from.isin(eu) & raw.iata_to.isin(eu)].rename(columns={"departure_ICAO": "o", "arrival_ICAO": "d"})
raw = raw.drop_duplicates(["o", "d"]).set_index(["o", "d"])
out = (raw[["iata_from", "iata_to", "flights_per_week"]]
       .join(tab("CAF_PAS", "A", "2024").rename("voli_eurostat_2024"))
       .join(tab("CAF_PAS", "M", "2024-08").rename("voli_eurostat_ago2024"))
       .join(tab("PAS_CRD", "A", "2024").rename("passeggeri_eurostat_2024")))
out = out[out.voli_eurostat_2024.notna() | out.voli_eurostat_ago2024.notna()].reset_index(drop=True)
out = out.rename(columns={"flights_per_week": "voli_sett_scraping"})
out.to_csv(out_csv, index=False)
print(f"{len(out):,} rotte europee del dataset con riscontro Eurostat -> {out_csv}")
