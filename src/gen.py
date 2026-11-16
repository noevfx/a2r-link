"""gen: spec JSON (valores JA em unidades do Resolve) -> timeline no DaVinci Resolve Studio com chaves no Inspector.

Fluxo: importa midia -> timeline temporaria pela API (posicao, trilhas, velocidade, valores estaticos) ->
Export DRT -> injeta chaves (drtlib) -> ImportTimelineFromFile -> renomeia.  Sem Fusion, sem XML de intercambio.

Spec (version 1):
{ "name": "Take", "clips": [ {
    "media": "C:/x.mp4", "media_fps": 25.0,
    "src_in": 0, "src_out": 120,          # quadros da MIDIA, src_out exclusivo
    "rec_start": 0, "track": 1,           # quadros da timeline, relativo ao inicio dela
    "speed": 100.0,                       # % (>0); reverso ainda nao suportado
    "static": {"Pan":0,"Tilt":0,"ZoomX":1,"ZoomY":1,"RotationAngle":0,"Opacity":100, ...},
    "keys":   {"Pan": [[d, px], ...], "ZoomX": [[d, v], ...], ...}   # d = quadros desde o inicio do clipe NA TIMELINE
} ] }
"""
import os, sys, re, time, json, uuid, math, tempfile, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'darwin':        # caminhos oficiais do scripting do DaVinci (documentacao Blackmagic)
    os.environ.setdefault('RESOLVE_SCRIPT_API', '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting')
    os.environ.setdefault('RESOLVE_SCRIPT_LIB', '/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so')
