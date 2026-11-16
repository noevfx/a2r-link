"""A2R Link: instalador e desinstalador (Windows e macOS). Reinstalar e seguro.
Uso: python install.py            (instala)      python install.py --remover   (remove tudo que o instalador criou)"""
import os, sys, json, shutil, subprocess

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "src"))
from i18n import T    # idioma do sistema (locale); o painel sobrepoe com A2R_LANG
MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"

VERSAO = open(os.path.join(AQUI, "version.txt"), encoding="utf-8").read().strip() \
    if os.path.exists(os.path.join(AQUI, "version.txt")) else ""

if WIN:
    import winreg
    BASE = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")   # %APPDATA% (com fallback se a var faltar)
    RESOLVE_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
    RESOLVE_API = r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
    ADOBE_RAIZ = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Adobe")
    # Windows: %APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit
    RESOLVE_SCRIPTS = os.path.join(BASE, "Blackmagic Design", "DaVinci Resolve", "Support", "Fusion", "Scripts", "Edit")
elif MAC:
    BASE = os.path.expanduser("~/Library/Application Support")         # Application Support do usuario
    RESOLVE_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
    RESOLVE_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
    ADOBE_RAIZ = "/Applications"
    # Mac: SEM a pasta "Support" do Windows — a varredura e em .../DaVinci Resolve/Fusion/Scripts
    RESOLVE_SCRIPTS = os.path.join(BASE, "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts", "Edit")
else:                                                                   # linux (bonus; sem painel CEP instalado por aqui)
    BASE = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")))
    RESOLVE_LIB = "/opt/resolve/libs/Fusion/fusionscript.so"
    RESOLVE_API = "/opt/resolve/Developer/Scripting/Modules"
    ADOBE_RAIZ = "/opt"
    RESOLVE_SCRIPTS = os.path.join(BASE, "Blackmagic Design", "DaVinci Resolve", "Fusion", "Scripts", "Edit")

CEP = os.path.join(BASE, "Adobe", "CEP", "extensions")
DESTINOS = {"premiere": "com.noevfx.bridge.premiere", "ae": "com.noevfx.bridge.ae"}
PASTA_DADOS = os.path.join(BASE, "NoeVFX")            # config, clipboard, logs e relatorios de debug do A2R Link
CONFIG = os.path.join(PASTA_DADOS, "config.json")


def verificar():
    """confere os pre-requisitos e avisa (so o Python errado interrompe)"""
    print(T("Conferindo pre-requisitos:", "Checking requirements:"))
    if sys.version_info < (3, 14):
        print(T("  [ERRO] Python %d.%d: o A2R Link precisa do Python 3.14 ou mais novo (64 bits). Baixe em python.org e rode de novo.",
                "  [ERROR] Python %d.%d: A2R Link needs Python 3.14 or newer (64 bit). Download at python.org and run again.")
              % sys.version_info[:2])
        return False
    print("  [ok] Python %d.%d.%d" % sys.version_info[:3])
    if os.path.exists(RESOLVE_LIB) or os.path.isdir(RESOLVE_API):
        print(T("  [ok] DaVinci Resolve encontrado (precisa ser a versao Studio, com External scripting = Local)",
                "  [ok] DaVinci Resolve found (must be the Studio version, External scripting = Local)"))
    else:
        print(T("  [aviso] Nao achei o DaVinci Resolve nos caminhos padrao. Instale o Studio antes de usar.",
                "  [warn] Could not find DaVinci Resolve in the usual places. Install Studio before using."))
    try:
        adobe = any(n.startswith("Adobe") for n in os.listdir(ADOBE_RAIZ))
    except OSError:
        adobe = False
    print(T("  [ok] Adobe encontrada", "  [ok] Adobe found") if adobe else T("  [aviso] Nao achei Premiere/After instalados nos caminhos padrao.", "  [warn] Could not find Premiere/After in the usual places."))
    return True


def debug_cep():
    """garante PlayerDebugMode=1 nas versoes de CSXS (so grava onde nao esta ligado); paineis sem assinatura so carregam assim"""
    feitos = []
    for v in range(9, 20):
        if WIN:
            chave = r"Software\Adobe\CSXS.%d" % v
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, chave, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                    try:
                        atual = winreg.QueryValueEx(k, "PlayerDebugMode")[0]
                    except FileNotFoundError:
                        atual = None
                    if str(atual) not in ("1", "0x1"):
                        winreg.SetValueEx(k, "PlayerDebugMode", 0, winreg.REG_SZ, "1"); feitos.append(v)
            except OSError:
                pass
        else:      # mac/linux: plist via defaults (idempotente; falhar numa versao nao atrapalha as outras)
            try:
                r = subprocess.run(["defaults", "read", "com.adobe.CSXS.%d" % v, "PlayerDebugMode"],
                                   capture_output=True, text=True, timeout=10)
                if r.stdout.strip() != "1":
                    subprocess.run(["defaults", "write", "com.adobe.CSXS.%d" % v, "PlayerDebugMode", "1"],
                                   capture_output=True, timeout=10)
                    feitos.append(v)
            except (OSError, subprocess.SubprocessError):
                pass
    return feitos


