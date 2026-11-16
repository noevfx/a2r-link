"""prproj: le Time Remapping de um .prproj (XML gzipped do Premiere).

O ExtendScript do Premiere nao expoe Time Remapping (HANDOFF). Lemos o .prproj salvo
(o bridge avisa para salvar quando o projeto esta sujo E ha rampa) e so varremos os
objetos dos takes copiados (indice de ids + busca por texto), sem montar a arvore toda:
custo baixo mesmo em projeto de horas com milhares de takes.

Grafo (Premiere 27, medido em Teste PR.prproj):
  Sequence(ObjectUID) -> TrackGroups -> TrackGroup(First=GUID do tipo) -> Tracks -> Track(ObjectURef)
  -> VideoClipTrack -> ClipItems -> TrackItem(ObjectRef) -> SubClip -> Clip(VideoClip)
  -> TimeRemapping -> Keyframes(TimeComponentParam "Speed")
  <Keyframes>t_ticks,v_seg_midia,tipo,0,infIn,velIn,infOut,velOut;...</Keyframes>   TPS = 254016000000
  tipos vistos: 6 = ponta, 7 = inicio de rampa (com influencia %), 8 = fim de rampa.
  A curva real esta descrita em _amostra (modelo medido contra render do Premiere).
"""
import bisect, gzip, re

TPS = 254016000000.0
GUID_VIDEO = '228cda18-3625-4d2d-951e-348879e4ed93'    # MediaType das VideoClipTrack
GUID_AUDIO = '80b8e3d5-6dca-4195-aefb-cb5f407ab009'    # MediaType das AudioClipTrack
OBJ = re.compile(r'<([A-Za-z]+) ObjectU?ID="([^"]+)"')
TOL_MATCH = 0.004        # ~1/4 de quadro a 60fps: casa take sem confundir com o vizinho


def _abre(caminho):
    raw = open(caminho, 'rb').read()
    try:
        return gzip.decompress(raw).decode('utf-8', 'replace')
    except OSError:
        return raw.decode('utf-8', 'replace')


def _unesc(s):
    return (s or '').replace('&quot;', '"').replace('&apos;', "'").replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')


def _campo(bloco, tag, padrao=None):
    m = re.search(r'<' + tag + r'>([^<]*)</' + tag + r'>', bloco)
    return _unesc(m.group(1)) if m else padrao


def _ref(bloco, tag):
    m = re.search(r'<' + tag + r'[^>]*ObjectU?Ref="([^"]+)"', bloco)
    return m.group(1) if m else None


_cache = {}

