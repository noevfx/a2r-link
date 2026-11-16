# A2R Link — Mapa de recursos (Premiere Pro + After Effects → DaVinci Resolve)

Documento de referência: tudo que o plugin **faz hoje**, o que está **em implementação** e o que está **no roadmap**, mais o **roteiro de material de teste** para exercitar cada recurso.

Legenda de status:
- ✅ **Verificado** — implementado e testado no Resolve real (21.2)
- 🧪 **Implementado, a validar** — código pronto, falta teste com material real
- 🗺️ **Roadmap** — não implementado ainda

---

## 1. Pipeline (como funciona)

`Copiar` no painel → leitor ExtendScript extrai dados da seq/comp → `clipboard.json` → `Colar` no Resolve → normalizer converte pro spec → `gen.py` monta itens → exporta DRT → `drtlib` injeta keyframes/timemap/transições → reimporta a timeline.

Sem XML/AAF/EDL de intercâmbio, sem Fusion, sem compound clip — tudo via API + formato DRT nativo.

## 2. Timeline de destino

| Recurso | Status | Detalhe |
|---|---|---|
| Resolução da origem | ✅ | Timeline nova sai com W×H exatos da seq/comp (ex.: 1080×1920 vertical não vira 4K) |
| Frame rate da origem | ✅ | `timelineFrameRate` custom (29.97, 23.976 etc.) |
| Seletor de destino | ✅ | Painel: **Nova timeline** (padrão) / **Timeline de mesmo nome** |
| Localizar por nome | ✅ | Modo "mesmo nome" acha a timeline pelo nome da seq/comp; não achou → cria nova + aviso |
| Posição e trilha | ✅ | Takes vão para o mesmo tempo e mesma trilha da origem |
| Substituição de colisão | ✅ | Clipe novo que sobrepõe clipe antigo na mesma trilha → o antigo é deletado (modo "atualizar take") |
| Preservação | ✅ | Itens não-colidentes (inclusive trilhas acima) ficam intactos |
| Segurança transacional | ✅ | Append roda numa sandbox (`DuplicateTimeline`); erro não corrompe a original |
| Pasta da timeline | ✅ | Timeline vai para o bin da original (append) ou sub-bin novo |

## 3. Vídeo — Premiere Pro

| Recurso | Status | Detalhe |
|---|---|---|
| In/out do clipe | ✅ | Janela de mídia exata |
| Posição/trilha | ✅ | |
| Velocidade constante | ✅ | Qualquer % (ex.: 526%) via `MediaTimemapBA` sem ripple |
| **Speed ramp com ease** | ✅ | Nós eased nativos (`mode=2`) com alças, editáveis no Resolve — **modo Editável: mesma contagem de nós da origem** (PR: keyframes de velocidade, quase exato contra render; AE: nós realocados nos pontos de virada, rajada preservada). **Modo Precisa**: ponto por quadro, sem alças |
| Fidelidade da rampa | ✅ | Editável: PR quase exato / AE até ~8 q de mídia na rajada (o ease do Resolve arredonda cantos — não é Bézier livre). Precisa: fiel à curva lida (AE desvio 0 na amostra; PR descida com alça >50% pode desviar ~4 q — regra não decifrada) |
| Position / Scale / Rotation / Opacity | ✅ | Estático e **animado** (keyframes → curva `f10`) |
| Ease em keyframes de transform | 🗺️ | Hoje sai amostragem densa (valor certo, forma densa); formato de ease do `f10` ainda não decifrado — falta exemplo real |
| Anchor Point estático | ✅ | |
| Anchor animado | ✅ | Convertido quadro a quadro (aviso) |
| Flip Horizontal / Vertical (efeito) | ✅ | Via `static['FlipX'/'FlipY']` |
| Scale to Frame Size | ✅ | Base de escala ajustada |
| Escala não-uniforme | ✅ | `ZoomGang=false`, ZoomX/ZoomY independentes |
| Crop (esq/dir/topo/base) | 🧪 | Estático provado (0–100% direto); animado vai pela mesma rota de keys dos demais params |
| Efeitos mapeados | ✅ | **60 nomes → plugin-ids Resolve FX** (todo o painel onde existe equivalente: blurs, keyers, distorções, keying, grão, transform, stylize); valores de param convertidos quando a unidade casa (ângulo°, %→0–1, cor, checkbox) — ver seção Efeitos |
| Efeitos não mapeados | ⚠️ | Aviso por efeito (Lumetri, terceiros) |
| Nested sequence | 🧪 | Expandida (flatten): clipes internos viram itens editáveis na trilha do pai pra cima. Speed/reverso **dentro** da nested leem do `.prproj` (`PlaybackSpeed`/`PlayBackwards` no Clip — QE não enxerga seq inativa; provado V2+V4 reversas → timemaps descendentes). Limitações: áudio interno não vai (aviso), speed/reverso **no clipe da nested** → aviso e não expande, detecção por nome da seq |
| Adjustment layer | 🧪 | "Adjustment Layer" → Adjustment Clip nativo na trilha/posição certas (via realocação DRT) |
| Reverso (speed < 0) | ✅ | Timemap descendente sintético — provado no AE (stretch −100) e no Premiere |
| Freeze frame | 🗺️ | Formato decifrado (sentinela `XMax=60000`), não integrado |
| Disabled clip | ✅ | Ignorado com aviso |
| **Cor de clipe (label)** | 🧪 | Lida do `.prproj` (label do take; fallback = label do bin herdado) → `SetClipColor` no Resolve, casamento por matiz para a paleta do Resolve. Vale para vídeo e áudio |
| Clipe de texto/gráfico | ⚠️→🗺️ | Hoje: aviso "sem arquivo de mídia" e ignorado. Roadmap: gerador `Sm2TiGenerator` (Text+) |

