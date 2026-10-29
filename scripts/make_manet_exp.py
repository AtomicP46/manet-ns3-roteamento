#!/usr/bin/env python3
"""Gera scratch/manet-exp.cc a partir do exemplo manet-routing-compare.cc (ns-3.48).

O arquivo gerado acrescenta quatro parametros de linha de comando:
  --manetMaxSpeed   velocidade maxima dos nos, em m/s      (padrao 20)
  --manetMinSpeed   velocidade minima dos nos, em m/s      (padrao 0)
  --manetPause      tempo de pausa dos nos, em s           (padrao 0)
  --manetOutPrefix  prefixo dos arquivos .flowmon e .mob   (padrao manet-routing-compare)

Com os valores padrao, o comportamento e igual ao do exemplo original.

Uso (dentro da pasta do ns-3):
  python3 /work/scripts/make_manet_exp.py
"""
import re
import sys
from pathlib import Path

SRC = Path("examples/routing/manet-routing-compare.cc")
DST = Path("scratch/manet-exp.cc")

HEADER = (
    "// Derivado de examples/routing/manet-routing-compare.cc (ns-3.48).\n"
    "// Gerado por scripts/make_manet_exp.py: acrescenta --manetMaxSpeed, --manetMinSpeed,\n"
    "// --manetPause e --manetOutPrefix. Valores padrao = comportamento do exemplo original.\n\n"
)

GLOBALS = '''NS_LOG_COMPONENT_DEFINE("manet-routing-compare");

// ---- Parametros extras (aceitos na linha de comando, ex.: --manetMaxSpeed=10) ----
static GlobalValue g_manetMaxSpeed("manetMaxSpeed",
                                   "Velocidade maxima dos nos (m/s)",
                                   IntegerValue(20),
                                   MakeIntegerChecker<int>());
static GlobalValue g_manetMinSpeed("manetMinSpeed",
                                   "Velocidade minima dos nos (m/s)",
                                   IntegerValue(0),
                                   MakeIntegerChecker<int>());
static GlobalValue g_manetPause("manetPause",
                                "Tempo de pausa dos nos (s)",
                                IntegerValue(0),
                                MakeIntegerChecker<int>());
static GlobalValue g_manetOutPrefix("manetOutPrefix",
                                    "Prefixo dos arquivos .flowmon e .mob",
                                    StringValue("manet-routing-compare"),
                                    MakeStringChecker());
// ---------------------------------------------------------------------------------'''

READ_PARAMS = '''IntegerValue vMaxSpeed;
    IntegerValue vMinSpeed;
    IntegerValue vPause;
    StringValue vPrefix;
    GlobalValue::GetValueByName("manetMaxSpeed", vMaxSpeed);
    GlobalValue::GetValueByName("manetMinSpeed", vMinSpeed);
    GlobalValue::GetValueByName("manetPause", vPause);
    GlobalValue::GetValueByName("manetOutPrefix", vPrefix);
    std::string tr_name(vPrefix.Get());'''

SPEEDS = '''int nodeSpeed = vMaxSpeed.Get(); // in m/s
    int nodeMinSpeed = vMinSpeed.Get(); // in m/s
    NS_ABORT_MSG_IF(nodeMinSpeed > nodeSpeed, "manetMinSpeed nao pode ser maior que manetMaxSpeed");'''

PATCHES = [
    ("declaracao dos parametros",
     r'NS_LOG_COMPONENT_DEFINE\("manet-routing-compare"\);',
     GLOBALS),
    ("leitura dos parametros / tr_name",
     r'std::string tr_name\("manet-routing-compare"\);',
     READ_PARAMS),
    ("velocidade maxima e minima",
     r'int nodeSpeed = 20;[^\n]*',
     SPEEDS),
    ("tempo de pausa",
     r'int nodePause = 0;[^\n]*',
     'int nodePause = vPause.Get(); // in s'),
    ("sorteio da velocidade",
     r'"ns3::UniformRandomVariable\[Min=0\.0\|Max="',
     '"ns3::UniformRandomVariable[Min=" << nodeMinSpeed << "|Max="'),
]


def apply(text, name, pattern, replacement):
    new_text, count = re.subn(pattern, lambda _m: replacement, text)
    if count != 1:
        sys.exit(
            f"ERRO: o trecho '{name}' foi encontrado {count} vez(es) (esperado: 1).\n"
            "O arquivo original e diferente do esperado; nada foi gerado."
        )
    return new_text


def main():
    if not SRC.exists():
        sys.exit(f"ERRO: {SRC} nao encontrado. Rode este script na pasta do ns-3.")
    text = SRC.read_text()
    for name, pattern, replacement in PATCHES:
        text = apply(text, name, pattern, replacement)
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(HEADER + text)
    print(f"OK: {DST} gerado a partir de {SRC}.")


if __name__ == "__main__":
    main()