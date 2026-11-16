"""drtlib: ler e escrever os blobs do DRT do DaVinci Resolve (21.2, DbPrjVer 17).

Formato (decifrado por teste, ver HANDOFF.md):
  EffectFiltersBA = hex( >I versao(2) + >I tamanho(1+zstd) + 0x81 + zstd(protobuf) )
  protobuf: repetido f1 = grupo { f1 id_grupo, f7, f9* = param { f1 id_param, f3{f1{f2 double}} = valor, f10 = chaves } }
  chaves (f10): 3 bytes 0xFF + (0x100 - 16*n) , depois n x [ tempo int32 LE | 00 00 0c 00 | double LE ]
"""
import re, struct, zipfile, math, uuid
from compression import zstd  # Python 3.14+

# ---------- protobuf minimo ----------
def _varint(b, i):
    v = s = 0
    while True:
        c = b[i]; i += 1
        v |= (c & 0x7F) << s; s += 7
        if not c & 0x80:
            return v, i

def parse(b):
    """bytes -> lista de (campo, tipo, valor). tipo: v varint, d double, f float, b bytes."""
    i, out = 0, []
    while i < len(b):
        k, i = _varint(b, i); f, w = k >> 3, k & 7
        if w == 0:
            v, i = _varint(b, i); out.append((f, 'v', v))
        elif w == 1:
            out.append((f, 'd', struct.unpack('<d', b[i:i+8])[0])); i += 8
        elif w == 5:
            out.append((f, 'f', struct.unpack('<f', b[i:i+4])[0])); i += 4
        elif w == 2:
            l, i = _varint(b, i); out.append((f, 'b', b[i:i+l])); i += l
        else:
            raise ValueError('wire %d' % w)
    return out

def _enc_varint(v):
    o = bytearray()
    while True:
        c = v & 0x7F; v >>= 7
        o.append(c | (0x80 if v else 0))
        if not v:
            return bytes(o)

def build(fields):
    """lista de (campo, tipo, valor) -> bytes"""
    o = bytearray()
    for f, t, v in fields:
        if t == 'v':
            o += _enc_varint(f << 3) + _enc_varint(v)
        elif t == 'd':
            o += _enc_varint(f << 3 | 1) + struct.pack('<d', v)
        elif t == 'f':
            o += _enc_varint(f << 3 | 5) + struct.pack('<f', v)
        else:
            o += _enc_varint(f << 3 | 2) + _enc_varint(len(v)) + v
    return bytes(o)

# ---------- chaves ----------
FLAGS = bytes.fromhex('00000c00')  # padrao observado nas chaves feitas a mao (curva padrao do Resolve)
FLAG_EASE = bytes.fromhex('00000d00')  # key com tangentes: consome 3 registros companions (in, out, reserva)

def keys_decode(blob):
    n = -struct.unpack('>i', blob[:4])[0] // 16   # cabecalho: int32 big-endian = -16 * n
    out = []
    for k in range(n):
        o = 4 + 16 * k
        t = struct.unpack('<i', blob[o:o+4])[0]
        out.append((t, blob[o+4:o+8], struct.unpack('<d', blob[o+8:o+16])[0]))
    return out

def keys_encode(keys):
    """keys: (quadro, valor) | (quadro, flags4, valor) | (quadro, flags4, valor, (s_in, s_out)).
    Com o 4o elemento, emite a key flagged + 3 companions logo apos ela (ordem: in, out, reserva).
    s = desvio vertical da alca vs a posicao linear: m_in = m_lin - 4*s/dt, m_out = m_lin + 4*s/dt
    (slopes em valor/segundo, dt = duracao do segmento em segundos)."""
    recs = []
    for k in keys:
        if len(k) == 2:
            recs.append((k[0], FLAGS, k[1]))
        elif len(k) == 3:
            assert k[1] != FLAG_EASE, 'key 0x0d sem companions come os 3 registros seguintes'
            recs.append(k)
        else:
            assert k[1] == FLAG_EASE, 'tuple de 4 elem tem que ser key eased (FLAG_EASE)'
            recs.append(k[:3])
            recs += [(0, FLAGS, k[3][0]), (0, FLAGS, k[3][1]), (0, FLAGS, 0.0)]
    out = bytearray(struct.pack('>i', -16 * len(recs)))
    for t, fl, v in recs:
        out += struct.pack('<i', int(t)) + fl + struct.pack('<d', float(v))
    return bytes(out)

# ---------- EffectFiltersBA ----------
RAW_MAX = 100  # abaixo disso o Resolve grava sem compressao (visto: 69 bytes cru; 129 bytes comprimido)
def efx_decode(hexstr):
    """hex -> (versao, estrutura) ; estrutura = parse(protobuf) dos grupos"""
    b = bytes.fromhex(hexstr)
    ver, ln = struct.unpack('>II', b[:8]); flag = b[8]
    raw = zstd.decompress(b[9:]) if flag == 0x81 else b[9:]
    return ver, flag, parse(raw)

