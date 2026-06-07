# Mi tutorial de Sleeplens

Asume que ya tenés todo instalado en `D:\proyectos\Proyectos Github\sleeplens`
(uv, venv, ffmpeg en cache, las 14 pistas de ambient, 15 tests pasando).

## Tu caso de uso

Vos escribís un `.txt` con el guion en español (o el idioma que quieras),
lo metés en la app, y sale un MP4. Sin tocar la API, sin la IA generando
nada. **El tutorial es solo eso.**

---

## Hacer un video (3 pasos, ~2 min de setup + render)

### 1. Escribí el guion

Abrí un bloc de notas y guardalo en alguna carpeta, por ejemplo
`D:\proyectos\Proyectos Github\sleeplens\output\`.

Formato: párrafos separados por una línea en blanco. Cada párrafo
se convierte en un bloque narrado con una pausa entre ellos.

Ejemplo (`D:\proyectos\Proyectos Github\sleeplens\output\historia-roma.txt`):

```
Bienvenido. Hoy vamos a recorrer dos mil años de historia sin
prisas, dejando que cada dato se asiente antes de pasar al siguiente.

Roma empezó como un pequeño asentamiento a orillas del río Tíber,
alrededor del año 753 antes de nuestra era. Sus primeros habitantes
vivían de la agricultura y el pastoreo.

Con el tiempo, esos pastores aprendieron a organizarse. Construyeron
murallas, eligieron reyes, y aprendieron a defenderse de los pueblos
vecinos que bajaban desde las montañas en busca de tierras fértiles.

La República llegó en el año 509 antes de Cristo, cuando los
romanos decidieron que ya no querían reyes. En su lugar crearon
una red de magistraturas, cónsules anuales y un Senado que
representaba a las familias más antiguas.
```

Más largo = más duración. ~150 palabras por minuto. **4500 palabras ≈ 30 min.**

### 2. Abrí la app

```powershell
cd "D:\proyectos\Proyectos Github\sleeplens"
uv run python run.py
```

Vas a la pestaña **Topic** y en el campo de abajo del todo
("Or load a script file") ponés la ruta a tu `.txt`, o usás el
botón **Browse** y elegís el archivo.

El textarea grande de arriba lo dejás vacío (no querés que la IA
genere nada, vos ya trajiste el guion).

### 3. Configurá rápido y dale Render

Ajustes que importan:

| Pestaña | Campo | Valor recomendado | Por qué |
| ------- | ----- | ----------------- | ------- |
| **Topic** | Pause between paragraphs | `1.8` s | Pausa cómoda para absorber |
| **Topic** | Language | `en` | English |
| **Audio** | Voice (dropdown) | `Aria — warm, conversational female [top pick]` | El dropdown ya tiene 46 voces curadas |
| **Audio** | TTS Rate | `-10%` | Más lento = más calmado |
| **Audio** | TTS Pitch | `-2Hz` | Un poco más grave |
| **Audio** | Ambient bed mode | `auto` | Matchea por keyword (rain, ocean, lofi, etc.) |
| **Audio** | Bed volume | `0.18` | Ambiente presente pero no tapa la voz |
| **Audio** | Duck amount | `12` dB | Voz clarísima, ambient baja cuando hablás |
| **Render** | Output preset | `sleep_720p` o `sleep_1080p` para Full HD | Suficiente para YouTube y podcast |
| **Render** | Encoder | `auto` | NVENC si tenés NVIDIA, si no libx264 |

Lo demás lo dejás como está. Si no querés tocar nada, los defaults
ya funcionan.

**Click "Render video"** y esperás. La barra de progreso te muestra
qué paso está corriendo (script → voz → timing → ambient → mix →
visual → encode).

### 4. Listo, agarrá el MP4

Cuando termina, el sidebar te muestra dónde quedó, qué tan largo es
y el estado del pipeline. El archivo vive en:

```
D:\proyectos\Proyectos Github\sleeplens\output\sleeplens-1717729384.mp4
```

El nombre es la timestamp del momento. Si querés un nombre más
amigable, renombralo desde el explorador de Windows o desde la
terminal:

```powershell
Rename-Item "D:\proyectos\Proyectos Github\sleeplens\output\sleeplens-1717729384.mp4" "historia-roma-30m.mp4"
```

### 4b. Botones del sidebar (de arriba para abajo)

| Botón | Qué hace |
| ----- | -------- |
| **Render full video** | El flujo completo: script → voz → ambient → mix → visual → encode |
| **Generate script only** | Solo genera el guion y lo guarda como `.txt` en `output/`. Útil para iterar el texto antes de invertir 5 min en renderizar audio + video |
| **Save settings (API key, model, etc.)** | Persiste TODO (API key, modelo, voz, ambient, output) en `.sleeplens.toml`. No necesitas renderizar para guardar |
| **Cancel** | Aparece habilitado durante un render. Cancela limpiamente (los archivos parciales se limpian) |

---

## Generar solo el guion (para iterar rápido)

Si querés probar varios enfoques del mismo tema sin esperar el
render completo cada vez, usá **Generate script only**. Te guarda
el `.txt` en `output/` y te dice la ruta. Después podés:

- Releerlo y ajustarlo
- Cargar ese `.txt` en el campo "Or load a script file" de la
  pestaña Topic
- Renderizar el video con el guion ya pulido

Tiempo típico: 5-15 segundos por iteración de guion, vs 5-10 min
por render completo.

---

## Atajo: si no querés abrir la GUI

Todo se puede hacer desde la terminal sin abrir la app:

```powershell
cd "D:\proyectos\Proyectos Github\sleeplens"

