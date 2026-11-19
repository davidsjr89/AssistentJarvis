import fcntl
import html
import time
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path

import markdown
from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizeGrip,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

APP_DIR = Path.home() / "Projetos/AssistentJarvis"
CONFIG = tomllib.loads((APP_DIR / "config.toml").read_text(encoding="utf-8"))
DAEMON_SOCKET = os.path.expanduser(CONFIG["paths"]["socket_path"])
WHISPER_BIN = os.path.expanduser(CONFIG["voice"]["whisper_bin"])
WHISPER_MODEL = os.path.expanduser(CONFIG["voice"]["whisper_model"])
PIPER_BIN = os.path.expanduser(CONFIG["voice"]["piper_bin"])
PIPER_VOICE = os.path.expanduser(CONFIG["voice"]["piper_voice"])

GUI_LOCK_PATH = APP_DIR / "gui.lock"
GUI_IPC_SOCKET = APP_DIR / "gui.sock"
ICON_SVG_PATH = APP_DIR / "assets/jarvis.svg"
_INSTANCE_LOCK_FD = None

HUD_STYLESHEET = """
QFrame#MainShell {
    background-color: rgba(7, 12, 20, 242);
    border: 1px solid rgba(0, 229, 255, 115);
    border-radius: 16px;
}
QFrame#SidePanel {
    background-color: rgba(11, 19, 32, 215);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 12px;
}
QFrame#TopBar {
    background-color: rgba(10, 18, 30, 180);
    border-bottom: 1px solid rgba(0, 229, 255, 50);
    border-top-left-radius: 15px;
    border-top-right-radius: 15px;
}
QLabel {
    color: #d8f3ff;
    font-family: "JetBrains Mono", "Fira Code", "Noto Sans", monospace;
    background: transparent;
}
QLabel#BrandTitle {
    color: #00e5ff;
    font-size: 14px;
    font-weight: 800;
    letter-spacing: 2px;
}
QLabel#SubLabel {
    color: #6b8ba4;
    font-size: 10px;
    letter-spacing: 1px;
}
QLabel#MetricTitle {
    color: #5bc0de;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#MetricVal {
    color: #e6f7ff;
    font-size: 11px;
    font-weight: 600;
}
QTextBrowser {
    background-color: rgba(5, 9, 16, 210);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 12px;
    padding: 14px;
    color: #e6f4ff;
    font-family: "Noto Sans", "Inter", sans-serif;
    font-size: 13px;
    selection-background-color: rgba(0, 229, 255, 90);
}
QScrollBar:vertical {
    background: rgba(10, 18, 30, 100);
    width: 7px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: rgba(0, 229, 255, 95);
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QLineEdit {
    background-color: rgba(11, 20, 34, 230);
    border: 1px solid rgba(0, 229, 255, 80);
    border-radius: 10px;
    padding: 11px 15px;
    font-family: "Noto Sans", sans-serif;
    font-size: 13.5px;
    color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #00e5ff;
    background-color: rgba(14, 26, 44, 245);
}
QPushButton {
    background-color: rgba(14, 27, 45, 220);
    border: 1px solid rgba(0, 229, 255, 70);
    border-radius: 8px;
    padding: 7px 12px;
    color: #bceeff;
    font-family: "JetBrains Mono", "Noto Sans", monospace;
    font-size: 11.5px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: rgba(0, 229, 255, 35);
    border-color: #00e5ff;
    color: #ffffff;
}
QPushButton#SendBtn {
    background-color: rgba(0, 180, 216, 220);
    border: 1px solid #00e5ff;
    color: #041018;
    font-weight: 800;
    padding: 9px 18px;
}
QPushButton#SendBtn:hover {
    background-color: #00e5ff;
}
QPushButton#ChipBtn {
    background-color: rgba(10, 22, 38, 190);
    border: 1px solid rgba(0, 229, 255, 45);
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 11px;
    text-align: left;
}
QPushButton#ChipBtn:hover {
    border-color: #00e5ff;
    background-color: rgba(0, 229, 255, 25);
}
QPushButton#WinBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    color: #7da6c2;
    font-size: 12px;
}
QPushButton#WinBtn:hover {
    background-color: rgba(0, 229, 255, 30);
    border-color: rgba(0, 229, 255, 80);
    color: #ffffff;
}
QPushButton:disabled {
    background-color: rgba(18, 24, 34, 150);
    border-color: rgba(100, 120, 140, 40);
    color: #526375;
}
QProgressBar {
    background-color: rgba(6, 12, 22, 220);
    border: 1px solid rgba(0, 229, 255, 50);
    border-radius: 4px;
    height: 7px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0096c7, stop:1 #00f5d4);
    border-radius: 3px;
}
QCheckBox {
    color: #8ab4cc;
    font-family: "JetBrains Mono", monospace;
    font-size: 11px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid rgba(0, 229, 255, 110);
    background: rgba(8, 16, 28, 220);
}
QCheckBox::indicator:checked {
    background: #00e5ff;
    border-color: #00e5ff;
}
"""


