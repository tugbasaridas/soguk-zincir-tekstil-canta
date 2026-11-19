Chart.defaults.animation = false;
Chart.defaults.font.family = 'Inter, "Segoe UI", Roboto, Arial, sans-serif';
Chart.defaults.color = '#4F6676';

const C = { navy:'#102A3A', blue:'#2E7DA6', orange:'#E0702E', rust:'#A8481A', gray:'#7A8C96', line:'#D5E0E3' };
const RENK = { T1:'#7A8C96', T2:'#2E7DA6', T3:'#E0702E' };
const q = new URLSearchParams(location.search);
const S = { tab:q.get('tab')||'canli', tasarim:q.get('tasarim')||'T2', pcm:+(q.get('pcm')??1), ortam:+(q.get('ortam')??30),
            bozulma:q.get('bozulma')||'temiz', model:q.get('model')||'gbr', t:+(q.get('t')??90),
            kaynak:'sim', kayitMetin:null, kayitAd:null };
let OPT, RUN, MAT, charts = {}, timer = null;

const $ = id => document.getElementById(id);
const f = (v, d=1) => v == null ? '–' : v.toFixed(d).replace('.', ',');
const hm = m => `${Math.floor(m/60)}:${String(m%60).padStart(2,'0')}`;

async function api(p) { return (await fetch(p)).json(); }

async function init() {
  OPT = await api('/api/secenekler');
  fill('tasarim', OPT.tasarimlar.map(t => [t.kod, t.ad]), S.tasarim);
  fill('pcm', OPT.pcm.map(p => [p, `${f(p)} kg PCM`]), S.pcm);
  fill('ortam', OPT.ortam.map(o => [o, `${f(o,0)} °C`]), S.ortam);
  fill('bozulma', OPT.bozulmalar.map(b => [b.kod, b.ad]), S.bozulma);
  fill('model', OPT.modeller.map(m => [m.kod, m.ad]), S.model);
  $('dosya').onchange = async e => { const fl = e.target.files[0]; if (!fl) return; await kayitYukle(await fl.text(), fl.name); e.target.value = ''; };
  $('ornekBtn').onclick = ornekYukle;
  $('simBtn').onclick = () => { S.kaynak = 'sim'; S.kayitMetin = null; load(); };
  for (const id of ['tasarim','pcm','ortam','bozulma','model']) $(id).onchange = e => { S[id] = id==='pcm'||id==='ortam' ? +e.target.value : e.target.value; load(); };
  document.querySelectorAll('.tab').forEach(b => b.onclick = () => setTab(b.dataset.tab));
  $('zaman').oninput = e => { S.t = +e.target.value; drawLive(); };
  $('oynat').onclick = togglePlay;
  setTab(S.tab);
  MAT = await api('/api/karsilastirma');
  if (q.get('kayit') === 'ornek') return ornekYukle();
  await load();
}

async function ornekYukle() {
  const txt = await (await fetch('/static/ornek_kayit_formati.csv')).text();
  await kayitYukle(txt, 'ornek_kayit_formati.csv');
}

async function kayitYukle(txt, ad) {
  S.kaynak = 'kayit'; S.kayitMetin = txt; S.kayitAd = ad;
  await load();
}

function saatEt(m) {
  const b = RUN && RUN.ozet.baslangic;
  if (RUN && RUN.kaynak === 'kayit' && b) { const [hh, mm] = b.split(' ')[1].split(':').map(Number); const x = hh*60 + mm + m; return `${String(Math.floor(x/60)%24).padStart(2,'0')}:${String(x%60).padStart(2,'0')}`; }
  return hm(m);
}

function fill(id, opts, sel) {
  $(id).innerHTML = opts.map(([v, l]) => `<option value="${v}" ${String(v)===String(sel)?'selected':''}>${l}</option>`).join('');
}

