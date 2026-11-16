"""normalizer: dados brutos dos leitores (Premiere / After) -> spec do gen.py (unidades do Resolve).

Os dois programas passam por UMA conversao so (`convert_channels`): posicao em px do container (sequencia/comp), ancora em px da midia,
escala % relativa ao tamanho NATIVO da midia (pode ser negativa = flip), rotacao horaria, opacidade.
Resolve: Pan/Tilt px da timeline (+direita/+cima), Zoom fator (1 = ajustado a timeline), RotationAngle anti-horario, FlipX/FlipY.
Ancora (com ou sem chaves) e dobrada na posicao do centro da imagem (o Resolve fica com a ancora no centro): visual identico.
3D: tratado como 2D (so Position X/Y, Scale X/Y, Rotation Z). Expressoes: ignoradas (valor lido sem a expressao).
"""
import math, urllib.parse
from i18n import T


# ---------- utilidades ----------
def _uri2path(p):
    """caminho de midia pode vir como URI file:// (%20 etc.) em algumas versoes do Premiere"""
    p = str(p or '')
    if p.startswith('file:'):
        u = urllib.parse.unquote(urllib.parse.urlparse(p).path)
        return u[1:] if len(u) > 2 and u[0] == '/' and u[2] == ':' else u
    return p


def _interp(keys, t):
    """valor linear de [(t, v)] em t; fora do intervalo segura a ponta. Aceita pontos de 3 elem (com tangente)."""
    if t <= keys[0][0]: return keys[0][1]
    if t >= keys[-1][0]: return keys[-1][1]
    for a, b in zip(keys, keys[1:]):
        t0, v0, t1, v1 = a[0], a[1], b[0], b[1]
        if t0 <= t <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def _tangentes(keys, samples):
    """Desvio de alca (S) por key via ajuste least-squares de Hermite por segmento: {i: (s_in, s_out)}.
    S_in = (m_lin - m_in)*dt/4, S_out = (m_out - m_lin)*dt/4 — tempos em segundos."""
    tans = {}
    for i in range(len(keys) - 1):
        t0, v0, t1, v1 = keys[i][0], keys[i][1], keys[i + 1][0], keys[i + 1][1]
        dt = t1 - t0
        if dt <= 1e-9: continue
        m_lin = (v1 - v0) / dt
        A = B = C = D0 = D1 = 0.0
        for ts, vs in samples:
            if ts <= t0 or ts >= t1: continue
            u = (ts - t0) / dt; u2, u3 = u * u, u * u * u
            h10 = u3 - 2 * u2 + u; h11 = u3 - u2
            resto = vs - ((2 * u3 - 3 * u2 + 1) * v0 + (-2 * u3 + 3 * u2) * v1)
            A += h10 * h10; B += h10 * h11; C += h11 * h11
            D0 += h10 * resto; D1 += h11 * resto
        det = A * C - B * B
        if abs(det) < 1e-12: continue
        m0 = (D0 * C - D1 * B) / det / dt   # tangente de saida da key i (v/s)
        m1 = (D1 * A - D0 * B) / det / dt   # tangente de chegada da key i+1 (v/s)
        tans.setdefault(i, [0.0, 0.0])[1] = (m0 - m_lin) * dt / 4.0
        tans.setdefault(i + 1, [0.0, 0.0])[0] = (m_lin - m1) * dt / 4.0
    return {i: tuple(v) for i, v in tans.items() if v[0] or v[1]}


def _hermite_pior(keys, tans, samples, pular=None):
    """(desvio_max, (i_seg, t, v)) entre a curva Hermite (tangentes das keys) e as amostras.
    `pular` = segmentos ignorados (onde nao cabe chave nova sem colidir no mesmo quadro)."""
    pior, onde = 0.0, None
    for i in range(len(keys) - 1):
        if pular and i in pular: continue
        t0, v0, t1, v1 = keys[i][0], keys[i][1], keys[i + 1][0], keys[i + 1][1]
        dt = t1 - t0
        if dt <= 1e-9: continue
        m_lin = (v1 - v0) / dt
        m0 = m_lin + 4.0 * tans.get(i, (0.0, 0.0))[1] / dt      # tangente de saida da key i
        m1 = m_lin - 4.0 * tans.get(i + 1, (0.0, 0.0))[0] / dt  # tangente de chegada da key i+1
        for ts, vs in samples:
            if ts <= t0 or ts >= t1: continue
            u = (ts - t0) / dt; u2, u3 = u * u, u * u * u
            h = (2*u3 - 3*u2 + 1)*v0 + (u3 - 2*u2 + u)*m0*dt + (-2*u3 + 3*u2)*v1 + (u3 - u2)*m1*dt
            if abs(h - vs) > pior: pior, onde = abs(h - vs), (i, ts, vs)
    return pior, onde


def _dedupe(keys, fps, samples=None):
    """fundir chaves que caem no mesmo quadro do blob (ele so guarda 1 por frame):
    fica a mais recente, mesmo criterio do Resolve na importacao. Com amostras, cada
    chave e snapada ao quadro inteiro e recebe o valor real da curva naquele quadro —
    o Resolve vai grava-la na posicao quantizada, entao o valor tem que ser o dela."""
    out = [list(keys[0])]
    for k in keys[1:]:
        if int(round(k[0] * fps)) == int(round(out[-1][0] * fps)): out[-1] = list(k)
        else: out.append(list(k))
    if samples:
        for k in out:
            f = int(round(k[0] * fps))
            k[0] = f / fps
            k[1] = _interp(samples, k[0])
    return out


def _adaptativo(keys, samples, tol, fps, maxpts=32):
    """insere chaves auxiliares nos piores desvios ate a curva Hermite (com tangentes por key)
    reproduzir as amostras dentro de tol. Chaves novas sao sempre em quadros inteiros
    (o blob quantiza para la), e desvios em segmentos sem quadro livre sao irredutiveis."""
    pts = _dedupe(keys, fps, samples)
    bloqueados = set()
    for _ in range(64):
        tans = _tangentes(pts, samples)
        pior, onde = _hermite_pior(pts, tans, samples, bloqueados)
        if pior <= tol or onde is None:
            return [[p[0], p[1]] + ([tans[i][0], tans[i][1]] if i in tans else []) for i, p in enumerate(pts)]
        if len(pts) >= maxpts:
            return None   # nao convergiu: as amostras densas sao estritamente melhores que um ajuste aberto
        i, ts, vs = onde
        ocup = {int(round(p[0] * fps)) for p in pts}
        f_lo, f_hi = int(math.floor(pts[i][0] * fps)) + 1, int(math.ceil(pts[i + 1][0] * fps)) - 1
        livres = [f for f in range(f_lo, f_hi + 1) if f not in ocup]
        if not livres:
            bloqueados.add(i)
            continue
        f = min(livres, key=lambda f_: abs(f_ - ts * fps))          # quadro livre mais perto do pior desvio
        pts.insert(i + 1, [f / fps, _interp(samples, f / fps)])
        bloqueados = {j + 1 if j > i else j for j in bloqueados}
    return None


def _melhor(keys, samples, tol, fps=25.0):
    """chaves originais se LINEAR ja reproduz; senao chaves com tangentes Hermite (ease editavel no
    Resolve, subdividindo nos piores desvios ate fechar); senao as amostras densas (fallback seguro).
    Chaves que cairiam no mesmo quadro do blob sao fundidas antes do ajuste (o Resolve so guarda 1 por
    quadro), assim as tangentes sao recalculadas para a chave sobrevivente."""
    if not samples: return _dedupe(keys, fps)
    dev = max(abs(_interp(keys, t) - v) for t, v in samples)
    if dev <= tol: return _dedupe(keys, fps, samples)
    if len(keys) >= 2:
        pts = _adaptativo(keys, samples, tol, fps)
        if pts: return pts
    return samples


def _chan(prop, idx=None, tol=0.3, fps=25.0):
    """propriedade (formato do leitor do AE) -> (estatico, [(t, v)] ou None)"""
    if not prop: return None, None
    pick = (lambda v: v[idx]) if idx is not None else (lambda v: v)
    ks = None
    if prop.get('keys'):
        ks = [(k['t'], pick(k['v'])) for k in prop['keys']]
        ks = _melhor(ks, [(t, pick(v)) for t, v in prop.get('samples') or []], tol, fps)
    return pick(prop['value']), ks


EPS = {'Pan': 0.5, 'Tilt': 0.5, 'ZoomX': 0.002, 'ZoomY': 0.002, 'RotationAngle': 0.05, 'Opacity': 0.2}   # tolerancia na unidade do Resolve


def _rdp(pts, eps):
    """Ramer-Douglas-Peucker em [[x, y], ...] (x = quadro). Mantem pontos cujo desvio da reta entre vizinhos mantidos > eps."""
    if len(pts) < 3: return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dmax, im = -1.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        yl = y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)     # distancia VERTICAL (mesmo criterio da interpolacao linear)
        d = abs(y - yl)
        if d > dmax: dmax, im = d, i
    if dmax <= eps: return [pts[0], pts[-1]]
    return _rdp(pts[:im + 1], eps)[:-1] + _rdp(pts[im:], eps)


def _reduz(keys):
    for prop, eps in EPS.items():
        if prop in keys and len(keys[prop]) > 3:
            if any(len(p) > 3 for p in keys[prop]): continue   # pontos com tangente nao passam pelo RDP
            keys[prop] = _rdp([list(p) for p in keys[prop]], eps)
    return keys


def _tags(ks_):
    """{t: (s_in, s_out)} dos pontos que carregam tangente (4 elementos: t, v, s_in, s_out)."""
    return {p[0]: (p[2], p[3]) for p in (ks_ or []) if len(p) > 3}


def _pt3(d_of, conv, mult, t, tag):
    """ponto [d, conv(t)] + tag de tangente escalada por mult (escalar ou funcao do valor de origem)."""
    p = [d_of(t), conv(t)]
    if tag is not None:
        m = mult(t) if callable(mult) else mult
        p += [tag[0] * m, tag[1] * m]
    return p


