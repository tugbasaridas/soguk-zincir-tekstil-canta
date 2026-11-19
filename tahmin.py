"""Ürün sıcaklığının 30 dk ileri tahmini ve sensör bozulmalarına dayanıklılık.

Eğitim: rastgele parametreli sentetik koşular.
Test: eğitimde hiç kullanılmamış 27 ızgara senaryosu (ayrık koşular, [6]).
Bozulmalar: sensör ofseti + sapma ([7]), paket kaybı / kesinti ([8]).
"""
import json
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from termal_model import TASARIMLAR, simule_et
from senaryolar import PCM_LIST, ORTAM_LIST

ORNEK = 6          # 10 sn adım x 6 = 1 dk örnekleme
UFUK = 30          # dk
GECIKMELER = [0, 5, 15, 30]


def sensor(hava, rng, ofset=0.0, sapma_h=0.0, kayip=0.0, gurultu=0.1):
    n = hava.size
    t_h = np.arange(n) / 60
    olcum = hava + rng.normal(0, gurultu, n) + ofset + sapma_h * t_h
    olcum = np.round(olcum / 0.0625) * 0.0625          # DS18B20 12-bit çözünürlük
    eksik = np.zeros(n, bool)
    if kayip > 0:                                       # patlamalı paket kaybı
        i = 0
        while i < n:
            if rng.random() < kayip / 8:
                L = rng.integers(3, 15); eksik[i:i + L] = True; i += L
            else:
                i += 1
    return olcum, eksik


def doldur(x, eksik):
    """Eksik kayıtları doğrusal enterpolasyonla doldur; bayrağı ayrı tut."""
    y = x.copy()
    if eksik.any():
        idx = np.arange(x.size)
        y[eksik] = np.interp(idx[eksik], idx[~eksik], x[~eksik])
    return y


def ozellik(s_hava, s_ort, UA, pcm):
    n = s_hava.size
    X, rows = [], []
    for i in range(30, n - UFUK):
        f = [s_hava[i - g] for g in GECIKMELER]
        f += [s_hava[i] - s_hava[i - 15], s_ort[i], i / 60, UA, pcm]
        X.append(f); rows.append(i)
    return np.array(X), np.array(rows)


def kosu(UA, pcm, amb, seed, **bozulma):
    rng = np.random.default_rng(seed)
    t, out = simule_et(UA, pcm, amb, rng=rng)
    out = out[::ORNEK]
    s_hava, eksik = sensor(out[:, 1], rng, **bozulma)
    s_ort, _ = sensor(out[:, 0], rng)
    s_hava_d = doldur(s_hava, eksik)
    X, rows = ozellik(s_hava_d, s_ort, UA, pcm)
    y = out[rows + UFUK, 2]
    return X, y, out, s_hava, eksik, rows


MODELLER = {
    "dogrusal": ("Doğrusal regresyon (Ridge)",
                 lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0))),
    "orman": ("Rastgele orman",
              lambda: RandomForestRegressor(n_estimators=150, min_samples_leaf=5, n_jobs=-1, random_state=0)),
    "gbr": ("Gradyan artırmalı regresyon",
            lambda: HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08, random_state=0)),
}


def egitim_verisi(n=180, seed=7):
    """Rastgele parametreli eğitim koşuları (test ızgarasından ayrı)."""
    rng = np.random.default_rng(seed)
    Xs, ys = [], []
    for k in range(n):
        UA = rng.uniform(0.35, 1.05)
        pcm = rng.choice([0.0, rng.uniform(0.2, 1.2)])
        amb = rng.uniform(22, 37)
        X, y, *_ = kosu(UA, pcm, amb, 50_000 + k)
        Xs.append(X); ys.append(y)
    return np.vstack(Xs), np.concatenate(ys)


def egit(tur="gbr", veri=None):
    X, y = veri if veri is not None else egitim_verisi()
    m = MODELLER[tur][1]()
    m.fit(X, y)
    return m


def kalibrasyon_ofseti(rng, ofset):
    """Yola çıkmadan önce 10 dk referans sensörle karşılaştırma ([7]).
    Doğrusal regresyonla ofset kestirimi."""
    ref = 4.0 + rng.normal(0, 0.05, 10)
    olc = ref + ofset + rng.normal(0, 0.1, 10)
    b, a = np.polyfit(ref, olc, 1)
    return float(np.mean(olc - ref))


DURUMLAR = {
    "Temiz sensör": dict(),
    "Ofset + sapma (+0,5 °C, +0,15 °C/sa)": dict(ofset=0.5, sapma_h=0.15),
    "Ofset düzeltilmiş (regresyon)": "duzelt",
    "%15 paket kaybı (doldurulmuş)": dict(kayip=0.15),
    "Sapma + kayıp birlikte": dict(ofset=0.5, sapma_h=0.15, kayip=0.15),
}


def test_kosulari():
    """Eğitimde kullanılmayan 27 ızgara koşusu, her bozulma için (X, y) listesi."""
    out = {}
    for ad, bz in DURUMLAR.items():
        liste = []
        for ti, tas in enumerate(TASARIMLAR):
            for pcm in PCM_LIST:
                for amb in ORTAM_LIST:
                    seed = 9_000 + ti * 100 + int(pcm * 10) * 10 + int(amb)
                    if bz == "duzelt":
                        rng = np.random.default_rng(seed + 1)
                        of = kalibrasyon_ofseti(rng, 0.5)
                        X, y, _, _, _, rows = kosu(tas.UA, pcm, amb, seed, ofset=0.5 - of, sapma_h=0.15)
                    else:
                        X, y, _, _, _, rows = kosu(tas.UA, pcm, amb, seed, **bz)
                    liste.append((tas.kisa, pcm, amb, X, y, rows))
        out[ad] = liste
    return out


if __name__ == "__main__":
    import os
    os.makedirs("cikti", exist_ok=True)
    import pickle, time
    veri = egitim_verisi()
    testler = test_kosulari()
    sonuc_model, sure = {}, {}
    sonuc, ornek = {}, None
    for tur, (mad, _) in MODELLER.items():
        t0 = time.time(); m = egit(tur, veri); sure[tur] = round(time.time() - t0, 1)
        pickle.dump(m, open(f"cikti/model_{tur}.pkl", "wb"))
        sonuc_model[tur] = dict(ad=mad, egitim_sn=sure[tur], durumlar={})
        for ad, liste in testler.items():
            hat, nai = [], []
            for kod, pcm, amb, X, y, rows in liste:
                p = m.predict(X)
                hat.append(np.abs(p - y)); nai.append(np.abs(X[:, 0] - y))
                if tur == "gbr" and ad == "Temiz sensör" and kod == "T2" and pcm == 1.0 and amb == 30.0:
                    ornek = dict(t=(rows / 60).tolist(), gercek=y.tolist(), tahmin=p.tolist())
            h = np.concatenate(hat)
            r = dict(MAE=round(float(h.mean()), 3), P95=round(float(np.percentile(h, 95)), 3),
                     MAE_naif=round(float(np.concatenate(nai).mean()), 3))
            sonuc_model[tur]["durumlar"][ad] = r
            if tur == "gbr":
                sonuc[ad] = r
            print(f"{mad:30s} {ad:40s} MAE={r['MAE']:.3f} P95={r['P95']:.3f}")
    json.dump(dict(sonuc=sonuc, ornek=ornek, modeller=sonuc_model),
              open("cikti/tahmin_sonuclari.json", "w"), ensure_ascii=False, indent=1)
