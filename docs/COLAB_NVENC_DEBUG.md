# Colab Pro + NVENC: estado actual del problema

Fecha: 2026-06-07.

## Qué queremos lograr

Renderizar un video de 6 minutos 54 segundos (414.8 segundos, 9954
frames a 24 fps), 1920×1080, H.264, con audio AAC, en una instancia
**Colab Pro con GPU T4**, usando el codificador de hardware **NVENC**
del T4 para que el encode termine en 1-2 minutos en vez de los
~10-15 minutos que tardaría por CPU.

## Estado actual

El pipeline `sleep_learning_engine render` corre hasta la fase de
encode y luego se queda colgado o falla. El log termina con esto:

```
20:47:51 | WARNING  | builder:_verify_encoder_works - Canary encode
                  for h264_nvenc failed:
  [h264_nvenc @ 0x5c03e1b7d740] InitializeEncoder failed:
  invalid param (8): Frame Dimension less than the minimum
  supported value.
  Error initializing output stream 0:0 -- Error while opening
  encoder for output stream #0:0 - maybe incorrect parameters
  such as bit_rate, rate, width or height

20:47:51 | WARNING  | builder:_verify_encoder_works - Canary encode
                  for h264_qsv failed:
  [h264_qsv @ 0x557ed32c4740] Error initializing an internal MFX
  session: unsupported (-3)
  Error initializing output stream 0:0 -- Error while opening
  encoder for output stream #0:0 - maybe incorrect parameters
  such as bit_rate, rate, width or height
```

Lo que significa en la práctica:
- El canary de NVENC falla, así que el pipeline NO elige `h264_nvenc`
- El canary de QSV falla (esperado, T4 no es Intel)
- Después del log que mostrás, el pipeline sigue intentando AMF
  y `libx264`. Si AMF también falla, cae a `libx264` CPU y el video
  sale eventualmente pero tarda ~10-15 min en vez de 1-2 min.
- Si AMF cuelga (lo que parece estar pasando según el log de las
  pruebas anteriores), el render queda colgado indefinidamente.

## Lo que ya probamos y por qué no funcionó

### 1. Canario original (`64x64`, `duration=0.04`, `-frames:v 1`)
El probe de NVENC usaba un frame de prueba minúsculo. El driver de
NVENC en el T4 del Colab del usuario rechaza ese probe con
`Frame Dimension less than the minimum supported value`. El 64x64
está por encima del mínimo documentado de NVENC, pero la
combinación de duración 0.04s + 1 frame forzado confunde la lógica
interna de timestamps del driver y reporta la dimensión como
inválida.

### 2. Parche de `LD_LIBRARY_PATH` (commit `83d4874`)
Antes del probe, parcheamos `os.environ["LD_LIBRARY_PATH"]` para
incluir `/usr/lib64-nvidia` (la ruta de las libs NVIDIA en
Colab). Sin esto, ffmpeg no encuentra `libcuda.so` y NVENC falla
en silencio. El parche funciona, pero el problema del canary es
ortogonal: el parche ya estaba aplicado en el log que el usuario
compartió y NVENC igual falló.

### 3. Canario arreglado (`128x128`, `duration=1`, `rate=24`,
`-pix_fmt yuv420p`, `-bf 0`) (commit `d8d5cb2`)
Cambiamos el probe a 128x128, 1 segundo a 24 fps, pix_fmt
explícito y sin B-frames. El error de NVENC cambió de "Cannot load
nvcuda.dll" a "Frame Dimension less than the minimum", o sea
mejoró pero sigue sin pasar. **El canary sigue rechazando NVENC
en este T4 específico**, aunque el hardware está disponible.

### 4. Fallback a `libx264` (vía `build()`)
Cuando el canary falla, el código intenta AMF, después `libx264`.
El render eventualmente termina, pero:
- En T4 (GPU) + 1 thread, libx264 tarda ~10-15 min para 6:55 de
  video 1080p
- Si el runtime está limitado a CPU (Colab free sin T4), tarda
  más