## 4. Áudio — Premiere Pro

| Recurso | Status | Detalhe |
|---|---|---|
| Trilhas e posição | ✅ | A1, A2… na mesma ordem |
| Volume constante | ✅ | dB exato |
| **Volume animado (keyframes)** | ✅ | `Level` com keys → curva no `f10` do clipe de áudio |
| Pan | ✅ | |
| Velocidade/remap em áudio linkado | ✅ | Mesmo timemap do vídeo linkado (mesma mídia+posição+in-point) |
| Fades de clipe | ✅ | Transição de ponta solta (Constant Power etc. numa borda) → `SetFades` (FadeIn/FadeOut); keyframes de Level também vão |
| Áudio-only copy | ✅ | Copiar só áudio funciona |

## 5. Transições

✅ Implementado via `TimelineItem.AddTransition` pós-reimport (tipos reais verificados) + blob DRT para crossfade de áudio entre clipes.

| Transição Premiere | Sai no Resolve como |
|---|---|
| Cross Dissolve | Cross Dissolve |
| Film Dissolve | Cross Dissolve (aproximação) |
| Additive / Non-Additive Dissolve | Idem, nomes nativos |
| Dip to Black | Dip To Color Dissolve |
| Dip to White | Dip To Color Dissolve (sai **preto** + aviso — API não expõe a cor) |
| Morph Cut | Smooth Cut |
| Wipe | **Edge Wipe** (tipo real verificado) |
| Push / Slide / Split / Cross Iris / Oval Iris / Diamond Iris / Clock Wipe / Band Wipe / Radial Wipe / Center Wipe / Barn Door / Blur Dissolve | Idem, nomes nativos |
| Animation/Grunge/Lights/Slide/Transformers/Wipe do PR (66 nomes) | **Transições Fusion reais** — `Templates.drfx` validado por `AddTransition`: Block Motion→Tile Wipe, Flip→Flip 3D, Fold→Fold, Pop→Pop Wobble, Spin→Spin, Spring→Elastic Rubber, Chaos→Disarrange, Earthquake→Camera Shake, Flicker/Flash→Brightness Flash, Glass→Shatter, Glitch/VHS→Glitch, Liquid→Ripple Warp, Chroma Leak→RGB Splitter, Cross/Zoom Blur→Crash Zoom, Directional Blur→Stretch Blur, Flare/Ray→Tunnel of Light, Radial Blur→Radial, 3D Roll/Roll→Cube, Film Roll→Film Strip, Stretch/Stretch Wipe→Stretch Blur, Whip→Pan Left, Shape→Shape Transition, 3D Spin(back)→Flip 3D, Page Peel→Page Curl, Slice→Slice Push, Wave→Ripple Warp, Soft Wipe/Luma Fade→Luma Wipe, Pencil Wipe→Paint On, Box/Checker Wipe, Mosaic→Mosaic Dissolve |
| Constant Power / Constant Gain / Exponential Fade (áudio, entre clipes) | Crossfade de áudio |
| Transição em ponta solta (um clipe só) | **Fade**: vídeo → `AddTransition` na borda; áudio → `SetFades` |
| Outras | Cross Dissolve + aviso |

