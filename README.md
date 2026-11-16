# A2R Link

![versão](https://img.shields.io/badge/vers%C3%A3o-0.1.5-blue)
![plataforma](https://img.shields.io/badge/Windows-10%2F11-555)
![licença](https://img.shields.io/badge/licen%C3%A7a-gratuita-green)

**Mande a timeline inteira — ou só os clipes selecionados — do Adobe Premiere Pro e do After Effects direto para a timeline do DaVinci Resolve**, com um clique. Sem exportar XML, sem AAF: os clipes chegam abertos na timeline de edição, com os keyframes no Inspector como se você tivesse feito à mão — sem Fusion, sem compound clip.

### Por que ele é diferente

- **As curvas chegam vivas** — Position, Scale, Rotation e Opacity chegam com as alças Bézier originais no Inspector do Resolve: você continua editando a curva em vez de recomeçar do zero. A speed ramp vai com **a mesma quantidade de pontos de velocidade que você criou** (modo Editável, padrão) ou **quadro a quadro** (modo Precisa) — chave no painel. E a rampa do Premiere sai mesmo sem o Premiere oferecer isso por script: o A2R lê a curva direto do arquivo do projeto. Nenhuma ponte gratuita entrega isso.
- **Feito pra revisão de edição** — o cliente pediu alteração? Você ajusta no Premiere/After, seleciona só os clipes novos e manda de novo: o A2R substitui cada um na mesma posição e trilha, sem deslocar nada em volta. A timeline do Resolve vira um espelho da sua edição.
- **Transições e efeitos de verdade** — ~66 transições chegam como os tipos reais do Resolve (wipe é wipe, não dissolve disfarçado), ~60 efeitos viram efeitos nativos do Resolve no Inspector e ~40 efeitos de áudio viram efeitos do Fairlight. Parâmetro animado vira comp do Fusion com as chaves.
- **A timeline nasce igual à origem** — resolução e fps certos no primeiro envio: o vertical 1080×1920 de reels sai vertical, 29.97 sai 29.97.
- **O que está por dentro vai junto** — sequências aninhadas e precomps são abertas por dentro (herdando velocidade, rampa e markers); títulos viram Text+ posicionados; markers chegam coloridos; o áudio linkado acompanha o mesmo retime do vídeo.
- **Honesto por construção** — o que não tem equivalente no Resolve fica de fora com um aviso pelo nome, nunca um efeito falso ou um item sumido em silêncio.
- **Gratuito e aberto** — código-fonte aqui, um instalador e auto-update com um clique dentro do próprio painel.

Painéis para o Premiere e o After + um script para o Resolve. Feito pela Noé VFX.

---

## Instalação

1. Baixe o zip da **[última release](../../releases/latest)**.
2. Extraia e rode `INSTALAR.bat` (Windows). No Mac, `INSTALAR.command`.
3. Reabra o Premiere/After: **Janela › Extensões › A2R Link**.
4. No DaVinci: **Workspace › Scripts › Edit › A2R Link - Colar**.

Pré-requisitos: Premiere Pro e/ou After Effects, **DaVinci Resolve Studio** (a API de scripting que o projeto usa é exclusiva da versão Studio) e Python 3.10+.

Para remover: `DESINSTALAR.bat` / `DESINSTALAR.command`.

## Uso

**Enviar a timeline ou os clipes** — no Premiere ou no After:

1. Selecione os clipes que quer mandar (ou não selecione nada: vai a sequência/comp inteira) e clique **Enviar ao DaVinci** (ou **Copiar** + **Colar**).
2. Os clipes aparecem na timeline do Resolve, nas mesmas posições e trilhas, e no Media Pool organizados em `Projeto › Sequência/Comp`.

**Atualizar uma edição que já está no DaVinci** — o modo pra quem trabalha com revisão:

O projeto já foi pro Resolve e o cliente pediu alteração? Você troca os clipes no Premiere/After, seleciona **só os clipes novos** e manda de novo. O A2R acha a timeline de mesmo nome, **substitui só os clipes que mudaram, na mesma posição e trilha** e deixa todo o resto intacto — sem deslocar, sem duplicar. Cada ida e volta atualiza só o que mudou.

**Chaves do painel**:

- **Destino › Nova timeline** — cria uma timeline nova com o nome da sequência/comp, na resolução e no fps da origem. **Mesmo nome** — cola na timeline que já existe com esse nome: substitui só os clipes que mudaram e mantém o resto. É o modo das revisões.
- **Rampa › Editável** (padrão) — a rampa de velocidade chega com a **mesma quantidade de pontos que você criou**, com as alças: no Premiere são os próprios keyframes de velocidade; no After, os pontos são posicionados na curva para segurar a rajada. Fica fácil de mexer no Resolve e bem próxima do original.
- **Rampa › Precisa** — um ponto por quadro, sem alças: segue a curva original quadro a quadro, pra quando a rampa tem que bater exatamente.

**Auto-update**: o painel verifica se saiu versão nova no GitHub toda vez que abre (e a cada 6h). Quando sai, aparece um cartão — **um clique baixa e instala**; depois é só reabrir o programa.

## O que vai

| Recurso | Estado |
|---|---|
| Posição, corte e trilha | ✅ exatos, vídeo e áudio |
| Seleção parcial | ✅ só os clipes selecionados (ou a timeline inteira) |
| Revisão de edição | ✅ reenvio substitui só os clipes que mudaram, na mesma posição/trilha — o resto fica intacto |
| Anchor Point, Position, Scale, Rotation, Opacity | ✅ estáticos e animados — **as curvas chegam editáveis** no Inspector do Resolve |
| Flip H/V, escala não uniforme | ✅ |
| Velocidade constante, clipe aparado | ✅ qualquer %, sem deslocar os vizinhos |
| Speed ramp do After Effects | ✅ Editável: mesma quantidade de pontos que no AE (aproximada — o ease do Resolve arredonda cantos, não é Bézier livre; a rajada fica). Precisa: quadro a quadro |
| Speed ramp / Time Remap do Premiere | ✅ lida do arquivo do projeto (o Premiere não expõe por script) — Editável nos keyframes de velocidade (quase exato); Precisa quadro a quadro |
| Reverso | ✅ |
| Freeze frame | ✅ Frame Hold do Premiere e camada congelada do After |
| Blend modes | ✅ Screen, Multiply, Overlay, Soft Light etc. (modos sem equivalente → aviso) |
| Transições | ✅ ~66 nomes → tipos reais do Resolve: dissolves, wipes, iris + 41 transições do Fusion (Shatter, Glitch, Crash Zoom, Page Curl, Cube...). Sem equivalente → fica fora com aviso |
| Fade em ponta solta | ✅ fade in/out nativo de vídeo e de áudio |
| Fade de áudio entre clipes | ✅ Constant Power/Gain/Exponential → crossfade |
| Volume e pan de áudio | ✅ estáticos e animados |
| Efeitos de áudio | ✅ ~40 nomes → efeitos do Fairlight |
| Efeitos de vídeo | ✅ ~60 nomes → efeitos nativos do Resolve no Inspector |
| Parâmetros de efeito | ✅ quando a unidade converte — ângulos, porcentagens, cores, liga/desliga, intensidade de blur (escala medida) |
| Parâmetros **animados** | ✅ viram comp do Fusion com as curvas de animação |
| Texto/gráficos do Premiere | ✅ viram Text+ na posição certa (animação de transform → valor fixo + aviso) |
| Adjustment layers | ✅ viram Adjustment Clips do Resolve, realocados na posição |
| Nested sequences (PR) e precomps (AE) | ✅ abertas por dentro — herdam velocidade, rampa e markers |
| Markers | ✅ da sequência/comp e dos clipes/camadas, com as cores |
| Labels de clipe | ✅ cores do AE/Premiere |
| Resolução e fps da origem | ✅ timeline nova sai com a config certa |
| Reenvio | ✅ nunca sobrescreve — cria `Nome 2` ou substitui só os clipes que mudaram no modo Mesmo nome |

## O que não vai (de propósito — com aviso, nunca em silêncio)

- **Lumetri Color** — a rota certa seria o grade nativo do Resolve, não efeito convertido. Ficou fora de propósito.
- **Efeitos sem equivalente no Resolve** (terceiros, alguns nativos) — ficam fora com aviso pelo nome.
- **Track mattes, máscaras e tracking** — máscara do AE é detectada e avisada; a transferência real não existe.
- **Parenting, expressões, 3D real** — camada 3D sai como 2D (aviso); motion blur não vai.
- **Ajustes de transição** (direção do wipe, centro do iris, canto do page curl) — a API não expõe; chegam com o visual padrão do Resolve.
- **Intensidades em pixel sem escala confiável** — vão com o valor padrão + aviso (a escala do blur gaussiano foi medida e converte certo).

## Como funciona (por dentro)

```
Premiere/AE (painel CEP + ExtendScript) → clipboard.json → bridge.py
   → normalizer.py (formato comum) → gen.py + drtlib.py
   → timeline temporária → export DRT → patch no arquivo do Resolve
   → reimport → timeline final no Resolve
```

- `src/readers/` — leitores ExtendScript (Premiere via ponte prmcp; AE via ExtendScript direto). O que o Premiere não expõe por script (Time Remap, Frame Hold) é lido do arquivo `.prproj` salvo.
- `src/drtlib.py` — encoder/decoder do formato DRT (protobuf-like): timemaps, keyframes com ease, efeitos nativos escritos no blob, transições.
- `src/gen.py` — monta a timeline no Resolve: API + patch do DRT + pós-import (markers, transições, fades, comps de efeitos animados).
- Atualizações: `bridge.py check-update` / `self-update` — release no GitHub → zip extraído em `%LOCALAPPDATA%\Programs\A2R Link` → `install.py` reponta a config.

## Limitações conhecidas

- **Testado no Windows**; o instalador de Mac existe (`INSTALAR.command`) mas ainda não foi validado em hardware.
- Editar a rampa na barra "Speed Change" do Resolve remove as alças dela (comportamento do próprio Resolve).
- A animação de parâmetros de efeito pode desalinhar quando o clipe tem speed ramp.
- Em casos raros, uma transição antiga pode duplicar na borda de um clipe reenviado.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `extensions/` | painel (comum aos dois programas) + manifests PR/AE |
| `src/` | `bridge.py`, `normalizer.py`, `gen.py`, `drtlib.py`, `prproj.py`, leitores JSX |
| `resolve/` | script **A2R Link - Colar.py** |
| `tests/` | fixtures e sondas usadas no desenvolvimento |
| `install.py`, `INSTALAR.*` | instalador multiplataforma |

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md) — o estado detalhado de desenvolvimento fica em [HANDOFF.md](HANDOFF.md) e o mapa de recursos em [RECURSOS.md](RECURSOS.md).

---

### English (summary)

**A2R Link** sends the whole timeline or just the selected clips from Adobe Premiere Pro / After Effects straight into a DaVinci Resolve Studio timeline — one click, no XML, no AAF. Re-sending updated clips replaces only what changed, in the same position and track — built for edit revisions. New timelines inherit the source resolution/fps (vertical reels stay vertical). Position, tracks, Motion/Inspector keyframes (real Bézier easing — stays editable in the Inspector), speed ramps (same node count as the source, or frame-accurate — panel switch; Premiere ramps read from the `.prproj` the DOM can't see), reverse, freeze frames, blend modes, ~66 transitions (real Resolve types incl. Fusion transitions), video/audio fades, ~60 video effects (native Resolve FX, incl. animated params via Fusion comps), ~40 Fairlight audio effects, titles, adjustment layers, nested content and markers — all with per-feature warnings instead of silent drops. Windows tested; macOS installer included (unverified). Panels check GitHub Releases and self-update with one click.