elif sys.platform == 'win32':
    os.environ.setdefault('RESOLVE_SCRIPT_API', r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting')
    os.environ.setdefault('RESOLVE_SCRIPT_LIB', r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll')
else:
    os.environ.setdefault('RESOLVE_SCRIPT_API', '/opt/resolve/Developer/Scripting')
    os.environ.setdefault('RESOLVE_SCRIPT_LIB', '/opt/resolve/libs/Fusion/fusionscript.so')
sys.path.append(os.path.join(os.environ['RESOLVE_SCRIPT_API'], 'Modules'))
import DaVinciResolveScript as dvr
import drtlib as L
from normalizer import _FX_CAMEL
from i18n import T

# propriedade -> (grupo, param, escala): valor_guardado = valor_usuario / escala  ('W' e 'H' = tamanho da timeline)
PARAM = {'Pan': ((4, 40), 'W'), 'Tilt': ((4, 41), 'H'), 'ZoomX': ((4, 42), 1), 'ZoomY': ((4, 43), 1),
         'Pitch': ((4, 45), 1), 'Yaw': ((4, 46), 1), 'RotationAngle': ((4, 47), 1),
         'CropLeft': ((6, 54), 'W'), 'CropRight': ((6, 55), 'W'), 'CropTop': ((6, 56), 'H'), 'CropBottom': ((6, 57), 'H'),
         'CropSoftness': ((6, 58), 1), 'Opacity': ((2, 1), 1)}
DEFAULT = {'Pan': 0, 'Tilt': 0, 'ZoomX': 1.0, 'ZoomY': 1.0, 'Pitch': 0, 'Yaw': 0, 'RotationAngle': 0,
           'CropLeft': 0, 'CropRight': 0, 'CropTop': 0, 'CropBottom': 0, 'CropSoftness': 0, 'Opacity': 100.0}
NOKEY = ('AnchorPointX', 'AnchorPointY', 'FlipX', 'FlipY', 'CompositeMode', 'CropRetain')   # chaves nao suportadas na v1


def _connect():
    r = dvr.scriptapp('Resolve')
    if not r:
        raise RuntimeError(T('DaVinci nao responde a API (External scripting = Local? reiniciar?)',
                             'DaVinci does not answer the API (External scripting = Local? restart?)'))
    return r, r.GetProjectManager().GetCurrentProject()


def _nome_livre(p, base):
    usados = {p.GetTimelineByIndex(i).GetName() for i in range(1, p.GetTimelineCount() + 1)}
    if base not in usados:
        return base
    n = 2
    while '%s %d' % (base, n) in usados:
        n += 1
    return '%s %d' % (base, n)


def _midia(mp, path, cache=None, organizar=False, recursivo=False):
    """devolve o MediaPoolItem da midia. Organizando: importa para a pasta ATUAL (o sub-bin da timeline), uma vez por arquivo;
    sem organizar: reaproveita o clipe da raiz se ja existir (comportamento antigo); com recursivo, busca em todos os bins."""
    chave = path.replace('/', '\\').lower()
    if cache is not None and chave in cache:
        return cache[chave]
    item = None
    if not organizar:
        if recursivo:
            item = _acha_media(mp.GetRootFolder(), chave)
        else:
            for c in mp.GetRootFolder().GetClipList():
                if (c.GetClipProperty('File Path') or '').replace('/', '\\').lower() == chave:
                    item = c; break
    if item is None:
        got = mp.ImportMedia([path])
        if not got:
            raise FileNotFoundError(T('nao importou: ', 'could not import: ') + path)
        item = got[0]
    if cache is not None:
        cache[chave] = item
    return item


def _subpasta(pasta, nome):
    for f in pasta.GetSubFolderList() or []:
        if f.GetName() == nome:
            return f
    return None


def _folder_de(pasta, mpi):
    """pasta do Media Pool que contem o MediaPoolItem mpi (busca recursiva)."""
    try:
        uid = mpi.GetUniqueId()
    except Exception:
        return None
    for c in pasta.GetClipList() or []:
        try:
            if c.GetUniqueId() == uid:
                return pasta
        except Exception:
            continue
    for f in pasta.GetSubFolderList() or []:
        r = _folder_de(f, mpi)
        if r is not None:
            return r
    return None


def _organiza(mp, bin_nome, tl_nome):
    """Media Pool: bin do projeto (reaproveita se existir) > sub-bin da timeline (nome livre). Deixa o sub-bin como pasta atual."""
    raiz = mp.GetRootFolder()
    b = _subpasta(raiz, bin_nome) or mp.AddSubFolder(raiz, bin_nome)
    if not b:
        raise RuntimeError(T('nao criou o bin "%s" no Media Pool', 'could not create bin "%s" in the Media Pool') % bin_nome)
    nome, n = tl_nome, 2
    while _subpasta(b, nome):
        nome = '%s %d' % (tl_nome, n); n += 1
    sb = mp.AddSubFolder(b, nome)
    if not sb:
        raise RuntimeError(T('nao criou o sub-bin "%s"', 'could not create the sub-bin "%s"') % nome)
    mp.SetCurrentFolder(sb)
    return b, sb


def _fps_exato(f):
    for nom, ex in ((23.976, 24000 / 1001), (29.97, 30000 / 1001), (47.952, 48000 / 1001), (59.94, 60000 / 1001)):
        if abs(f - nom) < 0.01:
            return ex
    return f


RAMPA_NOS_EXTRAS = False    # False = so os nos da origem (mesma quantidade); True = nos extras ate fechar a tolerancia


def _timemap_mapa(rm, rec0, fe, tot, mfps, uid):
    """MediaTimemapBA para clipe com remap. Com rm['nodes'] usa a forma EASED do Studio 21 (nos esparsos
    + alcas = rampa EDITAVEL no Inspector); sem nos cai na amostragem densa.
    O ease do Resolve e 'canto arredondado': entre nos a curva e a corda reta, e cada no com alca troca o
    canto por uma cubica que sai tangente de uma corda e chega tangente na outra. Entao a curva de origem
    vira o poligono das suas TANGENTES: os nos da origem marcam onde a curva e tocada, cada no do Resolve
    fica no cruzamento de duas tangentes vizinhas e a alca cobre o trecho entre os dois toques. Uma rampa
    do Premiere (velocidade A -> velocidade B) da 1 no. So entra toque extra onde o desvio contra a
    verdade amostrada (rm['dense'] ou rm['points']) passa da tolerancia."""
    pts = rm['points']; src0 = pts[0][1]
    nds = rm.get('nodes')
    if not nds:
        pontos = ([(rec0, src0)] if rec0 > 1e-9 else []) + [(rec0 + d / fe, s) for d, s in pts[1:]]
        return L.timemap_encode(pontos, (tot - 1) / mfps, pontos[-1][0], uid)
    denso = [(rec0, src0)]                                # verdade amostrada da origem
    for d, s in (rm.get('dense') or pts)[1:]:
        if rec0 + d / fe > denso[-1][0] + 1e-9:
            denso.append((rec0 + d / fe, s))
    dx = [q_[0] for q_ in denso]; fim = dx[-1]; q = 1.0 / fe

    def ref(t):
        if t <= rec0:
            return src0
        if t >= fim:
            return denso[-1][1]
        i = bisect.bisect_right(dx, t)
        a, b = denso[i - 1], denso[i]
        return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])

    def incl(t, lado):                                    # inclinacao de um lado so (3 pontos, 1 quadro de passo)
        d = q * lado
        if rec0 - 1e-9 <= t + 2 * d <= fim + 1e-9:
            return (-3 * ref(t) + 4 * ref(t + d) - ref(t + 2 * d)) / (2 * d)
        if rec0 - 1e-9 <= t + d <= fim + 1e-9:
            return (ref(t + d) - ref(t)) / d
        return None

    sobe = all(b_[1] >= a_[1] - 1e-9 for a_, b_ in zip(denso, denso[1:]))

    def toque(t, liso=False):                             # liso = ponto no meio da curva (sem quina): uma inclinacao so
        if liso and rec0 < t - q and t + q < fim:
            c = (ref(t + q) - ref(t - q)) / (2 * q)
            return [t, ref(t), c, c]
        sl, sr = incl(t, -1), incl(t, 1)
        sl, sr = (sr if sl is None else sl), (sl if sr is None else sr)
        if sobe:                                          # curva que nunca volta: ruido da estimativa nao pode inventar reverso
            sl, sr = max(sl, 0.0), max(sr, 0.0)
        return [t, ref(t), sl, sr]

    ts = [rec0]
    for t in sorted(rec0 + n_[0] / fe for n_ in nds):     # nos da origem dentro do take, a >= 1 quadro um do outro
        if t - ts[-1] >= q and fim - t >= q:
            ts.append(t)
    ts.append(fim)
    if fim - rec0 < 2 * q:
        return L.timemap_encode([(fim, denso[-1][1])], (tot - 1) / mfps, fim, uid)
    bps = [toque(t) for t in ts]
    FOLGA = 0.98                                          # janelas vizinhas nao encostam uma na outra

    def montar():
        n = len(bps)
        plano = [j in (0, n - 1) or abs(b[2] - b[3]) > 0.03 * max(1.0, abs(b[2]), abs(b[3])) for j, b in enumerate(bps)]
        vert = [None] * (n - 1); ruins = []
        for j in range(n - 1):
            (ta, ya, _, sa), (tb, yb, sb, _) = bps[j], bps[j + 1]
            c = (yb - ya) / (tb - ta); lim = 0.02 * max(1.0, abs(c))
            if abs(sa - c) <= lim and abs(sb - c) <= lim:                 # trecho reto: a corda ja resolve
                continue
            x = (yb - ya + sa * ta - sb * tb) / (sa - sb) if abs(sa - sb) > 1e-9 else None
            yv = ya + sa * (x - ta) if x is not None else None
            if x is None or not ta + 0.02 * (tb - ta) < x < tb - 0.02 * (tb - ta) or not min(ya, yb) - 0.25 / mfps <= yv <= max(ya, yb) + 0.25 / mfps:
                ruins.append(j); plano[j] = plano[j + 1] = True         # tangentes nao se cruzam no trecho (curva vira dentro dele)
                continue
            vert[j] = [x, yv, ta, tb]
        nos = []
        for j, b in enumerate(bps):
            if plano[j]:
                nos.append([b[0], b[1], None, None])
            if j < n - 1 and vert[j]:
                nos.append(vert[j])
        out = []
        for i, (x, y, ta, tb) in enumerate(nos):          # alca sempre EM CIMA da corda real (fora dela o render sai preto)
            h = None
            if ta is not None:
                pv, nx = nos[i - 1], nos[i + 1]
                inX, outX = (ta - x) * FOLGA, (tb - x) * FOLGA
                h = [inX, inX * (y - pv[1]) / (x - pv[0]), outX, outX * (nx[1] - y) / (nx[0] - x), 0.0, 0.0]
            out.append((x, y, h))
        return out, ruins

    TOL = 1.0                                             # tolerancia em quadros de midia (x velocidade local, ver tol_t)
    passo = q / 4

    def tol_t(tt):                                        # adaptativa: quadro de midia errado e invisivel numa rajada
        sl_ = abs(ref(tt + q) - ref(tt - q)) / (2 * q) if tt - q > rec0 else 1.0     # (imagem a 30x+), mas conta em trecho parado
        return TOL * min(max(sl_, 1.0), 8.0)

    def vira(j):                                          # quadro do trecho onde a velocidade mais foge da corda (pico/vale)
        ta, tb = bps[j][0], bps[j + 1][0]; c = (bps[j + 1][1] - bps[j][1]) / (tb - ta)
        t, melhor, tm = ta + q, -1.0, None
        while t <= tb - q + 1e-9:
            dv = abs((ref(t + q) - ref(t - q)) / (2 * q) - c)
            if dv > melhor:
                melhor, tm = dv, t
            t += q
        return tm

    teto = None                                           # None = sem limite de nos
    if not RAMPA_NOS_EXTRAS:
        if not montar()[1]:
            teto = 0                                      # os nos da origem bastam (rampa do Premiere): nada a refinar
        else:                                             # curva vira entre dois nos (Bezier do AE): os toques saem da propria
            teto = max(len(ts), len(nds))                 # curva, ate a MESMA quantidade de nos da origem
            bps = [toque(rec0), toque(fim)]
    for _ in range(60 if teto != 0 else 0):
        out, ruins = montar()
        if teto and len(out) >= teto and not ruins:
            break
        cur = [(0.0, 0.0, None)] + out
        novo = None
        for j in ruins:
            if bps[j + 1][0] - bps[j][0] >= 2 * q:
                novo = vira(j)
                break
        if novo is None:
            t, tm, mrel = rec0, None, 0.0
            while t <= fim:
                rel = abs(L.timemap_eval(cur, t) - ref(t)) * mfps / tol_t(t)
                if rel > mrel and all(abs(t - b_[0]) >= q for b_ in bps):     # so onde ainda cabe um toque novo
                    mrel, tm = rel, t
                t += passo
            if mrel <= 1.0 or tm is None:
                break
            novo = tm
        novo = rec0 + round((novo - rec0) * fe) / fe      # toque novo sempre em quadro cheio (inclinacao limpa)
        if any(abs(novo - b[0]) < 0.75 * q for b in bps):
            break                                         # ja ha toque ali: nao da pra apertar mais
        antes = list(bps)
        bps.append(toque(novo, True)); bps.sort(key=lambda b_: b_[0])
        if teto and len(montar()[0]) > teto:
            bps = antes                                   # passaria da quantidade da origem: fica como estava
            break
    if teto:                                              # quantidade travada: acerta a POSICAO de cada toque (busca local)
        def pior():
            o_, r_ = montar()
            if r_ or len(o_) > teto:
                return 1e9
            c_ = [(0.0, 0.0, None)] + o_
            t, m = rec0, 0.0
            while t <= fim:                               # erro medio em quadros de midia: privilegia o desenho geral da curva
                m += abs(L.timemap_eval(c_, t) - ref(t)) * mfps
                t += passo * 2
            return m
        base = pior()
        for _ in range(6):
            mexeu = False
            for j in range(1, len(bps) - 1):
                for d in (-8, -4, -2, -1, 1, 2, 4, 8):
                    t = bps[j][0] + d * q
                    if not bps[j - 1][0] + q <= t <= bps[j + 1][0] - q:
                        continue
                    velho = bps[j]; bps[j] = toque(t, True); e = pior()
                    if e < base - 1e-6:
                        base, mexeu = e, True
                    else:
                        bps[j] = velho
            if not mexeu:
                break
    out, _ = montar()
    return L.timemap_encode_eased(out, (tot - 1) / mfps, out[-1][0], uid)