def efx_encode(ver, flag, fields):
    """Blob pequeno vai cru (flag 0x80); maior vai em zstd (flag 0x81), como o proprio Resolve grava."""
    raw = build(fields)
    if len(raw) >= RAW_MAX:
        flag, body = 0x81, zstd.compress(raw)
    else:
        flag, body = 0x80, raw
    return (struct.pack('>II', ver, len(body) + 1) + bytes([flag]) + body).hex()

def params(fields):
    """estrutura -> {(grupo, param): {'valor': x|None, 'chaves': [(t,flags,v)]|None}}"""
    res = {}
    for f, t, v in fields:
        if f != 1 or t != 'b':
            continue
        g = parse(v); gid = next(x[2] for x in g if x[0] == 1)
        for ff, tt, vv in g:
            if ff == 9 and tt == 'b' and vv:
                p = parse(vv); pid = next(x[2] for x in p if x[0] == 1)
                val = None; ks = None
                raw3 = None
                for pf, pt, pv in p:
                    if pf == 3:
                        raw3 = pv.hex()
                        try:  # forma simples: f3{f1{f2 double}}
                            val = [x for x in parse([y for y in parse(pv) if y[0] == 1][0][2]) if x[0] == 2][0][2]
                        except Exception:
                            val = None
                    if pf == 10:
                        ks = keys_decode(pv)
                res[(gid, pid)] = {'valor': val, 'chaves': ks, 'f3': raw3 if val is None else None}
    return res

def efx_inject(hexstr, keymap):
    """Poe chaves em parametros que JA existem no blob. keymap {(grupo,param): [(quadro,valor),...]}.
    Levanta KeyError se algum parametro pedido nao existir (setar valor nao-padrao pela API antes)."""
    ver, flag, fields = efx_decode(hexstr)
    achados, novo = set(), []
    for f, t, v in fields:
        if f == 1 and t == 'b':
            g = parse(v); gid = next(x[2] for x in g if x[0] == 1); ng = []
            for gf, gt, gv in g:
                if gf == 9 and gt == 'b' and gv:
                    p = parse(gv); pid = next(x[2] for x in p if x[0] == 1)
                    if (gid, pid) in keymap:
                        p = [x for x in p if x[0] != 10] + [(10, 'b', keys_encode(keymap[(gid, pid)]))]
                        gv = build(p); achados.add((gid, pid))
                ng.append((gf, gt, gv))
            v = build(ng)
        novo.append((f, t, v))
    falta = set(keymap) - achados
    if falta:
        raise KeyError('parametros sem entrada no blob: %s' % sorted(falta))
    return efx_encode(ver, flag, novo)

def efx_inject_raw(hexstr, rawmap):
    """igual a efx_inject, mas rawmap {(grupo,param): bytes_do_f10 ja codificados} (para experimentar flags/curvas)."""
    ver, flag, fields = efx_decode(hexstr)
    achados, novo = set(), []
    for f, t, v in fields:
        if f == 1 and t == 'b':
            g = parse(v); gid = next(x[2] for x in g if x[0] == 1); ng = []
            for gf, gt, gv in g:
                if gf == 9 and gt == 'b' and gv:
                    p = parse(gv); pid = next(x[2] for x in p if x[0] == 1)
                    if (gid, pid) in rawmap:
                        p = [x for x in p if x[0] != 10] + [(10, 'b', rawmap[(gid, pid)])]
                        gv = build(p); achados.add((gid, pid))
                ng.append((gf, gt, gv))
            v = build(ng)
        novo.append((f, t, v))
    if set(rawmap) - achados:
        raise KeyError('parametros sem entrada no blob: %s' % sorted(set(rawmap) - achados))
    return efx_encode(ver, flag, novo)


def _fx_desc(plugin, params):
    """descritor longo do efeito (campo 3 do entry): uid + pluginid + contexto + params."""
    d = build([(1, 'v', 5195353), (2, 'b', plugin.encode()),
               (3, 'b', b'OfxImageEffectContextFilter'), (4, 'v', 1)])
    for nm, val in (params or {}).items():
        if isinstance(val, (list, tuple)) and val and isinstance(val[0], (list, tuple)):
            # animado: [(t,v)..] -> campo 10 com blob de chaves (o Resolve normaliza fora — ver HANDOFF)
            d += build([(5, 'b', build([(1, 'b', nm.encode()), (2, 'b', build([(2, 'd', float(val[0][1]))])),
                                        (10, 'b', keys_encode(val))]))])
            continue
        if isinstance(val, (list, tuple)):
            val = val[0] if val else 0                              # lista nao-chave (ex.: cor): primeiro componente
        if isinstance(val, bool):
            iv = build([(3, 'v', int(val))])
        elif isinstance(val, int) and val >= 0:
            iv = build([(1, 'v', val)])
        elif isinstance(val, str):
            iv = build([(5, 'b', val.encode())])
        else:
            iv = build([(2, 'd', float(val))])                      # numerico real: campo 2 double (ex.: HStrength)
        d += build([(5, 'b', build([(1, 'b', nm.encode()), (2, 'b', iv)]))])
    return build([(2, 'b', d)])

