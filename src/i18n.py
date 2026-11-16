# i18n minimo do A2R Link: pt-BR e en-US. O painel manda A2R_LANG (idioma do
# sistema via navigator.language); sem ele, caimos no locale do sistema e, por
# fim, em portugues (base do projeto). T() devolve a string do idioma ativo.
import locale
import os

_LANG = None


def _detecta():
    lang = os.environ.get("A2R_LANG", "").lower()
    if lang.startswith("en"):
        return "en"
    if lang.startswith("pt"):
        return "pt"
    try:
        loc = (locale.getlocale()[0] or "").lower()
        if loc.startswith("en"):
            return "en"
    except Exception:
        pass
    return "pt"


def LANG():
    global _LANG
    if _LANG is None:
        _LANG = _detecta()
    return _LANG


def T(pt, en):
    return pt if LANG() == "pt" else en
