# A2R Link

![versão](https://img.shields.io/badge/vers%C3%A3o-0.1.4-blue)
![plataforma](https://img.shields.io/badge/Windows-10%2F11-555)
![licença](https://img.shields.io/badge/licen%C3%A7a-gratuita-green)

**Copie clipes do Adobe Premiere Pro e do After Effects e cole direto na timeline do DaVinci Resolve** — sem exportar XML, sem AAF, sem passar por binário de edição. Os takes chegam abertos na timeline de edição, com keyframes no Inspector (sem Fusion, sem compound clip).

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

1. No Premiere ou no After, selecione os clipes/camadas (ou nada — vai tudo) e clique **Copiar** (ou **Enviar ao DaVinci**).
2. No DaVinci, rode o script **A2R Link - Colar** (ou clique **Colar** no painel).
3. Os takes aparecem na timeline, no Media Pool organizados em `Projeto › Sequência/Comp`.

**Destino do paste** (seletor no painel):

- **Nova timeline** — cria `Nome da sequência` com resolução e fps da origem.
- **Timeline de mesmo nome** — adiciona/substitui takes na timeline que já tem esse nome, mantendo posição e trilha originais; os demais takes ficam intactos (sem ripple). Ideal pra iterar: manda de novo só o que mudou.

**Auto-update**: o painel verifica releases novas no GitHub ao abrir (e a cada 6h). Quando sai versão nova, aparece um cartão — **um clique baixa e instala**; depois é só reabrir o programa.

## O que vai

| Recurso | Estado |
|---|---|
| Posição, corte e trilha | ✅ exatos, vídeo e áudio |
| Seleção parcial | ✅ só os takes selecionados |
| Anchor Point, Position, Scale, Rotation, Opacity | ✅ estáticos e animados (curva real: ease, Bézier, hold — amostrada e reduzida) |
| Ease editável no Inspector | ✅ chaves com tangentes (não assadas) |
| Flip H/V, escala não uniforme | ✅ |
| Velocidade constante, clipe aparado | ✅ |
| Speed ramp / Time Remap (AE) | ✅ timemap com ease editável |
| Time Remap do Premiere | ✅ lido do `.prproj` (o DOM não expõe) |
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
- **Parenting, expressões, 3D real** — camada 3D sai achatada (aviso); motion blur não vai.
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
- A UI de retime do Resolve achata o ease se você clicar nela (comportamento do Resolve — re-export preserva).
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

**A2R Link** copies clips from Adobe Premiere Pro / After Effects straight into a DaVinci Resolve Studio timeline — no XML, no AAF. Timeline position, tracks, Motion/Inspector keyframes (with real easing), speed, reverse, freeze frames, blend modes, ~66 transitions (real Resolve types incl. Fusion transitions), video/audio fades, ~60 video effects (native Resolve FX, incl. animated params via Fusion comps), ~40 Fairlight audio effects, titles, adjustment layers, nested content and markers — all with per-feature warnings instead of silent drops. Windows tested; macOS installer included (unverified). Panels check GitHub Releases and self-update with one click.