def _fx_entry(plugin, params):
    """campo 9 do grupo 50 = um efeito: descritor longo (com params) + curto (sem)."""
    short = build([(2, 'b', build([(1, 'v', 5195353), (2, 'b', plugin.encode()),
                                   (3, 'b', b'OfxImageEffectContextFilter')]))])
    return build([(1, 'v', 109), (2, 'v', 0), (3, 'b', _fx_desc(plugin, params)),
                  (4, 'b', short), (9, 'v', 0)])

def _fx_group(plugin, params, f7):
    """grupo 50 = um efeito OFX. f7 = slot na pilha (observado 24, 48, 50...; passo +2)."""
    return build([(1, 'v', 50), (3, 'v', 4), (7, 'v', f7),
                  (8, 'v', 52564416510 + f7), (9, 'b', _fx_entry(plugin, params))])

def efx_add_fx(hexstr, fxlist):
    """Acrescenta efeitos OFX ao EffectFiltersBA (que pode vir vazio).
    fxlist: [(plugin_id, {param: valor}), ...] — um grupo 50 por efeito."""
    ver, flag, fields = efx_decode(hexstr) if hexstr else (2, 0x80, [])
    f7s = [x[2] for f, t, v in fields if f == 1 and t == 'b'
           for x in parse(v) if x[0] == 7]
    nxt = max(f7s) + 2 if f7s else 24                          # slot seguinte livre: nunca colide com grupos existentes
    for i, (plugin, params) in enumerate(fxlist):
        fields.append((1, 'b', _fx_group(plugin, params, nxt + 2 * i)))
    return efx_encode(ver, flag, fields)

def fx_list(hexstr):
    """EffectFiltersBA -> [(plugin_id, {param: valor})] dos grupos 50."""
    if not hexstr:
        return []
    ver, flag, fields = efx_decode(hexstr)
    out = []
    for f, t, v in fields:
        if f != 1 or t != 'b':
            continue
        g = parse(v)
        if next((x[2] for x in g if x[0] == 1), None) != 50:
            continue
        for ff, tt, vv in g:
            if ff != 9 or not vv:
                continue
            plugin, prs = None, {}
            for a, b, c in parse(vv):
                if a != 3 or not isinstance(c, bytes):
                    continue
                try:
                    desc = parse(parse(c)[0][2])
                except Exception:
                    continue
                for dd, dt, dv in desc:
                    if dd == 2:
                        plugin = dv.decode('utf8', 'replace')
                    elif dd == 5:
                        pr = parse(dv)
                        nm = next((q[2].decode('utf8', 'replace') for q in pr if q[0] == 1), None)
                        wr = next((q[2] for q in pr if q[0] == 2), None)
                        if nm and wr:
                            try:
                                inner = parse(wr)
                                for tag, wtype, wval in inner:
                                    prs[nm] = wval.decode('utf8', 'replace') if isinstance(wval, bytes) else wval
                            except Exception:
                                pass
            if plugin:
                out.append((plugin, prs))
    return out


def in_field(frames):
    """valor do campo <In> (record frames, com fracao): '59|<double LE hex da fracao>' ; vazio se 0."""
    if frames <= 1e-9:
        return ''
    ip = int(math.floor(frames)); fr = frames - ip
    return '%d|%s' % (ip, struct.pack('<d', fr).hex())


# Templates de transicao (formato nativo DRT): um <Element> por transicao, inserido
# entre os <Element> dos clipes adjacentes dentro de <Items> da trilha.
_TR_VIDEO = '''<Element>
      <Sm2TiTransition DbId="{uid}">
       <FieldsBlob>{fields}</FieldsBlob>
       <PrettyType>{pretty}</PrettyType>
       <Name>{name}</Name>
       <Start>{start}</Start>
       <Duration>{dur}</Duration>
       <LinkedItemSync/>
       <WasDisbanded>false</WasDisbanded>
       <MarkersBA/>
       <UiMemento>0</UiMemento>
       <Flags>0</Flags>
       <PriorityIndex>0</PriorityIndex>
       <EffectFiltersBA>{efx}</EffectFiltersBA>
       <ImportExportMetadataBA/>
       <RenderTextEnabled>true</RenderTextEnabled>
       <RenderTextGanged>true</RenderTextGanged>
       <RenderTextPrefixed>true</RenderTextPrefixed>
       <AlignmentType>2</AlignmentType>
       <Position>2</Position>
      </Sm2TiTransition>
     </Element>'''
