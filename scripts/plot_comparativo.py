#!/usr/bin/env python3
"""Grafico comparativo agregado entre AODV, OLSR e DSDV em UMA condicao de mobilidade.

Quatro paineis (PDR, vazao, atraso, jitter) com uma barra por protocolo: media das sementes e
barra de erro = intervalo de confianca de 95%. A condicao e escolhida com --speed (padrao 10 m/s).

Uso:
  python3 scripts/plot_comparativo.py --speed 10
Saida: figures/comparativo_<v>ms.png e .pdf
"""
import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

PROTOCOLS = ["AODV", "OLSR", "DSDV"]
COLOR = {"AODV": "#2a78d6", "OLSR": "#eb6834", "DSDV": "#1baf7a"}
PANELS = [("pdr", "PDR (%)", "(a) PDR"), ("throughput_kbps", "Vazão (kbps)", "(b) Vazão"),
          ("avg_delay_ms", "Atraso fim a fim (ms)", "(c) Atraso fim a fim"), ("avg_jitter_ms", "Jitter (ms)", "(d) Jitter")]
INK, INK2, GRID, AXIS = "#0b0b0b", "#52514e", "#e6e5e1", "#b9b8b3"
plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42, "savefig.facecolor": "white"})


def main():
    work = Path("/work")
    ap = argparse.ArgumentParser(description="Comparativo agregado em uma velocidade.")
    ap.add_argument("--speed", type=int, default=10, help="velocidade maxima (m/s) da condicao escolhida")
    ap.add_argument("--csv", default=str(work / "data/resultados.csv") if work.is_dir() else "data/resultados.csv")
    ap.add_argument("--figdir", default=str(work / "figures") if work.is_dir() else "figures")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    offered = float(df[df["protocol"].isin(["AODV", "DSDV"])]["tx_packets"].median())
    df["pdr"] = 100.0 * df["rx_packets"] / offered
    sub = df[df["max_speed_mps"] == args.speed]
    if sub.empty:
        sys.exit(f"ERRO: nao ha simulacoes com velocidade maxima {args.speed} m/s em {args.csv}.")

    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.0))
    for ax, (col, ylabel, title) in zip(axes.flat, PANELS):
        means, errs = [], []
        for p in PROTOCOLS:
            x = sub[sub["protocol"] == p][col]
            n = len(x)
            means.append(x.mean())
            errs.append(stats.t.ppf(0.975, n - 1) * x.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0)
        ax.bar(PROTOCOLS, means, yerr=errs, color=[COLOR[p] for p in PROTOCOLS], width=0.6,
               capsize=4, error_kw=dict(elinewidth=1.2, ecolor=INK2), zorder=3)
        for i, (m, e) in enumerate(zip(means, errs)):
            ax.text(i, m + e + 0.02 * max(means), f"{m:.1f}", ha="center", va="bottom", fontsize=8, color=INK)
        ax.set_title(title, loc="left", fontsize=9, color=INK)
        ax.set_ylabel(ylabel, color=INK2, fontsize=8.5)
        ax.set_ylim(0, max(m + e for m, e in zip(means, errs)) * 1.18)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(AXIS)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(colors=INK2, labelsize=8, length=3, color=AXIS)
    fig.suptitle(f"Comparativo entre protocolos com velocidade máxima de {args.speed} m/s "
                 f"(média de {sub['seed'].nunique()} sementes, IC 95%)", fontsize=9.5, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    figdir = Path(args.figdir)
    figdir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(figdir / f"comparativo_{args.speed}ms.{ext}", dpi=300, bbox_inches="tight")
    print(f"Gravado em {figdir}/comparativo_{args.speed}ms.(png|pdf)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
