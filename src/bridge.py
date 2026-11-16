"""bridge: copiar no Premiere, colar no DaVinci.
  python bridge.py copy   -> le os clipes selecionados do Premiere e grava %APPDATA%\\NoeVFX\\clipboard.json
  python bridge.py paste  -> le o clipboard.json e monta a timeline no DaVinci (Studio, aberto, projeto aberto)
"""
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i18n import T, LANG


def appdata():
    """pasta de dados do usuario em cada sistema (AppData\\Roaming | ~/Library/Application Support | ~/.config)"""
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support')
    if os.environ.get('APPDATA'):
        return os.environ['APPDATA']
    if sys.platform == 'win32':
        return os.path.expanduser('~/AppData/Roaming')
    return os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))


def caminho_uri(p):
    """app.project.path pode vir como URI file:// (com %20) ou caminho nativo; devolve caminho local"""
    p = str(p or '')
    if p.startswith('file:'):
        u = urllib.parse.urlparse(p)
        p = urllib.parse.unquote(u.path)
        if sys.platform == 'win32' and len(p) > 2 and p[0] == '/' and p[2] == ':':
            p = p[1:]                                            # /C:/x -> C:/x
    return p


DADOS = os.environ.get('A2R_DADOS') or os.path.join(appdata(), 'NoeVFX')   # o painel passa a pasta de dados da configuracao
CLIP = os.path.join(DADOS, 'clipboard.json')
HERE = os.path.dirname(os.path.abspath(__file__))


def run_premiere(code, timeout=90):
    code = 'var __LANG = %s;\n%s' % (json.dumps(LANG()), code)   # leitores saem no idioma do sistema
    tok = open(os.path.join(appdata(), 'prmcp', 'token')).read().strip()
    req = urllib.request.Request('http://127.0.0.1:47300/run', data=json.dumps({'code': code}).encode(),
                                 headers={'Content-Type': 'application/json', 'x-prmcp-token': tok})
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if not r.get('success'):
        raise RuntimeError('Premiere: %s' % r.get('error'))
    return r['data']


def copy_premiere():
    code = open(os.path.join(HERE, 'readers', 'premiere_read.jsx'), encoding='utf-8').read()
    data = run_premiere(code)
    if data.get('erro'):
        raise RuntimeError(data['erro'])
    os.makedirs(os.path.dirname(CLIP), exist_ok=True)
    json.dump({'source': 'premiere', 'data': data}, open(CLIP, 'w', encoding='utf-8'), indent=1)
    print(T('copiado: %d clipe(s) (%s) -> %s', 'copied: %d clip(s) (%s) -> %s') % (len(data['clips']), T('selecionados', 'selected') if data['selectedOnly'] else T('todos', 'all'), CLIP))
    return data


def copy_ae():
    import ae_io
    data = ae_io.run_ae(open(os.path.join(HERE, 'readers', 'ae_read.jsx'), encoding='utf-8').read(), timeout=60)
    if data.get('erro'):
        raise RuntimeError(data['erro'])
    os.makedirs(os.path.dirname(CLIP), exist_ok=True)
    json.dump({'source': 'ae', 'data': data}, open(CLIP, 'w', encoding='utf-8'), indent=1)
    print(T('copiado do After: %d camada(s) (%s) -> %s', 'copied from After: %d layer(s) (%s) -> %s') % (len(data['layers']), T('selecionadas', 'selected') if data['selectedOnly'] else T('todas', 'all'), CLIP))
    return data


