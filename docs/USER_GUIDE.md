# Guia de uso de Sleep Learning Engine

Tutorial paso a paso para producir un video de sleep-learning cada vez
que quieras. Asume que el proyecto ya esta clonado en
`D:\proyectos\Proyectos Github\sleep_learning_engine`.

---

## Setup inicial (solo la primera vez)

### 1. Instalar uv (una vez por maquina)

Si todavia no lo tienes:

```powershell
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Cierra y abre la terminal para que tome el PATH.

### 2. Instalar dependencias

Desde la carpeta del proyecto:

```powershell
cd "D:\proyectos\Proyectos Github\sleep_learning_engine"
uv sync
```

Esto crea `.venv` y baja todo lo necesario (incluye pytest, ruff, mypy).

### 3. Dejar ffmpeg listo

Necesitas `ffmpeg.exe` (Windows) o `ffmpeg` (macOS/Linux). Cualquier
build 6.x u 8.x sirve. La forma mas facil:

1. Baja un build estatico desde
   https://www.gyan.dev/ffmpeg/builds/ (Windows) o
   https://johnvansickle.com/ffmpeg/ (Linux).
2. Copia `ffmpeg.exe` y `ffprobe.exe` a
   `D:\proyectos\Proyectos Github\sleep_learning_engine\cache\`.
3. Listo. El studio los detecta ahi primero.

Si ya tienes ffmpeg en el PATH del sistema, tambien lo encuentra.
Opcionalmente puedes setear la variable `FFMPEG_BIN` apuntando a tu
binario.

### 4. Generar la libreria de ambientes (una vez)

Para no depender de internet ni de copyright, el proyecto trae un
generador procedural. Solo correlo una vez:

```powershell
uv run python scripts/generate_ambient.py
```

Te crea 14 pistas en `assets\ambient\` (rain, ocean, forest, fire,
wind, river, brown noise, pink noise, alpha binaural, alpha pulse,
lofi, night crickets, cafe murmur). Cada una 60 segundos, perfecta
para loopear. Estas NO se suben al repo, son tu copia local.

### 5. (Opcional) API key para generar el guion

Por defecto puedes pegar un guion en la app. Si quieres que la IA
genere el guion desde un tema, saca tu key gratis en
https://build.nvidia.com (DeepSeek V4 en el free tier, 40 RPM).

Crea `.env` desde la plantilla:

```powershell
copy .env.example .env
notepad .env
```

Reemplaza `SLEEPLENS_API_KEY=` con tu key real. Guarda y cierra.

---

## Hacer un video (cada vez)

Tienes dos formas: GUI (mas visual) o CLI (mas rapida para CI).

### Opcion A - GUI (recomendado para empezar)

```powershell
cd "D:\proyectos\Proyectos Github\sleep_learning_engine"
uv run python run.py
```

Se abre la ventana oscura. Vas a ver 5 pestanas.

#### Pestana Topic

Tienes dos caminos:

- **Escribir un tema** en la caja grande. La IA generara un guion
  completo (necesita API key). Por ejemplo:
  "the history of the roman empire, told in a calm, sleep-friendly way"
- **Pegar un guion propio**: abajo del todo, en "Or load a script
  file", escribe la ruta a un `.txt` o usa el boton Browse.

Ajustes utiles de la pestana:

| Campo | Que hace | Tip |
| ----- | -------- | --- |
| Language | Idioma del guion | `en`, `es`, `pt`, etc. |
| Target word count | Largo objetivo del guion | 4500 = ~30 min de narracion |
| Pause between paragraphs | Silencio entre parrafos | 1.8 s funciona bien |

#### Pestana Provider

Aqui normalmente no tocas nada. La默认值 es NVIDIA NIM con DeepSeek
V4. Si quieres usar Ollama o LM Studio, elige del dropdown y la app
ajusta la URL y el modelo automaticamente.

#### Pestana Visuals

Tienes dos campos para el fondo:

- **Image**: una imagen estatica (PNG, JPG, WEBP). La app la
  mostrara en bucle (en realidad es estatica pero como fondo luce
  igual).
- **Video loop**: un clip corto (MP4, MOV, MKV). La app lo loopeara
  hasta llenar todo el video. Ideal para escenas de lluvia cayendo,
  una ventana con nieve, etc.

Tambien puedes arrastrar el archivo directo al cuadrado punteado
"Drag files here".

Si dejas los dos vacios, la app genera un fondo oscuro procedural
con estrellas y un mensaje "breathe in . breathe out". Es el
fallback automatico.

#### Pestana Audio

- **TTS backend**: dejalo en `edge` (gratis, sin key).
- **Voice**: el id del voice. Por defecto `en-US-AriaNeural`. Para
  espanol prueba `es-ES-ElviraNeural` o `es-MX-JorgeNeural`. Edge
  TTS tiene cientos de voces; puedes ver la lista en
  https://tts.travisvn.com o probar en
  https://speech.microsoft.com/portal.
- **Rate**: velocidad de la voz. `-5%` o `-10%` queda perfecto para
  dormir. `+0%` es normal.
- **Pitch**: tono. `-2Hz` lo hace un poquito mas grave y calmado.
- **Ambient bed mode**:
  - `auto`: la app elige el track que mas matchee con tu guion
    (rain, ocean, lofi, ...).
  - `keyword`: solo elige si hay match exacto.
  - `random`: agarra cualquiera.
  - `disabled`: sin ambient, solo la voz.
- **Bed volume**: cuanto se oye el ambient. 0.18 va bien. Mas alto
  = mas lluvia, menos voz.
- **Duck amount (dB)**: cuanto baja el ambient cuando habla la voz.
  12 dB es agresivo (voz clarisima); 6 dB es sutil (ambiente mas
  presente).

#### Pestana Render

- **Output preset**: `sleep_720p` (default) o `sleep_1080p` si quieres
  Full HD. `audio_only` te da solo el MP3.
- **Encoder**: dejalo en `auto`. Si tienes NVIDIA, usa NVENC. Si
  tienes AMD, usa AMF. Si nada, libx264 (CPU, mas lento).
- **fps**: 24 esta bien. 30 si quieres mas fluidez.
- **Bar height**: grosor de la barra verde. 6 px queda bien.
- **Bar position**: `bottom` o `top`.

#### Boton Render video

Click. La app empieza a:

1. Cargar o generar el guion.
2. Renderizar la voz (Edge TTS, tarda ~10 s por parrafo).
3. Medir tiempos y calcular el runtime final.
4. Elegir y mezclar el ambient.
5. Generar o cargar el fondo.
6. Encodear el MP4 final.

El log de abajo te muestra cada paso. Al terminar, el archivo
queda en `output\sleep_learning_engine-<timestamp>.mp4`.

Si te equivocas o demora mucho, click en **Cancel** y se detiene
limpio.

### Opcion B - CLI (rapida, repetible, ideal para CI)

```powershell
# Desde un tema
uv run python run.py render --topic "the history of jazz" --output-stem jazz

