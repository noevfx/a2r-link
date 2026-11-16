"""Gera as imagens do README (docs/img/) a partir dos dados REAIS:
- painel.png: copiado do print do painel (passar o caminho por argv[1] ou ja existir em docs/img/)
- rampa-premiere.svg / rampa-ae.svg: curva da origem + os dois modos que chegam no Resolve,
  calculados pelo proprio gen._timemap_mapa (mesmo codigo que gera a rampa de verdade)
- fluxo.svg: o caminho do clique (Premiere/After -> A2R Link -> Resolve)
Uso: python scripts/mk_imgs_readme.py [print_do_painel.png]
"""
import os, sys, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import drtlib as L
import gen, prproj

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(RAIZ, 'docs', 'img')
os.makedirs(OUT, exist_ok=True)

# ---------- captura dos pontos que o encoder recebe (o que de fato vai pro Resolve) ----------
CAP = []
_enc_e = L.timemap_encode_eased; _enc = L.timemap_encode
def _cap_e(pts, *a, **k): CAP.append(list(pts)); return _enc_e(pts, *a, **k)
def _cap(pts, *a, **k): CAP.append(list(pts)); return _enc(pts, *a, **k)
L.timemap_encode_eased, L.timemap_encode = _cap_e, _cap


def curvas(rm, fe, tot, mfps):
    """retorna (nos_resolve, eval_editavel, pontos_precisa) — tudo em segundos de timeline/midia"""
    pts = rm['points']; rec0 = pts[0][1]
    CAP.clear(); gen._timemap_mapa(rm, rec0, fe, tot, mfps, 'readme')
    nos = CAP[0]                                   # [(rec, src, h|None)]
    cur = [(0.0, 0.0, None)] + nos
    evalf = lambda t: L.timemap_eval(cur, t)
    rm2 = {k: v for k, v in rm.items() if k != 'nodes'}
    CAP.clear(); gen._timemap_mapa(rm2, rec0, fe, tot, mfps, 'readme')
    return nos, evalf, CAP[0]


# ---------- SVG ----------
BG, GRID, CURVA, ORIG, NO, TXT, MUT = '#0d1117', '#21262d', '#58a6ff', '#8b949e', '#ffa657', '#e6edf3', '#8b949e'

def subplot(px, dados, titulo, marcadores=None, densos=None, evalf=None, w=300, h=190, pad=30):
    """dados = curva de fundo (origem, tracejada) [(x,y)] em segundos; marcadores = [(x,y)] nos"""
    xs = [d[0] for d in dados]; ys = [d[1] for d in dados]
    for m in (marcadores or []): xs.append(m[0]); ys.append(m[1])
    for m in (densos or []): xs.append(m[0]); ys.append(m[1])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    dy = max(0.5, y1 - y0); y0, y1 = y0 - 0.06 * dy, y1 + 0.08 * dy
    sx = lambda x: pad + (x - x0) / (x1 - x0) * (w - 2 * pad)
    sy = lambda y: h - pad - (y - y0) / (y1 - y0) * (h - 2 * pad)
    e = ['<g transform="translate(%d,0)">' % px,
         '<rect x="0" y="0" width="%d" height="%d" fill="%s" rx="8"/>' % (w, h, BG),
         '<text x="%d" y="20" fill="%s" font-size="13" text-anchor="middle" font-family="Segoe UI,Arial">%s</text>' % (w / 2, TXT, titulo)]
    for i in range(4):   # linhas de grade
        gy = pad + i * (h - 2 * pad) / 3
        e.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>' % (pad, gy, w - pad, gy, GRID))
    pl = ' '.join('%.1f,%.1f' % (sx(x), sy(y)) for x, y in dados)
    e.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.4" stroke-dasharray="5 4"/>' % (pl, ORIG))
    if evalf:            # curva real do Resolve (pontos colados na verdade)
        n = 200; pl2 = ' '.join('%.1f,%.1f' % (sx(x0 + (x1 - x0) * i / n), sy(evalf(x0 + (x1 - x0) * i / n))) for i in range(n + 1))
        e.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.2"/>' % (pl2, CURVA))
    if densos:
        for x, y in densos:
            e.append('<circle cx="%.1f" cy="%.1f" r="2.1" fill="%s"/>' % (sx(x), sy(y), CURVA))
    for x, y in (marcadores or []):
        e.append('<circle cx="%.1f" cy="%.1f" r="4.5" fill="%s" stroke="%s" stroke-width="1.5"/>' % (sx(x), sy(y), NO, BG))
    e.append('</g>')
    return ''.join(e)


def svg_rampa(titulos, origem, keys_origem, nos_res, evalf, densos, nome):
    w, h = 3 * 310, 190
    corpo = subplot(5, origem, titulos[0], marcadores=keys_origem)
    corpo += subplot(315, origem, titulos[1], marcadores=[(n[0], n[1]) for n in nos_res], evalf=evalf)
    corpo += subplot(625, origem, titulos[2], densos=densos)
    s = '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s</svg>' % (w, h, w, h, corpo)
    open(os.path.join(OUT, nome), 'w', encoding='utf-8').write(s)
    print(nome, '| nos:', len(nos_res), '| densos:', len(densos))


