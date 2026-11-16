#!/bin/bash
# A2R Link - DESINSTALAR (Mac). Remove os paineis, o script do DaVinci e a configuracao.
# A2R Link - UNINSTALL (Mac). Removes the panels, the DaVinci script and the configuration.
# Se o macOS bloquear: clique com o botao direito > Abrir > Abrir.
# If macOS blocks it: right-click > Open > Open.
cd "$(dirname "$0")" || exit 1
LOC="$(defaults read -g AppleLocale 2>/dev/null || echo en)"
export A2R_LANG="${LOC%%_*}"
PY="$(command -v python3.14 || command -v python3.15 || command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  if [ "$A2R_LANG" = "pt" ]; then
    echo "Python nao encontrado. Rode pelo Terminal: python3 \"$PWD/install.py\" --remover"
  else
    echo "Python not found. Run in Terminal: python3 \"$PWD/install.py\" --remover"
  fi
  echo; read -r -p "Enter para fechar / press Enter to close..."
  exit 1
fi
"$PY" install.py --remover
echo; read -r -p "Enter para fechar / press Enter to close..."