class Prproj(object):
    def __init__(self, caminho):
        self.raw = _abre(caminho)
        self.objs = {m.group(2): (m.group(1), m.start(), m.end()) for m in OBJ.finditer(self.raw)}

    @classmethod
    def aberto(cls, caminho):
        """Prproj com cache por (caminho, tamanho, mtime) — remaps/markers/holds/labels
        sao lidos varias vezes na mesma operacao; parsear 6+ vezes um XML de MBs custa caro."""
        import os
        try:
            st = os.stat(caminho); chave = (caminho, st.st_size, st.st_mtime_ns)
        except OSError:
            chave = (caminho, 0, 0)
        if chave not in _cache:
            _cache.clear()                       # um projeto por vez: nao segurar XMLs velhos em memoria
            _cache[chave] = cls(caminho)
        return _cache[chave]

    def trecho(self, oid):
        """trecho XML do objeto (ObjectID numerico ou ObjectUID)"""
        e = self.objs.get(oid)
        if not e: return ''
        tag, ini, fim = e
        f = self.raw.find('</' + tag + '>', fim)
        return self.raw[ini:f] if f > 0 else self.raw[ini:ini + 4000]

    def sequencia(self, nome=None):
        """-> [(tipo, trackIdx(0based), trackUID)] das faixas de video/audio da sequencia pedida (ou a unica)"""
        alvo = None
        for m in re.finditer(r'<Sequence ObjectUID="[^"]+"[^>]*>', self.raw):
            f = self.raw.find('</Sequence>', m.end())
            b = self.raw[m.end():f if f > 0 else m.end() + 12000]
            if nome is None or _campo(b, 'Name') == nome:
                alvo = b; break
        if alvo is None: return []
        items = []
        for tg in re.finditer(r'<TrackGroup[^>]*>\s*<First>([0-9a-f-]+)</First>\s*<Second ObjectU?Ref="([^"]+)"', alvo):
            tipo = 'video' if tg.group(1) == GUID_VIDEO else ('audio' if tg.group(1) == GUID_AUDIO else None)
            if not tipo: continue
            for tr in re.finditer(r'<Track Index="(\d+)" ObjectU?Ref="([^"]+)"', self.trecho(tg.group(2))):
                items.append((tipo, int(tr.group(1)), tr.group(2)))
        return items

    def keyframes(self, clip_oid):
        """VideoClip -> [(t_seq_s, v_midia_s, tipo, infIn, velIn, infOut, velOut)] ou None se nao tem TimeRemapping"""
        clip = self.trecho(clip_oid)
        tr = self.trecho(_ref(clip, 'TimeRemapping'))
        param = self.trecho(_ref(tr, 'Keyframes')) if tr else ''
        if not param or (_campo(param, 'Name') not in (None, 'Speed')): return None
        knots = []
        for k in (_campo(param, 'Keyframes', '') or '').split(';'):
            p = k.split(',')
            if len(p) < 3 or not p[0].strip(): continue
            try:
                f = [float(x) for x in p[4:8]] + [0.0] * 4
                knots.append((float(p[0]) / TPS, float(p[1]), int(p[2]), f[0], f[1], f[2], f[3]))
            except ValueError:
                pass
        return knots or None

    def takes(self, tipo, tuid):
        """TrackItem da faixa -> [(start_s, end_s, clip_oid)] (TrackItem -> SubClip -> Clip)"""
        out = []
        for ti in re.finditer(r'<TrackItem Index="\d+" ObjectU?Ref="(\d+)"', self.trecho(tuid)):
            item = self.trecho(ti.group(1))
            sub = self.trecho(_ref(item, 'SubClip') or '')
            out.append((float(_campo(item, 'Start', '0')) / TPS,
                        float(_campo(item, 'End', '0')) / TPS,
                        _ref(sub, 'Clip') or ''))
        return out


