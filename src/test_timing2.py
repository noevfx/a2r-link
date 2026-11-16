"""Mede, com imagem renderizada, a que o tempo das chaves se refere.
Chaves de Zoom (0 -> 1.0) e (120 -> 2.8). Zoom medido na borda das barras de cor (x = 1920 + 640*Zoom).
Uso: python -I test_timing2.py <pasta_saida>"""
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
tl = mp.CreateEmptyTimeline('t2_%d' % int(time.time())); p.SetCurrentTimeline(tl); t0 = tl.GetStartFrame()
# (rotulo, srcIn, srcOut_append, offset_record, velocidade)
specs = [('A src0  100%', 0, 59, 0, None), ('B src30 100%', 30, 89, 400, None),
         ('C src0   50%', 0, 119, 800, 50), ('D src30  50%', 30, 149, 1200, 50)]
for nm, s, e, off, spd in specs:
    mp.AppendToTimeline([{'mediaPoolItem': clip, 'startFrame': s, 'endFrame': e, 'mediaType': 1, 'trackIndex': 1, 'recordFrame': t0 + off}])
its = tl.GetItemListInTrack('video', 1)
for (nm, s, e, off, spd), it in zip(specs, its):
    if spd: it.SetSpeed({'Percentage': spd})
    it.SetProperty('ZoomX', 1.01); it.SetProperty('ZoomY', 1.01)
for (nm, *_), it in zip(specs, its):
    print(nm, 'start', it.GetStart(), 'dur', it.GetDuration(), 'srcIn', it.GetSourceStartFrame(), 'srcOut', it.GetSourceEndFrame())
src = os.path.join(out, 't2_src.drt'); tl.Export(src, r.EXPORT_DRT)
km = {(4, 42): [(0, 1.0), (120, 2.8)], (4, 43): [(0, 1.0), (120, 2.8)]}
n = len(re.findall(r'<EffectFiltersBA>', L.seq_xml(src)[1]))
dst = os.path.join(out, 't2i_%d.drt' % int(time.time())); L.patch_drt(src, dst, [km] * n)
t2 = mp.ImportTimelineFromFile(dst); p.SetCurrentTimeline(t2); print('timeline:', t2.GetName())

def tcs(f):
    s = f - 108000; sec = s // 30
    return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)

def zoom_em(frame):
    t2.SetCurrentTimecode(tcs(frame)); png = os.path.join(out, 'q.png')
    if os.path.exists(png): os.remove(png)
    p.ExportCurrentFrameAsStill(png); time.sleep(0.3)
    im = cv2.imread(png)
    if im is None: return None
    h, w = im.shape[:2]; row = im[int(h * 2100 / 2160)].astype(int)   # perto da base: so barras
    cx = w // 2
    for x in range(cx + 20, w - 20):
        if (np.abs(row[x - 15] - row[x - 3]).sum() < 40 and np.abs(row[x + 3] - row[x + 15]).sum() < 40
                and np.abs(row[x - 3] - row[x + 3]).sum() > 150):
            # refina para o ponto exato da mudanca
            for k in range(x - 3, x + 3):
                if np.abs(row[k] - row[k + 1]).sum() > 60:
                    return round((k + 0.5 - cx) / (w / 6), 3)   # borda = cx + (w/6)*Zoom
    return None

for (nm, *_), it in zip(specs, t2.GetItemListInTrack('video', 1)):
    st = it.GetStart(); vals = []
    for d in (0, 20, 40, 60, 80):
        z = zoom_em(st + d)
        t_ef = None if z is None else round((z - 1.0) / 1.8 * 120, 1)
        vals.append((d, z, t_ef))
    print(nm, 'start', st, 'srcIn', it.GetSourceStartFrame(), '|', vals)
