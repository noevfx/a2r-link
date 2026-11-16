# Changelog — A2R Link

Versões em SemVer, em português. Release publicada é imutável: correção vira novo PATCH.

## Não lançado

**Novo (auto-update + marca)**
- **Atualização automática**: o painel checa `releases/latest` do GitHub (`noevfx/a2r-link`, override `"repo"` no config.json) ao abrir e a cada 6h; versão nova → cartão "Atualizar agora" que baixa o zip do release, extrai em `%LOCALAPPDATA%\Programs\A2R Link` (macOS: `Application Support/NoeVFX`) e roda o `install.py` de lá — um clique, depois é só reabrir o programa. Sem release ou sem net: silêncio. `bridge.py check-update`/`self-update` (semver real, asset `.zip` ou zipball).
- **Marca**: logo no cabeçalho do painel (`img/logo.png`); manifests sincronizados com `version.txt`.

**Correção (revisão SWE2MAX ×2)**
- **P0**: transição de vídeo quebrava a normalização inteira — `pretty, cat` ficou após `continue` (UnboundLocalError; e se um áudio passasse antes, o vídeo ia como `AUDIO_FADE`).
- AE: params de efeito usavam matchName cru (`ADBE X-0001`) — nenhum convertia; agora preferem `pp.name`. Chaves de efeito em precomp expandida remapeadas ao tempo do pai. Camada de áudio AE com efeito → aviso. 3D/motion blur → avisos.
- PR reader: `mkTime` auto-contido (a ponte não tem o helper do painel — `samples` voltavam vazios em silêncio); `val()` não trunca mais arrays (cores `[r,g,b]` chegavam como `[r,g]` → DropShadow cor/SplitTone morriam sem contar drop).
- Blend: `SOFT_LIGHT`/`HARD_LIGHT` casavam errado (enum sem `_`); `_BLEND_NORM` normaliza.
- Adjustment layer junto de título nunca era realocado (faltava `_ins`) — agora casa por Start exato.
- Efeito animado sem tool Fusion: aviso corrigido ("perdido", antes dizia "vai estático" — falso); `ConnectInput` checa retorno e tenta `Source`/`Input`; `SetKeyFrames` no formato verificado `{frame:{Value:v}}` via `inp.SetSource`.
- Mapas de áudio filtram `TransitionType` (item-transição podia sombrear clipe em `SetFades`/`AddEffect`); `_fx_desc` com lista vazia não quebra mais; `_conv_val` animado com try por amostra; rótulos e código morto limpos.

**Novo (rodada gaps)**
- **Blend modes**: `CompositeMode` do Resolve por clipe — leitores coletam (PR: enum do Opacity; AE: `blendingMode` enum 5212+), tabela PR/AE → enum do Resolve verificada por roundtrip DRT (Screen=5 etc.). Dissolve e modos de matte do AE ficam de fora com aviso.
- **Params de efeito animados**: chaves de param OFX não serializam no blob grupo-50 (campo-10 é normalizado fora pelo Resolve — provado). Caminho real: `AddFusionComp` + tool `ofx.<ns>.<Camel>` + `BezierSpline` por param — chaves preservadas no roundtrip DRT. Leitores agora emitem `keys`/`samples` de params animados; o efeito animado vai pra Fusion comp do clipe (estáticos continuam no Inspector via blob).
- **Escala pixel→normalizado medida**: `HStrength/VStrength` do GaussianBlur segue `sigma_px = 0.1 * dim_do_frame * S^2` (calibrado com step-edge sintético + `ExportFrame`; erro <1%). `Blurriness` (px) do Premiere → `sqrt(σ/(0.1·dim))`; Blurriness tratado como raio ≈ 2.5σ (aproximação documentada). BoxBlur usa a mesma lei (não medida individualmente).
- **Efeitos de áudio**: reader coleta componentes além de Volume/Panner; ~40 nomes do Premiere mapeados para Fairlight FX (`AddEffect('audio', id)` — verificado aplicar e sobreviver ao DRT). Params vão com default + aviso.
- **Params novos por plugin** (unidade provada no schema): Sharpen→`sharpen` (1–5), UltraSharpen→`sharpenStrength`, Glow→`threshold`/`brightness`, Vignette→`size`, Emboss→`power`, Dent→`strength`, BoxBlur→`Iterations`.
- **Máscaras detectadas**: layer AE com máscara agora avisa explicitamente (`numMasks`).

