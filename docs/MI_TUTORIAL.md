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
| **Audio** | TTS Voice | `en-US-AriaNeural` (ver sección "Voces en inglés" abajo) | Warm, conversational, top pick para sleep |
| **Audio** | TTS Rate | `-10%` | Más lento = más calmado |
| **Audio** | TTS Pitch | `-2Hz` | Un poco más grave |
| **Audio** | Ambient bed mode | `auto` | Matchea por keyword (rain, ocean, lofi, etc.) |
| **Audio** | Bed volume | `0.18` | Ambiente presente pero no tapa la voz |
| **Audio** | Duck amount | `12` dB | Voz clarísima, ambient baja cuando hablás |
| **Render** | Output preset | `sleep_720p` | Suficiente para YouTube y podcast |
| **Render** | Encoder | `auto` | NVENC si tenés NVIDIA, si no libx264 |

Lo demás lo dejás como está. Si no querés tocar nada, los defaults
ya funcionan.

**Click "Render video"** y esperás. La barra de progreso te muestra
qué paso está corriendo (script → voz → timing → ambient → mix →
visual → encode).

### 4. Listo, agarrá el MP4

Cuando termina te muestra dónde quedó:

```
D:\proyectos\Proyectos Github\sleeplens\output\sleeplens-1717729384.mp4
```

El nombre es la timestamp del momento. Si querés un nombre más
amigable, en la pestaña **Render** abajo no hay un campo directo,
pero lo más fácil es renombrarlo desde el explorador de Windows.

O desde la línea de comandos lo hacés más prolijo:

```powershell
Rename-Item "D:\proyectos\Proyectos Github\sleeplens\output\sleeplens-1717729384.mp4" "historia-roma-30m.mp4"
```

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
| Voz diferente | Audio tab | Cambiá el campo **Voice** (ver lista abajo) |
| Otro ambient (lluvia → océano) | Audio tab | Cambiá el campo **Ambient bed mode** a `keyword` o `random` |
| Sin ambient (solo voz) | Audio tab | **Ambient bed mode** = `disabled` |
| Más pausas | Topic tab | Subí **Pause between paragraphs** a `2.5` o `3` |
| Video más largo | Topic tab | Escribí un guion con más palabras |
| Fondo con imagen/video | Visuals tab | Pegá la ruta o arrastrá el archivo |
| Resolución 1080p | Render tab | **Output preset** = `sleep_1080p` |
| Solo audio MP3 | Render tab | **Output preset** = `audio_only` |

---

## Voces en inglés (curadas para sleep)

Edge TTS tiene cientos de voces. Acá está la lista curada de las
17 que mejor suenan para contenido de sleep-learning en inglés.
Todas son gratis, sin key, sin quota.

### Cómo elegir

Ya tenés 17 muestras de audio (10-17 segundos cada una) en
`output/voice-previews/`. Abrí esa carpeta en el explorador y
reproducí los MP3 hasta dar con la que más te guste. Después
poné el id exacto (ej. `en-US-AriaNeural`) en el campo **Voice**
de la pestaña Audio.

Si querés regenerarlas o probar una voz nueva:

```powershell
# Regenerar todas
uv run python scripts/voice_preview.py

# Probar una sola voz
uv run python scripts/voice_preview.py --voice en-US-AriaNeural

# Probar con tu propio texto
uv run python scripts/voice_preview.py --text "This is a test of how this voice sounds for sleep content."
```

### Las 17 voces (verificadas funcionando)

**Mujeres, US English (5):**
| Voice | Vibe | Cuándo usarla |
| ----- | ---- | ------------- |
| `en-US-AriaNeural` | Cálida, conversacional | **Top pick**. La más natural para narración sleep |
| `en-US-EmmaNeural` | Suave, ligeramente susurrada | Voiceover tipo meditación guiada |
| `en-US-JennyNeural` | Amigable, clara, algo enérgica | Cuando el tema requiere más vitalidad |
| `en-US-MichelleNeural` | Joven, brillante | Audiolibros juveniles, contenido moderno |
| `en-US-RogerNeural` | (hombre) Mayor, digno | Narración histórica, biografías |

**Hombres, US English (5):**
| Voice | Vibe | Cuándo usarla |
| ----- | ---- | ------------- |
| `en-US-GuyNeural` | Casual, cálido | Narración relajada, podcasts |
| `en-US-AndrewNeural` | Maduro, audiobook-style | Cursos largos, explicaciones densas |
| `en-US-BrianNeural` | Profunda, resonante | **Top pick masculino**. Voz de late-night radio |
| `en-US-RogerNeural` | (ya arriba) | |
| `en-US-AndrewNeural` | (ya arriba) | |

**Mujeres y hombres, UK English (4):**
| Voice | Vibe | Cuándo usarla |
| ----- | ---- | ------------- |
| `en-GB-SoniaNeural` | Británica madura, pulida | Contenido refinado, literatura inglesa |
| `en-GB-RyanNeural` | Británico cálido, audiobook | Temas históricos, biografías |
| `en-GB-LibbyNeural` | Británica joven | Temas modernos, lifestyle |
| `en-GB-ThomasNeural` | Británico maduro, profundo | Historia militar, exploración |

**Otros acentos (3):**
| Voice | Vibe | Cuándo usarla |
| ----- | ---- | ------------- |
| `en-AU-NatashaNeural` | Australiana calmada | Temas del hemisferio sur, naturaleza |
| `en-AU-WilliamNeural` | Australiano maduro | Outback, expediciones |
| `en-CA-ClaraNeural` | Canadiense calmada | Neutral, contenido general |
| `en-IN-NeerjaNeural` | India suave | Yoga, meditación, hinduismo/budismo |
| `en-IE-EmilyNeural` | Irlandesa suave | Folklore, leyendas, poesía |

### Ajustes finos por voz

Todas estas muestras están grabadas con **rate `-10%`** y **pitch `-2Hz`**.
Si querés afinar más:

| Voice | Rate sugerido | Pitch sugerido | Por qué |
| ----- | ------------- | -------------- | ------- |
| `en-US-AriaNeural` | `-10%` | `-2Hz` | Default, ya cálido |
| `en-US-BrianNeural` | `-8%` | `-3Hz` | Ya es grave, no exagerar |
| `en-US-EmmaNeural` | `-15%` | `0Hz` | Ya es susurrada, no pitch down |
| `en-US-AndrewNeural` | `-12%` | `-2Hz` | Audiobook pace |
| `en-GB-RyanNeural` | `-10%` | `-2Hz` | Default |
| `en-GB-SoniaNeural` | `-8%` | `-1Hz` | Ya es muy pulida, no bajar mucho |

---

## Troubleshooting express

**Tarda mucho en renderizar**
- Normal para videos largos. ~5-10 min por hora de video con NVENC.
- Si tenés NVIDIA, la pestaña Render debería mostrar NVENC
  automáticamente. Fijate en el log.
- Si usás CPU (libx264), puede ser 2-3x más lento. Está bien.

**La voz suena rara o muy rápida**
- Bajá **TTS Rate** a `-15%` o `-20%`.
- Cambiá **Voice** a otra. Probá `es-ES-LauraNeural` o `es-AR-ElenaNeural`.

**El ambient no aparece**
- Abrí `assets\ambient\` y verificá que estén los 14 archivos
  `.ogg`. Si está vacío, corré una vez:
  `uv run python scripts\generate_ambient.py`

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