def convert_channels(nm, rW, rH, rfps, cW, cH, sw, sh, X, Y, A, S, RO, OP, inp, outp, avisos):
    """Cada canal e (estatico, chaves|None); chaves = [(t_segundos_de_timeline, valor)].
    X,Y px do container; A=(ax,ay) cada um (est,chaves) px da midia; S=(sx,sy) % nativo; RO graus horario; OP %.
    Devolve (static, keys) do gen; d = quadros desde o inicio do clipe."""
    (xs, xk), (ys, yk) = X, Y
    (ax, axk), (ay, ayk) = A
    (sx, sxk), (sy, syk) = S
    ro, rok = RO; op, opk = OP
    k = min(rW / cW, rH / cH); f = min(rW / sw, rH / sh)
    d_of = lambda t: round((t - inp) * rfps, 3)
    static, keys = {}, {}
    zoom = lambda scale: abs(scale) / 100.0 * k / f

    def sign(st, ks_): return -1 if (st if not ks_ else ks_[0][1]) < 0 else 1
    if sign(sx, sxk) < 0: static['FlipX'] = True
    if sign(sy, syk) < 0: static['FlipY'] = True
    for ks_ in (sxk, syk):
        if ks_ and len({p[1] < 0 for p in ks_}) > 1:
            avisos.append(T('camada "%s": a escala cruza o zero (flip animado): usando o sinal da primeira chave',
                            'layer "%s": the scale crosses zero (animated flip): using the first keyframe sign') % nm)
    anchor_off = abs(ax - sw / 2) > 1e-6 or abs(ay - sh / 2) > 1e-6 or bool(axk or ayk)
    animado = any((xk, yk, axk, ayk, sxk, syk, rok))
    ev = lambda ks_, v, t: _interp(ks_, t) if ks_ else v
    if not anchor_off:
        tgx, tgy = _tags(xk), _tags(yk)
        if xk:
            keys['Pan'] = [_pt3(d_of, lambda t: (ev(xk, xs, t) - cW / 2) * k, k, t, tgx.get(t)) for t in sorted({p[0] for p in xk})]
        else:
            static['Pan'] = (xs - cW / 2) * k
        if yk:
            keys['Tilt'] = [_pt3(d_of, lambda t: -(ev(yk, ys, t) - cH / 2) * k, -k, t, tgy.get(t)) for t in sorted({p[0] for p in yk})]
        else:
            static['Tilt'] = -(ys - cH / 2) * k
    else:
        ts = {inp, outp}
        for ks_ in (xk, yk, axk, ayk, sxk, syk, rok):
            ts |= {p[0] for p in (ks_ or [])}
        ts = sorted(t for t in ts if inp - 1e-9 <= t <= outp + 1e-9)
        if rok or sxk or syk:   # rotacao/escala animadas com ancora deslocada: o movimento do centro e curvo -> por quadro
            n = int(round((outp - inp) * rfps)); ts = sorted(set(ts) | {inp + i / rfps for i in range(0, n + 1)})
        pan, tilt = [], []
        for t in ts:
            X_, Y_ = ev(xk, xs, t), ev(yk, ys, t); Ax, Ay = ev(axk, ax, t), ev(ayk, ay, t)
            Sx, Sy = ev(sxk, sx, t) / 100.0, ev(syk, sy, t) / 100.0; th = math.radians(ev(rok, ro, t))
            dx, dy = (sw / 2 - Ax) * Sx, (sh / 2 - Ay) * Sy
            cx = X_ + dx * math.cos(th) - dy * math.sin(th); cy = Y_ + dx * math.sin(th) + dy * math.cos(th)
            pan.append([d_of(t), (cx - cW / 2) * k]); tilt.append([d_of(t), -(cy - cH / 2) * k])
        if animado and len(ts) > 1:
            keys['Pan'], keys['Tilt'] = pan, tilt
        else:
            static['Pan'], static['Tilt'] = pan[0][1], tilt[0][1]
        if len(ts) > 3:
            avisos.append(T('"%s": âncora fora do centro ou animada, o movimento foi convertido quadro a quadro (visual igual)',
                            '"%s": off-center or animated anchor, motion was converted frame by frame (same visual)') % nm)
    tgz_x, tgz_y = _tags(sxk), _tags(syk)
    def _zmult(ks_):
        def m(t):
            v = ev(ks_, 0.0, t)
            return (1 if v >= 0 else -1) * k / (100.0 * f)
        return m
    if sxk:
        keys['ZoomX'] = [_pt3(d_of, lambda t: zoom(ev(sxk, sx, t)), _zmult(sxk), t, tgz_x.get(t)) for t in sorted({p[0] for p in sxk})]
    else:
        static['ZoomX'] = zoom(sx)
    if syk:
        keys['ZoomY'] = [_pt3(d_of, lambda t: zoom(ev(syk, sy, t)), _zmult(syk), t, tgz_y.get(t)) for t in sorted({p[0] for p in syk})]
    else:
        static['ZoomY'] = zoom(sy)
    if rok:
        tgr = _tags(rok)
        keys['RotationAngle'] = [_pt3(d_of, lambda t: -ev(rok, ro, t), -1.0, t, tgr.get(t)) for t in sorted({p[0] for p in rok})]
    elif ro: static['RotationAngle'] = -ro
    if opk:
        tgo = _tags(opk)
        keys['Opacity'] = [_pt3(d_of, lambda t: ev(opk, op, t), 1.0, t, tgo.get(t)) for t in sorted({p[0] for p in opk})]
    elif op is not None: static['Opacity'] = op
    _apara_chaves(keys, round(abs(outp - inp) * rfps, 3), avisos, nm)
    return static, _reduz(keys)


def _apara_chaves(keys, df, avisos, nm):
    """chaves de midia fora da regiao aparada (o Premiere aceita keys antes do inPoint/depois do outPoint)
    virariam tempos negativos/fora-da-faixa no DRT: limita a [0, duracao do clipe] e funde colisoes de quadro."""
    for pr in list(keys):
        antes = len(keys[pr])
        keys[pr] = [kv for kv in keys[pr] if -0.49 <= kv[0] <= df + 0.49]
        if len(keys[pr]) < antes:
            avisos.append(T('"%s": %d chave(s) de %s fora do trecho aparado foram cortadas',
                            '"%s": %d %s keyframe(s) outside the trimmed range were dropped') % (nm, antes - len(keys[pr]), pr))
        keys[pr] = _dedup_frames(keys[pr])   # o blob so guarda 1 chave por quadro: rede de seguranca (o _melhor ja dedupou)
        if not keys[pr]:
            del keys[pr]


def _dedup_frames(pts):
    """1 chave por quadro (criterio do blob): fica a mais recente."""
    dedup = []
    for kv in pts:
        if dedup and int(round(kv[0])) == int(round(dedup[-1][0])): dedup[-1] = kv
        else: dedup.append(kv)
    return dedup


# ---------- After Effects ----------
# cores de clipe do Resolve (nomes aceitos por SetClipColor) com RGB aproximado do swatch
CORES_RESOLVE = [
    ('Orange', (235, 130, 40)), ('Apricot', (235, 170, 105)), ('Yellow', (235, 200, 60)),
    ('Lime', (150, 190, 70)), ('Olive', (125, 140, 60)), ('Green', (80, 170, 90)),
    ('Teal', (75, 175, 175)), ('Navy', (70, 95, 170)), ('Blue', (90, 140, 235)),
    ('Purple', (140, 90, 200)), ('Violet', (190, 120, 205)), ('Pink', (233, 140, 160)),
    ('Red', (233, 75, 60)), ('Brown', (160, 110, 75)), ('Chocolate', (120, 75, 50)),
    ('Beige', (200, 180, 140))]

# label do After (layer.label 1..16) -> cor do Resolve por familia de matiz
COR_AE = {1: 'Red', 2: 'Yellow', 3: 'Teal', 4: 'Pink', 5: 'Violet', 6: 'Apricot', 7: 'Lime',
          8: 'Blue', 9: 'Green', 10: 'Purple', 11: 'Orange', 12: 'Brown', 13: 'Pink',
          14: 'Teal', 15: 'Beige', 16: 'Green'}


def _hsv(rgb):
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return h * 360.0, s, v


# Efeitos Premiere/AE -> plugin-id OFX do Resolve FX (colhidos do EffectFiltersBA real).
# matchName vem tipo "AE.ADBE Gaussian Blur 2" ou displayName; chave = nome em minusculo
# sem prefixo/sufixo numerico. SO ids verificados por roundtrip DRT: id errado corrompe o import.
_FX_OFx = {
    # Blur & Sharpen
    'gaussian blur': 'com.blackmagicdesign.resolvefx.gaussianblur',
    'fast blur': 'com.blackmagicdesign.resolvefx.boxblur',
    'box blur': 'com.blackmagicdesign.resolvefx.boxblur',
    'directional blur': 'com.blackmagicdesign.resolvefx.directionalblur',
    'camera blur': 'com.blackmagicdesign.resolvefx.lensblur',
    'lens blur': 'com.blackmagicdesign.resolvefx.lensblur',
    'bokeh blur': 'com.blackmagicdesign.resolvefx.lensblur',
    'focus blur': 'com.blackmagicdesign.resolvefx.cinefocus',
    'mosaic': 'com.blackmagicdesign.resolvefx.mosaicblur',
    'radial blur': 'com.blackmagicdesign.resolvefx.radialblur',
    'zoom blur': 'com.blackmagicdesign.resolvefx.zoomblur',
    'prism blur': 'com.blackmagicdesign.resolvefx.prismblur',
    'tilt-shift blur': 'com.blackmagicdesign.resolvefx.tiltshiftblur',
    'motion blur': 'com.blackmagicdesign.resolvefx.motionblur',
    'sharpen': 'com.blackmagicdesign.resolvefx.sharpen',
    'unsharp mask': 'com.blackmagicdesign.resolvefx.ultrasharpen',
    'sharpen edges': 'com.blackmagicdesign.resolvefx.sharpenedgeplugin',
    'reduce interlace flicker': 'com.blackmagicdesign.resolvefx.deflicker',
    # Color Correction (so equivalentes reais; Lumetri/cor de pagina Color e fora)
    'gradient tint': 'com.blackmagicdesign.resolvefx.splittone',
    'tint': 'com.blackmagicdesign.resolvefx.splittone',
    'invert': 'com.blackmagicdesign.resolvefx.invertcolor',
    'invert color': 'com.blackmagicdesign.resolvefx.invertcolor',
    'video limiter': 'com.blackmagicdesign.resolvefx.gamutlimiter',
    'vignette': 'com.blackmagicdesign.resolvefx.vignette',
    'deband': 'com.blackmagicdesign.resolvefx.deband',
    'dehaze': 'com.blackmagicdesign.resolvefx.dehaze',
    # Distort
    'lens distortion': 'com.blackmagicdesign.resolvefx.lensdistortion',
    'mirror': 'com.blackmagicdesign.resolvefx.mirror',
    'spherize': 'com.blackmagicdesign.resolvefx.dent',
    'twirl': 'com.blackmagicdesign.resolvefx.vortex',
    'wave warp': 'com.blackmagicdesign.resolvefx.waviness',
    'ripple': 'com.blackmagicdesign.resolvefx.ripple',
    # Keying
    'color key': 'com.blackmagicdesign.resolvefx.ofxhslkeyer',
    'extract': 'com.blackmagicdesign.resolvefx.ofxlumakeyer',
    'luma key': 'com.blackmagicdesign.resolvefx.ofxlumakeyer',
    'luma matte key': 'com.blackmagicdesign.resolvefx.ofxlumakeyer',
    'ultra key': 'com.blackmagicdesign.resolvefx.ofx3dkeyer',
    # Noise & Grain
    'dust & scratches': 'com.blackmagicdesign.resolvefx.dustbuster',
    'alpha dust & scratches': 'com.blackmagicdesign.resolvefx.dustbuster',
    'median': 'com.blackmagicdesign.resolvefx.noisereduction',
    'noise': 'com.blackmagicdesign.resolvefx.fastnoise',
    'add grain': 'com.blackmagicdesign.resolvefx.filmgrain',
    'film grain': 'com.blackmagicdesign.resolvefx.filmgrain',
    'remove grain': 'com.blackmagicdesign.resolvefx.noisereduction',
    # Transform / Perspective
    'transform': 'com.blackmagicdesign.resolvefx.transform',
    'basic 3d': 'com.blackmagicdesign.resolvefx.transform',
    '3d rotate': 'com.blackmagicdesign.resolvefx.transform',
    'crop': 'com.blackmagicdesign.resolvefx.transform',
    'camera shake': 'com.blackmagicdesign.resolvefx.camerashake',
    'wiggle': 'com.blackmagicdesign.resolvefx.camerashake',
    'picture-in-picture': 'com.blackmagicdesign.resolvefx.pictureinpicture',
    'picture in picture': 'com.blackmagicdesign.resolvefx.pictureinpicture',
    # Stylize / Time / Glows
    'find edges': 'com.blackmagicdesign.resolvefx.edgedetect',
    'emboss': 'com.blackmagicdesign.resolvefx.emboss',
    'strobe light': 'com.blackmagicdesign.resolvefx.stopmotion',
    'posterize time': 'com.blackmagicdesign.resolvefx.stopmotion',
    'echo': 'com.blackmagicdesign.resolvefx.motiontrails',
    'alpha glow': 'com.blackmagicdesign.resolvefx.glow',
    'glow': 'com.blackmagicdesign.resolvefx.glow',
    'drop shadow': 'com.blackmagicdesign.resolvefx.dropshadow',
}

