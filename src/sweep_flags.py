"""Varre os 4 bytes de flags das chaves e mede o resultado no render (rampa Pan 0 -> 600 px entre os quadros 0 e 60).
Pan medido nos quadros 10, 30 e 50 (linear daria 100, 300, 500). Uso: python -I sweep_flags.py <pasta> <b0,b1,b2,b3> [<b0,b1,b2,b3> ...]"""
import os, sys, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['RESOLVE_SCRIPT_API'] = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting'
os.environ['RESOLVE_SCRIPT_LIB'] = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
sys.path.append(os.environ['RESOLVE_SCRIPT_API'] + r'\Modules')
import DaVinciResolveScript as dvr
import cv2, numpy as np
import drtlib as L

out = sys.argv[1]
cands = [bytes(int(x, 0) for x in a.split(',')) for a in sys.argv[2:]]
r = dvr.scriptapp('Resolve'); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
clip = [c for c in mp.GetRootFolder().GetClipList() if c.GetName() == 'teste_noebridge.mp4'][0]
# timeline base (uma so): 1 clipe, Pan nao-padrao para o parametro existir
tl = mp.CreateEmptyTimeline('sw_%d' % int(time.time())); p.SetCurrentTimeline(tl); t0 = tl.GetStartFrame()
mp.AppendToTimeline([{'mediaPoolItem': clip, 'startFrame': 0, 'endFrame': 119, 'mediaType': 1, 'trackIndex': 1, 'recordFrame': t0}])
tl.GetItemListInTrack('video', 1)[0].SetProperty('Pan', 1)
src = os.path.join(out, 'sw_src.drt'); tl.Export(src, r.EXPORT_DRT)

def tcs(f):
    s = f - 108000; sec = s // 30
    return '01:%02d:%02d:%02d' % ((sec // 60) % 60, sec % 60, s % 30)

def borda(t2, frame):
    t2.SetCurrentTimecode(tcs(frame)); png = os.path.join(out, 'qs.png')
    if os.path.exists(png): os.remove(png)
    p.ExportCurrentFrameAsStill(png); time.sleep(0.25)
    im = cv2.imread(png)
    if im is None: return None
    h, w = im.shape[:2]; row = im[int(h * 2100 / 2160)].astype(int)
    for x in range(400, w - 20):
        if (np.abs(row[x - 15] - row[x - 3]).sum() < 40 and np.abs(row[x + 3] - row[x + 15]).sum() < 40
                and np.abs(row[x - 3] - row[x + 3]).sum() > 150):
            for k in range(x - 3, x + 3):
                if np.abs(row[k] - row[k + 1]).sum() > 60:
                    return ((k + 0.5) - 1920) % 640
    return None

for fl in cands:
    keys = [(0, fl, 0.0), (60, fl, 600 / 3840)]
    dst = os.path.join(out, 'sw_%s_%d.drt' % (fl.hex(), int(time.time() * 1000)))
    _, xml = L.seq_xml(src)
    import zipfile
    zin = zipfile.ZipFile(src); zout = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename.startswith('SeqContainer/') and info.filename.endswith('.xml'):
            x = data.decode('utf-8')
            def sub(m):
                if not m.group(1): return m.group(0)
                return '<EffectFiltersBA>%s</EffectFiltersBA>' % L.efx_inject_raw(m.group(1), {(4, 40): L.keys_encode(keys)})
            data = re.sub(r'<EffectFiltersBA>([0-9a-f]*)</EffectFiltersBA>', sub, x).encode('utf-8')
        zout.writestr(info, data)
    zout.close()
    t2 = mp.ImportTimelineFromFile(dst)
    if not t2:
        print('flags', fl.hex(), 'IMPORT FALHOU'); continue
    p.SetCurrentTimeline(t2)
    ms = [borda(t2, t0 + f) for f in (10, 30, 50)]
    # Pan mod 640: valores esperados lineares 100,300,500
    print('flags', fl.hex(), '->', [None if m is None else round(m, 1) for m in ms], '(linear = 100, 300, 500)', flush=True)
