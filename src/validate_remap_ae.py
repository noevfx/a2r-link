"""Compara, instante a instante, o quadro da MIDIA mostrado pelo After (verdade) e pelo DaVinci (timeline atual).
Uso: python -I validate_remap_ae.py <video.mp4> <pasta_saida> <t0_s> <t1_s> <passo_s>"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen, ae_io, cv2, numpy as np

MEDIA, OUT = sys.argv[1], sys.argv[2]; T0, T1, PASSO = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
cap = cv2.VideoCapture(MEDIA); lib = []
while True:
    ok, fr = cap.read()
    if not ok: break
    lib.append(cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32))
lib = np.stack(lib)

def quadro(png, premult=False):
    im = cv2.imread(png, cv2.IMREAD_UNCHANGED)
    if im is None: return None
    if im.ndim == 3 and im.shape[2] == 4: im = im[:, :, :3]
    g = cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32)
    return int(((lib - g) ** 2).mean(axis=(1, 2)).argmin())

r, p = gen._connect(); tl = p.GetCurrentTimeline(); t0 = tl.GetStartFrame(); rfps = float(tl.GetSetting('timelineFrameRate'))
def tcs(f):
    s = f - 108000; sec = s // 30
    return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)

erros = []; t = T0
while t <= T1 + 1e-9:
    pa = os.path.join(OUT, 'ra.png'); pr = os.path.join(OUT, 'rr.png')
    for f in (pa, pr):
        if os.path.exists(f): os.remove(f)
    ae_io.run_ae('var c=app.project.activeItem; c.saveFrameToPng(%f, new File("%s")); return 1;' % (t, pa.replace('\\', '/')), timeout=60)
    tl.SetCurrentTimecode(tcs(t0 + int(round(t * rfps)))); p.ExportCurrentFrameAsStill(pr); time.sleep(0.3)
    a, b = quadro(pa), quadro(pr)
    e = None if a is None or b is None else abs(a - b)
    erros.append(99 if e is None else e)
    print('t=%5.2fs  After=%3s  DaVinci=%3s  dif=%s %s' % (t, a, b, e, 'OK' if e is not None and e <= 1 else 'DIFERE'))
    t += PASSO
print('ERRO MAXIMO (quadros da midia): %s' % max(erros))