def _itens_xml(tl, kind):
    """[(trilha, start)] dos itens que viram blocos Sm2Ti*Clip no XML exportado — so midia real
    (tem File Path). Geradores/titulos entram em GetItemListInTrack mas sao outra tag no XML."""
    out = []
    for trk in range(1, tl.GetTrackCount(kind) + 1):
        for it in tl.GetItemListInTrack(kind, trk) or []:
            mi = it.GetMediaPoolItem()
            if mi and (mi.GetClipProperty('File Path') or ''):
                out.append((trk, it.GetStart()))
    return out


def _acha_media(pasta, chave):
    """MediaPoolItem cujo File Path bate com chave, procurando em todas as pastas (recursivo)."""
    for c in pasta.GetClipList() or []:
        if (c.GetClipProperty('File Path') or '').replace('/', '\\').lower() == chave:
            return c
    for f in pasta.GetSubFolderList() or []:
        r = _acha_media(f, chave)
        if r is not None:
            return r
    return None


def build(spec, cleanup=True, log=print):
    r, p = _connect(); mp = p.GetMediaPool()
    clips = spec['clips']
    avisos = []
    if spec.get('rampa') == 'precisa':      # chave "Rampa" do painel: um ponto por quadro (segue a origem), sem nos com alca
        for c_ in clips + (spec.get('audio_clips') or []):
            rm_ = c_.get('remap')
            if rm_ and rm_.get('nodes'):
                rm_.pop('nodes')
                if rm_.get('dense'):
                    pts_ = [rm_['dense'][0]]
                    for q_ in rm_['dense'][1:]:
                        if q_[0] > pts_[-1][0] + 1e-6:
                            pts_.append(q_)
                    if len(pts_) > 1:
                        rm_['points'] = pts_
    # destino 'existente': a timeline de MESMO NOME recebe os takes (mesma posicao/trilha; colisao
    # = o antigo sai). Se nao existir, cai no fluxo normal com aviso. Os patches (timemap/keys) so
    # entram via DRT, entao o append tambem faz export -> patch -> reimport -> substitui a original.
    alvo = None
    if spec.get('destino') == 'existente':
        for i in range(1, p.GetTimelineCount() + 1):
            t = p.GetTimelineByIndex(i)
            if t.GetName() == spec.get('name'):
                alvo = t; break
        if alvo is None:
            avisos.append(T('timeline "%s" nao existe no projeto: criando nova',
                            'timeline "%s" does not exist in the project: creating a new one') % spec.get('name'))
    append_mode = alvo is not None
    nome_final = spec.get('name', 'A2R Link') if append_mode else _nome_livre(p, spec.get('name', 'A2R Link'))
    organizar = bool(spec.get('bin')) and not append_mode
    sub_bin = None
    if organizar:
        _, sub_bin = _organiza(mp, spec['bin'], spec.get('name', 'A2R Link'))
        log('bin "%s" > sub-bin "%s"' % (spec['bin'], sub_bin.GetName()))   # linha de protocolo (o painel faz parse)
    cache_midia = {}
    pasta_alvo = None
    if append_mode:
        pasta_alvo = _folder_de(mp.GetRootFolder(), alvo.GetMediaPoolItem())   # a timeline substituida volta pro mesmo bin
        if pasta_alvo is not None:
            mp.SetCurrentFolder(pasta_alvo)                                  # midia nova cai no bin dela, nao espalha
        # sandbox: deletes/appends rodam numa copia; a original so e substituida depois do reimport
        try:
            tl = alvo.DuplicateTimeline('_tmp_%s' % uuid.uuid4().hex[:6]) or alvo
        except Exception:
            tl = alvo
        log(T('timeline existente "%s": adicionando/substituindo takes', 'existing timeline "%s": adding/replacing takes') % nome_final)
    else:
        tmp_nome = _nome_livre(p, '_tmp_%s' % uuid.uuid4().hex[:6])
        fps_proj = None
        if spec.get('fps'):   # timelineFrameRate e read-only apos a criacao: entra pelo frame rate do projeto
            fr = float(spec['fps'])
            fps_proj = p.GetSetting('timelineFrameRate')
            alvo = str(int(round(fr))) if abs(fr - round(fr)) < 1e-4 else ('%g' % fr)
            p.SetSetting('timelineFrameRate', alvo)
        else:
            log(T('AVISO: a sequencia nao informou taxa de quadros — a timeline herda a do projeto',
                  'WARNING: the sequence did not report a frame rate — the timeline inherits the project one'))
        tl = mp.CreateEmptyTimeline(tmp_nome)
        if fps_proj is not None:   # devolve o do projeto; a timeline fica com o dela
            for _ in range(3):   # o restore as vezes nao pega de primeira — confirma pelo read-back
                p.SetSetting('timelineFrameRate', fps_proj)
                if abs(float(p.GetSetting('timelineFrameRate')) - float(fps_proj)) < 1e-3:
                    break
        if not tl:
            raise RuntimeError(T('nao criou a timeline temporaria (aviso aberto no DaVinci? olhar os dois monitores)',
                                 'could not create the temporary timeline (a dialog open in DaVinci? check both monitors)'))
        if spec.get('width') and spec.get('height'):
            tl.SetSetting('useCustomSettings', '1')
            tl.SetSetting('timelineResolutionWidth', str(int(round(spec['width']))))
            tl.SetSetting('timelineResolutionHeight', str(int(round(spec['height']))))
    p.SetCurrentTimeline(tl)
    t0 = tl.GetStartFrame(); tl_fps = float(tl.GetSetting('timelineFrameRate'))
    W = int(tl.GetSetting('timelineResolutionWidth')); H = int(tl.GetSetting('timelineResolutionHeight'))
    log(T('timeline %dx%d @ %s fps', 'timeline %dx%d @ %s fps') % (W, H, tl_fps))
    if not append_mode and spec.get('fps') and abs(tl_fps - float(spec['fps'])) > 0.02:
        log(T('AVISO: a sequencia e %s fps mas a timeline saiu a %s fps — verifique',
              'WARNING: the sequence is %s fps but the timeline came out at %s fps — please check') % (spec['fps'], tl_fps))
    # trilhas
    ntr = max([c.get('track', 1) for c in clips] + [t.get('track', 1) for t in spec.get('titulos') or []] + [a.get('track', 1) for a in spec.get('ajustes') or []] or [0])
    while tl.GetTrackCount('video') < ntr:
        tl.AddTrack('video')
    # trilhas de audio
    aclips = spec.get('audio_clips') or []
    ntra = max([a.get('track', 1) for a in aclips] or [0])
    while tl.GetTrackCount('audio') < ntra:
        tl.AddTrack('audio')
    if append_mode:   # colisao por (trilha, intervalo): o antigo sai para o novo entrar na mesma posicao
        for c in clips:
            rm = c.get('remap')
            dur = int(math.ceil(rm['points'][-1][0])) if rm else int(math.ceil((c['src_out'] - c['src_in']) * tl_fps / c['media_fps'] / (c.get('speed', 100.0) / 100.0)))
            ini_, fim_ = t0 + c['rec_start'], t0 + c['rec_start'] + dur
            mortos = [it for it in tl.GetItemListInTrack('video', c.get('track', 1)) or []
                      if it.GetStart() < fim_ and it.GetEnd() > ini_]
            if mortos:
                tl.DeleteClips(mortos)
        for a in aclips:
            dur = int(a.get('rec_dur') or 0)
            if dur <= 0:
                continue
            ini_, fim_ = t0 + a['rec_start'], t0 + a['rec_start'] + dur
            mortos = [it for it in tl.GetItemListInTrack('audio', a.get('track', 1)) or []
                      if it.GetStart() < fim_ and it.GetEnd() > ini_]
            if mortos:
                tl.DeleteClips(mortos)
    # 1) coloca os clipes em ORDEM CRONOLOGICA; a velocidade vem logo apos cada um com RippleTimeline
    #    (a duracao passa a D0/s mantendo o trecho inteiro de midia; o ripple empurra so o que vem depois, que ainda nao existe)
    itens = [None] * len(clips)
    for i in sorted(range(len(clips)), key=lambda n: (clips[n]['rec_start'], clips[n].get('track', 1))):
        c = clips[i]
        if c.get('speed', 100.0) <= 0 and not c.get('remap'):
            raise NotImplementedError(T('velocidade <= 0 (reverso/congelar) ainda nao validada',
                                        'speed <= 0 (reverse/freeze) not validated yet'))
        mi = _midia(mp, c['media'], cache_midia, organizar, recursivo=append_mode)
        c['_total'] = max(1, int(float(mi.GetClipProperty('Frames') or 0)))
        rm = c.get('remap')
        if rm:   # time remap: a janela de midia vai onde a curva cobre, mas o record so precisa
            #      da duracao final — janela cheia cobria os vizinhos e o paste morria no lookup
            pts = rm['points']; total = c['_total']
            sa, sb = min(q[1] for q in pts), max(q[1] for q in pts)
            sf = max(0, int(math.floor(sa * c['media_fps']))); ef = min(total - 1, int(math.ceil(sb * c['media_fps'])))
            c['_rm'] = {'sf': sf, 'ef': ef, 'total': total}
            dr_media = max(1, int(round(math.ceil(pts[-1][0]) * c['media_fps'] / tl_fps)))   # round: ceil arredondava 359.0004 p/ 360 e cobria o vizinho
            ini, fim = sf, min(total, sf + dr_media)
            if sa == sb:   # timemap plano = freeze frame: basta 1 quadro de janela (a curva estica)
                fim = ini + 1
            if append_mode:   # redundante com dr_media, mantido por seguranca
                fim = max(ini + 1, fim)
        else:
            ini, fim = c['src_in'], c['src_out']
            if append_mode and abs(c.get('speed', 100.0) - 100.0) > 1e-6:   # idem: entra ja com a duracao final
                fim = max(ini + 1, min(fim, int(ini + (c['src_out'] - c['src_in']) / (c['speed'] / 100.0))))
        ok = mp.AppendToTimeline([{'mediaPoolItem': mi, 'startFrame': ini, 'endFrame': fim,   # endFrame e EXCLUSIVO (provado: 0..99 -> 99 quadros)
                                   'mediaType': 1, 'trackIndex': c.get('track', 1), 'recordFrame': t0 + c['rec_start']}])
        if not ok:
            raise RuntimeError(T('AppendToTimeline falhou no clipe %d', 'AppendToTimeline failed on clip %d') % i)
        cand = [it for it in (tl.GetItemListInTrack('video', c.get('track', 1)) or []) if it.GetStart() == t0 + c['rec_start']]
        if len(cand) != 1:
            raise RuntimeError(T('clipe %d: esperava 1 item em %d, achei %d (sobreposicao?)', 'clip %d: expected 1 item at %d, found %d (overlap?)') % (i, t0 + c['rec_start'], len(cand)))
        it = cand[0]; d0 = it.GetDuration()
        if rm:
            dr = int(math.ceil(rm['points'][-1][0]))
            plano = len({q[1] for q in rm['points']}) == 1   # freeze: SetSpeed desnecessario (a curva ja estica)
            if not append_mode and not plano:
                pct = 100.0 * d0 / dr
                if abs(pct - 100.0) > 0.01:
                    it.SetSpeed({'Percentage': pct, 'RippleTimeline': False})   # ripple=True divide clipes das OUTRAS trilhas (append cronologico ja garante a propria)
            c['_rm']['dur'] = dr
        elif abs(c.get('speed', 100.0) - 100.0) > 1e-6:
            # sem SetSpeed: com ripple ele divide clipes das outras trilhas; sem ripple, nao estica.
            # o record final sai pelo patch Duration+timemap (mesmo caminho do append e do audio)
            c['_rec_dur'] = int(round((c['src_out'] - c['src_in']) * tl_fps / c['media_fps'] / (c['speed'] / 100.0)))
        if c.get('cor'):
            it.SetClipColor(c['cor'])
        itens[i] = it
    # 1b) itens de audio: mesma janela de midia/posicao; volume/pan/fades sao nativos da API
    #     (SetSpeed nao estica audio -> a duracao final entra pelo patch de <Duration>+timemap)
    aitens = [None] * len(aclips)
    for i in sorted(range(len(aclips)), key=lambda n: (aclips[n]['rec_start'], aclips[n].get('track', 1))):
        a = aclips[i]
        if a.get('speed', 100.0) <= 0 and not a.get('remap'):
            avisos.append(T('audio %d com velocidade <= 0: ignorado', 'audio %d with speed <= 0: skipped') % i); continue
        mi = _midia(mp, a['media'], cache_midia, organizar, recursivo=append_mode)
        a['_total'] = max(1, int(float(mi.GetClipProperty('Frames') or 0)))
        rm = a.get('remap')
        if rm:
            pts = rm['points']; sa, sb = min(q[1] for q in pts), max(q[1] for q in pts)
            ini = max(0, int(math.floor(sa * a['media_fps'])))
            fim = min(a['_total'], ini + max(1, int(round(math.ceil(pts[-1][0]) * a['media_fps'] / tl_fps))))
        else:
            ini, fim = a['src_in'], a['src_out']
        if append_mode and a.get('rec_dur'):   # sem SetSpeed: entra ja com a duracao final para nao sobrepor vizinhos
            fim = max(ini + 1, min(fim, int(ini + a['rec_dur'] * a['media_fps'] / tl_fps)))
        ok = mp.AppendToTimeline([{'mediaPoolItem': mi, 'startFrame': ini, 'endFrame': fim,
                                   'mediaType': 2, 'trackIndex': a.get('track', 1), 'recordFrame': t0 + a['rec_start']}])
        if not ok:
            avisos.append(T('audio %d nao entrou na trilha %d', 'audio %d did not land on track %d') % (i, a.get('track', 1))); continue
        cand = [it for it in (tl.GetItemListInTrack('audio', a.get('track', 1)) or []) if it.GetStart() == t0 + a['rec_start']]
        if len(cand) != 1:
            avisos.append(T('audio %d: esperava 1 item em %d, achei %d', 'audio %d: expected 1 item at %d, found %d') % (i, t0 + a['rec_start'], len(cand))); continue
        it = cand[0]
        if a.get('cor'):
            it.SetClipColor(a['cor'])
        vk = a.get('vol_keys')
        if vk:
            first = vk[0][1]
            if it.SetProperty('AudioVolume', first if abs(first) > 1e-9 else -1e-3) is False:   # faz o param existir no blob
                avisos.append(T('audio %d: SetProperty(AudioVolume) falhou — chaves de volume nao aplicadas',
                                'audio %d: SetProperty(AudioVolume) failed — volume keys not applied') % i)
                a['_vol_skip'] = True
        elif a.get('volume_db'):
            it.SetProperty('AudioVolume', a['volume_db'])
        if a.get('pan') is not None:
            it.SetProperty('AudioPan', a['pan'])
        aitens[i] = it
    keymaps = []
    for i, (c, it) in enumerate(zip(clips, itens)):
        km = {}
        stt, kys = c.get('static') or {}, c.get('keys') or {}
        zx = stt.get('ZoomX'); zy = stt.get('ZoomY')
        gang_off = (zx is not None and zy is not None and abs(zx - zy) > 1e-9) or \
                   ('ZoomX' in kys and 'ZoomY' in kys and any(abs(a[1] - b[1]) > 1e-9 for a, b in zip(kys['ZoomX'], kys['ZoomY'])))
        if gang_off:
            it.SetProperty('ZoomGang', False)          # escala nao uniforme: X e Y independentes
        if c.get('composite'):                         # blend mode (enum COMPOSITE_*); serializa no DRT
            if it.SetProperty('CompositeMode', int(c['composite'])) is False:
                avisos.append(T('clipe %d: CompositeMode nao aplicado', 'clip %d: CompositeMode not applied') % i)
        for prop, val in stt.items():
            if val != DEFAULT.get(prop):
                if it.SetProperty(prop, val) is False:
                    avisos.append(T('clipe %d: SetProperty(%s) falhou — valor nao aplicado', 'clip %d: SetProperty(%s) failed — value not applied') % (i, prop))
        rm_ho = c.get('remap')
        if rm_ho:
            ho = rm_ho['points'][0][1] * _fps_exato(tl_fps)      # origem do mapa: record = src0
        else:
            ho = c['src_in'] / c['media_fps'] * _fps_exato(tl_fps)   # patch timemap com rec0=src0 (qualquer velocidade)
        for prop, pts in (c.get('keys') or {}).items():
            if prop in NOKEY or prop not in PARAM:
                avisos.append(T('clipe %d: chave em %s nao suportada, ignorada', 'clip %d: keyframe on %s unsupported, skipped') % (i, prop)); continue
            (gid, pid), esc = PARAM[prop]
            div = W if esc == 'W' else H if esc == 'H' else 1
            first = pts[0][1]
            forca = first if first != DEFAULT[prop] else first + (1e-3 if prop != 'Opacity' else -1e-3)
            if it.SetProperty(prop, forca) is False:   # sem o parametro no blob as chaves morrem no patch (e o inject levantaria KeyError)
                avisos.append(T('clipe %d: SetProperty(%s) falhou — %d chave(s) nao aplicadas', 'clip %d: SetProperty(%s) failed — %d key(s) not applied') % (i, prop, len(pts)))
                continue
            km[(gid, pid)] = [(int(round(p[0] + ho)), L.FLAG_EASE, p[1] / div, (p[2] / div, p[3] / div))
                              if len(p) > 3 else (int(round(p[0] + ho)), p[1] / div) for p in pts]
        keymaps.append(km)
    # 2b) titulos (clipes graficos do Premiere / texto): Text+ via API na posicao do playhead,
    #     depois realocados para trilha/inicio certos no patch DRT (a API nao aceita trilha)
    titulos_abs = []
    # a insercao de Text+ cai no playhead na trilha ativa e pode SOBRESCREVER clipe:
    # cada titulo entra numa zona vazia no fim da timeline; o patch DRT realoca depois.
    fim_tl = max([t0 + c['rec_start'] + (int(c['_rm']['dur']) if c.get('_rm') else
                  int(round((c['src_out'] - c['src_in']) * tl_fps / c['media_fps'] / (c.get('speed', 100.0) / 100.0)))) for c in clips] or [t0])
    if append_mode:   # a timeline ja tem conteudo: a zona vazia comeca no fim REAL dela, nao no fim dos clipes novos
        try: fim_tl = max(fim_tl, int(tl.GetEndFrame()))
        except Exception: pass
    rec_livre = fim_tl + int(tl_fps)   # 1s de margem
    for tt in spec.get('titulos') or []:
        sec = rec_livre / tl_fps
        tc = '%02d:%02d:%02d:%02d' % (int(sec // 3600), int((sec % 3600) // 60), int(sec % 60), int(round((sec % 1) * tl_fps)))
        rec_livre += tt['rec_dur'] + 2
        try:
            tl.SetCurrentTimecode(tc)
            item = tl.InsertFusionTitleIntoTimeline('Text+')
        except Exception as e:
            avisos.append(T('titulo "%s" nao inserido (%s)', 'title "%s" not inserted (%s)') % (tt['nome'], e)); continue
        if not item:
            avisos.append(T('titulo "%s" nao inserido', 'title "%s" not inserted') % tt['nome']); continue
        try:
            rec_livre = max(rec_livre, item.GetStart() + item.GetDuration() + 2)   # a duracao inserida pode passar do spec
        except Exception:
            pass
        try:
            item.SetName(tt['nome'])
            fc = item.GetFusionCompByIndex(1)
            tool = (fc.FindTool('Text1') or getattr(fc, 'Text1', None)) if fc else None
            if tool and tt.get('texto'):
                try: tool.StyledText = tt['texto']
                except Exception:
                    try: tool.SetInput('StyledText', tt['texto'])
                    except Exception: pass
            for prop_, v_ in (('Pan', tt.get('pan')), ('Tilt', tt.get('tilt')), ('RotationAngle', tt.get('rot')),
                              ('Opacity', tt.get('op')), ('ZoomX', tt.get('zoom')), ('ZoomY', tt.get('zoom'))):
                if v_ is not None:
                    try: item.SetProperty(prop_, v_)
                    except Exception: pass
        except Exception:
            pass
        titulos_abs.append({'track': tt['track'], 'start': t0 + tt['rec_start'], 'dur': tt['rec_dur'], 'nome': tt['nome'],
                            '_ins': int(item.GetStart())})
    for aj in spec.get('ajustes') or []:   # adjustment clip: gerador nativo; mesma zona vazia + realocacao
        sec = rec_livre / tl_fps
        tc = '%02d:%02d:%02d:%02d' % (int(sec // 3600), int((sec % 3600) // 60), int(sec % 60), int(round((sec % 1) * tl_fps)))
        rec_livre += aj['rec_dur'] + 2
        try:
            tl.SetCurrentTimecode(tc)
            item = tl.InsertGeneratorIntoTimeline('Adjustment Clip')
        except Exception as e:
            avisos.append(T('ajuste "%s" nao inserido (%s)', 'adjustment "%s" not inserted (%s)') % (aj['nome'], e)); continue
        if not item:
            avisos.append(T('ajuste "%s" nao inserido', 'adjustment "%s" not inserted') % aj['nome']); continue
        try:
            rec_livre = max(rec_livre, item.GetStart() + item.GetDuration() + 2)
        except Exception:
            pass
        try:
            item.SetName(aj['nome'])
        except Exception:
            pass
        titulos_abs.append({'track': aj['track'], 'start': t0 + aj['rec_start'], 'dur': aj['rec_dur'], 'nome': aj['nome'],
                            '_ins': int(item.GetStart())})
    # 3) exporta, injeta, importa
    base = os.path.join(tempfile.gettempdir(), 'noebridge'); os.makedirs(base, exist_ok=True)
    src = os.path.join(base, '_a2r_%s.drt' % uuid.uuid4().hex[:8])
    if not tl.Export(src, r.EXPORT_DRT):
        raise RuntimeError(T('Export DRT falhou', 'DRT export failed'))
    _, xml = L.seq_xml(src)
    starts = [int(re.search(r'<Start>(-?\d+)</Start>', m.group(0)).group(1))
              for m in re.finditer(r'<Sm2TiVideoClip\b.*?</Sm2TiVideoClip>', xml, re.S)
              if '<MediaFilePath>' in m.group(0) and re.search(r'<Start>(-?\d+)</Start>', m.group(0))]   # titulos Text+ nao tem MediaFilePath: ficam fora da ordem de midia
    itens_v = _itens_xml(tl, 'video')            # TODAS as trilhas (append tem itens antigos fora de 1..ntr)
    ordem = [s for _, s in itens_v]              # ordem de clipes no XML = por trilha, por posicao
    if starts != ordem:
        raise RuntimeError(T('ordem do XML %s difere da API %s', 'XML order %s differs from the API %s') % (starts, ordem))
    fe = _fps_exato(tl_fps)

    def _uid_de(tag, start):   # reaproveita o UniqueId do mapa que o proprio Resolve gerou para este clipe
        achados = []
        for blk in re.findall(r'<%s .*?</%s>' % (tag, tag), xml, re.S):
            if re.search(r'<Start>%d</Start>' % start, blk):
                h = re.search(r'<MediaTimemapBA>([0-9a-f]+)</MediaTimemapBA>', blk)
                if h:
                    d = L.timemap_decode(h.group(1))
                    if d['forma'] == 'retimado':
                        achados.append(d['entradas'].get('UniqueId'))
        return achados[0] if len(achados) == 1 else None   # ambiguo (mesmo start em trilhas diferentes): uuid novo

    por_start = {}
    for c, km in zip(clips, keymaps):
        pt = {'keys': km or None}
        if c.get('fx'):
            pt['fx'] = [(f['plugin'], f.get('params') or {}) for f in c['fx'] if not f.get('anim')]
        rm = c.get('remap')
        if rm:
            pts = rm['points']; src0 = pts[0][1]
            uid = _uid_de('Sm2TiVideoClip', t0 + c['rec_start']) if not append_mode else None
            uid = uid or str(uuid.uuid4())                        # append: uuid novo (o start pode existir em outra trilha)
            rec0 = src0                                           # origem (0,0) -> (src0, src0): velocidade 1 antes do clipe
            pt.update({'timemap_hex': _timemap_mapa(rm, rec0, fe, c['_rm']['total'], c['media_fps'], uid).hex(),
                       'in': L.in_field(rec0 * fe), 'duration': int(c['_rm']['dur'])})
        elif abs(c.get('speed', 100.0) - 100.0) > 1e-6:
            src0 = c['src_in'] / c['media_fps']; rec0 = src0      # velocidade constante: timemap de 2 pontos + Duration (mesmo caminho do audio)
            rec_end = rec0 + c['_rec_dur'] / fe; src_end = c['src_out'] / c['media_fps']
            pt.update({'timemap_hex': L.timemap_encode([(rec0, src0), (rec_end, src_end)],
                                                     (c['_total'] - 1) / c['media_fps'], rec_end, str(uuid.uuid4())).hex(),
                       'in': L.in_field(rec0 * fe), 'duration': c['_rec_dur']})
        por_start[(c.get('track', 1), t0 + c['rec_start'])] = pt
    trilhas = []
    for trk, st in itens_v:
        pt = por_start.get((trk, st))
        if pt is None and not append_mode:                    # no append os itens antigos nao tem par mesmo: normal
            avisos.append(T('item na trilha %d posicao %d sem par de injecao (ripple cruzou trilhas?): chaves/timemap nao aplicados nele',
                            'item on track %d at %d has no injection pair (ripple crossed tracks?): keys/timemap not applied to it') % (trk, st))
        trilhas.append(pt)
    # audio: ordem no XML = por trilha de audio, por posicao (mesma regra do video)
    itens_a = []
    if aclips:                                              # sem audio copiado nao ha patch de audio: check desnecessario
        starts_a = [int(x) for x in re.findall(r'<Sm2TiAudioClip.*?<Start>(\d+)</Start>', xml, re.S)]
        itens_a = _itens_xml(tl, 'audio')
        ordem_a = [s for _, s in itens_a]
        if starts_a != ordem_a:
            raise RuntimeError(T('ordem do XML de audio %s difere da API %s', 'audio XML order %s differs from the API %s') % (starts_a, ordem_a))
    por_start_a = {}
    for a, it_ok in zip(aclips, aitens):
        if it_ok is None:
            continue
        pt = {}
        if a.get('vol_keys') and not a.get('_vol_skip'):
            ho = (a['remap']['points'][0][1] if a.get('remap') else a['src_in'] / a['media_fps']) * fe   # mesma origem rec0=src0 do timemap
            pt['keys'] = {(124, 95): [(int(round(p[0] + ho)), L.FLAG_EASE, p[1], (p[2], p[3]))
                                      if len(p) > 3 else (int(round(p[0] + ho)), p[1]) for p in a['vol_keys']]}   # grupo 124, param 95 = AudioVolume (dB)
        rm = a.get('remap'); spd = a.get('speed', 100.0)
        if rm:
            src0 = rm['points'][0][1]
            uid = (_uid_de('Sm2TiAudioClip', t0 + a['rec_start']) if not append_mode else None) or str(uuid.uuid4())
            pt.update({'timemap_hex': _timemap_mapa(rm, src0, fe, a['_total'], a['media_fps'], uid).hex(),
                       'in': L.in_field(src0 * fe), 'duration': int(a['rec_dur'])})
        elif abs(spd - 100.0) > 1e-6:
            src0 = a['src_in'] / a['media_fps']; rec0 = src0
            rec_end = rec0 + a['rec_dur'] / fe; src_end = a['src_out'] / a['media_fps']
            uid = (_uid_de('Sm2TiAudioClip', t0 + a['rec_start']) if not append_mode else None) or str(uuid.uuid4())
            pt.update({'timemap_hex': L.timemap_encode([(rec0, src0), (rec_end, src_end)],
                                                     (a['_total'] - 1) / a['media_fps'], rec_end, uid).hex(),
                       'in': L.in_field(rec0 * fe), 'duration': int(a['rec_dur'])})
        por_start_a[(a.get('track', 1), t0 + a['rec_start'])] = pt
    atrilhas = None
    if aclips:
        atrilhas = []
        for trk, st in itens_a:
            pt = por_start_a.get((trk, st))
            if pt is None and not append_mode:
                avisos.append(T('item de audio na trilha %d posicao %d sem par de injecao',
                                'audio item on track %d at %d has no injection pair') % (trk, st))
            atrilhas.append(pt)
    dst = os.path.join(base, re.sub(r'[\\/:*?"<>|]+', '_', nome_final) + '_%s.drt' % uuid.uuid4().hex[:6])
    trans_abs = [{'kind': tr_['kind'], 'track': tr_['track'], 'start': t0 + tr_['start'],
                  'dur': tr_['dur'], 'cut': t0 + tr_['cut'], 'lado': tr_.get('lado'),
                  'cat': tr_.get('cat', 'simple'),
                  'pretty': tr_['pretty'], 'name': tr_['name']} for tr_ in spec.get('transitions') or []]
    # so transicoes de AUDIO entre dois clipes vao no DRT (blob de crossfade nativo);
    # video e fades de ponta solta vao pos-reimport via AddTransition/SetFades (tipos reais)
    drt_tr = [x for x in trans_abs if x['kind'] == 'audio' and not x.get('lado')]
    avisos.extend(L.patch_drt2(src, dst, trilhas, atrilhas, drt_tr or None, titulos_abs or None))
    novo = mp.ImportTimelineFromFile(dst)
    if not novo:
        raise RuntimeError(T('ImportTimelineFromFile falhou', 'ImportTimelineFromFile failed'))
    if append_mode:
        # sanity: a timeline reimportada tem que trazer o conteudo antigo + os itens novos.
        # um DRT parcialmente corrompido importa "ok" com itens dropados — sem o check a original morreria com dados bons.
        esperado_min = len(itens_v) + len(itens_a)
        got = sum(len(novo.GetItemListInTrack(tp, tr_) or []) for tp in ('video', 'audio')
                  for tr_ in range(1, novo.GetTrackCount(tp) + 1))
        if got < esperado_min:
            avisos.append(T('reimport trouxe %d itens (esperava >=%d): timeline original preservada, a nova ficou como sandbox',
                            'reimport brought %d items (expected >=%d): original timeline preserved, the new one stayed as sandbox') % (got, esperado_min))
            novo.SetName(nome_final + '_sandbox')
            return novo, avisos
        if mp.DeleteTimelines([alvo]) is False:             # substitui a original (ja foi exportada e patchada)
            avisos.append(T('a timeline original nao foi removida: a nova pode ter saido com nome duplicado',
                            'the original timeline was not removed: the new one may have come out with a duplicated name'))
        if tl is not alvo:
            mp.DeleteTimelines([tl])                        # e a sandbox duplicada
        tl = None
    novo.SetName(nome_final); p.SetCurrentTimeline(novo)
    # dedupe: re-paste na mesma timeline traria os mesmos markers de sequencia outra vez
    ja = set()
    try:
        for fid, mm in (novo.GetMarkers() or {}).items():
            if mm.get('customData') == 'a2r': ja.add(int(fid))
    except Exception:
        pass
    for m in spec.get('markers') or []:
        try:
            fid = t0 + m['start_f']
            if fid in ja: continue
            cor = {'Chapter': 'Green', 'Segmentation': 'Yellow', 'WebLink': 'Cyan', 'Flash Cue Point': 'Orange'}.get(m.get('tipo'), 'Blue')
            novo.AddMarker(fid, cor, m['nome'], m['comentario'], max(1, m['dur_f']), 'a2r')
        except Exception as e:
            avisos.append(T('marker "%s" nao entrou: %s', 'marker "%s" not added: %s') % (m['nome'], e))
    # markers de clipe: nao serializam no DRT -> AddMarker DEPOIS do reimport, no item novo.
    # frameId = frame de midia do clipe (src domain): normal = src_in + d*mfps/fps; remap = curva
    novo_items = {}
    for trk in range(1, novo.GetTrackCount('video') + 1):
        for it_ in novo.GetItemListInTrack('video', trk) or []:
            try:
                if (it_.GetProperties() or {}).get('TransitionType') is not None: continue   # transicao nao e clipe
            except Exception: pass
            novo_items[(trk, it_.GetStart())] = it_
    for c in clips:
        if not c.get('markers'):
            continue
        it_ = novo_items.get((c.get('track', 1), t0 + c['rec_start']))
        if it_ is None:
            avisos.append(T('clipe "%s": item nao encontrado para os markers', 'clip "%s": item not found for markers') % c.get('_nome', '?')); continue
        rm = c.get('remap')
        for mk_ in c['markers']:
            d = mk_['d']
            try:
                if rm:
                    pts = rm['points']; rec0 = pts[0][1]
                    conv = [[0.0, 0.0]] + [[rec0 + dd / fe, ss] for dd, ss in pts]
                    mt = L.timemap_eval(conv, rec0 + d / fe)
                    fid = int(round(mt * c['media_fps']))
                else:
                    fid = int(round(c['src_in'] + d * (c.get('speed', 100.0) / 100.0) * c['media_fps'] / fe))
                cor = {'Chapter': 'Green', 'Segmentation': 'Yellow', 'WebLink': 'Cyan', 'Flash Cue Point': 'Orange'}.get(mk_.get('tipo'), 'Blue')
                if it_.AddMarker(fid, cor, mk_.get('nome', ''), mk_.get('comentario', ''), max(1, mk_.get('dur_f', 1)), '') is False:
                    avisos.append(T('marker de clipe "%s" recusado (frameId %d fora da janela?)', 'clip marker "%s" rejected (frameId %d out of window?)') % (mk_.get('nome'), fid))
            except Exception as e:
                avisos.append(T('marker de clipe "%s" nao entrou: %s', 'clip marker "%s" not added: %s') % (mk_.get('nome'), e))
    # transicoes de video + fades (ponta solta): API nativa pos-reimport. itens-transicao
    # aparecem em GetItemListInTrack — filtro por TransitionType pra nao mirar neles.
    if trans_abs:
        ini_v, fim_v, ini_a, fim_a = {}, {}, {}, {}
        for trk in range(1, novo.GetTrackCount('video') + 1):
            for it_ in novo.GetItemListInTrack('video', trk) or []:
                try:
                    if (it_.GetProperties() or {}).get('TransitionType') is not None: continue
                except Exception: pass
                ini_v[(trk, it_.GetStart())] = it_; fim_v[(trk, it_.GetStart() + it_.GetDuration())] = it_
        for trk in range(1, novo.GetTrackCount('audio') + 1):
            for it_ in novo.GetItemListInTrack('audio', trk) or []:
                try:
                    if (it_.GetProperties() or {}).get('TransitionType') is not None: continue
                except Exception: pass
                ini_a[(trk, it_.GetStart())] = it_; fim_a[(trk, it_.GetStart() + it_.GetDuration())] = it_
        for tr_ in trans_abs:
            if tr_['kind'] == 'audio' and not tr_.get('lado'):
                continue                                       # crossfade ja foi no DRT
            nm = tr_.get('name') or tr_['pretty']
            try:
                if tr_['kind'] == 'audio':
                    alvo = ini_a.get((tr_['track'], tr_['cut'])) if tr_['lado'] == 'start' else fim_a.get((tr_['track'], tr_['cut']))
                    if alvo is None:
                        avisos.append(T('fade de audio "%s": item nao encontrado na borda', 'audio fade "%s": item not found on the edge') % nm); continue
                    fades = dict(alvo.GetFades() or {})
                    fades['FadeIn' if tr_['lado'] == 'start' else 'FadeOut'] = tr_['dur']
                    if alvo.SetFades(fades) is False:
                        avisos.append(T('fade de audio "%s" recusado', 'audio fade "%s" rejected') % nm)
                else:
                    if tr_.get('lado') == 'start':
                        alvo, pos = ini_v.get((tr_['track'], tr_['cut'])), 'start'
                    elif tr_.get('lado') == 'end':
                        alvo, pos = fim_v.get((tr_['track'], tr_['cut'])), 'end'
                    else:
                        alvo, pos = (fim_v.get((tr_['track'], tr_['cut'])) or ini_v.get((tr_['track'], tr_['cut']))), 'end' if fim_v.get((tr_['track'], tr_['cut'])) else 'start'
                    if alvo is None:
                        avisos.append(T('transicao "%s": item nao encontrado no corte %d', 'transition "%s": item not found at cut %d') % (nm, tr_['cut'])); continue
                    t_ = alvo.AddTransition({'type': tr_['pretty'], 'category': tr_.get('cat', 'simple'),
                                             'position': pos, 'alignment': 'center', 'duration': tr_['dur']})
                    if not t_:
                        avisos.append(T('transicao "%s" (tipo %s) recusada pelo Resolve', 'transition "%s" (type %s) rejected by Resolve') % (nm, tr_['pretty']))
            except Exception as e:
                avisos.append(T('transicao "%s" falhou: %s', 'transition "%s" failed: %s') % (nm, e))
    # efeitos com param ANIMADO: o blob grupo-50 nao serializa chaves de OFX -> vao numa
    # Fusion comp do clipe (MediaIn -> OFX animado -> MediaOut). Sobrevive ao roundtrip DRT.
    for i, c in enumerate(clips):
        fx_an = [f for f in (c.get('fx') or []) if f.get('anim')]
        if not fx_an:
            continue
        it_ = novo_items.get((c.get('track', 1), t0 + c['rec_start']))
        if it_ is None:
            avisos.append(T('clipe %d: item nao achado p/ efeitos animados', 'clip %d: item not found for animated effects') % i); continue
        try:
            fc = it_.GetFusionCompByIndex(1) or it_.AddFusionComp()
            tools = fc.GetToolList(False) or {}
            mi = next((v for v in tools.values() if getattr(v, 'Name', '') == 'MediaIn1'), None)
            mo = next((v for v in tools.values() if getattr(v, 'Name', '') == 'MediaOut1'), None)
            if mi is None or mo is None:
                avisos.append(T('clipe %d: Fusion comp sem MediaIn/MediaOut — %d efeito(s) animado(s) perdidos',
                                'clip %d: Fusion comp has no MediaIn/MediaOut — %d animated effect(s) lost') % (i, len(fx_an))); continue
            elo = mi   # cadeia: MediaIn -> fx1 -> fx2 -> MediaOut
            for f in fx_an:
                tid = _FX_CAMEL.get(f['plugin'])
                if not tid:
                    avisos.append(T('clipe %d: efeito "%s" animado sem tool Fusion — efeito perdido',
                                    'clip %d: animated effect "%s" has no Fusion tool — effect lost') % (i, f['plugin'])); continue
                tool = fc.AddTool(tid)
                if not tool:
                    avisos.append(T('clipe %d: tool "%s" recusada pela comp', 'clip %d: tool "%s" refused by the comp') % (i, tid)); continue
                ligou = False
                for inp_nm in ('Source', 'Input'):           # OFX chama 'Source'; MediaOut chama 'Input'
                    try:
                        if tool.ConnectInput(inp_nm, elo) is not False:
                            ligou = True; break
                    except Exception:
                        pass
                if not ligou:
                    avisos.append(T('clipe %d: tool "%s" nao conectou na cadeia — efeito perdido',
                                    'clip %d: tool "%s" did not connect to the chain — effect lost') % (i, tid)); continue
                elo = tool
                for pn, v_ in (f.get('params') or {}).items():
                    try: setattr(tool, pn, v_)
                    except Exception:
                        try: tool.SetInput(pn, v_)
                        except Exception: pass
                for pn, ks in (f.get('anim') or {}).items():
                    try:
                        bs = fc.BezierSpline(); bs.SetKeyFrames({int(t_): {'Value': float(v_)} for t_, v_ in ks})
                        inp = tool.GetInputList().get(pn) if hasattr(tool, 'GetInputList') else None
                        (inp.SetSource(bs) if inp is not None else setattr(tool, pn, bs))
                    except Exception as e_:
                        avisos.append(T('clipe %d: chaves em %s nao aplicadas (%s)', 'clip %d: keys on %s not applied (%s)') % (i, pn, e_))
            if elo is not mi:
                mo.ConnectInput('Input', elo)
        except Exception as e:
            avisos.append(T('clipe %d: comp de efeitos animados falhou: %s', 'clip %d: animated-effects comp failed: %s') % (i, e))
    # efeitos de audio (Fairlight FX): API nativa pos-reimport, params vao padrao
    for i, a in enumerate(aclips):
        if not a.get('afx'):
            continue
        alvo = None
        for trk_ in range(1, novo.GetTrackCount('audio') + 1):
            for it_ in novo.GetItemListInTrack('audio', trk_) or []:
                try:
                    if (it_.GetProperties() or {}).get('TransitionType') is not None: continue
                except Exception: pass
                if trk_ == a['track'] and it_.GetStart() == t0 + a['rec_start']:
                    alvo = it_; break
            if alvo: break
        if alvo is None:
            avisos.append(T('audio %d: item nao achado p/ efeitos', 'audio %d: item not found for effects') % i); continue
        for f in a['afx']:
            try:
                if alvo.AddEffect('audio', f['id']) is None:
                    avisos.append(T('audio %d: efeito "%s" recusado', 'audio %d: effect "%s" rejected') % (i, f.get('_nome', f['id'])))
            except Exception as e:
                avisos.append(T('audio %d: efeito "%s" falhou: %s', 'audio %d: effect "%s" failed: %s') % (i, f.get('_nome', f['id']), e))
    pasta_dest = sub_bin if sub_bin is not None else pasta_alvo   # volta pro sub-bin novo ou pro bin da timeline substituida
    if pasta_dest is not None:
        try:
            mpi = novo.GetMediaPoolItem()
            if mpi and mp.MoveClips([mpi], pasta_dest) is False:
                avisos.append(T('nao consegui mover a timeline para a pasta', 'could not move the timeline into the folder'))
        except Exception as e:
            avisos.append(T('timeline fora da pasta: %s', 'timeline outside the folder: %s') % e)
        mp.SetCurrentFolder(pasta_dest)
    if cleanup and tl is not None:
        mp.DeleteTimelines([tl])
    for a in avisos:
        log('AVISO: ' + a)
    log('pronto: timeline "%s" com %d clipe(s)' % (novo.GetName(), len(clips)))   # linha de protocolo (o painel faz parse)
    return novo, avisos


if __name__ == '__main__':
    build(json.load(open(sys.argv[1], encoding='utf-8')))