def _amostra(knots, fps, t0, t1):
    """curva tempo-do-clipe -> tempo-midia amostrada a cada quadro da faixa do clipe (+ nos exatos).
    Os nos do TimeRemapping estao em tempo DO CLIPE (0 = inicio do take, nao da sequencia):
    a janela de avaliacao e [0, t1-t0] e o resultado sai em tempo ABSOLUTO da sequencia (+t0).

    Modelo MEDIDO contra render do Premiere (quadro a quadro, Cesmac 16/11): trecho comum = velocidade
    constante (corda reta); par 7->8 = RAMPA entre as velocidades dos trechos vizinhos (por isso a
    corda da rampa vale a media das duas). A velocidade da rampa e um Bezier em (tempo, velocidade)
    com alcas horizontais de comprimento = influencia% do no 7, espelhada no no 8 (0% = rampa linear;
    maior = S mais marcado). Influencia <= 50%: exato; acima disso sobrou desvio de ate ~3 quadros de midia."""
    xs = [k[0] for k in knots]; ys = [k[1] for k in knots]
    tipos = [k[2] for k in knots]
    iIn = [k[3] / 100.0 for k in knots]; iOut = [k[5] / 100.0 for k in knots]
    n = len(xs)
    cord = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) if xs[i + 1] > xs[i] else 0.0 for i in range(n - 1)]
    rampa = [tipos[i] == 7 and tipos[i + 1] == 8 and xs[i + 1] > xs[i] for i in range(n - 1)]
    v0 = [cord[i - 1] if rampa[i] and i > 0 and not rampa[i - 1] else None for i in range(n - 1)]
    v1 = [cord[i + 1] if rampa[i] and i + 2 < n and not rampa[i + 1] else None for i in range(n - 1)]
    for ordem in (range(n - 1), range(n - 2, -1, -1)):       # rampas coladas: a velocidade passa de uma pra outra
        for i in ordem:
            if not rampa[i]: continue
            if v0[i] is None and i > 0 and rampa[i - 1] and v1[i - 1] is not None: v0[i] = v1[i - 1]
            if v1[i] is None and i + 2 < n and rampa[i + 1] and v0[i + 1] is not None: v1[i] = v0[i + 1]
            if v0[i] is not None and v1[i] is None: v1[i] = max(0.0, 2 * cord[i] - v0[i])
            if v1[i] is not None and v0[i] is None: v0[i] = max(0.0, 2 * cord[i] - v1[i])
    N = 256
    tab = {}
    for i in range(n - 1):
        if not rampa[i] or v0[i] is None: continue          # rampa sem vizinho nenhum: corda reta
        h = xs[i + 1] - xs[i]
        a = min(iOut[i], 1.0) if iOut[i] > 1e-4 else 0.0
        b = min(iIn[i + 1], 1.0) if iIn[i + 1] > 1e-4 else a
        X = []; V = []
        for j in range(N + 1):
            u = j / N; w = 1 - u
            X.append(xs[i] + h * (3 * w * w * u * a + 3 * w * u * u * (1 - b) + u ** 3))
            V.append(v0[i] + (v1[i] - v0[i]) * (3 * w * u * u + u ** 3))
        Y = [ys[i]]
        for j in range(N):
            Y.append(Y[-1] + (V[j] + V[j + 1]) / 2 * (X[j + 1] - X[j]))
        res = ys[i + 1] - Y[-1]                             # fecha exatamente no no seguinte
        tab[i] = (X, [y + res * (x - xs[i]) / h for x, y in zip(X, Y)])

    def eval_(t):
        if t <= xs[0]: return ys[0]
        if t >= xs[-1]: return ys[-1]
        for i in range(n - 1):
            if xs[i] <= t <= xs[i + 1]:
                if i not in tab:
                    return ys[i] + cord[i] * (t - xs[i])
                X, Y = tab[i]
                j = min(max(bisect.bisect_right(X, t) - 1, 0), N - 1)
                dx = X[j + 1] - X[j]
                return Y[j] + (Y[j + 1] - Y[j]) * (t - X[j]) / dx if dx > 0 else Y[j]
        return ys[-1]

    dur = t1 - t0
    # os nos vem em tempo DO CLIPE (a curva nasce em ~0, no inicio do take): off=t0 desloca a
    # avaliacao para o dominio deles. So aceitamos "absoluto" quando AMBOS os sinais batem:
    # primeiro no longe de 0 E ultimo no alem da duracao do take (nos clip-locais podem
    # passar da duracao em takes aparados, por isso uma condicao so nao basta).
    absoluto = bool(xs) and xs[0] > 0.5 and xs[-1] > dur + 0.5
    off = 0.0 if absoluto else t0
    ts = {t0 + i / fps for i in range(int(round(dur * fps)) + 1)} | {off + x for x in xs if t0 <= off + x <= t1} | {t0, t1}
    return [[round(t, 6), round(eval_(t - off), 6)] for t in sorted(ts)]


def _label_rgb(bloco):
    """asl.clip.label.color de um trecho de objeto -> int ou None"""
    m = re.search(r'<asl\.clip\.label\.color>(\d+)</asl\.clip\.label\.color>', bloco)
    return int(m.group(1)) if m else None