def instalar():
    if not verificar():
        return 1
    print(T("\nInstalando:", "\nInstalling:"))
    os.makedirs(PASTA_DADOS, exist_ok=True)
    cfg = {"python": sys.executable, "bridge": os.path.join(AQUI, "src", "bridge.py"),
           "readers": os.path.join(AQUI, "src", "readers"), "dados": PASTA_DADOS, "versao": VERSAO,
           "repo": "noevfx/a2r-link"}   # releases do GitHub (auto-update do painel)
    json.dump(cfg, open(CONFIG, "w", encoding="utf-8"), indent=1)
    print(T("  configuracao:", "  configuration:"), CONFIG)
    for nome, bundle in DESTINOS.items():
        dest = os.path.join(CEP, bundle)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(os.path.join(AQUI, "extensions", "common"), dest)
        os.makedirs(os.path.join(dest, "CSXS"), exist_ok=True)
        shutil.copy(os.path.join(AQUI, "extensions", nome, "manifest.xml"), os.path.join(dest, "CSXS", "manifest.xml"))
        shutil.copy(CONFIG, os.path.join(dest, "config.json"))   # copia dentro do painel
        # config embutida: o painel carrega js/config.js como qualquer outro script seu (nao precisa ler arquivo nem variavel de ambiente)
        open(os.path.join(dest, "js", "config.js"), "w", encoding="utf-8").write("window.A2R_CONFIG = " + json.dumps(cfg, ensure_ascii=False) + ";\n")
        print(T("  painel do %s: %s", "  %s panel: %s") % ("Premiere" if nome == "premiere" else "After Effects", dest))
    os.makedirs(RESOLVE_SCRIPTS, exist_ok=True)
    antigo = os.path.join(RESOLVE_SCRIPTS, "Noe Bridge - Colar.py")   # nome da primeira versao (antes de virar A2R Link)
    if os.path.exists(antigo):
        os.remove(antigo)
    shutil.copy(os.path.join(AQUI, "resolve", "A2R Link - Colar.py"), RESOLVE_SCRIPTS)
    print(T("  script do DaVinci:", "  DaVinci script:"), os.path.join(RESOLVE_SCRIPTS, "A2R Link - Colar.py"))
    d = debug_cep()
    print(T("  PlayerDebugMode (permite carregar paineis nao assinados):", "  PlayerDebugMode (allows unsigned panels):"), (T("ligado em CSXS %s", "enabled on CSXS %s") % d) if d else T("ja estava ligado", "was already enabled"))
    print(T("\nPronto. Reinicie o Premiere e o After. Painel: Janela > Extensoes > A2R Link.",
            "\nDone. Restart Premiere and After. Panel: Window > Extensions > A2R Link."))
    print(T("No DaVinci Studio: Preferences > System > General > External scripting using = Local (e reinicie o DaVinci).",
            "In DaVinci Studio: Preferences > System > General > External scripting using = Local (then restart DaVinci)."))
    return 0


def remover():
    print(T("Removendo o A2R Link:", "Removing A2R Link:"))
    for bundle in DESTINOS.values():
        dest = os.path.join(CEP, bundle)
        if os.path.isdir(dest):
            shutil.rmtree(dest); print(T("  removido:", "  removed:"), dest)
    for f in (os.path.join(RESOLVE_SCRIPTS, "A2R Link - Colar.py"), os.path.join(RESOLVE_SCRIPTS, "Noe Bridge - Colar.py")):
        if os.path.exists(f):
            os.remove(f); print(T("  removido:", "  removed:"), f)
    import glob
    for nome in ("config.json", "clipboard.json", "ultimo_colar.log"):
        f = os.path.join(PASTA_DADOS, nome)
        if os.path.exists(f):
            os.remove(f); print(T("  removido:", "  removed:"), f)
    for f in glob.glob(os.path.join(PASTA_DADOS, "A2R-debug-*.zip")):     # relatorios de debug tambem sao nossos
        try:
            os.remove(f); print(T("  removido:", "  removed:"), f)
        except OSError:
            pass
    try:
        os.rmdir(PASTA_DADOS); print(T("  removida a pasta vazia:", "  removed the empty folder:"), PASTA_DADOS)
    except OSError:
        pass          # a pasta tem outros arquivos (de outros produtos): fica
    print(T("\nPronto. Reinicie o Premiere e o After. Os timelines e bins que o A2R Link criou no DaVinci ficam (sao seus).",
            "\nDone. Restart Premiere and After. The timelines and bins A2R Link created in DaVinci stay (they are yours)."))
    print(T("O PlayerDebugMode do CEP nao foi desligado (outros paineis seus podem precisar dele).",
            "CEP PlayerDebugMode was not turned off (other panels of yours may need it)."))
    return 0


if __name__ == "__main__":
    sys.exit(remover() if "--remover" in sys.argv else instalar())
