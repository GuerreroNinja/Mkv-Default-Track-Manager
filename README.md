# MKV Default Track Manager

🇬🇧 [Read in English](README.md)

Una pequeña aplicación de escritorio (Python + Qt) para cambiar la **pista de audio y de subtítulos por defecto** de muchos archivos MKV a la vez, **sin recodificar ni remultiplexar**.

Lee las pistas de cada archivo y modifica solo los indicadores *default* en el propio archivo con `mkvpropedit`. Por eso funciona aunque tus archivos no compartan la misma estructura (distinto orden, distintos nombres, pistas que faltan...).

<!-- Añade una captura: ![Captura](docs/screenshot.png) -->

## Características

- Elige una carpeta y lista todos los MKV (opcionalmente incluyendo subcarpetas).
- Una fila por archivo con sus propios desplegables de **audio** y **subtítulos**, así que el orden de las pistas no importa. Cada entrada muestra idioma, códec, canales, nombre de la pista y una marca `[forced]`.
- **Aplicar a todos**: eliges un idioma una vez y se selecciona en todos los archivos que lo tengan, prefiriendo las pistas no forzadas.
- Distingue variantes de idioma (p. ej. *Spanish (Latin America)* frente a *Spanish (Spain)*, *Portuguese (Brazil)* frente a *Portuguese (Portugal)*), usando la etiqueta de idioma IETF si existe o palabras del nombre de la pista (`Latino`, `Castellano`, `Brasil`...).
- Los subtítulos pueden quedar en *Ninguno* (sin subtítulo por defecto).
- Las filas modificadas se resaltan; tras guardar, cada fila muestra ✓ o ✗ (con el detalle al pasar el ratón).
- Solo se tocan los archivos y los tipos de pista que realmente cambian.
- Lectura y escritura en paralelo.

## Requisitos

- Python 3.9+
- [MKVToolNix](https://mkvtoolnix.download/) (`mkvmerge` y `mkvpropedit` en el `PATH`)
- PyQt6

**Fedora**

```bash
sudo dnf install mkvtoolnix python3-pyqt6
```

**Debian / Ubuntu**

```bash
sudo apt install mkvtoolnix python3-pyqt6
```

**Arch**

```bash
sudo pacman -S mkvtoolnix-cli python-pyqt6
```

O con pip: `pip install PyQt6` (e instala MKVToolNix desde tu gestor de paquetes).

## Uso

```bash
python3 mkv_default_manager.py              # abre la última carpeta usada
python3 mkv_default_manager.py /ruta/a/la/temporada
```

1. Elige la carpeta (**Examinar…**).
2. Usa los desplegables de cada fila, o elige un idioma en el panel inferior y pulsa **Aplicar a todos** para audio y/o subtítulos.
3. Revisa las filas marcadas como **● Modificado**.
4. Pulsa **APLICAR CAMBIOS** y confirma.

## Cómo funciona

1. `mkvmerge -J <archivo>` devuelve la lista de pistas en JSON.
2. Para cada archivo modificado, `mkvpropedit` pone `flag-default=1` en la pista elegida y `flag-default=0` en el resto de pistas de ese tipo, de modo que nunca hay más de una por defecto por tipo. Las pistas se direccionan por tipo y posición (`track:a2`, `track:s1`), por lo que los archivos con estructuras distintas se tratan correctamente.

El indicador *forced* y el resto del archivo no se tocan.

## Opcional: lanzador en el menú de aplicaciones

Guárdalo como `~/.local/share/applications/mkv-default-manager.desktop` (ajusta la ruta):

```ini
[Desktop Entry]
Type=Application
Version=1.0
Name=MKV Default Track Manager
GenericName=Gestor de pistas MKV
Comment=Cambia el audio y los subtítulos por defecto de varios MKV sin recodificar
Exec=python3 /ruta/a/mkv_default_manager.py
Icon=video-x-matroska
Terminal=false
Categories=AudioVideo;Video;Utility;
Keywords=mkv;matroska;audio;subtitles;subtítulos;default;pistas;mkvpropedit;
StartupNotify=true
```

Después ejecuta `update-desktop-database ~/.local/share/applications`. Mantén el nombre `mkv-default-manager.desktop`: la aplicación fija ese nombre para que la ventana muestre el icono correcto en Wayland.

## Notas y advertencias

- `mkvpropedit` edita los archivos **en el sitio**. Normalmente solo toca las cabeceras (muy rápido), pero si no hay espacio libre en la cabecera puede tener que reescribir parte del archivo. **Prueba primero con una copia** y mantén copias de seguridad de lo que no puedas perder.
- Cierra cualquier reproductor que tenga los archivos abiertos antes de aplicar cambios.
- Si dos pistas tienen el mismo código de idioma y ningún nombre o etiqueta que las distinga, aparecerán igual en el desplegable; elige según el códec o los canales en esa fila.
- Probado en Linux (Fedora). No se ha probado en otras plataformas.

## Contribuir

Se aceptan issues y pull requests. Ideas: interfaz en inglés / i18n, activar o desactivar el indicador *forced*, filtro por nombre de archivo, arrastrar y soltar carpetas.

## Licencia

Elige una licencia para el repositorio (p. ej. MIT) y añade un archivo `LICENSE`.
