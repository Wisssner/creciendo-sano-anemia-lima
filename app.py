"""Prediction API — model trained directly on real Lima SIEN-HIS data
(2016-2025, DIRIS Centro/Este/Norte/Sur), via modelado/train_final_model_lima.py.

No mapping layer: `artifacts/serving_snapshot.pkl` and `artifacts/modelo_reducido.pkl`
both come straight from `modelado/`, which processed Lima's own HB/PT exports
end to end (extraction, schema harmonization, feature engineering, tuning,
evaluation). Every establishment in /establecimientos is a real Lima health
post, and every rate the model consumes is Lima's own history -- see
modelado/README or the project's root README for the full pipeline and its
declared limitations (2016-2018 cover only DIRIS Este+Sur; see modelado/build_lima_raw.py).

Run with: uvicorn app:app --reload --port 8010
"""
import re
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import Pool
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
ART = ROOT / "artifacts"

app = FastAPI(title="Tamizaje predictivo de anemia — Lima")

MODEL = joblib.load(ART / "modelo_reducido.pkl")
SNAP = joblib.load(ART / "serving_snapshot.pkl")
HB_CUTOFF = 11.0

# Real, held-out evaluation numbers (frozen test 2025, scored with the actual
# serialized modelo_reducido.pkl -- see modelado/evaluate_reduced_lima.py).
# Shown as-is in the UI -- nothing here is fabricated or copied from Junin.
CONFIANZA = {
    "auc": 0.7411,
    "recall": 0.5931,
    "precision": 0.2251,
    "auc_con_historial": 0.7392,
    "auc_sin_historial": 0.7418,
    "tasa_antropometria": 0.3664,  # share of visits with matched weight/height the model trained on
    "prevalencia_promedio": 0.2116,
}


def clean_eess_name(raw: str) -> str:
    """'I-3   - 00005627 - CENTRO DE SALUD CRUZ DE MOTUPE' -> readable name."""
    s = re.sub(r"\s+", " ", str(raw)).strip()
    parts = [p.strip() for p in s.split(" - ")]
    if len(parts) >= 3:
        categoria, _codigo, *nombre = parts
        return f"{' - '.join(nombre)} ({categoria})"
    return s

# Human-readable label for each of the 35 model inputs, used to build the
# per-case explanation from real SHAP values.
FEATURE_LABELS = {
    "hist_eess_prev_90d": "Nivel de anemia reciente en el establecimiento (90 días)",
    "roll_eess_30d": "Nivel de anemia reciente en el establecimiento (30 días)",
    "roll_eess_365d": "Nivel de anemia en el establecimiento (último año)",
    "roll_eess_7d": "Nivel de anemia muy reciente en el establecimiento (7 días)",
    "roll_eess_banda_edad": "Nivel de anemia en niños de su misma edad en el establecimiento",
    "roll_eess_hbc_30d": "Hemoglobina promedio reciente del establecimiento",
    "roll_eess_hbc_90d": "Hemoglobina promedio del establecimiento (90 días)",
    "roll_eess_hbc_365d": "Hemoglobina promedio del establecimiento (último año)",
    "prev_Renipress": "Historial general de anemia de este establecimiento",
    "roll_distrito_365d": "Nivel de anemia en el distrito",
    "roll_red_30d": "Nivel de anemia en la red de salud",
    "alt_vs_distrito": "Altitud del establecimiento frente a su entorno",
    "hist_hbc_prev": "Hemoglobina del control anterior",
    "hist_hbc_prev2": "Hemoglobina de dos controles atrás",
    "hist_hbc_media": "Promedio histórico de hemoglobina del niño",
    "hist_hb_prev": "Hemoglobina cruda del control anterior",
    "hist_hbc_x_gap": "Tiempo transcurrido desde el último control",
    "EdadMeses": "Edad del niño",
    "Sexo": "Sexo",
    "Cred": "Asistencia a control CRED",
    "Suplementacion": "Suplementación con hierro",
    "n_atenciones": "Cantidad de servicios recibidos hoy",
    "DistritoREN": "Distrito del establecimiento",
    "Microred": "Microrred del establecimiento",
    "Peso": "Peso para su edad",
    "Talla": "Talla para su edad",
    "imc": "Índice de masa corporal",
    "peso_x_mes": "Peso relativo a su edad",
    "talla_x_mes": "Talla relativa a su edad",
    "SIS": "Afiliación al Seguro Integral de Salud",
    "Juntos": "Afiliación al programa Juntos",
    "Qaliwarma": "Afiliación a Qali Warma",
    "Consejeria": "Consejería nutricional recibida",
    "Sesion": "Sesión demostrativa recibida",
    "hist_tiene_historia": "Tiene controles previos registrados",
}