def svg_fluxo():
    w, h = 940, 110
    box = ('<rect x="%d" y="25" width="%d" height="60" rx="10" fill="#161b22" stroke="%s"/>'
           '<text x="%d" y="61" fill="#e6edf3" font-size="16" text-anchor="middle" font-family="Segoe UI,Arial">%s</text>')
    seta = ('<line x1="%d" y1="55" x2="%d" y2="55" stroke="#58a6ff" stroke-width="2.5"/>'
            '<polygon points="%d,55 %d,49 %d,61" fill="#58a6ff"/>'
            '<text x="%d" y="42" fill="#8b949e" font-size="12" text-anchor="middle" font-family="Segoe UI,Arial">%s</text>')
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d"><rect width="%d" height="%d" fill="%s" rx="8"/>' % (w, h, w, h, w, h, BG)]
    s.append(box % (20, 250, '#30363d', 145, 'Premiere / After'))
    s.append(seta % (275, 350, 350, 341, 341, 312, 'um clique'))
    s.append(box % (355, 210, '#2f6fed', 460, 'A2R Link'))
    s.append(seta % (570, 645, 645, 636, 636, 607, 'na hora'))
    s.append(box % (650, 270, '#30363d', 785, 'DaVinci Resolve'))
    s.append('</svg>')
    open(os.path.join(OUT, 'fluxo.svg'), 'w', encoding='utf-8').write(''.join(s))
    print('fluxo.svg')


# ---------- AE (clipboard real) ----------
c = json.load(open(os.path.join(os.environ['APPDATA'], 'NoeVFX', 'clipboard.json'), encoding='utf-8'))
lay = c['data']['layers'][0]
rfps = c['data']['comp']['fps']; mfps = lay['mediaFps']
r0 = lay['remap'][0][0]
dens = [[(t - r0) * rfps, v] for t, v in lay['remap']]
rm = {'points': dens, 'dense': dens,
      'nodes': [[(k['t'] - r0) * rfps, k['v'], k['iI'], k['iO']] for k in lay['remapKeys']]}
nos, evalf, prec = curvas(rm, rfps, lay['remap'][-1][1] * mfps, mfps)
rec0 = rm['points'][0][1]
# dominio do eval = segundos de record (comeca em rec0); origem nos mesmos segundos pra alinhar os 3 paineis
origem_abs = [(d / rfps + rec0, s) for d, s in dens]
keys = [((k['t'] - r0) + rec0, k['v']) for k in lay['remapKeys'] if (k['t'] - r0) >= -1e-6]
nos_svg = [(n[0], n[1]) for n in nos]
dens_svg = [(p[0], p[1]) for p in prec if p[0] >= rec0]
svg_rampa(['no After', 'no DaVinci — Editável', 'no DaVinci — Precisa'],
          origem_abs, keys, nos_svg, evalf, dens_svg, 'rampa-ae.svg')

# ---------- Premiere (prproj real) ----------
f = sorted(glob.glob(r'C:/Users/enn_g/Desktop/Adobe Premiere Pro Auto-Save/Teste PR*.prproj'))[-1]
p = prproj.Prproj.aberto(f)
alvo = None
for tipo, tidx, tuid in p.sequencia():
    if tipo != 'video': continue
    for t0, t1, oid in p.takes(tipo, tuid):
        if oid and p.keyframes(oid): alvo = (tidx + 1, t0, t1, oid); break
    if alvo: break
tr, t0, t1, oid = alvo
knots = p.keyframes(oid)
rmr = prproj.remaps(f, None, 29.97, [(tr, t0, t1)])
saida = list(rmr.values())[0]
samples = saida['samples']
start = t0; rfps = 29.97
dens = [[(t - start) * rfps, v] for t, v in samples]
ab = saida['knots_absoluto']
nds = [[(t - start) * rfps if ab else t * rfps, v, min(ii, 1.0) if ii > 1e-4 else (1.0 / 3.0 if tipo in (7, 8) else 0.0), min(io, 1.0) if io > 1e-4 else (1.0 / 3.0 if tipo in (7, 8) else 0.0)] for t, v, tipo, ii, io in saida['knots']]
rm = {'points': dens, 'dense': dens, 'nodes': nds}
rec0 = dens[0][1]
nos, evalf, prec = curvas(rm, rfps, max(v for _, v in samples) * 29.97, 29.97)
origem_abs = [(d / rfps + rec0, s) for d, s in dens]
keys = [(k[0] / rfps + rec0, k[1]) for k in nds]
nos_svg = [(n[0], n[1]) for n in nos]
dens_svg = [(p_[0], p_[1]) for p_ in prec if p_[0] >= rec0]
svg_rampa(['no Premiere', 'no DaVinci — Editável', 'no DaVinci — Precisa'],
          origem_abs, keys, nos_svg, evalf, dens_svg, 'rampa-premiere.svg')

svg_fluxo()

if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
    import shutil
    shutil.copy(sys.argv[1], os.path.join(OUT, 'painel.png'))
    print('painel.png')