def _avisa_fx(item, nm, avisos, rotulo='clipe'):
    """avisa quando um item pulado carregava efeitos (morte silenciosa vira explicita)."""
    n = len(item.get('effects') or [])
    if n:
        avisos.append(T('%s "%s": %d efeito(s) nao convertido(s) (item sem midia/nao copiado)',
                        '%s "%s": %d effect(s) not converted (item without media/not copied)') % (rotulo, nm, n, rotulo, nm, n))


def _fx_chave(nome):
    """'AE.ADBE Gaussian Blur 2' / 'Gaussian Blur' -> 'gaussian blur'."""
    import re as _r
    n = nome.split('.')[-1]                       # matchName: sobra o nome amigavel
    n = _r.sub(r'^(AE|ADBE)\s+', '', n.strip())    # prefixo de namespace ("ADBE Gaussian Blur")
    n = _r.sub(r'\s*\d+$', '', n.strip())          # sufixo de versao ("... 2")
    return _r.sub(r'\s+', ' ', n.lower())


# Parametros com unidade PROVADA igual dos dois lados (ranges medidos no schema OFX real,
# tests/fx_params.json). Sem escala inventada: px->normalizado nao entra, vira aviso.
# {plugin_id: {param_ofx: (nome_curto_PR, tipo)}}  tipo: bool|pct|deg|cor|int
_FX_PARAMS = {
    'com.blackmagicdesign.resolvefx.gaussianblur': {
        'HStrength': ('Blurriness', 'px_blur_x'),
        'VStrength': ('Blurriness', 'px_blur_y')},
    'com.blackmagicdesign.resolvefx.boxblur': {
        'HStrength': ('Blur Radius', 'px_blur_x'),
        'VStrength': ('Blur Radius', 'px_blur_y'),
        'Iterations': ('Iterations', 'num')},
    'com.blackmagicdesign.resolvefx.sharpen': {
        'sharpen': ('Sharpen Amount', 'map_1_5')},
    'com.blackmagicdesign.resolvefx.ultrasharpen': {
        'sharpenStrength': ('Sharpen Amount', 'pct500')},
    'com.blackmagicdesign.resolvefx.glow': {
        'threshold': ('Glow Threshold', 'pct255'),
        'brightness': ('Glow Intensity', 'mul2')},
    'com.blackmagicdesign.resolvefx.vignette': {
        'softness': ('Feather', 'pct'),
        'size': ('Midpoint', 'pct')},
    'com.blackmagicdesign.resolvefx.emboss': {
        'angle': ('Direction', 'deg'),
        'power': ('Relief', 'num')},
    'com.blackmagicdesign.resolvefx.dent': {
        'strength': ('Amount', 'pct')},
    'com.blackmagicdesign.resolvefx.directionalblur': {
        'BlurAngle': ('Direction', 'deg'),
        'ShutterAngle': ('Shutter Angle', 'deg')},
    'com.blackmagicdesign.resolvefx.dropshadow': {
        'shadowAngle': ('Direction', 'deg'),
        'shadowStrength': ('Opacity', 'pct'),
        'shadowBlur': ('Softness', 'pct'),
        'shadowColorRed': ('Shadow Color', 'corR'),
        'shadowColorGreen': ('Shadow Color', 'corG'),
        'shadowColorBlue': ('Shadow Color', 'corB'),
        'isDropShadowOnly': ('Shadow Only', 'bool')},
    'com.blackmagicdesign.resolvefx.transform': {
        'rotate': ('Rotation', 'deg'),
        'scaleX': ('Scale Width', 'pct'), 'scaleY': ('Scale Height', 'pct'),
        'zoom': ('Scale', 'pct'),
        'yaw': ('Swivel', 'deg'), 'pitch': ('Tilt', 'deg'),
        'cropL': ('Left', 'pct'), 'cropR': ('Right', 'pct'),
        'cropT': ('Top', 'pct'), 'cropB': ('Bottom', 'pct')},
    'com.blackmagicdesign.resolvefx.mosaicblur': {
        'PixelFrequency': ('Horizontal Blocks', 'num')},
    'com.blackmagicdesign.resolvefx.splittone': {
        'strength': ('Amount to Tint', 'pct'),
        'shadowH': ('Map Black To', 'cor2hue'), 'shadowS': ('Map Black To', 'cor2sat'),
        'highlightH': ('Map White To', 'cor2hue'), 'highlightS': ('Map White To', 'cor2sat')},
    'com.blackmagicdesign.resolvefx.vortex': {
        'angle': ('Angle', 'deg')},
    'com.blackmagicdesign.resolvefx.mirror': {
        'angle1': ('Reflection Angle', 'deg180'), 'flip1': ('Invert', 'bool')},
    'com.blackmagicdesign.resolvefx.ofxlumakeyer': {
        'isInvert': ('Invert', 'bool')},
}

# plugin-id do blob -> REGS_ID do tool Fusion (ofx.<ns>.<Camel>): p/ efeitos com param animado,
# que vao pra Fusion comp do clipe (o blob grupo-50 nao serializa chaves de OFX)
_FX_CAMEL = {k: 'ofx.' + k.rsplit('.', 1)[0] + '.' + v for k, v in {
    'com.blackmagicdesign.resolvefx.gaussianblur': 'GaussianBlur',
    'com.blackmagicdesign.resolvefx.boxblur': 'BoxBlur',
    'com.blackmagicdesign.resolvefx.directionalblur': 'DirectionalBlur',
    'com.blackmagicdesign.resolvefx.lensblur': 'LensBlur',
    'com.blackmagicdesign.resolvefx.cinefocus': 'CineFocus',
    'com.blackmagicdesign.resolvefx.mosaicblur': 'MosaicBlur',
    'com.blackmagicdesign.resolvefx.radialblur': 'RadialBlur',
    'com.blackmagicdesign.resolvefx.zoomblur': 'ZoomBlur',
    'com.blackmagicdesign.resolvefx.prismblur': 'PrismBlur',
    'com.blackmagicdesign.resolvefx.tiltshiftblur': 'TiltShiftBlur',
    'com.blackmagicdesign.resolvefx.motionblur': 'MotionBlur',
    'com.blackmagicdesign.resolvefx.sharpen': 'Sharpen',
    'com.blackmagicdesign.resolvefx.ultrasharpen': 'UltraSharpen',
    'com.blackmagicdesign.resolvefx.sharpenedgeplugin': 'SharpenEdgePlugin',
    'com.blackmagicdesign.resolvefx.deflicker': 'Deflicker',
    'com.blackmagicdesign.resolvefx.splittone': 'SplitTone',
    'com.blackmagicdesign.resolvefx.invertcolor': 'InvertColor',
    'com.blackmagicdesign.resolvefx.gamutlimiter': 'GamutLimiter',
    'com.blackmagicdesign.resolvefx.vignette': 'Vignette',
    'com.blackmagicdesign.resolvefx.deband': 'Deband',
    'com.blackmagicdesign.resolvefx.dehaze': 'Dehaze',
    'com.blackmagicdesign.resolvefx.lensdistortion': 'LensDistortion',
    'com.blackmagicdesign.resolvefx.mirror': 'Mirror',
    'com.blackmagicdesign.resolvefx.dent': 'Dent',
    'com.blackmagicdesign.resolvefx.vortex': 'Vortex',
    'com.blackmagicdesign.resolvefx.waviness': 'Waviness',
    'com.blackmagicdesign.resolvefx.ripple': 'Ripple',
    'com.blackmagicdesign.resolvefx.ofxhslkeyer': 'OFXHSLKeyer',
    'com.blackmagicdesign.resolvefx.ofxlumakeyer': 'OFXLumaKeyer',
    'com.blackmagicdesign.resolvefx.ofx3dkeyer': 'OFX3DKeyer',
    'com.blackmagicdesign.resolvefx.dustbuster': 'DustBuster',
    'com.blackmagicdesign.resolvefx.noisereduction': 'NoiseReduction',
    'com.blackmagicdesign.resolvefx.filmgrain': 'FilmGrain',
    'com.blackmagicdesign.resolvefx.transform': 'Transform',
    'com.blackmagicdesign.resolvefx.camerashake': 'CameraShake',
    'com.blackmagicdesign.resolvefx.pictureinpicture': 'PictureInPicture',
    'com.blackmagicdesign.resolvefx.edgedetect': 'EdgeDetect',
    'com.blackmagicdesign.resolvefx.emboss': 'Emboss',
    'com.blackmagicdesign.resolvefx.stopmotion': 'StopMotion',
    'com.blackmagicdesign.resolvefx.motiontrails': 'MotionTrails',
    'com.blackmagicdesign.resolvefx.glow': 'Glow',
    'com.blackmagicdesign.resolvefx.dropshadow': 'DropShadow',
}.items()}
_FX_CAMEL['com.blackmagicdesign.resolvefx.fastnoise'] = 'FastNoise'   # tool Fusion nativa (nao e OFX)


