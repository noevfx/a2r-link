// A2R Link - painel CEP (roda no Chromium/Node do painel).
// Copiar: le o programa e grava %APPDATA%\NoeVFX\clipboard.json. Colar: chama o Python do projeto (bridge.py paste) que monta a timeline no DaVinci Resolve Studio.
(function () {
  var fs = require("fs"), path = require("path"), cp = require("child_process"), os = require("os");
  var host = "";
  try { host = JSON.parse(window.__adobe_cep__.getHostEnvironment()).appName; } catch (e) {}
  var PR = host === "PPRO", PROG = PR ? "Premiere" : "After Effects";
  // idioma do SISTEMA (navigator.language): portugues ou ingles — tudo que o usuario ve passa por T()
  var PT = String(navigator.language || "pt").toLowerCase().indexOf("pt") === 0;
  var LANG = PT ? "pt" : "en";
  function T(pt, en) { return PT ? pt : en; }
  var UNID = T("clipe", "clip"), G = PR ? "o" : "a";
  if (!PR) { UNID = T("camada", "layer"); G = "a"; }
  function $(id) { return document.getElementById(id); }
  var ocupado = false, logTxt = "";

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function log(l) { logTxt += l + "\n"; $("log").textContent = logTxt; }
  function estado(t, cls) { $("estado").textContent = t; $("estado").className = cls || ""; }   // texto de maquina (os testes leem)
  function plural(n, u) { return n + " " + u + (n === 1 ? "" : "s"); }
  // A configuracao (python, bridge.py, leitores, pasta de dados) e procurada em varios lugares: a variavel APPDATA pode faltar no Node do CEP.
  function pastaBase() {    // onde mora a pasta NoeVFX em cada sistema (AppData\Roaming no Windows, Application Support no Mac)
    if (process.env.APPDATA) return process.env.APPDATA;
    if (process.platform === "darwin") { try { return path.join(os.homedir(), "Library", "Application Support"); } catch (e) {} }
    try { return path.join(os.homedir(), "AppData", "Roaming"); } catch (e) {}
    return os.tmpdir();
  }
  function candidatosConfig() {
    var l = [path.join(pastaBase(), "NoeVFX", "config.json")];
    l.push(path.join(__dirname, "config.json"));                            // no CEP __dirname e a raiz do painel
    l.push(path.join(__dirname, "..", "config.json"));                      // (se algum dia for a pasta js)
    try { l.push(path.join(os.homedir(), "AppData", "Roaming", "NoeVFX", "config.json")); } catch (e) {}
    try { l.push(path.join(os.homedir(), "Library", "Application Support", "NoeVFX", "config.json")); } catch (e) {}
    try {
      var u = window.__adobe_cep__.getSystemPath("userData");
      if (u) l.push(path.join(decodeURI(String(u).replace(/^file:\/\/\//, "")), "NoeVFX", "config.json"));
    } catch (e) {}
    return l;
  }
  function config() {
    if (window.A2R_CONFIG && window.A2R_CONFIG.python && window.A2R_CONFIG.bridge && window.A2R_CONFIG.readers) return window.A2R_CONFIG;   // embutida pelo instalador (js/config.js)
    var cands = candidatosConfig(), falhas = [], i, txt;
    for (i = 0; i < cands.length; i++) {
      try {
        txt = fs.readFileSync(cands[i], "utf-8").replace(/^﻿/, "");
        var c = JSON.parse(txt);
        if (!c.python || !c.bridge || !c.readers) throw new Error("faltam campos");
        return c;
      } catch (e) { falhas.push(cands[i] + " -> " + e.message); }
    }
    log(T("Nao consegui ler a configuracao. Caminhos tentados:", "Could not read the configuration. Tried paths:") + "\n  " + falhas.join("\n  "));
    throw new Error(T("Não consegui ler a configuração do A2R Link (" + falhas[0].split(" -> ")[1] + "). Rode o instalador de novo e reinicie o programa. Detalhes abaixo.",
                      "Could not read the A2R Link configuration (" + falhas[0].split(" -> ")[1] + "). Run the installer again and restart the app. Details below."));
  }
  function diagnostico() {
    function ex(f) { try { return fs.existsSync(f) ? "existe" : "NAO existe"; } catch (e) { return "erro: " + e.message; } }
    var u = ""; try { u = os.userInfo().username; } catch (e) {}
    log("diagnostico: usuario=" + u + " | sistema=" + process.platform + " " + os.release() + " | node=" + process.version +
        " | APPDATA=" + process.env.APPDATA + " | HOME=" + process.env.HOME + " | __dirname=" + __dirname + " | cwd=" + process.cwd());
    log("  config embutida (window.A2R_CONFIG): " + (window.A2R_CONFIG ? "sim" : "NAO"));
    candidatosConfig().forEach(function (f) { log("  " + f + " -> " + ex(f)); });
    var c = window.A2R_CONFIG; if (c) { log("  python: " + c.python + " -> " + ex(c.python)); log("  bridge: " + c.bridge + " -> " + ex(c.bridge)); log("  readers: " + c.readers + " -> " + ex(c.readers)); }
  }
  function pastaDados(c) {
    return c.dados || path.join(pastaBase(), "NoeVFX");
  }
  function clipPath(c) { return path.join(pastaDados(c), "clipboard.json"); }

  // ---- relatorio de debug: um zip com tudo que o suporte precisa, gerado na pasta de dados ----
  var debugArq = null;
  function crc32(buf) {
    if (!crc32.t) { var t = []; for (var n = 0; n < 256; n++) { var c = n; for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1); t[n] = c >>> 0; } crc32.t = t; }
    var c = 0xFFFFFFFF;
    for (var i = 0; i < buf.length; i++) c = crc32.t[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function zipIt(entradas) {   // entradas: [{nome, buf}] -> zip com deflate (sem dependencias)
    var zlib = require("zlib"), partes = [], centrais = [], off = 0;
    var agora = new Date(), dosT = ((agora.getHours() << 11) | (agora.getMinutes() << 5) | (agora.getSeconds() >> 1)) & 0xFFFF,
        dosD = (((agora.getFullYear() - 1980) << 9) | ((agora.getMonth() + 1) << 5) | agora.getDate()) & 0xFFFF;
    entradas.forEach(function (e) {
      var nome = Buffer.from(e.nome, "utf8"), dados = zlib.deflateRawSync(e.buf, { level: 9 }), crc = crc32(e.buf);
      var h = Buffer.alloc(30);
      h.writeUInt32LE(0x04034b50, 0); h.writeUInt16LE(20, 4); h.writeUInt16LE(0x0800, 6); h.writeUInt16LE(8, 8);
      h.writeUInt16LE(dosT, 10); h.writeUInt16LE(dosD, 12);
      h.writeUInt32LE(crc, 14); h.writeUInt32LE(dados.length, 18); h.writeUInt32LE(e.buf.length, 22);
      h.writeUInt16LE(nome.length, 26); h.writeUInt16LE(0, 28);
      centrais.push({ nome: nome, crc: crc, cs: dados.length, us: e.buf.length, off: off });
      partes.push(h, nome, dados); off += 30 + nome.length + dados.length;
    });
    var cds = [];
    centrais.forEach(function (cen) {
      var h = Buffer.alloc(46);
      h.writeUInt32LE(0x02014b50, 0); h.writeUInt16LE(20, 4); h.writeUInt16LE(20, 6); h.writeUInt16LE(0x0800, 8); h.writeUInt16LE(8, 10);
      h.writeUInt16LE(dosT, 12); h.writeUInt16LE(dosD, 14);
      h.writeUInt32LE(cen.crc, 16); h.writeUInt32LE(cen.cs, 20); h.writeUInt32LE(cen.us, 24);
      h.writeUInt16LE(cen.nome.length, 28); h.writeUInt32LE(cen.off, 42);
      cds.push(h, cen.nome);
    });
    var cd = Buffer.concat(cds), eocd = Buffer.alloc(22);
    eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(centrais.length, 8); eocd.writeUInt16LE(centrais.length, 10);
    eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(off, 16);
    return Buffer.concat(partes.concat([cd, eocd]));
  }
  function gerarDebug(motivo) {
    var c = null; try { c = config(); } catch (e) {}
    var pasta = pastaDados(c || {}); try { fs.mkdirSync(pasta, { recursive: true }); } catch (e) {}
    var agora = new Date(), z = function (n) { return (n < 10 ? "0" : "") + n; };
    var arq = path.join(pasta, "A2R-debug-" + agora.getFullYear() + z(agora.getMonth() + 1) + z(agora.getDate()) +
                        "-" + z(agora.getHours()) + z(agora.getMinutes()) + z(agora.getSeconds()) + ".zip");
    function ex(f) { try { return fs.existsSync(f) ? "existe" : "NAO existe"; } catch (e) { return "erro: " + e.message; } }
    var host = {}; try { host = JSON.parse(window.__adobe_cep__.getHostEnvironment()) || {}; } catch (e) {}
    var amb = "A2R Link " + (c && c.versao ? "v" + c.versao : "(versao desconhecida)") + " - relatorio de debug\n" +
      "data: " + agora.toString() + "\nmotivo: " + (motivo || "erro no painel") + "\n" +
      "app: " + (host.appName || "?") + " " + (host.appVersion || "") + " (" + PROG + ")\n" +
      "sistema: " + process.platform + " " + os.release() + " (" + os.type() + " " + os.arch() + ")\n" +
      "usuario: " + (function () { try { return os.userInfo().username; } catch (e) { return "?"; } })() + " | node " + process.version + "\n" +
      "__dirname: " + __dirname + "\ncwd: " + process.cwd() + "\nAPPDATA: " + process.env.APPDATA + "\nHOME: " + process.env.HOME + "\n\n" +
      "caminhos da configuracao:\n  " + candidatosConfig().map(function (f) { return f + " -> " + ex(f); }).join("\n  ") +
      "\n\nconfiguracao carregada: " + JSON.stringify(c) +
      "\npasta de dados: " + pasta + " -> " + ex(pasta);
    var entradas = [
      { nome: "LEIA-ME.txt", buf: Buffer.from(T(
        "Este arquivo tem as informacoes que o suporte do A2R Link precisa.\nMande ele junto com um print (ou descricao) do que aconteceu.\nNao precisa abrir: e so enviar o zip inteiro.\n",
        "This file has the information A2R Link support needs.\nSend it along with a screenshot (or description) of what happened.\nNo need to open it: just send the whole zip.\n"), "utf8") },
      { nome: "ambiente.txt", buf: Buffer.from(amb, "utf8") },
      { nome: "painel.log", buf: Buffer.from(logTxt || "(vazio)", "utf8") }];
    [["clipboard.json", "clipboard.json"], ["ultimo_colar.log", "ultimo_colar.log"], ["config.json", "config.json"]].forEach(function (par) {
      var f = path.join(pasta, par[0]);
      try { if (fs.existsSync(f)) entradas.push({ nome: par[1], buf: fs.readFileSync(f) }); } catch (e) {}
    });
    try { fs.writeFileSync(arq, zipIt(entradas)); log(T("relatorio de debug: ", "debug report: ") + arq); return arq; }
    catch (e) { log(T("nao consegui gerar o relatorio de debug: ", "could not create the debug report: ") + e.message); return null; }
  }
  function revelar(arq) {   // abre a pasta do arquivo com ele selecionado (Explorer / Finder)
    if (!arq) return;
    try {
      var p;
      if (process.platform === "darwin") p = cp.spawn("open", ["-R", arq], { detached: true, stdio: "ignore" });
      else if (process.platform === "win32") p = cp.spawn("explorer", ["/select," + arq], { detached: true, stdio: "ignore" });
      else p = cp.spawn("xdg-open", [path.dirname(arq)], { detached: true, stdio: "ignore" });
      p.on("error", function () {});   // spawn falha de forma assincrona tambem: sem ouvinte derruba o painel
      p.unref();
    } catch (e) {}
  }

  function card(tipo, titulo, extra) {
    if (tipo === "erro") { try { $("detalhes").open = true; } catch (e) {} }
    var r = $("resultado"); r.className = "cartao " + tipo;
    r.innerHTML = '<div class="valor">' + esc(titulo) + "</div>" + (extra || "");
    if (tipo === "erro") {   // todo erro gera o relatorio na hora; o botao so abre a pasta com ele selecionado
      debugArq = gerarDebug(titulo);
      if (debugArq) {
        r.innerHTML += '<button class="btnDebug" id="bDebug">' + T("Relatório para o suporte", "Support report") + '</button>' +
          '<div class="caminho">' + T("o clique abre a pasta com o arquivo selecionado — é só enviar", "click opens the folder with the file selected — just send it") + '</div>';
        var b = $("bDebug");
        if (b) b.onclick = function () {
          if (!debugArq || !fs.existsSync(debugArq)) debugArq = gerarDebug("botao debug");
          revelar(debugArq);
        };
      }
    }
  }

  // mensagens em portugues simples para os erros mais comuns
  function traduz(texto) {
    var t = texto || "";
    if (/after effects n[aã]o responde|ae nao responde|ae_bridge/i.test(t))
      return T("O After Effects não está respondendo. Reabra o After com a composição aberta e tente de novo.",
               "After Effects is not responding. Reopen it with the composition open and try again.");
    if (/n[aã]o responde|does not answer|SCRIPTING_UNAVAILABLE|scriptapp|Connection|ECONN/i.test(t))
      return T("O DaVinci não está respondendo. Abra o DaVinci Resolve Studio com um projeto aberto e confira em Preferences > General se External scripting está em Local.",
               "DaVinci is not responding. Open DaVinci Resolve Studio with a project open and check Preferences > General for External scripting = Local.");
    if (/timeline temporaria|temporary timeline|Failed to create timeline|CREATE_TIMELINE/i.test(t))
      return T("O DaVinci abriu um aviso na tela e travou. Feche o aviso (olhe os dois monitores) e envie de novo.",
               "DaVinci opened a dialog and froze. Close it (check both monitors) and send again.");
    if (/nao importou|could not import|FileNotFound|No such file/i.test(t))
      return T("Não achei o arquivo de mídia de algum clipe. Confira se ele está online e no mesmo lugar.",
               "Could not find the media file of a clip. Check that it is online and in the same place.");
    if (/Nada copiado/i.test(t)) return T("Ainda não há nada copiado. Clique em Copiar primeiro.", "Nothing copied yet. Click Copy first.");
    return T("Não deu certo. Abra Detalhes para ver o que aconteceu.", "It did not work. Open Details to see what happened.");
  }

  // ---- conexao com o DaVinci (indicador) ----
  function checaDavinci() {
    var c; try { c = config(); } catch (e) { $("conexao").className = "pilula off"; $("conexaoTxt").textContent = T("sem configuração", "no configuration"); return; }
    var saida = "", p;
    try { p = cp.spawn(c.python, [c.bridge, "status"], { windowsHide: true, cwd: path.dirname(c.bridge), env: Object.assign({}, process.env, { A2R_DADOS: pastaDados(c), A2R_LANG: LANG }) }); } catch (e) { return; }
    var timer = setTimeout(function () { try { p.kill(); } catch (e) {} }, 25000);
    p.stdout.on("data", function (d) { saida += d.toString("utf8"); });
    p.on("error", function () {   // python invalido/movido: sem este ouvinte a excecao derruba o contexto do painel
      clearTimeout(timer);
      $("conexao").className = "pilula off"; $("conexaoTxt").textContent = T("DaVinci não encontrado", "DaVinci not found");
    });
    p.on("close", function () {
      clearTimeout(timer);
      var ok = false, proj = "";
      try { var j = JSON.parse(saida.trim().split(/\r?\n/).pop()); ok = !!j.resolve; proj = j.projeto || ""; } catch (e) {}
      $("conexao").className = "pilula " + (ok ? "on" : "off");
      $("conexaoTxt").textContent = ok ? (T("DaVinci conectado", "DaVinci connected") + (proj ? " · " + proj : "")) : T("DaVinci não encontrado", "DaVinci not found");
    });
  }

  // ---- atualizacao automatica (GitHub releases) ----
  function checaUpdate() {
    var c; try { c = config(); } catch (e) { return; }
    var saida = "", p;
    try { p = cp.spawn(c.python, [c.bridge, "check-update"], { windowsHide: true, cwd: path.dirname(c.bridge), env: Object.assign({}, process.env, { A2R_DADOS: pastaDados(c), A2R_LANG: LANG }) }); } catch (e) { return; }
    var timer = setTimeout(function () { try { p.kill(); } catch (e) {} }, 20000);
    p.stdout.on("data", function (d) { saida += d.toString("utf8"); });
    p.on("error", function () { clearTimeout(timer); });
    p.on("close", function () {
      clearTimeout(timer);
      var j = null;
      try { j = JSON.parse(saida.trim().split(/\r?\n/).pop()); } catch (e) {}
      if (!j || !j.ok || !j.tem_nova) return;
      $("updRot").textContent = T("Nova versão " + j.nova + " (a sua é " + j.atual + ")", "New version " + j.nova + " (yours is " + j.atual + ")");
      $("updTxt").textContent = T("Tem uma versão nova do A2R Link no GitHub.", "There is a new version of A2R Link on GitHub.");
      $("updMini").textContent = "";
      $("upd").className = "cartao";
      $("bUpd").onclick = function () { selfUpdate(j); };
    });
  }

  function selfUpdate(j) {
    var c; try { c = config(); } catch (e) { return; }
    var b = $("bUpd");
    b.disabled = true;
    b.innerHTML = '<span class="gira"></span>' + T("Atualizando...", "Updating...");
    $("updMini").textContent = T("Baixando e instalando — isso pode levar um minuto.", "Downloading and installing — this may take a minute.");
    var p;
    try { p = cp.spawn(c.python, ["-u", c.bridge, "self-update"], { windowsHide: true, cwd: path.dirname(c.bridge), env: Object.assign({}, process.env, { A2R_DADOS: pastaDados(c), A2R_LANG: LANG }) }); }
    catch (e) { b.disabled = false; b.textContent = T("Atualizar agora", "Update now"); return; }
    var timer = setTimeout(function () { try { p.kill(); } catch (e) {} }, 300000);   // download grande tem folga
    var erros = "";
    p.stderr.on("data", function (d) { erros += d.toString("utf8"); log(d.toString("utf8").trim()); });
    p.stdout.on("data", function (d) { var t = d.toString("utf8").trim(); if (t) { $("updMini").textContent = t.split(/\r?\n/).pop(); log(t); } });
    p.on("error", function () { clearTimeout(timer); b.disabled = false; b.textContent = T("Atualizar agora", "Update now"); });
    p.on("close", function (code) {
      clearTimeout(timer);
      if (code === 0) {
        $("updTxt").textContent = T("Pronto! Versão " + j.nova + " instalada.", "Done! Version " + j.nova + " installed.");
        $("updMini").textContent = T("Feche e reabra o programa para carregar a nova versão.", "Close and reopen the app to load the new version.");
        b.className = "oculto";
      } else {
        $("updMini").textContent = T("A atualização falhou. Tente de novo ou baixe pelo GitHub.", "The update failed. Try again or download from GitHub.");
        b.disabled = false; b.textContent = T("Tentar de novo", "Try again");
        b.onclick = function () {
          if (window.cep && window.cep.util && j.url) { window.cep.util.openURLInDefaultBrowser(j.url); }
          else { selfUpdate(j); }
        };
      }
    });
  }

  // ---- resumo da selecao ----
  function resumo() {
    if (ocupado) return;
    window.__adobe_cep__.evalScript("nb_resumo()", function (res) {
      var r; try { r = JSON.parse(res); } catch (e) { return; }
      if (!r || !r.ok) { $("selRot").textContent = T(PR ? "Sequência" : "Comp", PR ? "Sequence" : "Comp"); $("selValor").textContent = T("abra um projeto", "open a project"); return; }
      if (r.vazio) { $("selRot").textContent = T(PR ? "Sequência" : "Comp", PR ? "Sequence" : "Comp"); $("selValor").textContent = r.rotulo === "SEM_SEQUENCIA" ? T("sem sequência ativa", "no active sequence") : (r.rotulo === "SEM_COMP" ? T("abra uma comp", "open a comp") : r.rotulo); return; }
      $("selRot").textContent = T(PR ? "Sequência" : "Comp", PR ? "Sequence" : "Comp") + " · " + r.nome;
      if (r.total === 0) $("selValor").textContent = T("sem " + UNID + "s de vídeo", "no video " + UNID + "s");
      else if (r.selecionados > 0) $("selValor").textContent = plural(r.selecionados, UNID) + T(" selecionad" + G + (r.selecionados === 1 ? "" : "s"), " selected");
      else $("selValor").textContent = T("nada selecionado: vai tudo (", "nothing selected: sending all (") + plural(r.total, UNID) + ")";
    });
  }

  // ---- copiar ----
  // Premiere: depois da leitura normal, o bridge (remap-info) procura Time Remapping no .prproj.
  // Se acha, o leitor faz uma 2a passada reamostrando as props NOS TEMPOS DE MIDIA REAIS da curva
  // (sem rampa nada disso roda: o fluxo comum continua instantaneo).
  function remapInfo(c, cb) {
    var p, saida = "";
    try { p = cp.spawn(c.python, ["-u", c.bridge, "remap-info"], { windowsHide: true, cwd: path.dirname(c.bridge), env: Object.assign({}, process.env, { A2R_DADOS: pastaDados(c), A2R_LANG: LANG }) }); }
    catch (e) { log("remap-info " + T("falhou", "failed") + ": " + e.message); return cb(null); }
    var timer = setTimeout(function () { try { p.kill(); } catch (e) {} }, 20000);
    var feito = false, fim = function (v) { if (feito) return; feito = true; clearTimeout(timer); cb(v); };   // 'error' e 'close' chegam juntos: uma resposta so
    p.stdout.on("data", function (d) { saida += d.toString("utf8"); });
    p.stderr.on("data", function (d) { log(d.toString("utf8").trim()); });
    p.on("error", function () { fim(null); });
    p.on("close", function (code) {
      if (code !== 0) { log("remap-info " + T("saiu com codigo", "exited with code") + " " + code); return fim(null); }
      var j = null;
      try { j = JSON.parse(saida.trim().split(/\r?\n/).pop()); } catch (e) {}
      if (!j) { log(T("remap-info: resposta invalida", "remap-info: invalid response")); return fim(null); }
      if (!j.ok) { log(T("speed ramp: nao consegui ler o .prproj (", "speed ramp: could not read the .prproj (") + (j.erro || "?") + ")"); return fim(null); }
      if (j.dirty) log(T("AVISO: projeto com alteracoes nao salvas — se mexeu na rampa depois de salvar, salve e copie de novo",
                        "WARNING: project has unsaved changes — if you edited the ramp after saving, save and copy again"));
      fim(j);
    });
  }
  function copiar(cb) {
    var c;
    try { c = config(); } catch (e) { estado("Instalacao incompleta", "err"); card("erro", e.message); return cb && cb(false); }
    var arq = path.join(c.readers, PR ? "premiere_read.jsx" : "ae_read.jsx"), code;
    try { code = fs.readFileSync(arq, "utf-8"); } catch (e) { estado("Nao achei o leitor", "err"); card("erro", T("Não achei o leitor: ", "Reader not found: ") + arq); return cb && cb(false); }
    estado("lendo", "");
    window.__adobe_cep__.evalScript("var __LANG = " + JSON.stringify(LANG) + ";\nnb_run(" + JSON.stringify(code) + ")", function (res) {
      var r;
      try { r = JSON.parse(res); } catch (e) { estado("Resposta invalida", "err"); card("erro", T("O " + PROG + " respondeu algo inesperado.", "The " + PROG + " answered something unexpected.")); log(res); return cb && cb(false); }
      if (!r.success) { estado("Erro ao ler", "err"); card("erro", T("Não consegui ler o " + PROG + ".", "Could not read " + PROG + ".")); log(r.error); return cb && cb(false); }
      var d = r.data, n = d && (PR ? (d.clips || []).length + (d.audio || []).length : (d.layers || []).length);
      if (!d || d.erro || !n) { estado("Nada para copiar", "err"); card("aviso", T("Nada para copiar", "Nothing to copy"), '<div class="caminho">' + T("Selecione " + UNID + "s de vídeo e tente de novo.", "Select video " + UNID + "s and try again.") + '</div>'); return cb && cb(false); }
      function grava() {
        d.destino = chDestino.on() ? "nova" : "existente";   // o destino e o tipo de rampa viajam no clipboard
        d.rampa = chRampa.on() ? "editavel" : "precisa";
        fs.mkdirSync(path.dirname(clipPath(c)), { recursive: true });
        fs.writeFileSync(clipPath(c), JSON.stringify({ source: PR ? "premiere" : "ae", data: d }, null, 1), "utf-8");
      }
      function finaliza() {
        estado("copiado: " + plural(n, UNID), "ok");
        log(T("copiado ", "copied ") + plural(n, UNID) + T(" de ", " from ") + (PR ? d.sequence.name : d.comp.name));
        card("ok", T(plural(n, UNID) + " copiad" + G + (n === 1 ? "" : "s"), plural(n, UNID) + " copied"), '<div class="caminho">' + esc(PR ? d.sequence.name : d.comp.name) + T(" · pronto para colar", " · ready to paste") + '</div>');
        cb && cb(true);
      }
      try { grava(); } catch (e) { estado("Nao consegui gravar", "err"); card("erro", T("Não consegui guardar o que foi copiado.", "Could not save what was copied.")); log(e.message); return cb && cb(false); }
      if (!PR) { finaliza(); return; }
      remapInfo(c, function (req) {
        if (req && req.data) { d = req.data; }   // clips enriquecidos (remap/markers/labels/sub-patches):
        // sem isto o grava() da reamostragem apagava o enriquecimento do arquivo
        if (!req || !req.clips || !req.clips.length) { finaliza(); return; }
        var rarq = path.join(c.readers, "premiere_resample.jsx"), rcode;
        try { rcode = fs.readFileSync(rarq, "utf-8"); } catch (e) { log(T("nao achei o reamostrador: ", "resampler not found: ") + rarq); finaliza(); return; }
        // clipe longo com rampa: um tempo por quadro x varias props pode congelar o Premiere —
        // afina a lista (mantem os nos exatos da curva, que sao poucos) ate ~3000 tempos
        var MAXT = 3000;
        req.clips.forEach(function (rc) {
          rc.tms_full = rc.tms;      // a curva CHEIA fica para o timemap; a afinada so guia a reamostragem das props
          if (rc.tms.length > MAXT) {
            var passo = Math.ceil(rc.tms.length / MAXT), fina = [];
            for (var i = 0; i < rc.tms.length; i += passo) fina.push(rc.tms[i]);
            if (fina[fina.length - 1] !== rc.tms[rc.tms.length - 1]) fina.push(rc.tms[rc.tms.length - 1]);
            rc.tms = fina;
          }
        });
        estado("reamostrando", "");
        window.__adobe_cep__.evalScript("var __LANG = " + JSON.stringify(LANG) + ";\nvar __REQ = " + JSON.stringify(req) + ";\nnb_run(" + JSON.stringify(rcode) + ")", function (res2) {
          var feitos = 0, remapados = 0;
          try {
            var r2 = JSON.parse(res2);
            if (r2 && r2.success && r2.data && r2.data.results) {
              r2.data.results.forEach(function (rr) {
                var rc = null, i;
                for (i = 0; i < req.clips.length; i++) { if (req.clips[i].track === rr.track && Math.abs(req.clips[i].start - rr.start) < 0.004) rc = req.clips[i]; }
                d.clips.forEach(function (c2) {
                  if (c2.track === rr.track && Math.abs(c2.start - rr.start) < 0.004) {
                    if (rc) {
                      c2.remap = rc.tms_full || rc.tms;      // a curva entra SEMPRE: sem ela o clipe colava como velocidade constante
                      if (rc.knots) c2.remap_nodes = { knots: rc.knots, absoluto: rc.absoluto };   // nos p/ timemap eased (rampa editavel)
                      remapados++;
                    }
                    if (rr.props) { Object.keys(rr.props).forEach(function (nm) { c2.props[nm] = rr.props[nm]; }); feitos++; }
                  }
                });
                if (!rr.props) { if (rr.erro) log(T("reamostragem: ", "resampling: ") + rr.erro + " (track " + rr.track + ")"); }
              });
            } else { log(T("reamostragem falhou: ", "resampling failed: ") + (r2 && r2.error ? r2.error : res2)); }
          } catch (e) { log(T("reamostragem falhou: ", "resampling failed: ") + e.message); }
          if (remapados || feitos) {
            log(T("speed ramp: ", "speed ramp: ") + plural(remapados || feitos, T("clipe", "clip")) + (feitos
              ? T(" com Time Remapping — propriedades reamostradas na curva exata", " with Time Remapping — properties resampled on the exact curve")
              : T(" com Time Remapping — curva anexada (reamostragem falhou)", " with Time Remapping — curve attached (resampling failed)")));
            try { grava(); } catch (e) { log(T("nao gravei a reamostragem: ", "could not save the resampling: ") + e.message); }
          }
          finaliza();
        });
      });
    });
  }

  // ---- colar ----
  function colar(cb) {
    var c;
    try { c = config(); } catch (e) { estado("Instalacao incompleta", "err"); card("erro", e.message); return cb && cb(false); }
    if (!fs.existsSync(clipPath(c))) { estado("Nada copiado", "err"); card("aviso", T("Ainda não há nada copiado", "Nothing copied yet"), '<div class="caminho">' + T("Clique em Copiar primeiro.", "Click Copy first.") + '</div>'); return cb && cb(false); }
    estado("montando", "");
    var p, bruto = "", buf = "", avisos = [], bin = null, sub = null, tl = null, n = 0;
    try { p = cp.spawn(c.python, ["-u", c.bridge, "paste"], { windowsHide: true, cwd: path.dirname(c.bridge), env: Object.assign({}, process.env, { A2R_DADOS: pastaDados(c), A2R_LANG: LANG }) }); }
    catch (e) { estado("Erro: python", "err"); card("erro", T("Não consegui iniciar o Python do A2R Link.", "Could not start the A2R Link Python.")); log(e.message); return cb && cb(false); }
    function linha(l) {
      if (!l.trim()) return; log(l); bruto += l + "\n"; var m;
      if (/^AVISO:\s*/.test(l)) avisos.push(l.replace(/^AVISO:\s*/, ""));
      else if ((m = /^bin "(.*)" > sub-bin "(.*)"$/.exec(l))) { bin = m[1]; sub = m[2]; }
      else if ((m = /^pronto: timeline "(.*)" com (\d+) clipe/.exec(l))) { tl = m[1]; n = parseInt(m[2], 10); }
    }
    function pedacos(chunk) { buf += chunk.toString("utf8"); var partes = buf.split(/\r?\n/); buf = partes.pop(); partes.forEach(linha); }
    p.stdout.on("data", pedacos); p.stderr.on("data", pedacos);
    var feitoC = false, fimC = function (ok) { if (feitoC) return; feitoC = true; cb && cb(ok); };   // 'error' + 'close' chegam juntos: uma resposta so (senao o Enviar cola duas vezes)
    p.on("error", function (e) { estado("Erro: " + e.message, "err"); card("erro", T("Não consegui iniciar o Python do A2R Link.", "Could not start the A2R Link Python.")); fimC(false); });
    p.on("close", function (code) {
      if (buf.trim()) linha(buf.trim());
      if (code === 0 && tl) {
        var extra = '<div class="caminho">' + (bin ? esc(bin) + " › " + esc(sub) : "Media Pool") + "</div>";
        if (avisos.length) extra += "<ul>" + avisos.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ul>";
        estado(T("pronto: timeline criada no DaVinci", "done: timeline created in DaVinci"), "ok");
        card(avisos.length ? "aviso" : "ok", T(plural(n, UNID) + " na timeline \"", plural(n, UNID) + " in timeline \"") + tl + "\"" + (avisos.length ? " · " + plural(avisos.length, T("aviso", "warning")) : ""), extra);
        fimC(true);
      } else {
        estado("falhou (codigo " + code + ")", "err");
        card("erro", traduz(bruto));
        fimC(false);
      }
    });
  }

  // chave liga/desliga de duas opcoes: ligada (azul, bolinha a direita) = opcao da direita. A escolha fica guardada no painel.
  function chave(id, guarda, dicaOn, dicaOff) {
    var b = $(id), esq = $(id + "Off"), dir = $(id + "On"), linha = $("row" + id.slice(2)), ligada = true;
    try { if (window.localStorage.getItem(guarda) === "0") ligada = false; } catch (e) {}
    function pinta() {
      b.className = "sw" + (ligada ? " on" : "");
      esq.className = "lado esq" + (ligada ? "" : " ativo");
      dir.className = "lado dir" + (ligada ? " ativo" : "");
      b.title = ligada ? dicaOn : dicaOff;
      try { b.setAttribute("aria-checked", ligada ? "true" : "false"); } catch (e) {}
    }
    function poe(v) {
      if (ocupado) return;
      ligada = !!v; pinta();
      try { window.localStorage.setItem(guarda, ligada ? "1" : "0"); } catch (e) {}
    }
    b.onclick = function () { poe(!ligada); };
    esq.onclick = function () { poe(false); };
    dir.onclick = function () { poe(true); };
    esq.title = dicaOff; dir.title = dicaOn;
    pinta();
    return { on: function () { return ligada; }, poe: poe,
             trava: function (t) { b.disabled = t; linha.className = "chave" + (t ? " travada" : ""); } };
  }
  var chDestino = chave("chDestino", "a2r_destino_nova",
    T("Sempre cria uma timeline nova no DaVinci", "Always creates a new timeline in DaVinci"),
    T("Adiciona/substitui os takes na timeline com o nome da " + (PR ? "sequência" : "composição"), "Adds/replaces the takes in the timeline named after the " + (PR ? "sequence" : "composition")));
  var chRampa = chave("chRampa", "a2r_rampa_editavel",
    T("Rampa de velocidade com os mesmos nós da origem e alças: fácil de editar, curva aproximada", "Speed ramp with the same nodes as the source, with handles: easy to edit, approximate curve"),
    T("Rampa de velocidade com um ponto por quadro: segue a origem quadro a quadro, difícil de editar", "Speed ramp with one point per frame: follows the source frame by frame, hard to edit"));
  window.A2R_CHAVES = { destino: chDestino, rampa: chRampa };   // usado pelos testes

  function fim() {
    ocupado = false;
    ["bCopiar", "bColar", "bEnviar"].forEach(function (id) { var e = $(id); if (e) e.disabled = false; });
    chDestino.trava(false); chRampa.trava(false);
    $("bEnviar").textContent = T("Enviar ao DaVinci", "Send to DaVinci");
    resumo(); checaDavinci();
  }
  function acao(fn, rotulo) {
    return function () {
      if (ocupado) return;
      ocupado = true; logTxt = ""; $("log").textContent = "";
      ["bCopiar", "bColar", "bEnviar"].forEach(function (id) { var e = $(id); if (e) e.disabled = true; });
      chDestino.trava(true); chRampa.trava(true);
      if (rotulo) $("bEnviar").innerHTML = '<span class="gira"></span>' + rotulo;
      card("aviso", T("Trabalhando...", "Working..."), "");
      fn(fim);
    };
  }
  $("bCopiar").onclick = acao(copiar);
  $("bColar").onclick = acao(colar);
  $("bEnviar").onclick = acao(function (f) { copiar(function (ok) { if (ok) colar(f); else f(); }); }, T("Enviando...", "Sending..."));

  // textos fixos da interface no idioma do sistema
  $("subtitulo").textContent = PROG + T(" para DaVinci Resolve", " to DaVinci Resolve");
  $("conexaoTxt").textContent = T("verificando", "checking");
  $("selRot").textContent = T("Selecionado", "Selected");
  $("selValor").textContent = T("lendo...", "reading...");
  $("bEnviar").textContent = T("Enviar ao DaVinci", "Send to DaVinci");
  $("bCopiar").textContent = T("Copiar", "Copy");
  $("bCopiar").title = T("Le o que esta selecionado (ou tudo, se nada estiver) e guarda", "Reads the selection (or everything, if nothing is) and stores it");
  $("bColar").textContent = T("Colar", "Paste");
  $("bColar").title = T("Monta no DaVinci o que foi copiado", "Builds in DaVinci what was copied");
  $("destinoRot").textContent = T("Destino", "Destination");
  $("chDestinoOff").textContent = T("Mesmo nome", "Same name");
  $("chDestinoOn").textContent = T("Nova timeline", "New timeline");
  $("rampaRot").textContent = T("Rampa", "Ramp");
  $("chRampaOff").textContent = T("Precisa", "Precise");
  $("chRampaOn").textContent = T("Editável", "Editable");
  try { document.querySelector("#detalhes summary").textContent = T("Detalhes", "Details"); } catch (e) {}
  try { var cv = config(); $("subtitulo").textContent = T("Adobe para DaVinci Resolve", "Adobe to DaVinci Resolve") + (cv && cv.versao ? " · v" + cv.versao : ""); } catch (e) {}
  log("A2R Link (" + PROG + ") " + T("carregado", "loaded"));
  try { diagnostico(); } catch (e) { log("diagnostico falhou: " + e.message); }
  resumo(); checaDavinci(); checaUpdate();
  setInterval(resumo, 2000);
  setInterval(function () { if (!ocupado) checaDavinci(); }, 12000);
  setInterval(checaUpdate, 21600000);   // re-checa a cada 6h com o painel aberto
})();
