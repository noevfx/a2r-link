"""Descobre a que o tempo das chaves se refere: clipe deslocado, aparado na cabeça, com velocidade, em outra trilha.
Uso: python -I test_timing.py <pasta_saida>"""
import os, sys, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['RESOLVE_SCRIPT_API'] = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting'
os.environ['RESOLVE_SCRIPT_LIB'] = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
sys.path.append(os.environ['RESOLVE_SCRIPT_API'] + r'\Modules')
import DaVinciResolveScript as dvr
import drtlib as L

out = sys.argv[1]
r = dvr.scriptapp('Resolve'); p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
clip = [c for c in mp.GetRootFolder().GetClipList() if c.GetName() == 'teste_noebridge.mp4'][0]
nome = 'tm_%d' % int(time.time())
tl = mp.CreateEmptyTimeline(nome); assert tl, 'timeline nao criada'
p.SetCurrentTimeline(tl)
t0 = tl.GetStartFrame()
specs = [  # (startFrame, endFrame, recordOffset, trilha, velocidade)
    ('A normal       ', 0, 89, 0, 1, None),
    ('B deslocado+aparado', 30, 119, 300, 1, None),
    ('C velocidade 50', 0, 44, 600, 1, 50),
    ('D trilha 2     ', 0, 89, 0, 2, None),
]
for nm, s, e, off, trk, spd in specs:
    res = mp.AppendToTimeline([{'mediaPoolItem': clip, 'startFrame': s, 'endFrame': e, 'mediaType': 1,
                                'trackIndex': trk, 'recordFrame': t0 + off}])
    print(nm, 'append ->', bool(res))
items = []
for trk in (1, 2):
    for it in tl.GetItemListInTrack('video', trk) or []:
        items.append((trk, it))
for trk, it in items:
    print('item trilha', trk, 'start', it.GetStart(), 'dur', it.GetDuration(), 'srcIn', it.GetSourceStartFrame(), 'srcOut', it.GetSourceEndFrame())
    it.SetProperty('ZoomX', 1.01); it.SetProperty('ZoomY', 1.01)
# velocidade no clipe C (3o da trilha 1)
c = tl.GetItemListInTrack('video', 1)[2]
print('SetSpeed 50 ->', c.SetSpeed({'Percentage': 50}), 'dur', c.GetDuration(), 'srcIn', c.GetSourceStartFrame(), 'srcOut', c.GetSourceEndFrame())
src = os.path.join(out, nome + '_src.drt'); print('export', tl.Export(src, r.EXPORT_DRT))
_, xml = L.seq_xml(src)
print('ordem no XML:', re.findall(r'<Name>([^<]*)</Name>\s*<Start>(\d+)</Start>\s*<Duration>(\d+)</Duration>', xml))
# Zoom 1 -> 3 entre os quadros 0 e 30 de cada clipe
km = {(4, 42): [(0, 1.0), (30, 3.0)], (4, 43): [(0, 1.0), (30, 3.0)]}
n_clips = len(re.findall(r'<EffectFiltersBA>', xml))
dst = os.path.join(out, 'tmi_%d.drt' % int(time.time())); L.patch_drt(src, dst, [km] * n_clips)
t2 = mp.ImportTimelineFromFile(dst); print('importou:', bool(t2), t2.GetName() if t2 else None)
p.SetCurrentTimeline(t2)
print('NOME_FINAL', t2.GetName(), 'INICIO', t2.GetStartFrame())