def _conv_val(tipo, v, rW=None, rH=None):
    """Um valor Adobe -> valor OFX conforme a unidade. Devolve None quando nao converte.
    px_blur_x/y: medido no Resolve — sigma_px = 0.1 * dim_do_frame * Strength^2 (Strength
    horizontal escala com a largura, vertical com a altura); Blurriness (px) do Premiere
    e tratado como raio (~2.5 sigma) — aproximacao honesta, nao exata."""
    x = v[0] if isinstance(v, (list, tuple)) else v
    if tipo == 'pct255':
        return float(x) / 255.0
    if tipo == 'pct500':
        return min(1.0, float(x) / 500.0)
    if tipo == 'mul2':
        return min(10.0, float(x) * 2.0)
    if tipo == 'map_1_5':
        return min(5.0, 1.0 + 4.0 * float(x) / 500.0)
    if tipo in ('px_blur_x', 'px_blur_y'):
        dim = rW if tipo == 'px_blur_x' else rH          # medido: sigma = 0.1 * dim * S^2 (H->largura, V->altura)
        if dim is None: return None
        import math
        return min(1.0, max(0.0, math.sqrt((float(x) / 2.5) / (0.1 * dim))))
    if tipo == 'bool':
        return 1 if x else 0
    if tipo == 'pct':
        return float(x) / 100.0
    if tipo in ('deg', 'num'):
        return float(x)
    if tipo == 'deg180':
        return ((float(x) + 180.0) % 360.0) - 180.0
    if tipo in ('cor2hue', 'cor2sat'):
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            import colorsys
            r, g, b = (float(y) for y in v[:3])
            if max(r, g, b) > 1.0: r, g, b = r / 255, g / 255, b / 255
            h_, s_, _ = colorsys.rgb_to_hsv(r, g, b)
            return h_ if tipo == 'cor2hue' else s_
        return None
    if tipo.startswith('cor'):
        i = 'RGB'.index(tipo[-1])
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            return float(v[i]) / (255.0 if max(v[:3]) > 1.0 else 1.0)
    return None


def _fx_params(pid, params_pr, avisos, rotulo, nm_item, nm_fx, conv_t=None, rW=None, rH=None):
    """Converte os params lidos do Adobe nos mapeados do _FX_PARAMS.
    conv_t: media/comp tempo (s) -> quadro relativo ao inicio do clipe (p/ chaves animadas).
    Devolve ({param_ofx: valor}, {param_ofx: [(quadro_rel, valor)]}, n_drop, n_anim)."""
    out, anim_out, drop, anim = {}, {}, 0, 0
    if not params_pr:
        return out, anim_out, drop, anim
    tab = _FX_PARAMS.get(pid) or {}
    for ofx, (nm_pr, tipo) in tab.items():
        e = params_pr.get(nm_pr)
        if e is None:
            continue
        if e.get('anim'):
            anim += 1
            if conv_t is not None:
                src = e.get('samples') or e.get('keys') or []
                ks = []
                for t_, v_ in src:
                    try:
                        cv = _conv_val(tipo, v_, rW, rH)
                        if cv is not None:
                            ks.append((int(round(conv_t(t_))), cv))
                    except Exception:
                        drop += 1
                ks = _dedup_frames(ks)
                if len(ks) > 1:
                    anim_out[ofx] = ks
                    continue
        v = e.get('v')
        if v is None:
            continue
        try:
            cv = _conv_val(tipo, v, rW, rH)
            if cv is not None:
                out[ofx] = cv
        except Exception:
            drop += 1
    lidos = set(params_pr)
    mapeados = {v_[0] for v_ in tab.values()}
    n_lidos_extra = len(lidos - mapeados)
    anim_livre = anim - len(anim_out)
    if n_lidos_extra or anim_livre:
        avisos.append(T('%s "%s": efeito "%s" com %d param(s) sem conversao%s',
                        '%s "%s": effect "%s" has %d param(s) without conversion%s')
                      % (rotulo, nm_item, nm_fx, n_lidos_extra + drop,
                         T(' (%d animados vao estaticos)', ' (%d animated come out static)') % anim_livre if anim_livre else ''))
    return out, anim_out, drop, anim


# efeitos de AUDIO do Premiere -> id Fairlight do Resolve (AddEffect('audio', id));
# os 29 ids vieram de Resolve.GetEffectsList('audio'). Params vao padrao + aviso.
_AF = 'Audio FX/Fairlight FX/'
_AFX = {
    'chorus': _AF + 'Chorus', 'flanger': _AF + 'Flanger', 'modulation': _AF + 'Modulation',
    'phaser': _AF + 'Modulation',
    'deesser': _AF + 'De-Esser', 'de-esser': _AF + 'De-Esser', 'dehummer': _AF + 'De-Hummer',
    'delay': _AF + 'Delay', 'echo': _AF + 'Echo', 'multitap delay': _AF + 'Delay',
    'distortion': _AF + 'Distortion', 'guitar suite': _AF + 'Distortion', 'lo-fi': _AF + 'Distortion',
    'denoise': _AF + 'Noise Reduction', 'noise reduction': _AF + 'Noise Reduction',
    'dereverb': _AF + 'Noise Reduction',
    'dynamics': _AF + 'Multiband Compressor', 'multiband compressor': _AF + 'Multiband Compressor',
    'single-band compressor': _AF + 'Multiband Compressor', 'compressor': _AF + 'Multiband Compressor',
    'hard limiter': _AF + 'Limiter', 'limiter': _AF + 'Limiter',
    'eq': _AF + 'Fairlight EQ', 'parametric eq': _AF + 'Fairlight EQ', 'aeq': _AF + 'Fairlight EQ',
    'treble': _AF + 'Fairlight EQ', 'bass': _AF + 'Fairlight EQ', 'notch filter': _AF + 'Fairlight EQ',
    'amplify': _AF + 'Gain', 'gain': _AF + 'Gain',
    'pitch shifter': _AF + 'Pitch', 'pitch': _AF + 'Pitch',
    'reverb': _AF + 'Reverb', 'studio reverb': _AF + 'Reverb', 'studios reverb': _AF + 'Reverb', 'surround reverb': _AF + 'Reverb',
    'vocal enhancer': _AF + 'Vocal Channel', 'mastering': _AF + 'Vocal Channel',
    'stereo expander': _AF + 'Stereo Width', 'stereo width': _AF + 'Stereo Width',
    'dialogue processor': _AF + 'Dialogue Processor', 'soft clipper': _AF + 'Soft Clipper',
}


def _fx_nome(fx):
    """efeito pode vir string (clipboard antigo) ou dict {nome, params} (novo)."""
    if isinstance(fx, dict):
        return fx.get('nome') or '', fx.get('params') or {}
    return str(fx), {}


def _cor_rgb(v):
    """inteiro asl.clip.label.color do Premiere (0xRRGGBB) -> cor do Resolve mais proxima.
    Casamento por matiz: os swatches do Premiere sao bem mais escuros que os do Resolve,
    entao RGB puro sempre desviava para Chocolate/dark. Hue domina, saturacao desempata."""
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    h, s, _ = _hsv((r, g, b))
    def dist(c):
        hc, sc, _ = _hsv(c[1])
        dh = min(abs(h - hc), 360 - abs(h - hc)) / 180.0
        return dh * 2.0 + abs(s - sc)
    return min(CORES_RESOLVE, key=dist)[0]


# Composite/blend mode -> enum int do Resolve (constantes resolve.COMPOSITE_*: SetProperty('CompositeMode', int))
_BLEND = {'NORMAL': 0, 'ADD': 1, 'SUBTRACT': 2, 'DIFFERENCE': 3, 'MULTIPLY': 4, 'SCREEN': 5,
          'OVERLAY': 6, 'HARDLIGHT': 7, 'SOFTLIGHT': 8, 'DARKEN': 9, 'LIGHTEN': 10,
          'COLOR_DODGE': 11, 'COLOR_BURN': 12, 'EXCLUSION': 13, 'HUE': 14, 'SATURATION': 15,
          'COLOR': 16, 'DIVIDE': 18, 'LINEAR_DODGE': 19, 'LINEAR_BURN': 20,
          'LINEAR_LIGHT': 21, 'VIVID_LIGHT': 22, 'PIN_LIGHT': 23, 'HARD_MIX': 24,
          'LIGHTER_COLOR': 25, 'DARKER_COLOR': 26, 'LUMINOSITY': 30}
# Premiere 'Blend Mode' (Opacity.getValue): enum interno 1-based ALFABETICO, Subtract/Divide no fim
# (nao e o indice do dropdown! Normal=18 medido em clips default) — verificado PR 25.x
_PR_BLEND = ['COLOR_BURN', 'COLOR_DODGE', 'DARKEN', 'DARKER_COLOR', 'DIFFERENCE', 'DISSOLVE',
             'EXCLUSION', 'HARD_LIGHT', 'HARD_MIX', 'HUE', 'LIGHTEN', 'LIGHTER_COLOR',
             'LINEAR_BURN', 'LINEAR_DODGE', 'LINEAR_LIGHT', 'LUMINOSITY', 'MULTIPLY', 'NORMAL',
             'OVERLAY', 'PIN_LIGHT', 'SATURATION', 'SCREEN', 'SOFT_LIGHT', 'VIVID_LIGHT',
             'SUBTRACT', 'DIVIDE']
# AE BlendingMode: enum = 5212+indice (DANCING_DISSOLVE ocupa o slot 2); >= 28 sao modos de matte
_AE_BLEND_OFF = 5212
_AE_BLEND = ['NORMAL', 'DISSOLVE', 'DANCING_DISSOLVE', 'DARKEN', 'MULTIPLY', 'COLOR_BURN', 'LINEAR_BURN',
             'DARKER_COLOR', 'LIGHTEN', 'SCREEN', 'COLOR_DODGE', 'LINEAR_DODGE', 'LIGHTER_COLOR',
             'OVERLAY', 'SOFT_LIGHT', 'HARD_LIGHT', 'VIVID_LIGHT', 'LINEAR_LIGHT', 'PIN_LIGHT',
             'HARD_MIX', 'DIFFERENCE', 'EXCLUSION', 'SUBTRACT', 'DIVIDE', 'HUE', 'SATURATION',
             'COLOR', 'LUMINOSITY']

_BLEND_NORM = {k.replace('_', ''): v for k, v in _BLEND.items()}   # PR/AE usam SOFT_LIGHT; o enum do Resolve nao tem '_'


def _composite(v, tab, off, rotulo, nm, avisos):
    if v is None: return None
    try: i = int(v) - off
    except Exception: return None
    nome = tab[i] if 0 <= i < len(tab) else None
    if nome is None:
        avisos.append(T('%s "%s": blend mode desconhecido (%s), ignorado',
                        '%s "%s": unknown blend mode (%s), ignored') % (rotulo, nm, v)); return None
    if nome == 'NORMAL': return None
    out = _BLEND_NORM.get(nome.replace('_', ''))
    if out is None:
        avisos.append(T('%s "%s": blend mode "%s" sem equivalente no Resolve',
                        '%s "%s": blend mode "%s" has no Resolve equivalent') % (rotulo, nm, nome)); return None
    return out


def _nome_projeto(bruto, padrao):
    import os
    n = os.path.splitext(bruto or '')[0].strip()
    return n or padrao