function setTab(t) {
  S.tab = t;
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === t));
  document.querySelectorAll('.pane').forEach(p => p.classList.toggle('active', p.id === 'tab-' + t));
  if (RUN) { if (t === 'canli') drawLive(); if (t === 'karsilastirma') drawCmp(); if (t === 'sensor') drawSensor(); }
}

async function load() {
  const tas = OPT.tasarimlar.find(t => t.kod === S.tasarim);
  $('layers').innerHTML = `<b>${tas.ad}</b><br>${tas.katmanlar.join(' · ')}<br>R ≈ ${f(tas.R,2)} m²K/W`;
  $('ortam').disabled = $('bozulma').disabled = S.kaynak === 'kayit';
  if (S.kaynak === 'kayit') {
    const r = await fetch(`/api/kayit?tasarim=${S.tasarim}&pcm=${S.pcm}&model=${S.model}&ad=${encodeURIComponent(S.kayitAd)}`, { method:'POST', body:S.kayitMetin, headers:{'Content-Type':'text/csv'} });
    const d = await r.json();
    if (!r.ok) { $('ustat').className = 'ustat kayit'; $('ustat').textContent = 'Hata: ' + (d.detail || r.status); S.kaynak = 'sim'; return load(); }
    RUN = d;
    $('hint').textContent = 'Hazır kayıt modu: iç hava ve ortam değerleri yüklenen dosyadan gelir; boş ya da eksik dakikalar doldurulup “tahmini” olarak işaretlenir. Ürünün iç sıcaklığı ölçülmediği için yalnızca tahmin gösterilir.';
    $('ustat').className = 'ustat kayit';
    $('ustat').textContent = `Kaynak: ${S.kayitAd} · ${RUN.ozet.toplam} dk${RUN.ozet.baslangic ? ', başlangıç ' + RUN.ozet.baslangic : ''} · ${RUN.ozet.doldurulan} kayıp dakika`;
  } else {
    RUN = await api(`/api/kosu?tasarim=${S.tasarim}&pcm=${S.pcm}&ortam=${S.ortam}&bozulma=${S.bozulma}&model=${S.model}`);
    $('ustat').className = 'ustat'; $('ustat').textContent = 'Kaynak: simülasyon';
    $('hint').textContent = 'Veriler termal model ve sensör simülatöründen gelir; “ürün referansı” yalnızca doğrulama içindir, sahada ölçülmez.';
  }
  $('zaman').max = RUN.t_max;
  S.t = Math.min(S.t, +$('zaman').max); $('zaman').value = S.t;
  drawLive(); drawCmp(); await drawSensor();
}

function togglePlay() {
  if (timer) { clearInterval(timer); timer = null; $('oynat').textContent = '▶ Oynat'; return; }
  $('oynat').textContent = '❚❚ Durdur';
  timer = setInterval(() => { if (S.t >= +$('zaman').max) return togglePlay(); S.t += 2; $('zaman').value = S.t; drawLive(); }, 120);
}

function events(t) {
  const R = RUN, ev = [{ m:0, c:C.blue, x: R.kaynak === 'kayit'
    ? `Hazır kayıt yüklendi · ${R.baslik} · ${R.tasarim_ad}, ${f(R.pcm)} kg PCM · ${R.model_ad}`
    : `Teslimat başladı · ${R.tasarim_ad}, ${f(R.pcm)} kg PCM, ortam ${f(R.ortam,0)} °C · ${R.model_ad}` }];
  if (R.ozet.ofset_tahmini != null) ev.push({ m:0, c:C.blue, x:`Kalibrasyon: referans sensörle ofset +${f(R.ozet.ofset_tahmini,2)} °C bulundu ve düzeltildi` });
  let i = 0; const d = R.doldurulmus;
  while (i <= t) { if (d[i]) { let j = i; while (j+1 < d.length && d[j+1]) j++; if (i <= t) ev.push({ m:i, c:C.rust, x:`${saatEt(i)}–${saatEt(j)} arası ${j-i+1} kayıt alınamadı; doğrusal doldurma, “tahmini” olarak işaretlendi` }); i = j+1; } else i++; }
  const u = R.ozet.ilk_uyari_dk; if (u != null && u <= t) ev.push({ m:u, c:C.orange, x:`UYARI: 30 dk içinde ${f(R.esik,0)} °C eşiğine ulaşılması bekleniyor (tahmin ${f(R.tahmin[u],2)} °C)` });
  const g = R.ozet.gercek_asim_dk; if (g != null && g <= t) ev.push({ m:g, c:'#8E2F12', x:`Ürün ${f(R.esik,0)} °C eşiğini aştı (simülasyon referansı)` });
  return ev.sort((a,b) => b.m - a.m);
}

