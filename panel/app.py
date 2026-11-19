"""Soğuk zincir izleme paneli — FastAPI arka ucu.

Çalıştırma (depo kök klasöründen):
    python -m uvicorn panel.app:app --port 8000
Sunucuda (Render, Codespaces vb.):
    uvicorn panel.app:app --host 0.0.0.0 --port $PORT
Tarayıcı: http://localhost:8000
"""
import os, sys, json, pickle, csv, io
from datetime import datetime
from functools import lru_cache
import numpy as np
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)
from termal_model import TASARIMLAR, ESIK, simule_et          # noqa: E402
from senaryolar import calistir, PCM_LIST, ORTAM_LIST          # noqa: E402
import tahmin as T                                              # noqa: E402

STATIC = os.path.join(os.path.dirname(__file__), "static")
CIKTI = os.path.join(KOK, "cikti")
TAS = {t.kisa: t for t in TASARIMLAR}

BOZULMALAR = {
    "temiz": ("Temiz sensör", dict()),
    "sapma": ("Ofset + sapma (düzeltmesiz)", dict(ofset=0.5, sapma_h=0.15)),
    "duzeltilmis": ("Ofset regresyonla düzeltilmiş", "duzelt"),
    "kayip": ("%15 paket kaybı", dict(kayip=0.15)),
    "hepsi": ("Sapma + paket kaybı", dict(ofset=0.5, sapma_h=0.15, kayip=0.15)),
}

_MODEL = {}


def model_al(tur="gbr"):
    """Eğitilmiş modeli diskten yükler; yoksa eğitip kaydeder."""
    if tur not in T.MODELLER:
        raise HTTPException(400, f"Bilinmeyen model: {tur}")
    if tur not in _MODEL:
        yol = os.path.join(CIKTI, f"model_{tur}.pkl")
        if os.path.exists(yol):
            _MODEL[tur] = pickle.load(open(yol, "rb"))
        else:
            _MODEL[tur] = T.egit(tur)
            pickle.dump(_MODEL[tur], open(yol, "wb"))
    return _MODEL[tur]


app = FastAPI(title="Soğuk Zincir İzleme Paneli")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _hazirla():
    # Varsayılan model açılışta hazırlanır; diğerleri ilk seçildiklerinde yüklenir/eğitilir.
    model_al("gbr")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/secenekler")
def secenekler():
    return dict(
        tasarimlar=[dict(kod=t.kisa, ad=t.ad, R=round(t.R_toplam, 3), UA=round(t.UA, 3),
                         katmanlar=[k[0] for k in t.katmanlar]) for t in TASARIMLAR],
        pcm=PCM_LIST, ortam=ORTAM_LIST, esik=ESIK,
        bozulmalar=[dict(kod=k, ad=v[0]) for k, v in BOZULMALAR.items()],
        modeller=[dict(kod=k, ad=v[0]) for k, v in T.MODELLER.items()],
    )


def ozellik_tum(s_hava, s_ort, UA, pcm):
    """Hazır kayıt için: kaydın sonuna kadar her dakika tahmin üret."""
    X, rows = [], []
    for i in range(30, s_hava.size):
        f = [s_hava[i - g] for g in T.GECIKMELER]
        f += [s_hava[i] - s_hava[i - 15], s_ort[i], i / 60, UA, pcm]
        X.append(f); rows.append(i)
    return np.array(X), np.array(rows)