def ae_to_spec(data, rW, rH, rfps, name=None):
    comp = data['comp']; cW, cH = comp['width'], comp['height']
    avisos = []
    if abs(rW / cW - rH / cH) > 1e-6:
        avisos.append(T('proporcao da comp (%dx%d) difere da timeline do Resolve (%dx%d): usando escala %.4f',
                        'comp aspect ratio (%dx%d) differs from the Resolve timeline (%dx%d): using scale %.4f') % (cW, cH, rW, rH, min(rW / cW, rH / cH)))
    clips, audio_clips = [], []
    ajustes = []
    # precomp -> pseudo-camadas expandidas: tempos de chave/amostra remapeados de comp-local para
    # coordenadas do pai (t' = st + t/s); _rec0/_rec1 = span na timeline do pai; _trk = trilha
    # (sublayer de cima = trilha acima do pai). Media window fica em coordenadas da sub-comp.
    layers_exp = []
    for L in data['layers']:
        if not L.get('isComp'):
            layers_exp.append(L); continue
        nm = L['name']; sp = float(L.get('stretch', 100)) / 100.0
        if not L.get('subLayers') or sp <= 0:
            avisos.append(T('camada "%s" e precomp%s: ignorada', 'layer "%s" is a precomp%s: skipped') %
                          (nm, ' com stretch <= 0' if sp <= 0 else '', nm, ' with stretch <= 0' if sp <= 0 else '')); continue
        st_p = L['startTime']; base = comp['numLayers'] - L['index'] + 1
        nsub = L.get('subNumLayers') or len(L['subLayers'])
        if any((pp or {}).get('keys') for pp in (L.get('props') or {}).values()):
            avisos.append(T('precomp "%s": transform animado da precomp nao aplicado ao conteudo expandido',
                            'precomp "%s": animated precomp transform not applied to expanded content') % nm)
        for sub in L['subLayers']:
            ps = dict(sub)
            ps['_rec0'] = st_p + sub['inPoint'] / sp; ps['_rec1'] = st_p + sub['outPoint'] / sp
            ps['_trk'] = base + (nsub - sub['index'])
            for pp in (ps.get('props') or {}).values():
                if not pp: continue
                if pp.get('keys'):
                    for kk in pp['keys']: kk['t'] = st_p + kk['t'] / sp
                if pp.get('samples'):
                    pp['samples'] = [[st_p + t / sp, v] for t, v in pp['samples']]
            au = ps.get('audio')
            if au:
                if au.get('keys'):
                    for kk in au['keys']: kk['t'] = st_p + kk['t'] / sp
                if au.get('samples'):
                    au['samples'] = [[st_p + t / sp, v] for t, v in au['samples']]
            if ps.get('remap'):
                ps['remap'] = [[st_p + t / sp, v] for t, v in ps['remap']]
            if ps.get('remapKeys'):
                for kk in ps['remapKeys']: kk['t'] = st_p + kk['t'] / sp
            if ps.get('markers'):   # markers de layer: dominio sub-comp -> coordenadas do pai (lista nova)
                ps['markers'] = [dict(mk_, t=st_p + mk_['t'] / sp, dur=mk_.get('dur', 0) / sp) for mk_ in ps['markers']]
            for fx_ in (ps.get('effects') or []):            # idem: chaves de param de efeito animado
                for fx_p in (fx_.get('params') or {}).values():
                    if isinstance(fx_p, dict) and fx_p.get('keys'):
                        fx_p['keys'] = [[st_p + t / sp, v] for t, v in fx_p['keys']]
                    if isinstance(fx_p, dict) and fx_p.get('samples'):
                        fx_p['samples'] = [[st_p + t / sp, v] for t, v in fx_p['samples']]
            ps['name'] = '%s/%s' % (nm, sub['name'])
            layers_exp.append(ps)
    for L in layers_exp:
        nm = L['name']
        trk = int(L.get('_trk', comp['numLayers'] - L['index'] + 1))
        r0, r1 = L.get('_rec0', L['inPoint']), L.get('_rec1', L['outPoint'])   # span record (pai, se expandida)
        if L.get('adjustment'):
            ajustes.append({'nome': nm, 'track': trk,
                            'rec_start': int(round(min(r0, r1) * rfps)),
                            'rec_dur': max(1, int(round(abs(r1 - r0) * rfps)))})
            _avisa_fx(L, nm, avisos, 'camada'); continue
        if L.get('semFootage') or not L.get('mediaPath'):
            avisos.append(T('camada "%s" sem arquivo de midia (precomp/solido/texto/forma): ignorada',
                            'layer "%s" has no media file (precomp/solid/text/shape): skipped') % nm)
            _avisa_fx(L, nm, avisos, 'camada'); continue
        if not L.get('enabled', True): avisos.append(T('camada "%s" desligada: ignorada', 'layer "%s" disabled: skipped') % nm); continue
        reverso = L.get('stretch', 100) < 0
        congelada = L.get('stretch', 100) == 0   # stretch 0 = layer congelada no quadro do in-point
        if reverso and L.get('timeRemap') and L.get('remap'):
            avisos.append(T('camada "%s" com stretch %s (reverso/congelar%s): ainda nao suportado, ignorada',
                            'layer "%s" with stretch %s (reverse/freeze%s): not supported yet, skipped') %
                          (nm, L.get('stretch'), ' + Time Remap' if reverso else '', nm, L.get('stretch'), ' + Time Remap' if reverso else '')); continue
        if not L.get('hasVideo', True) and not L.get('hasAudio'):
            avisos.append(T('camada "%s" sem arquivo de video (precomp/solido/texto/forma): ignorada',
                            'layer "%s" has no video file (precomp/solid/text/shape): skipped') % nm)
            _avisa_fx(L, nm, avisos, 'camada'); continue
        if L.get('parent'): avisos.append(T('camada "%s": tem pai (parenting nao convertido)', 'layer "%s": has a parent (parenting not converted)') % nm)
        sw, sh = L.get('sourceW') or cW, L.get('sourceH') or cH; mfps = float(L['mediaFps'])
        stretch = float(L.get('stretch', 100.0)); speed = 100.0 if congelada else 10000.0 / stretch; s = speed / 100.0
        st, inp, outp = L['startTime'], L['inPoint'], L['outPoint']
        sa_ = abs(s)   # stretch negativo: startTime = borda FINAL da layer e in/out trocam de papel
        if congelada:
            a_, b_ = (inp - st), (outp - st)   # janela de midia do take (sem stretch); o freeze fica no timemap plano
        elif reverso:
            a_, b_ = (st - max(inp, outp)) * sa_, (st - min(inp, outp)) * sa_
        else:
            a_, b_ = (inp - st) * sa_, (outp - st) * sa_
        src_in = int(round(min(a_, b_) * mfps)); src_out = int(round(max(a_, b_) * mfps))
        dur_f = max(1, int(round(abs(r1 - r0) * rfps)))
        remap = None
        if congelada:
            remap = {'points': [[0.0, src_in / mfps], [float(dur_f), src_in / mfps]]}   # timemap plano = quadro congelado
            if L.get('timeRemap') and L.get('remap'):
                avisos.append(T('camada "%s": congelada com Time Remap ativo — o freeze venceu e a rampa foi ignorada',
                                'layer "%s": frozen with active Time Remap — the freeze won and the ramp was skipped') % nm)
        elif reverso:
            remap = {'points': [[0.0, src_out / mfps], [float(dur_f), src_in / mfps]]}   # timemap descendente
            speed, s = 100.0, 1.0
        elif L.get('timeRemap') and L.get('remap'):
            # curva real tempo-da-comp -> tempo-da-midia (amostrada); reduz com tolerancia de 0.2 quadro de midia
            dens = [[(t - r0) * rfps, v] for t, v in L['remap']]
            pts = _rdp(dens, 0.2 / mfps)
            if any(b[1] < a[1] - 1e-6 for a, b in zip(pts, pts[1:])):
                avisos.append(T('camada "%s": Time Remap com trecho em reverso: reverso ainda nao suportado, ignorado',
                                'layer "%s": Time Remap with a reversed stretch: reverse not supported yet, skipped') % nm); continue
            if len(pts) < 2: pts = [pts[0], [pts[0][0] + 1, pts[0][1]]]
            remap = {'points': pts, 'dense': dens}
            if L.get('remapKeys'):   # nos do Time Remap com ease temporal -> timemap "eased" nativo (rampa editavel)
                remap['nodes'] = [[(k['t'] - r0) * rfps, k['v'], k['iI'], k['iO']] for k in L['remapKeys']]
            speed, s = 100.0, 1.0
            src_in = int(math.floor(min(p_[1] for p_ in pts) * mfps)); src_out = int(math.ceil(max(p_[1] for p_ in pts) * mfps)) + 1
        if L.get('hasAudio') and L.get('mediaPath'):
            au = L.get('audio') or {}
            ks_a = None
            if au.get('keys'):
                ks_a = _melhor([(k['t'], k['v']) for k in au['keys']],
                               [(t, v) for t, v in au.get('samples') or []], 0.2, rfps)
                ks_a = [_pt3(lambda t: round((t - r0) * rfps, 3), lambda t: float(_interp(ks_a, t)), 1.0, kv[0], (kv[2], kv[3]) if len(kv) > 3 else None) for kv in ks_a]
                df_a = round(abs(r1 - r0) * rfps, 3)
                ks_a = _dedup_frames([kv for kv in ks_a if -0.49 <= kv[0] <= df_a + 0.49]) or None
            audio_clips.append({'media': _uri2path(L['mediaPath']), 'media_fps': mfps, 'src_in': src_in, 'src_out': src_out,
                                'rec_start': int(round(min(r0, r1) * rfps)), 'rec_dur': dur_f,
                                'track': trk, 'speed': speed,
                                'volume_db': float(au.get('value') or 0.0), 'vol_keys': ks_a,
                                '_nome': nm, **({'remap': remap} if remap and not congelada else {}),
                                **({'cor': COR_AE[L['label']]} if L.get('label') in COR_AE else {})})
        if not L.get('hasVideo', True):
            _avisa_fx(L, nm, avisos, 'camada de audio')
            avisos.append(T('camada "%s" sem video: copiada como audio', 'layer "%s" has no video: copied as audio') % nm); continue
        if L.get('threeD'):
            avisos.append(T('camada "%s": 3D nao convertido — sai achatada em 2D', 'layer "%s": 3D not converted — flattened to 2D') % nm)
        if L.get('motionBlur'):
            avisos.append(T('camada "%s": motion blur nao convertido', 'layer "%s": motion blur not converted') % nm)
        P = L['props']
        if L.get('numMasks'):
            avisos.append(T('camada "%s": %d mascara(s) nao transferida(s)', 'layer "%s": %d mask(s) not transferred') % (nm, L['numMasks']))
        if L.get('dimensionsSeparated'):
            X, Y = _chan(P.get('PositionX'), fps=rfps), _chan(P.get('PositionY'), fps=rfps)
        else:
            X, Y = _chan(P.get('Position'), 0, fps=rfps), _chan(P.get('Position'), 1, fps=rfps)
        A = (_chan(P.get('Anchor'), 0, fps=rfps), _chan(P.get('Anchor'), 1, fps=rfps))
        S = (_chan(P.get('Scale'), 0, 0.2, rfps), _chan(P.get('Scale'), 1, 0.2, rfps))
        for pr in P.values():
            if pr and pr.get('expression'):
                avisos.append(T('camada "%s": expressao ativa (valor lido sem a expressao)',
                                'layer "%s": active expression (value read without the expression)') % nm); break
        static, keys = convert_channels(nm, rW, rH, rfps, cW, cH, sw, sh, X, Y, A, S, _chan(P.get('Rotation'), None, 0.1, rfps), _chan(P.get('Opacity'), None, 0.2, rfps),
                                        r0, r1, avisos)
        mks = None
        if L.get('markers'):   # marker de layer: t no dominio da layer -> offset no record do take
            mks = [{'d': int(round((m['t'] - min(r0, r1)) * rfps)), 'nome': m.get('name', ''),
                    'comentario': m.get('name', ''), 'tipo': m.get('tipo', 'Comment'),
                    'dur_f': max(1, int(round(m.get('dur', 0) * rfps)))} for m in L['markers']]
            mks = [m for m in mks if 0 <= m['d'] <= dur_f] or None
        fxc = []
        for fx in L.get('effects', []):
            nm_fx, prm = _fx_nome(fx)
            pid = _FX_OFx.get(_fx_chave(nm_fx))
            if pid:
                out, an, _, _ = _fx_params(pid, prm, avisos, 'camada', nm, nm_fx,
                                           conv_t=lambda t_: (t_ - min(r0, r1)) * rfps, rW=rW, rH=rH)
                fxc.append({'plugin': pid, 'params': out, **({'anim': an} if an else {})})
                avisos.append(T('camada "%s": efeito "%s" transferido%s',
                                'layer "%s": effect "%s" transferred%s')
                              % (nm, nm_fx, '' if out else T(' com parametros padrao', ' with default parameters')))
            else:
                avisos.append(T('camada "%s": efeito "%s" nao convertido', 'layer "%s": effect "%s" not converted') % (nm, nm_fx))
        clips.append({'media': _uri2path(L['mediaPath']), 'media_fps': mfps, 'src_in': src_in, 'src_out': src_out,
                      'rec_start': int(round(min(r0, r1) * rfps)), 'track': trk, 'speed': speed,
                      'static': static, 'keys': keys, '_nome': nm, **({'remap': remap} if remap else {}),
                      **({'markers': mks} if mks else {}),
                      **({'fx': fxc} if fxc else {}),
                      **({'composite': _cp} if (_cp := _composite(L.get('blendingMode'), _AE_BLEND, _AE_BLEND_OFF, 'camada', nm, avisos)) else {}),
                      **({'cor': COR_AE[L['label']]} if L.get('label') in COR_AE else {})})
    markers = [{'nome': m['name'], 'comentario': m.get('comentario', ''), 'tipo': m.get('tipo', 'Comment'),
                'start_f': int(round(m['start'] * rfps)), 'dur_f': int(round((m['end'] - m['start']) * rfps))}
               for m in data.get('markers') or []]
    return {'version': 1, 'name': name or comp['name'], 'bin': _nome_projeto(data.get('project'), 'After Effects (sem projeto)'),
            'fps': comp['fps'], 'width': comp['width'], 'height': comp['height'],
            **({'destino': data['destino']} if data.get('destino') else {}),
            **({'rampa': data['rampa']} if data.get('rampa') else {}),
            **({'markers': markers} if markers else {}),
            **({'ajustes': ajustes} if ajustes else {}),
            'clips': clips, 'audio_clips': audio_clips}, avisos


