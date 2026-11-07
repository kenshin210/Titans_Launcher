import re
import shutil
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from Application.styles import load_stylesheet


class SoundDisplaySettingsWidget(QWidget):
    def __init__(self, launcher):
        super().__init__()
        self.launcher = launcher
        self.setObjectName("soundDisplaySettings")
        self.setStyleSheet(load_stylesheet(theme_color=launcher.get_theme_color()))
        self.display_outputs = {}

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 10, 0)
        content_layout.setSpacing(12)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        title = QLabel("Display & Sound")
        title.setObjectName("soundDisplayTitle")
        content_layout.addWidget(title)

        description = QLabel(
            "Configure available PipeWire audio and KDE Wayland display settings. "
            "Controls are enabled only when the system reports support."
        )
        description.setObjectName("soundDisplayDescription")
        description.setWordWrap(True)
        content_layout.addWidget(description)

        content_layout.addWidget(self._build_audio_card())
        content_layout.addWidget(self._build_display_card())
        content_layout.addWidget(self._build_cec_card())
        content_layout.addStretch()

        self.refresh_all()

    @staticmethod
    def _run(command, timeout=4, input_text=None):
        try:
            return subprocess.run(
                command,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return subprocess.CompletedProcess(command, 127, "", str(error))

    @staticmethod
    def _is_success(result):
        return not isinstance(result, Exception) and result.returncode == 0

    def _build_audio_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Audio Output")
        title.setObjectName("soundDisplaySectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        self.audio_sink_combo = QComboBox()
        self.audio_sink_combo.setObjectName("soundDisplayControl")
        form.addRow("Output device:", self.audio_sink_combo)

        volume_row = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("soundDisplaySlider")
        self.volume_slider.setRange(0, 150)
        self.volume_value = QLabel("Unavailable")
        self.volume_value.setObjectName("soundDisplayValue")
        self.volume_slider.valueChanged.connect(
            lambda value: self.volume_value.setText(f"{value}%")
        )
        volume_row.addWidget(self.volume_slider, stretch=1)
        volume_row.addWidget(self.volume_value)
        form.addRow("Volume:", volume_row)

        self.audio_mute = QCheckBox("Muted")
        form.addRow("Mute:", self.audio_mute)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.audio_apply_button = QPushButton("Apply Audio")
        self.audio_apply_button.setObjectName("soundDisplayButton")
        self.audio_apply_button.clicked.connect(self.apply_audio_settings)
        refresh_audio_button = QPushButton("Refresh Audio")
        refresh_audio_button.setObjectName("soundDisplayButton")
        refresh_audio_button.clicked.connect(self.refresh_audio)
        actions.addWidget(refresh_audio_button)
        actions.addWidget(self.audio_apply_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.audio_status = QLabel()
        self.audio_status.setObjectName("soundDisplayStatus")
        self.audio_status.setWordWrap(True)
        layout.addWidget(self.audio_status)
        return card

    def _build_display_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Display")
        title.setObjectName("soundDisplaySectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        self.display_combo = QComboBox()
        self.display_combo.setObjectName("soundDisplayControl")
        self.display_combo.currentIndexChanged.connect(self.update_display_controls)
        form.addRow("Display:", self.display_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("soundDisplayControl")
        form.addRow("Resolution / refresh rate:", self.mode_combo)

        self.scale_combo = QComboBox()
        self.scale_combo.setObjectName("soundDisplayControl")
        for scale in ("1", "1.25", "1.5", "1.75", "2"):
            self.scale_combo.addItem(f"{scale}x", scale)
        form.addRow("Display / text scale:", self.scale_combo)

        self.hdr_checkbox = QCheckBox("Enable HDR")
        form.addRow("HDR:", self.hdr_checkbox)

        self.color_range_combo = QComboBox()
        self.color_range_combo.setObjectName("soundDisplayControl")
        self.color_range_combo.addItems(["Automatic", "Full", "Limited"])
        form.addRow("Color range:", self.color_range_combo)
        layout.addLayout(form)

        self.vsync_status = QLabel(
            "V-Sync is managed by the compositor or individual applications on Wayland."
        )
        self.vsync_status.setObjectName("soundDisplayStatus")
        self.vsync_status.setWordWrap(True)
        layout.addWidget(self.vsync_status)

        actions = QHBoxLayout()
        self.display_apply_button = QPushButton("Apply Display")
        self.display_apply_button.setObjectName("soundDisplayButton")
        self.display_apply_button.clicked.connect(self.apply_display_settings)
        self.display_refresh_button = QPushButton("Refresh Displays")
        self.display_refresh_button.setObjectName("soundDisplayButton")
        self.display_refresh_button.clicked.connect(self.refresh_displays)
        actions.addWidget(self.display_apply_button)
        actions.addWidget(self.display_refresh_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.display_status = QLabel()
        self.display_status.setObjectName("soundDisplayStatus")
        self.display_status.setWordWrap(True)
        layout.addWidget(self.display_status)
        return card

    def _build_cec_card(self):
        card = QFrame()
        card.setObjectName("soundDisplayCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("HDMI-CEC")
        title.setObjectName("soundDisplaySectionTitle")
        layout.addWidget(title)

        self.cec_status = QLabel()
        self.cec_status.setObjectName("soundDisplayStatus")
        self.cec_status.setWordWrap(True)
        layout.addWidget(self.cec_status)

        actions = QHBoxLayout()
        self.cec_on_button = QPushButton("Wake TV")
        self.cec_on_button.setObjectName("soundDisplayButton")
        self.cec_on_button.clicked.connect(lambda: self.send_cec_command("on 0"))
        self.cec_standby_button = QPushButton("TV Standby")
        self.cec_standby_button.setObjectName("soundDisplayButton")
        self.cec_standby_button.clicked.connect(lambda: self.send_cec_command("standby 0"))
        self.cec_refresh_button = QPushButton("Refresh CEC")
        self.cec_refresh_button.setObjectName("soundDisplayButton")
        self.cec_refresh_button.clicked.connect(self.refresh_cec)
        actions.addWidget(self.cec_on_button)
        actions.addWidget(self.cec_standby_button)
        actions.addWidget(self.cec_refresh_button)
        actions.addStretch()
        layout.addLayout(actions)
        return card

    def refresh_all(self):
        self.refresh_audio()
        self.refresh_displays()
        self.refresh_cec()

    def refresh_audio(self):
        wpctl = shutil.which("wpctl")
        self.audio_sink_combo.clear()
        if not wpctl:
            self.audio_status.setText("PipeWire controls unavailable: wpctl was not found.")
            self.audio_sink_combo.setEnabled(False)
            self.volume_slider.setEnabled(False)
            self.audio_mute.setEnabled(False)
            self.audio_apply_button.setEnabled(False)
            return

        result = self._run([wpctl, "status"])
        if not self._is_success(result):
            self.audio_status.setText("Could not read PipeWire audio devices.")
            self.audio_sink_combo.setEnabled(False)
            self.volume_slider.setEnabled(False)
            self.audio_mute.setEnabled(False)
            self.audio_apply_button.setEnabled(False)
            return

        in_sinks = False
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if re.search(r"\bSinks:\s*$", stripped):
                in_sinks = True
                continue
            if in_sinks and stripped and stripped.endswith(":"):
                break
            if not in_sinks:
                continue
            match = re.match(r"^\s*[│├└─ ]*(\*)?\s*(\d+)\.\s*(.+?)(?:\s+\[vol:.*)?\s*$", line)
            if match:
                sink_id, sink_name = match.group(2), match.group(3).strip()
                suffix = " (default)" if match.group(1) else ""
                self.audio_sink_combo.addItem(f"{sink_name}{suffix}", sink_id)

        self.audio_sink_combo.setEnabled(self.audio_sink_combo.count() > 0)
        default_volume = self._run([wpctl, "get-volume", "@DEFAULT_AUDIO_SINK@"])
        if self._is_success(default_volume):
            volume_match = re.search(r"Volume:\s*([0-9.]+)", default_volume.stdout)
            if volume_match:
                volume_percent = round(float(volume_match.group(1)) * 100)
                self.volume_slider.blockSignals(True)
                self.volume_slider.setValue(volume_percent)
                self.volume_slider.blockSignals(False)
                self.volume_value.setText(f"{volume_percent}%")
            self.audio_mute.setChecked("MUTED" in default_volume.stdout.upper())
        audio_available = self.audio_sink_combo.count() > 0 or self._is_success(default_volume)
        self.volume_slider.setEnabled(audio_available)
        self.audio_mute.setEnabled(audio_available)
        self.audio_apply_button.setEnabled(audio_available)
        self.audio_status.setText(
            "PipeWire controls ready." if audio_available else "No PipeWire output sink was detected."
        )

    def apply_audio_settings(self):
        wpctl = shutil.which("wpctl")
        if not wpctl:
            return
        sink_id = self.audio_sink_combo.currentData()
        if sink_id is not None:
            default_result = self._run([wpctl, "set-default", str(sink_id)])
            if not self._is_success(default_result):
                self.audio_status.setText("Could not select the requested audio output.")
                return
        volume = self.volume_slider.value() / 100
        volume_result = self._run([wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", f"{volume:.2f}"])
        mute_value = "1" if self.audio_mute.isChecked() else "0"
        mute_result = self._run([wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", mute_value])
        if self._is_success(volume_result) and self._is_success(mute_result):
            self.audio_status.setText("Audio settings applied.")
        else:
            self.audio_status.setText("PipeWire could not apply one or more audio settings.")

    def refresh_displays(self):
        kscreen_doctor = shutil.which("kscreen-doctor")
        self.display_outputs.clear()
        self.display_combo.clear()
        self.mode_combo.clear()
        if not kscreen_doctor:
            self.display_status.setText("KDE display controls unavailable: kscreen-doctor was not found.")
            self.display_combo.setEnabled(False)
            self.mode_combo.setEnabled(False)
            self.scale_combo.setEnabled(False)
            self.hdr_checkbox.setEnabled(False)
            self.color_range_combo.setEnabled(False)
            self.display_apply_button.setEnabled(False)
            return

        result = self._run([kscreen_doctor, "-o"])
        if not self._is_success(result):
            self.display_status.setText("Could not query displays with kscreen-doctor.")
            self.display_combo.setEnabled(False)
            self.mode_combo.setEnabled(False)
            self.scale_combo.setEnabled(False)
            self.hdr_checkbox.setEnabled(False)
            self.color_range_combo.setEnabled(False)
            self.display_apply_button.setEnabled(False)
            return

        # kscreen-doctor emits ANSI color codes even when piped.
        clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        blocks = re.split(r"(?m)^Output:\s*", clean_output)[1:]
        for block in blocks:
            lines = block.splitlines()
            if not lines:
                continue
            header = lines[0].strip()
            header_match = re.match(r"(\d+)\s+(\S+)\s+(.*)", header)
            state_lines = {line.strip().lower() for line in lines[1:]}
            if not header_match or "connected" not in state_lines:
                continue
            output_id, connector = header_match.group(1), header_match.group(2)
            modes_line = next((line for line in lines if line.strip().startswith("Modes:")), "")
            modes = []
            current_mode = None
            for mode_match in re.finditer(r"(\d+):\s*(\d+x\d+@[\d.]+)([*!]*)", modes_line):
                mode_id, mode, flags = mode_match.groups()
                label = f"{mode} (current)" if "*" in flags else mode
                modes.append((label, mode_id))
                if "*" in flags:
                    current_mode = mode_id

            scale_line = next((line for line in lines if line.strip().startswith("Scale:")), "")
            scale_match = re.search(r"Scale:\s*([\d.]+)", scale_line)
            scale = scale_match.group(1) if scale_match else "1"
            hdr_line = next((line for line in lines if re.search(r"HDR:", line, re.IGNORECASE)), "")
            color_line = next((line for line in lines if "RgbRange:" in line), "")
            color_match = re.search(r"RgbRange:\s*(\w+)", color_line)
            vrr_line = next((line for line in lines if re.search(r"Vrr:", line, re.IGNORECASE)), "")
            self.display_outputs[connector] = {
                "id": output_id,
                "modes": modes,
                "current_mode": current_mode,
                "scale": scale,
                "hdr_line": hdr_line,
                "color_range": color_match.group(1) if color_match else None,
                "vrr_line": vrr_line,
            }
            self.display_combo.addItem(f"{connector} ({output_id})", connector)

        display_available = self.display_combo.count() > 0
        self.display_combo.setEnabled(display_available)
        self.update_display_controls(self.display_combo.currentIndex())
        if not display_available:
            self.display_status.setText("No connected displays were reported by KScreen.")

    def update_display_controls(self, _index):
        connector = self.display_combo.currentData()
        output = self.display_outputs.get(connector)
        if not output:
            self.mode_combo.setEnabled(False)
            self.scale_combo.setEnabled(False)
            self.hdr_checkbox.setEnabled(False)
            self.color_range_combo.setEnabled(False)
            self.display_apply_button.setEnabled(False)
            return

        self.mode_combo.clear()
        for label, mode in output["modes"]:
            self.mode_combo.addItem(label, mode)
        if output["current_mode"] is not None:
            current_index = self.mode_combo.findData(output["current_mode"])
            if current_index >= 0:
                self.mode_combo.setCurrentIndex(current_index)
        self.mode_combo.setEnabled(bool(output["modes"]))

        scale_index = self.scale_combo.findData(output["scale"])
        if scale_index < 0:
            self.scale_combo.addItem(f"{output['scale']}x (current)", output["scale"])
            scale_index = self.scale_combo.count() - 1
        self.scale_combo.setCurrentIndex(scale_index)
        self.scale_combo.setEnabled(True)

        hdr_text = output["hdr_line"].lower()
        hdr_supported = bool(output["hdr_line"]) and not re.search(
            r"not supported|unsupported|incapable", hdr_text
        )
        self.hdr_checkbox.blockSignals(True)
        self.hdr_checkbox.setChecked("enabled" in hdr_text or "true" in hdr_text)
        self.hdr_checkbox.blockSignals(False)
        self.hdr_checkbox.setEnabled(hdr_supported)
        self.hdr_checkbox.setToolTip(
            "HDR state is reported by KScreen." if hdr_supported else "HDR is not reported as supported by KScreen."
        )

        color_range = output["color_range"]
        self.color_range_combo.setEnabled(color_range is not None)
        if color_range is not None:
            if self.color_range_combo.findText(color_range) < 0:
                self.color_range_combo.addItem(color_range)
            self.color_range_combo.setCurrentText(color_range)

        vrr_text = output["vrr_line"].strip()
        self.vsync_status.setText(
            f"Adaptive sync (VRR): {vrr_text.split(':', 1)[1].strip()}"
            if vrr_text else
            "V-Sync is managed by the compositor or individual applications on Wayland."
        )
        self.display_apply_button.setEnabled(True)
        self.display_status.setText("Display controls ready.")

    def apply_display_settings(self):
        kscreen_doctor = shutil.which("kscreen-doctor")
        connector = self.display_combo.currentData()
        output = self.display_outputs.get(connector)
        if not kscreen_doctor or not output:
            return

        prefix = f"output.{connector}"
        commands = []
        mode = self.mode_combo.currentData()
        if mode:
            commands.append(f"{prefix}.mode.{mode}")
        scale = self.scale_combo.currentData()
        if scale:
            commands.append(f"{prefix}.scale.{scale}")
        if output["hdr_line"]:
            commands.append(f"{prefix}.hdr.{ 'enable' if self.hdr_checkbox.isChecked() else 'disable' }")
        if output["color_range"] is not None:
            commands.append(f"{prefix}.rgbRange.{self.color_range_combo.currentText().lower()}")

        for command in commands:
            result = self._run([kscreen_doctor, command])
            if not self._is_success(result):
                details = result.stderr.strip() if not isinstance(result, Exception) else str(result)
                self.display_status.setText(f"KScreen rejected {command}: {details}")
                return
        self.display_status.setText("Display settings applied.")
        self.refresh_displays()

    def refresh_cec(self):
        cec_client = shutil.which("cec-client")
        cec_ctl = shutil.which("cec-ctl")
        if cec_client:
            result = self._run([cec_client, "-l"])
            found = (
                self._is_success(result)
                and bool(result.stdout.strip())
                and not re.search(
                    r"found devices:\s*0|no devices|no adapters",
                    result.stdout,
                    re.IGNORECASE,
                )
            )
            self.cec_status.setText(
                "CEC client detected. TV wake and standby commands are available."
                if found else
                "cec-client is installed, but no CEC adapter was reported."
            )
            self.cec_on_button.setEnabled(found)
            self.cec_standby_button.setEnabled(found)
            return
        if cec_ctl:
            result = self._run([cec_ctl, "--list-devices"])
            found = self._is_success(result) and bool(result.stdout.strip())
            self.cec_status.setText(
                "CEC adapter detected; this system has cec-ctl but not cec-client, "
                "so TV power commands are unavailable here."
                if found else
                "cec-ctl is installed, but no CEC adapter was reported."
            )
            self.cec_on_button.setEnabled(False)
            self.cec_standby_button.setEnabled(False)
            return
        self.cec_status.setText("HDMI-CEC controls unavailable: install cec-client or cec-ctl.")
        self.cec_on_button.setEnabled(False)
        self.cec_standby_button.setEnabled(False)

    def send_cec_command(self, command):
        cec_client = shutil.which("cec-client")
        if not cec_client:
            return
        result = self._run([cec_client, "-s", "-d", "1"], input_text=f"{command}\n", timeout=8)
        if self._is_success(result):
            self.cec_status.setText(f"HDMI-CEC command sent: {command}.")
        else:
            details = result.stderr.strip() if not isinstance(result, Exception) else str(result)
            self.cec_status.setText(f"HDMI-CEC command failed: {details}")
