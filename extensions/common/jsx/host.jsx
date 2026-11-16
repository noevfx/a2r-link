// A2R Link - host ExtendScript (Premiere e After). Carregado uma vez pelo CEP; as funcoes sao chamadas sob demanda pelo painel.
//  nb_run(code)  : roda o corpo de um leitor (src/readers/*.jsx) com `return` e devolve JSON {success, data, error}
//  nb_resumo()   : resumo leve da selecao para o painel (chamado a cada ~2 s)
var NB_HOST_OK = "0.1.4";   // sonda: se o painel quebrar, evalScript("NB_HOST_OK") prova se este arquivo carregou

function mkTime(s) { var t = new Time(); t.seconds = s; return t; }   // o leitor do Premiere usa este helper

function nb_run(code) {
  var evalResult = null, errorMsg = null;
  try {
    if (typeof app.enableQE === "function") { try { app.enableQE(); } catch (e0) {} }
    evalResult = eval("(function() { " + code + " })()");
  } catch (err) {
    errorMsg = err.toString() + (err.line ? " (linha " + err.line + ")" : "");
  }
  try {
    return JSON.stringify({ success: errorMsg === null, data: evalResult, error: errorMsg });
  } catch (e2) {
    return JSON.stringify({ success: false, data: null, error: "Falha ao serializar: " + e2.toString() });
  }
}

function nb_resumo() {
  try {
    if (!app.project) { return JSON.stringify({ ok: false }); }
    var t, i;
    if (typeof app.project.activeSequence !== "undefined") {   // so o Premiere tem activeSequence (app.name vem undefined no Premiere)
      var q = app.project.activeSequence;
      if (!q) { return JSON.stringify({ ok: true, vazio: true, rotulo: "SEM_SEQUENCIA" }); }
      var tot = 0, sel = 0;
      for (t = 0; t < q.videoTracks.numTracks; t++) {
        for (i = 0; i < q.videoTracks[t].clips.numItems; i++) { tot++; if (q.videoTracks[t].clips[i].isSelected()) { sel++; } }
      }
      for (t = 0; t < q.audioTracks.numTracks; t++) {
        for (i = 0; i < q.audioTracks[t].clips.numItems; i++) { tot++; if (q.audioTracks[t].clips[i].isSelected()) { sel++; } }
      }
      return JSON.stringify({ ok: true, host: "PPRO", projeto: String(app.project.name), nome: q.name, total: tot, selecionados: sel });
    }
    var c = app.project.activeItem;
    if (!c || !(c instanceof CompItem)) { return JSON.stringify({ ok: true, vazio: true, rotulo: "SEM_COMP" }); }
    var totA = 0, selA = 0, L;
    for (i = 1; i <= c.numLayers; i++) {
      L = c.layer(i);
      if (L.source && L.source instanceof FootageItem && L.source.hasVideo) { totA++; if (L.selected) { selA++; } }
    }
    return JSON.stringify({ ok: true, host: "AEFT", nome: c.name, total: totA, selecionados: selA });
  } catch (e) {
    return JSON.stringify({ ok: false, erro: e.toString() });
  }
}
