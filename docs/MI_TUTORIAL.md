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
| **Topic** | Language | `es` | Para que las voces Edge en español matcheen |
| **Audio** | TTS Voice | `es-ES-ElviraNeural` o `es-MX-DaliaNeural` | Voces suaves en español, gratis |
| **Audio** | TTS Rate | `-10%` | Más lento = más calmado |
| **Audio** | TTS Pitch | `-2Hz` | Un poco más grave |
| **Audio** | Ambient bed mode | `auto` | Matchea por keyword (lluvia, océano, etc.) |
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
| Voz diferente | Audio tab | Cambiá el campo **Voice** |
| Otro ambient (lluvia → océano) | Audio tab | Cambiá el campo **Ambient bed mode** a `keyword` o `random` |
| Sin ambient (solo voz) | Audio tab | **Ambient bed mode** = `disabled` |
| Más pausas | Topic tab | Subí **Pause between paragraphs** a `2.5` o `3` |
| Video más largo | Topic tab | Escribí un guion con más palabras |
| Fondo con imagen/video | Visuals tab | Pegá la ruta o arrastrá el archivo |
| Resolución 1080p | Render tab | **Output preset** = `sleep_1080p` |
| Solo audio MP3 | Render tab | **Output preset** = `audio_only` |

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
  logs\                 <- log rotado para debug
  docs\USER_GUIDE.md    <- tutorial genérico para nuevos usuarios
  docs\MI_TUTORIAL.md   <- este archivo
```

Listo, con esto podés producir videos en piloto automático.
El setup está hecho, solo falta el contenido.
