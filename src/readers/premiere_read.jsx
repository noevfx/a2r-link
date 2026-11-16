// Leitor do Premiere (ExtendScript ES3). Corpo de funcao para o painel PR MCP Bridge (premiere_run / POST /run).
// Le os clipes SELECIONADOS da sequencia ativa (ou todos, se nada estiver selecionado) e devolve dados brutos do Premiere.
// Tempos em SEGUNDOS; Position/Anchor normalizados (0..1); sem converter nada aqui (conversao = normalizer.py).
var PT = (typeof __LANG !== "undefined" ? __LANG : "pt") === "pt";
function T(pt, en) { return PT ? pt : en; }
var q = app.project.activeSequence;
if (!q) { return {erro: T("sem sequencia ativa", "no active sequence")}; }
var TPS = 254016000000;
var seqInfo = {project: String(app.project.name), name: q.name, width: q.frameSizeHorizontal, height: q.frameSizeVertical, fps: TPS / Number(q.timebase)};
// o Time Remapping nao e legivel por script: o bridge le a curva do .prproj salvo/exportado (src/prproj.py)
try { seqInfo.path = String(app.project.path); } catch (e0) {}
try { seqInfo.dirty = !!qe.project.isDirty(); } catch (e1) { try { seqInfo.dirty = !!app.project.isDirty; } catch (e2) {} }

function num(v) { return Number(v); }
function val(v) {
  if (typeof v === "object" && v !== null && v.length) { var a = []; for (var i = 0; i < v.length; i++) { a.push(num(v[i])); } return a; }
  return v;
}
function mkTime(s) { var t = new Time(); t.seconds = s; return t; }   // self-contained: o bridge posta este arquivo cru na ponte
// displayName e LOCALIZADO (muda com a lingua do Premiere); matchName e o nome interno estavel.
// identifica componentes/props por matchName quando existe, com displayName em ingles como plano B.
function nomeEstavel(o) {
  try { var m = String(o.matchName || ""); if (m) return m; } catch (e) {}
  return String(o.displayName || "");
}
// casa por nome interno exato ou por sufixo ".Nome" (ex.: "AE.ADBE Motion"): nao confunde
// "Motion" com "Motion Graphics Template" nem "Scale" com "Scale Width".
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
    if (termina(nomeEstavel(p), "." + ingles)) { return p; }   // matchName "...Position", "...Scale Width" etc.
  }
  return null;
}
function readProp(pr, tms) {
  // tms = tempos de MIDIA (s) em que amostrar a curva real (Bezier/ease/hold ja aplicados pelo Premiere)
  if (!pr) { return null; }
  var o = {};
  var varying = false;
  try { varying = pr.isTimeVarying(); } catch (e) {}
  if (varying) {
    var ks = pr.getKeys() || [], arr = [];
    for (var k = 0; k < ks.length; k++) { try { arr.push([ks[k].seconds, val(pr.getValueAtKey(ks[k]))]); } catch (ek) {} }
    if (arr.length) o.keys = arr;
    if (tms && ks.length > 1) {
      var sm = [];
      for (var m = 0; m < tms.length; m++) { try { sm.push([tms[m], val(pr.getValueAtTime(mkTime(tms[m])))]); } catch (em) {} }
      if (sm.length) o.samples = sm;
    }
  }
  try { o.value = val(pr.getValue()); } catch (e2) { o.value = null; }
  return o;
}
function qeInfo(trackIdx, clipStartSec) {
  var out = {speed: 100, reversed: false, scaleToFrameSize: null};
  try {
    var qt = qe.project.getActiveSequence().getVideoTrackAt(trackIdx);
    for (var i = 0; i < qt.numItems; i++) {
      var qc = qt.getItemAt(i);
      if (qc.type == "Clip" && Math.abs(qc.start.secs - clipStartSec) < 0.0005) {
        out.speed = num(qc.speed) * 100;   // qe.speed e um fator (1 = 100%)
        out.reversed = (qc.reversed == true);
        out.scaleToFrameSize = (qc.scaleToFrameSize == true);
        break;
      }
    }
  } catch (e) { out.qeErro = String(e); }
  return out;
}