def paketle(kaynak, baslik, tasarim, pcm, mdl, s_hava, s_hava_d, eksik, s_ort, urun, rows, p, t_max, ekstra):
    n = s_hava_d.size
    tahmin = [None] * n
    for r, v in zip(rows, p):
        tahmin[int(r)] = round(float(v), 3)
    gercek_asim = None
    if urun is not None:
        gercek_asim = next((i for i in range(n) if urun[i] > ESIK), None)
    ilk_uyari = next((int(r) for r, v in zip(rows, p) if v >= ESIK), None)
    return dict(
        kaynak=kaynak, baslik=baslik, tasarim=tasarim, tasarim_ad=TAS[tasarim].ad, pcm=pcm,
        model=mdl, model_ad=T.MODELLER[mdl][0], esik=ESIK, ufuk_dk=T.UFUK, t_max=t_max,
        t_dk=list(range(n)),
        ortam_sensor=[round(float(v), 3) for v in s_ort],
        ic_hava_ham=[None if e else round(float(v), 3) for v, e in zip(s_hava, eksik)],
        ic_hava=[round(float(v), 3) for v in s_hava_d],
        doldurulmus=[bool(e) for e in eksik],
        urun_referans=None if urun is None else [round(float(v), 3) for v in urun],
        tahmin=tahmin,
        ozet=dict(gercek_asim_dk=gercek_asim, ilk_uyari_dk=ilk_uyari,
                  erken_uyari_dk=None if (gercek_asim is None or ilk_uyari is None) else gercek_asim - ilk_uyari,
                  doldurulan=int(eksik.sum()), toplam=int(n), **ekstra),
    )


@lru_cache(maxsize=512)
def _kosu(tasarim, pcm, ortam, bozulma, mdl, seed):
    tas = TAS[tasarim]
    ad, bz = BOZULMALAR[bozulma]
    ofset_tahmini = None
    if bz == "duzelt":
        rng = np.random.default_rng(seed + 1)
        ofset_tahmini = T.kalibrasyon_ofseti(rng, 0.5)
        bz = dict(ofset=0.5 - ofset_tahmini, sapma_h=0.15)
    rng = np.random.default_rng(seed)
    _, out = simule_et(tas.UA, pcm, ortam, rng=rng)
    out = out[::T.ORNEK]
    s_hava, eksik = T.sensor(out[:, 1], rng, **bz)
    s_ort, _ = T.sensor(out[:, 0], rng)
    s_hava_d = T.doldur(s_hava, eksik)
    X, rows = T.ozellik(s_hava_d, s_ort, tas.UA, pcm)
    p = model_al(mdl).predict(X)
    hedef = out[rows + T.UFUK, 2]
    d = paketle("simulasyon", f"Simülasyon · ortam {ortam:g} °C · {ad}", tasarim, pcm, mdl,
                s_hava, s_hava_d, eksik, s_ort, out[:, 2], rows, p, out.shape[0] - 1 - T.UFUK,
                dict(mae=round(float(np.mean(np.abs(p - hedef))), 3),
                     ofset_tahmini=None if ofset_tahmini is None else round(ofset_tahmini, 3)))
    d.update(ortam=ortam, bozulma=bozulma, bozulma_ad=ad)
    return d


@app.get("/api/kosu")
def kosu(tasarim: str = "T2", pcm: float = 1.0, ortam: float = 30.0,
         bozulma: str = "temiz", model: str = "gbr", seed: int = 4242):
    return _kosu(tasarim, pcm, ortam, bozulma, model, seed)


def _zaman(v, t0):
    """Dakika sayısı ya da tarih-saat metnini başlangıçtan itibaren dakikaya çevirir."""
    v = v.strip()
    try:
        return float(v.replace(",", "."))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                dt = datetime.strptime(v, fmt)
                return dt
            except ValueError:
                pass
    raise HTTPException(400, f"Zaman okunamadı: {v!r} (dakika ya da 2026-07-15 08:00 biçimi)")


def _sayi(v):
    v = (v or "").strip().replace(",", ".")
    if v == "" or v.lower() in ("nan", "na", "null", "-"):
        return None
    return float(v)


