#!/usr/bin/env python
# A2R Link - Colar (menu Workspace > Scripts do DaVinci Resolve Studio)
# Monta na timeline o que foi copiado no Premiere/After (pasta de dados NoeVFX\clipboard.json).
# Chama o Python do projeto por fora (o Python do menu do Resolve pode ser outro) e grava o resultado em ultimo_colar.log
import json, os, subprocess, sys

if sys.platform == "darwin":
    BASE = os.path.expanduser("~/Library/Application Support")
elif os.environ.get("APPDATA"):
    BASE = os.environ["APPDATA"]
elif sys.platform == "win32":
    BASE = os.path.expanduser("~/AppData/Roaming")
else:
    BASE = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
DADOS = os.path.join(BASE, "NoeVFX")

cfg_path = os.path.join(DADOS, "config.json")
cfg = json.load(open(cfg_path, encoding="utf-8"))
DADOS = cfg.get("dados", DADOS)
log = open(os.path.join(DADOS, "ultimo_colar.log"), "w", encoding="utf-8")
kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # esconde a janela do console (so Windows)
subprocess.Popen([cfg["python"], "-u", cfg["bridge"], "paste"], stdout=log, stderr=subprocess.STDOUT,
                 cwd=os.path.dirname(cfg["bridge"]), env=dict(os.environ, A2R_DADOS=DADOS), **kw)