// extrai o dict bruto de um item de trilha de video. qeTrk = indice da trilha p/ qeInfo
// (-1 = pula QE: sub-sequencias nao sao ativas -> speed/reversed padrao). seqFps = fps da seq dona do item.
function clipInfo(c, trk, qeTrk, seqFps) {
  var info = {
    name: c.name, track: trk, mediaPath: null,
    start: c.start.seconds, end: c.end.seconds, inPoint: c.inPoint.seconds, outPoint: c.outPoint.seconds,
    duration: c.duration.seconds, enabled: !c.disabled, props: {}
  };
  try { info.mediaPath = c.projectItem ? c.projectItem.getMediaPath() : null; info.temPI = !!c.projectItem; } catch (e3) {}
  try {
    var md = c.projectItem.getProjectMetadata();
    var m = /VideoInfo[^>]*>\s*(\d+)\s*x\s*(\d+)/.exec(md);
    if (m) { info.sourceW = num(m[1]); info.sourceH = num(m[2]); }
  } catch (e4) {}
  try { var fi = c.projectItem.getFootageInterpretation(); info.mediaFps = fi.frameRate; } catch (e5) {}
  var qi = (qeTrk >= 0) ? qeInfo(qeTrk, c.start.seconds) : {speed: 100, reversed: false, scaleToFrameSize: null};
  info.speed = qi.speed; info.reversed = qi.reversed;
  info.scaleToFrameSize = qi.scaleToFrameSize; if (qi.qeErro) { info.qeErro = qi.qeErro; }
  // tempos de midia em que amostrar: um por quadro da sequencia ao longo do clipe (inPoint/outPoint vem esticados pela velocidade)
  var spd = qi.speed / 100, inSrc = c.inPoint.seconds * spd, nFr = Math.round((c.end.seconds - c.start.seconds) * seqFps);
  var tms = [];
  for (var f = 0; f <= nFr; f++) { tms.push(inSrc + (f / seqFps) * spd); }
  info.effects = [];
  var leuMotion = false, leuOpacity = false;
  for (var j = 0; j < c.components.numItems; j++) {
    var comp = c.components[j], cn = comp.displayName;
    if (ehComp(comp, "Motion", "Motion")) {
      leuMotion = true;
      info.props.Position = readProp(findProp(comp, "AE.ADBE Motion.Position", "Position"), tms);
      info.props.Scale = readProp(findProp(comp, "AE.ADBE Motion.Scale", "Scale"), tms);
      info.props.ScaleWidth = readProp(findProp(comp, "AE.ADBE Motion.Scale Width", "Scale Width"), tms);
      info.props.UniformScale = readProp(findProp(comp, "AE.ADBE Motion.Uniform Scale", "Uniform Scale"));
      info.props.Rotation = readProp(findProp(comp, "AE.ADBE Motion.Rotation", "Rotation"), tms);
      info.props.Anchor = readProp(findProp(comp, "AE.ADBE Motion.Anchor Point", "Anchor Point"), tms);
      info.props.CropLeft = readProp(findProp(comp, "AE.ADBE Motion.Crop Left", "Crop Left"), tms);
      info.props.CropRight = readProp(findProp(comp, "AE.ADBE Motion.Crop Right", "Crop Right"), tms);
      info.props.CropTop = readProp(findProp(comp, "AE.ADBE Motion.Crop Top", "Crop Top"), tms);
      info.props.CropBottom = readProp(findProp(comp, "AE.ADBE Motion.Crop Bottom", "Crop Bottom"), tms);
    } else if (ehComp(comp, "Opacity", "Opacity")) {
      leuOpacity = true;
      info.props.Opacity = readProp(findProp(comp, "AE.ADBE Opacity.Opacity", "Opacity"), tms);
      try {
        var bm = findProp(comp, "AE.ADBE Opacity.Blend Mode", "Blend Mode");
        if (bm) { info.blendMode = num(bm.getValue()); }
      } catch (eb) {}
    } else if (cn === "Text" || cn.indexOf("Text") === 0) {
      try {
        var st = findProp(comp, "Source Text", "Source Text");
        if (st) { info.texto = String(st.getValue()); }
      } catch (et) {}
    } else if (ehComp(comp, "Frame Hold", "Frame Hold") || cn.indexOf("Frame Hold") === 0) {
      try {
        var fh = findProp(comp, "Frame Hold Source Time", "Frame Hold Source Time");
        var fhv = fh ? num(fh.getValue()) : NaN;   // segundos de midia do quadro congelado
        if (isFinite(fhv)) { info.frameHold = fhv; }
        else { info.effects.push(nomeEstavel(comp)); }     // componente achado mas tempo ilegivel: avisa como nao convertido
      } catch (efh) {}
    } else {
      // nome interno estavel + valores dos params (pra o normalizer converter os mapeados)
      var fxo = {nome: nomeEstavel(comp), params: {}};
      try {
        var np = comp.properties.numItems;
        for (var k = 0; k < np && k < 60; k++) {
          var pr = comp.properties[k];
          var pn = nomeEstavel(pr), dot = pn.lastIndexOf(".");
          if (dot >= 0) { pn = pn.substr(dot + 1); }
          if (!pn) { try { pn = pr.displayName; } catch (en) { continue; } }
          if (!pn || fxo.params[pn] !== undefined) { continue; }
          var pv = null; try { pv = val(pr.getValue()); } catch (ev) {}
          var pa = false; try { pa = !!pr.isTimeVarying(); } catch (ev2) {}
          if (pv !== null || pa) {
            var fxp = {v: pv, anim: pa};
            if (pa) {
              try {
                var fks = pr.getKeys() || [], farr = [];
                for (var kk = 0; kk < fks.length; kk++) { try { farr.push([fks[kk].seconds, val(pr.getValueAtKey(fks[kk]))]); } catch (ekk) {} }
                if (farr.length) fxp.keys = farr;
              } catch (ek) {}
              if (tms && tms.length) {
                var fsm = [];
                for (var fm = 0; fm < tms.length; fm++) { try { fsm.push([tms[fm], val(pr.getValueAtTime(mkTime(tms[fm])))]); } catch (efm) {} }
                if (fsm.length) fxp.samples = fsm;
              }
            }
            fxo.params[pn] = fxp;
          }
        }
      } catch (ec) {}
      info.effects.push(fxo);
    }
  }
  if (!leuMotion && c.components.numItems) { info.avisoLeitura = "componente Motion nao identificado (Premiere localizado?) — propriedades padrao usadas"; }
  return info;
}

