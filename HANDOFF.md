# A2R Link (antes Noe Bridge) — HANDOFF (estado em 18/11/2026)

## ESTADO — rodada "gaps reais" (blend modes, fx animados, px_blur, audio FX, máscaras)

- **Blend modes**: reader PR lê enum do componente Opacity (`blendMode`), AE lê `layer.blendingMode`
  (enum 5212+); `_PR_BLEND`/`_AE_BLEND` → `composite` (int do Resolve 0-31) → `SetProperty('CompositeMode',N)`
  pré-export → serializa no DRT. **Verificado**: Screen(5) roundtrip inteiro. Dissolve/matte modes → aviso.
- **Params de efeito animados**: campo-10 do blob grupo-50 é **normalizado fora** pelo Resolve (provado —
  keys somem no re-export). Caminho real: `TimelineItem.AddFusionComp()` + `comp.AddTool('ofx.<ns>.<Camel>')`
  + `tool.SetInput('Source', clip_src?)`... na prática: `fc.BezierSpline()` → `inp.SetSource(spline)` →
  `spline.SetKeyFrames({frame:{Value=v}})` — **verificado**: DropShadow angle 90→180→270, valores lidos nos
  frames 0/30/60. Leitores emitem `keys`/`samples` por param; normalizer converte e emite `anim` no spec;
  gen cria UMA comp por clipe que tem qualquer param animado. Param animado é excluído do `pt['fx']` (não
  duplica no Inspector). Mapa blob-id→tool-id: `normalizer._FX_CAMEL` (deriva de `tests/fx_params.json`).
- **Escala px→normalizado (medida, não doc)**: OFX blur segue `sigma_px = 0.1 * dim_do_frame * S²`
  (HStrength→largura, VStrength→altura; quadrático, linear em σ, escala com resolução). Calibrado com
  step-edge sintético via Fusion + `ExportFrame` + PIL/numpy; erro <1% (alvo σ24 → 24.19). Premiere
  `Blurriness` px ≈ raio → σ=px/2.5 → `S = sqrt((px/2.5)/(0.1*dim))`. BoxBlur assume a mesma lei (não
  medida). Conv: `px_blur_x`/`px_blur_y` recebem `rW`/`rH` do normalizer.
- **Efeitos de áudio**: `premiere_read.jsx` enumera `info.components` de clips de áudio além de
  Volume/Panner → `afx` no spec; `_AFX` mapeia ~40 nomes PR → Fairlight FX ids; gen aplica
  `TimelineItem.AddEffect('audio', 'fx.FairlightXxx')` pós-import — verificado aplicar e sobreviver a DRT.
  Params vão com default + aviso.
- **Transições**: API não expõe direção/params (`TransitionType`/`Duration` só leitura de metadados);
  transições Fusion expõem a comp mas os templates `.setting` não publicam UserControls — vai com defaults
  do template (documentado, não é bug). Transições simples serializam `Sm2TiTransition`+`FieldsBlob`
  (zlib, ~44B defaults).
- **Máscaras**: `numMasks` lido no AE reader; layer com máscara → aviso explícito. PowerWindow/tracker
  fora do escopo. PR não expõe máscaras por DOM — sem detecção lá.
- **Params novos**: Sharpen→`sharpen` (map_1_5: PR 0-500 → 1-5), UltraSharpen→`sharpenStrength` (pct500),
  Glow→`threshold`(pct255)/`brightness`(mul2), Vignette→`size`, Emboss→`power`, Dent→`strength`,
  BoxBlur→`HStrength/VStrength`(px_blur, mesma lei do Gaussian)/`Iterations`.
- **Cleanup**: comps/timelines de calibração ficaram nas timelines de teste (`_test_*`, `TESTE_A2R*`).

## ESTADO 18/11 — rodada "tudo de uma vez": markers de clipe, texto posicionado, nested completo, validações

**Verificado no Resolve real (paste `_batch_sint2` e `TESTE_A2R 12`):**

- **Markers de clipe (NOVO)**: PR lê via `.prproj` (`prproj.clip_markers` — cadeia Clip→`Markers`→`Marker`→objeto
  `DVAMarker` JSON; `mStartTime` em ticks TPS, dominio midia; source markers compartilham a colecao entre
  takes). AE lê `layer.marker` (keyTime no domínio comp). Spec carrega `d` = offset em quadros no record
  do take (inverte `m_curve` quando remap/reverso). Resolve: **markers NÃO serializam no DRT** —
  `MarkersBA` sai vazio sempre; entram via `TimelineItem.AddMarker(frameId, cor, nome, nota, dur)` DEPOIS
  do reimport. `frameId` = **frame de midia** do clipe (src_in + d·mfps/fps; com remap = timemap_eval).
  Verificado: MARKER_CLIPE 2.5s → fid 60 nos 4 takes que cobrem a janela (filtrados corretamente).
- **Título com posição**: clipes sem mídia COM `texto` (gráficos do Premiere) viram Text+ — agora com
  transform estático via `SetProperty` no item (pan/tilt/zoom/rot/op; animado cai estático + aviso).
  Verificado: Pan 300, Tilt 500, Zoom 1.5, Rot 15, Opacity 80 no Inspector.
- **Nested completo**: `patch_sub` agora puxa `remaps` + `clip_markers` + `speeds` do `.prproj` por sub-seq
  (recursivo). Flatten: props NÃO levam +off (são domínio mídia — era bug latente: props animadas em
  nested deslocavam ~off segundos); remap/knots-absolutos/markers LEVAM +off (domínio sub-seq).
- **Avisos novos**: `reversed + remap` (a rampa não entra com o reverso); título com transform animado.
- **Crop animado**: verificado no blob — `CropTop` saiu com keys `0x0d`+companions (grupo 6, params 54-57).
- **Reverso+speed no mesmo clipe**: timemap descendente `[5→5, 7.4→0]` no blob — funciona.
- **Áudio vol_keys**: `(124,95)` com 3 keys `f10` no paste real — confirmado fora do sintético.
- **Bug real**: `SetSetting('timelineFrameRate','24.0')` falha silencioso (timeline saía 25fps) — agora
  emite '24' quando o valor é inteiro.
- **Freeze frame (NOVO, código pronto — falta validação real)**:
  - **PR "Frame Hold"**: leitor lê `frameHold` do componente (`Frame Hold Source Time`, segundos de
    mídia) → normalizer emite `remap` plano `[[0, t], [dur_f, t]]` → timemap com fonte constante no
    Resolve. Combinado com speed/reverso/rampa: o freeze vence + aviso. Áudio linkado NÃO congela
    (`m_curve=None`) — igual ao Premiere.
  - **AE `stretch=0`** (layer congelada): mesmo timemap plano no quadro do in-point; áudio segue a
    janela normal (não congela). Antes era ignorada com aviso.
  - gen.py: timemap plano (sa==sb) appenda janela de 1 quadro e pula SetSpeed (a curva estica).
  - AE freeze via hold do Time Remap já funcionava pela curva (sem mudança).
- **Flag `0x08`**: importa e sobrevive ao re-export; semântica não identificada (suspeita: hold/estado
  especial) — não usada no pipeline.
- **Freeze VERIFICADO de ponta a ponta**:
  - Sintético: `remap` plano `[[0,5],[96,5]]` → DRT re-exportado timemap `(5,5),(9,5)`, `In=120 Dur=96`.
  - **REAL (Premiere "Insert Frame Hold Segment")**: o DOM esconde o hold (`clip.components` não lista),
    mas o `.prproj` traz `<FrameHold>tipo</FrameHold>` + `<FrameHoldStart>ticks</FrameHoldStart>` no
    VideoClip — `prproj.frame_holds()` lê por take (main + sub-seqs). Take tr4 6.5–10s → DRT
    re-exportado `[(6.0,6.0),(9.5,6.0)]` — plano no quadro certo. Leitor JSX também tenta `frameHold`
    (bonus, o `.prproj` é a fonte confiável).
  - Chave **Hold** de prop (degrau): sai como duas keys a 1 quadro de distância — visualmente o hold
    exato; no Resolve vira rampa de 1 frame, não flag de hold (verificado no take tr2).
- **Correções da revisão secundária (SWE2MAX)**:
  - `remap-info` devolve `data` enriquecido; painel faz `d = req.data` antes do segundo `grava()`
    (antes, a reamostragem apagava markers/labels/sub-patches do arquivo — mesma classe do bug de
    `remap_nodes` da 0.1.3).
  - `paste` sempre re-enriquece do `.prproj` quando `seq.path` existe.
  - Áudio linkado a Frame Hold NÃO herda o timemap plano (`_m_curve` gate) — verificado.
  - Zona vazia de títulos/ajustes no modo existente parte do fim REAL (`GetEndFrame`); `rec_livre`
    avança por `GetDuration()` real.
  - Markers de layer em precomp remapeados ao pai (`t' = st_p + t/sp`, `dur' = dur/sp`) — verificado.
  - Markers de sequência do PR usam `rfps`; take de sub-seq com rampa: lido + aviso; sub-clips
    ganham `label_rgb`; `_aviso_subseq` quando a seq nomeada falta no `.prproj`; `frameHold` NaN →
    aviso "não convertido"; `mDuration`→`dur_f`; cor `Flash Cue Point`→Orange; `AddMarker` False→aviso;
    AE stretch=0+TimeRemap avisa.