_TR_FIELDS = '000000020000001c8012190000002c789c6366606400028ee3f30fbf642000006baa031f'
_TR_EFX = '000000020000003a800a37081238024a004a004a004a004a29088b015224ffffffe00000000000000c0000000000000000001800000000000c00000000000000f03f'
_TR_WIPE_FIELDS = '0000000200000020801c1d0000002c789c63c8c8c8c8000002f2f307bf4d21000006dca0373'
_TR_AUDIO_EFX = ('00000002000001418128b52ffd60ea02b50900d24e3631608bda00016b1886611886618aaa90c45a8b2c4bb74e225968cc77bbad'
                 'cdb43f34bdb7510008cd286032991041dcafba3a6db563c78e1f207ad278bd56901d3be66054645e53f64ec70e0cfdd6395ec'
                 '67bbd5ad6a24a3d7f9d724c23acdc237c3969bcd14eafb71f24ba8e1ffab3d3eb4423ac3212140da3e3030d6c4098b087f'
                 'e98b5b46efaa5cf4b7da7f3948a06887acc1863ab5b85577fe4cb10e35c6c4c1b8b08035e8d6996843765b48b674648a9'
                 'f9ac295016da65d268eb7bb08f0c615802d148a3258514040c7448221f13001601828924325a012300e9f0abc6e90af86'
                 'f499c4a043085b2b044a134bcb479940460f4f9df4213e27805a1a8862fe8bcb86058bb0b23aeab01486d4073cdcda64f'
                 'c1d02980a688b20aada10ad6ead65663955acbce363a856d7330570bd2da6206')


def _trans_el(tr):
    """Monta o <Element> de uma transicao. tr: {'kind','start','dur','pretty','name'}."""
    if tr.get('kind') == 'audio':
        return _TR_VIDEO.format(uid=uuid.uuid4(), fields=_TR_FIELDS,
                                pretty='Final Cut Pro 7', name='', efx=_TR_AUDIO_EFX,
                                start=tr['start'], dur=tr['dur'])
    pretty, fields = tr['pretty'], _TR_FIELDS
    if pretty == 'WIPE': fields, pretty = _TR_WIPE_FIELDS, 'Cross Dissolve'
    return _TR_VIDEO.format(uid=uuid.uuid4(), fields=fields, pretty=pretty,
                            name=tr.get('name') or pretty, efx=_TR_EFX,
                            start=tr['start'], dur=tr['dur'])


def insere_transicoes(xml, transitions):
    """Insere <Element> de transicao entre os clipes adjacentes em <Items> de cada trilha.
    transitions: [{'kind': 'video'|'audio', 'track': n, 'start': abs_f, 'dur': f, 'cut': abs_f,
                   'pretty': str, 'name': str}] — start/cut em quadros absolutos da timeline.
    Devolve (xml, avisos)."""
    avisos = []
    if not transitions:
        return xml, avisos
    por_trilha = {}
    for tr in transitions:
        por_trilha.setdefault((tr.get('kind', 'video'), tr['track']), []).append(tr)
    for (kind, tno), trs in por_trilha.items():
        vec = 'AudioTrackVec' if kind == 'audio' else 'VideoTrackVec'
        vm = re.search(r'<%s>(.*?)</%s>' % (vec, vec), xml, re.S)
        if not vm:
            avisos.append('transicao: %s nao encontrado no DRT (trilha %d ignorada)' % (vec, tno)); continue
        tblks = list(re.finditer(r'<Sm2TiTrack .*?</Sm2TiTrack>', vm.group(1), re.S))
        if tno < 1 or tno > len(tblks):
            avisos.append('transicao: trilha %s %d nao existe no DRT' % (kind, tno)); continue
        tb = tblks[tno - 1]; blk = tb.group(0)
        im = re.search(r'<Items>(.*?)</Items>', blk, re.S)
        if not im:
            avisos.append('transicao na trilha %s %d ignorada (trilha vazia)' % (kind, tno)); continue
        inner = im.group(1)
        els = list(re.finditer(r'<Element>\s*<Sm2Ti(?:VideoClip|AudioClip|Generator)\b.*?</Sm2Ti\w+>\s*</Element>', inner, re.S))
        for tr in sorted(trs, key=lambda x: x['cut']):
            esq = None
            for e in els:
                st = re.search(r'<Start>(-?\d+)</Start>', e.group(0)); du = re.search(r'<Duration>(\d+)</Duration>', e.group(0))
                if st and du and abs(int(st.group(1)) + int(du.group(1)) - tr['cut']) <= 1:
                    esq = e; break
            if esq is None:
                avisos.append('transicao "%s" ignorada: nenhum clipe termina no corte %d (trilha %s %d)' % (tr.get('name') or tr.get('pretty'), tr['cut'], kind, tno)); continue
            pos = inner.find(esq.group(0), esq.start()) + len(esq.group(0))
            inner = inner[:pos] + _trans_el(tr) + inner[pos:]
            els = list(re.finditer(r'<Element>\s*<Sm2Ti(?:VideoClip|AudioClip|Generator|Transition)\b.*?</Sm2Ti\w+>\s*</Element>', inner, re.S))
        nblk = blk[:im.start(1)] + inner + blk[im.end(1):]
        xml = xml[:vm.start(1) + tb.start()] + nblk + xml[vm.start(1) + tb.end():]
    return xml, avisos