// projectItem que e sequencia? casa pelo nome em app.project.sequences e le os clipes de video dela
function leSubSeq(pi, depth) {
  if ((depth || 0) >= 2 || !pi) { return null; }
  for (var s = 0; s < app.project.sequences.numSequences; s++) {
    var sq = app.project.sequences[s];
    if (sq.name != pi.name) { continue; }
    var subFps = TPS / Number(sq.timebase);
    var r = {numTracks: sq.videoTracks.numTracks, numAudio: sq.audioTracks.numTracks, fps: subFps, clips: []};
    for (var st_ = 0; st_ < sq.videoTracks.numTracks; st_++) {
      var str_ = sq.videoTracks[st_];
      for (var si = 0; si < str_.clips.numItems; si++) {
        var sc = str_.clips[si];
        var info2 = clipInfo(sc, st_ + 1, -1, subFps);
        if (info2.temPI && !info2.mediaPath) {
          var n2 = leSubSeq(sc.projectItem, (depth || 0) + 1);
          if (n2) { info2.subSeq = true; info2.subSeqNome = sc.projectItem.name; info2.subNumTracks = n2.numTracks; info2.subClips = n2.clips; info2.subFps = n2.fps; }
        }
        r.clips.push(info2);
      }
    }
    return r;
  }
  return null;
}

