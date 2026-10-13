# Guía de despliegue — Creciendo Sano (API + interfaz)

Esta app es un único servicio FastAPI que sirve la API (`/predecir`,
`/establecimientos`, `/distritos`, `/info`) y la interfaz web estática
(`web/index.html`, `web/app.js`) desde el mismo proceso: `app.py` monta
`web/` en la ruta raíz. **No hay frontend separado**, así que no se necesita
Vercel: basta con un solo servicio en Render. Si en el futuro separas el
frontend en su propio proyecto, la sección "Si separas el frontend" al
final explica cómo conectar Vercel a este backend.

## 1. Subir el código a GitHub

```bash
cd deploy_app
# el repo git y el primer commit ya existen (git init + commit ya hechos)
gh repo create creciendo-sano-anemia-lima --private --source=. --remote=origin
git push -u origin master
```

Si no tienes `gh` (GitHub CLI), crea el repositorio manualmente en
github.com → "New repository" → sin README/licencia (ya existen en local) →
copia la URL, luego:

```bash
git remote add origin https://github.com/<tu-usuario>/creciendo-sano-anemia-lima.git
git branch -M main
git push -u origin main
```

## 2. Crear el servicio en Render

1. Entra a https://render.com y crea una cuenta (puedes usar tu cuenta de
   GitHub para iniciar sesión, así Render pide permiso para leer tus repos).
2. Dashboard → **New +** → **Web Service**.
3. Conecta el repositorio `creciendo-sano-anemia-lima` que acabas de subir.
4. Render detecta `render.yaml` automáticamente y precarga la configuración
   (nombre, build command, start command). Si prefieres configurarlo a
   mano en vez de usar `render.yaml`, usa estos valores:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`
5. No se requieren variables de entorno adicionales (el modelo no usa
   claves ni credenciales externas).
6. Click **Create Web Service**. El primer build tarda 3-6 minutos
   (instala catboost, pandas, etc.).

## 3. Verificar que funciona

Cuando el deploy termine, Render te da una URL del tipo
`https://creciendo-sano-anemia-lima.onrender.com`.

```bash
curl https://creciendo-sano-anemia-lima.onrender.com/info
```

Debe responder con el JSON de métricas (`"test_auc":0.7411`, etc.). Luego
abre la URL en el navegador: debe cargar el formulario de "Creciendo Sano".

**Si falla:**
- Revisa la pestaña **Logs** del servicio en Render — casi siempre es un
  error de import (dependencia faltante en `requirements.txt`) o un error
  al cargar los artefactos (`artifacts/*.pkl` no subidos — revisa
  `git status` y que no estén en `.gitignore`).
- Error 502/503 al abrir la URL justo después del deploy: el servicio
  puede estar todavía arrancando (carga ~45 MB de artefactos en memoria);
  espera 30-60 segundos y recarga.
- Si el build falla instalando `catboost` o `pandas` (error tipo
  `AttributeError: 'Distribution' object has no attribute 'dry_run'` o
  "Failed building wheel for catboost"): Render está usando una versión de
  Python demasiado nueva (sin wheel precompilado para `catboost`, que
  termina compilándose desde cero y falla). `render.yaml` fija
  `PYTHON_VERSION=3.11.9`, pero esa variable **solo se aplica si creaste el
  servicio con el botón "New + → Blueprint"** (el que lee `render.yaml`
  automáticamente). Si lo creaste con "New + → Web Service" a mano, Render
  ignora `render.yaml` por completo y usa su versión de Python más
  reciente por defecto. El repo ya incluye un archivo `.python-version`
  (con `3.11.9`), que Render sí respeta en ambos flujos; si el problema
  persiste, fija la versión también a mano: en el servicio → **Environment**
  → **Add Environment Variable** → `PYTHON_VERSION` = `3.11.9` → guarda y
  dispara un **Manual Deploy → Clear build cache & deploy**.

## 4. Actualizar la app en el futuro

Render se conecta al repositorio y redespliega automáticamente con cada
`git push` a la rama principal:

```bash
# después de editar app.py, el modelo, o la interfaz
git add -A
git commit -m "describe el cambio"
git push
```

Render detecta el push, reconstruye y reemplaza el servicio en vivo sin
que tengas que hacer nada en el dashboard (puedes ver el progreso en la
pestaña **Events**).

## 5. Limitaciones del plan gratuito de Render

- **Se duerme por inactividad**: tras ~15 minutos sin tráfico, el servicio
  se apaga; la siguiente visita tarda 30-60 segundos en "despertar"
  (cold start) mientras Render reconstruye el contenedor y tu app recarga
  los ~45 MB de `serving_snapshot.pkl` en memoria.
- **750 horas/mes gratis** compartidas entre todos tus servicios free —
  suficiente para un solo servicio corriendo todo el mes.
- **512 MB de RAM** en el plan free; este modelo (CatBoost + un snapshot de
  ~45 MB en pandas) cabe cómodo, pero si en el futuro agregas más tablas
  de servicio conviene vigilar el uso de memoria en la pestaña **Metrics**.
- Sin dominio propio en el plan free (usa el subdominio `.onrender.com`);
  se puede añadir un dominio personalizado en planes pagos.

## No importar este repo en Vercel

Si ya creaste un proyecto en Vercel apuntando a este mismo repositorio,
bórralo: Vercel empaqueta cada app como una función serverless con un
límite de 500 MB, y este backend (catboost + pandas + numpy + ~45 MB de
artefactos) pesa cerca de 680 MB — no es un problema de dependencias de
más, es que este tipo de app (modelo cargado en memoria, proceso de larga
duración) no es lo que una función serverless está hecha para servir.
Render, en cambio, corre un servidor persistente (sin ese límite de
tamaño), que es exactamente lo que `app.py` necesita.

## Si separas el frontend (Vercel)

Esta versión no lo necesita, pero si en algún momento separas `web/` en su
propio proyecto de frontend (por ejemplo para usar un framework como
React/Vite), así se conecta a este backend:

1. Despliega `web/` como un proyecto estático en Vercel
   (`vercel.com` → **New Project** → importa el repo del frontend).
2. En el código del frontend, reemplaza las llamadas relativas
   (`fetch('/predecir')`) por una variable de entorno:
   ```js
   const API_URL = import.meta.env.VITE_API_URL || '';
   fetch(`${API_URL}/predecir`, { ... });
   ```
3. En Vercel → **Settings → Environment Variables**, agrega
   `VITE_API_URL=https://creciendo-sano-anemia-lima.onrender.com`.
4. En el backend (`app.py`), habilita CORS para el dominio de Vercel
   (FastAPI: `from fastapi.middleware.cors import CORSMiddleware`), porque
   frontend y backend ya no comparten origen.