**Limitações novas documentadas**: params/direção de transição não são expostos pela API (transição vai com defaults do template — a Fusion comp da transição é acessível mas os templates não publicam UserControls); máscaras/track mattes/tracking ficam fora com aviso ou documentados.

**Novo**
- **Transições nativas** (Premiere): criadas pós-reimport via `TimelineItem.AddTransition` com os **tipos reais do Resolve** — verificado: Edge Wipe e Dip To Color pousam como wipe/dip de verdade, não dissolve. Mapeadas: Cross/Film Dissolve, Additive/Non-Additive Dissolve, Dip to Black/White (→ Dip To Color; branco sai preto + aviso — API não expõe a cor), Morph Cut → Smooth Cut, Wipe → Edge Wipe, Push/Slide/Split/iris/wipes nomeados. Áudio entre clipes: Constant Power/Gain, Exponential Fade → crossfade nativo (blob DRT). Não mapeadas → Cross Dissolve + aviso.
- **Fades de ponta solta**: transição com clipe de um lado só (antes ignorada) vira fade — vídeo: `AddTransition` na borda (fade in/out nativo); áudio: `SetFades` (FadeIn/FadeOut verificados).
- **Valores de efeito** (Premiere e After): leitores emitem `{nome, params}`; `_FX_PARAMS` converte os mapeados com unidade provada pelo schema OFX (`INPN_Min/MaxAllowed` colhido — `tests/fx_params.json`, 19 plugins): ângulos em graus, percentuais → 0–1, cores RGB, checkboxes. Pixel-strengths (ex.: Blurriness px → HStrength 0–1) sem escala honesta ficam no default + aviso "param(s) sem conversao"; params animados vão estáticos + aviso.
- **Documento `RECURSOS.md`**: mapa completo de recursos (feito/em validação/roadmap) + roteiro de material de teste.

**Validação pendente**: transição real numa sequência do Premiere (o lado DRT foi provado: `Cross Dissolve` insere e re-exporta intacto na posição/duração certas).

**Novo (efeitos)**
- **Efeitos de vídeo** (Premiere e After): nomes de efeito viram **plugins Resolve FX** nativos no Inspector — escritos direto no `EffectFiltersBA` (grupo-50 do blob, decifrado por diff de DRT). Tabela de 20 plugin-ids verificados por roundtrip; matchName `ADBE X`/`AE.ADBE X n` normalizado para o nome amigável. Params: mecanismo de encode decifrado e provado (tag 2=double etc. — `HStrength` roundtripu `0.92`), mas escalas por plugin não mapeadas → efeitos chegam com **defaults + aviso**. Não mapeados (Lumetri, terceiros) viram aviso explícito. Efeito desligado no AE não copia.

**Novo (18/11)**
- **Markers de clipe**: source markers do Premiere (lidos do `.prproj`, coleção `DVAMarker`) e markers de layer do After chegam no Resolve como clip markers coloridos (`TimelineItem.AddMarker` após o reimport — não serializam no DRT). Filtrados pela janela de mídia do take; posição respeita speed/reverso/rampa.
- **Ease editável no Inspector** (Premiere e After): curvas de Motion/transform com ease viram keys `0x0d` + tangentes Hermite no blob — editáveis no Resolve, não assadas (desvio medido ≤ 0.3 px no roundtrip real). Subdivisão adaptativa até 32 keys quando a curva não fecha com os pontos originais.
- **Texto posicionado**: gráficos de texto do Premiere viram Text+ com transform estático (posição/escala/rotação/opacidade); transform animado cai estático com aviso.
- **Nested completo**: sub-sequências agora herdam speed ramp e markers do `.prproj` por sub-seq (recursivo); textos dentro de nested são resgatados como Text+.
- **Avisos novos**: reverso + Time Remap no mesmo clipe (rampa não entra); transform animado em título.

