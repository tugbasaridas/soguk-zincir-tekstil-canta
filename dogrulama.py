"""Termal modelin açık deneysel veriyle doğrulanması.

Veri: Leungtongkum vd., "Dataset of air velocity and temperature fields inside an
insulated box equipped with phase change material under several operating conditions",
Data in Brief, 2023/2024. Mendeley Data, doi:10.17632/sz5dgkz7k8.1 (CC BY 4.0).

Veri seti, kutu kapatıldıktan sonra 400-600. dakikalar arasındaki (yarı kararlı rejim)
ORTALAMA sıcaklıkları, kutunun orta düzlemindeki ölçüm noktalarında verir. Zaman serisi
içermez. Bu yüzden doğrulama, modelin aynı aralıktaki ortalama iç sıcaklığı ile
ölçülen noktaların ortalamasının karşılaştırılmasıdır.

Kutu ve PCM değerleri yayımlanmış deney tanımından (Data in Brief 2022, PMC9679728):
  iç boyut 500 x 310 x 300 mm, ısı geçiş alanı 1,027 m2, K = 0,61-0,71 W/m2K,
  PCM: 3,5 kg musluk suyu (erime ~0 °C), 460 x 280 x 50 mm, -2 °C'de ön koşullandırma,
  ürün: 16 paket 200 x 100 x 50 mm, %76,4 su (Tylose benzeri).
Yayında verilmeyen değerler (VARSAYIM): ürün yoğunluğu ve özgül ısısı, iç taşınım katsayıları.

Çalıştırma:  python dogrulama.py <veri klasörü>   (varsayılan: veri/sz5dgkz7k8-1)
"""
import sys, os, glob, json, re
import numpy as np
import openpyxl
from termal_model import Parametre, simule_et

KLASOR = sys.argv[1] if len(sys.argv) > 1 else "veri/sz5dgkz7k8-1"

# ---- Deney kutusu parametreleri ----
K_ORT, ALAN_KUTU = 0.66, 1.027                     # W/m2K (0,61-0,71 ortası), m2
UA_KUTU = K_ORT * ALAN_KUTU
IC_ALAN = 2 * (0.50 * 0.31 + 0.50 * 0.30 + 0.31 * 0.30)
PCM_YUZ = 0.46 * 0.28
URUN_KG = 16 * 0.2 * 0.1 * 0.05 * 1050            # VARSAYIM: yoğunluk 1050 kg/m3
P_KUTU = Parametre(
    urun_kg=URUN_KG, urun_cp=3700.0,               # VARSAYIM: %76 su içeren jel için
    hava_c=2000.0,                                  # hava + iç polipropilen astar
    pcm_L=334e3, pcm_tm=0.0, pcm_aralik=0.4,        # su/buz
    pcm_cp_s=2100.0, pcm_cp_l=4180.0,
    ha_urun=0.5 * 3.0,                              # VARSAYIM: ~0,5 m2 açık ürün yüzeyi x 3 W/m2K
    ha_pcm=PCM_YUZ * 4.0,                           # PCM açık yüzü x 4 W/m2K (doğal taşınım)
    hc_pcm=0.0,                                     # ürün PCM'e temas etmiyor
    kaplama=PCM_YUZ / IC_ALAN,                      # PCM'in kapladığı duvar oranı
)
PCM_KG = 3.5


