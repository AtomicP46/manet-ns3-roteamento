#!/usr/bin/env python3
"""Roda as simulacoes do experimento MANET e extrai as metricas do FlowMonitor.

Rodar DENTRO do container, na pasta do ns-3 (ou usar --ns3-dir).

  # teste rapido (1 simulacao, ~35 s):
  python3 /work/scripts/run_experiments.py --protocols AODV --speeds 5 --seeds 1 --out /tmp/smoke.csv

  # experimento completo (3 protocolos x 5 velocidades x 10 sementes = 150 simulacoes):
  python3 /work/scripts/run_experiments.py

  # so calcular as metricas de um arquivo .flowmon que ja existe:
  python3 /work/scripts/run_experiments.py --parse-only /tmp/t1.flowmon

Se for interrompido (Ctrl+C, terminal fechado), basta rodar o mesmo comando de novo:
as simulacoes ja gravadas no CSV sao puladas.

Definicao das metricas (apenas os fluxos de DADOS: UDP, porta de destino 9; o trafego de
controle dos protocolos de roteamento e ignorado):
  PDR (%)          = pacotes recebidos / pacotes enviados * 100
  Vazao (kbps)     = pacotes recebidos * 64 B * 8 / 100 s / 1000
  Atraso medio     = soma dos atrasos / pacotes recebidos            (ms)
  Jitter medio     = soma dos jitters / (pacotes recebidos - 1)      (ms)
"""
import argparse
import csv
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------- Parametros do experimento (unica fonte da verdade) ----------------
PROTOCOLS = ["AODV", "OLSR", "DSDV"]
MAX_SPEEDS = [2, 5, 10, 15, 20]  # velocidade maxima dos nos (m/s) = nivel de mobilidade
MIN_SPEED = 1                    # velocidade minima dos nos (m/s)
PAUSE = 0                        # tempo de pausa (s)
SEEDS = list(range(1, 11))       # RngRun de 1 a 10

# ---------------- Constantes do cenario (iguais ao exemplo manet-routing-compare) ----
DATA_PORT = "9"          # porta UDP dos fluxos de dados
UDP_PROTOCOL = "17"      # numero do protocolo UDP no IP
PAYLOAD_BYTES = 64       # bytes de dados por pacote
TRAFFIC_WINDOW_S = 100.0 # o trafego dura de ~100 s ate 200 s
EXPECTED_FLOWS = 10      # numero de pares origem/destino

FIELDS = [
    "protocol", "max_speed_mps", "seed", "data_flows", "tx_packets", "rx_packets",
    "pdr_percent", "throughput_kbps", "avg_delay_ms", "avg_jitter_ms", "wall_seconds",
]


def parse_ns(text):
    """Converte '+1.00515e+11ns' em float (nanossegundos)."""
    text = text.strip()
    if not text.endswith("ns"):
        raise ValueError(f"valor de tempo inesperado: {text!r}")
    return float(text[:-2])


def compute_metrics(flowmon_path):
    """Calcula as metricas a partir de um arquivo .flowmon (XML do FlowMonitor)."""
    root = ET.parse(flowmon_path).getroot()
    classifier, stats = {}, {}
    for flow in root.iter("Flow"):
        flow_id = flow.get("flowId")
        if flow.get("destinationPort") is not None:  # bloco que descreve o fluxo
            classifier[flow_id] = flow
        elif flow.get("txPackets") is not None:      # bloco com as estatisticas
            stats[flow_id] = flow
    if not classifier or not stats:
        raise ValueError("arquivo .flowmon sem estatisticas ou sem classificador de fluxos")

    tx = rx = jitter_den = n_flows = 0
    delay_ns = jitter_ns = 0.0
    for flow_id, desc in classifier.items():
        if desc.get("protocol") != UDP_PROTOCOL or desc.get("destinationPort") != DATA_PORT:
            continue
        st = stats.get(flow_id)
        if st is None:
            continue
        n_flows += 1
        flow_rx = int(st.get("rxPackets"))
        tx += int(st.get("txPackets"))
        rx += flow_rx
        delay_ns += parse_ns(st.get("delaySum"))
        jitter_ns += parse_ns(st.get("jitterSum"))
        jitter_den += max(flow_rx - 1, 0)
    if n_flows == 0:
        raise ValueError("nenhum fluxo de dados (UDP, porta 9) encontrado")
    if n_flows != EXPECTED_FLOWS:
        print(f"AVISO: {n_flows} fluxos de dados (esperado {EXPECTED_FLOWS})", file=sys.stderr)

    return {
        "data_flows": n_flows,
        "tx_packets": tx,
        "rx_packets": rx,
        "pdr_percent": round(100.0 * rx / tx, 6) if tx else None,
        "throughput_kbps": round(rx * PAYLOAD_BYTES * 8 / TRAFFIC_WINDOW_S / 1000.0, 6),
        "avg_delay_ms": round(delay_ns / rx / 1e6, 6) if rx else None,
        "avg_jitter_ms": round(jitter_ns / jitter_den / 1e6, 6) if jitter_den else None,
    }


