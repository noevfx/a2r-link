"""Monta o pacote de distribuicao do A2R Link em release/vX.Y.Z/ (versao lida de version.txt).
O zip tem duas pastas irmao, Windows/ e Mac/, cada uma completa: a pessoa descompacta,
entra na pasta do sistema dela e da duplo clique no instalador. Uso: python scripts/build_release.py"""
import os, sys, zipfile, hashlib, stat

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSAO = open(os.path.join(RAIZ, "version.txt"), encoding="utf-8").read().strip()
PASTA_ZIP = "A2R Link %s" % VERSAO
DESTINO = os.path.join(RAIZ, "release", "v" + VERSAO)
ZIP = os.path.join(DESTINO, "A2R-Link_%s.zip" % VERSAO)

# payload comum aos dois sistemas (o install.py e o mesmo nos dois)
COMUM = [
    "install.py", "version.txt",
    "extensions/common/index.html", "extensions/common/js/main.js", "extensions/common/jsx/host.jsx",
    "extensions/common/img/logo.png",
    "extensions/premiere/manifest.xml", "extensions/ae/manifest.xml",
    "resolve/A2R Link - Colar.py",
    "src/bridge.py", "src/gen.py", "src/normalizer.py", "src/drtlib.py", "src/ae_io.py", "src/prproj.py", "src/i18n.py",
    "src/readers/premiere_read.jsx", "src/readers/premiere_resample.jsx", "src/readers/ae_read.jsx",
]
SOMENTE = {   # (arquivo_fonte_relativo, nome_dentro_da_pasta)
    "Windows": [("LEIA-ME.txt", "LEIA-ME.txt"), ("INSTALAR.bat", "INSTALAR.bat"), ("DESINSTALAR.bat", "DESINSTALAR.bat")],
    "Mac": [("LEIA-ME-MAC.txt", "LEIA-ME.txt"), ("INSTALAR.command", "INSTALAR.command"), ("DESINSTALAR.command", "DESINSTALAR.command")],
}
EXECUTAVEIS = ("INSTALAR.command", "DESINSTALAR.command")   # precisam do bit de execucao pra abrir com duplo clique no Finder


def _adiciona(z, fonte, alvo, executavel=False):
    info = zipfile.ZipInfo(alvo)
    info.date_time = (2026, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3            # Unix: sem isso (0=Windows/FAT) o Finder/extrator ignora as permissoes e o .command nao abre com duplo clique
    info.external_attr = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH |
                          (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH if executavel else 0)) << 16
    z.writestr(info, open(os.path.join(RAIZ, fonte), "rb").read())


def main():
    if os.path.exists(ZIP):
        print("ERRO: %s ja existe. Release publicada e imutavel: suba a versao em version.txt." % ZIP)
        return 1
    arquivos = COMUM + [f for itens in SOMENTE.values() for f, _ in itens]
    faltam = [a for a in arquivos if not os.path.exists(os.path.join(RAIZ, a))]
    if faltam:
        print("ERRO: faltam arquivos:", faltam); return 1
    os.makedirs(DESTINO, exist_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for pasta, proprios in SOMENTE.items():
            for a in COMUM:
                _adiciona(z, a, "%s/%s/%s" % (PASTA_ZIP, pasta, a))
            for fonte, nome in proprios:
                _adiciona(z, fonte, "%s/%s/%s" % (PASTA_ZIP, pasta, nome), executavel=(nome in EXECUTAVEIS))
    h = hashlib.sha256(open(ZIP, "rb").read()).hexdigest()
    open(os.path.join(DESTINO, "SHA256SUMS.txt"), "w", encoding="utf-8").write("%s  %s\n" % (h, os.path.basename(ZIP)))
    print("pacote:", ZIP, "(%d KB)" % (os.path.getsize(ZIP) // 1024))
    print("SHA-256:", h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