# Lo más simple
uv run python run.py render --script "D:\proyectos\Proyectos Github\sleeplens\output\historia-roma.txt"

# Con nombre de salida personalizado
uv run python run.py render --script .\output\historia-roma.txt --output-stem historia-roma

# Con fondo personalizado
uv run python run.py render --script .\output\historia-roma.txt --background-image D:\fondos\lluvia.jpg --output-stem historia-roma

# Salida JSON para logs/CI
uv run python run.py render --script .\output\historia-roma.txt --json
```

El flag `--json` te imprime una línea así, útil si querés loguear
cuánto tardó:

```json
{"status": "ok", "output": "...\\historia-roma.mp4", "duration_seconds": 1820.5, "word_count": 4520, "runtime": "30m 20s"}
```

---

## Querés cambiar algo entre videos

| Si querés... | Andá a | Tocá |
| ------------- | ------ | ---- |
| Voz diferente | Audio tab | Cambiá el dropdown **Voice** (46 curadas, todas en español, inglés, etc.) |
| Voz custom (no está en el dropdown) | Audio tab | Elegí **Custom...** en el dropdown, escribí el id en el campo de al lado |
| Otro ambient (lluvia → océano) | Audio tab | Cambiá el campo **Ambient bed mode** a `keyword` o `random` |
| Sin ambient (solo voz) | Audio tab | **Ambient bed mode** = `disabled` |
| Más pausas | Topic tab | Subí **Pause between paragraphs** a `2.5` o `3` |
| Video más largo | Topic tab | Escribí un guion con más palabras |
| Fondo con imagen/video | Visuals tab | Pegá la ruta o arrastrá el archivo |
| Resolución 1080p | Render tab | **Output preset** = `sleep_1080p` |
| Solo audio MP3 | Render tab | **Output preset** = `audio_only` |
| Cambiar el modelo de IA | Provider tab | Dropdown **Model** (curado por provider); o **Custom...** para escribir uno |
| Editar el system prompt | Provider tab | Click **Show advanced**, editá el textbox. Si lo dejás vacío, usa el default |

---

## Voces en el dropdown (curadas para sleep)

El dropdown **Voice** de la pestaña Audio tiene 46 voces curadas
de Edge TTS, organizadas por idioma:

| Idioma | Cantidad | Top picks |
| ------ | -------- | --------- |
| English (US) | 8 | **Aria** (mujer, cálida), **Brian** (hombre, profunda) |
| English (UK) | 4 | **Ryan** (hombre, audiobook) |
| English (AU / CA / IN / IE) | 5 | Natasha, William, Clara, Neerja, Emily |
| Spanish (ES / MX / AR) | 5 | Elvira, Laura, Dalia, Jorge, Elena |
| French (FR / CA) | 3 | Denise, Henri, Sylvie |
| German | 2 | Katja, Conrad |
| Italian | 3 | Elsa, Diego, Isabella |
| Portuguese (BR / PT) | 3 | Francisca, Antonio, Raquel |
| Japanese | 2 | Nanami, Keita |
| Chinese (CN / HK / TW) | 4 | Xiaoxiao, Yunyang, HiuMaan, HsiaoChen |
| Other | 7 | Korean, Dutch, Polish, Russian, Turkish, etc. |

Si querés una voz que no esté en la lista, elegí **Custom...** en
el dropdown y escribí el id en el campo de al lado (ej.
`en-US-MichelleNeural`).

### Cómo elegir la mejor voz para tu video

Ya tenés 17 muestras de audio (10-17 segundos cada una) en
`output/voice-previews/`. Abrí esa carpeta en el explorador y
reproducí los MP3 hasta dar con la que más te guste. El id exacto
que aparece en el nombre del archivo lo buscás en el dropdown.

Si querés regenerarlas o probar más:

```powershell
# Regenerar todas
uv run python scripts/voice_preview.py

