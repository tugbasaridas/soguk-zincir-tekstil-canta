"""3 tasarım x 3 PCM miktarı x 3 ortam sıcaklığı senaryo matrisi."""
import csv, json
import numpy as np
from termal_model import TASARIMLAR, simule_et, esik_suresi

PCM_LIST = [0.0, 0.5, 1.0]
ORTAM_LIST = [25.0, 30.0, 35.0]


def calistir(sure_h=8.0):
    sonuc = []
    seriler = {}
    for ti, tas in enumerate(TASARIMLAR):
        for pcm in PCM_LIST:
            for amb in ORTAM_LIST:
                rng = np.random.default_rng(1000 + ti * 100 + int(pcm * 10) * 10 + int(amb))
                t, out = simule_et(tas.UA, pcm, amb, sure_h=sure_h, rng=rng)
                s = esik_suresi(t, out[:, 2])
                sonuc.append(dict(tasarim=tas.kisa, UA=round(tas.UA, 3), R=round(tas.R_toplam, 3),
                                  pcm_kg=pcm, ortam=amb,
                                  esik_suresi_h=None if s is None else round(s, 2),
                                  urun_max=round(float(out[:, 2].max()), 2)))
                seriler[(tas.kisa, pcm, amb)] = (t, out)
    return sonuc, seriler


if __name__ == "__main__":
    import os
    os.makedirs("cikti", exist_ok=True)
    sonuc, _ = calistir()
    with open("cikti/senaryo_sonuclari.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sonuc[0].keys()))
        w.writeheader(); w.writerows(sonuc)
    for tas in TASARIMLAR:
        print(tas.kisa, "R=%.3f UA=%.3f" % (tas.R_toplam, tas.UA))
    for r in sonuc:
        print(r)