class PredictRequest(BaseModel):
    renipress: str  # Lima establishment id
    sexo: str = Field(pattern="^[MF]$")
    fecha_nacimiento: date
    fecha_atencion: date = Field(default_factory=date.today)
    peso: float = Field(gt=0, lt=40)
    talla: float = Field(gt=0, lt=140)
    cred: bool = False
    suplementacion: bool = False
    consejeria: bool = False
    sesion: bool = False
    sis: bool = False
    juntos: bool = False
    qaliwarma: bool = False
    tiene_historial: bool = False
    hb_previa: float | None = None
    fecha_previa: date | None = None
    n_controles: int | None = None


def _age_months(nacimiento: date, atencion: date) -> float:
    return max((atencion - nacimiento).days, 0) / 30.4368


def _age_band(edad_meses: float) -> float:
    bins = SNAP["age_bands"]
    for i in range(len(bins) - 1):
        if bins[i] <= edad_meses < bins[i + 1]:
            return float(i)
    return np.nan


def _rate(name: str, renipress: str, red: str) -> float:
    """Establecimiento -> red -> Lima. The department level always has a
    value, so this never returns NaN."""
    v = SNAP["eess"].at[renipress, name] if renipress in SNAP["eess"].index else np.nan
    if pd.notna(v):
        return float(v)
    v = SNAP["red"].at[red, name] if red in SNAP["red"].index else np.nan
    return float(v) if pd.notna(v) else float(SNAP["departamento"][name])


def _rate_red(name: str, red: str) -> float:
    """Red -> Lima, for a feature meant to describe the network, not the post."""
    v = SNAP["red"].at[red, name] if red in SNAP["red"].index else np.nan
    return float(v) if pd.notna(v) else float(SNAP["departamento"][name])


def _rate_banda(renipress: str, banda: float) -> float:
    v = SNAP["eess_banda_edad"].get((renipress, banda), np.nan)
    if pd.notna(v):
        return float(v)
    v = SNAP["departamento_banda_edad"].get(banda, np.nan)
    return float(v) if pd.notna(v) else float(SNAP["prior"])


def build_features(req: PredictRequest) -> dict:
    eess = SNAP["eess"]
    if req.renipress not in eess.index:
        raise HTTPException(422, f"Establecimiento '{req.renipress}' no está en la lista.")
    e = eess.loc[req.renipress]
    red = e["Red"] if pd.notna(e["Red"]) else ""

    edad_meses = _age_months(req.fecha_nacimiento, req.fecha_atencion)
    if not (6 <= edad_meses <= 59):
        raise HTTPException(
            422, f"Edad calculada: {edad_meses:.1f} meses. El modelo solo fue "
            "validado para 6-59 meses (de 6 meses a 4 años 11 meses); fuera de "
            "ese rango el resultado no es confiable.")
    banda = _age_band(edad_meses)

    dist_alt = SNAP["dist_alt"].get(e["DistritoREN"], SNAP["dist_alt_global"])
    altura_ren = e["AlturaREN"] if pd.notna(e["AlturaREN"]) else dist_alt
    alt_vs_distrito = altura_ren - dist_alt

    prev_renipress = SNAP["prev_renipress_enc"].get(req.renipress, SNAP["prior"])
    roll_distrito = SNAP["distrito_365d"].get(e["DistritoREN"], np.nan)
    if pd.isna(roll_distrito):
        roll_distrito = SNAP["departamento"]["roll_eess_365d"]

    n_atenciones = sum([req.cred, req.suplementacion, req.consejeria, req.sesion])
    talla_m = req.talla / 100
    imc = req.peso / (talla_m ** 2)
    peso_x_mes = req.peso / edad_meses
    talla_x_mes = req.talla / edad_meses

    hbc_fallback = _rate("roll_eess_hbc_365d", req.renipress, red)
    if req.tiene_historial and req.hb_previa is not None:
        hist_hbc_prev = hist_hb_prev = hist_hbc_media = float(req.hb_previa)
        hist_hbc_prev2 = float(req.hb_previa)
        if req.fecha_previa is not None:
            gap = max((req.fecha_atencion - req.fecha_previa).days, 1)
        else:
            gap = 180
        hist_hbc_x_gap = (hist_hbc_prev - HB_CUTOFF) * np.log1p(gap)
        tiene_historia = 1
    else:
        hist_hbc_prev = hist_hbc_prev2 = hist_hbc_media = hist_hb_prev = hbc_fallback
        hist_hbc_x_gap = 0.0
        tiene_historia = 0

    return {
        "hist_eess_prev_90d": _rate("hist_eess_prev_90d", req.renipress, red),
        "roll_eess_30d": _rate("roll_eess_30d", req.renipress, red),
        "roll_eess_365d": _rate("roll_eess_365d", req.renipress, red),
        "roll_eess_7d": _rate("roll_eess_7d", req.renipress, red),
        "roll_eess_banda_edad": _rate_banda(req.renipress, banda),
        "roll_eess_hbc_30d": _rate("roll_eess_hbc_30d", req.renipress, red),
        "roll_eess_hbc_90d": _rate("roll_eess_hbc_90d", req.renipress, red),
        "roll_eess_hbc_365d": hbc_fallback,
        "prev_Renipress": prev_renipress,
        "roll_distrito_365d": roll_distrito,
        "roll_red_30d": _rate_red("roll_eess_30d", red),
        "alt_vs_distrito": alt_vs_distrito,
        "hist_hbc_prev": hist_hbc_prev,
        "hist_hbc_prev2": hist_hbc_prev2,
        "hist_hbc_media": hist_hbc_media,
        "hist_hb_prev": hist_hb_prev,
        "hist_hbc_x_gap": hist_hbc_x_gap,
        "EdadMeses": edad_meses,
        "Sexo": req.sexo,
        "Cred": float(req.cred),
        "Suplementacion": float(req.suplementacion),
        "n_atenciones": n_atenciones,
        "DistritoREN": e["DistritoREN"],
        "Microred": e["Microred"],
        "Peso": req.peso,
        "Talla": req.talla,
        "imc": imc,
        "peso_x_mes": peso_x_mes,
        "talla_x_mes": talla_x_mes,
        "SIS": float(req.sis),
        "Juntos": float(req.juntos),
        "Qaliwarma": float(req.qaliwarma),
        "Consejeria": float(req.consejeria),
        "Sesion": float(req.sesion),
        "hist_tiene_historia": tiene_historia,
    }