def labels(caminho, seq_nome, alvos):
    """alvos = [(tipo, track 1based, start_s, end_s)] dos clipes copiados (video e audio) ->
    {(tipo, track, start): rgb_int}. Cor de clipe de timeline: primeiro no proprio Clip do
    take (SubClip -> Clip); se nao tiver, no filho do MasterClip (label do bin se propaga
    pras instancias: Index 0 = video, 1 = audio)."""
    p = Prproj.aberto(caminho)
    saida = {}
    for tipo, tidx, tuid in p.sequencia(seq_nome):
        for ti in re.finditer(r'<TrackItem Index="\d+" ObjectU?Ref="(\d+)"', p.trecho(tuid)):
            item = p.trecho(ti.group(1))
            t0 = float(_campo(item, 'Start', '0')) / TPS
            sub = p.trecho(_ref(item, 'SubClip') or '')
            clip_oid = _ref(sub, 'Clip') or ''
            rgb = _label_rgb(p.trecho(clip_oid))
            if rgb is None:      # fallback: label do bin (filho do MasterClip do tipo certo)
                mc = p.trecho(_ref(sub, 'MasterClip') or '')
                alvo_tag = 'VideoClip' if tipo == 'video' else 'AudioClip'
                for m in re.finditer(r'<Clip Index="\d+" ObjectU?Ref="(\d+)"', mc):
                    if p.objs.get(m.group(1), ('', 0, 0))[0] == alvo_tag:
                        rgb = _label_rgb(p.trecho(m.group(1)))
                        if rgb is not None: break
            if rgb is None: continue
            for a in alvos:
                if a[0] == tipo and a[1] == tidx + 1 and abs(a[2] - t0) < TOL_MATCH:
                    saida[(tipo, tidx + 1, round(t0, 3))] = rgb
    return saida


def speeds(caminho, seq_nome, alvos):
    """alvos = [(track 1based, start_s)] dos clipes de uma sequencia ->
    {(track, start): {'speed': fator (1=100%), 'reversed': bool}}.
    Speed/reverso moram no Clip (irmao de InPoint/OutPoint/ClipID):
    <PlaybackSpeed>fator</PlaybackSpeed>  e  <PlayBackwards>true</PlayBackwards>
    (campos esparsos: ausentes = 1.0 / false). Serve para clipes de SUB-SEQUENCIAS,
    onde o QE nao enxerga speed/reversed por a seq nao ser a ativa."""
    p = Prproj.aberto(caminho)
    saida = {}
    for tipo, tidx, tuid in p.sequencia(seq_nome):
        if tipo != 'video': continue
        for t0, t1, clip_oid in p.takes(tipo, tuid):
            if not clip_oid: continue
            clip = p.trecho(clip_oid)
            sp = _campo(clip, 'PlaybackSpeed')
            rev = _campo(clip, 'PlayBackwards')
            if sp is None and rev is None: continue
            v = {'speed': float(sp) if sp else 1.0, 'reversed': rev == 'true'}
            for a in alvos:
                if a[0] == tidx + 1 and abs(a[1] - t0) < TOL_MATCH:
                    saida[(tidx + 1, round(t0, 3))] = v
    return saida


def frame_holds(caminho, seq_nome, alvos):
    """alvos = [(track 1based, start_s)] -> {(track, start): segundos_de_midia do quadro congelado}.
    O Frame Hold do Premiere NAO aparece em clip.components (o QE/DOM esconde): mora no VideoClip
    do .prproj — <FrameHold>tipo</FrameHold> + <FrameHoldStart>ticks</FrameHoldStart> (dominio midia).
    Tipo 4 = tempo custom (usa FrameHoldStart); 1 = in point; 2 = out point."""
    p = Prproj.aberto(caminho)
    saida = {}
    for tipo, tidx, tuid in p.sequencia(seq_nome):
        if tipo != 'video': continue
        for t0, t1, clip_oid in p.takes(tipo, tuid):
            if not clip_oid: continue
            clip = p.trecho(clip_oid)
            fh = _campo(clip, 'FrameHold')
            if not fh or fh == '0': continue
            t_hold = None
            fhs = _campo(clip, 'FrameHoldStart')
            if fhs:
                t_hold = float(fhs) / TPS
            elif fh == '1':
                t_hold = float(_campo(clip, 'InPoint', '0')) / TPS
            elif fh == '2':
                t_hold = float(_campo(clip, 'OutPoint', '0')) / TPS
            if t_hold is None: continue
            for a in alvos:
                if a[0] == tidx + 1 and abs(a[1] - t0) < TOL_MATCH:
                    saida[(tidx + 1, round(t0, 3))] = t_hold
    return saida


