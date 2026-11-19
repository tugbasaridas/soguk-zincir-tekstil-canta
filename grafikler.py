"""Rapor için PNG grafikler ve sunum için çizgi verisi."""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from senaryolar import calistir, PCM_LIST, ORTAM_LIST
from termal_model import TASARIMLAR, ESIK

os.makedirs("cikti", exist_ok=True)

RENK = {"T1": "#9AA9B2", "T2": "#3A8FB7", "T3": "#E0702E"}

sonuc, seriler = calistir()

# 1) 30 °C, 1 kg PCM: üç tasarımın ürün sıcaklığı
fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
for tas in TASARIMLAR:
    t, out = seriler[(tas.kisa, 1.0, 30.0)]
    ax.plot(t / 3600, out[:, 2], color=RENK[tas.kisa], lw=2.2, label=tas.ad)
ax.axhline(ESIK, color="#A8481A", ls="--", lw=1.4, label="Üst eşik 6 °C (varsayım)")
ax.set_xlabel("Süre (saat)"); ax.set_ylabel("Ürün sıcaklığı (°C)")
ax.set_title("Ortam 30 °C, 1 kg PCM — ön simülasyon (varsayımsal parametreler)")
ax.legend(frameon=False); ax.grid(alpha=.25); fig.tight_layout()
fig.savefig("cikti/urun_sicakligi_30C_1kgPCM.png")

# 2) Eşik süresi ısı haritası
M = np.zeros((9, 3))
etiket = []
for i, tas in enumerate(TASARIMLAR):
    for j, pcm in enumerate(PCM_LIST):
        etiket.append(f"{tas.kisa} · {pcm:g} kg PCM")
        for k, amb in enumerate(ORTAM_LIST):
            r = next(x for x in sonuc if x["tasarim"] == tas.kisa and x["pcm_kg"] == pcm and x["ortam"] == amb)
            M[i * 3 + j, k] = r["esik_suresi_h"] if r["esik_suresi_h"] is not None else 8
fig, ax = plt.subplots(figsize=(6.5, 6), dpi=150)
im = ax.imshow(M, cmap="Blues", aspect="auto")
ax.set_xticks(range(3), [f"{a:g} °C" for a in ORTAM_LIST]); ax.set_yticks(range(9), etiket)
for (a, b), v in np.ndenumerate(M):
    ax.text(b, a, f"{v:.1f} sa", ha="center", va="center", color="white" if v > 3 else "#102A3A")
ax.set_title("Ürün 6 °C'yi aşana kadar geçen süre")
fig.colorbar(im, label="saat"); fig.tight_layout(); fig.savefig("cikti/esik_suresi_isi_haritasi.png")

# 3) Tahmin hatası
tr = json.load(open("cikti/tahmin_sonuclari.json"))
ad = list(tr["sonuc"].keys()); mae = [tr["sonuc"][a]["MAE"] for a in ad]
fig, ax = plt.subplots(figsize=(9, 4), dpi=150)
ax.barh(ad[::-1], mae[::-1], color="#3A8FB7")
for i, v in enumerate(mae[::-1]):
    ax.text(v + 0.02, i, f"{v:.2f} °C", va="center")
ax.set_xlabel("Ortalama mutlak hata (°C), 30 dk ileri tahmin")
ax.set_title("Ayrık 27 test koşusunda tahmin hatası")
fig.tight_layout(); fig.savefig("cikti/tahmin_hatasi.png")

# Sunum için: 2 dk örneklemeli eğriler
egri = {}
for tas in TASARIMLAR:
    t, out = seriler[(tas.kisa, 1.0, 30.0)]
    egri[tas.kisa] = out[::12, 2].round(2).tolist()
json.dump(dict(egri=egri, M=M.round(2).tolist(), etiket=etiket), open("cikti/sunum_verisi.json", "w"))
print("tamam", M.max(), {k: max(v) for k, v in egri.items()})