function drawLive() {
  const R = RUN, t = S.t, E = R.esik;
  $('saat').textContent = RUN.kaynak === 'kayit' && RUN.ozet.baslangic ? `saat ${saatEt(t)} (t = ${hm(t)})` : `t = ${hm(t)} sa`;
  const tah = R.tahmin[t];
  $('k-hava').textContent = `${f(R.ic_hava[t],2)} °C`;
  $('k-hava-s').innerHTML = R.doldurulmus[t] ? '<span class="flag">tahmini kayıt</span>' : 'ölçülen';
  $('k-ortam').textContent = `${f(R.ortam_sensor[t],1)} °C`;
  $('k-tahmin').textContent = `${f(tah,2)} °C`;
  $('k-tahmin-s').textContent = tah == null ? '' : `${saatEt(t+R.ufuk_dk)} için · eşiğe ${tah >= E ? 'ulaşıyor' : f(E - tah,2) + ' °C pay'}`;
  const nd = R.doldurulmus.slice(0, t+1).filter(Boolean).length;
  $('k-dolu').textContent = `${nd} / ${t+1}`;
  const b = $('banner');
  if (R.urun_referans && R.urun_referans[t] > E) { b.className = 'banner bad'; b.textContent = `Eşik aşıldı: ürün ${f(E,0)} °C’nin üzerinde`; }
  else if (tah != null && tah >= E) { b.className = 'banner warn'; b.textContent = `Uyarı: 30 dk içinde ${f(E,0)} °C eşiğine ulaşılması bekleniyor · tahmin ${f(tah,2)} °C`; }
  else { b.className = 'banner ok'; b.textContent = `Durum normal · 30 dk sonrası tahmin ${f(tah,2)} °C, eşik ${f(E,0)} °C`; }
  $('ch-sub').textContent = `${R.kaynak === 'kayit' ? 'Hazır kayıt: ' + R.baslik : R.bozulma_ad} · ${R.model_ad}`;

  const xs = R.t_dk.slice(0, t+1);
  const hava = xs.map(i => ({ x:i, y:R.ic_hava[i] }));
  const dol = xs.filter(i => R.doldurulmus[i]).map(i => ({ x:i, y:R.ic_hava[i] }));
  const ref = R.urun_referans ? xs.map(i => ({ x:i, y:R.urun_referans[i] })) : [];
  const tp = xs.filter(i => R.tahmin[i] != null).map(i => ({ x:i + R.ufuk_dk, y:R.tahmin[i] }));
  const ds = [
    { label:'İç hava sensörü', data:hava, borderColor:C.blue, borderWidth:2, pointRadius:0 },
    { label:'Doldurulan kayıt', data:dol, type:'scatter', backgroundColor:C.rust, pointRadius:3 },
    { label:'Ürün tahmini (+30 dk)', data:tp, borderColor:C.orange, borderWidth:2.5, borderDash:[7,5], pointRadius:0 },
    ...(ref.length ? [{ label:'Ürün (simülasyon referansı)', data:ref, borderColor:C.navy, borderWidth:2, pointRadius:0 }] : []),
    { label:`Eşik ${f(E,0)} °C`, data:[{x:0,y:E},{x:R.t_dk.length-1,y:E}], borderColor:'#8E2F12', borderWidth:1.5, borderDash:[4,4], pointRadius:0 },
  ];
  const ymax = Math.max(12, ...hava.map(p=>p.y), ...ref.map(p=>p.y), ...tp.map(p=>p.y)) + 1;
  chart('chLive', 'line', ds, { x:{ type:'linear', min:0, max:R.t_dk.length-1, ticks:{ stepSize:60, callback:v => saatEt(v) } }, y:{ min:2, max:2*Math.ceil(ymax/2), ticks:{ stepSize:2 }, title:{display:true, text:'°C'} } });

  $('log').innerHTML = events(t).map(e => `<li><span class="tm">${saatEt(e.m)}</span><span class="dot" style="background:${e.c}"></span><span>${e.x}</span></li>`).join('');
  const rows = []; for (let i = t; i > t-7 && i >= 0; i--) rows.push(i);
  $('kayit').innerHTML = rows.map(i => `<tr><td>${saatEt(i)}</td><td>${f(R.ic_hava[i],2)} °C</td><td>${f(R.ortam_sensor[i],1)} °C</td><td>${f(R.tahmin[i],2)} °C</td><td>${R.doldurulmus[i] ? '<span class="flag">tahmini</span>' : '<span class="okf">ölçüm</span>'}</td></tr>`).join('');
}

