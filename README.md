# A2R Link

![versão](https://img.shields.io/badge/vers%C3%A3o-0.1.5-blue)
![plataforma](https://img.shields.io/badge/Windows-10%2F11-555)
![licença](https://img.shields.io/badge/licen%C3%A7a-gratuita-green)

**Mande a timeline inteira — ou só os clipes selecionados — do Premiere Pro e do After Effects direto pra timeline do DaVinci Resolve, com um clique.** Sem exportar arquivo nenhum: os clipes chegam prontos pra editar, com os keyframes e as curvas do jeito que você fez — sem virar Fusion, sem virar compound clip.

### Por que ele é diferente

- **Suas animações continuam animações** — posição, tamanho, rotação e opacidade chegam com as mesmas curvas que você fez: dá pra continuar mexendo no Resolve em vez de refazer do zero. A rampa de velocidade vai com **os mesmos keyframes que você criou** (Editável, padrão) ou **um keyframe a cada quadro** (Precisa) — você escolhe no painel. E a rampa do Premiere sai mesmo o Premiere não deixando ler isso por fora: o A2R pega a curva direto do arquivo do projeto. Nenhuma outra ponte gratuita faz isso.
- **Feito pra revisão de edição** — o cliente pediu alteração? Você ajusta no Premiere/After, seleciona só os clipes novos e manda de novo: cada um volta pro mesmo lugar, na mesma trilha, sem empurrar nada em volta. A timeline do Resolve vira um espelho da sua edição.
- **Transições e efeitos de verdade** — ~66 transições chegam como a transição real do Resolve (wipe é wipe, não dissolve disfarçado), ~60 efeitos de vídeo viram efeitos do próprio Resolve e ~40 efeitos de áudio viram efeitos do Fairlight. Animação de efeito vira uma comp do Fusion que você pode abrir e mexer.
- **A timeline nasce igual à origem** — se é vertical de reels, sai vertical; se é 29.97, sai 29.97. Sem configurar nada.
- **O que está por dentro vai junto** — sequência dentro de sequência e precomp vêm abertas, com velocidade, rampa e markers delas; títulos viram textos do Resolve no lugar certo; markers chegam coloridos; o áudio grudado no clipe acompanha a mesma velocidade.
- **Honesto** — se algo não tem como ir, o A2R avisa pelo nome em vez de fingir que foi.
- **Gratuito e aberto** — o código está aqui, instala com um instalador e se atualiza com um clique dentro do próprio painel.

Painéis pro Premiere e pro After + um script pro Resolve. Feito pela Noé VFX.

---

## Instalação

1. Baixe o zip da **[versão mais nova](../../releases/latest)**.
2. Extraia e rode `INSTALAR.bat` (Windows). No Mac, `INSTALAR.command`.
3. Reabra o Premiere/After: **Janela › Extensões › A2R Link**.
4. No DaVinci: **Workspace › Scripts › Edit › A2R Link - Colar**.

Precisa de: Premiere ou After, **DaVinci Resolve Studio** (a versão gratuita não tem a parte que o A2R usa) e Python 3.14+.

Para remover: `DESINSTALAR.bat` / `DESINSTALAR.command`.

## Uso

**Mandar clipes ou a timeline inteira** — no Premiere ou no After:

1. Selecione os clipes que quer mandar (ou não selecione nada: vai tudo) e clique **Enviar ao DaVinci** (ou **Copiar** + **Colar**).
2. Eles aparecem na timeline do Resolve, nos mesmos lugares e trilhas, organizados no Media Pool por projeto e sequência.

**Atualizar uma edição que já está no DaVinci** — o modo pra quem trabalha com revisão:

O projeto já foi pro Resolve e o cliente pediu alteração? Você troca os clipes no Premiere/After, seleciona **só os clipes novos** e manda de novo. O A2R acha a timeline de mesmo nome, **substitui só os clipes que mudaram, no mesmo lugar e trilha**, e deixa todo o resto intacto — sem empurrar, sem duplicar.

**Chaves do painel**:

- **Destino › Nova timeline** — cria uma timeline nova com o nome da sequência/comp, na resolução e no fps da origem. **Mesmo nome** — cola na timeline que já existe: substitui só os clipes que mudaram e mantém o resto. É o modo das revisões.
- **Rampa › Editável** (padrão) — a rampa chega **com os mesmos keyframes que você criou**: dá pra continuar mexendo nela no Resolve e ela fica bem perto da original.
- **Rampa › Precisa** — **um keyframe a cada quadro**: a curva enche de keyframes, mas sai igualzinha à original — pra quando ela tem que bater frame a frame.

**Auto-update**: o painel procura versão nova toda vez que abre. Quando sai, aparece um cartão — **um clique baixa e instala**; depois é só reabrir o programa.

## O que vai

| No Premiere/After você fez | No DaVinci chega |
|---|---|
| Cortou, posicionou e organizou os clipes em trilhas | ✅ igual — vídeo e áudio |
| Selecionou só alguns clipes | ✅ vão só eles (sem seleção, vai a timeline inteira) |
| Moveu, redimensionou, girou ou animou um clipe | ✅ keyframes com as mesmas curvas — dá pra continuar mexendo |
| Espelhou o clipe (flip) | ✅ |
| Acelerou ou desacelerou com velocidade constante | ✅ qualquer %, sem empurrar os vizinhos |
| Fez speed ramp / Time Remap | ✅ do jeito que você escolheu na chave: mesmos keyframes (Editável) ou um keyframe por quadro (Precisa) |
| Pôs o clipe ao contrário | ✅ |
| Congelou um quadro (Frame Hold) | ✅ |
| Misturou camadas com blend mode (Screen, Multiply...) | ✅ o mesmo modo no Resolve (sem equivalente → aviso) |
| Pôs transição entre clipes | ✅ ~66 viram a transição real do Resolve — dissolves, wipes, iris e as do Fusion (Shatter, Glitch, Crash Zoom, Page Curl...). Sem equivalente → aviso |
| Fade no começo ou no fim de um clipe | ✅ fade de verdade, vídeo e áudio |
| Crossfade de áudio entre clipes | ✅ |
| Mexeu no volume ou no pan (fixo ou animado) | ✅ |
| Pôs efeito de áudio | ✅ ~40 viram efeitos do Fairlight |
| Pôs efeito de vídeo | ✅ ~60 viram efeitos do próprio Resolve, com os valores que dá pra converter |
| Animou um parâmetro de efeito | ✅ vira uma comp do Fusion com as curvas |
| Fez texto/gráfico no Premiere | ✅ texto do Resolve no lugar certo (se o movimento for animado, sai fixo + aviso) |
| Pôs adjustment layer | ✅ Adjustment Clip do Resolve, na posição certa |
| Usou sequência aninhada ou precomp | ✅ o conteúdo de dentro aparece na timeline — com velocidade, rampa e markers |
| Marcou com markers | ✅ chegam com as cores |
| Deu cor (label) ao clipe | ✅ mesma cor no Resolve |
| Editou vertical ou em fps quebrado (reels, 29.97...) | ✅ a timeline nova nasce com a resolução e o fps da origem |
| Mandou de novo uma timeline que já existe | ✅ nunca sobrescreve — cria `Nome 2`, ou no modo Mesmo nome substitui só os clipes que mudaram |

## O que não vai (com aviso, nunca em silêncio)

- **Cor do Lumetri** — não passa. No Resolve a cor se faz na página Color; você refaz lá.
- **Efeito que só existe no Adobe** (de terceiros ou alguns do próprio) — fica de fora, com um aviso dizendo o nome dele.
- **Máscara, track matte e rastreamento** — não dá pra levar; o A2R detecta e avisa.
- **Parenting, expressões e 3D** — o 3D chega como 2D (com aviso); motion blur não vai.
- **Ajustes finos da transição** (direção, centro...) — a transição chega, mas com o visual padrão do Resolve.
- **Valor de efeito que não dá pra converter com segurança** — chega com o valor padrão + aviso (o blur converte certo).

## Como funciona (por dentro)

```
Premiere/AE (painel CEP + ExtendScript) → clipboard.json → bridge.py
   → normalizer.py (formato comum) → gen.py + drtlib.py
   → timeline temporária → export DRT → patch no arquivo do Resolve
   → reimport → timeline final no Resolve
```

- `src/readers/` — leitores ExtendScript (Premiere via ponte prmcp; AE via ExtendScript direto). O que o Premiere não expõe por script (Time Remap, Frame Hold) é lido do arquivo `.prproj` salvo.
- `src/drtlib.py` — encoder/decoder do formato DRT (protobuf-like): timemaps, keyframes com ease, efeitos nativos escritos no arquivo, transições.
- `src/gen.py` — monta a timeline no Resolve: API + patch do DRT + pós-import (markers, transições, fades, comps de efeitos animados).
- Atualizações: `bridge.py check-update` / `self-update` — release no GitHub → zip extraído em `%LOCALAPPDATA%\Programs\A2R Link` → `install.py` reponta a config.

## Limitações conhecidas

- **Testado no Windows**; tem instalador de Mac, mas ainda não foi testado num Mac de verdade.
- Se você mexer na rampa pela barra "Speed Change" do clipe no Resolve, a curva dela perde a suavização — é do Resolve, não nosso.
- A animação de um efeito pode sair do tempo certo quando o clipe tem rampa de velocidade.
- Raramente, uma transição antiga pode duplicar na borda de um clipe reenviado.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `extensions/` | o painel (o mesmo nos dois programas) + manifests PR/AE |
| `src/` | `bridge.py`, `normalizer.py`, `gen.py`, `drtlib.py`, `prproj.py`, leitores JSX |
| `resolve/` | script **A2R Link - Colar.py** |
| `tests/` | testes usados no desenvolvimento |
| `install.py`, `INSTALAR.*` | instalador multiplataforma |

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md) — o estado detalhado de desenvolvimento fica em [HANDOFF.md](HANDOFF.md) e o mapa de recursos em [RECURSOS.md](RECURSOS.md).

---

### English (summary)

**A2R Link** sends the whole timeline or just the selected clips from Adobe Premiere Pro / After Effects straight into a DaVinci Resolve Studio timeline — one click, no XML, no AAF. Re-sending updated clips replaces only what changed, in the same position and track — built for edit revisions. New timelines inherit the source resolution/fps (vertical reels stay vertical). Position, tracks, Motion/Inspector keyframes (real Bézier easing — stays editable in the Inspector), speed ramps (same keyframe count as the source, or one keyframe per frame — panel toggle; Premiere ramps read from the `.prproj` the DOM can't see), reverse, freeze frames, blend modes, ~66 transitions (real Resolve types incl. Fusion transitions), video/audio fades, ~60 video effects (native Resolve FX, incl. animated params via Fusion comps), ~40 Fairlight audio effects, titles, adjustment layers, nested content and markers — all with per-feature warnings instead of silent drops. Windows tested; macOS installer included (unverified). Panels check GitHub Releases and self-update with one click.
