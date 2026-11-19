"""Hazır kayıt yükleme özelliği için ÖRNEK CSV biçimi üretir.

Bu dosya gerçek bir ölçüm DEĞİLDİR: biçimi göstermek için simülasyondan
üretilmiş, gerçekçi boşluklar içeren bir kayıttır. Gerçek bir hazır kayıt
(ör. bir veri kaydedicinin dışa aktardığı CSV) aynı sütunlarla yüklenebilir:

    zaman;ic_hava;ortam
    2026-07-15 08:00;4,06;31,2
    ...
- zaman: tarih-saat (YYYY-AA-GG SS:DD) ya da başlangıçtan itibaren dakika
- ic_hava: çanta içi hava sensörü (°C); boş hücre = alınamayan ölçüm
- ortam: dış ortam sensörü (°C)
- urun (isteğe bağlı): doğrulama için ürün sıcaklığı
"""
import csv
from datetime import datetime, timedelta
import numpy as np
from termal_model import TASARIMLAR, simule_et
import tahmin as T

rng = np.random.default_rng(2026)
tas = next(t for t in TASARIMLAR if t.kisa == "T2")
_, out = simule_et(tas.UA, 1.0, 32.0, sure_h=6.0, rng=rng)
out = out[::T.ORNEK]
hava, eksik = T.sensor(out[:, 1], rng, kayip=0.12)
ort, _ = T.sensor(out[:, 0], rng)
t0 = datetime(2026, 7, 15, 8, 0)
satir = []
for i in range(out.shape[0]):
    if eksik[i] and rng.random() < 0.5:
        continue                      # paket hiç gelmemiş: satır yok
    satir.append([(t0 + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M"),
                  "" if eksik[i] else f"{hava[i]:.2f}".replace(".", ","),
                  f"{ort[i]:.2f}".replace(".", ",")])
for yol in ("ornek_kayit_formati.csv", "panel/static/ornek_kayit_formati.csv"):
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["zaman", "ic_hava", "ortam"])
        w.writerows(satir)
print(len(satir), "satır,", int(eksik.sum()), "kayıp dakika")