# Desde un guion propio
uv run python run.py render --script .\mi-guion.txt --output-stem mi-leccion

# Con fondo personalizado
uv run python run.py render --topic "..." --background-image assets\visuals\rain.jpg

# Salida JSON para CI
uv run python run.py render --topic "..." --json
```

El flag `--json` imprime una sola linea con el resultado, facil de
parsear:

```json
{"status": "ok", "output": "...\\jazz.mp4", "duration_seconds": 1820.5, "word_count": 4520, "runtime": "30m 20s"}
```

---

## Ajustes rapidos que vas a usar todo el tiempo

| Quiero... | Que hago |
| --------- | -------- |
| Cambiar la voz | Audio tab > cambia el campo Voice |
| Mas pausa entre parrafos | Topic tab > sube "Pause between paragraphs" |
| Video mas largo | Topic tab > sube "Target word count" |
| Video mas corto | Topic tab > baja "Target word count" |
| Fondo personalizado | Visuals tab > escribe ruta o arrastra |
| Solo audio, sin video | Render tab > preset "audio_only" |
| Otro idioma | Topic tab > cambia Language |
| Ambiente con mas presencia | Audio tab > sube "bed volume" |
| Ambiente mas sutil | Audio tab > baja "bed volume" o subelo en "duck dB" |
| Mas calidad de imagen | Render tab > preset "sleep_1080p" |

---

## Donde queda todo

```
D:\proyectos\Proyectos Github\sleep_learning_engine\
  output\                  <- tus MP4 finales aqui
  cache\tts\               <- cache de TTS (segmentos por parrafo)
  cache\mixed.wav          <- mezcla final voz + ambient
  assets\ambient\          <- 14 pistas procedurales (solo en tu maquina)
  assets\visuals\          <- si pones fondos personalizados
  logs\sleep_learning_engine.log       <- log rotado, util si algo falla
  .sleep_learning_engine.toml          <- ajustes persistidos (se sobreescribe al render)
  .env                     <- tu API key (NO se sube al repo)
```

---

## Problemas comunes

**"ffmpeg not found"**
- Pasa si no hay ffmpeg ni en `cache\` ni en PATH ni via
  `FFMPEG_BIN`. Ve a la seccion "Dejar ffmpeg listo" arriba.

**"Authentication failed" del proveedor**
- API key mal copiada o expirada. Reemplazala en `.env` o pegala
  directo en la pestana Provider de la GUI.

**"No ambient tracks found"**
- No has corrido `scripts/generate_ambient.py` o tu carpeta
  `assets\ambient\` esta vacia. Correl una vez.

**El video sale sin barra de progreso**
- Si la imagen de fondo es muy oscura, la barra verde aun se ve.
  Si no se ve, revisa que "Bar height" no este en 0.

**Quiero resetear todos los ajustes**
- Borra `.sleep_learning_engine.toml` y vuelve a abrir la app. Arranca con los
  valores por defecto.

**Los tests fallan despues de un cambio**
- Correlos con detalle: `uv run pytest -v`
- Si solo falla uno, agregale `-k nombre_del_test` para aislarlo.

---

## Workflow recomendado (en produccion)

1. Escribe un `.txt` con el guion (en espanol, ingles, lo que sea).
   Mas control que dejar a la IA inventar.
2. Elige un fondo que pegue con el tema (lluvia para tristeza,
   estrellas para astronomia, etc.).
3. Elige el ambient que matchee (rain, lofi, alpha, ocean).
4. Render con `--script` y `--background-image`.
5. Sube el MP4 a YouTube, podcast, donde quieras.

Tiempo tipico para un video de 30 min: ~5-10 min en una laptop
moderna con NVENC, ~15-20 min con libx264.