def _remaps_do_prproj(pack):
    """le o .prproj salvo e anexa c['remap'] (amostras t_seq_abs -> t_midia) nos clipes copiados.
    Devolve o dict de remaps encontrados; levanta excecao se o parse falhar."""
    seq = pack['data']['sequence']
    import prproj
    rm = prproj.remaps(caminho_uri(seq['path']), seq.get('name'), seq['fps'],
                       [(c['track'], c['start'], c['end']) for c in pack['data']['clips']
                        if c.get('mediaPath') or c.get('subSeq')])
    lb = prproj.labels(caminho_uri(seq['path']), seq.get('name'),
                       [('video', c['track'], c['start'], c['end']) for c in pack['data']['clips'] if c.get('mediaPath')] +
                       [('audio', c['track'], c['start'], c['end']) for c in pack['data'].get('audio', []) if c.get('mediaPath')])
    for tp, lst in (('video', pack['data']['clips']), ('audio', pack['data'].get('audio', []))):
        for c in lst:
            for (tp2, tr, t0), v in lb.items():
                if tp2 == tp and tr == c['track'] and abs(c['start'] - t0) < 0.004:
                    c['label_rgb'] = v
    mk = prproj.clip_markers(caminho_uri(seq['path']), seq.get('name'),
                             [(c['track'], c['start']) for c in pack['data']['clips'] if c.get('mediaPath')])
    fh = prproj.frame_holds(caminho_uri(seq['path']), seq.get('name'),
                            [(c['track'], c['start']) for c in pack['data']['clips'] if c.get('mediaPath')])
    for c in pack['data']['clips']:
        for (tr, t0), v in rm.items():
            if tr == c['track'] and abs(c['start'] - t0) < 0.004:
                c['remap'] = v['samples']
                c['remap_nodes'] = {'knots': v['knots'], 'absoluto': v['knots_absoluto']}
        for (tr, t0), ms in mk.items():
            if tr == c['track'] and abs(c['start'] - t0) < 0.004:
                c['markers'] = [{'t': m[0], 'nome': m[1], 'comentario': m[2], 'tipo': m[3], 'dur': m[4]} for m in ms]
        for (tr, t0), t_hold in fh.items():
            if tr == c['track'] and abs(c['start'] - t0) < 0.004:
                c['frameHold'] = t_hold
        # speed/reverso/rampa/markers de clipes DENTRO de sub-seqs: o QE nao os le (seq nao ativa) -> .prproj
        def patch_sub(cl):
            if not cl.get('subSeq') or not cl.get('subSeqNome') or not cl.get('subClips'):
                return
            try:
                sub_fps = cl.get('subFps') or seq['fps']
                midias = [s for s in cl['subClips'] if s.get('mediaPath') or s.get('subSeq')]
                alvos = [(s['track'], s['start']) for s in midias]
                sp = prproj.speeds(caminho_uri(seq['path']), cl['subSeqNome'], alvos)
                rm2 = prproj.remaps(caminho_uri(seq['path']), cl['subSeqNome'], sub_fps,
                                    [(s['track'], s['start'], s['end']) for s in midias])
                mk2 = prproj.clip_markers(caminho_uri(seq['path']), cl['subSeqNome'], alvos)
                fh2 = prproj.frame_holds(caminho_uri(seq['path']), cl['subSeqNome'], alvos)
                lb2 = prproj.labels(caminho_uri(seq['path']), cl['subSeqNome'],
                                    [('video', s['track'], s['start'], s['end']) for s in midias])
                if not (sp or rm2 or mk2 or lb2 or fh2) and midias and \
                   not prproj.Prproj.aberto(caminho_uri(seq['path'])).sequencia(cl['subSeqNome']):
                    cl['_aviso_subseq'] = True
                for s in cl['subClips']:
                    for (tr2, t02), v2 in sp.items():
                        if tr2 == s['track'] and abs(s['start'] - t02) < 0.004:
                            s['speed'] = v2['speed'] * 100.0
                            s['reversed'] = v2['reversed']
                    for (tr2, t02), v2 in rm2.items():
                        if tr2 == s['track'] and abs(s['start'] - t02) < 0.004:
                            s['remap'] = v2['samples']
                            s['remap_nodes'] = {'knots': v2['knots'], 'absoluto': v2['knots_absoluto']}
                    for (tr2, t02), ms2 in mk2.items():
                        if tr2 == s['track'] and abs(s['start'] - t02) < 0.004:
                            s['markers'] = [{'t': m[0], 'nome': m[1], 'comentario': m[2], 'tipo': m[3], 'dur': m[4]} for m in ms2]
                    for (tr2, t02), t_hold2 in fh2.items():
                        if tr2 == s['track'] and abs(s['start'] - t02) < 0.004:
                            s['frameHold'] = t_hold2
                    for (tp2, tr2, t02), v2 in lb2.items():
                        if tp2 == 'video' and tr2 == s['track'] and abs(s['start'] - t02) < 0.004:
                            s['label_rgb'] = v2
                    patch_sub(s)
            except Exception:
                pass
        patch_sub(c)
    return rm