function cellColor(v) {
  if (v < 1) return ['#EAF2F5', C.navy]; if (v < 2) return ['#C7DDE6', C.navy]; if (v < 3) return ['#8DBBD0', C.navy];
  if (v < 4) return ['#2C6E8F', '#F4F7F6']; return ['#173F57', '#F4F7F6'];
}

function drawCmp() {
  const rows = [];
  for (const t of OPT.tasarimlar) for (const p of OPT.pcm) {
    const cells = OPT.ortam.map(o => { const r = MAT.sonuc.find(x => x.tasarim===t.kod && x.pcm_kg===p && x.ortam===o); const v = r.esik_suresi_h ?? 8; const [bg, fg] = cellColor(v); return `<td style="background:${bg};color:${fg}">${r.esik_suresi_h==null?'> 8':f(v)}</td>`; }).join('');
    rows.push(`<tr class="${t.kod===S.tasarim && p===S.pcm ? 'sel':''}"><td class="lbl">${t.kod} · ${f(p)} kg PCM</td>${cells}</tr>`);
  }
  $('hm').innerHTML = `<tr><th></th>${OPT.ortam.map(o => `<th>${f(o,0)} °C</th>`).join('')}</tr>` + rows.join('');
  $('cmp-sub').textContent = `${f(S.pcm)} kg PCM · ortam ${f(S.ortam,0)} °C`;
  const ds = OPT.tasarimlar.map(t => ({ label:t.ad, data:MAT.egriler[`${t.kod}|${S.pcm}|${S.ortam}`].map((y,i) => ({x:MAT.t_saat[i], y})), borderColor:RENK[t.kod], borderWidth:t.kod===S.tasarim?3.5:2, pointRadius:0 }));
  ds.push({ label:'Eşik 6 °C', data:[{x:0,y:OPT.esik},{x:8,y:OPT.esik}], borderColor:'#8E2F12', borderDash:[4,4], borderWidth:1.5, pointRadius:0 });
  chart('chCmp', 'line', ds, { x:{ type:'linear', min:0, max:8, ticks:{ stepSize:1, callback:v => v + ' sa' } }, y:{ title:{display:true, text:'Ürün sıcaklığı (°C)'} } });
}

