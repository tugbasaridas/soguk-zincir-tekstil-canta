"""Toplu parametreli (3 düğümlü) çanta termal modeli.

Düğümler: çanta içi hava, ürün (yoğurt), PCM (entalpi yöntemi).
Ön çalışma amaçlıdır; tüm parametreler literatür aralıklarından seçilmiş
VARSAYIMLARDIR ve İP1-İP3'te ekipçe güncellenecektir.
"""
from dataclasses import dataclass
import numpy as np

# Çanta geometrisi: 30 x 20 x 25 cm
ALAN = 2 * (0.30 * 0.20 + 0.30 * 0.25 + 0.20 * 0.25)  # m2
R_YUZEY = 0.17  # iç + dış yüzey film direnci, m2K/W


@dataclass
class Tasarim:
    ad: str
    kisa: str
    katmanlar: list          # (katman adı, kalınlık m, k W/mK) ya da (ad, None, ek R)

    @property
    def R_toplam(self):
        r = R_YUZEY
        for _, d, k in self.katmanlar:
            r += k if d is None else d / k
        return r

    @property
    def UA(self):
        return ALAN / self.R_toplam


TASARIMLAR = [
    Tasarim("T1 · İnce yansıtıcı nonwoven", "T1", [
        ("Polyester dış kumaş", 0.001, 0.05),
        ("Nonwoven keçe", 0.005, 0.040),
        ("Alüminize yansıtıcı astar", None, 0.08),
    ]),
    Tasarim("T2 · Elyaf dolgulu çok katmanlı", "T2", [
        ("PU kaplı polyester oxford", 0.001, 0.05),
        ("Hollow silikonize elyaf dolgu", 0.015, 0.040),
        ("Alüminize yansıtıcı astar", None, 0.08),
    ]),
    Tasarim("T3 · 3B aralıklı kumaş + dolgu", "T3", [
        ("PU kaplı polyester oxford", 0.001, 0.05),
        ("Hollow silikonize elyaf dolgu", 0.015, 0.040),
        ("3B aralıklı (spacer) kumaş", 0.010, 0.045),
        ("Alüminize yansıtıcı astar", None, 0.08),
    ]),
]

# Ürün ve PCM (varsayım)
URUN_KG, URUN_CP = 2.0, 3750.0           # 4 x 500 g yoğurt, J/kgK
HAVA_C = 600.0                             # hava + iç astar ısıl kapasitesi, J/K
PCM_L, PCM_TM, PCM_ARALIK = 180e3, 5.0, 1.0  # J/kg, erime merkezi °C, erime aralığı °C
PCM_CP_S, PCM_CP_L = 2000.0, 2200.0
HA_URUN = 1.5                              # hava-ürün (4 kap yüzeyi), W/K
HA_PCM_KG = 2.0                            # hava-PCM (cep yüzeyi), W/K per kg
HC_PCM_KG = 1.0                            # PCM-ürün temas, W/K per kg
KAPLAMA_KG = 0.8                           # 1 kg PCM cebi duvar alanının %80'ini kaplar
ESIK = 6.0                                 # varsayılan üst sıcaklık eşiği, °C


@dataclass
class Parametre:
    """Model parametreleri. Varsayılanlar: yoğurt + tekstil çanta (ön çalışma varsayımları).
    Doğrulamada (dogrulama.py) deney kutusunun değerleriyle değiştirilir."""
    urun_kg: float = URUN_KG
    urun_cp: float = URUN_CP
    hava_c: float = HAVA_C
    pcm_L: float = PCM_L
    pcm_tm: float = PCM_TM
    pcm_aralik: float = PCM_ARALIK
    pcm_cp_s: float = PCM_CP_S
    pcm_cp_l: float = PCM_CP_L
    ha_urun: float = HA_URUN
    ha_pcm: float = None        # toplam hava-PCM (W/K); None -> HA_PCM_KG x kütle
    hc_pcm: float = None        # toplam PCM-ürün temas (W/K); None -> HC_PCM_KG x kütle
    kaplama: float = None       # PCM'in kapladığı duvar oranı; None -> min(0,9; 0,8 x kütle)


