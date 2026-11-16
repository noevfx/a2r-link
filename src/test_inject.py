"""Prova ponta a ponta numa timeline existente: valores nao-padrao -> export -> injeta chaves -> importa -> confere.
Uso: python -I test_inject.py <pasta_saida> <nome_timeline_limpa>"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['RESOLVE_SCRIPT_API'] = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting'
os.environ['RESOLVE_SCRIPT_LIB'] = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
sys.path.append(os.environ['RESOLVE_SCRIPT_API'] + r'\Modules')
import DaVinciResolveScript as dvr
import drtlib as L

out, nome = sys.argv[1], sys.argv[2]
r = dvr.scriptapp('Resolve'); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
tl = next(p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1) if p.GetTimelineByIndex(i).GetName() == nome)
p.SetCurrentTimeline(tl); it = tl.GetItemListInTrack('video', 1)[0]
# 1) garante que os parametros existam (valor nao-padrao)
for k, v in (('Pan', 1), ('Tilt', 1), ('ZoomX', 1.01), ('RotationAngle', 1), ('Opacity', 99)):
    it.SetProperty(k, v)
src = os.path.join(out, 'inj_src.drt'); tl.Export(src, r.EXPORT_DRT)
# 2) chaves: Pan 0 -> 960 px (quadro 0 -> 60), Zoom 1 -> 2, Rotacao 0 -> 90, Opacidade 100 -> 20
W, H = 3840, 2160
km = {(4, 40): [(0, 0.0), (60, 960 / W)], (4, 42): [(0, 1.0), (60, 2.0)], (4, 43): [(0, 1.0), (60, 2.0)],
      (4, 47): [(0, 0.0), (60, 90.0)], (2, 1): [(0, 100.0), (60, 20.0)]}
dst = os.path.join(out, 'inj_dst.drt'); L.patch_drt(src, dst, [km])
# 3) importa e reexporta para conferir
n0 = p.GetTimelineCount()
t2 = mp.ImportTimelineFromFile(dst)
print('importou:', bool(t2), t2.GetName() if t2 else None, '| timelines', n0, '->', p.GetTimelineCount())
back = os.path.join(out, 'inj_back.drt'); t2.Export(back, r.EXPORT_DRT)
_, xml = L.seq_xml(back)
for pk, d in L.params(L.efx_decode([h for h in L.clip_efx(xml) if h][0])[2]).items():
    print(pk, d['valor'], d['chaves'])
p.SetCurrentTimeline(t2)
print('timeline atual:', p.GetCurrentTimeline().GetName(), 'playhead', p.GetCurrentTimeline().GetCurrentTimecode())