Regras:
- Entre dois clipes: só quando os **dois lados** do corte estão no conjunto copiado.
- Ponta solta (fade in/out de clipe): só quando **o clipe da borda** está no conjunto copiado.
- Sem clipe adjacente no corte → aviso e ignora (não inventa transição).

## 6. After Effects

| Recurso | Status | Detalhe |
|---|---|---|
| Layers com mídia | ✅ | Arquivo, in/out, posição na timeline da comp |
| Ordem de layers → trilhas | ✅ | Layer de cima = trilha de cima |
| Transform 2D (Pos/Âncora/Scale/Rot/Op) | ✅ | Estático e animado |
| **Time Remap com ease** | ✅ | Nós eased nativos; validado em paste real (`mode=2`) |
| Áudio da layer (Levels) | ✅ | Inclusive animado |
| Stretch ≠100% | ✅ | Velocidade constante |
| Comp → timeline nativa | ✅ | Resolução e fps da comp (ex.: 1080×1920 @ 29.97) |
| Layer sem mídia (sólido/texto/forma) | ⚠️ | Ignorada com aviso |
| **Precomp** | 🧪 | Expandida: sublayers viram clipes editáveis empilhados da trilha do pai pra cima (`L8_precomp/x` provado @trk7). Stretch≤0 e transform animado da precomp geram aviso |
| Adjustment layer (`adjustmentLayer`) | 🧪 | `L4_adjust` do fixture virou Adjustment Clip nativo (trk3 @86400) |
| Parenting | ⚠️ | Aviso, não convertido |
| Expressões | ⚠️ | Valor lido sem expressão + aviso |
| Layer 3D / câmeras | ⚠️ | Só eixo Z de rotação é lido; profundidade não vai |
| Stretch negativo (reverso) | ✅ | Timemap descendente (provado: L6 do fixture, mídia 4→0s) |
| Cor da layer (label) | 🧪 | `layer.label` (1–16) → `SetClipColor` no Resolve (tabela de matiz) |

## 7. Roadmap (ordem de implementação)

1. ~~**Transições**~~ — ✅ tipos reais via `AddTransition` + fades de ponta solta (vídeo e áudio)
2. **Markers** — ✅ sequência/comp + markers de clipe via `AddMarker` pós-reimport (não serializam no DRT)
3. ~~**Nested sequences**~~ — ✅ AE (precomp→sublayers) e Premiere (seq aninhada→clipes internos) ambos flatten provados. Limitações documentadas
4. ~~**Adjustment clips**~~ — ✅ provado (Adjustment Clip nativo realocado via DRT)
5. ~~**Efeitos**~~ — ✅ **60 nomes mapeados** → plugin-ids Resolve FX + params com unidade provada (ângulo/%/cor/bool/hue + **blur px→normalizado medido**: σ=0,1·dim·S²). **Params animados** → Fusion comp + BezierSpline (provado). Incremental: mais params por plugin
6. ~~**Ease em keyframes de Inspector**~~ — ✅ keys `0x0d` + tangentes Hermite (desvio ≤0,3px)
7. ~~**Reverso + freeze frame**~~ — ✅ timemap descendente + timemap plano (PR Frame Hold via `.prproj`, AE stretch=0)
8. **Track mattes / máscaras / tracking** — detecção + aviso no AE (`numMasks`); transferência real é escopo grande (Fusion masks/Power Window)
9. **Lumetri/cor** — rota é `SetCDL`/grade nativa, não OFX (fora do escopo atual por decisão)
10. ~~**Efeitos de áudio**~~ — ✅ ~40 nomes → Fairlight FX (`AddEffect('audio',id)`), params com default + aviso
11. ~~**Blend modes**~~ — ✅ `CompositeMode` por clipe (PR/AE → enum do Resolve; Dissolve/mattes com aviso)
12. **Auto-update** — painel checa GitHub Releases (`noevfx/a2r-link`), um clique baixa+instala em `%LOCALAPPDATA%\Programs\A2R Link`