def run_one(ns3_dir, protocol, max_speed, seed, workdir):
    """Roda uma simulacao e devolve a linha de resultados."""
    tag = f"{protocol}_v{max_speed}_s{seed}"
    prefix = workdir / tag
    csv_tmp = workdir / f"{tag}.csv"
    program = (
        f"manet-exp --protocol={protocol} --manetMaxSpeed={max_speed} "
        f"--manetMinSpeed={MIN_SPEED} --manetPause={PAUSE} --RngRun={seed} "
        f"--traceMobility=false --flowMonitor=true "
        f"--manetOutPrefix={prefix} --CSVfileName={csv_tmp}"
    )
    start = time.time()
    proc = subprocess.run(
        ["./ns3", "run", "--no-build", program],
        cwd=ns3_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    elapsed = time.time() - start
    flowmon = Path(f"{prefix}.flowmon")
    if proc.returncode != 0 or not flowmon.exists():
        tail = (proc.stderr or "").strip()[-400:]
        raise RuntimeError(f"ns3 terminou com codigo {proc.returncode}. Fim da saida: {tail}")
    metrics = compute_metrics(flowmon)
    flowmon.unlink()
    csv_tmp.unlink(missing_ok=True)
    return {
        "protocol": protocol, "max_speed_mps": max_speed, "seed": seed,
        **metrics, "wall_seconds": round(elapsed, 1),
    }


def load_done(out_path):
    """Le o CSV existente e devolve as combinacoes ja executadas."""
    done = set()
    if out_path.exists() and out_path.stat().st_size > 0:
        with out_path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames != FIELDS:
                sys.exit(f"ERRO: {out_path} existe mas tem colunas diferentes das esperadas. "
                         "Mude o nome com --out ou apague o arquivo.")
            for row in reader:
                done.add((row["protocol"], int(row["max_speed_mps"]), int(row["seed"])))
    return done


def main():
    ap = argparse.ArgumentParser(description="Roda o experimento MANET e extrai as metricas.")
    ap.add_argument("--protocols", nargs="+", default=PROTOCOLS, choices=PROTOCOLS)
    ap.add_argument("--speeds", nargs="+", type=int, default=MAX_SPEEDS,
                    help="velocidades maximas em m/s")
    ap.add_argument("--seeds", nargs="+", type=int, default=SEEDS, help="valores de RngRun")
    ap.add_argument("--jobs", type=int, default=1, help="simulacoes em paralelo (padrao 1)")
    ap.add_argument("--ns3-dir", default=".", help="pasta do ns-3 (padrao: pasta atual)")
    ap.add_argument("--out", default=None,
                    help="CSV de saida (padrao: /work/data/resultados.csv, ou data/resultados.csv)")
    ap.add_argument("--parse-only", metavar="ARQUIVO.flowmon",
                    help="so calcula as metricas de um .flowmon e sai")
    args = ap.parse_args()

    if args.parse_only:
        for key, value in compute_metrics(args.parse_only).items():
            print(f"{key:16s} {value}")
        return 0

    ns3_dir = Path(args.ns3_dir).resolve()
    if not (ns3_dir / "ns3").exists():
        sys.exit(f"ERRO: {ns3_dir}/ns3 nao encontrado. Rode na pasta do ns-3 ou use --ns3-dir.")
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = Path("/work/data/resultados.csv") if Path("/work").is_dir() \
            else Path("data/resultados.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    done = load_done(out_path)
    # sementes por fora: se parar no meio, cada combinacao tem o mesmo numero de repeticoes
    todo = [(p, v, s) for s in args.seeds for v in args.speeds for p in args.protocols
            if (p, v, s) not in done]
    total = len(args.seeds) * len(args.speeds) * len(args.protocols)
    print(f"{total - len(todo)} de {total} simulacoes ja estavam no CSV; "
          f"{len(todo)} para rodar (jobs={args.jobs}). Saida: {out_path}")
    if not todo:
        return 0

    new_file = not out_path.exists() or out_path.stat().st_size == 0
    workdir = Path(tempfile.mkdtemp(prefix="manet-"))
    pool = ThreadPoolExecutor(max_workers=args.jobs)
    failures = completed = 0
    interrupted = False
    try:
        with out_path.open("a", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
                fh.flush()
            futures = {pool.submit(run_one, ns3_dir, p, v, s, workdir): (p, v, s)
                       for p, v, s in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                p, v, s = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:  # uma falha nao derruba o lote
                    failures += 1
                    print(f"[{i}/{len(todo)}] FALHOU {p} v={v} seed={s}: {exc}", file=sys.stderr)
                    continue
                writer.writerow(row)
                fh.flush()
                completed += 1
                print(f"[{i}/{len(todo)}] {p:5s} v={v:2d} seed={s:2d}  "
                      f"PDR={row['pdr_percent']}%  vazao={row['throughput_kbps']} kbps  "
                      f"atraso={row['avg_delay_ms']} ms  jitter={row['avg_jitter_ms']} ms  "
                      f"({row['wall_seconds']} s)")
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrompido. Rode o mesmo comando para continuar de onde parou.")
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"Concluido: {completed} novas, {failures} falhas. Resultados em {out_path}")
    if interrupted:
        return 130
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