def move_titulos(xml, titulos):
    """titulos: [{'track','start','dur','nome'}] (quadros absolutos). Os itens Text+ inseridos
    pela API caem no playhead/V1: aqui eles sao realocados — Element do Sm2TiVideoClip SEM
    <File Path> sai de onde estiver e entra na trilha certa, com Start/Duration corrigidos.
    Ordem dos elementos sem-midia = ordem de insercao = ordem de `titulos`."""
    avisos = []
    if not titulos:
        return xml, avisos
    vm = re.search(r'<VideoTrackVec>(.*?)</VideoTrackVec>', xml, re.S)
    if not vm:
        return xml, ['titulos: VideoTrackVec nao encontrado no DRT']
    vec = vm.group(1)
    tblks = list(re.finditer(r'<Sm2TiTrack .*?</Sm2TiTrack>', vec, re.S))
    trilhas_xml = [tb.group(0) for tb in tblks]
    vagos = []     # (trilha_idx, start, element_str) dos itens sem midia (Text+ / Adjustment Clip)
    for ti, tb in enumerate(trilhas_xml):
        for e in re.finditer(r'<Element>\s*<(Sm2Ti(?:VideoClip|Generator))\b.*?</\1>\s*</Element>', tb, re.S):
            if '<MediaFilePath>' not in e.group(0):
                st = re.search(r'<Start>(-?\d+)</Start>', e.group(0))
                vagos.append((ti, int(st.group(1)) if st else -1, e.group(0)))
    starts_ok = {tt['_ins'] for tt in titulos if tt.get('_ins') is not None}
    if starts_ok:
        vagos = [v for v in vagos if v[1] in starts_ok]          # append: so itens RECEM-inseridos — os antigos sem-midia nao sao tocados
    for i, tt in enumerate(titulos):
        hit = None
        if tt.get('_ins') is not None:
            hit = next((v for v in vagos if v[1] == tt['_ins']), None)   # casa exata pelo start de insercao
        elif i < len(vagos):
            hit = vagos[i]                                             # sem _ins: pareamento ordinal (timeline nova)
        if hit is None:
            avisos.append('elemento sem-midia "%s" nao apareceu no DRT' % tt['nome']); continue
        ti_ori, _, el = hit
        # corrige Start/Duration/nome
        el2 = re.sub(r'<Start>-?\d+</Start>', '<Start>%d</Start>' % tt['start'], el, count=1)
        el2 = re.sub(r'<Duration>\d+</Duration>', '<Duration>%d</Duration>' % max(1, tt['dur']), el2, count=1)
        if tt.get('nome'):
            el2 = re.sub(r'<Name>[^<]*</Name>', '<Name>%s</Name>' % tt['nome'].replace('&', '&amp;').replace('<', '&lt;'), el2, count=1)
        # remove da trilha de origem
        trilhas_xml[ti_ori] = trilhas_xml[ti_ori].replace(el, '', 1)
        # insere na trilha alvo em ordem cronologica dentro de <Items>
        alvo = tt['track']
        if alvo < 1 or alvo > len(trilhas_xml):
            avisos.append('titulo "%s": trilha %d nao existe — ficou onde caiu' % (tt['nome'], alvo))
            if '<Items/>' in trilhas_xml[ti_ori]:
                trilhas_xml[ti_ori] = trilhas_xml[ti_ori].replace('<Items/>', '<Items>' + el2 + '</Items>', 1)
            elif '</Items>' in trilhas_xml[ti_ori]:
                trilhas_xml[ti_ori] = trilhas_xml[ti_ori].replace('</Items>', el2 + '</Items>', 1)
            else:
                trilhas_xml[ti_ori] = trilhas_xml[ti_ori] + el2
            continue
        tb = trilhas_xml[alvo - 1]
        if '<Items/>' in tb:
            tb = tb.replace('<Items/>', '<Items></Items>', 1)   # trilha vazia exporta <Items/> autocontido
        im = re.search(r'<Items>(.*?)</Items>', tb, re.S)
        if not im:
            trilhas_xml[alvo - 1] = tb + el2
            continue
        inner = im.group(1)
        els = list(re.finditer(r'<Element>\s*<Sm2Ti\w+\b.*?</Sm2Ti\w+>\s*</Element>', inner, re.S))
        ins = len(inner)
        for e in els:
            st = re.search(r'<Start>(-?\d+)</Start>', e.group(0))
            if st and int(st.group(1)) > tt['start']:
                ins = e.start(); break
        trilhas_xml[alvo - 1] = tb[:im.start(1)] + inner[:ins] + el2 + inner[ins:] + tb[im.end(1):]
    # remonta o VideoTrackVec por posicoes (preserva <Element> que envolve cada Sm2TiTrack)
    out = []; last = 0
    for i, tb in enumerate(tblks):
        out.append(vec[last:tb.start()]); out.append(trilhas_xml[i]); last = tb.end()
    out.append(vec[last:])
    xml = xml[:vm.start(1)] + ''.join(out) + xml[vm.end(1):]
    return xml, avisos


