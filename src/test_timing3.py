"""Mede o tempo das chaves com Position X (rampa 0 -> 1000 px em 400 quadros = 2.5 px/quadro).
Posicao medida pela borda das barras de cor: boundary = 1920 + Pan + 640*k.
Uso: python -I test_timing3.py <pasta_saida>"""
import os, sys, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['RESOLVE_SCRIPT_API'] = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting'
os.environ['RESOLVE_SCRIPT_LIB'] = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
sys.path.append(os.environ['RESOLVE_SCRIPT_API'] + r'\Modules')
import DaVinciResolveScript as dvr
import cv2, numpy as np
import drtlib as L

out = sys.argv[1]
r = dvr.scriptapp('Resolve'); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
clip = [c for c in mp.GetRootFolder().GetClipList() if c.GetName() == 'teste_noebridge.mp4'][0]
tl = mp.CreateEmptyTimeline('t3_%d' % int(time.time())); p.SetCurrentTimeline(tl); t0 = tl.GetStartFrame()
specs = [('A src0  100%', 0, 119, 0, None), ('B src30 100%', 30, 149, 500, None),
         ('C src0   50%', 0, 119, 1000, 50), ('D src30  50%', 30, 149, 1500, 50), ('E src0  200%', 0, 59, 2000, 200)]
for nm, s, e, off, spd in specs:
    mp.AppendToTimeline([{'mediaPoolItem': clip, 'startFrame': s, 'endFrame': e, 'mediaType': 1, 'trackIndex': 1, 'recordFrame': t0 + off}])
its = tl.GetItemListInTrack('video', 1)
for (nm, s, e, off, spd), it in zip(specs, its):
    if spd: it.SetSpeed({'Percentage': spd})
    it.SetProperty('Pan', 1)
for (nm, *_), it in zip(specs, its):
    print(nm, 'start', it.GetStart(), 'dur', it.GetDuration(), 'srcIn', it.GetSourceStartFrame(), 'srcOut', it.GetSourceEndFrame())
src = os.path.join(out, 't3_src.drt'); tl.Export(src, r.EXPORT_DRT)
km = {(4, 40): [(0, 0.0), (400, 1000 / 3840)]}
n = len(re.findall(r'<EffectFiltersBA>', L.seq_xml(src)[1]))
dst = os.path.join(out, 't3i_%d.drt' % int(time.time())); L.patch_drt(src, dst, [km] * n)
t2 = mp.ImportTimelineFromFile(dst); p.SetCurrentTimeline(t2); print('timeline:', t2.GetName())

def tcs(f):
    s = f - 108000; sec = s // 30
    return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)

def pan_mod(frame):
    """retorna (Pan mod 640) medido pela borda das barras (zoom 1); None se nao achou."""
    t2.SetCurrentTimecode(tcs(frame)); png = os.path.join(out, 'q3.png')
    if os.path.exists(png): os.remove(png)
    p.ExportCurrentFrameAsStill(png); time.sleep(0.3)
    im = cv2.imread(png)
    if im is None: return None
    h, w = im.shape[:2]; row = im[int(h * 2100 / 2160)].astype(int)
    for x in range(400, w - 20):
        if (np.abs(row[x - 15] - row[x - 3]).sum() < 40 and np.abs(row[x + 3] - row[x + 15]).sum() < 40
                and np.abs(row[x - 3] - row[x + 3]).sum() > 150):
            for k in range(x - 3, x + 3):
                if np.abs(row[k] - row[k + 1]).sum() > 60:
                    return ((k + 0.5) - 1920) % 640   # primeira borda >= 400 px
    return None

for (nm, *_), it in zip(specs, t2.GetItemListInTrack('video', 1)):
    st = it.GetStart(); vals = []
    for d in (0, 10, 20, 30, 40, 50):
        m = pan_mod(st + d)
        vals.append((d, None if m is None else round(m, 1)))
    print(nm, 'start', st, 'srcIn', it.GetSourceStartFrame(), 'dur', it.GetDuration(), '| (d, Pan mod 640):', vals)
