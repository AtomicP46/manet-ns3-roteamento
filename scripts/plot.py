#!/usr/bin/env python3
"""Gera o resumo estatistico e os graficos a partir de data/resultados.csv.

Dentro do container (precisa de python3-pandas, python3-matplotlib e python3-scipy):
  python3 /work/scripts/plot.py

Saidas:
  data/resumo.csv                      media e IC 95% por protocolo e velocidade
  figures/pdr, vazao, atraso, jitter   um grafico por metrica (.png e .pdf)
  figures/resumo_2x2                   as quatro metricas numa figura so (.png e .pdf)

Como cada metrica e calculada
  PDR (%)   = pacotes recebidos / pacotes oferecidos * 100.
              "Oferecidos" e uma constante do cenario (10 fontes x 4 pacotes/s ate 200 s),
              estimada como a mediana de tx_packets de AODV e DSDV. NAO usamos o tx_packets
              do FlowMonitor de cada simulacao: no OLSR, pacotes sem rota sao descartados no
              socket, antes da camada IP, e nunca chegam a ser contados como enviados, o que
              inflaria o PDR. Use --offered N para fixar o valor manualmente.
  Vazao, atraso e jitter dependem so de pacotes recebidos, entao vem direto do CSV.
  IC 95% = media +/- t(0,975; n-1) * desvio padrao / raiz(n), sobre as sementes.
"""
import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from scipy import stats  # noqa: E402

PROTOCOLS = ["AODV", "OLSR", "DSDV"]
# Cor fixa por protocolo (3 primeiros slots de uma paleta validada para daltonismo) e marcador
# proprio: a identidade nao depende so da cor (importante para impressao em preto e branco).
STYLE = {
    "AODV": dict(color="#2a78d6", marker="o"),
    "OLSR": dict(color="#eb6834", marker="s"),
    "DSDV": dict(color="#1baf7a", marker="^"),
}
DODGE = {"AODV": -0.3, "OLSR": 0.0, "DSDV": 0.3}  # desloca levemente no eixo x p/ nao sobrepor

# (coluna, rotulo do eixo, nome do arquivo, titulo no painel 2x2, limite inferior/superior do y)
METRICS = [
    ("pdr", "PDR (%)", "pdr", "(a) PDR", (0, 100)),
    ("throughput_kbps", "Vazão (kbps)", "vazao", "(b) Vazão", (0, None)),
    ("avg_delay_ms", "Atraso fim a fim (ms)", "atraso", "(c) Atraso fim a fim", (0, None)),
    ("avg_jitter_ms", "Jitter (ms)", "jitter", "(d) Jitter", (0, None)),
]
XLABEL = "Velocidade máxima dos nós (m/s)"

INK, INK2 = "#0b0b0b", "#52514e"
GRID, AXIS = "#e6e5e1", "#b9b8b3"

plt.rcParams.update({
    "font.size": 9,
    "pdf.fonttype": 42,  # fontes embutidas (evita problemas no LaTeX/SBC)
    "savefig.facecolor": "white",
})


def offered_packets(df, override):
    if override:
        return float(override)
    ref = df[df["protocol"].isin(["AODV", "DSDV"])]["tx_packets"]
    if ref.empty:
        sys.exit("ERRO: sem linhas de AODV/DSDV para estimar os pacotes oferecidos; use --offered.")
    return float(ref.median())


def summarize(df, col):
    g = df.groupby(["protocol", "max_speed_mps"])[col]
    out = g.agg(n="count", mean="mean", std="std").reset_index()
    tcrit = stats.t.ppf(0.975, out["n"] - 1)
    out["ci95"] = tcrit * out["std"] / np.sqrt(out["n"])
    return out


def style_axes(ax):
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.grid(axis="y", color=GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=8, length=3, color=AXIS)


def draw_metric(ax, summ, ylabel, ylim, speeds):
    for proto in PROTOCOLS:
        s = summ[summ["protocol"] == proto].sort_values("max_speed_mps")
        if s.empty:
            continue
        ax.errorbar(
            s["max_speed_mps"] + DODGE[proto], s["mean"], yerr=s["ci95"].fillna(0),
            label=proto, linewidth=2, markersize=7, markeredgecolor="white",
            markeredgewidth=1.2, capsize=3, elinewidth=1.2, zorder=3, **STYLE[proto],
        )
    style_axes(ax)
    ax.set_xticks(speeds)
    ax.set_xlabel(XLABEL, color=INK2, fontsize=8.5)
    ax.set_ylabel(ylabel, color=INK2, fontsize=8.5)
    ax.set_ylim(*ylim)


