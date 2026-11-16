"""Valida Premiere -> Resolve comparando quadros renderizados nos mesmos instantes.
Uso: python -I validate_e2e.py <pasta_saida> [tempo_s ...]   (Resolve: timeline atual; Premiere: sequencia ativa)"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge, gen, cv2, numpy as np

out = sys.argv[1]; rest = sys.argv[2:]
ORIGEM = 'pr'
if rest and rest[0] in ('pr', 'ae'):
    ORIGEM = rest[0]; rest = rest[1:]
tempos = [float(x) for x in rest] or [0.0, 1.0, 2.0]
r, p = gen._connect(); tl = p.GetCurrentTimeline(); t0 = tl.GetStartFrame(); rfps = float(tl.GetSetting('timelineFrameRate'))

def tcs(f):
    s = f - 108000; sec = s // 30
    return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)

linhas = []
for t in tempos:
    base = os.path.join(out, 'pr_%g' % t); png_pr = base + '.png'
    if os.path.exists(png_pr): os.remove(png_pr)
    if ORIGEM == 'pr':
        bridge.run_premiere("""var s=app.project.activeSequence; s.setPlayerPosition(String(Math.round(%f*254016000000)));
            var q=qe.project.getActiveSequence(); q.exportFramePNG(q.CTI.timecode, %s); return 1;""" % (t, '"' + base.replace('\\', '\\\\') + '"'))
    else:
        import ae_io
        ae_io.run_ae('var c=app.project.activeItem; c.saveFrameToPng(%f, new File("%s")); return 1;' % (t, png_pr.replace('\\', '/')), timeout=60)
    for _ in range(40):
        if os.path.exists(png_pr): break
        time.sleep(0.25)
    png_rs = os.path.join(out, 'rs_%g.png' % t)
    if os.path.exists(png_rs): os.remove(png_rs)
    tl.SetCurrentTimecode(tcs(t0 + int(round(t * rfps)))); p.ExportCurrentFrameAsStill(png_rs); time.sleep(0.4)
    a = cv2.imread(png_pr, cv2.IMREAD_UNCHANGED); b = cv2.imread(png_rs)
    if a is not None and a.ndim == 3 and a.shape[2] == 4:
        # Premiere: alfa "reto" (RGB cheio) -> multiplica pelo alfa; After: alfa premultiplicado (RGB ja multiplicado) -> so descarta o alfa
        al = a[:, :, 3:4].astype(float) / 255.0
        a = (a[:, :, :3].astype(float) * (al if ORIGEM == 'pr' else 1.0)).astype(np.uint8)
    if a is None or b is None:
        print('t=%g: falha ao ler (premiere=%s resolve=%s)' % (t, a is not None, b is not None)); continue
    b2 = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)
    diff = np.abs(a.astype(int) - b2.astype(int)).mean()
    print('t=%4.1fs  diferenca media por pixel = %.2f / 255  (%s)' % (t, diff, 'OK' if diff < 12 else 'DIVERGE'))
    side = np.hstack([cv2.resize(a, (640, 360)), cv2.resize(b2, (640, 360))])
    cv2.imwrite(os.path.join(out, 'cmp_%g.jpg' % t), side)