# Probar una sola voz
uv run python scripts/voice_preview.py --voice en-US-BrianNeural

# Probar con tu propio texto
uv run python scripts/voice_preview.py --text "The story of jazz, told slowly and calmly."
```

### Ajustes finos por voz (top picks)

Todas las muestras están grabadas con **rate `-10%`** y **pitch `-2Hz`**.
Si querés afinar más:

| Voice | Rate | Pitch | Por qué |
| ----- | ---- | ----- | ------- |
| `en-US-AriaNeural` | `-10%` | `-2Hz` | Default cálido |
| `en-US-BrianNeural` | `-8%` | `-3Hz` | Ya es grave, no exagerar |
| `en-US-EmmaNeural` | `-15%` | `0Hz` | Ya es susurrada, no pitch down |
| `en-US-AndrewNeural` | `-12%` | `-2Hz` | Audiobook pace |
| `en-GB-RyanNeural` | `-10%` | `-2Hz` | Default |

---

## Modelos de IA (Provider tab)

El dropdown **Model** muestra los modelos más comunes para el
proveedor seleccionado. Cambia solo cuando cambiás de provider.

| Provider | Modelos curados |
| -------- | --------------- |
| NVIDIA NIM (default) | DeepSeek V4, DeepSeek R1, Llama 3.1 70B, Llama 3.1 8B, Mistral Large 2, Qwen 2.5 72B |
| OpenAI | GPT-4o mini, GPT-4o, GPT-4.1 mini, GPT-4.1, o1-mini, o1-preview |
| Anthropic (via proxy) | Claude Sonnet 4.5, Claude Opus 4, Claude Haiku 4 |
| Ollama (local) | Llama 3.1, Llama 3.2, Mistral, Qwen 2.5, Phi-3 |
| LM Studio (local) | local-model |
| Custom | lo que vos pongas |

Si querés un modelo que no está, elegí **Custom...** y escribí
el id en el campo de al lado. Click **Load model list from
provider** para que el provider te devuelva su lista actual y se
fusione con la curada.

---

## System prompt (avanzado)

Por default la IA escribe con un tono calmado, en segunda persona,
con pausas entre párrafos. Si querés cambiar el tono (más formal,
más corto, más poético, en otro estilo):

1. Pestaña **Provider**
2. Click **Show advanced (system prompt)**
3. Editá el textbox con tus instrucciones

Si lo dejás vacío, usa el default. Si lo llenás, sobreescribe el
default para esa sesión (se guarda en `.sleeplens.toml`).

---

## Troubleshooting express

**Tarda mucho en renderizar**
- Normal para videos largos. ~5-10 min por hora de video con NVENC.
- Si tenés NVIDIA, la pestaña Render debería mostrar NVENC
  automáticamente. Fijate en el log.
- Si usás CPU (libx264), puede ser 2-3x más lento. Está bien.

**`Cannot load nvcuda.dll` o `Error opening encoder` en el log**
- Tu ffmpeg tiene NVENC compilado pero no tenés el runtime de CUDA
  instalado. La app ahora detecta esto automáticamente: si el
  encoder falla en el primer frame, hace fallback a `libx264` y
  termina el render. Fijate en el log, debería decir
  `Encoder h264_nvenc failed at init ... Retrying with libx264.`
- Si querés acelerar con GPU de verdad, instalá los drivers
  actuales de NVIDIA + CUDA runtime. Mientras tanto, dejá el
  selector de encoder en `auto` y la app resuelve sola.

**`ffmpeg exited with code 4294967284` o `Cannot allocate memory`**
- Tu equipo se quedó sin RAM. La encode 1080p necesita ~700 MB
  libres y el filtro `geq` (barra de progreso) suma otros 150 MB.
  En un equipo con 8 GB de RAM total y Windows + navegador
  abiertos, no queda espacio.
- **Solución rápida:** bajá la resolución a 720p en la pestaña
  Render (4x menos memoria para el filter graph) y bajá el
  preset de libx264 a `ultrafast`. La encode termina a costa de
  un poco de calidad pero el video sale completo.
- **Solución nube:** corré el render en Google Colab (gratis).
  Tirá `python -m sleeplens cloud` desde la carpeta del proyecto
  y abrí la URL. El notebook tiene T4 GPU + 12.7 GB de RAM, y
  termina la encode 1080p en 1-2 minutos con NVENC real.

**La voz suena rara o muy rápida**
- Bajá **TTS Rate** a `-15%` o `-20%`.
- Cambiá **Voice** a otra. Probá `es-ES-LauraNeural` o `es-AR-ElenaNeural`.

**El ambient no aparece**
- Abrí `assets\ambient\` y verificá que estén los 14 archivos
  `.ogg`. Si está vacío, corré una vez:
  `uv run python scripts\generate_ambient.py`
- Si querés que el generador **deje las pistas al mismo volumen**
  (importante: el mixer hace duck/unduck, y si una pista está 6 dB
  más alta que otra te despertás), agregá `--normalize`:
  `uv run python scripts\generate_ambient.py --normalize`

**Quiero que el ambient varíe, no siempre la misma pista**
- Por default, sleeplens arma un **playlist aleatorio sin
  repetición** con las pistas que matchean los keywords del
  script. Cada pista suena una vez antes de que el ciclo
  completo se repita, así un video de 6 horas no es la misma
  pista 360 veces.
- Si querés forzar el comportamiento (auto / keyword / random /
  disabled), cambiá **Ambient bed mode** en la pestaña Audio.

**Quiero ver el log detallado de un error**
- Está en `D:\proyectos\Proyectos Github\sleeplens\logs\sleeplens.log`
  (rota a 5 MB con 5 archivos de historia).

**Quiero resetear todos los ajustes a default**
- Borrá `D:\proyectos\Proyectos Github\sleeplens\.sleeplens.toml`.
  La próxima vez que abras la app arranca limpia.

---

## Tu setup en una línea

```
D:\proyectos\Proyectos Github\sleeplens\
  .venv\                <- venv manejado por uv
  cache\ffmpeg.exe      <- binario ffmpeg
  assets\ambient\       <- 14 pistas procedurales (rain, lofi, etc.)
  output\               <- donde caen tus MP4 finales
  output\voice-previews <- 17 muestras de voz para elegir tu favorita
  logs\                 <- log rotado para debug
  docs\USER_GUIDE.md    <- tutorial genérico para nuevos usuarios
  docs\MI_TUTORIAL.md   <- este archivo
```

Listo, con esto podés producir videos en piloto automático.
El setup está hecho, solo falta el contenido.