VARSAYILAN = Parametre()


def pcm_T(H, m, p=VARSAYILAN):
    """Özgül entalpiden (J/kg, katı Tm-aralık/2 referanslı) sıcaklık."""
    Ts = p.pcm_tm - p.pcm_aralik / 2
    if H <= 0:
        return Ts + H / p.pcm_cp_s
    if H <= p.pcm_L:
        return Ts + p.pcm_aralik * H / p.pcm_L
    return Ts + p.pcm_aralik + (H - p.pcm_L) / p.pcm_cp_l


def ortam_profili(t_s, taban, rng, kapak_aralik=5400, kapak_sure=120):
    """Ortam sıcaklığı ve kapak açılma maskesi (dağıtım durakları)."""
    faz = rng.uniform(0, 2 * np.pi)
    T = taban + 1.5 * np.sin(2 * np.pi * t_s / 10800 + faz) + rng.normal(0, 0.15, t_s.size)
    acik = ((t_s % kapak_aralik) > kapak_aralik - kapak_sure) & (t_s > 0)
    return T, acik


def simule_et(UA, pcm_kg, taban, sure_h=8.0, dt=10.0, rng=None,
              T0_urun=4.0, T0_pcm=3.0, p=VARSAYILAN, sabit_ortam=False, T0_hava=None):
    """sabit_ortam=True: dalgalanma ve kapak açılması yok (laboratuvar deneyi gibi)."""
    rng = rng or np.random.default_rng(0)
    t = np.arange(0, sure_h * 3600 + dt, dt)
    if sabit_ortam:
        Tamb, acik = np.full(t.size, float(taban)), np.zeros(t.size, bool)
    else:
        Tamb, acik = ortam_profili(t, taban, rng)
    Ta, Tp = (T0_urun if T0_hava is None else T0_hava), T0_urun
    H = (T0_pcm - (p.pcm_tm - p.pcm_aralik / 2)) * p.pcm_cp_s
    Cp = p.urun_kg * p.urun_cp
    f = min(0.9, KAPLAMA_KG * pcm_kg) if p.kaplama is None else p.kaplama
    ha_pcm = HA_PCM_KG * pcm_kg if p.ha_pcm is None else p.ha_pcm
    hc_pcm = HC_PCM_KG * pcm_kg if p.hc_pcm is None else p.hc_pcm
    out = np.zeros((t.size, 4))
    for i in range(t.size):
        Tpcm = pcm_T(H, pcm_kg, p) if pcm_kg > 0 else Tp
        out[i] = (Tamb[i], Ta, Tp, Tpcm)
        kapak = 6.0 if acik[i] else 1.0
        q_amb_hava = UA * (1 - f) * kapak * (Tamb[i] - Ta)
        q_amb_pcm = UA * f * (Tamb[i] - Tpcm)
        q_ap = p.ha_urun * (Ta - Tp)
        q_apcm = ha_pcm * (Ta - Tpcm)
        q_cp = hc_pcm * (Tpcm - Tp)
        if acik[i]:
            q_amb_hava += UA * f * (kapak - 1) * (Tamb[i] - Ta)
        Ta += dt * (q_amb_hava - q_ap - q_apcm) / p.hava_c
        Tp += dt * (q_ap + q_cp) / Cp
        if pcm_kg > 0:
            H += dt * (q_amb_pcm + q_apcm - q_cp) / pcm_kg
    return t, out  # sütunlar: ortam, iç hava, ürün, PCM


def esik_suresi(t, Tp, esik=ESIK):
    idx = np.argmax(Tp > esik)
    if Tp[idx] <= esik:
        return None  # süre boyunca aşılmadı
    return t[idx] / 3600