def patch_drt2(src, dst, patches, audio_patches=None, transitions=None, titulos=None):
    """patches: lista (um por clipe de video, na ordem do arquivo) de None ou
    {'keys': {(g,p): [(t,v)..]} ou None, 'timemap_hex': str ou None, 'in': str ou None, 'duration': int ou None}
    audio_patches: idem para os blocos Sm2TiAudioClip (mesma estrutura de patch).
    transitions: lista de dicts para insere_transicoes (quadros absolutos).
    Devolve a lista de avisos das transicoes."""
    avisos = []
    zin = zipfile.ZipFile(src); zout = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename.startswith('SeqContainer/') and info.filename.endswith('.xml'):
            xml = data.decode('utf-8')
            def mk_sub(it):
                def clip_sub(m):
                    blk = m.group(0)
                    if '<MediaFilePath>' not in blk:
                        return blk              # titulo Text+/sem-midia: nao consome patch
                    pt = next(it, None)
                    if not pt:
                        return blk
                    if pt.get('keys') or pt.get('fx'):
                        def _efx_sub(e):
                            h = e.group(1)
                            if pt.get('keys'):
                                h = efx_inject(h, pt['keys']) if h else h
                            if pt.get('fx'):
                                h = efx_add_fx(h, pt['fx'])
                            return '<EffectFiltersBA>%s</EffectFiltersBA>' % h if h else e.group(0)
                        blk = re.sub(r'<EffectFiltersBA>([0-9a-f]*)</EffectFiltersBA>|<EffectFiltersBA\s*/>',
                                     _efx_sub, blk, count=1)
                        if pt.get('fx') and '<EffectFiltersBA>' not in blk:      # tag ausente: cria na posicao canonica (antes de ImportExportMetadataBA ou do fecho)
                            blk = re.sub(r'(<ImportExportMetadataBA|</Sm2Ti(?:Video|Audio)Clip>)',
                                         lambda c: '<EffectFiltersBA>%s</EffectFiltersBA>%s' % (efx_add_fx('', pt['fx']), c.group(0)), blk, count=1)
                        if pt.get('keys') and not re.search(r'<EffectFiltersBA>[0-9a-f]', blk):
                            avisos.append('clipe com chaves mas EffectFiltersBA vazio/ausente: chaves nao aplicadas')
                    if pt.get('timemap_hex'):
                        blk = re.sub(r'<MediaTimemapBA>[0-9a-f]*</MediaTimemapBA>', '<MediaTimemapBA>%s</MediaTimemapBA>' % pt['timemap_hex'], blk, count=1)
                        iv = pt.get('in') or ''
                        blk = re.sub(r'<In>[^<]*</In>|<In\s*/>', ('<In>%s</In>' % iv) if iv else '<In/>', blk, count=1)
                    if pt.get('duration') is not None:
                        blk = re.sub(r'<Duration>\d+</Duration>', '<Duration>%d</Duration>' % pt['duration'], blk, count=1)
                    return blk
                return clip_sub
            xml = re.sub(r'<Sm2TiVideoClip .*?</Sm2TiVideoClip>', mk_sub(iter(patches)), xml, flags=re.S)
            if audio_patches is not None:
                xml = re.sub(r'<Sm2TiAudioClip .*?</Sm2TiAudioClip>', mk_sub(iter(audio_patches)), xml, flags=re.S)
            if transitions:
                xml, _avs = insere_transicoes(xml, transitions)
                avisos.extend(_avs)
            if titulos:
                xml, _avs = move_titulos(xml, titulos)
                avisos.extend(_avs)
            data = xml.encode('utf-8')
        zout.writestr(info, data)
    zout.close()
    return avisos


