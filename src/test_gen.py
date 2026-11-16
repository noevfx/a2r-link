"""Valida gen.build por render: compara Pan medido (borda das barras) com o Pan esperado em varios quadros de cada clipe."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen, cv2, numpy as np

MEDIA = sys.argv[1]; OUT = sys.argv[2]
spec = {'name': 'Teste gen %d' % int(time.time()), 'clips': [
    {'media': MEDIA, 'media_fps': 25.0, 'src_in': 0, 'src_out': 90, 'rec_start': 0, 'track': 1, 'speed': 100.0,
     'static': {}, 'keys': {'Pan': [[0, 0], [60, 600]]}},
    {'media': MEDIA, 'media_fps': 25.0, 'src_in': 30, 'src_out': 120, 'rec_start': 300, 'track': 1, 'speed': 100.0,
     'static': {}, 'keys': {'Pan': [[0, 0], [60, 600]]}},
    {'media': MEDIA, 'media_fps': 25.0, 'src_in': 0, 'src_out': 45, 'rec_start': 600, 'track': 2, 'speed': 50.0,
     'static': {}, 'keys': {'Pan': [[0, 0], [60, 600]]}},
]}
tl, avisos = gen.build(spec)
r, p = gen._connect()
t0 = tl.GetStartFrame()

def tcs(f):
    s = f - 108000; sec = s // 30
    return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)

def pan_mod(frame):
    tl.SetCurrentTimecode(tcs(frame)); png = os.path.join(OUT, 'qg.png')
    if os.path.exists(png): os.remove(png)
    p.ExportCurrentFrameAsStill(png); time.sleep(0.3)
    im = cv2.imread(png); h, w = im.shape[:2]; row = im[int(h * 2100 / 2160)].astype(int)
    for x in range(400, w - 20):
        if (np.abs(row[x - 15] - row[x - 3]).sum() < 40 and np.abs(row[x + 3] - row[x + 15]).sum() < 40
                and np.abs(row[x - 3] - row[x + 3]).sum() > 150):
            for k in range(x - 3, x + 3):
                if np.abs(row[k] - row[k + 1]).sum() > 60:
                    return ((k + 0.5) - 1920) % 640
    return None

ok_total = True
for n, c in enumerate(spec['clips']):
    for d in (0, 15, 30, 45):
        m = pan_mod(t0 + c['rec_start'] + d)
        esp = (10 * d) % 640
        erro = None if m is None else min(abs(m - esp), 640 - abs(m - esp))
        bom = erro is not None and erro <= 8
        ok_total &= bom
        print('clipe %d d=%2d  esperado Pan mod640=%5.1f  medido=%s  erro=%s  %s' % (n, d, esp, None if m is None else round(m, 1), None if erro is None else round(erro, 1), 'OK' if bom else 'FALHOU'))
print('RESULTADO:', 'TUDO OK' if ok_total else 'HA FALHAS', '| avisos:', avisos)
