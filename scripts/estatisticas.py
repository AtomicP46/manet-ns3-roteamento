#!/usr/bin/env python3
"""Estatistica descritiva por configuracao (protocolo x velocidade maxima).

Para cada configuracao e cada metrica calcula: n, media, desvio-padrao (amostral, n-1), minimo,
maximo e intervalo de confianca de 95% (t de Student). Saida: data/estatisticas.csv (formato longo).

Metricas:
  pdr_percent       = rx_packets / pacotes oferecidos * 100
  throughput_mbps   = throughput_kbps / 1000
  avg_delay_ms, avg_jitter_ms
  rx_packets        pacotes recebidos
  lost_packets      = pacotes oferecidos - rx_packets (perdidos)
Pacotes oferecidos = mediana de tx_packets de AODV e DSDV (constante do cenario; ver README:
no OLSR o FlowMonitor nao conta os pacotes descartados antes da camada IP).

Uso (container ou qualquer maquina com python3-pandas e python3-scipy):
  python3 scripts/estatisticas.py                  # le data/resultados.csv
  python3 /work/scripts/estatisticas.py            # dentro do container
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROTOCOLS = ["AODV", "OLSR", "DSDV"]
METRICS = ["pdr_percent", "throughput_mbps", "avg_delay_ms", "avg_jitter_ms", "rx_packets", "lost_packets"]


def main():
    work = Path("/work")
    ap = argparse.ArgumentParser(description="Estatisticas por configuracao.")
    ap.add_argument("--csv", default=str(work / "data/resultados.csv") if work.is_dir() else "data/resultados.csv")
    ap.add_argument("--out", default=str(work / "data/estatisticas.csv") if work.is_dir() else "data/estatisticas.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    ref = df[df["protocol"].isin(["AODV", "DSDV"])]["tx_packets"]
    if ref.empty:
        sys.exit("ERRO: sem linhas de AODV/DSDV para estimar os pacotes oferecidos.")
    offered = float(ref.median())
    df["pdr_percent"] = 100.0 * df["rx_packets"] / offered
    df["throughput_mbps"] = df["throughput_kbps"] / 1000.0
    df["lost_packets"] = offered - df["rx_packets"]

    rows = []
    for (proto, speed), g in df.groupby(["protocol", "max_speed_mps"]):
        for m in METRICS:
            x = g[m].dropna()
            n = len(x)
            std = x.std(ddof=1) if n > 1 else float("nan")
            ci = stats.t.ppf(0.975, n - 1) * std / np.sqrt(n) if n > 1 else float("nan")
            rows.append({"protocol": proto, "max_speed_mps": speed, "metric": m, "n": n,
                         "mean": x.mean(), "std": std, "min": x.min(), "max": x.max(), "ci95": ci})
    out = pd.DataFrame(rows)
    out["_o"] = out["protocol"].map({p: i for i, p in enumerate(PROTOCOLS)})
    out = out.sort_values(["_o", "max_speed_mps", "metric"]).drop(columns="_o").round(6)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"{len(df)} simulacoes lidas de {args.csv}; pacotes oferecidos por simulacao: {offered:.0f}")
    print(f"{len(out)} linhas gravadas em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