- El proceso parece colgado porque el log no flushea progreso

### 5. Stream del output con `subprocess.Popen` (commit `83d4874`)
Cambiamos de `subprocess.run(..., capture_output=True)` a
`subprocess.Popen` con line-buffered stdout merged con stderr.
Esto arregla la percepción de "se queda colgado" (el output
ahora se ve en tiempo real), pero NO arregla el canary.

### 6. Verificación GPU con `nvidia-smi` (commit `83d4874`)
La celda 1 ahora corre `nvidia-smi` en vez de solo chequear
`ffmpeg -encoders`. El T4 del Colab del usuario SÍ aparece
(`Tesla T4, 15360 MiB, ...`). La GPU existe y está bindeada. NVENC
debería estar disponible.

### 7. Render local con `libx264` forzado
Probé localmente con `output_preset=sleep_720p`,
`hardware_accel=libx264`, `render_threads=1`. El pipeline anda
end-to-end: 1 párrafo de 40s → MP4 de 8.6 MB en 68.6 segundos. El
canario se salta completamente porque forzamos `libx264`. Esto
confirma que el pipeline funciona; el problema es solo el canario
del NVENC en Colab.

## Configuración actual del usuario

`.sleeplens.toml`:
```toml
output_preset = "sleep_720p"
render_threads = 1
hardware_accel = "libx264"
script_file = "D:/Downloads/prueba.txt"
background_image = "D:/Youtube/sleepingdevfer34/learn_rag_sleeping/learn_rag_while_sleeping.jpeg"
```

`D:/Downloads/prueba.txt` (el script original) ya no existe en el
disco del usuario. Tuve que crear un script de prueba (`Sleep is
a fundamental biological process...`) para validar el pipeline
localmente.

`assets/ambient/` contiene 97 mp3 normalizados a -23 LUFS (estándar
broadcast).

## Resumen del problema

El canario de NVENC en `src/sleep_learning_engine/video/builder.py:_verify_encoder_works`
reporta `Frame Dimension less than the minimum supported value`
incluso con el probe de 128x128 / 1s / yuv420p / sin B-frames. El
mismo hardware (T4 en Colab Pro) sí aparece en `nvidia-smi` con
15 GB de VRAM y un driver NVIDIA funcionando. La diferencia
entre "NVENC anda en el hardware" y "el canario lo rechaza" no la
hemos podido identificar todavía.

## Archivos relevantes en el repo

- `src/sleep_learning_engine/video/builder.py` — contiene
  `_verify_encoder_works` (el canario problemático) y `build` (el
  fallback a `libx264`).
- `scripts/generate_colab_notebook.py` — generador del notebook
  público de Colab. La celda 4 llama `subprocess.Popen` con el
  parche de `LD_LIBRARY_PATH` y streaming output.
- `scripts/generate_drive_notebook.py` — generador del notebook
  personal (variante Drive). Misma estructura, paths Drive-mounted.
- `docs/cloud/low_ram_render.ipynb` — notebook público de Colab.
- `docs/cloud/drive_render.ipynb` — notebook personal del
  usuario.
- `.sleeplens.toml` — config del usuario, apunta a
  `libx264 forzado + 720p + 1 thread` para evitar el canario.

## Histórico de commits relevantes

- `79a8212` — Rename del proyecto (incluye fallback
  `.sleeplens.toml` ↔ `.sleep_learning_engine.toml`).
- `83d4874` — Tres fixes cloud: `nvidia-smi` check, `LD_LIBRARY_PATH`
  patch, `subprocess.Popen` con streaming.
- `d8d5cb2` — Canario NVENC arreglado (de 64x64 a 128x128 + 1s +
  yuv420p).
- `450ec04` — `CHANGELOG.md` actualizado.
- `cacc2ae` — `CHANGELOG.md` con los fixes posteriores al rename.

(Este documento NO incluye soluciones; solo describe el estado
actual y todo lo probado. La decisión de cómo proceder queda
abierta.)