def olcum_oku(yol):
    ws = openpyxl.load_workbook(yol, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    kosul = dict(zip(rows[0][:6], rows[1][:6]))
    degerler = []
    basla = next(i for i, r in enumerate(rows) if r and r[0] == "Z (mm)")
    for r in rows[basla + 1:]:
        if not r or not isinstance(r[0], str) or not r[0].startswith("Y ="):
            break
        degerler += [float(c) for c in r[1:] if isinstance(c, (int, float))]
    return kosul, np.array(degerler)


def main():
    dosyalar = sorted(glob.glob(os.path.join(KLASOR, "C*.xlsx")))
    sonuc = []
    for yol in dosyalar:
        kosul, d = olcum_oku(yol)
        T0 = kosul.get("Initial load temperature (°C)")
        if not isinstance(T0, (int, float)):
            continue                                    # boş kutu deneyleri: ürün yok
        amb = float(kosul["Ambient temperature (°C)"])
        t, out = simule_et(UA_KUTU, PCM_KG, amb, sure_h=10.0, dt=10.0, T0_urun=float(T0),
                           T0_pcm=-2.0, p=P_KUTU, sabit_ortam=True, T0_hava=float(T0))
        pencere = (t >= 400 * 60) & (t <= 600 * 60)
        hava = float(out[pencere, 1].mean()); urun = float(out[pencere, 2].mean())
        ad = os.path.basename(yol)
        sonuc.append(dict(
            kosul=int(kosul["Condition"]), dosya=ad,
            pcm_konum="yan duvar" if "Side" in ad else "üst",
            en_boy="1,7 (dikey)" if "Vertical" in ad else "1,0",
            bosluk_mm=kosul.get("Spacing beneath load (mm)"),
            ortam=amb, T0=float(T0),
            olcum_ort=round(float(d.mean()), 2), olcum_min=round(float(d.min()), 2),
            olcum_max=round(float(d.max()), 2), nokta=int(d.size),
            model_hava=round(hava, 2), model_urun=round(urun, 2),
            model_ort=round((hava + urun) / 2, 2),
        ))
    hata = np.array([r["model_ort"] - r["olcum_ort"] for r in sonuc])
    ozet = dict(n=len(sonuc), RMSE=round(float(np.sqrt((hata ** 2).mean())), 2),
                MAE=round(float(np.abs(hata).mean()), 2), sapma_ort=round(float(hata.mean()), 2),
                UA=round(UA_KUTU, 3), urun_kg=round(URUN_KG, 1))
    for r in sonuc:
        print(f"C{r['kosul']:02d} {r['pcm_konum']:9s} AR {r['en_boy']:11s} ortam {r['ortam']:4.0f} T0 {r['T0']:4.0f}"
              f" | ölçüm ort {r['olcum_ort']:5.2f} [{r['olcum_min']:5.2f}, {r['olcum_max']:5.2f}] n={r['nokta']}"
              f" | model hava {r['model_hava']:5.2f} ürün {r['model_urun']:5.2f} ort {r['model_ort']:5.2f}")
    print(ozet)
    os.makedirs("cikti", exist_ok=True)
    json.dump(dict(ozet=ozet, kosullar=sonuc), open("cikti/dogrulama_sonuclari.json", "w"),
              ensure_ascii=False, indent=1)


def grafik():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = json.load(open("cikti/dogrulama_sonuclari.json"))
    k = d["kosullar"]
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)
    for i, r in enumerate(k):
        ax.plot([r["olcum_min"], r["olcum_max"]], [i, i], color="#C9D8DC", lw=6, solid_capstyle="round")
        ax.plot(r["olcum_ort"], i, "o", color="#102A3A", ms=9, label="Ölçüm ortalaması" if i == 0 else None)
        ax.plot(r["model_ort"], i, "s", color="#E0702E", ms=8, label="Model" if i == 0 else None)
    ax.set_yticks(range(len(k)), [f"C{r['kosul']:02d} · {r['pcm_konum']} · {r['ortam']:g} °C · {r['T0']:g} °C" for r in k])
    ax.invert_yaxis(); ax.set_xlabel("Sıcaklık (°C), 400–600. dk ortalaması")
    ax.set_title(f"Model doğrulama: RMSE {d['ozet']['RMSE']} °C, MAE {d['ozet']['MAE']} °C (gri: ölçülen aralık)")
    ax.legend(frameon=False, loc="lower right"); ax.grid(axis="x", alpha=.3); fig.tight_layout()
    fig.savefig("cikti/model_dogrulama.png")


if __name__ == "__main__":
    main()
    grafik()
