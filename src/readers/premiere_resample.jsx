// Reamostrador do Premiere (ExtendScript ES3). Corpo de funcao (use `return`).
// 2a passada, SO para clipes com Time Remapping: o bridge (remap-info) leu a curva do .prproj
// e manda __REQ = {clips:[{track, start, tms:[[t_seq_abs, t_midia], ...]}]} — avaliamos cada
// propriedade nos tempos de MIDIA reais que cada quadro da timeline usa (Bezier/ease incluidos)
// e devolvemos samples2 = [[t_seq_abs, valor]] — ja no dominio da timeline, pronto pro normalizer.
var PT = (typeof __LANG !== "undefined" ? __LANG : "pt") === "pt";
function T(pt, en) { return PT ? pt : en; }
var q = app.project.activeSequence;
if (!q) { return {erro: T("sem sequencia ativa", "no active sequence")}; }
if (typeof __REQ === "undefined" || !__REQ.clips) { return {erro: T("sem pedido de reamostragem", "no resampling request")}; }

function num(v) { return Number(v); }
function val(v) { return (typeof v === "object" && v !== null) ? [num(v[0]), num(v[1])] : v; }
// mesma identificacao a prova de localizacao do premiere_read.jsx (manter em sincronia)
function nomeEstavel(o) {
  try { var m = String(o.matchName || ""); if (m) return m; } catch (e) {}
  return String(o.displayName || "");
}
function termina(nome, sufixo) {
  nome = nome.toLowerCase(); sufixo = sufixo.toLowerCase();
  return nome.length >= sufixo.length && nome.substr(nome.length - sufixo.length) == sufixo;
}
function ehComp(comp, interno, ingles) {
  var mn = nomeEstavel(comp);
  return mn == interno || termina(mn, "." + interno) || comp.displayName == ingles;
}
function findProp(comp, interno, ingles) {
  var i, p;
  for (i = 0; i < comp.properties.numItems; i++) {
    p = comp.properties[i];
    if (nomeEstavel(p) == interno || p.displayName == ingles) { return p; }
  }
  for (i = 0; i < comp.properties.numItems; i++) {
    p = comp.properties[i];
    if (termina(nomeEstavel(p), "." + ingles)) { return p; }
  }
  return null;
}
function readProp(pr, tms) {
  if (!pr) { return null; }
  var o = {}, varying = false;
  try { varying = pr.isTimeVarying(); } catch (e) {}
  if (varying) {
    var ks = pr.getKeys(), arr = [];
    for (var k = 0; k < ks.length; k++) { arr.push([ks[k].seconds, val(pr.getValueAtKey(ks[k]))]); }
    o.keys = arr;
    if (tms && tms.length) {
      var sm = [];
      for (var m = 0; m < tms.length; m++) { sm.push(val(pr.getValueAtTime(mkTime(tms[m][1])))); }
      o.samples = sm;
    }
  }
  try { o.value = val(pr.getValue()); } catch (e2) { o.value = null; }
  return o;
}

var LISTA = {
  "Motion":   [["Position", "AE.ADBE Motion.Position", "Position"], ["Scale", "AE.ADBE Motion.Scale", "Scale"],
               ["ScaleWidth", "AE.ADBE Motion.Scale Width", "Scale Width"], ["UniformScale", "AE.ADBE Motion.Uniform Scale", "Uniform Scale"],
               ["Rotation", "AE.ADBE Motion.Rotation", "Rotation"], ["Anchor", "AE.ADBE Motion.Anchor Point", "Anchor Point"],
               ["CropLeft", "AE.ADBE Motion.Crop Left", "Crop Left"], ["CropRight", "AE.ADBE Motion.Crop Right", "Crop Right"],
               ["CropTop", "AE.ADBE Motion.Crop Top", "Crop Top"], ["CropBottom", "AE.ADBE Motion.Crop Bottom", "Crop Bottom"]],
  "Opacity":  [["Opacity", "AE.ADBE Opacity.Opacity", "Opacity"]]
};

var res = [];
for (var r = 0; r < __REQ.clips.length; r++) {
  var req = __REQ.clips[r], tr = q.videoTracks[req.track - 1], alvo = null, i;
  if (tr) {
    for (i = 0; i < tr.clips.numItems; i++) {
      if (Math.abs(tr.clips[i].start.seconds - req.start) < 0.0005) { alvo = tr.clips[i]; break; }
    }
  }
  if (!alvo) { res.push({track: req.track, start: req.start, erro: "clipe nao achado"}); continue; }
  var props = {};
  for (var j = 0; j < alvo.components.numItems; j++) {
    var comp = alvo.components[j], lst = null;
    if (ehComp(comp, "Motion", "Motion")) lst = LISTA.Motion;
    else if (ehComp(comp, "Opacity", "Opacity")) lst = LISTA.Opacity;
    if (!lst) { continue; }
    for (var pi = 0; pi < lst.length; pi++) {
      var pr = readProp(findProp(comp, lst[pi][1], lst[pi][2]), req.tms);
      if (pr && pr.samples) {
        var s2 = [];
        for (var s = 0; s < pr.samples.length; s++) { s2.push([req.tms[s][0], pr.samples[s]]); }   // mesmo indice: tempo absoluto da sequencia
        pr.samples2 = s2;
        delete pr.samples;
      }
      if (pr) { props[lst[pi][0]] = pr; }
    }
  }
  res.push({track: req.track, start: req.start, props: props});
}
return {results: res};
