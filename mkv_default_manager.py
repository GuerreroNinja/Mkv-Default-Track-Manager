#!/usr/bin/env python3
"""
MKV Default Track Manager
-------------------------
Cambia la pista de audio y de subtítulos por defecto de muchos MKV a la vez,
sin recodificar, usando mkvpropedit (mkvtoolnix).

Dependencias (Fedora):
    sudo dnf install mkvtoolnix python3-pyqt6

Uso:
    python3 mkv_default_manager.py [directorio]
"""
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

LANGS = {
    "ja": "Japanese", "jpn": "Japanese", "en": "English", "eng": "English",
    "es": "Spanish", "spa": "Spanish", "fr": "French", "fre": "French",
    "fra": "French", "de": "German", "ger": "German", "deu": "German",
    "it": "Italian", "ita": "Italian", "pt": "Portuguese", "por": "Portuguese",
    "ru": "Russian", "rus": "Russian", "zh": "Chinese", "chi": "Chinese",
    "zho": "Chinese", "ko": "Korean", "kor": "Korean", "ca": "Catalan",
    "cat": "Catalan", "ar": "Arabic", "ara": "Arabic", "nl": "Dutch",
    "dut": "Dutch", "nld": "Dutch", "pl": "Polish", "pol": "Polish",
    "tr": "Turkish", "tur": "Turkish", "sv": "Swedish", "swe": "Swedish",
    "th": "Thai", "tha": "Thai", "vi": "Vietnamese", "vie": "Vietnamese",
    "id": "Indonesian", "ind": "Indonesian", "und": "Undefined",
}


def lang_name(code: str) -> str:
    base = (code or "und").split("-")[0].lower()
    return LANGS.get(base, code or "und")


# Variantes por subetiqueta IETF (es-419, es-ES, pt-BR...)
VARIANT_TAGS = {
    "Spanish": {"419": "Latin America", "MX": "Latin America", "AR": "Latin America",
                "CL": "Latin America", "CO": "Latin America", "PE": "Latin America",
                "VE": "Latin America", "UY": "Latin America", "US": "Latin America",
                "ES": "Spain"},
    "Portuguese": {"BR": "Brazil", "PT": "Portugal"},
    "Chinese": {"HANS": "Simplified", "CN": "Simplified",
                "HANT": "Traditional", "TW": "Traditional", "HK": "Traditional"},
}
# Variantes por palabras en el nombre de la pista (cuando el idioma es solo "spa")
VARIANT_NAMES = {
    "Spanish": [
        ("Latin America", ("latino", "latam", "latin", "hispanoam", "mexic", "sudamerica")),
        ("Spain", ("castellano", "españa", "espana", "spain", "europe", "iberic", "peninsul")),
    ],
    "Portuguese": [
        ("Brazil", ("brasil", "brazil")),
        ("Portugal", ("portugal", "europe")),
    ],
}


def lang_label(code: str, track_name: str = ""):
    """Devuelve (etiqueta con variante, idioma base). Ej: ('Spanish (Latin America)', 'Spanish')."""
    base = lang_name(code)
    parts = (code or "und").replace("_", "-").split("-")[1:]
    for p in parts:
        variant = VARIANT_TAGS.get(base, {}).get(p.upper())
        if variant:
            return f"{base} ({variant})", base
    lowered = (track_name or "").lower()
    for variant, words in VARIANT_NAMES.get(base, []):
        if any(w in lowered for w in words):
            return f"{base} ({variant})", base
    return base, base


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def track_label(t: dict) -> str:
    parts = [t["lang"]]
    extra = " ".join(x for x in (t["codec"], f'{t["ch"]}ch' if t["ch"] else "") if x)
    if extra:
        parts.append(extra)
    if t["name"]:
        parts.append(f'«{t["name"]}»')
    label = " · ".join(parts)
    if t["forced"]:
        label += "  [forced]"
    return label