- **Freeze frame**: "Frame Hold"/"Insert Frame Hold Segment" do Premiere (lido do `.prproj` — o efeito é invisível no DOM) e layer com `timeStretch = 0` do After viram timemap plano (quadro congelado) — verificado de ponta a ponta no Resolve. Áudio linkado não congela (igual ao Premiere). Combinado com velocidade/reverso/rampa: o freeze vence com aviso.

**Correção (18/11)**
- Propriedades animadas dentro de sequência aninhada não deslocam mais (props são domínio mídia — o offset de sequência era aplicado indevidamente).
- Timeline nova com fps inteiro sai com a taxa certa (`24.0` era rejeitado silenciosamente pelo `SetSetting` do Resolve).
- Clipboard enriquecido (markers/labels/rampas de sub-seqs) não é mais apagado pela reamostragem do painel — `remap-info` devolve os dados e o painel os mantém; o paste sempre relê o `.prproj` por segurança.
- Títulos/ajustes no modo timeline-existente não caem mais em cima do conteúdo antigo (a zona vazia parte do fim real da timeline).
- Markers de camadas dentro de precomp saem na posição certa (eram lidos no domínio da sub-comp).
- Áudio ligado a um clipe congelado toca normal (não herda mais o timemap plano).

## 0.1.4 — 17/11/2026

**Novo**
- **Seletor de destino no painel**: `Nova timeline` (padrão) ou `Timeline de mesmo nome` — adiciona os takes na timeline do Resolve que tem o nome da sequência/composição, mantendo posição e trilha originais; clipe na mesma posição/trilha é substituído pelo novo, os demais ficam intactos (sem ripple). Se a timeline não existe, cria uma nova com aviso.
- **Timeline nova com a configuração da origem**: resolução e frame rate vêm da sequência do Premiere ou da composição do After (ex.: comp 1080x1920 @ 29.97 vira timeline 1080x1920 @ 29.97), não mais da timeline aberta no Resolve.

**Correção**
- Sequência vertical 1080x1920 não cai mais numa timeline 4K herdada do projeto.
- No modo timeline-existente, take com velocidade/remap não desloca os vizinhos (a duração final entra pelo patch DRT, sem ripple).

## 0.1.3 — 16/11/2026

**Novo**
- **Áudio copiado junto com o vídeo** (Premiere e After): os clipes de áudio ligados chegam na timeline do Resolve nas trilhas de áudio correspondentes, com posição e duração exatas. Volume do clipe (`AudioVolume`, em dB), pan (`AudioPan`), fades de início/fim (`SetFades` nativo) e **keyframes de volume** (fades por chave) vão junto. Mídia só de áudio também é copiada.
- **Speed ramp editável no Resolve**: o timemap agora vai na forma **eased** nativa do Studio 21 — os nós do Time Remapping do Premiere/After viram pontos de velocidade esparsos com alças de ease, que aparecem como uma rampa editável de verdade no Inspector (antes: ~60 pontos amostrados por quadro). As influências de ease lidas do `.prproj`/do AE são convertidas nas alças. Sem nós disponíveis, cai na amostragem densa de antes.
- O áudio linkado a um clipe com rampa recebe o **mesmo timemap** do vídeo (fica em sincronia).

**Correção**
- O `remap_nodes` era apagado pelo painel na segunda gravação do clipboard (a reamostragem reescrevia o objeto em memória por cima do enriquecido pelo `remap-info`): agora os nós são transportados pelo painel junto com a curva.