def _dva_markers(p, clip_xml):
    """trecho de um Clip -> [(t_s, nome, comentario, tipo)] dos markers de CLIPE.
    Cadeia: Clip -> <Markers ObjectRef> -> <Marker><Second ObjectRef> -> objeto com
    <DVAMarker>{json}</DVAMarker> (mStartTime em ticks TPS, dominio de midia)."""
    import json as _json
    out = []
    for mref in re.finditer(r'<Markers ObjectU?Ref="(\d+)"', clip_xml):
        mcol = p.trecho(mref.group(1))
        for m2 in re.finditer(r'<Marker[^>]*>\s*<First>[^<]*</First>\s*<Second ObjectU?Ref="(\d+)"', mcol):
            mk = p.trecho(m2.group(1))
            dva = re.search(r'<DVAMarker>([^<]+)</DVAMarker>', mk)
            if not dva: continue
            try:
                d = _json.loads(_unesc(dva.group(1)))['DVAMarker']
                dur = float((d.get('mDuration') or {}).get('ticks') or 0) / TPS
                out.append((float(d['mStartTime']['ticks']) / TPS, d.get('mName', ''),
                            d.get('mComment', ''), d.get('mType', 'Comment'), dur))
            except Exception:
                pass
    return out


def clip_markers(caminho, seq_nome, alvos):
    """alvos = [(track 1based, start_s)] -> {(track, start): [(t_midia_s, nome, comentario, tipo)]}.
    Markers de clipe moram no Clip do take (SubClip -> Clip), nao no TrackItem."""
    p = Prproj.aberto(caminho)
    saida = {}
    for tipo, tidx, tuid in p.sequencia(seq_nome):
        if tipo != 'video': continue
        for t0, t1, clip_oid in p.takes(tipo, tuid):
            if not clip_oid: continue
            ms = _dva_markers(p, p.trecho(clip_oid))
            if not ms: continue
            for a in alvos:
                if a[0] == tidx + 1 and abs(a[1] - t0) < TOL_MATCH:
                    saida[(tidx + 1, round(t0, 3))] = ms
    return saida


def remaps(caminho, seq_nome, fps, alvos):
    """alvos = [(track 1based, start_s, end_s)] dos clipes copiados ->
    {(track, start): {'samples': [[t_seq_s, midia_s]], 'keys': n, 'tipos': [...]}}"""
    p = Prproj.aberto(caminho)
    saida = {}
    for tipo, tidx, tuid in p.sequencia(seq_nome):
        if tipo != 'video': continue
        for t0, t1, clip_oid in p.takes(tipo, tuid):
            if not clip_oid: continue
            for a in alvos:
                if a[0] == tidx + 1 and abs(a[1] - t0) < TOL_MATCH:
                    knots = p.keyframes(clip_oid)
                    if knots:
                        xs = [k[0] for k in knots]
                        absoluto = bool(xs) and xs[0] > 0.5 and xs[-1] > (a[2] - a[1]) + 0.5   # mesma regra do _amostra
                        saida[(tidx + 1, round(t0, 3))] = {
                            'samples': _amostra(knots, fps, a[1], a[2]),
                            'knots': [[k[0], k[1], k[2], k[3] / 100.0, k[5] / 100.0] for k in knots],  # t, midia(s), tipo, infIn, infOut (0..1)
                            'knots_absoluto': absoluto,
                            'keys': len(knots), 'tipos': sorted({k[2] for k in knots}),
                            'influencias': [round(max(k[3], k[5]), 1) for k in knots if max(k[3], k[5]) > 0]}
    return saida