### Bugs corrigidos nesta rodada
- **Órfãos no paste AE**: `SetSpeed` com `RippleTimeline:True` dividia clipes das outras trilhas (a premissa "o que vem depois não existe" só vale na própria trilha). Velocidade constante agora sai por patch `Duration`+timemap (mesmo caminho do append/áudio); remap encolhe com `RippleTimeline:False`.
- **`<Items/>` autocontido**: trilha vazia no DRT exporta `<Items/>`; a realocação de títulos/ajustes jogava o elemento para fora da trilha e o import o descartava.

## 8. Limitações conhecidas

- **Editar a rampa na barra "Speed Change" do Resolve remove as alças** (comportamento do Resolve). Re-export/roundtrip DRT preserva.
- **Ease de rampa é aproximação**: o modelo do Resolve é canto arredondado (alças arredondam a junção das retas, não são tangentes Bézier da origem). Modo Editável aproxima pela mesma contagem de nós; quem precisa bit-a-bit usa o modo Precisa (denso, sem alças).
- **Keyframes de Inspector saem densos** (1 ponto/quadro) — valor certo, edição menos limpa.
- **API não persiste timeline até salvar o projeto** — timelines criadas por script somem se o Resolve recarregar sem salvar.

## 9. Roteiro de material de teste

Projeto de teste sugerido (uma seq no Premiere + uma comp no AE cobrem tudo):

### Sequência Premiere (`TESTE_A2R`)
1. **V1**: clipe A → **Cross Dissolve** (centrada) → clipe B → **Dip to Black** → clipe C
2. **V2**: clipe com **speed ramp eased** (já existe no seu projeto) + clipe com **reverso** (esperar aviso) + clipe com **Flip Horizontal**
3. **V3**: clipe com **Position/Scale/Rotation animados** com ease + **Opacity** com fade por keyframe + **Crop** aplicado (esperar aviso) + um efeito não mapeado tipo Lumetri (esperar aviso)
4. **V4**: **nested sequence** (esperar aviso) + **adjustment layer** com Blur (esperar aviso)
5. **A1**: áudio linkado do clipe com rampa + **Constant Power** entre dois áudios adjacentes
6. **A2**: áudio com **volume animado** (keyframes de Level) e **pan** ≠0
7. **Markers**: alguns markers de sequência na régua + marker num clipe (chegam coloridos via `AddMarker`)
8. Teste de **seleção parcial**: selecionar só o clipe B → dissolve vem; selecionar B sem vizinho → aviso
9. Teste **append**: copiar V1 inteira → depois alterar só o clipe B e mandar "Timeline de mesmo nome" → só B é substituído, transições vizinhas preservadas

### Comp After Effects (`TESTE_A2R_COMP`)
1. Layer vídeo com **Time Remap eased** (rampa subindo e voltando)
2. Layer com **transform animado** (pos/scale/rot com easy ease)
3. Layer com **áudio** + levels animados
4. **Precomp** (esperar aviso), **sólido** (aviso), layer com **parenting** (aviso), layer com **expressão** (aviso)
5. Comp em resolução diferente da timeline aberta no Resolve (ex.: 1080×1920 num projeto 4K) → deve nascer nativa

### Verificação no Resolve
- Cada `Sm2TiTransition` deve aparecer como dissolve na trilha certa, duração certa, posição certa
- Curva "Retime Frame" com cantos suaves = ease vivo
- Inspector: valores batem; keyframes densos (esperado hoje)
- Áudio: waveform, nível, pan e fades conferem