def scan_file(path: Path):
    r = subprocess.run(["mkvmerge", "-J", str(path)], capture_output=True, text=True)
    if r.returncode >= 2:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300] or "mkvmerge falló")
    data = json.loads(r.stdout)
    audio, subs = [], []
    for t in data.get("tracks", []):
        ty = t.get("type")
        if ty not in ("audio", "subtitles"):
            continue
        p = t.get("properties", {})
        label, base = lang_label(p.get("language_ietf") or p.get("language") or "und",
                                 p.get("track_name", ""))
        tr = {
            "lang": label,
            "base": base,
            "name": p.get("track_name", ""),
            "codec": t.get("codec", ""),
            "ch": p.get("audio_channels"),
            "default": bool(p.get("default_track", False)),
            "forced": bool(p.get("forced_track", False)),
        }
        (audio if ty == "audio" else subs).append(tr)
    return audio, subs


def pick_track(tracks: list, lang: str):
    """Índice de la primera pista del idioma (prefiere las no forzadas)."""
    cands = [i for i, t in enumerate(tracks) if t["lang"] == lang]
    if not cands:  # p. ej. "Spanish" genérico: vale cualquier variante
        cands = [i for i, t in enumerate(tracks) if t["base"] == lang]
    if not cands:
        return None
    for i in cands:
        if not tracks[i]["forced"]:
            return i
    return cands[0]


class NoWheelCombo(QComboBox):
    """Evita cambiar valores sin querer al hacer scroll sobre la tabla."""
    def wheelEvent(self, e):
        e.ignore()


