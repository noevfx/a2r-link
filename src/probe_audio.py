# -*- coding: utf-8 -*-
r"""Sonda 2 do audio no DRT (DaVinci aberto no projeto de teste):
   item de audio APARADO (startFrame>0) e com velocidade -> como o DRT guarda
   o offset de midia e a velocidade (<In> vem vazio no audio)."""
import os, re, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen, drtlib as L


def _walk(pasta, out):
    for c in pasta.GetClipList() or []:
        out.append(c)
    for f in pasta.GetSubFolderList() or []:
        _walk(f, out)


def dump_clips(xml, titulo):
    print('=== %s ===' % titulo)
    for m in re.finditer(r'<Sm2TiAudioClip .*?</Sm2TiAudioClip>', xml, re.S):
        blk = m.group(0)
        print('--- audio clip')
        for tag in ('Start', 'Duration', 'In', 'Out', 'MediaStartTime', 'MediaTimemapBA',
                    'MediaTrackIdx', 'MediaFrameRate', 'EffectFiltersBA'):
            mm = re.search(r'<%s>(.*?)</%s>' % (tag, tag), blk, re.S)
            if mm is not None:
                print('  %-18s %s' % (tag, mm.group(1)[:130]))


r, p = gen._connect()
mp = p.GetMediaPool()
todos = []
_walk(mp.GetRootFolder(), todos)
mi = [c for c in todos if c.GetClipProperty('Audio Ch')][0]
print('midia:', mi.GetName(), '| frames:', mi.GetClipProperty('Frames'))

import uuid
tl = mp.CreateEmptyTimeline('_probe2_' + uuid.uuid4().hex[:4])
p.SetCurrentTimeline(tl)
t0 = tl.GetStartFrame()
if tl.GetTrackCount('audio') < 1:
    tl.AddTrack('audio')

# item 1: aparado — midia 60..160
print('append aparado:', bool(mp.AppendToTimeline([{'mediaPoolItem': mi, 'mediaType': 2, 'trackIndex': 1,
                                                    'recordFrame': t0, 'startFrame': 60, 'endFrame': 160}])))
# item 2: inteiro depois, depois SetSpeed 50%
print('append inteiro:', bool(mp.AppendToTimeline([{'mediaPoolItem': mi, 'mediaType': 2, 'trackIndex': 1,
                                                    'recordFrame': t0 + 100, 'startFrame': 0, 'endFrame': 100}])))
itens = tl.GetItemListInTrack('audio', 1) or []
print('itens:', [(it.GetStart(), it.GetDuration()) for it in itens])
if len(itens) > 1:
    print('SetSpeed 50% ->', itens[1].SetSpeed({'Percentage': 50.0, 'RippleTimeline': False}))
    print('dur depois:', itens[1].GetDuration())

f = os.path.join(tempfile.gettempdir(), 'noebridge', '_probe2.drt')
tl.Export(f, r.EXPORT_DRT)
_, xml = L.seq_xml(f)
dump_clips(xml, 'APARADO + 50%')
mp.DeleteTimelines([tl])
print('fim')
