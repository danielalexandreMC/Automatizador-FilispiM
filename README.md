# 🎙️ Automatizador FilispiM

Automatizador de radio para emisións en directo con GTK4 e GStreamer. Permite xestionar playlists, podcasts, eventos programados e parrilla de emisións con control de audio profesional.

![Plataforma](https://img.shields.io/badge/Plataforma-Debian%2012-blue)
![Python](https://img.shields.io/badge/Python-3.11%2B-green)
![GTK](https://img.shields.io/badge/GTK-4.6-orange)
![Licenza](https://img.shields.io/badge/Licenza-GPL--3.0-success)

---

## 📋 Requisitos do sistema

### Sistema operativo
- **Debian 12 (Bookworm)** ou superior
- Tamén compatible con Ubuntu 22.04+ e outras distribucións baseadas en Debian

### Dependencias do sistema

Instala as dependencias necesarias antes de executar o proxecto:

```bash
sudo apt update
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-gst-plugins-base-1.0 \
    gir1.2-gstreamer-1.0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    libgstreamer1.0-dev \
    sqlite3 \
    git
```

### Dependencias de Python

| Paquete    | Versión mínima | Descripción                                      |
| ---------- | -------------- | ------------------------------------------------ |
| PyGObject  | >= 3.44        | Bindings de Python para GTK4 e GStreamer         |
| SQLAlchemy | >= 2.0         | ORM para base de datos SQLite                    |
| feedparser | >= 6.0         | Lectura e parseo de feeds RSS de podcasts        |
| requests   | >= 2.31        | Descarga de ficheiros de audio e peticiones HTTP |

---

## 🚀 Instalación

### Clonar o repositorio

```bash
git clone https://github.com/danielalexandreMC/Automatizador-FilispiM.git
cd Automatizador-FilispiM
```

### Crear e activar o entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Instalar dependencias de Python

```bash
pip install -r requirements.txt
```

### Executar a aplicación

```bash
python3 -m radio_automator
```

> **Nota:** Para saír do entorno virtual, executa `deactivate`. Para reentrar, executa `source .venv/bin/activate`.

---

## ⌨️ Atallos de teclado

| Tecla            | Acción                 |
| ---------------- | ---------------------- |
| `Ctrl + Espacio` | Reproducir / Pausa     |
| `Ctrl + S`       | Detener reproducción   |
| `Ctrl + N`       | Nova playlist          |
| `Ctrl + O`       | Abrir ficheiro         |
| `Ctrl + Q`       | Pechar aplicación      |
| `F11`            | Modo pantalla completa |
| `F5`             | Actualizar / Recargar  |

---

## 📁 Estructura do proxecto

```
Automatizador-FilispiM/
├── radio_automator/
│   ├── main.py                    # Punto de entrada principal
│   ├── services/
│   │   ├── audio_engine.py        # Motor de audio (GStreamer playbin)
│   │   ├── play_queue.py          # Cola de reprodución e modo Continuidad
│   │   └── database.py            # Modelo de base de datos (SQLAlchemy)
│   ├── ui/
│   │   ├── transport_bar.py       # Barra de transporte (Play, Stop, VU meter, progreso)
│   │   ├── playlists_panel.py     # Panel de xestión de playlists
│   │   ├── playlist_editor.py     # Editor de contido de playlists
│   │   ├── podcasts_panel.py      # Panel de xestión de podcasts (RSS)
│   │   ├── events_panel.py        # Panel de eventos programados
│   │   ├── parrilla_panel.py      # Panel de parrilla de emisións
│   │   ├── shortcuts_dialog.py    # Diálogo de atallos de teclado
│   │   └── config_panel.py        # Panel de configuración
│   └── models/
│       └── ...                    # Modelos de datos
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 🎵 Características principais

### Reprodución de audio
- Motor de audio baseado en **GStreamer** con pipeline `playbin`
- VU meter en tempo real con indicadores de nivel
- Barra de progreso con navegación
- Carga automática da playlist **Continuidad** cando a cola está baleira
- Soporte para MP3, OGG, FLAC, WAV e máis formatos

### Playlists
- Creación e edición de playlists
- Engadir cartafoles completos de audio
- Xestión de orde das pistas
- Playlist de sistema "Continuidad" como respaldo automático

### Podcasts
- Subscrición a feeds RSS
- Descarga automática de episodios
- Listado e reprodución de podcasts

### Eventos programados
- Creación e edición de eventos
- Programación horaria para emisións

### Parrilla de emisións
- Visión xeral da programación
- Organización por bloques horarios

---

## 🔧 Resolución de problemas

### O audio non reproduce
- Verifica que GStreamer está instalado correctamente:
  ```bash
  gst-launch-1.0 -v audiotestsrc ! autoaudiosink
  ```
- Comproba que os plugins de GStreamer están dispoñibles:
  ```bash
  gst-inspect-1.0 | grep -i mp3
  ```

### Problemas coa interfaz gráfica
- A aplicación require **GTK 4.6** como mínimo (Debian 12 inclúe GTK 4.6)
- Se tes problemas de renderizado, verifica a versión de GTK:
  ```bash
  pkg-config --modversion gtk4
  ```

### A barra espaciadora pausa ao escribir texto
- O atallo de Play/Pausa é **Ctrl + Espacio** para non interferir cos campos de texto

---

## 📝 Notas de desenvolvemento

- A aplicación está optimizada para **Debian 12 (Bookworm)** con GTK 4.6
- Non se usan APIs de GTK 4.10+ para manter a compatibilidade
- Os diálogos usan `Gtk.Window` con botóns manuais en lugar de `Gtk.MessageDialog` por compatibilidade
- `FileChooserDialog` úsase en lugar de `FileChooserNative` para maior fiabilidade en GTK 4.6

---

## 📄 Licenza

Este proxecto distribúese baixo a licenza **GPL-3.0**. Consulta o ficheiro `LICENSE` para máis detalles.