def legend_handles():
    """Chaves da legenda so com linha e marcador (sem as hastes das barras de erro)."""
    return [Line2D([0], [0], label=p, linewidth=2, markersize=7, markeredgecolor="white",
                   markeredgewidth=1.2, **STYLE[p]) for p in PROTOCOLS]


def save(fig, base):
    for ext in ("png", "pdf"):
        fig.savefig(f"{base}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    work = Path("/work")
    ap = argparse.ArgumentParser(description="Resumo estatistico e graficos do experimento MANET.")
    ap.add_argument("--csv", default=str(work / "data/resultados.csv") if work.is_dir()
                    else "data/resultados.csv")
    ap.add_argument("--figdir", default=str(work / "figures") if work.is_dir() else "figures")
    ap.add_argument("--summary", default=str(work / "data/resumo.csv") if work.is_dir()
                    else "data/resumo.csv")
    ap.add_argument("--offered", type=float, default=None,
                    help="pacotes oferecidos por simulacao (padrao: estimado dos dados)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    need = {"protocol", "max_speed_mps", "seed", "tx_packets", "rx_packets", "throughput_kbps",
            "avg_delay_ms", "avg_jitter_ms"}
    if not need <= set(df.columns):
        sys.exit(f"ERRO: faltam colunas no CSV: {sorted(need - set(df.columns))}")

    offered = offered_packets(df, args.offered)
    df["pdr"] = 100.0 * df["rx_packets"] / offered
    print(f"{len(df)} simulacoes lidas de {args.csv}")
    print(f"Pacotes oferecidos por simulacao: {offered:.0f}"
          + (" (informado)" if args.offered else " (mediana de tx_packets de AODV e DSDV)"))

    counts = df.groupby(["protocol", "max_speed_mps"]).size()
    if counts.nunique() != 1:
        print("AVISO: numero de repeticoes diferente entre as combinacoes:\n" + counts.to_string())
    if "data_flows" in df.columns:
        few = df[df["data_flows"] < 10].groupby("protocol").size()
        if not few.empty:
            print("Simulacoes em que alguma fonte nunca enviou nada (fluxos de dados < 10):",
                  few.to_dict())

    speeds = sorted(df["max_speed_mps"].unique())
    summaries = {}
    for col, *_ in METRICS:
        summaries[col] = summarize(df, col)
    if "pdr_percent" in df.columns:  # PDR "ingenuo" do FlowMonitor, so para comparacao
        df["pdr_flowmonitor"] = df["pdr_percent"]
        summaries["pdr_flowmonitor"] = summarize(df, "pdr_flowmonitor")

    # ---- resumo.csv (formato largo) ----
    base = summaries["pdr"][["protocol", "max_speed_mps", "n"]].copy()
    for name, s in summaries.items():
        base = base.merge(
            s[["protocol", "max_speed_mps", "mean", "ci95"]].rename(
                columns={"mean": f"{name}_mean", "ci95": f"{name}_ci95"}),
            on=["protocol", "max_speed_mps"])
    base["_o"] = base["protocol"].map({p: i for i, p in enumerate(PROTOCOLS)})
    base = base.sort_values(["_o", "max_speed_mps"]).drop(columns="_o").round(4)
    Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(args.summary, index=False)
    print(f"Resumo gravado em {args.summary}")

    # ---- um grafico por metrica ----
    figdir = Path(args.figdir)
    figdir.mkdir(parents=True, exist_ok=True)
    for col, ylabel, fname, _title, ylim in METRICS:
        fig, ax = plt.subplots(figsize=(3.4, 2.6))
        draw_metric(ax, summaries[col], ylabel, ylim, speeds)
        ax.legend(handles=legend_handles(), frameon=False, fontsize=8, labelcolor=INK, loc="best")
        save(fig, figdir / fname)

    # ---- as quatro metricas numa figura so (2 x 2, largura de pagina) ----
    fig, axes = plt.subplots(2, 2, figsize=(7.0, 5.0))
    for ax, (col, ylabel, _f, title, ylim) in zip(axes.flat, METRICS):
        draw_metric(ax, summaries[col], ylabel, ylim, speeds)
        ax.set_title(title, loc="left", fontsize=9, color=INK)
    fig.legend(handles=legend_handles(), loc="upper center", ncol=3, frameon=False, fontsize=9,
               labelcolor=INK, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    save(fig, figdir / "resumo_2x2")
    print(f"Graficos gravados em {figdir}/ (pdr, vazao, atraso, jitter e resumo_2x2; .png e .pdf)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
