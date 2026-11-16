#!/bin/bash
# A2R Link - INSTALAR (Mac). Duplo clique instala os paineis do Premiere/After e o script do DaVinci.
# A2R Link - INSTALL (Mac). Double-click installs the Premiere/After panels and the DaVinci script.
# Se o macOS bloquear ("desenvolvedor nao identificado"): clique com o botao direito > Abrir > Abrir.
# If macOS blocks it ("unidentified developer"): right-click > Open > Open.
cd "$(dirname "$0")" || exit 1
# idioma do sistema -> A2R_LANG (o install.py e os paineis usam)
LOC="$(defaults read -g AppleLocale 2>/dev/null || echo en)"
export A2R_LANG="${LOC%%_*}"
# procura o 3.14+ antes do generico (num Mac com python3 antigo o generico ganha e o install.py morre com "precisa de 3.14")
PY="$(command -v python3.14 || command -v python3.15 || command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  if [ "$A2R_LANG" = "pt" ]; then
    echo "Python nao encontrado. Baixe o Python 3.14 em python.org (botao Downloads) e rode este arquivo de novo."
  else
    echo "Python not found. Download Python 3.14 at python.org (Downloads button) and run this file again."
  fi
  echo; read -r -p "Enter para fechar / press Enter to close..."
  exit 1
fi
"$PY" install.py
echo; read -r -p "Enter para fechar / press Enter to close..."