**Notas técnicas**
- Descoberto no DRT: `Sm2TiAudioClip` usa o mesmo `<In>` codificado e o mesmo `MediaTimemapBA` do vídeo; `EffectFiltersBA` de áudio é o grupo **124** (param 95 = volume dB, 97/98 = fades) — mesmas chaves `f10` das props de vídeo.
- `probe_audio.py`: sonda que decifrou o formato de áudio no Resolve aberto (volume/pan/fades nativos, `<In>` e timemap aparado/velocidade).

## 0.1.2 — 16/11/2026

**Novo**
- **Versão Mac**: o release agora traz as pastas `Windows/` e `Mac/` lado a lado, cada uma autocontida com instalador e desinstalador (`INSTALAR.command`/`DESINSTALAR.command` executáveis no Mac, `.bat` no Windows). Mesmos painéis, mesmo script do DaVinci, caminhos do sistema resolvidos na instalação.
- **Relatório de debug**: qualquer erro no painel gera sozinho um zip com ambiente, versão, log, `clipboard.json` e `config.json`. O cartão de erro mostra "Relatório para o suporte" — um clique abre a pasta com o arquivo já selecionado, pronto para o beta tester enviar.
- **Speed ramp do Premiere com curvas**: Time Remapping (incluindo Beziers) é lido do `.prproj` — só dos takes copiados, sem varrer o projeto — e reproduzido no DaVinci quadro a quadro com curva monotônica contínua. Quando há rampa, o painel faz uma segunda leitura guiada pela curva para amostrar Motion/Opacidade nos tempos de mídia exatos.
- Aviso "salve o projeto" só aparece quando existe rampa **e** alterações não salvas (o arquivo `.prproj` é que guarda a curva).

- **Bilíngue automático**: a interface, os erros, os avisos, o relatório de debug e os instaladores saem em português ou inglês conforme o idioma do sistema (`navigator.language` no painel, `Get-UICulture` no `.bat`, `AppleLocale` no `.command`, locale do sistema no Python). Linhas técnicas de protocolo (logs que o painel faz parse) ficam fixas em português.

**Correção**
- O painel continuava sem achar a configuração: a cópia guardada dentro do próprio painel era procurada na pasta errada (no CEP, `__dirname` já é a raiz do painel, não a pasta `js`). Agora o instalador embute a configuração no painel (`js/config.js`), que passa a abrir sem depender de ler arquivo nem de variável de ambiente. A busca em arquivo continua como plano B, com o caminho certo da cópia interna.
- Os Detalhes passam a mostrar um diagnóstico na abertura do painel (usuário, APPDATA, `__dirname` e quais arquivos esperados existem), para investigar por que a pasta `%APPDATA%\NoeVFX` some ou não é lida.
- Domínios de tempo do remap: os nós do Time Remapping são em tempo do clipe, e agora são avaliados assim — clipe com rampa fora do frame zero e clipe aparado no meio da curva saem corretos; antes a curva travava no último valor.
- Propriedades (Motion/Opacidade) sob rampa deixam de usar velocidade constante como aproximação: eram amostradas numa janela de mídia curta e congelavam cedo.
- Interface: o título não espreme mais com o cartão de resultado aberto, e o cartão rola sozinho em vez de empurrar o painel.
- O pacote do release passa a incluir `src/prproj.py` e o leitor de segunda passada (sem eles o remap não funcionava instalado pelo zip).
- Clipe com propriedade ausente não derruba mais a conversão (usa padrão: centro, 100%, 0°, opaco).