def patch_drt(src, dst, keymaps):
    """Reescreve o DRT com as chaves. keymaps: lista, uma por clipe de video na ordem do arquivo
    (dict como em efx_inject, ou None para nao mexer)."""
    zin = zipfile.ZipFile(src); zout = zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED)
    for info in zin.infolist():
        data = zin.read(info.filename)
        if info.filename.startswith('SeqContainer/') and info.filename.endswith('.xml'):
            xml = data.decode('utf-8'); it = iter(keymaps)
            def sub(m):
                km = next(it, None)
                if not km or not m.group(1):
                    return m.group(0)
                return '<EffectFiltersBA>%s</EffectFiltersBA>' % efx_inject(m.group(1), km)
            xml = re.sub(r'<EffectFiltersBA>([0-9a-f]*)</EffectFiltersBA>', sub, xml)
            data = xml.encode('utf-8')
        zout.writestr(info, data)
    zout.close()

# ---------- mapa de tempo (retime) : MediaTimemapBA ----------
# Formato (de resolve-advanced/vendor/drp-format/media-timemap.js, MIT, medido no Resolve 21):
#  identidade (1x): 0x02 + doubles BE ;  retimado: keyed-dict {YMin,YMax,XMax,UniqueId,LastValidYOffset,KeyframesBA,DbType='Sm2TimeMap'}
#  KeyframesBA = protobuf { f160 varint 0 ; f1* = {09 recordSec double LE ; 11 sourceSec double LE} } ; origem implicita (0,0)
T_INT32, T_DOUBLE, T_STRING, T_BYTES = 0x02, 0x06, 0x0a, 0x0c


def _u16be(s):
    return s.encode('utf-16-be')


def kd_encode(entries):
    """entries: [(chave, tipo, valor)] ; tipo T_DOUBLE/T_STRING/T_BYTES(valor em bytes ou None)/T_INT32 -> bytes"""
    out = bytearray(struct.pack('>II', 1, len(entries)))
    for k, t, v in entries:
        kb = _u16be(k); out += struct.pack('>I', len(kb)) + kb + struct.pack('>IB', t, 0)
        if t == T_STRING:
            sb = _u16be(v); out += struct.pack('>I', len(sb)) + sb
        elif t == T_BYTES:
            out += struct.pack('>I', 0xFFFFFFFF) if v is None else struct.pack('>I', len(v)) + v
        elif t == T_DOUBLE:
            out += struct.pack('>d', v)
        elif t == T_INT32:
            out += struct.pack('>i', v)
        else:
            raise ValueError(t)
    return bytes(out)


def kd_decode(b):
    """bytes -> [(chave, tipo, valor)] (valor: str, bytes, float ou int)"""
    n = struct.unpack('>I', b[4:8])[0]; o = 8; out = []
    for _ in range(n):
        kl = struct.unpack('>I', b[o:o+4])[0]; k = b[o+4:o+4+kl].decode('utf-16-be'); o += 4 + kl
        t = struct.unpack('>I', b[o:o+4])[0]; o += 5
        if t == T_STRING:
            ln = struct.unpack('>I', b[o:o+4])[0]; o += 4; v = b[o:o+ln].decode('utf-16-be'); o += ln
        elif t == T_BYTES:
            ln = struct.unpack('>I', b[o:o+4])[0]; o += 4
            if ln == 0xFFFFFFFF: v = None
            else: v = b[o:o+ln]; o += ln
        elif t == T_DOUBLE:
            v = struct.unpack('>d', b[o:o+8])[0]; o += 8
        elif t == T_INT32:
            v = struct.unpack('>i', b[o:o+4])[0]; o += 4
        else:
            raise ValueError('tipo 0x%x' % t)
        out.append((k, t, v))
    return out


def timemap_encode(points, source_dur_sec, record_dur_sec, unique_id, origin_src=0.0):
    """points: [(recordSec, sourceSec), ...] depois da origem (0, origin_src). Forma R21 em protobuf, nao-eased."""
    fields = [(160, 'v', 0)]
    if origin_src:
        fields.append((2, 'd', origin_src))
    for rec, src in points:
        inner = b'\x09' + struct.pack('<d', rec) + b'\x11' + struct.pack('<d', src)
        fields.append((1, 'b', inner))
    kf = build(fields)
    return kd_encode([('YMin', T_DOUBLE, -1.0), ('YMax', T_DOUBLE, -1.0), ('XMax', T_DOUBLE, record_dur_sec),
                      ('UniqueId', T_STRING, unique_id), ('LastValidYOffset', T_DOUBLE, source_dur_sec),
                      ('KeyframesBA', T_BYTES, kf), ('DbType', T_STRING, 'Sm2TimeMap')])


