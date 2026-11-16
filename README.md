# A2R Link

![versão](https://img.shields.io/badge/vers%C3%A3o-0.1.5-blue)
![plataforma](https://img.shields.io/badge/Windows-10%2F11-555)
![licença](https://img.shields.io/badge/licen%C3%A7a-gratuita-green)

**Envie a timeline inteira ou só os takes selecionados do Adobe Premiere Pro e do After Effects direto para a timeline do DaVinci Resolve** — sem exportar XML, sem AAF. Os takes chegam abertos na timeline de edição, com keyframes no Inspector (sem Fusion, sem compound clip).

### Por que ele é diferente

- **Keyframes chegam vivos** — Position/Scale/Rotation/Opacity chegam com as alças Bézier originais no Inspector do Resolve: você continua editando a curva em vez de recomeçar do zero. A speed ramp vai com **os mesmos nós da origem** (modo Editável, padrão) ou **quadro a quadro** (modo Precisa) — chave no painel. Rampa do Premiere sai mesmo sem API pra isso (lida do `.prproj`). Nenhuma ponte gratuita entrega isso.
- **Feito pra revisão de edição** — mande de novo só os takes alterados: o A2R substitui cada um na mesma posição e trilha, sem ripple. A timeline do Resolve vira um espelho da sua edição no Premiere/AE.
- **Transições e efeitos de verdade** — ~66 transições saem como tipos reais do Resolve (wipe é wipe, não dissolve disfarçado), ~60 efeitos viram Resolve FX nativos no Inspector e ~40 efeitos de áudio viram Fairlight FX. Param animado vira Fusion comp com chaves.
- **A timeline nasce igual à origem** — resolução e fps certos no primeiro envio: o vertical 1080×1920 de reels sai vertical, 29.97 sai 29.97.
- **O que está por dentro vai junto** — nested sequences e precomps são expandidas recursivamente (herdando speed, rampa e markers); títulos viram Text+ posicionados; markers chegam coloridos; o áudio linkado segue o mesmo retime do vídeo.
- **Honesto por construção** — o que não tem equivalente fica fora com aviso nomeado, nunca um dissolve falso ou um drop silencioso.
- **Gratuito e aberto** — código-fonte aqui, um instalador e auto-update com um clique dentro do próprio painel.

Painéis CEP para Premiere e After + script para o Resolve. Feito pela Noé VFX.

---

## Instalação

1. Baixe o zip da **[última release](../../releases/latest)**.
2. Extraia e rode `INSTALAR.bat` (Windows). No Mac, `INSTALAR.command`.
3. Reabra o Premiere/After: **Janela › Extensões › A2R Link**.
4. No DaVinci: **Workspace › Scripts › Edit › A2R Link - Colar**.

Pré-requisitos: Premiere Pro e/ou After Effects, **DaVinci Resolve Studio** (a API de scripting que o projeto usa é exclusiva da versão Studio) e Python 3.10+.

Para remover: `DESINSTALAR.bat` / `DESINSTALAR.command`.

## Uso

**Enviar a timeline ou os takes** — no Premiere ou no After:

1. Selecione os takes que quer mandar (clipe, camada — ou nada: aí vai a sequência/comp inteira) e clique **Enviar ao DaVinci** (ou **Copiar** + **Colar**).
2. Os takes aparecem na timeline do Resolve, nas mesmas posições e trilhas, e no Media Pool organizados em `Projeto › Sequência/Comp`.

**Atualizar uma edição que já está no DaVinci** — o modo pra quem trabalha com revisão:

O projeto já foi pro Resolve e o cliente pediu alteração? Você troca os takes no Premiere/After, seleciona **só os takes novos** e manda de novo. O A2R acha a timeline de mesmo nome, **substitui só os takes que mudaram na mesma posição e trilha** e deixa todo o resto intacto — corte a corte, sem ripple, sem duplicar nada. A timeline do Resolve vira um espelho vivo da edição: cada ida e volta atualiza só o que mudou.

**Chaves do painel**:

- **Destino › Nova timeline** — cria `Nome da sequência` com resolução e fps da origem. **Mesmo nome** — adiciona/substitui takes na timeline que já existe com esse nome, mantendo posição e trilha originais; os demais takes ficam intactos (sem ripple). É o modo das revisões: manda de novo só o que mudou.
- **Rampa › Editável** (padrão) — a rampa chega com a **mesma quantidade de nós da origem** e com alças: no Premiere são os próprios keyframes de velocidade; no After, os nós são realocados na curva para segurar a rajada. Fica leve de mexer no Resolve, com fidelidade quase exata.
- **Rampa › Precisa** — um ponto por quadro, sem alças: segue a curva original frame a frame, pra quando a rampa tem que bater exatamente.

**Auto-update**: o painel verifica releases novas no GitHub ao abrir (e a cada 6h). Quando sai versão nova, aparece um cartão — **um clique baixa e instala**; depois é só reabrir o programa.

## O que vai

| Recurso | Estado |
|---|---|
| Posição, corte e trilha | ✅ exatos, vídeo e áudio |
| Seleção parcial | ✅ só os takes selecionados (ou a timeline inteira) |
| Revisão de edição | ✅ reenvio com takes novos substitui só o que mudou, na mesma posição/trilha — o resto fica intacto |
| Anchor Point, Position, Scale, Rotation, Opacity | ✅ estáticos e animados — **curvas Bézier chegam corretas e editáveis** (alças no Inspector do Resolve, não assadas) |
| Flip H/V, escala não uniforme | ✅ |
| Velocidade constante, clipe aparado | ✅ |
| Speed ramp do After Effects | ✅ timemap real — Editável: mesma contagem de nós do AE (aproximada; o ease do Resolve arredonda cantos, não é Bézier livre — rajada preservada). Precisa: quadro a quadro |
| Speed ramp / Time Remap do Premiere | ✅ lido do `.prproj` (o DOM não expõe) — Editável nos keyframes de velocidade (quase exato); Precisa quadro a quadro |
| Reverso | ✅ timemap descendente |
| Freeze frame | ✅ Frame Hold / Insert Frame Hold do PR, `timeStretch=0` do AE |
| Blend modes | ✅ Screen/Multiply/Overlay/Soft Light etc. → `CompositeMode` (modos sem equivalente → aviso) |
| Transições | ✅ ~66 nomes → tipos reais do Resolve (dissolves, wipes, iris, 17 tipos simples + 41 transições Fusion: Shatter, Glitch, Crash Zoom, Page Curl, Cube...). Sem equivalente → fica fora com aviso |
| Fades em ponta solta | ✅ fade in/out nativo (vídeo: `AddTransition`; áudio: `SetFades`) |
| Fades de áudio entre clipes | ✅ Constant Power/Gain/Exponential → crossfade nativo |
| Volume e pan de áudio | ✅ estáticos e keyframes |
| Efeitos de áudio | ✅ ~40 nomes → Fairlight FX (params com default + aviso) |
| Efeitos de vídeo | ✅ ~60 nomes → plugins Resolve FX nativos no Inspector |
| Params de efeito (estáticos) | ✅ quando a unidade casa — ângulo°, %→0–1, cor, checkbox, blur px→normalizado (escala medida) |
| Params de efeito **animados** | ✅ via Fusion comp + BezierSpline (ex.: Drop Shadow angle animado) |
| Texto/gráficos do Premiere | ✅ viram Text+ posicionados (transform animado → estático + aviso) |
| Adjustment layers | ✅ Adjustment Clip nativo realocado na posição certa |
| Nested sequences (PR) e precomps (AE) | ✅ expandidas recursivamente — herdam speed, rampa, markers |
| Markers | ✅ markers de sequência/comp + markers de clipe/layer (coloridos, `AddMarker`) |
| Labels de clipe | ✅ cores do AE/PR mapeadas |
| Resolução e fps da origem | ✅ timeline nova sai com a config certa |
| Reenvio | ✅ não sobrescreve — `Nome 2` ou substituição cirúrgica no modo existente |

## O que não vai (de propósito — com aviso, nunca em silêncio)

- **Lumetri Color** — a rota correta é grade nativa/`SetCDL`, não OFX. Fora do escopo.
- **Efeitos sem equivalente no Resolve** (terceiros, alguns nativos) — ficam fora com aviso por nome.
- **Track mattes, máscaras e tracking** — máscaras do AE são detectadas e avisadas; a transferência real não existe.
- **Parenting, expressões, 3D real** — camada 3D sai como 2D (aviso); motion blur não vai.
- **Params de transição** (direção do wipe, centro do iris, canto do page curl) — a API não expõe; vai com os defaults do template.
- **Pixel-strengths sem escala provada** — vai o default + aviso (a escala do blur gaussiano foi medida; demais, conservador).

## Como funciona (por dentro)

```
Premiere/AE (CEP panel + ExtendScript) → clipboard.json → bridge.py
   → normalizer.py (spec comum) → gen.py + drtlib.py
   → timeline temporária → export DRT → patch no XML/binário do DRT
   → reimport → timeline final no Resolve
```

- `src/readers/` — leitores ExtendScript (Premiere via ponte prmcp; AE via ExtendScript direto). O que o DOM não expõe (Time Remap, Frame Hold) é lido do `.prproj` salvo.
- `src/drtlib.py` — encoder/decoder do formato DRT (protobuf-like): timemaps, keyframes com ease, `EffectFiltersBA` (efeitos OFX nativos escritos no blob), transições.
- `src/gen.py` — monta a timeline no Resolve: API + DRT patch + pós-import (markers, transições, fades, comps de efeitos animados).
- Atualizações: `bridge.py check-update` / `self-update` — release no GitHub → zip extraído em `%LOCALAPPDATA%\Programs\A2R Link` → `install.py` reponta a config.

## Limitações conhecidas

- **Windows testado**; o instalador Mac existe (`INSTALAR.command`) mas não foi validado em hardware.
- Editar a rampa na barra "Speed Change" do Resolve remove as alças dela (comportamento do próprio Resolve — reexportar pelo DRT preserva).
- Keyframes de efeito animados usam frames de timeline do clipe; com speed ramp podem desalinhar.
- Transições antigas junto de takes preservados podem duplicar na borda em casos raros.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `extensions/` | painel CEP (common) + manifests PR/AE |
| `src/` | `bridge.py`, `normalizer.py`, `gen.py`, `drtlib.py`, `prproj.py`, leitores JSX |
| `resolve/` | script **A2R Link - Colar.py** |
| `tests/` | fixtures e sondas usadas no desenvolvimento |
| `install.py`, `INSTALAR.*` | instalador multiplataforma |

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md) — o estado detalhado de desenvolvimento fica em [HANDOFF.md](HANDOFF.md) e o mapa de recursos em [RECURSOS.md](RECURSOS.md).

---

### English (summary)

**A2R Link** sends the whole timeline or just the selected takes from Adobe Premiere Pro / After Effects straight into a DaVinci Resolve Studio timeline — no XML, no AAF. Re-sending updated takes replaces only what changed, in the same position and track — built for edit revisions. New timelines inherit the source resolution/fps (vertical reels stay vertical). Position, tracks, Motion/Inspector keyframes (real Bézier easing — stays editable in the Inspector), speed ramps (same node count as the source, or frame-accurate — panel switch; Premiere ramps read from the `.prproj` the DOM can't see), reverse, freeze frames, blend modes, ~66 transitions (real Resolve types incl. Fusion transitions), video/audio fades, ~60 video effects (native Resolve FX, incl. animated params via Fusion comps), ~40 Fairlight audio effects, titles, adjustment layers, nested content and markers — all with per-feature warnings instead of silent drops. Windows tested; macOS installer included (unverified). Panels check GitHub Releases and self-update with one click.
