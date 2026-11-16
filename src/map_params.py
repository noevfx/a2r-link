"""Mapeia IDs e unidades dos parametros do Inspector: seta cada propriedade pela API,
exporta o DRT, decodifica e mostra o que mudou. Uso: python -I map_params.py <pasta_saida>"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['RESOLVE_SCRIPT_API'] = r'C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting'
os.environ['RESOLVE_SCRIPT_LIB'] = r'C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll'
sys.path.append(os.environ['RESOLVE_SCRIPT_API'] + r'\Modules')
import DaVinciResolveScript as dvr
import drtlib as L

r = dvr.scriptapp('Resolve')
p = r.GetProjectManager().GetCurrentProject(); mp = p.GetMediaPool()
out = sys.argv[1]
clip = [c for c in mp.GetRootFolder().GetClipList() if c.GetName().startswith('teste_noebridge')][0]
tl = next(p.GetTimelineByIndex(i) for i in range(1, p.GetTimelineCount() + 1)
          if p.GetTimelineByIndex(i).GetName() == 'T_limpa')
p.SetCurrentTimeline(tl)
it = tl.GetItemListInTrack('video', 1)[0]

def snap(tag):
    f = os.path.join(out, tag + '.drt'); tl.Export(f, r.EXPORT_DRT)
    _, xml = L.seq_xml(f); efx = [h for h in L.clip_efx(xml) if h]
    return L.params(L.efx_decode(efx[0])[2]) if efx else {}

base = snap('base'); print('base:', base)
TESTS = [
    ('RotationAngle', 10),
    ('AnchorPointX', 100), ('AnchorPointY', 60), ('Pitch', 0.3), ('Yaw', 0.2),
    ('FlipX', True), ('FlipY', True),
    ('CropLeft', 100), ('CropRight', 200), ('CropTop', 50), ('CropBottom', 70),
    ('CropSoftness', 0.5), ('CropRetain', True),
    ('Opacity', 70), ('CompositeMode', 2),
]
DEFAULT = {'ZoomX': 1.0, 'ZoomY': 1.0, 'Opacity': 100.0, 'CompositeMode': 0}
res = {}
for k, v in TESTS:
    ok = it.SetProperty(k, v)
    s = snap('t_' + k)
    diff = {str(key): val for key, val in s.items() if base.get(key) != val}
    res[k] = {'set': v, 'ok': ok, 'diff': diff}
    print(k, v, 'ok=%s' % ok, '->', diff)
    it.SetProperty(k, DEFAULT.get(k, False if isinstance(v, bool) else 0))
json.dump(res, open(os.path.join(out, 'map.json'), 'w'), indent=1, default=str)