**Revisão externa aplicada** (segunda leitura de código, bugs reais corrigidos):
- Mac: o script do DaVinci ia para a pasta errada (`.../Support/Fusion/...` só existe no Windows; no Mac é `.../DaVinci Resolve/Fusion/Scripts`) — o item de menu não apareceria.
- Mac: os `.command` do zip saíam sem permissão de execução (zip criado no Windows precisa marcar o sistema como Unix) — duplo clique falharia.
- Premiere em português/outros idiomas perdia TODAS as propriedades: `displayName` é localizado ("Movimento"≠"Motion"). Agora a identificação usa `matchName` (nome interno estável) com inglês como plano B, e avisa quando não identifica.
- Clique em Enviar com o Python quebrado/movido podia colar DUAS vezes no DaVinci (eventos `error`+`close` chegam juntos) — callbacks agora disparam uma vez só.
- Reamostragem parcial apagava a rampa do clipe que falhava — a curva agora entra sempre, mesmo se uma propriedade falhar.
- A curva do remap usa as **influências de ease gravadas no .prproj** (antes descartadas): cada segmento é um Bézier com alça na direção da tangente monotônica e comprimento = influência% — reproduz o ease real em vez de achatar, sem risco de overshoot/reverso.
- Chaves de propriedade fora do trecho aparado viravam tempos negativos no DaVinci — agora são cortadas com aviso.
- Falhas silenciosas viraram aviso: keyframes sem reamostragem, `getValue()` falho (antes derrubava o paste inteiro), efeitos não convertidos, item sem par de injeção.
- Casamento take×rampa apertado para ~¼ de quadro a 60fps (antes podia trocar vizinhos em sequência 60p).
- Erros do After Effects não são mais atribuídos ao DaVinci no cartão.
- `getMediaPath()` vindo como `file://` é normalizado antes de chegar ao DaVinci.
- Desinstalar também remove os relatórios de debug gerados pelo painel.
- Mac `.command` procura `python3.14` antes do `python3` genérico (senão Python antigo instalado ganhava a frente).

## 0.1.1 — 16/11/2026

**Correção**
- O painel dizia "A instalação está incompleta" mesmo com tudo instalado e escondia o motivo real. Agora ele procura a configuração em vários lugares
  (pasta de dados do usuário, cópia dentro da própria pasta do painel, pasta pessoal e a pasta de dados do CEP), não depende de variável de ambiente,
  mostra o motivo exato nos Detalhes (que abrem sozinhos no erro) e o indicador mostra "sem configuração" em vez de ficar eternamente em "verificando".
- A pasta de dados (clipboard e logs) passa a vir da configuração, e o instalador grava uma cópia da configuração dentro de cada painel.

## 0.1.0 — 16/11/2026 (primeira versão)

Painéis CEP para o Premiere e o After Effects (2027) que enviam clipes/camadas direto para a timeline do DaVinci Resolve Studio 21.2, sem exportar XML.

**Leva para o DaVinci**
- Anchor Point, Position, Scale, Rotation e Opacity, estáticos e com keyframes (a curva real — ease, Bézier, hold — é amostrada e reduzida).
- Flip (escala negativa), escala não uniforme, camada 3D tratada como 2D.
- Corte, posição na timeline, várias trilhas, velocidade constante, clipe aparado.
- Time Remap e speed ramp do After Effects.
- Tudo aberto na timeline de edição, com os keyframes no Inspector (sem Fusion, sem compound clip).

**Organização no Media Pool**
- Bin com o nome do projeto › sub-bin com o nome da sequência/comp › mídia usada e timeline. Reenviar não sobrescreve (`Nome 2`).

**Painel**
- Botões Enviar ao DaVinci, Copiar e Colar; indicador de conexão com o DaVinci; resumo da seleção; cartão de resultado com avisos e erros em português simples.
- Script `Workspace > Scripts > Edit > A2R Link - Colar` dentro do DaVinci.

**Instalação**
- `INSTALAR.bat` (confere pré-requisitos) e `DESINSTALAR.bat` (remove painéis, script e configuração; não apaga timelines nem bins do DaVinci).

**Fora do escopo (de propósito)**: efeitos e plugins, track mattes, máscaras, parenting, expressões, 3D real.

**Limitações conhecidas**: Time Remap do Premiere (o Premiere não expõe por script); curvas Bézier editáveis dentro do DaVinci (vão como chaves lineares reduzidas, visualmente iguais); reverso e congelar quadro; painel não verificado clicando dentro dos programas (testado pelo código real do painel contra o Premiere, o After e o DaVinci).
