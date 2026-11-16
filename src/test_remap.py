"""Valida o time remap: para cada quadro de saida mede QUAL quadro da midia apareceu (casando a imagem com os quadros do video)
e compara com o esperado pela curva. Uso: python -I test_remap.py <video.mp4> <pasta_saida>"""
import os, sys, time, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen, cv2, numpy as np

MEDIA, OUT = sys.argv[1], sys.argv[2]
# biblioteca de quadros da midia (cinza 160x90)
cap = cv2.VideoCapture(MEDIA); lib = []
while True:
    ok, fr = cap.read()
    if not ok: break
    lib.append(cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32))
lib = np.stack(lib); print('quadros da midia:', len(lib))

def quadro_da_midia(png):
    im = cv2.imread(png)
    if im is None: return None
    g = cv2.resize(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), (160, 90), interpolation=cv2.INTER_AREA).astype(np.float32)
    d = ((lib - g) ** 2).mean(axis=(1, 2)); return int(d.argmin())

def esperado(pts, d, mfps):
    for (d0, s0), (d1, s1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            s = s0 + (s1 - s0) * (d - d0) / (d1 - d0); return int(math.floor(s * mfps + 0.002))
    return int(math.floor(pts[-1][1] * mfps))

if __name__ == '__main__':
    pts = [(0, 0.0), (30, 1.0), (75, 3.0), (120, 3.8)]    # d = quadros da timeline, s = segundos de midia
    spec = {'name': 'Teste remap %d' % int(time.time()), 'clips': [
        {'media': MEDIA, 'media_fps': 25.0, 'src_in': 0, 'src_out': 100, 'rec_start': 0, 'track': 1, 'speed': 100.0,
         'static': {}, 'keys': {}, 'remap': {'points': pts}}]}
    tl, av = gen.build(spec)
    r, p = gen._connect(); t0 = tl.GetStartFrame()
    it = tl.GetItemListInTrack('video', 1)[0]; print('duracao do clipe:', it.GetDuration(), '(esperado 120)')
    def tcs(f):
        s = f - 108000; sec = s // 30
        return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)
    erros = []
    for d in range(0, 120, 5):
        tl.SetCurrentTimecode(tcs(t0 + d)); png = os.path.join(OUT, 'rm.png')
        if os.path.exists(png): os.remove(png)
        p.ExportCurrentFrameAsStill(png); time.sleep(0.25)
        m = quadro_da_midia(png); e = esperado(pts, d, 25.0)
        erros.append(abs(m - e) if m is not None else 99)
        print('d=%3d  medido=%3s  esperado=%3d  %s' % (d, m, e, 'OK' if m is not None and abs(m - e) <= 1 else 'DIFERE'))
    print('ERRO MAXIMO (quadros da midia):', max(erros))