class ScanWorker(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(list)

    def __init__(self, files):
        super().__init__()
        self.files = files

    def run(self):
        total = len(self.files)

        def job(i):
            try:
                return scan_file(self.files[i]), None
            except Exception as e:  # noqa: BLE001
                return None, str(e)

        results = []
        with ThreadPoolExecutor(8) as ex:
            for n, res in enumerate(ex.map(job, range(total)), 1):
                results.append(res)
                self.progress.emit(n, total)
        self.done.emit(results)


class ApplyWorker(QThread):
    item = pyqtSignal(int, int, str)
    progress = pyqtSignal(int, int)

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs  # [(row, args)]

    def run(self):
        def job(j):
            row, args = j
            r = subprocess.run(args, capture_output=True, text=True)
            return row, r.returncode, (r.stdout + r.stderr).strip()

        total = len(self.jobs)
        with ThreadPoolExecutor(4) as ex:
            for n, (row, rc, out) in enumerate(ex.map(job, self.jobs), 1):
                self.item.emit(row, rc, out)
                self.progress.emit(n, total)


class MainWindow(QMainWindow):
    def __init__(self, start_dir=None):
        super().__init__()
        self.setWindowTitle("MKV Default Track Manager")
        self.resize(1100, 700)
        self.settings = QSettings("mkv-default-manager", "mkv-default-manager")
        self.rows = []  # dicts: path, audio, subs, ca, cs, oa, os, status
        self.worker = None

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        # --- Directorio
        top = QHBoxLayout()
        top.addWidget(QLabel("Directorio:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.returnPressed.connect(lambda: self.load_dir(self.dir_edit.text()))
        top.addWidget(self.dir_edit, 1)
        btn = QPushButton(QIcon.fromTheme("folder-open"), " Examinar…")
        btn.setToolTip("Elegir directorio")
        btn.clicked.connect(self.browse)
        top.addWidget(btn)
        self.recursive = QCheckBox("Incluir subcarpetas")
        self.recursive.toggled.connect(lambda: self.load_dir(self.dir_edit.text()))
        top.addWidget(self.recursive)
        lay.addLayout(top)

        self.count_label = QLabel("Selecciona un directorio")
        lay.addWidget(self.count_label)

        # --- Tabla
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Archivo", "AUDIO", "SUBTÍTULOS", "Estado"])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lay.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        # --- Aplicar a todos
        self.g_audio = QComboBox()
        self.g_subs = QComboBox()
        for text, combo, fn in (
            ("Audio:", self.g_audio, self.apply_all_audio),
            ("Subtítulos:", self.g_subs, self.apply_all_subs),
        ):
            r = QHBoxLayout()
            lbl = QLabel(text)
            lbl.setMinimumWidth(80)
            r.addWidget(lbl)
            combo.setMinimumWidth(220)
            r.addWidget(combo)
            b = QPushButton("Aplicar a todos")
            b.clicked.connect(fn)
            r.addWidget(b)
            r.addStretch(1)
            lay.addLayout(r)

        # --- Botones finales
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("CANCELAR")
        cancel.clicked.connect(self.close)
        self.apply_btn = QPushButton("APLICAR CAMBIOS")
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self.apply_changes)
        bottom.addWidget(cancel)
        bottom.addWidget(self.apply_btn)
        lay.addLayout(bottom)

        d = start_dir or self.settings.value("last_dir", "")
        if d:
            self.load_dir(d)

    # ------------------------------------------------------------ carga
    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Elegir directorio", self.dir_edit.text())
        if d:
            self.load_dir(d)

    def load_dir(self, d):
        p = Path(d).expanduser()
        if not p.is_dir():
            return
        self.dir_edit.setText(str(p))
        self.settings.setValue("last_dir", str(p))
        it = p.rglob("*") if self.recursive.isChecked() else p.iterdir()
        files = sorted((f for f in it if f.is_file() and f.suffix.lower() == ".mkv"), key=natural_key)
        self.table.setRowCount(0)
        self.rows = []
        self.files = files
        self.count_label.setText(f"{len(files)} MKV encontrados — leyendo pistas…")
        if not files:
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, len(files))
        self.worker = ScanWorker(files)
        self.worker.progress.connect(lambda n, t: self.progress.setValue(n))
        self.worker.done.connect(self.scan_done)
        self.worker.start()

    def scan_done(self, results):
        self.progress.setVisible(False)
        base = Path(self.dir_edit.text())
        errors = 0
        self.table.setRowCount(len(results))
        for i, (res, err) in enumerate(results):
            path = self.files[i]
            try:
                name = str(path.relative_to(base))
            except ValueError:
                name = path.name
            item = QTableWidgetItem(name)
            item.setToolTip(str(path))
            self.table.setItem(i, 0, item)
            status = QTableWidgetItem("")
            self.table.setItem(i, 3, status)
            if err:
                errors += 1
                status.setText("✗ error")
                status.setToolTip(err)
                self.rows.append(None)
                continue
            audio, subs = res
            ca, cs = NoWheelCombo(), NoWheelCombo()
            for t in audio:
                ca.addItem(track_label(t))
            cs.addItem("— Ninguno —")
            for t in subs:
                cs.addItem(track_label(t))
            oa = next((k for k, t in enumerate(audio) if t["default"]), 0)
            os_ = next((k for k, t in enumerate(subs) if t["default"]), -1)
            if audio:
                ca.setCurrentIndex(oa)
            else:
                ca.addItem("— sin pistas —")
                ca.setEnabled(False)
            cs.setCurrentIndex(os_ + 1)
            row = dict(path=path, audio=audio, subs=subs, ca=ca, cs=cs,
                       oa=oa, os=os_, status=status)
            self.rows.append(row)
            self.table.setCellWidget(i, 1, ca)
            self.table.setCellWidget(i, 2, cs)
            ca.currentIndexChanged.connect(lambda _=0, r=row: self.refresh_row(r))
            cs.currentIndexChanged.connect(lambda _=0, r=row: self.refresh_row(r))

        self.count_label.setText(
            f"{len(results)} MKV encontrados" + (f" ({errors} con error de lectura)" if errors else ""))
        self.fill_global_combos()

    def fill_global_combos(self):
        counts_a, counts_s = {}, {}
        for r in self.rows:
            if not r:
                continue
            for t in r["audio"]:
                counts_a[t["lang"]] = counts_a.get(t["lang"], 0) + 1
            for t in r["subs"]:
                counts_s[t["lang"]] = counts_s.get(t["lang"], 0) + 1
        self.g_audio.clear()
        self.g_subs.clear()
        for lang in sorted(counts_a, key=lambda k: -counts_a[k]):
            self.g_audio.addItem(lang)
        self.g_subs.addItem("— Ninguno —")
        for lang in sorted(counts_s, key=lambda k: -counts_s[k]):
            self.g_subs.addItem(lang)

    # ------------------------------------------------------------ edición
    def refresh_row(self, r):
        changed = (r["audio"] and r["ca"].currentIndex() != r["oa"]) or \
                  (r["cs"].currentIndex() - 1 != r["os"])
        r["status"].setText("● Modificado" if changed else "")
        r["status"].setForeground(QBrush(QColor("#e08a00")))
        r["status"].setToolTip("")

    def apply_all_audio(self):
        lang = self.g_audio.currentText()
        missing = 0
        for r in filter(None, self.rows):
            idx = pick_track(r["audio"], lang)
            if idx is None:
                missing += 1
            else:
                r["ca"].setCurrentIndex(idx)
        if missing:
            self.count_label.setText(f"{missing} archivo(s) sin audio en {lang} (sin cambios)")

    def apply_all_subs(self):
        lang = self.g_subs.currentText()
        missing = 0
        for r in filter(None, self.rows):
            if self.g_subs.currentIndex() == 0:
                r["cs"].setCurrentIndex(0)
                continue
            idx = pick_track(r["subs"], lang)
            if idx is None:
                missing += 1
            else:
                r["cs"].setCurrentIndex(idx + 1)
        if missing:
            self.count_label.setText(f"{missing} archivo(s) sin subtítulos en {lang} (sin cambios)")

    # ------------------------------------------------------------ aplicar
    def build_args(self, r):
        args = ["mkvpropedit", str(r["path"])]
        if r["audio"] and r["ca"].currentIndex() != r["oa"]:
            sel = r["ca"].currentIndex()
            for i in range(len(r["audio"])):
                args += ["--edit", f"track:a{i + 1}", "--set", f"flag-default={int(i == sel)}"]
        sel_s = r["cs"].currentIndex() - 1
        if sel_s != r["os"]:
            for i in range(len(r["subs"])):
                args += ["--edit", f"track:s{i + 1}", "--set", f"flag-default={int(i == sel_s)}"]
        return args if len(args) > 2 else None

    def apply_changes(self):
        jobs = []
        for i, r in enumerate(self.rows):
            if r and (args := self.build_args(r)):
                jobs.append((i, args))
        if not jobs:
            QMessageBox.information(self, "Sin cambios", "No hay nada que modificar.")
            return
        if QMessageBox.question(
                self, "Confirmar",
                f"Se modificarán las pistas por defecto de {len(jobs)} archivo(s).\n"
                "mkvpropedit edita los archivos en el sitio. ¿Continuar?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.apply_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(jobs))
        self.progress.setValue(0)
        self.failed = 0
        self.worker = ApplyWorker(jobs)
        self.worker.item.connect(self.job_done)
        self.worker.progress.connect(lambda n, t: self.progress.setValue(n))
        self.worker.finished.connect(self.apply_finished)
        self.worker.start()

    def job_done(self, row, rc, out):
        r = self.rows[row]
        st = r["status"]
        if rc >= 2:
            self.failed += 1
            st.setText("✗ error")
            st.setForeground(QBrush(QColor("#d32f2f")))
            st.setToolTip(out)
            return
        r["oa"] = r["ca"].currentIndex() if r["audio"] else r["oa"]
        r["os"] = r["cs"].currentIndex() - 1
        st.setText("✓ Guardado" + (" (aviso)" if rc == 1 else ""))
        st.setForeground(QBrush(QColor("#2e7d32")))
        st.setToolTip(out)

    def apply_finished(self):
        self.apply_btn.setEnabled(True)
        self.progress.setVisible(False)
        if self.failed:
            QMessageBox.warning(self, "Terminado con errores",
                                f"{self.failed} archivo(s) fallaron. Pasa el ratón sobre «✗ error» para ver el detalle.")
        else:
            QMessageBox.information(self, "Listo", "Cambios aplicados correctamente.")


def main():
    app = QApplication(sys.argv)
    missing = [t for t in ("mkvmerge", "mkvpropedit") if not shutil.which(t)]
    if missing:
        QMessageBox.critical(None, "Falta mkvtoolnix",
                             f"No se encuentra: {', '.join(missing)}\n\nInstálalo con:\nsudo dnf install mkvtoolnix")
        return 1
    win = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