def timemap_encode_eased(points, source_dur_sec, record_dur_sec, unique_id):
    """Forma EASED do Sm2TimeMap (Studio 21): pontos esparsos + alcas de ease = rampa editavel no Inspector.
    points: [(recordSec, sourceSec, handles|None), ...] depois da origem (0,0) implicita.
    handles: [inRec, inSrc, outRec, outSrc] relativos ao ponto (in<0<out); a curva entre
    P+in e P+out vira uma cubica cujos dois pontos de controle internos ficam EM P (corner smooth).
    Sem campo 160/YMin; KeyframesBA = 0x81 + zstd(protobuf). Formato medido em resolve-advanced/vendor/drp-format."""
    fields = [(1, 'b', b'')]                                   # origem vazia (0,0)
    for rec, src, h in points:
        inner = b'\x09' + struct.pack('<d', rec) + b'\x11' + struct.pack('<d', src)
        if h:
            inner += b'\x1a' + _enc_varint(len(h) * 8) + b''.join(struct.pack('<d', v) for v in h)
        fields.append((1, 'b', inner))
    kf = b'\x81' + zstd.compress(build(fields))
    last_src = points[-1][1]
    return kd_encode([('YMax', T_DOUBLE, min(last_src, source_dur_sec)), ('XMax', T_DOUBLE, record_dur_sec),
                      ('UniqueId', T_STRING, unique_id), ('Mode', T_INT32, 2),
                      ('LastValidYOffset', T_DOUBLE, source_dur_sec),
                      ('KeyframesBA', T_BYTES, kf), ('DbType', T_STRING, 'Sm2TimeMap')])


def timemap_decode(hexstr):
    """MediaTimemapBA (hex) -> {'forma': 'identidade'|'retimado', 'pontos': [(rec, src)], 'origem': src0, 'entradas': dict}"""
    b = bytes.fromhex(hexstr)
    if len(b) >= 8 and struct.unpack('>I', b[:4])[0] == 1:
        ent = {k: v for k, t, v in kd_decode(b)}
        kf = ent.get('KeyframesBA'); pts = []; origem = 0.0
        if kf:
            if kf[0] == 0x81:
                kf = zstd.decompress(kf[1:])
            for f, t, v in parse(kf):
                if f == 2 and t == 'd': origem = v
                if f == 1 and t == 'b':
                    if not v: continue                       # origem vazia (0,0) da forma eased
                    rec = src = 0.0; o = 0; h = None
                    while o < len(v):
                        if v[o] == 0x09: rec = struct.unpack('<d', v[o+1:o+9])[0]; o += 9
                        elif v[o] == 0x11: src = struct.unpack('<d', v[o+1:o+9])[0]; o += 9
                        elif v[o] == 0x1a:
                            ln, o = _varint(v, o + 1)
                            h = [struct.unpack('<d', v[o+i*8:o+i*8+8])[0] for i in range(ln // 8)]; o += ln
                        else: break
                    pts.append((rec, src) if h is None else (rec, src, h))
        return {'forma': 'retimado', 'pontos': pts, 'origem': origem, 'entradas': ent}
    return {'forma': 'identidade', 'bytes': b}


def timemap_eval(pontos, t):
    """src(t) do mapa: pontos = [(rec, src, handles|None), ...] incluindo origem (0,0).
    Modelo medido no Studio 21 (drp-format sourceSecAt): ponto eased substitui o canto entre
    P+in e P+out por uma cubica cujos dois pontos de controle ficam EM P; fora da janela, corda reta."""
    for p in pontos:
        h = p[2] if len(p) > 2 else None
        if not h:
            continue
        inX, inY, outX, outY = h[0], h[1], h[2], h[3]
        if t < p[0] + inX or t > p[0] + outX:
            continue
        lo, hi = 0.0, 1.0
        for _ in range(60):
            u = (lo + hi) / 2
            x = p[0] + (1 - u) ** 3 * inX + u ** 3 * outX
            if x < t:
                lo = u
            else:
                hi = u
        u = (lo + hi) / 2
        return p[1] + (1 - u) ** 3 * inY + u ** 3 * outY
    for i in range(1, len(pontos)):
        if t <= pontos[i][0] or i == len(pontos) - 1:
            a, b = pontos[i - 1], pontos[i]
            dr = b[0] - a[0]
            return a[1] + (b[1] - a[1]) * (t - a[0]) / dr if dr else a[1]
    return pontos[0][1]


# ---------- arquivo DRT ----------
def seq_xml(zpath):
    z = zipfile.ZipFile(zpath)
    n = [x for x in z.namelist() if x.startswith('SeqContainer/') and x.endswith('.xml')][0]
    return n, z.read(n).decode('utf-8')

def clip_efx(xml):
    """devolve lista de hex EffectFiltersBA de cada clipe de video (ordem do arquivo)"""
    return re.findall(r'<EffectFiltersBA>([0-9a-f]*)</EffectFiltersBA>', xml)