async function drawSensor() {
  const rows = await api(`/api/sensor_karsilastirma?tasarim=${S.tasarim}&pcm=${S.pcm}&ortam=${S.ortam}&model=${S.model}`);
  $('sen-sub').textContent = `simülasyon · ${S.tasarim} · ${f(S.pcm)} kg · ${f(S.ortam,0)} °C`;
  drawModels();
  $('senTbl').querySelector('tbody').innerHTML = rows.map(r => `<tr${r.kod===S.bozulma?' style="background:#FBE3D3"':''}><td>${r.ad}</td><td><b>${f(r.mae,2)} °C</b></td><td>${r.doldurulan}</td><td>${r.ilk_uyari_dk==null?'–':hm(r.ilk_uyari_dk)}</td><td>${r.erken_uyari_dk==null?'–':r.erken_uyari_dk+' dk'}</td></tr>`).join('');
  const R = RUN;
  $('raw-sub').textContent = R.kaynak === 'kayit' ? 'Hazır kayıt: ' + R.baslik : R.bozulma_ad;
  const ham = R.t_dk.map(i => ({ x:i, y:R.ic_hava_ham[i] }));
  const dol = R.t_dk.filter(i => R.doldurulmus[i]).map(i => ({ x:i, y:R.ic_hava[i] }));
  chart('chRaw', 'line', [
    { label:'Ham ölçüm (boşluklar = kayıp paket)', data:ham, borderColor:C.blue, borderWidth:1.8, pointRadius:0, spanGaps:false },
    { label:'Doldurulan kayıt (tahmini)', data:dol, type:'scatter', backgroundColor:C.rust, pointRadius:2.5 },
    ...(R.urun_referans ? [{ label:'Ürün (simülasyon referansı)', data:R.t_dk.map(i => ({x:i, y:R.urun_referans[i]})), borderColor:C.navy, borderWidth:1.5, borderDash:[3,3], pointRadius:0 }] : []),
  ], { x:{ type:'linear', min:0, max:R.t_dk.length-1, ticks:{ stepSize:60, callback:v => saatEt(v) } }, y:{ title:{display:true, text:'°C'} } });
}

let MDL = null;
async function drawModels() {
  MDL = MDL || await api('/api/model_karsilastirma');
  const kodlar = Object.keys(MDL), durumlar = Object.keys(MDL[kodlar[0]].durumlar);
  const kisa = { 'Temiz sensör':'Temiz', 'Ofset + sapma (+0,5 °C, +0,15 °C/sa)':'Ofset + sapma', 'Ofset düzeltilmiş (regresyon)':'Ofset düzeltilmiş', '%15 paket kaybı (doldurulmuş)':'%15 paket kaybı', 'Sapma + kayıp birlikte':'Sapma + kayıp' };
  const enIyi = durumlar.map(d => Math.min(...kodlar.map(k => MDL[k].durumlar[d].MAE)));
  const naif = MDL[kodlar[0]].durumlar;
  $('mdlTbl').innerHTML = `<thead><tr><th>Model</th>${durumlar.map(d => `<th>${kisa[d] || d}</th>`).join('')}</tr></thead><tbody>` +
    kodlar.map(k => `<tr${k===S.model?' style="outline:2px solid #E0702E"':''}><td>${MDL[k].ad}</td>${durumlar.map((d,j) => { const v = MDL[k].durumlar[d].MAE; return `<td class="${v===enIyi[j]?'best':''}">${f(v,2)}</td>`; }).join('')}</tr>`).join('') +
    `<tr><td class="muted">Naif (ürün = iç hava)</td>${durumlar.map(d => `<td class="muted">${f(naif[d].MAE_naif,2)}</td>`).join('')}</tr></tbody>`;
}

function chart(id, type, datasets, scales) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), { type, data:{ datasets }, options:{ maintainAspectRatio:false, parsing:true,
    plugins:{ legend:{ position:'bottom', labels:{ boxWidth:18, boxHeight:3, font:{ size:12 } } } },
    scales:{ ...scales, x:{ ...scales.x, grid:{ color:'#E6EDEF' } }, y:{ ...scales.y, grid:{ color:'#E6EDEF' } } } } });
}

init();
