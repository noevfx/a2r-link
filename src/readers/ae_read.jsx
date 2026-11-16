// Leitor do After Effects (ExtendScript ES3). Corpo de funcao (use `return`). Ponte: %TEMP%\ae_bridge\task.json.
// Le as camadas de footage SELECIONADAS da comp ativa (ou todas se nada estiver selecionado). Dados brutos do AE:
// tempos em segundos da COMP; Position/Anchor em px; Scale %; Rotation graus (horario +); Opacity %.
var PT = (typeof __LANG !== "undefined" ? __LANG : "pt") === "pt";
function T(pt, en) { return PT ? pt : en; }
var comp = app.project.activeItem;
if (!comp || !(comp instanceof CompItem)) { return {erro: T("abra uma comp e selecione camadas", "open a comp and select layers")}; }

function val(v) {
  if (v instanceof Array) { var o = []; for (var i = 0; i < v.length; i++) { o.push(v[i]); } return o; }
  return v;
}
function readProp(pr, t0, t1, fps) {
  // amostra a curva REAL (ease/Bezier/hold/trajetoria espacial ja aplicados) a cada quadro entre t0 e t1
  if (!pr) { return null; }
  var o = {value: val(pr.value)};
  if (pr.expressionEnabled) { o.expression = true; }
  if (pr.numKeys > 0) {
    var ks = [];
    for (var k = 1; k <= pr.numKeys; k++) {
      ks.push({t: pr.keyTime(k), v: val(pr.keyValue(k)),
               inI: pr.keyInInterpolationType(k), outI: pr.keyOutInterpolationType(k)});
    }
    o.keys = ks;
    if (pr.numKeys > 1 && t1 > t0) {
      var sm = [], n = Math.round((t1 - t0) * fps);
      for (var f = 0; f <= n; f++) { var tt = t0 + f / fps; sm.push([tt, val(pr.valueAtTime(tt, false))]); }
      o.samples = sm;
    }
  }
  return o;
}
function readLayer(l, rate, depth) {
  var info = {name: l.name, index: l.index, enabled: l.enabled, startTime: l.startTime, inPoint: l.inPoint, outPoint: l.outPoint,
              stretch: l.stretch, threeD: l.threeDLayer, parent: l.parent ? l.parent.name : null,
              adjustment: l.adjustmentLayer, motionBlur: l.motionBlur, blendingMode: l.blendingMode,
              numMasks: l.mask ? l.mask.numProperties : 0,
              timeRemap: (l.timeRemapEnabled === true), mediaPath: null, props: {}, label: l.label};
  if (l.source && l.source instanceof CompItem) {
    info.isComp = true; info.subNumLayers = l.source.numLayers;
    if ((depth || 0) < 2) {   // precomp: le as camadas internas (flatten) — recursao limitada
      var subs = [];
      for (var si = 1; si <= l.source.numLayers; si++) { subs.push(readLayer(l.source.layer(si), l.source.frameRate, (depth || 0) + 1)); }
      info.subLayers = subs;
    }
    return info;
  }
  if (l.source && l.source instanceof FootageItem) {
    info.sourceW = l.source.width; info.sourceH = l.source.height; info.mediaFps = l.source.frameRate;
    info.hasVideo = l.source.hasVideo;
    try { if (l.source.mainSource instanceof FileSource) { info.mediaPath = l.source.mainSource.file.fsName; } } catch (e) {}
  } else { info.semFootage = true; }
  if (info.timeRemap) {   // Time Remap: amostra a funcao tempo-da-comp -> tempo-da-midia a cada quadro (ease/Bezier ja aplicados)
    var rmp = l.property("ADBE Time Remapping");
    if (rmp) {
      var nfr = Math.round((l.outPoint - l.inPoint) * rate), rs = [];
      for (var q = 0; q <= nfr; q++) { var tq = l.inPoint + q / rate; rs.push([tq, rmp.valueAtTime(tq, false)]); }
      info.remap = rs;
      // nos com ease temporal (influencia %) -> timemap "eased" nativo do Resolve (rampa editavel)
      try {
        var nk = rmp.numKeys, rks = [];
        for (var k = 1; k <= nk; k++) {
          rks.push({t: rmp.keyTime(k), v: rmp.keyValue(k),
                    iI: rmp.keyInTemporalEase(k)[0].influence / 100, iO: rmp.keyOutTemporalEase(k)[0].influence / 100});
        }
        info.remapKeys = rks;
      } catch (e6) {}
    }
  }
  // markers da camada (tempo no dominio da LAYER — verificado no normalizer)
  try {
    var _lm = l.marker;
    if (_lm && _lm.numKeys) {
      var _lms = [];
      for (var _mi = 1; _mi <= _lm.numKeys; _mi++) {
        var _mv = _lm.keyValue(_mi);
        _lms.push({t: _lm.keyTime(_mi), name: String(_mv.comment || ''), dur: _mv.duration || 0,
                   tipo: String(_mv.chapter ? 'Chapter' : 'Comment')});
      }
      if (_lms.length) info.markers = _lms;
    }
  } catch (eM) {}
  // audio da camada: "Audio Levels" em dB (chaves = fades)
  try {
    info.hasAudio = (l.hasAudio === true) && (l.audioEnabled !== false);
    if (info.hasAudio) { info.audio = readProp(l.property("ADBE Audio Levels"), l.inPoint, l.outPoint, rate); }
  } catch (e7) { info.hasAudio = false; }
  var tr = l.property("ADBE Transform Group");
  if (tr) {
    var pos = tr.property("ADBE Position");
    info.dimensionsSeparated = (pos && pos.dimensionsSeparated === true) ? true : false;
    if (info.dimensionsSeparated) {
      info.props.PositionX = readProp(tr.property("ADBE Position_0"), l.inPoint, l.outPoint, rate);
      info.props.PositionY = readProp(tr.property("ADBE Position_1"), l.inPoint, l.outPoint, rate);
    } else { info.props.Position = readProp(pos, l.inPoint, l.outPoint, rate); }
    info.props.Anchor = readProp(tr.property("ADBE Anchor Point"), l.inPoint, l.outPoint, rate);
    info.props.Scale = readProp(tr.property("ADBE Scale"), l.inPoint, l.outPoint, rate);
    info.props.Rotation = readProp(tr.property("ADBE Rotate Z"), l.inPoint, l.outPoint, rate);
    info.props.Opacity = readProp(tr.property("ADBE Opacity"), l.inPoint, l.outPoint, rate);
  }
  info.effects = [];
  try {
    var par = l.property("ADBE Effect Parade");
    if (par) {
      for (var ei = 1; ei <= par.numProperties; ei++) {
        try {
          var ef = par.property(ei);
          if (ef.enabled === false) continue;               // desligado de proposito: nao copia
          var mn = ""; try { mn = String(ef.matchName || ""); } catch (em) {}
          var fxo = {nome: mn || String(ef.name || ""), params: {}};
          try {
            for (var pi = 1; pi <= ef.numProperties && pi <= 60; pi++) {
              var pp = ef.property(pi);
              var pn = ""; try { pn = String(pp.name || ""); } catch (ep2) {}
              if (!pn) {
                try { pn = String(pp.matchName || ""); var dot = pn.lastIndexOf("."); if (dot >= 0) { pn = pn.substr(dot + 1); } } catch (ep) {}
              }
              if (!pn || fxo.params[pn] !== undefined) { continue; }
              var pv = null; try { pv = val(pp.value); } catch (ev) {}
              var pa = false; try { pa = pp.numKeys > 0; } catch (ev2) {}
              if (pv !== null || pa) {
                var fxp = {v: pv, anim: pa};
                if (pa) {
                  try {
                    var farr = [];
                    for (var ki = 1; ki <= pp.numKeys; ki++) {
                      try { farr.push([pp.keyTime(ki), val(pp.keyValue(ki))]); } catch (ek) {}
                    }
                    if (farr.length) fxp.keys = farr;
                  } catch (eks) {}
                }
                fxo.params[pn] = fxp;
              }
            }
          } catch (eps) {}
          info.effects.push(fxo);
        } catch (ee) {}
      }
    }
  } catch (efx) {}
  return info;
}
var sel = comp.selectedLayers, usar = [], i;
if (sel.length > 0) { usar = sel; } else { for (i = 1; i <= comp.numLayers; i++) { usar.push(comp.layer(i)); } }
var out = [];
for (i = 0; i < usar.length; i++) {
  out.push(readLayer(usar[i], comp.frameRate, 0));
}
var markers = [];
try {
  var _mk = comp.marker;
  for (var _i = 1; _i <= _mk.numKeys; _i++) {
    var _mv = _mk.keyValue(_i);
    markers.push({name: String(_mv.comment || ''), start: _mv.time, end: _mv.time + (_mv.duration || 0),
                  tipo: String(_mv.chapter ? 'Chapter' : 'Comment'), comentario: String(_mv.comment || '')});
  }
} catch (eM) {}
var projNome = ""; try { projNome = app.project.file ? decodeURI(app.project.file.name) : ""; } catch (ep) {}
return {project: projNome, comp: {name: comp.name, width: comp.width, height: comp.height, fps: comp.frameRate, duration: comp.duration, numLayers: comp.numLayers},
        selectedOnly: sel.length > 0, layers: out, markers: markers};
