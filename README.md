# Radio Automator

**Sistema de automatizacion radiofonica de codigo abierto**

Radio Automator e un aplicativo de escritorio para GNU/Linux que permite xestionar a programacion e reproducion dunha emisora de radio de forma automatica. Disenado para emisoras comunitarias, universitarias e libres que necesitan un sistema robusto sen depender de servizos na nube nin software privativo.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![GTK](https://img.shields.io/badge/GTK-4.6-green)
![GStreamer](https://img.shields.io/badge/GStreamer-1.0-red)
![License](https://img.shields.io/badge/License-GPL--3.0-orange)
![Status](https://img.shields.io/badge/Estado-Alpha--0.2.0-yellow)

---

## Estado do proxecto

Esta e a version **0.2.0-alpha**. O aplicativo e funcional e pode usarse para xestionar a programacion e reproducion dunha emisora, pero aun esta en fase de desenvolvemento activo. Probado en **Debian 12 (Bookworm)** con GTK 4.6.

### Funcionalidades operativas

- Reproduccion de audio local (MP3, OGG, FLAC, WAV, M4A, OPUS, AAC, WMA...)
- Streaming HTTP/HTTPS
- Xestion de playlists con soporte para pistas, carpetas e playlists aniadas
- Sistema de Continuidad automatico (reproduccion de fondo cando non hai eventos)
- Parrilla semanal visual con deteccion de conflictos horarios
- Visualizacion de bloques de Continuidad nos ocos da parrilla
- Automatizacion: reproduccion automatica segundo a parrilla programada
- Crossfade configurable entre pistas
- VU meters por canales
- Xestion de podcasts RSS con descarga automatica
- Logotipo da emisora personalizable no sidebar
- Tema oscuro
- Logging con rotacion de arquivos
- Notificacions toast

### Limitacions coñecidas

- A compatibilidade verificada e **GTK 4.6** (Debian 12). Non se probou en GTK 4.10+
- Algunes APIs de GTK 4.10+ non estan dispoñibles e foron adaptadas (FileChooserNative con `parent`, ausencia de `remove_all()`, etc.)
- O sistema de usuarios (roles admin/operator/readonly) esta definido na base de datos pero sen autenticacion implementada ainda
- O drag & drop de playlists non esta completamente funcional
- A saida a streaming (Icecast/Shoutcast) non esta implementada

---

## Requisitos do sistema

### Sistema operativo

- **Debian 12 (Bookworm)** (probado e recomendado)
- Ubuntu 22.04+ ou distribucions baseadas en Debian con GTK 4

### Dependencias de sistema

```bash
# Debian/Ubuntu
sudo apt install python3 python3-pip python3-gi \
    gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-libav
```

### Dependencias de Python

```
PyGObject >= 3.44
SQLAlchemy >= 2.0
feedparser >= 6.0
requests >= 2.31
```

### Hardware recomendado

- Procesador: calquera CPU moderna
- RAM: 512 MB minimos, 1 GB recomendados
- Almacenamento: depende da biblioteca de audio
- Saida de audio: PulseAudio ou PipeWire

---

## Instalacion

### Desde o repositorio

```bash
# 1. Clonar o repositorio
git clone https://github.com/TU-USUARIO/radio-automator.git
cd radio-automator

# 2. Crear entorno virtual (opcional pero recomendado)
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Executar
python -m radio_automator.main
```

### Como paquete

```bash
pip install .
radio-automator
```

---

## Uso rapido

1. **Configurar**: Abre o panel **Configuracion** e establece o nome da emisora, a carpeta de musica e o logotipo
2. **Engadir musica**: No panel **Playlists**, crea unha playlist e engade carpetas ou ficheiros de audio
3. **Continuidad**: No panel **Continuidad**, engade pistas de fondo que soaran cando non haxa eventos programados
4. **Programar**: Na **Parrilla Semanal** ou no panel **Eventos**, crea eventos coas horas e playlists correspondentes
5. **Podcasts**: No panel **Podcasts**, anade feeds RSS para descarga automatica de episodios
6. **Automatizar**: O motor de automatizacion xestionara a reproduccion automaticamente segundo a parrilla

### Atajos de teclado

| Atajo | Accion |
|-------|--------|
| `Ctrl+Q` | Saír do aplicativo |
| `Ctrl+1` a `Ctrl+6` | Navegar entre paneis |
| `Espacio` | Play / Pausa |
| `Ctrl+->` | Pista seguinte |
| `Ctrl+<-` | Pista anterior |
| `Ctrl+S` | Deter reproducion |
| `F1` | Amosar atajos de teclado |

---

## Arquitectura

O aplicativo segue unha arquitectura en tres capas con separacion clara:

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

A comunicacion entre modulos realízase mediante un bus de eventos central (`EventBus`) con patron publish/subscribe e prioridades.

### Estructura de directorios

```
radio-automator/
├── pyproject.toml
├── requirements.txt
├── LICENSE
├── .gitignore
├── radio_automator/
│   ├── __init__.py
│   ├── main.py                 # Punto de entrada (Gtk.Application)
│   ├── core/
│   │   ├── config.py           # ConfigManager (clave-valor en SQLite)
│   │   ├── database.py         # Modelos ORM (SQLAlchemy 2.0)
│   │   ├── event_bus.py        # Sistema pub/sub con prioridades
│   │   └── logger.py           # Logging con rotacion de arquivos
│   ├── services/
│   │   ├── audio_engine.py     # Reproductor GStreamer
│   │   ├── automation_engine.py # Orquestador parrilla + continuidad
│   │   ├── folder_scanner.py   # Escaneo de carpetas con anti-repeticion
│   │   ├── notification_service.py
│   │   ├── parrilla_service.py # Logica de parrilla semanal
│   │   ├── play_queue.py       # Cola de reproducion
│   │   ├── playlist_service.py # CRUD de playlists
│   │   ├── podcast_scheduler.py
│   │   └── podcast_service.py  # Feeds RSS e descarga
│   └── ui/
│       ├── layout.py           # Sidebar + Stack + HeaderBar
│       ├── parrilla_panel.py   # Grid semanal con DrawingArea + Cairo
│       ├── transport_bar.py    # Controles + VU meters
│       ├── config_panel.py     # Configuracion
│       ├── playlists_panel.py  # Xestion de playlists
│       ├── playlist_editor.py  # Editor de playlist
│       ├── continuidad_panel.py
│       ├── events_panel.py     # Eventos programados
│       ├── podcasts_panel.py   # Feeds RSS
│       ├── theme.py            # Tema escuro CSS
│       ├── toast_overlay.py    # Notificacions toast
│       ├── log_viewer.py       # Visor de logs
│       ├── about_dialog.py
│       ├── shortcuts_dialog.py
│       └── status_bar.py       # Barra de estado con reloxo
└── tests/
    ├── test_fase1.py           # Base de datos (31 tests)
    ├── test_fase2.py           # UI e playlists (37 tests)
    ├── test_fase3.py           # Podcasts (35 tests)
    ├── test_fase4.py           # Motor de audio (54 tests)
    ├── test_fase5.py           # Parrilla (25 tests)
    ├── test_fase6.py           # Automatizacion (23 tests)
    └── test_fase7.py           # Integracion
```

---

## Modelo de datos

A base de datos SQLite (WAL mode, foreign keys) crease automaticamente na primeira execucion en `~/.config/radio-automator/radio_automator.db`. Pode cambiarse coa variable de entorno `RADIO_AUTOMATOR_DIR`.

| Tabla | Descricion |
|-------|------------|
| `playlists` | Playlists con nome, modo (loop/single), flag `is_system` para Continuidad |
| `playlist_items` | Elementos de playlist (track, folder, playlist, time_announce) |
| `events` | Eventos programados (hora inicio/fin, dias, repetir, streaming URL) |
| `folder_tracks` | Estado de reproducion de arquivos en carpetas (anti-repeticion) |
| `continuity_state` | Estado de Continuidad (indice, posicion en ms) |
| `podcast_feeds` | Fontes RSS (modo replace/accumulate) |
| `podcast_episodes` | Episodios descargados |
| `play_history` | Registro de pistas reproducidas |
| `system_config` | Configuracion clave-valor |
| `users` | Operadores (modelo definido, sen autenticacion implementada) |

---

## Probas

```bash
# Executar todas as probas
pytest tests/ -v

# Con cobertura
pytest tests/ --cov=radio_automator --cov-report=term-missing

# Unha fase concreta
pytest tests/test_fase5.py -v
```

---

## Compatibilidade GTK 4.6

O aplicativo esta adaptado para funcionar en GTK 4.6 (a version incluida en Debian 12). Algunhas APIs de GTK 4.10+ non estan dispoñibles e foron substituidas:

| GTK 4.10+ (non dispoñible) | Alternativa usada en GTK 4.6 |
|---|---|
| `Gtk.Picture.set_content_size()` | `set_size_request()` |
| `Gtk.Widget.remove_all()` | Bucle manual con `get_first_child()` |
| `FileChooserNative(transient_for=...)` | `FileChooserNative(parent=...)` |
| `Gtk.CssProvider.var()` | Valores CSS directos |

---

## Licencia

Este proxecto esta licenciado baixo a **GNU General Public License v3.0** (GPL-3.0). Consulta o arquivo [LICENSE](LICENSE) para mais detalles.

---

## Agradecementos

- **GTK** pola toolkit de interface grafica
- **GStreamer** polo framework multimedia
- **SQLAlchemy** polo ORM
- **feedparser** polo parseo de feeds RSS/Atom
- **Python Software Foundation** pola linguaxe de programacion

---

*Desarrollado con Python 3.11+, GTK 4.6, GStreamer 1.0 e SQLAlchemy 2.0*
