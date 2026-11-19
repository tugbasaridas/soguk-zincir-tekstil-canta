"""Tüm ön çalışmayı sırayla çalıştırır ve cikti/ klasörünü üretir.

    python calistir_hepsi.py

Sıra: 27 senaryo -> tahmin modelleri (3 model, ~30 sn) -> grafikler -> deneysel doğrulama.
"""
import runpy, sys, time

ADIMLAR = [
    ("senaryolar.py", "3 tasarım x 3 PCM x 3 ortam = 27 senaryo"),
    ("tahmin.py", "Tahmin modelleri: eğitim + ayrık test + sensör bozulmaları"),
    ("grafikler.py", "Rapor grafikleri"),
    ("dogrulama.py", "Termal modelin açık deney verisiyle doğrulanması"),
]

for dosya, aciklama in ADIMLAR:
    t0 = time.time()
    print(f"\n=== {dosya}: {aciklama}")
    sys.argv = [dosya]
    runpy.run_path(dosya, run_name="__main__")
    print(f"--- {dosya} bitti ({time.time() - t0:.1f} sn)")
print("\nTamam. Sonuçlar cikti/ klasöründe. Paneli açmak için: python -m uvicorn panel.app:app --port 8000")