def remap_info():
    """(chamado pelo painel logo apos o Copiar) enriquece clipboard.json com o remap do .prproj
    e devolve JSON com a lista de reamostragem para a 2a passada do leitor (premiere_resample.jsx):
    as props de um clipe remapeado vivem em tempo de MIDIA e precisam ser avaliadas nos tempos m(d) reais."""
    pack = json.load(open(CLIP, encoding='utf-8'))
    out = {'ok': True, 'clips': []}
    if pack.get('source') != 'premiere':
        print(json.dumps(out)); return
    seq = pack['data'].get('sequence', {})
    if not seq.get('path'):
        print(json.dumps(out)); return
    try:
        rm = _remaps_do_prproj(pack)
    except Exception as e:
        print(json.dumps({'ok': False, 'erro': str(e), 'clips': []})); return
    out['dirty'] = bool(seq.get('dirty'))
    for c in pack['data']['clips']:
        for (tr, t0), v in rm.items():
            if tr == c['track'] and abs(c['start'] - t0) < 0.004:
                out['clips'].append({'track': tr, 'start': c['start'], 'tms': v['samples'],
                                     'knots': v['knots'], 'absoluto': v['knots_absoluto']})
    out['data'] = pack['data']   # clips ja enriquecidos (remap/markers/labels/sub-patches): o painel
    # substitui d por isto ANTES do segundo grava() — senao a reamostragem apaga o enriquecimento
    json.dump(pack, open(CLIP, 'w', encoding='utf-8'), indent=1)
    print(json.dumps(out))


def paste(name=None):
    import gen, normalizer
    pack = json.load(open(CLIP, encoding='utf-8'))
    r, p = gen._connect()
    data = pack['data']
    if pack['source'] == 'premiere':
        seq = data['sequence']
        sW, sH, sfps, sNome = seq['width'], seq['height'], seq['fps'], seq['name']
    elif pack['source'] == 'ae':
        comp = data['comp']
        sW, sH, sfps, sNome = comp['width'], comp['height'], comp['fps'], comp['name']
    else:
        raise NotImplementedError(pack['source'])
    # referencia de destino para escalar as props: 'existente' = a timeline de mesmo nome (ela ja
    # existe e nao muda); qualquer outro caso a timeline nova herda EXATAMENTE a origem
    # (resolucao e fps da sequencia/comp — nunca da timeline aberta no Resolve)
    W, H, fps = sW, sH, sfps
    if data.get('destino') == 'existente':
        for i in range(1, p.GetTimelineCount() + 1):
            t = p.GetTimelineByIndex(i)
            if t.GetName() == (name or sNome):
                W = int(t.GetSetting('timelineResolutionWidth')); H = int(t.GetSetting('timelineResolutionHeight'))
                fps = float(t.GetSetting('timelineFrameRate'))
                break
    if pack['source'] == 'premiere':
        falta_remap = bool(seq.get('path'))   # sempre enriquece do .prproj: remap/markers/labels/sub-patches
        # podem ter sido apagados por um clipboard externo ou por uma gravacao antiga do painel
        if falta_remap:   # Time Remapping e speed/reverso de sub-seqs nao vem pelo leitor: lidos do .prproj
            try:
                rm = _remaps_do_prproj(pack)
                if rm:
                    print(T('speed ramp: %d clipe(s) com Time Remapping lidos do .prproj', 'speed ramp: %d clip(s) with Time Remapping read from .prproj') % len(rm))
            except Exception as e:
                print(T('AVISO: nao consegui ler o speed ramp do projeto (%s)', 'AVISO: could not read the speed ramp from the project (%s)') % e)
        if any(c.get('remap') for c in pack['data']['clips']) and seq.get('dirty'):
            print(T('AVISO: o projeto tinha alteracoes nao salvas ao copiar: o speed ramp pode estar desatualizado (salve e copie de novo se mexeu na rampa)',
                    'AVISO: the project had unsaved changes when copied: the speed ramp may be stale (save and copy again if you edited the ramp)'))
        spec, avisos = normalizer.premiere_to_spec(pack['data'], W, H, fps, name=name)
    elif pack['source'] == 'ae':
        spec, avisos = normalizer.ae_to_spec(pack['data'], W, H, fps, name=name)
    else:
        raise NotImplementedError(pack['source'])
    for a in avisos:
        print('AVISO:', a)
    return gen.build(spec)


REPO = 'noevfx/a2r-link'   # releases do GitHub (override: "repo" no config.json)


def _versao():
    try:
        return open(os.path.join(HERE, '..', 'version.txt'), encoding='utf-8').read().strip()
    except OSError:
        return '0'


def _semver(s):
    import re
    p = [int(x) for x in re.findall(r'\d+', str(s or ''))[:3]]
    return tuple(p + [0] * (3 - len(p)))


def _repo():
    try:
        return json.load(open(os.path.join(DADOS, 'config.json'), encoding='utf-8')).get('repo') or REPO
    except Exception:
        return REPO


def _release_mais_novo():
    req = urllib.request.Request('https://api.github.com/repos/%s/releases/latest' % _repo(),
                                 headers={'User-Agent': 'a2r-link-updater', 'Accept': 'application/vnd.github+json'})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())