// quais clipes? selecionados; se nenhum, todos
var anySel = false, t, i;
for (t = 0; t < q.videoTracks.numTracks; t++) {
  for (i = 0; i < q.videoTracks[t].clips.numItems; i++) { if (q.videoTracks[t].clips[i].isSelected()) { anySel = true; } }
}
for (t = 0; t < q.audioTracks.numTracks; t++) {
  for (i = 0; i < q.audioTracks[t].clips.numItems; i++) { if (q.audioTracks[t].clips[i].isSelected()) { anySel = true; } }
}
var clips = [];
for (t = 0; t < q.videoTracks.numTracks; t++) {
  var tr = q.videoTracks[t];
  for (i = 0; i < tr.clips.numItems; i++) {
    var c = tr.clips[i];
    if (anySel && !c.isSelected()) { continue; }
    var info = clipInfo(c, t + 1, t, seqInfo.fps);
    if (info.temPI && !info.mediaPath) {              // nested sequence ou gerador com projectItem
      var sub = leSubSeq(c.projectItem, 0);
      if (sub) {
        info.subSeq = true; info.subSeqNome = c.projectItem.name; info.subNumTracks = sub.numTracks;
        info.subClips = sub.clips; info.subAudioCount = sub.numAudio; info.subFps = sub.fps;
      }
    }
    clips.push(info);
  }
}
// markers de sequencia
var markers = [];
try {
  var _ms = q.markers, _nm = _ms ? _ms.numMarkers : 0;
  for (var _i = 0; _i < _nm; _i++) {
    var _m = _ms[_i];
    markers.push({name: String(_m.name || ''), start: _m.start.seconds, end: _m.end ? _m.end.seconds : _m.start.seconds,
                  tipo: String(_m.type || 'Comment'), comentario: String(_m.comments || '')});
  }
} catch (eM) {}
// trilhas de audio: clipes ligados acompanham a selecao (linked selection do Premiere)
var audios = [];
for (t = 0; t < q.audioTracks.numTracks; t++) {
  var tr = q.audioTracks[t];
  for (i = 0; i < tr.clips.numItems; i++) {
    var c = tr.clips[i];
    if (anySel && !c.isSelected()) { continue; }
    var info = {
      name: c.name, track: t + 1, mediaPath: null, speed: 100, reversed: false,
      start: c.start.seconds, end: c.end.seconds, inPoint: c.inPoint.seconds, outPoint: c.outPoint.seconds,
      enabled: !c.disabled, props: {}
    };
    try { info.mediaPath = c.projectItem ? c.projectItem.getMediaPath() : null; } catch (e3) {}
    try { var fi = c.projectItem.getFootageInterpretation(); info.mediaFps = fi.frameRate; } catch (e5) {}
    try {   // velocidade via QE (trilha de audio)
      var qa = qe.project.getActiveSequence().getAudioTrackAt(t);
      for (var qi = 0; qi < qa.numItems; qi++) {
        var qc = qa.getItemAt(qi);
        if (qc.type == "Clip" && Math.abs(qc.start.secs - c.start.seconds) < 0.0005) {
          info.speed = num(qc.speed) * 100; info.reversed = (qc.reversed == true); break;
        }
      }
    } catch (e4) {}
    var aspd = info.speed / 100, ainSrc = c.inPoint.seconds * aspd, anFr = Math.round((c.end.seconds - c.start.seconds) * seqInfo.fps);
    var atms = [];
    for (var f = 0; f <= anFr; f++) { atms.push(ainSrc + (f / seqInfo.fps) * aspd); }
    info.effects = [];
    for (var j = 0; j < c.components.numItems; j++) {
      var comp = c.components[j];
      if (ehComp(comp, "Volume", "Volume")) {
        info.props.Level = readProp(findProp(comp, "AE.ADBE Volume.Level", "Level"), atms);
      } else if (ehComp(comp, "Panner", "Panner")) {
        info.props.Pan = readProp(findProp(comp, "AE.ADBE Panner.Pan", "Pan"), atms) ||
                         readProp(findProp(comp, "AE.ADBE Panner.Balance", "Balance"), atms);
      } else {
        try { info.effects.push({nome: nomeEstavel(comp), params: {}}); } catch (e6) {}
      }
    }
    audios.push(info);
  }
}
// transicoes: colecoes por trilha (DOM normal), tempos em segundos de sequencia
var trans = [];
function leTransicoes(tr, tno, kind) {
  var n = 0;
  try { n = tr.transitions.numItems; } catch (e) { return; }
  for (var i = 0; i < n; i++) {
    var it = tr.transitions[i];
    try {
      trans.push({kind: kind, track: tno, name: it.name,
                  start: it.start.seconds, end: it.end.seconds});
    } catch (e2) {}
  }
}
for (t = 0; t < q.videoTracks.numTracks; t++) { leTransicoes(q.videoTracks[t], t + 1, "video"); }
for (t = 0; t < q.audioTracks.numTracks; t++) { leTransicoes(q.audioTracks[t], t + 1, "audio"); }
return {sequence: seqInfo, selectedOnly: anySel, clips: clips, audio: audios, transitions: trans, markers: markers};