**Efeitos OFX — IMPLEMENTADO e provado no Resolve (roundtrip real)**: cada efeito é um
**grupo-50** dentro do `EffectFiltersBA` (um por efeito; f7 = slot na pilha 24,48,50..., f8 =
timestamp qualquer). Dentro: campo-9 = `{1:v 109, 2:v 0, 3:b{2:b{1:v 5195353, 2:b pluginid,
3:b 'OfxImageEffectContextFilter', 4:v 1, 5:b×N params}}, 4:b{descritor curto}, 9:v 0}`.
Plugin-id = `com.blackmagicdesign.resolvefx.<nome minusculo sem espaço>` — **mas há
irregulares** (`sharpenedgeplugin`, `softsharpenskin`), então `normalizer._FX_OFx` só tem
ids VERIFICADOS por roundtrip (20 colhidos). Param = `{1:b nome, 2:b{tipo:val}}`: tipo 1=varint,
2=double, 3=varint(bool), 5=string — real: `HStrength → {2:d 0.736}` (roundtripu com 0.92).
Encoder: `drtlib.efx_add_fx`/`fx_list`; reader AE enumera `ADBE Effect Parade` (desligado=pula).
Paste real: `['Gaussian Blur','Box Blur']` aparecem no Inspector via `GetEffects('ofx')`.
**Params por plugin**: mecanismo pronto (`spec['fx'][].params`), mas nomes/escalas por plugin
só saem com pares reais PR↔Resolve (PR Blurriness em px ≠ escala do HStrength) — por isso
efeitos vão com **defaults + aviso**; mapear param-a-param é trabalho incremental de dados.

**Rodada de dupla revisão SWE2MAX — aplicada**: (a) `move_titulos` não toca mais itens
sem-mídia ANTIGOS no append — pareamento por Start exato de inserção (`_ins`); (b) sanity check
antes de `DeleteTimelines` (reimport com itens a menos → original preservada + sandbox); (c)
`SetProperty` falho vira aviso e a chave não vai pro patch (evitava KeyError no `efx_inject`);
(d) `fim_tl` usa `c['_rm']['dur']` — freeze/rampa não subestimam mais a zona de títulos;
(e) markers de sequência dedupe por `customData='a2r'` (não duplicam no re-paste);
(f) `f7` do grupo-50 = `max(f7s)+2` (nunca colide com grupos existentes); (g) `int` negativo em
param cai pra double (evitava loop infinito no varint); (h) fallback `</Sm2TiVideoClip>` sem `>`
duplicado + tag criada na posição canônica; (i) efeitos em itens pulados (ajuste/sem-mídia/título)
viram aviso explícito; (j) cache `Prproj.aberto` por (path,size,mtime) — de 6+ parses pra 1;
(k) 'ajust' cobre Camada de Ajuste PT-BR; (l) try-per-effect no AE reader.
**Schema de params OFX colhido** (`tests/fx_params.json`, 19 plugins): `Fusion.AddTool(
'ofx.com.blackmagicdesign.resolvefx.<CamelCase>')` → `GetInputList()` → `{INPS_ID → nome, default}`.
Próximo passo natural: tabela `PR param → OFX param` por plugin + leitura de valores no reader.