@app.post("/api/kayit")
async def kayit(request: Request, tasarim: str = "T2", pcm: float = 1.0, model: str = "gbr",
                ad: str = "yüklenen kayıt"):
    """Hazır sıcaklık kaydı (CSV) yükler.

    Sütunlar: zaman, ic_hava, ortam  (isteğe bağlı: urun — doğrulama için)
    Ayırıcı virgül ya da noktalı virgül. Boş hücre ya da eksik dakika = kayıp paket.
    """
    metin = (await request.body()).decode("utf-8-sig")
    ayirici = ";" if metin.count(";") > metin.count(",") else ","
    okuyucu = csv.DictReader(io.StringIO(metin), delimiter=ayirici)
    alan = {k.strip().lower(): k for k in (okuyucu.fieldnames or [])}
    for gerekli in ("zaman", "ic_hava", "ortam"):
        if gerekli not in alan:
            raise HTTPException(400, f"CSV’de '{gerekli}' sütunu yok. Gerekli sütunlar: zaman, ic_hava, ortam")
    satirlar = list(okuyucu)
    if not satirlar:
        raise HTTPException(400, "CSV boş")
    zam = [_zaman(r[alan["zaman"]], None) for r in satirlar]
    if isinstance(zam[0], datetime):
        t0 = zam[0]; dk = [(z - t0).total_seconds() / 60 for z in zam]
    else:
        t0 = None; dk = [z - zam[0] for z in zam]
    n = int(round(max(dk))) + 1
    if n < 61:
        raise HTTPException(400, "Kayıt en az 60 dakika olmalı")
    if n > 24 * 60:
        raise HTTPException(400, "Kayıt en fazla 24 saat olabilir")
    hava = np.full(n, np.nan); ort = np.full(n, np.nan); urun = np.full(n, np.nan)
    for d, r in zip(dk, satirlar):
        i = int(round(d))
        if 0 <= i < n:
            v = _sayi(r[alan["ic_hava"]]); o = _sayi(r[alan["ortam"]])
            if v is not None: hava[i] = v
            if o is not None: ort[i] = o
            if "urun" in alan:
                u = _sayi(r[alan["urun"]])
                if u is not None: urun[i] = u
    eksik = np.isnan(hava)
    if eksik.all() or np.isnan(ort).all():
        raise HTTPException(400, "İç hava ya da ortam sütununda hiç değer yok")
    hava_d = T.doldur(np.nan_to_num(hava), eksik)
    ort_d = T.doldur(np.nan_to_num(ort), np.isnan(ort))
    tas = TAS[tasarim]
    X, rows = ozellik_tum(hava_d, ort_d, tas.UA, pcm)
    p = model_al(model).predict(X)
    u = None
    if not np.isnan(urun).all():
        u = T.doldur(np.nan_to_num(urun), np.isnan(urun))
    d = paketle("kayit", ad, tasarim, pcm, model, np.nan_to_num(hava), hava_d, eksik, ort_d, u,
                rows, p, n - 1, dict(mae=None, ofset_tahmini=None,
                                     baslangic=None if t0 is None else t0.strftime("%d.%m.%Y %H:%M")))
    return d


@lru_cache(maxsize=1)
def _matris():
    sonuc, seriler = calistir()
    egriler = {}
    for (k, p, a), (t, out) in seriler.items():
        egriler[f"{k}|{p:g}|{a:g}"] = [round(float(v), 2) for v in out[::12, 2]]
    return dict(sonuc=sonuc, egriler=egriler, t_saat=[round(i * 2 / 60, 3) for i in range(len(next(iter(egriler.values()))))])


@app.get("/api/karsilastirma")
def karsilastirma():
    return _matris()


@app.get("/api/sensor_karsilastirma")
def sensor_karsilastirma(tasarim: str = "T2", pcm: float = 1.0, ortam: float = 30.0,
                         model: str = "gbr", seed: int = 4242):
    return [dict(kod=k, ad=BOZULMALAR[k][0], **{x: _kosu(tasarim, pcm, ortam, k, model, seed)["ozet"][x]
             for x in ("mae", "doldurulan", "ilk_uyari_dk", "gercek_asim_dk", "erken_uyari_dk")})
            for k in BOZULMALAR]


@app.get("/api/model_karsilastirma")
def model_karsilastirma():
    """27 ayrık test koşusunda model x sensör durumu MAE tablosu (tahmin.py çıktısı)."""
    yol = os.path.join(CIKTI, "tahmin_sonuclari.json")
    if not os.path.exists(yol):
        raise HTTPException(404, "Önce 'python tahmin.py' çalıştırın")
    return json.load(open(yol))["modeller"]