def _prep(row: dict) -> pd.DataFrame:
    X = pd.DataFrame([row])[MODEL["features"]]
    for c in MODEL["cat_cols"]:
        X[c] = pd.Categorical(X[c].astype(str), categories=MODEL["cat_levels"][c])
        X[c] = X[c].cat.codes.replace(-1, np.nan)
    return X.fillna(-999)


def _explicar(X: pd.DataFrame, top_n: int = 6) -> list[dict]:
    """Real per-case SHAP values from the fitted CatBoost model -- not a
    fabricated or globally-averaged importance."""
    pool = Pool(X)
    shap = MODEL["model"].get_feature_importance(pool, type="ShapValues")
    contrib = shap[0][:-1]  # last column is the bias term
    order = np.argsort(-np.abs(contrib))[:top_n]
    max_abs = max(abs(contrib[i]) for i in order) or 1.0
    out = []
    for i in order:
        name = MODEL["features"][i]
        val = float(contrib[i])
        out.append({
            "label": FEATURE_LABELS.get(name, name),
            "direccion": "sube" if val > 0 else "baja",
            "intensidad": round(float(min(abs(val) / max_abs, 1.0)), 3),
        })
    return out


@app.get("/info")
def info():
    return {"modelo": {"features": len(MODEL["features"]), "test_auc": CONFIANZA["auc"]},
            "confianza": CONFIANZA}


@app.get("/establecimientos")
def establecimientos():
    e = SNAP["eess"].reset_index()
    e["nombre"] = e["EESS"].apply(clean_eess_name)
    e = e.dropna(subset=["DistritoREN"]).sort_values("nombre")
    return [{"renipress": r.Renipress, "nombre": r.nombre, "distrito": r.DistritoREN,
             "provincia": "LIMA", "red": r.Red, "altura": r.AlturaREN}
            for r in e.itertuples()]


@app.get("/distritos")
def distritos():
    distritos = sorted(SNAP["eess"]["DistritoREN"].dropna().unique().tolist())
    return {"LIMA": distritos}


@app.post("/predecir")
def predecir(req: PredictRequest):
    row = build_features(req)
    X = _prep(row)
    proba = float(MODEL["model"].predict_proba(X)[0, 1])
    thr = MODEL["threshold"]
    riesgo_alto = proba >= thr
    factores = _explicar(X)

    return {
        "probabilidad": round(proba, 4),
        "riesgo_alto": riesgo_alto,
        "edad_meses": round(row["EdadMeses"], 1),
        "prevalencia_promedio": CONFIANZA["prevalencia_promedio"],
        "factores": factores,
        "confianza": CONFIANZA,
    }


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