def check_update():
    """JSON: {ok, atual, nova, url, notas, tem_nova} — o painel chama ao abrir"""
    try:
        rel = _release_mais_novo()
        tag = str(rel.get('tag_name') or '').lstrip('vV')
        out = {'ok': True, 'atual': _versao(), 'nova': tag, 'url': rel.get('html_url'),
               'notas': (rel.get('body') or '')[:800], 'tem_nova': _semver(tag) > _semver(_versao())}
    except Exception as e:
        out = {'ok': False, 'erro': str(e)}
    print(json.dumps(out, ensure_ascii=False))


def _pasta_app():
    """onde a versao auto-instalada mora (estavel entre atualizacoes)"""
    if sys.platform == 'darwin':
        return os.path.join(appdata(), 'NoeVFX', 'A2R Link')
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.join(appdata(), '..', 'Local'), 'Programs', 'A2R Link')
    return os.path.expanduser('~/.local/share/A2R Link')


def self_update():
    """baixa o release mais novo, instala numa pasta estavel e roda o instalador dele"""
    import tempfile, zipfile, shutil, subprocess, io
    rel = _release_mais_novo()
    tag = str(rel.get('tag_name') or '').lstrip('vV')
    url_zip = next((a['browser_download_url'] for a in rel.get('assets', [])
                    if str(a.get('browser_download_url', '')).lower().endswith('.zip')), rel.get('zipball_url'))
    if not url_zip:
        raise RuntimeError(T('o release %s nao tem pacote para baixar', 'release %s has no downloadable package') % tag)
    print(T('baixando %s...', 'downloading %s...') % tag, flush=True)
    buf = urllib.request.urlopen(urllib.request.Request(url_zip, headers={'User-Agent': 'a2r-link-updater'}), timeout=300).read()
    destino = _pasta_app()
    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(buf)).extractall(td)
        raiz = next((os.path.join(td, d) for d in os.listdir(td) if os.path.isdir(os.path.join(td, d))), td)
        if not os.path.isfile(os.path.join(raiz, 'install.py')):      # pacote com uma pasta por sistema (Windows/ e Mac/)
            raiz = os.path.join(raiz, 'Mac' if sys.platform == 'darwin' else 'Windows')
        if not os.path.isfile(os.path.join(raiz, 'install.py')):
            raise RuntimeError(T('o pacote baixado nao tem install.py — atualizacao cancelada',
                                 'downloaded package has no install.py — update cancelled'))
        # copia completa ao lado e so entao troca: se algo falhar no meio, a versao instalada continua inteira
        novo, velho = destino + '.novo', destino + '.antigo'
        for sobra in (novo, velho):
            shutil.rmtree(sobra, ignore_errors=True)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copytree(raiz, novo)
        os.chdir(os.path.dirname(destino))      # o painel nos inicia DENTRO da pasta instalada; no Windows ela nao sai enquanto for a pasta atual
        if os.path.isdir(destino):
            os.rename(destino, velho)
        try:
            os.rename(novo, destino)
        except OSError:
            if os.path.isdir(velho) and not os.path.isdir(destino):
                os.rename(velho, destino)       # devolve a versao que estava
            raise
        shutil.rmtree(velho, ignore_errors=True)
    print(T('instalando...', 'installing...'), flush=True)
    r = subprocess.run([sys.executable, os.path.join(destino, 'install.py')],
                       capture_output=True, text=True, cwd=destino)
    sys.stdout.write(r.stdout or '')
    if r.returncode != 0:
        sys.stderr.write(r.stderr or '')
        raise RuntimeError(T('o instalador da nova versao falhou', 'the new version installer failed'))
    print(T('atualizado para %s — feche e reabra o Premiere/After', 'updated to %s — close and reopen Premiere/After') % tag)


def status():
    """imprime uma linha JSON: o DaVinci esta respondendo? (usado pelo painel para o indicador de conexao)"""
    import gen
    try:
        r, p = gen._connect()
        proj = p.GetName() if p else None
        print(json.dumps({'resolve': True, 'projeto': proj, 'versao': r.GetVersionString()}))
    except Exception as e:
        print(json.dumps({'resolve': False, 'erro': str(e)}))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'copy':
        copy_premiere()
    elif cmd == 'copy-ae':
        copy_ae()
    elif cmd == 'status':
        status()
    elif cmd == 'check-update':
        check_update()
    elif cmd == 'self-update':
        self_update()
    elif cmd == 'remap-info':
        remap_info()
    elif cmd == 'paste':
        paste(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