# ---------- Premiere ----------
def premiere_to_spec(data, rW, rH, rfps, name=None):
    seq = data['sequence']; sW, sH, sfps = seq['width'], seq['height'], seq['fps']
    avisos = []
    if abs(rW / sW - rH / sH) > 1e-6:
        avisos.append(T('proporcao da sequencia (%dx%d) difere da timeline do Resolve (%dx%d): usando escala %.4f',
                        'sequence aspect ratio (%dx%d) differs from the Resolve timeline (%dx%d): using scale %.4f') % (sW, sH, rW, rH, min(rW / sW, rH / sH)))
    clips = []; titulos = []; ajustes = []
    # sequencia aninhada -> pseudo-clipes expandidos (flatten): start/end/track nas coordenadas do pai
    # (sub-seq t=0 cai em start - inPoint); props/keys/samples ganham o mesmo offset de tempo.
    clips_exp = []
    for c in data['clips']:
        if not c.get('subSeq'):
            clips_exp.append(c); continue
        nm = c['name']
        if c.get('_aviso_subseq'):
            avisos.append(T('seq aninhada "%s" nao encontrada no .prproj salvo: speed/reverso/markers internos podem faltar (salve o projeto e copie de novo)',
                            'nested seq "%s" not found in the saved .prproj: inner speed/reverse/markers may be missing (save the project and copy again)') % nm)
        if abs(c.get('speed', 100.0) - 100.0) > 1e-6 or c.get('reversed') or c.get('remap'):
            avisos.append(T('seq aninhada "%s" com velocidade/reverso/rampa: nao expandida, ignorada',
                            'nested seq "%s" with speed/reverse/ramp: not expanded, skipped') % nm); continue
        off = c['start'] - c['inPoint']
        if c.get('subAudioCount'):
            avisos.append(T('seq aninhada "%s" tem trilhas de audio: so o video foi expandido',
                            'nested seq "%s" has audio tracks: only the video was expanded') % nm)
        for sub in c.get('subClips') or []:
            ps = dict(sub)
            ps['start'] = sub['start'] + off; ps['end'] = sub['end'] + off
            ps['track'] = c['track'] + sub['track'] - 1
            # props keys/samples e markers sao domínio MIDIA do sub-clipe — NAO levam off.
            # remap/knots sao domínio da SUB-SEQUENCIA — ganham o off do pai.
            if ps.get('remap'):
                ps['remap'] = [[t + off, v] for t, v in ps['remap']]
            rn = ps.get('remap_nodes')
            if rn and rn.get('absoluto') and rn.get('knots'):
                ps['remap_nodes'] = dict(rn, knots=[[k[0] + off] + list(k[1:]) for k in rn['knots']])
            ps['name'] = '%s/%s' % (nm, sub['name'])
            if (abs(ps.get('speed', 100.0) - 100.0) > 1e-6 or ps.get('reversed')) and \
               any((pp or {}).get('keys') for pp in (ps.get('props') or {}).values()):
                avisos.append(T('clipe "%s": velocidade/reverso dentro de nested com props animadas — tempos podem sair deslocados',
                                'clip "%s": speed/reverse inside nested with animated props — timing may come out shifted') % ps['name'])
            clips_exp.append(ps)
    for c in clips_exp:
        nm = c['name']
        if not c.get('enabled', True): avisos.append(T('clipe "%s" desativado: ignorado', 'clip "%s" disabled: skipped') % nm); continue
        if not c.get('mediaPath'):
            if not c.get('temPI') or c.get('texto') is not None:
                ent = {'nome': nm, 'texto': c.get('texto') or nm,
                       'rec_start': int(round(c['start'] * rfps)), 'rec_dur': int(round((c['end'] - c['start']) * rfps)),
                       'track': c['track']}
                p_ = c.get('props') or {}
                k_ = min(rW / sW, rH / sH)   # mesma compensacao de aspecto do convert_channels
                pos = (p_.get('Position') or {}).get('value')
                if pos is not None:
                    ent['pan'] = (pos[0] - 0.5) * sW * k_; ent['tilt'] = -(pos[1] - 0.5) * sH * k_
                sc_ = (p_.get('Scale') or {}).get('value')
                if sc_ is not None: ent['zoom'] = sc_ / 100.0
                ro_ = (p_.get('Rotation') or {}).get('value')
                if ro_: ent['rot'] = -ro_
                op_ = (p_.get('Opacity') or {}).get('value')
                if op_ is not None: ent['op'] = op_
                if any((pp or {}).get('keys') for pp in p_.values()):
                    avisos.append(T('titulo "%s": transform animado nao convertido (sai estatico)',
                                    'title "%s": animated transform not converted (comes out static)') % nm)
                titulos.append(ent)
            elif 'adjust' in nm.lower() or 'ajust' in nm.lower():
                ajustes.append({'nome': nm, 'track': c['track'],
                                'rec_start': int(round(c['start'] * rfps)),
                                'rec_dur': max(1, int(round((c['end'] - c['start']) * rfps)))})
                _avisa_fx(c, nm, avisos)
            else:
                avisos.append(T('clipe "%s" sem arquivo de midia (nested/gerador/camada de ajuste nomeada em outro idioma?): ignorado',
                                'clip "%s" has no media file (nested/generator/adjustment layer in another language?): skipped') % nm)
                _avisa_fx(c, nm, avisos)
            continue
        sw, sh = c.get('sourceW') or sW, c.get('sourceH') or sH
        mfps = float(c.get('mediaFps') or sfps)
        speed = float(c.get('speed') or 100.0); s = speed / 100.0
        # com velocidade != 100% o Premiere reporta inPoint/outPoint esticados: voltar a segundos de midia
        in_src = c['inPoint'] * s; out_src = c['outPoint'] * s
        remap = m_curve = None
        if c.get('frameHold') is not None:   # Frame Hold do Premiere: quadro congelado = timemap plano
            dur_f = max(1, int(round((c['end'] - c['start']) * rfps)))
            remap = {'points': [[0.0, c['frameHold']], [float(dur_f), c['frameHold']]]}
            # m_curve fica None: o Frame Hold NAO congela o audio linkado (ele toca normal no Premiere)
            if c.get('reversed') or abs(speed - 100.0) > 1e-6 or c.get('remap'):
                avisos.append(T('clipe "%s": Frame Hold combinado com velocidade/reverso/rampa — o freeze tem prioridade, o resto foi ignorado',
                                'clip "%s": Frame Hold combined with speed/reverse/ramp — the freeze takes priority, the rest was skipped') % nm)
            speed, s = 100.0, 1.0
        elif c.get('reversed'):
            dur_f = max(1, int(round((c['end'] - c['start']) * rfps)))
            remap = {'points': [[0.0, out_src], [float(dur_f), in_src]]}   # timemap descendente = reverso
            m_curve = [[c['start'], out_src], [c['end'], in_src]]
            speed, s = 100.0, 1.0
            if c.get('remap'):
                avisos.append(T('clipe "%s": reverso + Time Remapping — a rampa nao entra junto com o reverso',
                                'clip "%s": reverse + Time Remapping — the ramp is not carried with the reverse') % nm)
        elif c.get('remap'):      # speed ramp lido do .prproj pelo bridge: mesma rota do Time Remap do AE
            dens = [[(t - c['start']) * rfps, v] for t, v in c['remap']]
            pts = _rdp(dens, 0.2 / mfps)
            if any(b[1] < a[1] - 1e-6 for a, b in zip(pts, pts[1:])):
                avisos.append(T('clipe "%s": speed ramp com trecho em reverso: ainda nao suportado, ignorado',
                                'clip "%s": speed ramp with a reversed stretch: not supported yet, skipped') % nm); continue
            if len(pts) < 2: pts = [pts[0], [pts[0][0] + 1, pts[0][1]]]
            remap = {'points': pts, 'dense': dens}
            rn = c.get('remap_nodes')
            if rn and rn.get('knots'):   # nos do TimeRemapping com influencia -> timemap "eased" nativo (rampa editavel)
                ab = bool(rn.get('absoluto'))
                nds = []
                for t, v, tipo, iIn, iOut in rn['knots']:
                    eIn = min(iIn, 1.0) if iIn > 1e-4 else (1.0 / 3.0 if tipo in (7, 8) else 0.0)
                    eOut = min(iOut, 1.0) if iOut > 1e-4 else (1.0 / 3.0 if tipo in (7, 8) else 0.0)
                    nds.append([(t - c['start']) * rfps if ab else t * rfps, v, eIn, eOut])
                remap['nodes'] = nds
            m_curve = [list(p_) for p_ in c['remap']]    # t da sequencia (ABSOLUTO) -> t de midia (amostras cheias)
            speed, s = 100.0, 1.0
            in_src = min(p_[1] for p_ in c['remap']); out_src = max(p_[1] for p_ in c['remap'])
        base = min(sW / sw, sH / sh) if c.get('scaleToFrameSize') else 1.0     # Scale 100 = nativo ou ajustado ao quadro
        p = c['props']

        def tl(t, c=c, in_src=in_src, s=s): return c['start'] + (t - in_src) / s      # tempo de midia -> tempo da sequencia

        def chan(prop, idx=None, mult=1.0, tol=0.3, tl=tl, default=None, nome='?'):
            if not prop: return (default * mult if default is not None else None), None
            pick = (lambda v: v[idx]) if idx is not None else (lambda v: v)
            ks = None
            if m_curve is not None:
                if prop.get('samples2') is not None:
                    # 2a passada do leitor: valor ja avaliado nos tempos de midia REAIS m(d) — chaves em tempo de timeline
                    ks = [[t, pick(v) * mult] for t, v in prop['samples2']]
                else:
                    # fallback (clipboard sem a 2a passada): amostras do leitor estao em tempo de MIDIA — reamostra em m(d)
                    sm = [(t, pick(v)) for t, v in prop.get('samples') or []]
                    if sm:
                        n = int(round((c['end'] - c['start']) * rfps))
                        ks = [[c['start'] + d / rfps, _interp(sm, _interp(m_curve, c['start'] + d / rfps)) * mult] for d in range(n + 1)]
                    elif prop.get('keys') and idx in (None, 0):
                        avisos.append(T('clipe "%s": %s tem keyframes mas a reamostragem nao veio (saiu estatico)',
                                        'clip "%s": %s has keyframes but the resampling did not arrive (came out static)') % (nm, nome))
            elif prop.get('keys'):
                ks = [(tl(t), pick(v) * mult) for t, v in prop['keys']]
                ks = _melhor(ks, [(tl(t), pick(v) * mult) for t, v in prop.get('samples') or []], tol, rfps)
            v = prop.get('value')
            if v is None:
                return (default * mult if default is not None else None), ks      # getValue() falhou no leitor: usa o padrao
            return pick(v) * mult, ks
        X = chan(p.get('Position'), 0, sW, default=0.5, nome='Position'); Y = chan(p.get('Position'), 1, sH, default=0.5, nome='Position')
        Anc = (chan(p.get('Anchor'), 0, sw, default=0.5, nome='Anchor'), chan(p.get('Anchor'), 1, sh, default=0.5, nome='Anchor'))
        un = (p.get('UniformScale') or {}).get('value', True)
        sc = chan(p.get('Scale'), None, base, 0.2, default=100.0, nome='Scale')
        scw = chan(p.get('ScaleWidth'), None, base, 0.2, default=100.0, nome='ScaleWidth') if (un is False and p.get('ScaleWidth')) else sc
        S = (scw, sc)        # Premiere: Scale = altura (e largura se uniforme); Scale Width so se nao uniforme
        crops = {}
        for cp in ('CropLeft', 'CropRight', 'CropTop', 'CropBottom'):
            v, ks = chan(p.get(cp), None, 1.0, 0.5, tl, 0.0, cp)   # % de crop: mesma escala 0-100 no Resolve
            dim = rW if cp in ('CropLeft', 'CropRight') else rH
            if ks: crops[cp] = [_pt3(lambda t: round((t - c['start']) * rfps, 3), lambda t: _interp(ks, t) * dim / 100.0, dim / 100.0, kv[0], (kv[2], kv[3]) if len(kv) > 3 else None) for kv in ks]
            elif v: crops[cp] = v
        static, keys = convert_channels(nm, rW, rH, rfps, sW, sH, sw, sh, X, Y, Anc, S, chan(p.get('Rotation'), None, 1.0, 0.1, tl, 0.0, 'Rotation'), chan(p.get('Opacity'), None, 1.0, 0.2, tl, 100.0, 'Opacity'),
                                        c['start'], c['end'], avisos)
        tmp_c = {cp: cv for cp, cv in crops.items() if isinstance(cv, list)}
        _apara_chaves(tmp_c, round(abs(c['end'] - c['start']) * rfps, 3), avisos, nm)
        for cp, cv in crops.items():
            if isinstance(cv, list):
                if tmp_c.get(cp): keys[cp] = tmp_c[cp]
            else: static[cp] = cv
        def _rec_t(mt):   # tempo de midia -> tempo de sequencia dentro do take (inverte m_curve se houver)
            if m_curve:
                mc = sorted(m_curve, key=lambda q: q[1])      # monotona: inverte por bissecao linear
                if mt <= mc[0][1]: return mc[0][0]
                if mt >= mc[-1][1]: return mc[-1][0]
                for a_, b_ in zip(mc, mc[1:]):
                    if a_[1] <= mt <= b_[1]:
                        return a_[0] if b_[1] == a_[1] else a_[0] + (b_[0] - a_[0]) * (mt - a_[1]) / (b_[1] - a_[1])
                return mc[-1][0]
            return c['start'] + (mt - in_src) / s
        import re as _re
        fxc = []
        for fx in c.get('effects', []):
            nm_fx, prm = _fx_nome(fx)
            if _re.search(r'flip', nm_fx, _re.I) and _re.search(r'horizontal', nm_fx, _re.I): static['FlipX'] = True
            elif _re.search(r'flip', nm_fx, _re.I) and _re.search(r'vertical', nm_fx, _re.I): static['FlipY'] = True
            else:
                pid = _FX_OFx.get(_fx_chave(nm_fx))
                if pid:
                    def _fx_t(mt_):   # tempo de midia (s) -> quadro relativo ao inicio do clipe
                        rt = _rec_t(mt_) if m_curve else c['start'] + (mt_ - in_src) / s
                        return (rt - c['start']) * rfps
                    out, an, _, _ = _fx_params(pid, prm, avisos, 'clipe', nm, nm_fx, conv_t=_fx_t, rW=rW, rH=rH)
                    fxc.append({'plugin': pid, 'params': out, **({'anim': an} if an else {})})
                    avisos.append(T('clipe "%s": efeito "%s" transferido%s',
                                    'clip "%s": effect "%s" transferred%s')
                                  % (nm, nm_fx, '' if out else T(' com parametros padrao', ' with default parameters')))
                else:
                    avisos.append(T('clipe "%s": efeito "%s" nao convertido', 'clip "%s": effect "%s" not converted') % (nm, nm_fx))
        mks = None
        if c.get('markers'):   # marker de clipe: t em seg de midia -> offset no record do take
            mks = [{'d': int(round((_rec_t(m['t']) - c['start']) * rfps)),
                    'nome': m.get('nome', ''), 'comentario': m.get('comentario', ''),
                    'tipo': m.get('tipo', 'Comment'), 'dur_f': max(1, int(round(m.get('dur', 0) * rfps)))} for m in c['markers']]
            dur_c = int(round((c['end'] - c['start']) * rfps))
            mks = [m for m in mks if 0 <= m['d'] <= dur_c] or None   # so os que caem dentro do take
        clips.append({'media': _uri2path(c['mediaPath']), 'media_fps': mfps, 'src_in': int(round(in_src * mfps)), 'src_out': int(round(out_src * mfps)),
                      'rec_start': int(round(c['start'] * rfps)), 'track': c['track'], 'speed': speed,
                      'static': static, 'keys': keys, '_nome': nm, **({'remap': remap} if remap else {}),
                      **({'markers': mks} if mks else {}),
                      **({'_m_curve': m_curve} if m_curve else {}),
                      **({'fx': fxc} if fxc else {}),
                      **({'composite': _cp} if (_cp := _composite(c.get('blendMode'), _PR_BLEND, 1, 'clipe', nm, avisos)) else {}),
                      **({'cor': _cor_rgb(c['label_rgb'])} if c.get('label_rgb') is not None else {})})
    audio_clips = []
    for a in data.get('audio') or []:
        nm = a['name']
        if not a.get('enabled', True): avisos.append(T('audio "%s" desativado: ignorado', 'audio "%s" disabled: skipped') % nm); continue
        if not a.get('mediaPath'): avisos.append(T('audio "%s" sem arquivo de midia: ignorado', 'audio "%s" has no media file: skipped') % nm); continue
        media_a = _uri2path(a['mediaPath']); mfps_a = float(a.get('mediaFps') or sfps)
        speed_a = float(a.get('speed') or 100.0); sa = speed_a / 100.0
        in_src = a['inPoint'] * sa; out_src = a['outPoint'] * sa
        rec0f = int(round(a['start'] * rfps)); dur_f = int(round((a['end'] - a['start']) * rfps))
        link = None    # clipe de video ligado: mesma midia, mesma posicao E mesmo in-point -> herda o remap
        for c in clips:
            if c['media'] == media_a and abs(c['rec_start'] - rec0f) <= 2 and abs(c['src_in'] - int(round(in_src * mfps_a))) <= 2:
                link = c; break
        mc = link.get('_m_curve') if link else None
        aremap = link.get('remap') if (link and mc is not None) else None   # Frame Hold tem remap sem
        # m_curve: o audio linkado NAO congela junto (no Premiere o freeze e so do video)
        if a.get('reversed') and not aremap:
            aremap = {'points': [[0.0, out_src], [float(dur_f), in_src]]}   # timemap descendente = reverso
            mc = [[a['start'], out_src], [a['end'], in_src]]
        afx = []
        for fxa in a.get('effects', []):
            nm_fx, _ = _fx_nome(fxa)
            fid = _AFX.get(_fx_chave(nm_fx))
            if fid:
                afx.append({'id': fid, '_nome': nm_fx})
                avisos.append(T('audio "%s": efeito "%s" transferido (parametros padrao)', 'audio "%s": effect "%s" transferred (default parameters)') % (nm, nm_fx))
            else:
                avisos.append(T('audio "%s": efeito "%s" nao convertido', 'audio "%s": effect "%s" not converted') % (nm, nm_fx))
        pr = a.get('props') or {}
        vol, pan = pr.get('Level'), pr.get('Pan')
        vol_db = float(vol['value']) if vol and vol.get('value') is not None else 0.0
        pan_v = float(pan['value']) if pan and pan.get('value') is not None else None
        vol_ks = None
        if vol and vol.get('keys'):
            sm = [(t, v) for t, v in (vol.get('samples') or vol['keys'])]
            if mc:      # clipe com rampa: chaves em tempo de midia -> reamostra em m(d)
                vol_ks = _rdp([[d, _interp(sm, _interp(mc, a['start'] + d / rfps))] for d in range(dur_f + 1)], 0.2)
            else:
                def tl_a(t, in_src=in_src, sa=sa, a=a): return a['start'] + (t - in_src) / sa
                ks = [(tl_a(t), v) for t, v in vol['keys']]
                ks = _melhor(ks, [(tl_a(t), v) for t, v in vol.get('samples') or []], 0.2, rfps)
                vol_ks = _dedup_frames([kv for kv in (_pt3(lambda t: round((t - a['start']) * rfps, 3), lambda t: _interp(ks, t), 1.0, kvv[0], (kvv[2], kvv[3]) if len(kvv) > 3 else None) for kvv in ks) if -0.49 <= kv[0] <= dur_f + 0.49]) or None
        audio_clips.append({'media': media_a, 'media_fps': mfps_a, 'src_in': int(round(in_src * mfps_a)), 'src_out': int(round(out_src * mfps_a)),
                            'rec_start': rec0f, 'rec_dur': dur_f, 'track': a['track'], 'speed': speed_a,
                            'volume_db': vol_db, 'vol_keys': vol_ks, '_nome': nm,
                            **({'pan': pan_v} if pan_v is not None else {}),
                            **({'afx': afx} if afx else {}),
                            **({'remap': aremap} if aremap else {}),
                            **({'cor': _cor_rgb(a['label_rgb'])} if a.get('label_rgb') is not None else {})})
    # transicoes: so entram as que ficam inteiras dentro do conjunto copiado (corte com clipe dos dois lados)
    # nomes REAIS do Resolve testados via TimelineItem.AddTransition (categoria 'simple' ou
    # 'fusion' — os 67 templates do Templates.drfx foram verificados um a um).
    _PRETTY = {
        # Dissolve (simple)
        'Cross Dissolve': ('Cross Dissolve', 'simple'), 'Film Dissolve': ('Cross Dissolve', 'simple'),
        'Additive Dissolve': ('Additive Dissolve', 'simple'), 'Non-Additive Dissolve': ('Non-Additive Dissolve', 'simple'),
        'Dip to Black': ('Dip To Color Dissolve', 'simple'), 'Dip to White': ('Dip To Color Dissolve', 'simple'),
        'Dip to Color': ('Dip To Color Dissolve', 'simple'),
        'Morph Cut': ('Smooth Cut', 'simple'), 'Smooth Cut': ('Smooth Cut', 'simple'),
        'Blur Dissolve': ('Blur Dissolve', 'simple'), 'Lens Blur': ('Blur Dissolve', 'simple'),
        # Wipe/Slide/Iris (simple)
        'Wipe': ('Edge Wipe', 'simple'), 'Linear Wipe': ('Edge Wipe', 'simple'), 'Edge Wipe': ('Edge Wipe', 'simple'),
        'Clock Wipe': ('Clock Wipe', 'simple'), 'Band Wipe': ('Band Wipe', 'simple'),
        'Radial Wipe': ('Radial Wipe', 'simple'), 'Center Wipe': ('Center Wipe', 'simple'),
        'Barn Door': ('Barn Door', 'simple'),
        'Cross Iris': ('Cross Iris', 'simple'), 'Oval Iris': ('Oval Iris', 'simple'), 'Diamond Iris': ('Diamond Iris', 'simple'),
        'Push': ('Push', 'simple'), 'Slide': ('Slide', 'simple'), 'Split': ('Split', 'simple'),
        # Animation -> fusion
        'Block Motion': ('Tile Wipe', 'fusion'), 'Flip Motion': ('Flip 3D', 'fusion'),
        'Fold Motion': ('Fold', 'fusion'), 'Pop Motion': ('Pop Wobble', 'fusion'),
        'Spin Motion': ('Spin', 'fusion'), 'Spring Motion': ('Elastic Rubber', 'fusion'),
        # Grunge & Distort -> fusion
        'Chaos': ('Disarrange', 'fusion'), 'Earthquake': ('Camera Shake', 'fusion'),
        'Flicker': ('Brightness Flash', 'fusion'), 'Glass': ('Shatter', 'fusion'),
        'Glitch': ('Glitch', 'fusion'), 'VHS Damage': ('Glitch', 'fusion'),
        'Liquid Distortion': ('Ripple Warp', 'fusion'),
        # Lights & Blurs -> fusion
        'Chroma Leak': ('RGB Splitter', 'fusion'),
        'Cross Zoom': ('Crash Zoom', 'fusion'), 'Zoom Blur': ('Crash Zoom', 'fusion'),
        'Directional Blur': ('Stretch Blur', 'fusion'),
        'Flare': ('Tunnel of Light', 'fusion'), 'Ray': ('Tunnel of Light', 'fusion'),
        'Flash': ('Brightness Flash', 'fusion'), 'Glow': ('Glow', 'fusion'),
        'Radial Blur': ('Radial', 'fusion'),
        # Slide -> fusion
        '3D Roll': ('Cube', 'fusion'), 'Roll': ('Cube', 'fusion'), 'Film Roll': ('Film Strip', 'fusion'),
        'Stretch': ('Stretch Blur', 'fusion'), 'Stretch Wipe': ('Stretch Blur', 'fusion'),
        'Whip': ('Pan Left', 'fusion'),
        # Smart Tools / Transformers / Wipe -> fusion
        'Shape Dissolve': ('Shape Transition', 'fusion'), 'Shape Flow': ('Shape Transition', 'fusion'),
        '3D Spin': ('Flip 3D', 'fusion'), '3D Spinback': ('Flip 3D', 'fusion'),
        'Page Peel': ('Page Curl', 'fusion'), 'Slice': ('Slice Push', 'fusion'),
        'Wave': ('Ripple Warp', 'fusion'),
        'Soft Wipe': ('Luma Wipe', 'fusion'), 'Luma Fade': ('Luma Wipe', 'fusion'),
        'Pencil Wipe': ('Paint On', 'fusion'),
        'Box Wipe': ('Box Wipe', 'fusion'), 'Checker Wipe': ('Checker Wipe', 'fusion'),
        'Mosaic': ('Mosaic Dissolve', 'fusion'),
    }
    _AUDIO_TR = {'Constant Power', 'Constant Gain', 'Exponential Fade'}
    transitions = []
    if data.get('transitions'):
        ends = {}      # (kind, track) -> [(inicio, fim)] em quadros de record
        for c in clips:
            if c.get('remap'):
                pts = c['remap']['points']; d = int(round(pts[-1][0] - pts[0][0]))
            else:
                d = int(round((c['src_out'] - c['src_in']) / (c['media_fps'] or rfps) * rfps / (c['speed'] / 100.0)))
            ends.setdefault(('video', c['track']), []).append((c['rec_start'], c['rec_start'] + d))
        for a in audio_clips:
            ends.setdefault(('audio', a['track']), []).append((a['rec_start'], a['rec_start'] + a['rec_dur']))
        for tr in data['transitions']:
            kind = tr.get('kind', 'video'); nm_t = tr.get('name') or ''
            s_f, e_f = int(round(tr['start'] * rfps)), int(round(tr['end'] * rfps))
            if e_f <= s_f: continue
            par = ends.get((kind, tr['track'])) or []
            corte = [f for ini, f in par if s_f - 2 < f < e_f + 2 and any(abs(ini2 - f) <= 1 for ini2, _ in par)]
            lado = None
            if len(corte) == 1:
                cut = corte[0]
            elif any(abs(f - e_f) <= 2 for ini, f in par):
                cut, lado = e_f, 'end'        # clipe termina no fim da janela -> fade-out
            elif any(abs(ini - s_f) <= 2 for ini, f in par):
                cut, lado = s_f, 'start'      # clipe comeca no inicio da janela -> fade-in
            else:
                avisos.append(T('transicao "%s" na trilha %d ignorada (sem clipe adjacente no conjunto copiado)',
                                'transition "%s" on track %d skipped (no adjacent clip in the copied set)') % (nm_t, tr['track'])); continue
            cat = 'simple'
            if kind == 'audio':
                if nm_t not in _AUDIO_TR:
                    avisos.append(T('transicao de audio "%s" nao mapeada: vai como crossfade padrao',
                                    'audio transition "%s" unmapped: goes as default crossfade') % nm_t)
                pretty = 'AUDIO_FADE'
            else:
                alvo = _PRETTY.get(nm_t)
                if not alvo:
                    avisos.append(T('transicao "%s" na trilha %d ignorada (sem equivalente no Resolve)',
                                    'transition "%s" on track %d skipped (no Resolve equivalent)') % (nm_t, tr['track'])); continue
                pretty, cat = alvo
                if nm_t == 'Dip to White':
                    avisos.append(T('transicao "Dip to White": a API nao expoe a cor — vai como dip para preto',
                                    'transition "Dip to White": API does not expose color — goes as dip to black'))
                elif pretty != nm_t:
                    avisos.append(T('transicao "%s" aproximada: vai como "%s"',
                                    'transition "%s" approximated: goes as "%s"') % (nm_t, pretty))
            transitions.append({'kind': kind, 'track': tr['track'], 'start': s_f, 'dur': e_f - s_f,
                                'cut': cut, 'lado': lado, 'pretty': pretty, 'cat': cat, 'name': nm_t})
    markers = [{'nome': m['name'], 'comentario': m.get('comentario', ''), 'tipo': m.get('tipo', 'Comment'),
                'start_f': int(round(m['start'] * rfps)), 'dur_f': int(round((m['end'] - m['start']) * rfps))}
               for m in data.get('markers') or []]
    return {'version': 1, 'name': name or seq['name'], 'bin': _nome_projeto(seq.get('project'), 'Premiere (sem projeto)'),
            'fps': sfps, 'width': sW, 'height': sH,
            **({'destino': data['destino']} if data.get('destino') else {}),
            **({'rampa': data['rampa']} if data.get('rampa') else {}),
            **({'transitions': transitions} if transitions else {}),
            **({'titulos': titulos} if titulos else {}),
            **({'ajustes': ajustes} if ajustes else {}),
            **({'markers': markers} if markers else {}),
            'clips': clips, 'audio_clips': audio_clips}, avisos
