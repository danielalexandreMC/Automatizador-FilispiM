[README.md](https://github.com/user-attachments/files/26761154/README.md)
# Radio Automator

**Sistema de automatización radiofónica de código abierto**

Radio Automator es una aplicación de escritorio para GNU/Linux (Debian/Ubuntu) que permite gestionar la programación y reproducción de una emisora de radio de forma automática. Diseñado con un enfoque en la simplicidad y la fiabilidad, es ideal para emisoras comunitarias, universitarias y libres que necesitan un sistema robusto sin depender de servicios en la nube ni software privativo.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![GTK](https://img.shields.io/badge/GTK-4.0-green)
![GStreamer](https://img.shields.io/badge/GStreamer-1.0-red)
![License](https://img.shields.io/badge/License-GPL--3.0-orange)

---

## Tabla de Contenidos

- [Características principales](#características-principales)
- [Captura de pantalla (descripción)](#captura-de-pantalla)
- [Requisitos del sistema](#requisitos-del-sistema)
- [Instalación](#instalación)
- [Uso rápido](#uso-rápido)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Modelo de datos](#modelo-de-datos)
- [Paneles de la interfaz](#paneles-de-la-interfaz)
- [Servicios](#servicios)
- [Configuración](#configuración)
- [Pruebas](#pruebas)
- [Roadmap](#roadmap)
- [Contribuciones](#contribuciones)
- [Licencia](#licencia)

---

## Características principales

### Gestión de Playlists
- Creación y edición de playlists con nombre y modo de reproducción (loop / single)
- Soporte para cuatro tipos de elementos dentro de una playlist:
  - **Pistas individuales** (archivos de audio locales)
  - **Carpetas enteras** (escaneo recursivo con anti-repetición)
  - **Playlists anidadas** (referencia a otras playlists, con detección de ciclos mediante BFS)
  - **Anuncios de hora** (marcadores temporales)
- Reordenación de elementos mediante arrastrar y soltar (drag & drop)
- Editor de playlist dedicado con vista de pista actual, siguiente y cola completa

### Continuidad
- Playlist del sistema "Continuidad" que se reproduce automáticamente cuando no hay eventos programados
- Estado persistente: guarda el índice de la última pista reproducida y la posición en milisegundos
- Al reanudarse, continúa exactamente desde donde se quedó (incluso entre sesiones)
- Modo loop infinito: al llegar al final, vuelve a empezar automáticamente

### Parrilla Semanal
- Vista de programación semanal de 7 días x 24 horas (Lunes a Domingo, 00:00 a 24:00)
- Eventos con hora de inicio obligatoria y hora de fin opcional
- Selección de días de la semana por evento (checkboxes Lun-Dom)
- Patrones de repetición: semanal, diario, una sola vez, días seleccionados, cada N días, rango de fechas
- Tipos de contenido por evento: playlist, archivo local, carpeta local o streaming (URL)
- Detección automática de conflictos horarios (solapamientos entre eventos)
- Colores diferenciados: azul (evento normal), naranja (streaming), rojo (reproduciendo ahora)

### Eventos Programados
- Eventos normales: contenido local (playlist, archivo o carpeta)
- Eventos de streaming: con URL obligatoria y horas de inicio/fin obligatorias
- Activación/desactivación individual de eventos sin eliminarlos
- Indicadores visuales de estado (pasado, reproduciendo, futuro)

### Podcasts
- Suscripción a feeds RSS/Atom de podcasts
- Descarga automática de episodios nuevos
- Modo **Reemplazar**: mantiene solo los N episodios más recientes, eliminando los antiguos
- Modo **Acumular**: conserva todos los episodios descargados
- Comprobación periódica configurable (por defecto cada 24 horas)
- Límite de 50 feeds RSS simultáneos
- Gestión individual de episodios (visualización, eliminación)

### Motor de Audio (GStreamer)
- Reproductor basado en GStreamer con pipeline playbin
- Formatos soportados: MP3, OGG, FLAC, WAV, M4A, OPUS, AAC, WMA, MP4, WEBM, SPX, MP2
- Streaming HTTP/HTTPS con gestión de buffering
- Crossfade configurable entre pistas (fade-in / fade-out con curva lineal, 0-15 segundos)
- VU Meter por canales (izquierdo/derecho) con detección de clipping
- Control de volumen, silencio (mute) y seek (búsqueda por posición)
- Extracción automática de metadatos (título, artista) desde tags del archivo
- Modo simulación: funciona sin GStreamer instalado para desarrollo y pruebas

### Motor de Automatización
- Orquesta la reproducción automática basándose en la Parrilla y la Continuidad
- Cada N segundos (configurable, 2-60s) comprueba qué debe reproducirse
- Flujo de decisiones:
  1. Si hay un evento de parrilla activo ahora, lo reproduce
  2. Si el evento tiene hora de fin y ya pasó, lo detiene
  3. Si no hay eventos, inicia Continuidad como fallback
  4. Si el usuario reproduce algo manualmente, no interfiere hasta que pare
- Guarda y restaura el estado de Continuidad automáticamente

### Interfaz de Usuario
- Tema oscuro personalizado (fondo #1A1A1A, superficie #2D2D2D, acento #E53935)
- Sidebar de navegación con 6 paneles: Parrilla, Playlists, Continuidad, Eventos, Podcasts, Config
- Barra de transporte con controles de reproducción, barra de progreso, volumen y VU meters
- Barra de estado con reloj en tiempo real, nombre del panel activo y estado de reproducción
- Sistema de notificaciones toast (info, éxito, advertencia, error) como overlay
- Título de ventana dinámico que muestra la pista en reproducción
- Diálogo "Acerca de" y dialogo de atajos de teclado
- Registro de logging con rotación de archivos

### Atajos de Teclado
| Atajo | Acción |
|-------|--------|
| `Ctrl+Q` | Salir de la aplicación |
| `Ctrl+1` a `Ctrl+6` | Navegar entre paneles |
| `Espacio` | Play / Pausa |
| `Ctrl+→` | Siguiente pista |
| `Ctrl+←` | Pista anterior |
| `Ctrl+S` | Detener reproducción |
| `F1` | Mostrar atajos de teclado |

---

## Captura de pantalla

La aplicación presenta una interfaz de ventana única con sidebar izquierdo, área de contenido principal, barra de transporte inferior y barra de estado. El esquema de color es oscuro con acentos en rojo (#E53935), diseñado para uso prolongado en estudios de radio.

---

## Requisitos del sistema

### Sistema operativo
- **Debian 12+ (Bookworm)** o **Ubuntu 22.04+ (Jammy)** u otra distribución basada en Debian
- Se recomienda un entorno de escritorio con GTK 4 (GNOME 42+, Cinnamon, XFCE 4.18+)

### Dependencias de sistema
```bash
# Debian/Ubuntu
sudo apt install python3 python3-pip python3-gi \
    gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav \
    libcairo2-dev libgirepository1.0-dev
```

### Dependencias de Python
```
PyGObject >= 3.44
SQLAlchemy >= 2.0
feedparser >= 6.0
requests >= 2.31
```

### Dependencias opcionales (desarrollo)
```
pytest >= 7.0
pytest-cov >= 4.0
```

### Hardware recomendado
- Procesador: cualquier CPU moderna (el procesamiento de audio es eficiente)
- RAM: 512 MB mínimos, 1 GB recomendados
- Almacenamiento: depende de la biblioteca de audio (los podcasts se descargan localmente)
- Salida de audio: cualquier dispositivo soportado por PulseAudio o PipeWire

---

## Instalación

### Desde el repositorio (recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/danielalexandreMC/Automatizador-FilispiM.git
cd Automatizador-FilispiM

# 2. Crear un entorno virtual (opcional pero recomendado)
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar
python -m radio_automator.main
```

### Instalación como paquete

```bash
# Desde el directorio del proyecto
pip install .

# Luego ejecutar directamente
radio-automator
```

### Sin GStreamer (modo simulación)

La aplicación funciona sin GStreamer instalado, pero sin reproducción de audio real. Útil para desarrollo y pruebas de la interfaz:

```bash
# Solo instalar dependencias de Python (sin dependencias de sistema GTK/GStreamer)
pip install PyGObject SQLAlchemy feedparser requests
```

> **Nota:** En modo simulación, los controles de transporte funcionan pero no hay audio real. Los VU meters no muestran datos reales.

---

## Uso rápido

1. **Agregar música**: Ve al panel "Playlists", crea una playlist y añade carpetas o archivos de audio
2. **Configurar Continuidad**: Ve al panel "Continuidad" y añade pistas de fondo. Esta playlist se reproducirá cuando no haya eventos programados
3. **Programar eventos**: Ve al panel "Eventos", crea un evento con hora de inicio y selecciona una playlist
4. **Ver la parrilla**: En el panel "Parrilla" puedes ver la programación semanal completa con los conflictos detectados
5. **Suscribir podcasts**: En el panel "Podcasts" añade la URL de un feed RSS para descarga automática
6. **Iniciar automatización**: El motor de automatización gestionará la reproducción automáticamente según la parrilla

---

## Arquitectura del sistema

La aplicación sigue una arquitectura por capas con separación clara entre datos, lógica de negocio y presentación:

```
┌─────────────────────────────────────────────┐
│                  UI (GTK4)                   │
│  layout · panels · transport · theme         │
├─────────────────────────────────────────────┤
│               Services                       │
│  audio_engine · automation · parrilla        │
│  play_queue · podcast · folder_scanner       │
│  notification · playlist                    │
├─────────────────────────────────────────────┤
│                 Core                         │
│  database (SQLAlchemy) · config · event_bus  │
│  logger                                     │
├─────────────────────────────────────────────┤
│              SQLite + GStreamer              │
└─────────────────────────────────────────────┘
```

### EventBus (pub/sub)

La comunicación entre módulos se realiza mediante un bus de eventos central (`EventBus`) que implementa el patrón publish/subscribe con prioridades. Los módulos publican eventos y otros se suscriben para reaccionar. Eventos principales:

- `audio.track_started` / `audio.track_finished` / `audio.stopped`
- `parrilla.event_started` / `parrilla.event_stopped`
- `automation.started` / `automation.source_changed`
- `podcast.feed_added` / `podcast.feed_checked`

### Singletons

Los servicios principales usan el patrón singleton con funciones `get_*()` y `reset_*()` (para tests):

```python
from radio_automator.services.audio_engine import get_audio_engine
from radio_automator.services.automation_engine import get_automation_engine
from radio_automator.services.play_queue import get_play_queue
from radio_automator.services.parrilla_service import get_parrilla_service
from radio_automator.services.podcast_service import get_podcast_service
```

---

## Estructura del proyecto

```
radio-automator/
├── pyproject.toml              # Configuración del paquete (setuptools)
├── requirements.txt            # Dependencias de Python
├── LICENSE                     # Licencia GPL-3.0
├── README.md                   # Este archivo
├── radio_automator/
│   ├── __init__.py             # Versión del proyecto
│   ├── main.py                 # Punto de entrada (Gtk.Application)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # ConfigManager (clave-valor en SQLite)
│   │   ├── database.py         # Modelos ORM (SQLAlchemy 2.0) + init_db()
│   │   ├── event_bus.py        # Sistema pub/sub con prioridades
│   │   └── logger.py           # Logging con rotación de archivos
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audio_engine.py     # Reproductor GStreamer (play, pause, crossfade, VU)
│   │   ├── automation_engine.py # Orquestador: parrilla + continuidad + manual
│   │   ├── folder_scanner.py   # Escaneo de carpetas con anti-repetición
│   │   ├── notification_service.py # Notificaciones toast y desktop
│   │   ├── parrilla_service.py # Lógica de parrilla semanal (conflictos, eventos)
│   │   ├── play_queue.py       # Cola de reproducción (resolución de playlists)
│   │   ├── playlist_service.py # CRUD de playlists y sus items
│   │   ├── podcast_scheduler.py# Scheduler periódico de podcasts
│   │   └── podcast_service.py  # Gestión de feeds RSS y descarga de episodios
│   └── ui/
│       ├── __init__.py
│       ├── about_dialog.py     # Diálogo "Acerca de"
│       ├── config_panel.py     # Panel de configuración
│       ├── continuidad_panel.py # Panel de Continuidad
│       ├── events_panel.py     # Panel de eventos programados
│       ├── layout.py           # Sidebar + Stack + HeaderBar
│       ├── log_viewer.py       # Visor de logs
│       ├── parrilla_panel.py   # Grid semanal de parrilla
│       ├── playlist_editor.py  # Editor detallado de playlist
│       ├── playlists_panel.py  # Panel principal de playlists
│       ├── podcasts_panel.py   # Panel de gestión de podcasts
│       ├── shortcuts_dialog.py # Diálogo de atajos de teclado
│       ├── status_bar.py       # Barra de estado con reloj
│       ├── theme.py            # Tema oscuro CSS personalizado
│       ├── toast_overlay.py    # Overlay de notificaciones toast
│       └── transport_bar.py    # Controles de reproducción + VU meters
└── tests/
    ├── __init__.py
    ├── test_fase1.py           # Tests de base de datos (31 tests)
    ├── test_fase2.py           # Tests de UI y playlists (37 tests)
    ├── test_fase3.py           # Tests de podcasts (35 tests)
    ├── test_fase4.py           # Tests del motor de audio (54 tests)
    ├── test_fase5.py           # Tests de parrilla (25 tests)
    ├── test_fase6.py           # Tests de automatización (23 tests)
    └── test_fase7.py           # Tests de integración general
```

---

## Modelo de datos

La base de datos SQLite (con WAL mode y foreign keys activadas) contiene las siguientes tablas:

| Tabla | Descripción |
|-------|-------------|
| `users` | Operadores del sistema (admin, operator, readonly). Máximo 3 |
| `playlists` | Playlists con nombre, modo (loop/single) y flag `is_system` para Continuidad |
| `playlist_items` | Elementos de una playlist (track, folder, playlist, time_announce) con posición |
| `events` | Eventos programados con hora inicio/fin, días de la semana, patrón de repetición, URL de streaming |
| `folder_tracks` | Estado de reproducción de archivos en carpetas (anti-repetición) |
| `continuity_state` | Estado persistente de Continuidad (índice, posición en ms) |
| `podcast_feeds` | Fuentes RSS de podcasts con modo (replace/accumulate) |
| `podcast_episodes` | Episodios descargados con ruta local y tamaño |
| `play_history` | Registro de pistas reproducidas (filepath, título, artista, duración, fuente) |
| `system_config` | Configuración general del sistema (clave-valor) |

### Almacenamiento

- Base de datos: `~/.config/radio-automator/radio_automator.db`
- Variable de entorno: `RADIO_AUTOMATOR_DIR` permite cambiar la ubicación
- Logs: rotación automática en el directorio de datos

---

## Paneles de la interfaz

### Parrilla (Parrilla Semanal)
Grid visual de 7 columnas (días) x 48 filas (intervalos de 30 minutos). Los eventos se muestran como bloques coloreados posicionados según su hora de inicio y duración. Los conflictos se indican visualmente.

### Playlists
Lista de playlists con tarjetas que muestran nombre, número de elementos, modo y tipo. Al seleccionar una, se abre el editor dedicado.

### Continuidad
Gestión de la playlist del sistema. Muestra las pistas, permite añadir/quitar elementos y muestra el estado actual de reproducción (índice y posición).

### Eventos
CRUD de eventos programados con formulario que incluye nombre, playlist o streaming URL, hora inicio/fin, días de la semana y patrón de repetición.

### Podcasts
Lista de feeds RSS con indicadores de estado. Permite añadir feeds, comprobar actualizaciones manualmente y gestionar episodios individuales.

### Configuración
Ajustes del sistema organizados en secciones: Audio (crossfade, normalización, dispositivo de salida), Emisora (nombre, carpeta de música), Interfaz (tema, idioma) y Podcasts (intervalo de comprobación, descargas concurrentes).

---

## Servicios

### AudioEngine
Motor de reproducción basado en GStreamer. Gestiona un pipeline `playbin` con soporte para archivos locales, streaming, volumen, crossfade, VU meters y extracción de metadatos. Funciona en modo simulación si GStreamer no está disponible.

### AutomationEngine
El "cerebro" de la automatización. Coordina Parrilla, AudioEngine y Continuidad. Se ejecuta en un hilo separado (daemon) que realiza comprobaciones periódicas (cada 5s por defecto). Implementa lógica de prioridad: parrilla > continuidad > manual.

### PlayQueue
Cola de reproducción que resuelve playlists anidadas recursivamente (con detección de ciclos BFS), carpetas con anti-repetición y pistas individuales. Soporta modos loop y single, y shuffle.

### ParrillaService
Gestiona la programación semanal: consulta de eventos por día/semana, detección de conflictos horarios, cálculo de posiciones para el grid visual, y determinación del evento actual y próximo.

### PodcastService
Gestión completa de podcasts: parseo de feeds RSS (feedparser), descarga de episodios (requests con streaming), modos replace/accumulate, sanitización de nombres de archivo y gestión de almacenamiento.

### FolderScanner
Escaneo recursivo de carpetas de audio con anti-repetición persistente en SQLite. Registra archivos, marca como reproducidos y selecciona aleatoriamente entre los no reproducidos.

---

## Configuración

La configuración se almacena en la tabla `system_config` (clave-valor) y se gestiona mediante `ConfigManager`. Valores por defecto:

| Clave | Valor por defecto | Descripción |
|-------|-------------------|-------------|
| `crossfade_duration` | `3.0` | Duración del crossfade en segundos |
| `crossfade_curve` | `linear` | Tipo de curva (linear, logarithmic, sigmoid) |
| `silence_detection` | `true` | Detección de silencio activada |
| `normalization` | `false` | Normalización de volumen desactivada |
| `audio_output_device` | `auto` | Dispositivo de salida de audio |
| `station_name` | `Mi Emisora` | Nombre de la emisora |
| `music_folder` | `~/Music` | Carpeta predeterminada de música |
| `theme` | `dark` | Tema visual |
| `language` | `es` | Idioma de la interfaz |
| `podcast_check_interval_hours` | `24` | Intervalo de comprobación de podcasts |
| `podcast_max_concurrent_downloads` | `3` | Descargas simultáneas de podcasts |

---

## Pruebas

El proyecto incluye una suite de pruebas unitarias organizadas por fases de desarrollo:

```bash
# Ejecutar todas las pruebas
pytest tests/ -v

# Ejecutar una fase específica
pytest tests/test_fase1.py -v

# Con cobertura
pytest tests/ --cov=radio_automator --cov-report=term-missing
```

Actualmente hay **205+ tests** pasando que cubren:
- Fase 1: Base de datos y modelos ORM
- Fase 2: Interfaz de usuario y gestión de playlists
- Fase 3: Sistema de podcasts
- Fase 4: Motor de audio
- Fase 5: Parrilla semanal
- Fase 6: Motor de automatización
- Fase 7: Integración general

---

## Roadmap

### Fases completadas
- [x] **Fase 1**: Base de datos y modelos ORM (SQLAlchemy 2.0 + SQLite)
- [x] **Fase 2**: Interfaz de usuario GTK4 + gestión de playlists (incluidas anidadas)
- [x] **Fase 3**: Sistema de podcasts (feeds RSS, descarga, replace/accumulate)
- [x] **Fase 4**: Motor de audio GStreamer (play, pause, crossfade, VU, streaming)
- [x] **Fase 5**: Parrilla semanal (grid, eventos, conflictos, auto-scheduler)
- [x] **Fase 6**: Motor de automatización + pulido de UI (toasts, logging, atajos)

### Trabajo futuro propuesto
- [ ] **Salida de streaming/icecast**: Emitir la señal por internet
- [ ] **Normalización de volumen**: Loudness normalización (EBU R128) con GStreamer loudnorm
- [ ] **Detección de silencio**: Auto-advance cuando se detecte silencio prolongado
- [ ] **Multi-operador**: Login/logout de operadores con distintos roles
- [ ] **Exportar/importar**: Backup y restauración de la base de datos
- [ ] **Plugin system**: Extensibilidad mediante plugins de terceros
- [ ] **Soporte RTL**: Soporte para idiomas de derecha a izquierda
- [ ] **Interfaz web**: Panel de control remoto via navegador

---

## Contribuciones

Las contribuciones son bienvenidas. Para contribuir:

1. Haz un fork del repositorio
2. Crea una rama feature: `git checkout -b feature/nueva-funcionalidad`
3. Realiza tus cambios y escribe pruebas
4. Asegúrate de que todos los tests pasan: `pytest tests/ -v`
5. Haz commit: `git commit -m 'Añadir nueva funcionalidad'`
6. Haz push: `git push origin feature/nueva-funcionalidad`
7. Abre un Pull Request

### Guía de estilo
- Seguir PEP 8 para el código Python
- Usar type hints (anotaciones de tipo) en todo el código nuevo
- Documentar clases y funciones públicas con docstrings
- Mantener los tests actualizados con cualquier cambio funcional

---

## Licencia

Este proyecto está licenciado bajo la **GNU General Public License v3.0** (GPL-3.0).

Puedes usar, modificar y distribuir este software bajo los términos de la licencia GPL-3.0. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

## Agradecimientos

- **GTK** por el toolkit de interfaz gráfica
- **GStreamer** por el framework de multimedia
- **SQLAlchemy** por el ORM de base de datos
- **feedparser** por el parseo de feeds RSS/Atom
- **Python Software Foundation** por el lenguaje de programación

---

*Desarrollado con Python 3.11+, GTK 4, GStreamer 1.0 y SQLAlchemy 2.0*
