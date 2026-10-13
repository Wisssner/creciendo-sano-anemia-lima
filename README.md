# Creciendo Sano — API de tamizaje de anemia (Lima)

Servicio único (API + interfaz web) que sirve el modelo CatBoost final
(35 variables, ROC AUC 0.7411 en test 2025) entrenado con datos reales de
Lima. No requiere base de datos ni servicios externos: los artefactos
(`artifacts/modelo_reducido.pkl`, `artifacts/serving_snapshot.pkl`) ya
contienen el modelo y las tablas de respaldo necesarias.

## Ejecutar en local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app:app --reload --port 8010
```

Abrir `http://127.0.0.1:8010/`.

## Estructura

```
app.py                  API FastAPI (/predecir, /establecimientos, /distritos, /info) + sirve web/
artifacts/               modelo final y tablas de servicio (congelados, no se regeneran aquí)
web/                      interfaz estática (HTML/JS), servida por la misma app
requirements.txt         dependencias con versión fija
render.yaml               configuración de despliegue en Render
```

## Despliegue

Ver `GUIA_DEPLOY.md` para los pasos exactos (GitHub → Render).

## Advertencia de uso

No reemplaza la medición de hemoglobina ni el criterio clínico. Apoya la
priorización de tamizaje; no diagnostica. Validado únicamente con datos de
Lima 2016-2025.