def build_tray_icon() -> QIcon:
    if ICON_SVG_PATH.exists():
        return QIcon(str(ICON_SVG_PATH))
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#07111e"))
    p.setPen(QPen(QColor("#00e5ff"), 3.0))
    p.drawRoundedRect(6, 6, 52, 52, 12, 12)
    p.end()
    return QIcon(pixmap)


class IpcListenerThread(QThread):
    command_received = pyqtSignal(str)

    def run(self) -> None:
        if GUI_IPC_SOCKET.exists():
            try:
                GUI_IPC_SOCKET.unlink()
            except OSError:
                pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(GUI_IPC_SOCKET))
        os.chmod(GUI_IPC_SOCKET, 0o600)
        srv.listen(5)
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    cmd = conn.recv(64).decode("utf-8", errors="ignore").strip()
                    self.command_received.emit(cmd or "toggle")
            except OSError:
                break


def speak_async(text: str) -> None:
    if not (os.path.exists(PIPER_BIN) and os.path.exists(PIPER_VOICE)):
        return
    clean = text.replace("*", "").replace("#", "").replace("`", "")[:1200]
    try:
        piper = subprocess.Popen(
            [PIPER_BIN, "--model", PIPER_VOICE, "--output_raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        subprocess.Popen(
            ["pw-play", "--raw", "--rate=22050", "--channels=1", "--format=s16", "-"],
            stdin=piper.stdout,
            stderr=subprocess.DEVNULL,
        )
        assert piper.stdin is not None
        piper.stdin.write(clean.encode("utf-8"))
        piper.stdin.close()
    except Exception:
        pass


class ArcReactorWidget(QWidget):
    """Núcleo holográfico animado em QPainter puro (zero overhead quando oculto)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.state = "idle"  # idle | thinking | listening | error
        self.angle_outer = 0.0
        self.angle_mid = 0.0
        self.angle_inner = 0.0
        self.pulse_phase = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)  # ~30 FPS

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def pause(self) -> None:
        self.timer.stop()

    def resume(self) -> None:
        if not self.timer.isActive():
            self.timer.start(33)

    def _tick(self) -> None:
        speed = {"idle": 1.0, "thinking": 4.2, "listening": 2.8, "error": 0.6}.get(self.state, 1.0)
        self.angle_outer = (self.angle_outer + 0.9 * speed) % 360.0
        self.angle_mid = (self.angle_mid - 1.6 * speed) % 360.0
        self.angle_inner = (self.angle_inner + 2.4 * speed) % 360.0
        self.pulse_phase = (self.pulse_phase + 0.08 * speed) % (2 * math.pi)
        self.update()

    def _palette(self) -> tuple[QColor, QColor, str]:
        if self.state == "thinking":
            return QColor("#ffb703"), QColor("#00e5ff"), "COMPUTE"
        if self.state == "listening":
            return QColor("#38bdf8"), QColor("#00f5d4"), "VOICE IN"
        if self.state == "error":
            return QColor("#ef4444"), QColor("#f97316"), "OFFLINE"
        return QColor("#00e5ff"), QColor("#00f5d4"), "ONLINE"

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        primary, secondary, label = self._palette()
        pulse = 0.5 + 0.5 * math.sin(self.pulse_phase)

        # Halo radial suave
        halo = QRadialGradient(QPointF(cx, cy), 70.0)
        c0 = QColor(primary)
        c0.setAlpha(int(65 + 45 * pulse))
        c1 = QColor(primary)
        c1.setAlpha(0)
        halo.setColorAt(0.0, c0)
        halo.setColorAt(0.65, QColor(primary.red(), primary.green(), primary.blue(), 18))
        halo.setColorAt(1.0, c1)
        p.setBrush(QBrush(halo))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 70.0, 70.0)

        # Anel externo segmentado
        r_out = QRectF(cx - 62, cy - 62, 124, 124)
        pen_out = QPen(QColor(primary.red(), primary.green(), primary.blue(), 170), 2.2)
        p.setPen(pen_out)
        for seg in range(4):
            start = int((self.angle_outer + seg * 90) * 16)
            p.drawArc(r_out, start, 56 * 16)

        # Anel intermediário contra-rotativo
        r_mid = QRectF(cx - 48, cy - 48, 96, 96)
        pen_mid = QPen(QColor(secondary.red(), secondary.green(), secondary.blue(), 210), 3.0)
        p.setPen(pen_mid)
        for seg in range(3):
            start = int((self.angle_mid + seg * 120) * 16)
            p.drawArc(r_mid, start, 75 * 16)

        # Marcações finas (ticks de HUD)
        p.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 95), 1.2))
        for i in range(24):
            ang = math.radians(i * 15 + self.angle_outer * 0.3)
            x1, y1 = cx + 53 * math.cos(ang), cy + 53 * math.sin(ang)
            x2, y2 = cx + 57 * math.cos(ang), cy + 57 * math.sin(ang)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Anel interno rápido
        r_in = QRectF(cx - 33, cy - 33, 66, 66)
        p.setPen(QPen(primary, 1.8))
        for seg in range(6):
            start = int((self.angle_inner + seg * 60) * 16)
            p.drawArc(r_in, start, 34 * 16)

        # Núcleo central pulsante
        core_r = 21.0 + 3.0 * pulse
        core_grad = QRadialGradient(QPointF(cx, cy), core_r)
        core_grad.setColorAt(0.0, QColor(230, 252, 255, 220))
        core_grad.setColorAt(0.5, QColor(primary.red(), primary.green(), primary.blue(), 140))
        core_grad.setColorAt(1.0, QColor(primary.red(), primary.green(), primary.blue(), 25))
        p.setBrush(QBrush(core_grad))
        p.setPen(QPen(primary, 1.4))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Rótulo central
        p.setPen(QColor("#041018"))
        p.setFont(QFont("JetBrains Mono", 7, QFont.Weight.Bold))
        p.drawText(QRectF(cx - 30, cy - 8, 60, 16), Qt.AlignmentFlag.AlignCenter, label)
        p.end()


class TelemetryWorker(QThread):
    updated = pyqtSignal(dict)

    def run(self) -> None:
        data = {
            "gpu_util": 0,
            "vram_used": 0,
            "vram_total": 16303,
            "gpu_temp": 0,
            "ram_used": 0.0,
            "ram_total": 32.0,
        }
        # 1. RAM direta via /proc/meminfo (zero subprocesso, imune a idioma)
        try:
            meminfo = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        meminfo[parts[0].rstrip(":")] = int(parts[1])
            total_gb = meminfo.get("MemTotal", 0) / (1024 * 1024)
            avail_gb = meminfo.get("MemAvailable", 0) / (1024 * 1024)
            data["ram_total"] = round(total_gb, 1)
            data["ram_used"] = round(max(0.0, total_gb - avail_gb), 1)
        except Exception:
            pass

        # 2. RTX 5080 via nvidia-smi
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=2,
            ).strip()
            parts = [int(x.strip()) for x in out.split(",")]
            if len(parts) == 4:
                data["gpu_util"], data["vram_used"], data["vram_total"], data["gpu_temp"] = parts
        except Exception:
            pass

        self.updated.emit(data)


class PromptWorker(QThread):
    finished_ok = pyqtSignal(dict)
    finished_err = pyqtSignal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self) -> None:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(180)
                s.connect(DAEMON_SOCKET)
                s.sendall(json.dumps({"prompt": self.prompt}, ensure_ascii=False).encode("utf-8"))
                s.shutdown(socket.SHUT_WR)
                chunks = []
                while data := s.recv(65536):
                    chunks.append(data)
            resp = json.loads(b"".join(chunks).decode("utf-8"))
            self.finished_ok.emit(resp)
        except Exception as e:
            self.finished_err.emit(str(e))


class VoiceWorker(QThread):
    transcribed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def run(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name
        try:
            subprocess.run(
                ["timeout", "5", "pw-record", "--format=s16", "--rate=16000", "--channels=1", wav_path],
                check=False,
                stderr=subprocess.DEVNULL,
            )
            res = subprocess.run(
                [WHISPER_BIN, "-m", WHISPER_MODEL, "-l", "pt", "-nt", "-f", wav_path],
                capture_output=True,
                text=True,
            )
            text = res.stdout.strip()
            if text:
                self.transcribed.emit(text)
            else:
                self.failed.emit("Nenhuma fala detectada nos 5 segundos de gravação.")
        except Exception as e:
            self.failed.emit(f"Erro no módulo de voz: {e}")
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)


class DraggableTopBar(QFrame):
    def __init__(self, parent_window: QWidget):
        super().__init__()
        self.setObjectName("TopBar")
        self.parent_window = parent_window
        self._drag_offset = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.parent_window.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
            self._drag_offset = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.parent_window.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None


class JarvisWindow(QWidget):
    def __init__(self, icon: QIcon):
        super().__init__()
        self.app_icon = icon
        self.worker: PromptWorker | None = None
        self.voice_worker: VoiceWorker | None = None
        self.telemetry_worker: TelemetryWorker | None = None
        self.messages_html: list[str] = []
        self.pinned = False

        self.setWindowTitle("J.A.R.V.I.S. // CachyOS Core")
        self.setWindowIcon(icon)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(980, 640)
        self.setMinimumSize(760, 500)
        self.setStyleSheet(HUD_STYLESHEET)

        self._build_ui()
        self._setup_tray()
        self._setup_ipc()
        self._setup_timers()

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.hide)
        self._append_system(
            "SISTEMA INICIALIZADO • CachyOS Kernel BORE + RTX 5080 CUDA • Pressione [ESC] para recolher à bandeja."
        )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.shell = QFrame()
        self.shell.setObjectName("MainShell")
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # ── BARRA SUPERIOR (ARRASTÁVEL) ──
        top_bar = DraggableTopBar(self)
        top_bar.setFixedHeight(44)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 12, 0)

        brand = QLabel("◈ J.A.R.V.I.S. // CACHYOS")
        brand.setObjectName("BrandTitle")

        self.model_badge = QLabel("MODEL: gemma4:12b")
        self.model_badge.setStyleSheet(
            "background: rgba(0, 229, 255, 22); border: 1px solid rgba(0, 229, 255, 75);"
            "border-radius: 6px; padding: 2px 8px; color: #7ef9ff; font-size: 10.5px;"
        )

        self.clock_lbl = QLabel()
        self.clock_lbl.setStyleSheet("color: #7ea8c4; font-size: 11px;")

        self.pin_btn = QPushButton("📌")
        self.pin_btn.setObjectName("WinBtn")
        self.pin_btn.setToolTip("Fixar acima das janelas")
        self.pin_btn.clicked.connect(self.toggle_pin)

        hide_btn = QPushButton("—")
        hide_btn.setObjectName("WinBtn")
        hide_btn.setToolTip("Ocultar na bandeja (Esc)")
        hide_btn.clicked.connect(self.hide)

        top_layout.addWidget(brand)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.model_badge)
        top_layout.addStretch()
        top_layout.addWidget(self.clock_lbl)
        top_layout.addSpacing(10)
        top_layout.addWidget(self.pin_btn)
        top_layout.addWidget(hide_btn)
        shell_layout.addWidget(top_bar)

        # ── CORPO PRINCIPAL (SIDEBAR HUD + CHAT) ──
        body = QHBoxLayout()
        body.setContentsMargins(14, 14, 14, 12)
        body.setSpacing(14)

        # SIDEBAR ESQUERDA (ARC REACTOR + TELEMETRIA + ATALHOS)
        side = QFrame()
        side.setObjectName("SidePanel")
        side.setFixedWidth(235)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(14, 14, 14, 12)
        side_layout.setSpacing(10)

        reactor_wrap = QHBoxLayout()
        self.reactor = ArcReactorWidget()
        reactor_wrap.addStretch()
        reactor_wrap.addWidget(self.reactor)
        reactor_wrap.addStretch()
        side_layout.addLayout(reactor_wrap)

        self.status_lbl = QLabel("● PROTOCOLO ATIVO")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("color: #00f5d4; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        side_layout.addWidget(self.status_lbl)

        # Telemetria Hardware
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background-color: rgba(0, 229, 255, 35); max-height: 1px;")
        side_layout.addWidget(sep1)

        tel_hdr = QLabel("TELEMETRIA DE HARDWARE")
        tel_hdr.setObjectName("SubLabel")
        side_layout.addWidget(tel_hdr)

        self.gpu_lbl = QLabel("RTX 5080: --%  •  --°C")
        self.gpu_lbl.setObjectName("MetricVal")
        self.gpu_bar = QProgressBar()
        self.gpu_bar.setRange(0, 100)
        self.gpu_bar.setTextVisible(False)

        self.vram_lbl = QLabel("VRAM: -- / 16.3 GB")
        self.vram_lbl.setObjectName("MetricVal")
        self.vram_bar = QProgressBar()
        self.vram_bar.setRange(0, 100)
        self.vram_bar.setTextVisible(False)

        self.ram_lbl = QLabel("DDR5: -- / 32.0 GB")
        self.ram_lbl.setObjectName("MetricVal")
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setTextVisible(False)

        side_layout.addWidget(self.gpu_lbl)
        side_layout.addWidget(self.gpu_bar)
        side_layout.addWidget(self.vram_lbl)
        side_layout.addWidget(self.vram_bar)
        side_layout.addWidget(self.ram_lbl)
        side_layout.addWidget(self.ram_bar)

        # Módulos MCP
        mcp_lbl = QLabel("MCP: ● OS  ● DEV  ● GMAIL  ● WEB")
        mcp_lbl.setStyleSheet("color: #4cc9f0; font-size: 9.5px; margin-top: 4px;")
        side_layout.addWidget(mcp_lbl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background-color: rgba(0, 229, 255, 35); max-height: 1px;")
        side_layout.addWidget(sep2)

        # Comandos Rápidos
        quick_hdr = QLabel("COMANDOS RÁPIDOS")
        quick_hdr.setObjectName("SubLabel")
        side_layout.addWidget(quick_hdr)

        quick_actions = [
            ("📅  Agenda Próxima", "Quais são os meus próximos compromissos na agenda?"),
            ("📧  E-mails Não Lidos", "Liste meus e-mails não lidos mais recentes."),
            ("⚡  Diagnóstico GPU/RAM", "Qual é o estado atual da minha GPU, RAM e disco?"),
            ("📁  Listar Projetos", "Liste os projetos existentes em ~/Projetos."),
        ]
        for title, prompt in quick_actions:
            btn = QPushButton(title)
            btn.setObjectName("ChipBtn")
            btn.clicked.connect(lambda _checked=False, p=prompt: self.send_prompt(p))
            side_layout.addWidget(btn)

        side_layout.addStretch()

        self.tts_check = QCheckBox("Resposta por Voz (PT-BR)")
        side_layout.addWidget(self.tts_check)

        clear_btn = QPushButton("⌫ Limpar Memória")
        clear_btn.clicked.connect(self.clear_memory)
        side_layout.addWidget(clear_btn)

        body.addWidget(side)

        # ÁREA DIREITA (CHAT + INPUT)
        right = QVBoxLayout()
        right.setSpacing(10)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        right.addWidget(self.chat_view, stretch=1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Fale ou digite um comando para o J.A.R.V.I.S...")
        self.input_box.returnPressed.connect(self.send_current_input)

        self.voice_btn = QPushButton("🎙️ VOZ")
        self.voice_btn.setToolTip("Grava 5 segundos via PipeWire e transcreve na RTX 5080")
        self.voice_btn.clicked.connect(self.start_voice_capture)

        self.send_btn = QPushButton("ENVIAR ▸")
        self.send_btn.setObjectName("SendBtn")
        self.send_btn.clicked.connect(self.send_current_input)

        input_row.addWidget(self.input_box, stretch=1)
        input_row.addWidget(self.voice_btn)
        input_row.addWidget(self.send_btn)
        right.addLayout(input_row)

        # Rodapé discreto + alça de redimensionamento
        footer = QHBoxLayout()
        footer_lbl = QLabel("LOCAL CUDA • ZERO-COST • SANDBOX BWRAP + HITL SECURITY")
        footer_lbl.setStyleSheet("color: #446078; font-size: 9.5px; letter-spacing: 1px;")
        footer.addWidget(footer_lbl)
        footer.addStretch()
        footer.addWidget(QSizeGrip(self.shell))
        right.addLayout(footer)

        body.addLayout(right, stretch=1)
        shell_layout.addLayout(body, stretch=1)

        outer.addWidget(self.shell)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip("J.A.R.V.I.S. // CachyOS Assistant")

        menu = QMenu()
        act_toggle = QAction("Abrir / Ocultar HUD", self)
        act_toggle.triggered.connect(self.toggle_visibility)

        act_voice = QAction("🎙️ Comando de Voz (5s)", self)
        act_voice.triggered.connect(self._tray_voice)

        act_clear = QAction("Limpar Memória", self)
        act_clear.triggered.connect(self.clear_memory)

        act_quit = QAction("Encerrar Interface", self)
        act_quit.triggered.connect(QApplication.quit)

        menu.addAction(act_toggle)
        menu.addAction(act_voice)
        menu.addAction(act_clear)
        menu.addSeparator()
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _setup_ipc(self) -> None:
        self.ipc_thread = IpcListenerThread(self)
        self.ipc_thread.command_received.connect(self._on_ipc_command)
        self.ipc_thread.start()

    def _setup_timers(self) -> None:
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)
        self._update_clock()

        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._poll_telemetry)
        self.telemetry_timer.start(3000)
        self._poll_telemetry()

    def _update_clock(self) -> None:
        self.clock_lbl.setText(datetime.now().strftime("%d/%m/%Y  •  %H:%M:%S"))

    def _poll_telemetry(self) -> None:
        if not self.isVisible():
            return
        if self.telemetry_worker and self.telemetry_worker.isRunning():
            return
        self.telemetry_worker = TelemetryWorker()
        self.telemetry_worker.updated.connect(self._apply_telemetry)
        self.telemetry_worker.start()

    def _apply_telemetry(self, d: dict) -> None:
        self.gpu_lbl.setText(f"RTX 5080: {d['gpu_util']}%  •  {d['gpu_temp']}°C")
        self.gpu_bar.setValue(min(100, max(0, d["gpu_util"])))

        vram_gb = d["vram_used"] / 1024.0
        vram_tot_gb = max(0.1, d["vram_total"] / 1024.0)
        vram_pct = int((d["vram_used"] / max(1, d["vram_total"])) * 100)
        self.vram_lbl.setText(f"VRAM: {vram_gb:.1f} / {vram_tot_gb:.1f} GB")
        self.vram_bar.setValue(min(100, max(0, vram_pct)))

        ram_pct = int((d["ram_used"] / max(0.1, d["ram_total"])) * 100)
        self.ram_lbl.setText(f"DDR5: {d['ram_used']:.1f} / {d['ram_total']:.1f} GB")
        self.ram_bar.setValue(min(100, max(0, ram_pct)))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.reactor.resume()
        self.clock_timer.start(1000)
        self.telemetry_timer.start(3000)
        self._update_clock()
        self._poll_telemetry()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # Pausa animações e telemetria na bandeja -> ~0% CPU em segundo plano
        self.reactor.pause()
        self.clock_timer.stop()
        self.telemetry_timer.stop()

    def toggle_pin(self) -> None:
        self.pinned = not self.pinned
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
        if self.pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            self.pin_btn.setStyleSheet("color: #00e5ff; border: 1px solid #00e5ff; border-radius: 6px; padding: 3px 8px;")
        else:
            self.pin_btn.setStyleSheet("")
        self.setWindowFlags(flags)
        self.show_and_focus()

    def _on_ipc_command(self, cmd: str) -> None:
        if cmd == "show":
            self.show_and_focus()
        else:
            self.toggle_visibility()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_visibility()

    def _tray_voice(self) -> None:
        self.show_and_focus()
        self.start_voice_capture()

    def show_and_focus(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.input_box.setFocus()

    def toggle_visibility(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_and_focus()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def _render_chat(self) -> None:
        doc = """
        <style>
            body { color: #e2f1ff; font-size: 13px; line-height: 1.5; }
            .msg-user {
                background: rgba(0, 145, 200, 0.16);
                padding: 10px 14px;
                border-radius: 10px;
                margin-bottom: 12px;
                border-left: 3px solid #00e5ff;
            }
            .msg-ai {
                background: rgba(14, 24, 38, 0.85);
                padding: 11px 14px;
                border-radius: 10px;
                margin-bottom: 14px;
                border-left: 3px solid #00f5d4;
            }
            .msg-sys {
                color: #5c7c99;
                font-family: monospace;
                font-size: 11px;
                margin-bottom: 12px;
                letter-spacing: 0.5px;
            }
            .meta-user { color: #00e5ff; font-family: monospace; font-size: 10.5px; font-weight: bold; margin-bottom: 4px; }
            .meta-ai { color: #00f5d4; font-family: monospace; font-size: 10.5px; font-weight: bold; margin-bottom: 5px; }
            pre, code {
                background: #070d17;
                color: #79d2ff;
                font-family: "JetBrains Mono", monospace;
                padding: 2px 5px;
                border-radius: 4px;
            }
            pre { padding: 10px; border: 1px solid rgba(0, 229, 255, 0.25); }
            a { color: #38bdf8; }
            ul, ol { margin-top: 4px; margin-bottom: 4px; }
        </style>
        """ + "".join(self.messages_html)
        self.chat_view.setHtml(doc)
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _append_system(self, text: str) -> None:
        self.messages_html.append(f'<div class="msg-sys">» {html.escape(text)}</div>')
        self._render_chat()

    def _append_user(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        safe = html.escape(text).replace("\n", "<br>")
        self.messages_html.append(
            f'<div class="msg-user"><div class="meta-user">OPERADOR • {ts}</div>{safe}</div>'
        )
        self._render_chat()

    def _append_ai(self, model: str, md_text: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        rendered = markdown.markdown(md_text, extensions=["fenced_code", "tables", "nl2br"])
        self.messages_html.append(
            f'<div class="msg-ai"><div class="meta-ai">J.A.R.V.I.S. • {html.escape(model)} • {ts}</div>{rendered}</div>'
        )
        self._render_chat()

    def _set_state(self, state: str, status_text: str, color: str, busy: bool) -> None:
        self.reactor.set_state(state)
        self.status_lbl.setText(status_text)
        self.status_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        self.input_box.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.voice_btn.setEnabled(not busy)

    def send_current_input(self) -> None:
        prompt = self.input_box.text().strip()
        if not prompt:
            return
        self.input_box.clear()
        self.send_prompt(prompt)

    def send_prompt(self, prompt: str) -> None:
        self._append_user(prompt)
        self._set_state("thinking", "● PROCESSANDO CUDA...", "#ffb703", True)
        self.worker = PromptWorker(prompt)
        self.worker.finished_ok.connect(self._on_reply)
        self.worker.finished_err.connect(self._on_error)
        self.worker.start()

    def _on_reply(self, resp: dict) -> None:
        reply = resp.get("reply", "(Sem resposta)")
        model = resp.get("model", "local")
        self.model_badge.setText(f"MODEL: {model}")
        self._set_state("idle", "● PROTOCOLO ATIVO", "#00f5d4", False)
        self._append_ai(model, reply)
        if self.tts_check.isChecked():
            speak_async(reply)
        self.input_box.setFocus()

    def _on_error(self, err: str) -> None:
        self._set_state("error", "● FALHA NO DAEMON", "#ef4444", False)
        self._append_system(f"ERRO DE CONEXÃO: {err}")

    def start_voice_capture(self) -> None:
        self._set_state("listening", "🎙️ CAPTURANDO ÁUDIO (5s)", "#38bdf8", True)
        self.voice_worker = VoiceWorker()
        self.voice_worker.transcribed.connect(self._on_voice_ok)
        self.voice_worker.failed.connect(self._on_voice_err)
        self.voice_worker.start()

    def _on_voice_ok(self, text: str) -> None:
        self.send_prompt(text)

    def _on_voice_err(self, err: str) -> None:
        self._set_state("idle", "● PROTOCOLO ATIVO", "#00f5d4", False)
        self._append_system(err)

    def clear_memory(self) -> None:
        self.messages_html.clear()
        self._append_system("MEMÓRIA DE SESSÃO REINICIADA.")
        self.worker = PromptWorker("/clear")
        self.worker.finished_ok.connect(lambda _: self._set_state("idle", "● PROTOCOLO ATIVO", "#00f5d4", False))
        self.worker.finished_err.connect(self._on_error)
        self.worker.start()


def acquire_single_instance_lock() -> bool:
    global _INSTANCE_LOCK_FD
    GUI_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = open(GUI_LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        _INSTANCE_LOCK_FD = fd
        return True
    except BlockingIOError:
        fd.close()
        return False


def signal_existing_instance(minimized: bool) -> None:
    if minimized:
        return
    for _ in range(10):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(str(GUI_IPC_SOCKET))
                s.sendall(b"toggle")
                return
        except OSError:
            time.sleep(0.1)


def main() -> None:
    minimized = "--minimized" in sys.argv
    if not acquire_single_instance_lock():
        signal_existing_instance(minimized)
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("J.A.R.V.I.S. CachyOS")
    app.setDesktopFileName("cachy-assistant")
    app.setQuitOnLastWindowClosed(False)

    icon = build_tray_icon()
    app.setWindowIcon(icon)
    window = JarvisWindow(icon)
    if not minimized:
        window.show_and_focus()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