**Transicoes e fades (API nativa, verificado)**: `TimelineItem.AddTransition({type, category:'simple',
position, alignment:'center', duration})` cria transicoes REAIS pos-reimport — nao depende mais de
blob DRT capturado. Nomes verificados (os que retornam item): Cross Dissolve, Dip To Color Dissolve,
Additive/Non-Additive Dissolve, Smooth Cut, Cross/Oval/Diamond Iris, Push, Slide, Split, Edge Wipe,
Clock Wipe, Band Wipe, Radial Wipe, Center Wipe, Barn Door, Blur Dissolve. Mapeamento `_PRETTY` usa
esses nomes ('Wipe'→'Edge Wipe', 'Morph Cut'→'Smooth Cut', 'Dip to Black/White'→'Dip To Color
Dissolve' — branco sai preto: API nao expoe a cor, avisa). **Fades de ponta solta**: transicao com
clipe de um lado so virava aviso — agora `lado:'start'|'end'` e vai `AddTransition` na borda (video)
ou `SetFades({FadeIn/FadeOut})` (audio). Audio ENTRE clipes continua no blob DRT (crossfade nativo
ja funcionava). Itens-transicao sao filtrados por `TransitionType` nos mapas pos-import.
**Params de efeito — primeira leva verificada**: leitores (PR `comp.properties` + AE Effect Parade)
emitem `{nome, params:{curto:{v,anim}}}`; `_FX_PARAMS` converte so unidades provadas via schema
OFX colhido (ranges `INPN_Min/MaxAllowed`): DirectionalBlur `BlurAngle`←Direction(deg), DropShadow
angle/Opacity%/Softness%/ShadowColorRGB/ShadowOnly, Transform rotate/scaleX/scaleY/zoom(%→fator),
MosaicBlur PixelFrequency←Horizontal Blocks. Pixel-strength (Blurriness px → HStrength 0..1) NAO
entra — sem escala honesta, vira aviso "param(s) sem conversao". Animados vao estaticos + aviso.

**Mapa de efeitos expandido (60 nomes → ids verificados)**: `_FX_OFx` cobre o painel do
Premiere inteiro onde existe equivalente real no Resolve FX — blurs/sharpen (11), cor
(splittone/invert/gamutlimiter/vignette/deband/dehaze), distorção (lensdistortion/mirror/dent/
vortex/waviness/ripple), keying (ofxhslkeyer/ofxlumakeyer/ofx3dkeyer), ruído/grão, transform
(transform/basic3d/3drotate/crop/camerashake/wiggle/pip), stylize/time (edgedetect/emboss/
stopmotion/motiontrails/glow/dropshadow). **59/60 validados no registro Fusion**
(`ofx.com.blackmagicdesign.resolvefx.*`); `fastnoise` é tool Fusion nativa — id veio de export
real. Sem equivalente (ficam aviso): Channel/Compound Blur, ASC CDL, B&W, Brightness&Contrast,
Color Mixer/Pass/Replace, Gamma, Hue/Sat, Levels, Lumetri, ProcAmp, Corner Pin, Magnify,
Turbulent Displace, Warp Stabilizer, gradientes/fill, Logo Cutout, Track Matte Key, Auto Reframe,
Grow/Shrink/Move/Offset/Spin/Spacer/Motion Tile. **Params novos** (unidade provada): transform
ganha Swivel/Tilt→yaw/pitch + crop LRTB→cropLRTB; splittone Amount→strength + cores→hue/sat
(cor2hue/cor2sat); vignette Feather→softness; vortex Angle→angle; mirror ReflectionAngle→angle1
(deg180 wrap); emboss Direction→angle; dirblur Shutter Angle; lumakeyer Invert.

**Pendente**: instalador Mac — estático OK (paths CEP `~/Library/Application Support/Adobe/CEP/extensions`, scripts
`.../DaVinci Resolve/Fusion/Scripts/Edit`, plist `defaults write com.adobe.CSXS.N PlayerDebugMode 1`,
Gatekeeper contornado no LEIA-ME-MAC) — só falta hardware Mac pra validar; transições além de
Dissolve/crossfade (sem material de prova); semântica do `0x08` (sessão Resolve caiu no meio do probe);
mapeamento de params de efeitos (nomes/escalas OFX por plugin — ver acima).

---


## ESTADO f10 — ease do Inspector IMPLEMENTADO (17/11/2026) — roundtrip provado 0.3px

Key record do Inspector (f10): 16 bytes = frame(i32LE) + flags(4B) + valor(f64). Cabeçalho = -16*n (i32BE).

### IMPLEMENTAÇÃO (verificada: AE Bezier real -> Resolve -> re-export -> 0.27/0.30 px)

- `drtlib`: `FLAGS=0x0c` linear; `FLAG_EASE=0x0d` marca key com tangente. `keys_encode` aceita
  `(frame, valor)`, `(frame, flags, valor)` e `(frame, FLAG_EASE, valor, (s_in, s_out))` — com o 4º
  elemento emite a key `0d` + 3 companions (in, out, reserva=0). `keys_decode` devolve todos os
  registros com flags intactas.
- `normalizer`: representação de ponto passou a aceitar 4 elementos `[t, v, s_in, s_out]`.
  `_melhor(keys, samples, tol, fps)`: linear intacto → **ajuste Hermite least-squares por segmento**
  (`_tangentes`) + **subdivisão adaptativa** (`_adaptativo`, cap 32) → samples densos (fallback).
  Aplicado nos mesmos canais de antes (Pan/Tilt/Zoom/Rot/Opacity/crops/volume AE+PR).
- `gen`: pontos tagged viram `(frame, FLAG_EASE, v/div, (s_in/div, s_out/div))` — S escala com o
  mesmo divisor do valor (S tem unidade de valor, não de slope).
- **PROVA**: comp "Comp 1" do AE (Position Bezier espacial de verdade) → Pan 27 keys / Tilt 17 keys
  (mix eased+linear) → paste `Comp 1 5` → DRT re-exportado → curva Hermite reconstruída do blob
  bate as amostras do AE com **desvio máx 0.27px (Pan) / 0.30px (Tilt)**. Keys ficam EDITÁVEIS no
  Inspector (flags `0d` + companions sobrevivem ao roundtrip do Resolve).

### Armadilhas resolvidas no caminho

- **Grades de tempo por canal**: juntar os tempos de Pan e Tilt quebrava a curva (Pan herdava
  tempos auxiliares do Tilt e interpolava linear → 74px). Cada canal emite no seu próprio grid.
- **Colisão sub-quadro** (bug real): duas chaves (ex.: auxiliar ~19.5f + original ~20.4f) caem no
  mesmo frame do blob — o Resolve fica só com a última e a tangente da outra se perde (10–90px).
  Correção em 3 camadas no `normalizer`: `_dedupe` funde chaves com `round(t·fps)` igual ANTES do
  ajuste (critério idêntico ao do blob) **e snapa a chave sobrevivente ao quadro inteiro com o
  valor real da amostra naquele quadro** — sem isso a chave deslocada carregava o valor do tempo
  original (~31px de erro em queda brusca). `_adaptativo` só insere chaves em quadros inteiros
  livres (o blob quantiza pra lá — o ajuste agora otimiza a curva que o Resolve realmente vê);
  segmentos sem quadro livre são "bloqueados" e o ajuste segue no segundo pior desvio (desvio
  sub-quadro é irredutível). Rede de segurança residual em `convert_channels` (merge simples).
- **Formato do companion**: campo frame ignorado; valor = desvio vertical S da alça vs a posição
  linear (alça X ~¼ do segmento). `m_in = m_lin − 4·S_in/dt`, `m_out = m_lin + 4·S_out/dt`
  (slopes em valor/segundo). Companions devem seguir CADA key `0d` — senão a key "come" o registro
  da próxima como tangente.

### O modelo (provado por injeção + still measurement)

### O modelo (provado por injeção + still measurement)

- **Enum válido das flags (byte 2)**: `08, 0c, 0d, 0e, 0f` — todo o resto rejeita o DRT inteiro.
  `0e/0f` importam mas o Resolve COME a key no re-export (inválidas na prática). `08` importa e
  preserva, mas o clipe resultante não renderiza still (semântica desconhecida — suspeita: hold/outro modo).
- `0x0c` = **LINEAR** — medido: barra [295,495,695] em f10/30/50 (Pan 0→0.3125 em 60f).
- **`0x0d` = KEY COM TANGENTE (ease editável!)**: a key flagged consome os registros seguintes
  como dados de tangente. Layout serializado: `[key 0d][registro(s) de tangente][próxima key]`.
  O Resolve, no re-export, **sempre grava 3 registros extras por key 0d** (pad de zeros se não houver
  → blob de 5 records pra param de 2 keys). Zeros = "unset" → curva cai pra linear.
- **O companion efetivo é o 1º registro depois da key** (slots 2 e 3 não afetaram a curva em nenhum
  teste — provavelmente tangente de saída/modo, só relevante pra keys internas com segmento depois).
- **Campo frame do companion é ignorado** (testado ±30, idêntico). **O campo valor = a tangente**:
  - `S=+0.5` → curva passa DO alvo e volta (overshoot; f30=855, f50=1104 vs alvo ~895)
  - `S=-0.3` → curva atrasa e chega por baixo (undershoot; f50=449)
  - `S=+0.1` → quase linear levemente adiantado; `S=2.0` → barra sai da tela
  - Sinal parece **invertido** vs a inclinação de chegada (S>0 chega de cima descendo).
  - **Unidade não calibrada** — chute: dv/dt por segundo (linear=0.13/s, S=0.5 ≈ 3.8× isso).
- **Armadilha**: `0d` na key0 sem companions a seguir = a key COME o record da próxima key como
  tangente → animação morre (medido congelado). Companions devem seguir CADA key flagged.

### Medição sem GPU (método que funciona)

Render jobs H.264/NVENC **travam o Resolve** (job zumbi → `IsRenderingInProgress` eterno → só restart).
O caminho barato e estável: `p.SetCurrentTimeline` → `SetCurrentTimecode` → `tl.GrabStill()` →
`album.ExportStills([still], dir, prefixo, 'jpg')` → cv2 mede a borda da barra branca.
**Detalhe crucial**: usar o objeto still RETORNADO pelo GrabStill — `GetStills()[-1]` pega still
velho e corrompe a medida. Ainda assim o subsistema de still **morre após ~80 grabs** na sessão
(retorna None pra sempre — pede restart).

### MODELO FINAL (calibrado, provado por medida de curva)

Flag `0x0d` numa key → a key consome **3 registros companions** logo após ela:
`[key 0d][comp_in][comp_out][comp_reserva][próxima key]`. Zeros = unset → linear.
- **comp_in = tangente de CHEGADA** (afeta segmento à esquerda), **comp_out = SAÍDA** (segmento à direita), slot3 inerte.
- Campo frame do companion é ignorado; **valor S = desvio vertical da alça Bezier vs a posição linear**
  (a alça X fica fixa a ~¼ do segmento). Fórmulas calibradas (slopes em valor/SEGUNDO, dt = duração do segmento em segundos):
  - `m_in  = m_lin − 4·S_in /dt`   → `S_in  = (m_lin − m_in )·dt/4`
  - `m_out = m_lin + 4·S_out/dt`   → `S_out = (m_out − m_lin)·dt/4`
  - `m_lin` = Δv/Δt do segmento que a tangente encara.
- Ease-in Adobe (chegada plana, m_in=0) → `S_in = dv/4`. Ease-out (m_out=0) → `S_out = −dv/4`.
  S>0 em in = chega "por cima" (overshoot); S<0 = chega por baixo/acelera no fim.
- Verificado com dv e dt variados (inclui overshoot previsto quando S > dv/4).

### Revisão secundária (SWE2MAX) — achados aplicados

- **`ho` com `/s` residual** (bug real, pré-existente ao f10): no caminho não-append com speed≠100 e
  clipe aparado (src_in>0), `head_offset()` dividia por `s`, mas o patch timemap usa `rec0=src0`
  igual ao append — chaves deslocavam `src0·fe·(1−1/s)` quadros. `head_offset` removido; agora
  `ho = src0·fe` sempre (remap e não-remap, qualquer velocidade).
- `_adaptativo` em `maxpts` agora devolve `None` (fallback denso é estritamente melhor que fit
  aberto); antes podia devolver tagged pior que samples.
- `_dedupe` roda também sem samples (merge sem snap).
- **Crops do Premiere**: o leitor não passava `tms` → samples nunca existiam → ease de crop caía
  linear silencioso. Agora passa `tms` (mesma amostragem das outras props). Crops/`vol_ks`/`ks_a`
  também passaram a receber o filtro de faixa + dedupe de quadro (`_apara_chaves`/`_dedup_frames`)
  — antes escapavam por entrarem depois de `convert_channels`.
- Guards em `keys_encode`: 4-elem exige `FLAG_EASE`; 3-elem com `FLAG_EASE` é rejeitado
  (impediria a key de "comer" os registros seguintes por engano).
- Flags dos companions confirmadas empiricamente: `00000c00` no re-export real do Resolve.
- Código morto removido (no-op ZoomGang em gen.py).

### Regressão Premiere (verificada)

- Fixture `TESTE_A2R.prproj`: keys lineares preservadas (o _melhor detecta linear e mantém as keys
  originais — correto).
- Caminho eased forjado (keys+samples smoothstep no clipboard): `chan`→`_melhor` emitiu tagged →
  paste `TESTE_A2R 11` → blob com 2 keys `0d` + companions por canal → **curva re-exportada =
  smoothstep exata (dev 0.00000)**. Os S vieram `∓dv/4` como previsto (tangentes zero nas pontas).
- **Ease real feito à mão no Premiere** (Position/Scale/Rotation com velocity curves no Effect
  Controls): 7/6/10/2 keys `0d` por canal → blob re-exportado bate as amostras PR com
  **dev 0.25px (Pan), 0.15px (Tilt), 0.06° (Rotation), 0.000 (ZoomX)** — prova final do caminho PR.

### O que ainda falta no f10

1. O que é `0x08` (importa/preserva mas clip não renderiza still — hold? tipo especial?). Sem uso no pipeline.
2. Conferência visual da curva eased no Resolve (stills) — a prova numérica já fechou; opcional.


## ESTADO 0.1.4 (17/11/2026) — destino da timeline + config nativa da origem
**Feito e verificado nesta rodada** (DaVinci aberto, paste real AE e Premiere):
- **Timeline nova herda EXATAMENTE a origem** (bug do usuário: seq/comp 1080x1920 caía numa timeline 4K aberta). O `spec` agora carrega `fps/width/height` da sequência/comp (`normalizer`); `bridge.paste` usa a origem como referência de escala (não mais a timeline aberta); `gen.build` aplica na temporária `SetSetting('useCustomSettings','1')` + `timelineResolutionWidth/Height` + `timelineFrameRate` ANTES dos appends. Provado: comp AE 1080x1920@29.97 → timeline "…Vertical 3" 1080x1920@29.97.
- **Seletor de destino no painel** (`index.html` `<select id="selDestino">`, `main.js` grava `d.destino` no clipboard): `Nova timeline` (padrão, comportamento antigo) / `Timeline de mesmo nome`.
- **Modo "Timeline de mesmo nome"** (`spec['destino']=='existente'`): `gen.build` localiza a timeline por `spec['name']`; se não acha, avisa e cai no fluxo novo. Se acha: **deleta colisões** por (trilha, intervalo record) com `DeleteClips`, cria trilhas que faltam, `AppendToTimeline` no `recordFrame` exato, **sem ripple** — velocidade/remap entram pelo patch DRT (`<Duration>`+timemap de 2 pontos, mesmo caminho do áudio). Exporta a timeline inteira, patcha SÓ os itens novos (`por_start`), reimporta, `DeleteTimelines` na original, renomeia e move pro bin dela (`_folder_de` acha a pasta pelo UniqueId do MediaPoolItem). Os itens antigos passam intactos pelo roundtrip (patch=None). Props escaladas pra res DA TIMELINE EXISTENTE (aviso de escala quando difere).
- **Bug achado no teste**: `_rec_dur` derivado do `d0` appended (janela clampada) dava duration errada em take acelerado (526% → 5 em vez de 26) — agora vem da janela de mídia real `(src_out-src_in)*tl_fps/media_fps/speed`. Também: append sem SetSpeed precisa entrar com janela ≤ footprint (clamps em ini/fim) senão sobrepõe vizinhos antigos e `AppendToTimeline` falha.
- **Verificado**: append AE (3 takes substituídos na mesma timeline 4K, nome preservado, V2 526% dur=26 com timemap retimado), subset de 1 take preservando os outros 5 itens, fallback "não existe → cria nova em 1080x1920", append Premiere com rampa `mode=2` intacta. `tests/test_painel.js` ganhou `A2R_DESTINO` pra exercitar o seletor.
- **Revisão externa aplicada** (subagente; 3 altas + 4 médias/baixas corrigidas e re-verificadas no Resolve):
  - `starts != ordem` crashava o append quando a timeline alvo tinha itens em trilhas ACIMA das copiadas ou itens sem mídia real (geradores/títulos): agora `_itens_xml` varre `GetTrackCount` filtrando só quem tem `File Path`; o check de áudio é pulado quando `aclips` vazio. Provado: append com V4/A5 extras na timeline passou e os itens sobreviveram intactos.
  - **Atomicidade**: deletes/appends do modo existente rodavam na timeline ORIGINAL — qualquer erro a deixava corrompida. Agora o trabalho roda num `DuplicateTimeline` sandbox; a original só morre depois do reimport ok. Provado: falha por mídia inexistente deixou a original intacta (sandbox `_tmp_` órfão descartado).
  - `head_offset` no append+speed≠100 usava a convenção `/s` do SetSpeed, mas o timemap entra com `rec0=src0` — keys de clipe acelerado e aparado deslocavam (mesmo bug do áudio na 0.1.3, agora no vídeo).
  - `_midia` em append só procurava na raiz → duplicava mídia que vive em bins; agora `recursivo=True` varre as pastas, e imports novos caem no bin da timeline (`SetCurrentFolder(pasta_alvo)`).
  - `_uid_de` ambíguo (mesmo `<Start>` em trilhas diferentes) agora devolve `None` → uuid novo; regex `<In\s*/>` cobre a variante com espaço; `DeleteTimelines` da original tem retorno checado.
  - Painel: `grava()` pós-reamostragem não rodava quando `feitos==0` → o remap se perdia em silêncio (agora grava por `remapados`); `selDestino` com guard de nulo e desabilitado durante a ação.
- **NOTA**: em um dos testes as timelines criadas no dia "sumiram" — foi o usuário apagando manualmente, não o código (nada no fluxo novo deleta timelines além da `_tmp_` de trabalho).

## ESTADO 0.1.3+ (17/11/2026) — fidelidade da rampa eased corrigida + reverso + validações
**Feito e verificado nesta rodada** (DaVinci Studio 21.2.0.6 aberto):
- **FIDELIDADE DA RAMPA EASED — bug real encontrado e corrigido**: a conversão direta influência→handle divergia da curva real do Premiere em até **60 quadros** (medido comparando o mapa eased vs a amostragem densa do mesmo take Cesmac). Causa: o modelo eased do Resolve é "canto suavizado" (cúbica com controles EM P), e entre nós esparsos a curva real pode subir e voltar DENTRO do segmento — nó esparso não representa. Correção em `gen._timemap_mapa`: loop de refino que avalia `L.timemap_eval` (port do `sourceSecAt` do drp-format) contra a amostragem real `rm['points']`; onde o desvio passa de 0.5 quadro de mídia, o ease recua (se o desvio cai dentro da janela eased de um nó) ou entra um **ponto auxiliar linear** na posição exata. Resultado medido: **60.7 → 0.48 quadros** de desvio máximo; paste real ficou `mode=2`, 36 pontos, 4 com alças (editável e fiel).
- **Reverso provado no formato**: timemap com src decrescente (`MediaTimemapBA` 2 pontos, rec crescente) importa e re-exporta intacto no Resolve 21.2 — timeline `_probe_reverso` no projeto pra conferência visual. O vendor documenta também a forma "oficial" do reverso (campo 2 = origem src ≠ 0, campo 160=9) e o mapa de **freeze** (`YMin=YMax=freezeSec`, `XMax=60000` sentinel, `<In>` vazio) — decifrados, ainda não ligados ao pipeline.
- **AE eased validado em paste real**: camada com Time Remap saiu `mode=2`, 31 pts, 4 eased — e o áudio linkado com o mesmo mapa (timeline "…Vertical 2" no bin "teste").
- **Volume animado do Premiere já estava implementado**: `premiere_read.jsx` lê `Level`/`Pan` com keys+samples via `readProp`; `normalizer` gera `vol_keys` (incl. reamostragem pela curva `m(d)` quando o clipe tem rampa) — verificado lendo o código, falta só conferência visual de um fade animado real.
- **`drtlib.timemap_eval`**: avaliador oficial do modelo de timemap (cúbica corner + cordas), usado pelo refino e pelos testes.

**FALTA (pendências reais)**:
1. **Eases em keyframes de Inspector** (`f10`, 16B/chave: `tempo i32 | flags 4B | valor double`) — o campo flags é sempre `00000c00` nos nossos exports; precisa de um DRT com keyframe eased feito à mão no Resolve pra decifrar. `f3` = valor estático, `f10` = lista de chaves (coexistem; f3 fica com o 1º valor).
2. Congelar (formato já decifrado, falta ligar) e reverso na UI do painel (formato provado, falta spec/leitor).
3. Conferência visual: rampa eased vs Premiere lado a lado; `_probe_reverso` tocando ao contrário.

## ESTADO 0.1.3 (16/11/2026, noite) — ÁUDIO implementado + rampa EASED (editável) — testado no Resolve real
**Feito e verificado nesta rodada** (DaVinci Studio 21.2.0.6 aberto, paste real do Premiere Cesmac):
- **Áudio completo na ponte** (Premiere e After): `premiere_read.jsx` lê `q.audioTracks[t].clips` (posição, mediaPath, mediaFps, speed via QE, props `Level` dB e `Pan` dos componentes Volume/Panner; seleção acompanha linked selection). `ae_read.jsx` lê `l.hasAudio`/`audioEnabled` + `ADBE Audio Levels` (dB, keys+samples); camada só-áudio vira item de áudio. `normalizer` emite `spec['audio_clips']` (media, src_in/out em quadros de mídia, rec_start/rec_dur em quadros de timeline, track de áudio, volume_db, vol_keys em dB, pan, speed, remap herdado do vídeo ligado por mídia+posição ±2q). `gen.build` cria trilhas de áudio, anexa com `mediaType: 2` e aplica `SetProperty('AudioVolume', dB)` / `SetProperty('AudioPan', v)` / `SetFades({FadeIn, FadeOut})` — **API nativa, sem injeção**.
- **Formato de áudio do DRT decifrado** (`src/probe_audio.py`): `Sm2TiAudioClip` usa o MESMO `<In>` codificado (`59|<double fracao>`; vazio só quando 0) e o MESMO `MediaTimemapBA` do vídeo. `EffectFiltersBA` de áudio = grupo **124**: param **95 = AudioVolume (dB)**, **97 = FadeIn**, **98 = FadeOut** (param 96 = Pan, presumido) — mesma curva `f3{f1{f2}}` e mesmas chaves `f10` das props de vídeo. `SetSpeed` em áudio NÃO muda duração (ao contrário do vídeo): velocidade de áudio entra por patch de `<Duration>`+timemap de 2 pontos.
- **Timemap EASED (rampa editável no Inspector)**: `drtlib.timemap_encode_eased` — forma nativa do Studio 21 (`Mode=2`, sem YMin, `KeyframesBA=0x81+zstd(protobuf)`, origem `f1{}` vazia, pontos `{09 rec, 11 src, 1a alças}`; alças = 6 doubles LE `[inRec,inSrc,outRec,outSrc,0,0]` relativos ao ponto; a janela `P+in..P+out` vira cúbica com controles internos EM P, tangente = corda vizinha — modelo validado por render no `drp-format` do resolve-advanced). Nós Premiere (`knots` do prproj, influência% → fração do segmento vizinho) e AE (`remapKeys` = `keyIn/OutTemporalEase().influence`) viram `remap['nodes']` no spec; `gen._timemap_mapa` escolhe eased quando há nós, denso sem eles.
- **Paste real do Premiere validado**: rampa do Cesmac chegou `mode=2` com **5 pontos com alças** (editável) no vídeo E no áudio ligado — antes eram ~60 pontos densos. Áudio veio na trilha certa com volume do Premiere (0,178 dB). Chaves `f10` de volume animado injetadas em `(124,95)` e RE-exportadas pelo Resolve = aceitas nativamente.
- **Bug do painel corrigido**: o `grava()` pós-reamostragem reescrevia o `clipboard.json` com o objeto `d` em memória (sem `remap_nodes`) por cima do enriquecido pelo `remap-info` — agora `remap-info` devolve `knots`/`absoluto` e o painel anexa `c2.remap_nodes` antes de gravar. Painéis reinstalados.
- **Revisão externa aplicada** (subagente; 1 alta + 4 médias corrigidas e re-verificadas): nós de remap antes do take quebravam a ordem do timemap eased (`_timemap_mapa` agora filtra `rc<rec0`, ordena e deduplica; nó que cola na origem conserva o ease); `anySel` do leitor só varria vídeo (selecionar só áudio copiava tudo — agora varre `audioTracks`, e painel/`nb_resumo` contam áudio); `vol_keys` vazio → IndexError (`if vk:`); `ho` das vol_keys alinhado à convenção `rec0=src0` do timemap (era `÷speed`, podia deslocar chaves em áudio acelerado); link áudio↔vídeo exige mesmo `src_in` ±2q (evita herdar curva de take errado); len do campo `0x1a` virou varint; `_total` clampado ≥1; `qc.type=="Clip"` no loop QE de áudio.

**FALTA (pendências reais)**:
1. **Achatar acidental**: tocar no retime do clipe na UI (Retime Controls, selo de %, "Legacy Speed Mode") faz o Resolve REESCREVER o mapa com alças zeradas — o ease morre de verdade (mapa re-exportado sai linear). Provado: build API-only re-exporta `mode=2` com alças intactas (timeline `_TESTE_eased_video`); clipe tocado na UI volta `mode=None`+alças 0. O áudio do mesmo take fica intacto (ninguém abre retime de áudio). Comportamento do Resolve, não bug — documentar pro usuário: conferir a curva sem tocar a barra.
   - Falta conferir se a curva eased aproxima bem a rampa original (a tangente usada é a corda do segmento, não o Bézier exato do Premiere).
2. Keyframes de volume no paste real (só testado em spec sintético: 4 chaves `f10` em `(124,95)` aceitas e re-exportadas).
3. Eases em keyframes de Inspector (Position/etc.) — formato das flags `f10` não decifrado; segue amostragem densa.
4. Reverso/congelar; curvas espaciais de Position; teste do instalador em Mac real.
5. `probe_audio.py` é ferramenta de investigação (pode virar teste permanente ou sair do release).

## ESTADO 0.1.2 (16/11/2026, noite) — bilíngue implementado; painéis reinstalados; release reconstruído
**Feito e verificado nesta rodada**:
- **Bilíngue PT/EN por idioma do sistema** (pedido do Eduardo, "detectado pelo idioma do sistema"): `main.js` lê `navigator.language` e exporta `A2R_LANG` para os subprocessos Python; leitores `.jsx` recebem `var __LANG` injetado no início do código avaliado (painel e `bridge.run_premiere`); `src/i18n.py` (novo) centraliza `T(pt,en)`/`LANG()` com fallback `A2R_LANG` → `locale.getlocale()` → pt; `install.py` importa o mesmo `i18n`; `.bat` lê `(Get-UICulture).TwoLetterISOLanguageName`, `.command` lê `defaults read -g AppleLocale`; LEIA-MEs ganharam seção inglesa; `traduz()` do painel casa as mensagens nos dois idiomas. **Linhas de protocolo (`bin "x" > sub-bin "y"`, `pronto: timeline ...`) ficam em PT fixo — o painel faz parse delas.** `tests/test_painel.js` agora embrulha o script com `return eval(...)` (imita o valor da última expressão do evalScript do CEP — aceita `var __LANG=...; nb_run(...)`).
- **Ponte `prmcp` diagnosticada e confirmada**: o canal morreu com o contexto ExtendScript do painel PR MCP Bridge (até `1+1` falhava com "EvalScript error") — NÃO era o Premiere fechado (o painel A2R seguia lendo a sequência via `nb_run` próprio). Restart do Premiere reviveu: `return 1+1` → 2 e a sequência Cesmac leu pelo CLI. IMPORTANTE: `prmcp_run` envolve o código em `(function(){...})()` — código precisa de `return` explícito para devolver dado (`1+1` → `null`).
- **Painéis reinstalados** com a build bilíngue; **release 0.1.2 reconstruído** (42 entradas, `src/i18n.py` nas duas pastas, `.command` 755, `install.py` do zip compila; SHA: `0f1130fba36350aa6bad85f03dda8f7bfd536653b695fc848dc20c2abfb8722e`).
- Verificações: `py_compile` em todo `.py`, `node --check` em `main.js` e leitores (via cópia `.js` — node não checa `.jsx`), `bash -n` nos `.command`, teste do painel PPRO (Premiere fechado → cartão de erro PT + zip de debug gerado, caminho correto), `i18n` responde `en`/`pt` conforme `A2R_LANG`.

**FALTA (pendências reais)**:
1. **Teste real no DaVinci** — Resolve fechado na hora; enviar a sequência Cesmac com a rampa e conferir chegada (timemap, quadros, ripple).
2. **Áudio (PR + AE: faixas, volume, fades)** — NÃO implementado; depende de DaVinci aberto para decifrar o formato DRT de áudio.
3. Curvas espaciais do Position e alças Bezier editáveis no Resolve (mesmo estado anterior).
4. Reverso/congelar; teste do instalador em Mac real.

## ESTADO 0.1.2 (16/11/2026, fim do dia) — implementado e testado em unidade; falta teste real no DaVinci
**Feito e verificado nesta rodada**:
- **Release multiplataforma**: `release\v0.1.2\A2R-Link_0.1.2.zip` (88 KB, SHA em `SHA256SUMS.txt`) com `A2R Link 0.1.2\Windows\` e `...\Mac\` lado a lado, cada uma autocontida (INSTALAR+DESINSTALAR+LEIA-ME+install.py+fontes). `.command` com bit 755; `install.py` ramifica Windows/macOS (PlayerDebugMode via `defaults write` no Mac; dados em `~/Library/Application Support/NoeVFX`; Resolve em `/Library/Application Support/Blackmagic Design/...`). `bridge.py`, `gen.py` e `resolve/A2R Link - Colar.py` portáteis (sem `APPDATA`/`winreg`/`creationflags` fixos). Branch Mac verificado por simulação com monkeypatch de `sys.platform`.
- **Relatório de debug**: qualquer erro no painel gera `A2R-debug-AAAAMMDD-HHMMSS.zip` na pasta de dados (ambiente, versão, log, `clipboard.json`, `config.json`, `LEIA-ME.txt`). O cartão vermelho mostra "Relatório para o suporte" — um clique abre Explorer/Finder com o arquivo selecionado (regenera na hora, nunca revela zip velho). Zip próprio escrito à mão em ES3-compatible JS (deflate via `CEFPython`/`window.cep.fs`? não — implementação STORE/deflate manual com CRC-32; validado `testzip: None`). Testado de ponta a ponta no painel instalado.
- **Speed ramp do Premiere COMPLETO**: `src/prproj.py` lê `TimeRemapping` do `.prproj` gzip só dos takes copiados (índice de ObjectID/ObjectUID + fatias, sem DOM). Domínios resolvidos: os nós da curva `Speed` são em **tempo do clipe** (0 = início do take), `InPoint/OutPoint` são em **tempo de mídia**; `_amostra` desloca a avaliação conforme o domínio detectado (heurística: nós clip-local sempre nascem em ~0). Regressões: clipe em zero, deslocado (20.42s), aparado no meio da curva (21.9s de mídia em 7.74s de timeline), nós absolutos.
- **2ª passada de amostragem**: `remap-info` (bridge) + `src/readers/premiere_resample.jsx` — quando o `paste`/`copy` detecta rampa no `.prproj`, o painel re-lê Motion/Opacidade chamando `getValueAtTime` nos tempos de mídia exatos da curva (antes: janela constante → props travadas cedo). `normalizer` ganhou defaults para props ausentes e `m_curve` em tempo absoluto (bug do `+start` duplo corrigido).
- **Interface**: cabeçalho `flex-wrap` (pílula desce em vez de espremer o título), `#resultado` com `max-height` + rolagem interna.

**Revisão externa aplicada** (subagente revisor achou; todos corrigidos e re-verificados):
- `install.py` Mac: `RESOLVE_SCRIPTS` tinha `Support` a mais (só Windows tem) — script ficaria fora da varredura do Resolve.
- `build_release.py`: `create_system=3` agora (sem isso o bit 755 do `.command` se perdia na extração no Mac).
- Leitores: `displayName`→`matchName`+sufixo `.Nome`+inglês (Premiere localizado perdia tudo); `avisoLeitura` quando o Motion não identifica; efeitos vão pelo nome interno (flip casa por regex no normalizer).
- `main.js`: guard `feito` contra `error`+`close` duplo (Enviar colava 2x), `p.on('error')` em `checaDavinci`/`revelar`, `c2.remap` sempre atribuído, `tms` afinado a ~3000 para a reamostragem (curva cheia em `tms_full`), `traduz` distingue erro do AE, `os.userInfo` protegido.
- `prproj.py`: nós agora carregam `(t, v, tipo, infIn, velIn, infOut, velOut)`; avaliação = Bézier cúbico por segmento — tangente PCHIP × alça `influência%` (tipo 8/junção sem % → ⅓, tipo 6 → 0); alças cruzadas encolhem; heurística de domínio endurecida (`xs[0]>0.5 E xs[-1]>dur`); entidades XML unescape; regexes `ObjectU?Ref`; tolerância de casamento 0,004s (¼ quadro a 60fps); `influencias` reportado para diagnóstico.
- `normalizer.py`: `value:None`→default, aviso quando keys ficam estáticas sob remap, chaves fora do trim cortadas ([0,dur] com aviso), `_uri2path` na mídia, aviso para efeito não convertido.
- `gen.py`: nome de timeline saneado (`[\\/:*?"<>|]`), item sem par de injeção vira AVISO.
- Velocidades dos nós do .prproj (`velIn/velOut`) NÃO decodificam como dv/dt em unidades óbvias (~0 em pontos de rampa alta) — não usadas; decifrar exige sessão com Premiere aberto comparando curva renderizada.
- Veredito do revisor sobre domínios: cadeia consistente de ponta a ponta, sem shift sistemático; riscos residuais = forma da curva entre nós (melhorado com influências), casamento de take (apertado), heurística de domínio (endurecida), TC de sequência ≠0 (clip.start é relativo à sequência — não-issue confirmado por análise).
- O que NÃO se confirmou/executável: ripple do `SetSpeed` entre trilhas e `por_start` — marcado para o teste real no DaVinci.

**FALTA (pendências reais)**:
1. **Teste real no DaVinci** — Resolve estava fechado; não foi possível validar a chegada da rampa/curvas renderizadas. Requer: DaVinci aberto + `External scripting = Local`, enviar a sequência Cesmac com rampa, comparar quadros.
2. **Áudio (PR + AE: faixas, volume, fades)** — NÃO implementado. ExtendScript lê (`audioTracks`/`ADBE Audio Levels`), mas falta o formato DRT de áudio (chaves de volume em `Sm2TiAudioClip`) — decifrar com DaVinci aberto.
3. **Curvas espaciais do Position** — trajetória Bezier do path ainda é aproximada pela amostragem temporal densa; não há leitura das alças espaciais do AE (`spatialTangents`) nem garantia matemática de erro ≤ tolerância no path.
4. **Curvas ease/Bezier → chaves nativas do Resolve** — hoje tudo vira chaves lineares amostradas (fieis à curva renderizada, mas sem as alças editáveis no Inspector). Flags de curva do DRT parcialmente decifradas (`00 00 0c 00` linear, `byte3=0x80` suave); alças Bezier editáveis não decifradas.
5. **Reverso** — trechos com velocidade negativa seguem avisando e ignorando.
6. Teste do `install.py`/`*.command` em Mac real.

## EM ANDAMENTO 0.1.2 (16/11/2026) — correção do painel, instalada na máquina, NÃO publicada
O painel 0.1.1 seguia sem achar a configuração. Causas encontradas: (1) `%APPDATA%\NoeVFX` simplesmente não existia na máquina
(a cópia central sumiu — motivo ainda não confirmado); (2) no CEP real `__dirname` é a raiz do painel (não a pasta `js`), então
`__dirname/../config.json` procurava `extensions\config.json` — a cópia interna nunca era achada (o teste em Node achava porque lá
`__dirname` é a pasta js de verdade). Correção: o instalador grava `js/config.js` com `window.A2R_CONFIG` embutido (o painel não precisa
ler arquivo nenhum para configurar) e a busca em arquivo virou plano B com os dois caminhos. O painel imprime `diagnostico:` nos
Detalhes na abertura (usuário, APPDATA, __dirname, quais arquivos existem).
Feito: `main.js` (config embutida + 5 caminhos + diagnostico), `index.html` (carrega `js/config.js`), `install.py` (grava `js/config.js`
e a cópia `config.json` no painel; corrigido SyntaxError na linha que gerava o config.js), `bridge.py` (`A2R_DADOS`), CHANGELOG,
`tests\test_painel.js` (carrega o `js/config.js` do painel instalado; sem PANEL_JS usa a config instalada/central).
Instalado via `install.py` (painéis + script do DaVinci + `%APPDATA%\NoeVFX\config.json` recriado). Teste `AEFT copiar` no painel
instalado sem APPDATA: passou da configuração (falhou só em "AE nao respondeu" = ponte do AE fechada, esperado).
FALTA: Eduardo reiniciar After/Premiere, abrir o painel, abrir Detalhes e mandar as linhas `diagnostico:` (revelam por que o config
central não era lido). ATENÇÃO: `release\v0.1.2\A2R-Link_0.1.2.zip` foi gerado ANTES do conserto do `install.py` e contém o arquivo
quebrado (INSTALAR.bat morre com SyntaxError) — não distribuir; regenerar ou descartar quando a 0.1.2 for confirmada.
CONFIRMADO (16/11): o painel instalado FUNCIONOU no After — enviou 3 camadas, criou a timeline no DaVinci com o aviso de escala.
Ajuste de interface feito: cabeçalho com flex-wrap (a pílula de status desce em vez de espremer o título) e `#resultado` com
max-height + rolagem própria (dados pós-envio não esticam o painel). Reinstalado via `install.py`.

## EM ANDAMENTO — speed ramp do Premiere e áudio (16/11/2026)
**Speed ramp (Time Remapping) — IMPLEMENTADO E TESTADO EM UNIDADE**. Decifrado no `Teste PR.prproj` real. O ExtendScript NÃO lê
remap — a curva mora no `.prproj` (gzip XML): `Sequence → TrackGroups → tracks → TrackItem → SubClip → Clip → TimeRemapping →
TimeComponentParam "Speed"` com `Keyframes` = `t_ticks(254016000000/s),v_seg_mídia,tipo,0,f5..f8` (tipos 6=ponta, 7=suavizado c/
influência%, 8=junção). `src/prproj.py`: varredura preguiçosa (índice de ids + fatias de texto, sem DOM inteiro: rápido em projeto
de 1h), curva Hermite monotônica (Fritsch-Carlson, C¹ → velocidade contínua, sem reverso), amostragem por quadro. `premiere_read.jsx`
devolve `sequence.path`/`dirty`. `bridge.py` ganhou `remap-info` (devolve a curva por clipe para a 2ª leitura) e o `paste` casa os
takes (faixa+início) e injeta `c['remap']`. `premiere_resample.jsx` (novo leitor) é chamado pelo painel SÓ quando há rampa e devolve
`samples2` — props reamostradas com `getValueAtTime` nos tempos de mídia exatos da curva. Aviso de salvar só se houver remap + projeto
sujo. Domínios resolvidos e regredidos: nós clip-local (deslocamento `off=t0`), `InPoint/OutPoint` em tempo de mídia, clipe aparado no
meio da curva, nós absolutos (robustez). **FALTA**: teste de chegada real no DaVinci (render/comparação de quadros) — Resolve estava fechado.
`sequence.exportAsProject()` segue como upgrade possível se o `.prproj` salvo estiver desatualizado e o usuário não quiser salvar.
**Áudio (pedido do Eduardo: TUDO com volume e fades, também no AE)**: AINDA NÃO COMEÇADO. Lado ExtendScript é direto
(`q.audioTracks` no PR; `layer.hasAudio`/`ADBE Audio Levels` no AE). No DaVinci: faixas de áudio + itens (AppendToTimeline
mediaType 2) + chaves de volume — formato DRT de áudio não decifrado (mesma rota dos params de vídeo, grupo por mapear).
Crossfades/transitions fora do escopo inicial (avisa). Áudio de clipe com rampa: o timemap talvez sirva também no item de áudio — validar.
Premiere e AE bridges e o DaVinci estavam fechados na hora do teste (`AE nao respondeu`, `DaVinci nao responde a API`).

## RELEASE 0.1.1 (16/11/2026) - correção do painel (substitui a 0.1.0 para uso)
O Eduardo testou o painel de verdade no After e no Premiere: aparecia 'A instalação está incompleta' (o painel não achava o config.json, causa exata não confirmada;
suspeita: APPDATA ausente no Node do CEP). Correção: o painel procura a configuração em 4 lugares (APPDATA, cópia dentro da pasta do painel, pasta pessoal, CEP userData),
mostra o motivo exato nos Detalhes e o indicador vira 'sem configuração'. `install.py` grava `dados` na config e uma cópia dela dentro de cada painel; `bridge.py` usa `A2R_DADOS`.
Testado: painéis INSTALADOS (Premiere e After) rodados em Node SEM a variável APPDATA (`SIM_SEM_APPDATA=1 PANEL_JS=<painel instalado> node tests\test_painel.js`): envio ok nas duas rotas.
Pacote: `release\v0.1.1\A2R-Link_0.1.1.zip` (SHA em `SHA256SUMS.txt`). A 0.1.0 fica como está (imutável). Falta o Eduardo clicar no painel de verdade de novo.

## RELEASE 0.1.0 (16/11/2026) — pacote pronto para distribuir
`release\v0.1.0\A2R-Link_0.1.0.zip` (32 KB) + `SHA256SUMS.txt`; gerado por `scripts\build_release.py` (lista fixa de arquivos de uso; testes e ferramentas de dev ficam de fora).
Verificado: instalar a partir do zip em APPDATA isolado, imports do runtime, `bridge.py status` com DaVinci aberto, desinstalar (nada sobra). Backup do código-fonte em
`_backups\v0.1.0\`. Espelho no Drive: feito (`espelhar-no-drive.ps1 -Projeto "A2R Link"`). VirusTotal e GitHub: ainda NÃO feitos (commit e push só com ordem do Eduardo; ver `D:\.IA agents\global\RELEASES.md`).
Instalador: confere Python>=3.14, Resolve e pasta Adobe; desinstalador remove painéis, script, `config.json`, `clipboard.json`, `ultimo_colar.log` (não desliga o PlayerDebugMode).

## NOME DO PRODUTO: **A2R Link** (decisão do Eduardo; sem "VFX" no nome; A2R = Adobe to Resolve)
Painel CEP (menu `Janela > Extensões > A2R Link`), script do DaVinci `A2R Link - Colar.py`. IDs internos mantidos (`com.noevfx.bridge.*`); pasta do projeto renomeada de `Noe Bridge` para `A2R Link` em 16/11/2026
(configuração atualizada rodando `install.py` de novo; nome antigo do script do DaVinci era `Noe Bridge - Colar.py`). Painel novo: indicador de conexão (`bridge.py status`), resumo da seleção (`nb_resumo`),
cartão de resultado verde/âmbar/vermelho, erros em português simples, Detalhes recolhido. `host.jsx`: `app.name` vem `undefined` no Premiere (detectar por `activeSequence`).

## ORGANIZAÇÃO NO MEDIA POOL (pedido do Eduardo, validado)
Leitores devolvem o nome do projeto (`sequence.project` no Premiere, `project` no AE); o normalizer põe `spec['bin']` = nome do projeto (sem extensão;
fallback "Premiere (sem projeto)"/"After Effects (sem projeto)") e `spec['name']` = nome da sequência/comp (sem prefixo). `gen.build`: cria/reaproveita o bin do
projeto, cria sub-bin com o nome da timeline (`Nome 2`... se já existir), importa a mídia para o sub-bin (uma vez por arquivo, sem mexer nas pastas do usuário),
cria a timeline com o nome livre no projeto e a garante dentro do sub-bin (`MoveClips`). Verificado pela árvore do Media Pool (`NoeBridgeTeste > SeqCurva > {mídia, timeline}`).

## EXTENSÕES (painéis) — estado e como foram testadas
`extensions\common` (index.html, js\main.js, jsx\host.jsx) + manifesto por programa; `install.py` copia para `%APPDATA%\Adobe\CEP\extensions\com.noevfx.bridge.{premiere,ae}`
e grava `%APPDATA%\NoeVFX\config.json` (python, bridge.py, pasta dos leitores). O painel lê o leitor `.jsx` do disco a cada clique (atualizar leitor = sem reinstalar).
Botões: Copiar (grava `clipboard.json`), Colar no DaVinci (spawn do `bridge.py paste`, mostra o log), Enviar (os dois).
TESTADO: (1) `tests\test_painel.js` roda o `main.js` REAL em Node com CEP falso ligado às pontes reais: Premiere 27 (SeqCurva) e After 27 (CompFinal, 2 camadas) →
"pronto: timeline criada no DaVinci"; quadros comparados: Premiere 0.4–8.5/255 (o maior = suavização de borda fina), After 0.08–0.48/255.
(2) logs do CEP (`%TEMP%\CEPHtmlEngine12-*com.noevfx.bridge.*.log`) mostram que o Premiere 27 e o After 27 CARREGARAM os painéis na abertura (StartOn).
(3) `resolve\A2R Link - Colar.py` rodado direto: cola e grava `ultimo_colar.log`.
NÃO VERIFICADO POR MIM (precisa do Eduardo): clicar nos botões no painel de verdade e ver o item `Workspace > Scripts > Edit > A2R Link - Colar` no DaVinci
(a captura de tela estava indisponível e o TeamViewer da sessão remota bloqueava os cliques; o acesso ao TeamViewer foi negado por ele).
O classificador de segurança do Claude Code BLOQUEOU abrir a porta de depuração (`.debug`) dos painéis; NÃO contornar. `install.py --debug` existe mas não deve ser usado.

## ESCOPO TRAVADO (decisão do Eduardo, 16/11/2026)
Só as propriedades básicas de qualquer clipe/camada: **Anchor Point, Position, Scale, Rotation, Opacity + keyframes delas** (Flip = escala negativa).
FORA do escopo, não gastar tempo: efeitos/plugins, track mattes, máscaras, parenting, expressões, câmera/3D de verdade (3D vira 2D), motion blur, texto/shape/precomp.
Time remap/speed ramp e curvas continuam só no que já está pronto e validado (After); o Time Remap do Premiere (leitura via .prproj) é opcional e só se ele pedir de novo.

Ponte "copiar no Premiere/After, colar no DaVinci Resolve Studio", com takes abertos na timeline de edição
e keyframes no Inspector (SEM Fusion, SEM compound clip, SEM XML de intercâmbio).

## Decisão técnica (provada na máquina do Eduardo, Resolve Studio 21.2.0.6, DbPrjVer 17)
- A API oficial NÃO escreve keyframe de Inspector. Provado: nenhum método de keyframe em Resolve/Project/Timeline/
  TimelineItem/MediaPool (só CopyAttributes/CopyGrades). Escrever propriedade em outro tempo, com o losango ligado e
  nos 3 KeyframeMode, NÃO cria chave (só altera a existente).
- Rota que funciona: injetar as chaves no **DRT** (formato nativo do Resolve). Provado: editar um valor de chave dentro do
  DRT, reimportar (`MediaPool.ImportTimelineFromFile`) e reexportar mantém o valor; renderiza certo; sem checagem de integridade.
- Fluxo planejado (híbrido, robusto): 1) escritor monta a timeline pela API (mídia, posições, SetSpeed, valores estáticos
  não-padrão nas propriedades que terão chave, para o parâmetro existir no blob); 2) `Timeline.Export(.drt, EXPORT_DRT)`;
  3) `drtlib` injeta o campo de chaves (f10) em cada parâmetro; 4) reimporta o DRT como nova timeline.

## Formato (ver `src/drtlib.py`)
- DRT = ZIP com `SeqContainer/<uuid>.xml`. O clipe `Sm2TiVideoClip` tem `<EffectFiltersBA>` (vazio se tudo padrão).
- EffectFiltersBA = hex( >I versão(2) + >I (1+tamanho zstd) + 0x81 + zstd(protobuf) ).
- protobuf: `f1` = grupo { `f1` id_grupo, `f7`, `f9`* = param { `f1` id_param, `f3{f1{f2 double}}` = valor atual, `f10` = chaves } }.
- chaves `f10`: bytes `FF FF FF (0x100-16n)` + n × [ tempo int32 LE (quadros da timeline, relativo ao clipe) | `00 00 0c 00` | double LE ].
  As flags `00 00 0c 00` são as das chaves feitas à mão (curva padrão). Significado/variantes (linear, hold, ease) NÃO decifrado.
- Parâmetros (grupo 4 = Transform): 40 Position X (= px / largura da timeline), 41 Position Y (= px / altura), 42 e 43 Zoom X e Y
  (fator, 1.0 = ajustado ao quadro; andam juntos por causa do ZoomGang), 47 Rotation (graus, anti-horário positivo).
  Opacidade: grupo 2, param 1 (0-100). Unidade confirmada com chaves: Pan 100 -> 0.0260416 (100/3840).
- Timeline de teste: 3840x2160, 29.97 fps; Start do clipe em quadros absolutos (01:00:00:00 = 108000).
- Resolve: Pan/Tilt em pixels da timeline, +Pan = direita, +Tilt = cima; RotationAngle positivo = anti-horário (no Premiere/After
  positivo é horário -> usar -rotação); SetSpeed(Percentage) funciona (50 e -100 reverso); mudar a velocidade muda a duração
  do clipe sozinho (reconferir). `ZoomGang` travou o Resolve numa tentativa: não mexer.

## PROVADO ponta a ponta (15/11/2026)
`src/test_inject.py`: valores não-padrão pela API -> Export DRT -> `drtlib.patch_drt` injeta chaves (Pan, Zoom, Rotação,
Opacidade, quadros 0 e 60) -> ImportTimelineFromFile -> reexport mostra as chaves -> quadros renderizados em 0/30/60
mostram a animação (gira, amplia, escurece). Take aberto na timeline de edição, chaves no Inspector, sem Fusion.

## Mapa completo de parâmetros (grupo, id) — via `src/map_params.py`
| Propriedade | (grupo, id) | Valor guardado |
| :-- | :-- | :-- |
| Position X / Y | (4,40) / (4,41) | px / largura da timeline ; px / altura |
| Zoom X / Y | (4,42) / (4,43) | fator |
| Pitch / Yaw | (4,45) / (4,46) | direto |
| Rotation | (4,47) | graus |
| Anchor | (4,48) | ponto: f3 = 0a12 3a10 <x double><y double>, px/largura e px/altura |
| Flip X / Y | (4,50) / (4,51) | bool: f3 = 0a02 2801 |
| Crop L / R / T / B | (6,54) / (6,55) / (6,56) / (6,57) | px/largura (L,R) ; px/altura (T,B) |
| Crop Softness / Retain | (6,58) / (6,151) | direto / bool |
| Opacity | (2,1) | 0-100 |
| CompositeMode | (2,0) | inteiro: f3 = 0a02 2002 |
Chaves só foram provadas em parâmetros escalares (40-43, 47, opacidade). Anchor/Flip/Crop com chave: não testado.
Importante: o parâmetro precisa EXISTIR no blob (valor não-padrão via SetProperty antes do Export), senão `efx_inject` levanta KeyError.
Tempo das chaves = quadros relativos ao início do clipe (provado com clipe em 01:00:00:00; clipe deslocado/velocidade: testar).

## REGRA DO TEMPO DAS CHAVES (medida por render, `src/test_timing3.py`)
tempo_da_chave (quadros da timeline, gravado no DRT) = d + head, onde
  d    = quadros desde o início do clipe NA TIMELINE;
  head = src_in(quadros da mídia) × (fps_timeline ÷ fps_mídia) ÷ (velocidade/100).
A velocidade NÃO muda o eixo (50% e 200% com src_in=0 deram o mesmo que 100%). Cabeça aparada conta (30 quadros de mídia 25fps em
timeline 29.97 = 36 quadros; com 50% = 72). Reverso (velocidade negativa): NÃO testado.

## Gerador pronto e VALIDADO: `src/gen.py` + `src/test_gen.py`
`gen.build(spec)`: importa mídia, cria timeline temporária pela API (trilhas, AppendToTimeline, SetSpeed, estáticos), exporta DRT, injeta
chaves, importa, renomeia, apaga a temporária. Spec em unidades do Resolve (Pan/Tilt em px, Zoom fator, Rotation já com o sinal do Resolve).
Validação (3 clipes: normal, aparado na cabeça, outra trilha a 50%; rampa 10 px/quadro; 12 medições por render): erro máx 2,5 px. TUDO OK.
Armadilhas descobertas: (a) blob pequeno (<~100 bytes) é gravado CRU com flag 0x80; maior vai em zstd 0x81 (drtlib.efx_encode já decide);
(b) AppendToTimeline em trilha inexistente "funciona" e não coloca nada: criar trilhas antes (gen.build faz);
(c) SetSpeed(x%) mantém a duração e muda o consumo de mídia (×x): gen.build compensa o trecho colocado; slow-mo pede mais mídia que o trecho
    (se faltar mídia, avisa e encurta); (d) o nome da timeline importada vem do nome do arquivo .drt (gen.build renomeia);
(e) GetProperty NÃO acompanha o tempo (devolve o valor estático): só o render mede animação (`ExportCurrentFrameAsStill` + borda das barras).

## PREMIERE -> DAVINCI FUNCIONA PONTA A PONTA (validado por quadro comparado, 15/11/2026)
`python src/bridge.py copy` (lê os clipes selecionados do Premiere pelo painel PR MCP Bridge, POST 127.0.0.1:47300/run com
`x-prmcp-token`, grava `%APPDATA%\NoeVFX\clipboard.json`) e `python src/bridge.py paste "Nome"` (normaliza e monta a timeline no Resolve).
Peças: `src/readers/premiere_read.jsx` (leitor ES3), `src/normalizer.py` (unidades), `src/gen.py` (gerador), `src/validate_e2e.py`
(compara quadro do Premiere x Resolve; PNG do Premiere traz ALFA: compor sobre preto antes de comparar).
Teste: sequência 1920x1080@25 com chaves em Position/Scale/Rotation/Opacity (0 s e 2 s) -> timeline 3840x2160@29.97.
Diferença média por pixel: 0.53 (0 s), 2.78 (1 s), 1.30 (2 s); 8.4 a 0.5 s por diferença de CURVA (Premiere linear x padrão do Resolve).
Conversão: Pan=(x-0.5)*seqW*k ; Tilt=-(y-0.5)*seqH*k ; Zoom=(Scale/100)*k*base/f ; Rotation=-graus ; k=min(rW/sW,rH/sH);
f=min(rW/srcW,rH/srcH) (Scale entire image to fit); base=1 (Scale 100=nativo) ou min(sW/srcW,sH/srcH) se `scaleToFrameSize`.
Leitura no Premiere (ExtendScript): clip.start/end/inPoint/outPoint (seg), projectItem.getMediaPath(), getFootageInterpretation().frameRate,
QE: `qe.project.getActiveSequence().getVideoTrackAt(t).getItemAt(i)` tem `.speed` (fator, 1=100%), `.reversed`, `.scaleToFrameSize`
(NÃO usar `.reverse`: lança erro). Position/Anchor normalizados 0..1; chaves em segundos de MÍDIA. Premiere 27.0.0 (2027) grava e RENDERIZA
chaves escritas por script (addKey + setValueAtKey) — testado.
Ainda NÃO testado no Premiere: clipe aparado (inPoint>0) com chaves, velocidade ≠100%, reverso, âncora fora do centro, escala não uniforme, crop.

## AFTER EFFECTS -> DAVINCI FUNCIONA (validado por quadro comparado, 15/11/2026)
`python src/bridge.py copy-ae` (camadas selecionadas da comp ativa; ponte de arquivos `%TEMP%\ae_bridge\task.json` -> `result.json`,
o código roda como CORPO DE FUNÇÃO: usar `return`; `src/ae_io.py`) e `python src/bridge.py paste "Nome"`.
Leitor `src/readers/ae_read.jsx`; conversor `normalizer.ae_to_spec`. AE 27.0 (2027).
Resultados (diferença média por pixel /255): translação+escala+rotação+opacidade animadas: 0.5 a 3.6 (curva) e 1.1 no fim;
ÂNCORA fora do centro + rotação 0->90 + escala + posição animadas: 0.25 a 0.44 (dobra a âncora na posição do centro e amostra por quadro);
camada aparada (inPoint 1) com stretch 200% (câmera lenta) e chaves em tempo de comp: 0.5 a 4.4.
Conversão AE: Pan=(x-cW/2)*k ; Tilt=-(y-cH/2)*k ; Zoom=Scale/100*k/f ; Rotation=-graus ; velocidade%=10000/stretch ;
mídia: src = (t_comp-startTime) * (100/stretch) ; chaves em tempo de comp = tempo de timeline (d=(t-inPoint)*fps).
Âncora fora do centro: centro da imagem c' = P + R(θ)·S·(c−a), R horário em tela y-baixo; amostra por quadro se rotação animada.
Armadilha: cabeçalho da lista de chaves = int32 big-endian −16·n (corrigido; antes só 1 byte, quebrava com ≥16 chaves).
Armadilha de validação: PNG do After é alfa PREMULTIPLICADO (não multiplicar de novo); o do Premiere é alfa reto (multiplicar).
Premiere + aparo + 50% de velocidade também validado (inPoint/outPoint vêm ESTICADOS pela velocidade: multiplicar por s).
Câmera lenta no Resolve: AppendToTimeline do trecho a 100% e `SetSpeed({'Percentage':x,'RippleTimeline':True})` (duração D0/s, mantém o trecho
inteiro; gen coloca os clipes em ordem cronológica porque o ripple empurra os posteriores). Mudar a velocidade no Premiere é só pela UI
(Clip > Speed/Duration; QE `.speed` é somente leitura); no AE é `layer.stretch`.

## ETAPA 16/11/2026: curvas, time remap, Flip, âncora com chaves, vários clipes (tudo validado por render)
- **Curvas (fidelidade)**: os leitores AMOSTRAM a curva real quadro a quadro (AE: `valueAtTime`; Premiere: `getValueAtTime(mkTime(tempo_de_midia))`)
  e o `normalizer` usa as chaves originais se a interpolação LINEAR já as reproduz (tolerância por propriedade), senão as amostras, reduzidas por
  Ramer-Douglas-Peucker (`EPS`: Pan/Tilt 0.5 px, Zoom 0.002, Rotação 0.05°, Opacidade 0.2). Valida: AE com Easy Ease 70% + trajetória espacial curva +
  hold na opacidade: diferença 0.8 a 5 /255 em 9 instantes; Premiere com chaves Bezier/hold: 0.8 a 8.2.
- **Flags de chave no Resolve (`sweep_flags.py`, medido por render)**: `00 00 0c 00` = LINEAR EXATO (é o que `keys_encode` grava); byte3=`0x80` = curva SUAVE
  (91/295/500 em vez de 100/300/500); byte2≠0x0c ou byte3=0x01 → chave ignorada; bytes 0/1 sem efeito; byte3 0x04..0x40 = linear. As ALÇAS Bezier
  editáveis do Resolve NÃO estão decifradas (precisa de amostra feita à mão com alça editada). Por isso o envio é: amostras reduzidas com chaves lineares.
- **Cabeçalho da lista de chaves** = int32 BE de −16·n (corrigido; antes quebrava com ≥16 chaves).
- **Flip** = escala negativa no AE → `FlipX/FlipY` estáticos (`SetProperty('FlipX', True)`); `ZoomGang=False` quando X≠Y (escala não uniforme). Premiere: efeito
  "Horizontal Flip"/"Vertical Flip" → leitor devolve `effects[]`. **Âncora com chaves**: dobrada na posição do centro da imagem (Resolve fica com âncora no centro),
  amostrando por quadro quando há rotação/escala animadas. **3D** → 2D (só Position X/Y, Scale X/Y, Rotation Z). Expressão: ignorada. Validado AE: flip + âncora
  animada + escala não uniforme + 3D: 0.2 a 1.2 /255. Vários clipes/trilhas/tempos/stretch/opacidade: AE (3 camadas) 0.16 a 0.76.
- **TIME REMAP / SPEED RAMP (Resolve)**: o mapa de tempo do clipe é `<MediaTimemapBA>` (keyed-dict `Sm2TimeMap` com `KeyframesBA` protobuf de pontos
  [recordSec, sourceSec]; origem implícita (0,0); ver `drtlib.timemap_encode/decode`, byte-exato com o do Resolve; formato documentado no
  `davinci-resolve-mcp/resolve-advanced/vendor/drp-format/media-timemap.js`, MIT). O mapa cobre a MÍDIA inteira em tempo "esticado"; o clipe abre uma janela por
  `<In>` (`'59|<double LE hex da fração>'`, ver `drtlib.in_field`) e `<Duration>`. `gen.py` (clip['remap']={'points':[[d_quadros, seg_midia],...]}): coloca o trecho,
  SetSpeed médio com ripple só para a duração, exporta, injeta mapa com origem (0,0)→(src0,src0) (velocidade 1 antes do clipe) + `<In>`=src0·fps + `<Duration>`.
  Validação INDEPENDENTE DE CURVA (casa cada quadro renderizado com os quadros do vídeo): rampa sintética 100%→250%→66%: erro 0 quadros em 24 pontos;
  AE Time Remap com ease começando no meio da mídia: erro máx 1 quadro em 16 instantes (`validate_remap_ae.py`, `test_remap.py`).
  Leitor AE: `ae_read.jsx` amostra `ADBE Time Remapping` por quadro; normalizer reduz com 0.2 quadro de mídia. Trechos em reverso: ainda não (avisa e ignora).
- **PREMIERE TIME REMAP: NÃO é legível por ExtendScript nem pelo QE** (confirmado no Premiere 27: o componente "Time Remapping" aparece no Effect Controls mas
  `clip.components` só tem Opacity e Motion; QE `.speed` só lê o fator constante). Digitar o valor do Speed no Effect Controls NÃO funciona (só pelo gráfico).
  Caminho: ler o `.prproj` (gzip XML) depois de `app.project.save()`; PRECISA de um exemplo real com a "canetinha" (speed ramp) feito à mão para eu ver como o
  Premiere grava (valores e alças Bezier) — `NoeBridgeTeste.prproj`, sequência SeqTrim/SeqCurva; salvar e me avisar.

- **TRANSIÇÕES (DRT)**: `<Sm2TiTransition>` é um `<Element>` entre os `<Element>` dos clipes dentro de `<Items>` da `<Sm2TiTrack>` (video em `VideoTrackVec`, audio em `AudioTrackVec`). Templates em `drtlib` (`_TR_VIDEO` + blobs `_TR_FIELDS`/`_TR_EFX`/`_TR_WIPE_FIELDS`/`_TR_AUDIO_EFX`, formato decifrado no toolkit drp-format, MIT); span = `<Start>`/`<Duration>` absolutos, `PrettyType` seleciona o estilo, `Position`/`AlignmentType` ficam 2 (o span manda). `drtlib.insere_transicoes(xml, transitions)` acha o clipe que termina no `cut` e insere depois dele; `patch_drt2(..., transitions=)` chama depois dos patches de clipe e devolve avisos. Leitor: `track.transitions` (DOM normal) em `premiere_read.jsx`; normalizer emite `spec['transitions']` só se o corte tem clipe copiado dos dois lados (mapa de nomes em `_PRETTY`/`_AUDIO_TR`). Validado no Resolve: Cross Dissolve importa e re-exporta intacto; falta teste com transição real no Premiere. `RECURSOS.md` tem o mapa completo de recursos + roteiro de testes.

## Falta fazer
0. Premiere: leitor de Time Remapping via `.prproj` (precisa do exemplo); reverso (Premiere reversed / AE stretch<0), congelar, rampas de velocidade (Time Remap), 3D/parenting/expressão (hoje só avisa),
   escala não uniforme, crop, chaves em Anchor/Flip, vários clipes na mesma seleção do AE/Premiere (testar com 2+ camadas e trilhas).
0b. Ergonomia: atalho global/painel para "copiar" e "colar" (hoje linha de comando `python src/bridge.py ...`), toast com avisos, empacotar.
1. Flags de curva (linear/hold/ease): hoje só a curva padrão `00 00 0c 00` (precisa de amostras feitas à mão).
2. Reverso e rampas de velocidade (hoje `gen.build` recusa velocidade <= 0). Chaves em Anchor/Flip/Crop/Composite: Anchor é ponto (formato de chave não decifrado).
3. Conversores (normalizadores) para unidades do Resolve: Premiere (Position normalizada, Scale, Rotation horário, Opacity) e After
   (px da comp, âncora, stretch). Depois os leitores (ExtendScript) que geram o JSON neutro.
4. Painel/atalho de copiar e colar. NUNCA criar timeline com nome existente (aviso no monitor 1 trava a API; `gen` já evita).
4. Leitores: ExtendScript no Premiere (premiere-bridge MCP, 127.0.0.1:47300) e no After (ae_run_custom_script). Ver relatórios em
   `D:\Noe VFX\.Labs\Noe VFX Console\reports\` (Blueprint, Revisão, Pesquisa DaVinci A-D, Keyframes no Inspector sem Fusion).

## Pendências de ambiente
- Projeto `_TESTE_NoeBridge_descartar` (banco "Projetos") tem várias timelines de teste; apagar com confirmação do Eduardo.
- No fim da sessão o Resolve passou a devolver propriedades vazias e a falhar `CreateTimelineFromClips` (tela do PC parecia
  bloqueada/apagada, captura vazia). Reabrir o Resolve/destravar a tela antes de continuar.
- Computer-use: o DaVinci fica no monitor 2; o widget do NetMonitor conta como janela em primeiro plano.
