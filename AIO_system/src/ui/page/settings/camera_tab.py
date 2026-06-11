"""
Camera connection settings tab.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QScrollArea,
    QComboBox,
)

from src.AI.cam.basler_manager import get_camera_count
from src.utils.config_util import ToggleButton, build_default_camera_connection_config
from src.utils.logger import log


def _merge_missing(dst, defaults):
    changed = False
    for key, value in defaults.items():
        if key not in dst:
            dst[key] = value
            changed = True
        elif isinstance(dst[key], dict) and isinstance(value, dict):
            changed = _merge_missing(dst[key], value) or changed
    return changed


class CameraTab(QWidget):
    """Camera connection controls."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._ensure_config()
        self.init_ui()

    def _ensure_config(self):
        defaults = build_default_camera_connection_config()
        config = self.app.config.setdefault("camera_connection_config", {})
        if not isinstance(config, dict):
            config = {}
            self.app.config["camera_connection_config"] = config
        _merge_missing(config, defaults)
        return config

    def _rgb_config(self):
        config = self._ensure_config()
        rgb_cameras = config.setdefault("rgb_cameras", {})
        if not isinstance(rgb_cameras, dict):
            rgb_cameras = {}
            config["rgb_cameras"] = rgb_cameras
        defaults = build_default_camera_connection_config()["rgb_cameras"]["0"]
        camera_config = rgb_cameras.setdefault("0", {})
        if not isinstance(camera_config, dict):
            camera_config = {}
            rgb_cameras["0"] = camera_config
        _merge_missing(camera_config, defaults)
        return camera_config

    def _hyper_config(self):
        config = self._ensure_config()
        defaults = build_default_camera_connection_config()["hyperspectral"]
        hyper_config = config.setdefault("hyperspectral", {})
        if not isinstance(hyper_config, dict):
            hyper_config = {}
            config["hyperspectral"] = hyper_config
        _merge_missing(hyper_config, defaults)
        return hyper_config

    def _hyper_section(self, section_name):
        hyper_config = self._hyper_config()
        defaults = build_default_camera_connection_config()["hyperspectral"].get(section_name, {})
        section = hyper_config.setdefault(section_name, {})
        if not isinstance(section, dict):
            section = {}
            hyper_config[section_name] = section
        if isinstance(defaults, dict):
            _merge_missing(section, defaults)
        return section

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_content.setMaximumWidth(1610)

        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setAlignment(Qt.AlignTop)
        scroll_layout.setSpacing(0)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addSpacing(25)

        self._create_rgb_section(scroll_layout)
        scroll_layout.addSpacing(30)
        self._create_hyperspectral_section(scroll_layout)
        scroll_layout.addSpacing(30)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        self.apply_styles()

    def _create_section(self, parent_layout, title, status_name):
        layout = QVBoxLayout()
        layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setAlignment(Qt.AlignLeft)

        title_label = QLabel(title)
        title_label.setObjectName("title_label")
        header_layout.addWidget(title_label)
        header_layout.addSpacing(15)

        status_label = QLabel("대기")
        status_label.setObjectName(status_name)
        status_label.setStyleSheet(
            """
            color: #616161;
            font-size: 14px;
            font-weight: normal;
            """
        )
        header_layout.addWidget(status_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)
        layout.addSpacing(15)

        contents_box = QFrame()
        contents_box.setObjectName("contents_box")

        contents_layout = QVBoxLayout(contents_box)
        contents_layout.setSpacing(25)
        contents_layout.setContentsMargins(30, 30, 30, 30)

        layout.addWidget(contents_box)
        parent_layout.addLayout(layout)
        return contents_layout, status_label

    def _create_rgb_section(self, parent_layout):
        rgb_config = self._rgb_config()
        contents_layout, self.rgb_status = self._create_section(
            parent_layout,
            "RGB 카메라 연결",
            "rgb_camera_status",
        )

        input_layout = QGridLayout()
        input_layout.setSpacing(10)

        self.rgb_enabled = self._add_toggle(input_layout, 0, "사용 여부", bool(rgb_config.get("enabled", True)))
        self.rgb_index = self._add_int_input(
            input_layout,
            1,
            "장치 인덱스",
            rgb_config.get("camera_index", 0),
            0,
            16,
        )
        self.rgb_ip = self._add_text_input(
            input_layout,
            2,
            "Basler IP",
            rgb_config.get("camera_ip", ""),
            "IP 미지정 시 인덱스로 연결",
        )
        self.rgb_fallback = self._add_toggle(
            input_layout,
            3,
            "웹캠 대체",
            bool(rgb_config.get("fallback_webcam", True)),
        )

        contents_layout.addLayout(input_layout)
        contents_layout.addLayout(
            self._button_layout(
                test_text="카메라 검색",
                test_func=self.on_test_rgb,
                apply_func=self.on_apply_rgb,
            )
        )

    def _create_hyperspectral_section(self, parent_layout):
        hyper_config = self._hyper_config()
        camera_config = self._hyper_section("camera")
        lumo_config = self._hyper_section("lumo")
        breeze_compat = self._hyper_section("breeze_compat")
        contents_layout, self.hyper_status = self._create_section(
            parent_layout,
            "초분광 카메라 연결 (Spectral Runtime)",
            "hyperspectral_camera_status",
        )

        input_layout = QGridLayout()
        input_layout.setSpacing(10)

        self.hyper_enabled = self._add_toggle(input_layout, 0, "사용 여부", bool(hyper_config.get("enabled", True)))
        self.hyper_mode = self._add_combo(
            input_layout,
            1,
            "연결 방식",
            [
                ("Breeze Runtime", "breeze"),
                ("Spectral Runtime (Lumo)", "spectral_runtime"),
            ],
            hyper_config.get("connection_mode", "breeze"),
        )
        self.lumo_provider_mode = self._add_combo(
            input_layout,
            2,
            "Provider Mode",
            [
                ("native", "native"),
            ],
            lumo_config.get("provider_mode", "native"),
        )
        self.lumo_auto_network = self._add_toggle(
            input_layout,
            3,
            "자동 네트워크 탐색",
            bool(lumo_config.get("auto_from_local_network", False)),
        )
        self.lumo_interface = self._add_text_input(
            input_layout,
            4,
            "Interface Name",
            lumo_config.get("interface_name", ""),
            "Windows 네트워크 어댑터 이름",
        )
        self.lumo_mac = self._add_text_input(
            input_layout,
            5,
            "MAC Address",
            lumo_config.get("mac_address", ""),
            "예: 70-F8-E7-B0-11-1B",
        )
        self.lumo_ip = self._add_text_input(
            input_layout,
            6,
            "Camera IP",
            lumo_config.get("ip_address", ""),
            "MAC 검색 시 자동 입력",
        )
        self.lumo_serial = self._add_text_input(
            input_layout,
            7,
            "Serial Number",
            lumo_config.get("serial_number", ""),
            "선택 입력",
        )
        self.lumo_device_index = self._add_int_input(
            input_layout,
            8,
            "Device Index",
            lumo_config.get("device_index", 0),
            0,
            32,
        )
        self.lumo_timeout = self._add_int_input(
            input_layout,
            9,
            "Grab Timeout",
            lumo_config.get("grab_timeout_ms", 5000),
            1,
            60000,
            unit="ms",
        )
        self.lumo_skip_scan = self._add_toggle(
            input_layout,
            10,
            "Skip Scan",
            bool(lumo_config.get("skip_scan", False)),
        )

        camera_title = QLabel("카메라 획득 설정")
        camera_title.setObjectName("title_label")

        acquisition_layout = QGridLayout()
        acquisition_layout.setSpacing(10)
        self.lumo_band_count = self._add_int_input(
            acquisition_layout,
            0,
            "Band Count",
            camera_config.get("band_count", 224),
            1,
            4096,
        )
        self.lumo_spatial_width = self._add_int_input(
            acquisition_layout,
            1,
            "Spatial Width",
            camera_config.get("spatial_width", 640),
            1,
            8192,
        )
        self.lumo_integration_time = self._add_int_input(
            acquisition_layout,
            2,
            "Integration Time",
            camera_config.get("integration_time_us", 4000),
            1,
            1000000,
            unit="us",
        )
        self.lumo_line_rate = self._add_float_input(
            acquisition_layout,
            3,
            "Line Rate",
            camera_config.get("line_rate_hz", 100.0),
            0.0,
            100000.0,
            3,
            unit="Hz",
        )
        self.lumo_rgb_bands = self._add_text_input(
            acquisition_layout,
            4,
            "RGB Bands",
            ",".join(str(v) for v in camera_config.get("rgb_bands", [32, 96, 160])),
            "예: 32,96,160",
        )
        self.lumo_mirror_line = self._add_toggle(
            acquisition_layout,
            5,
            "Mirror Line",
            bool(breeze_compat.get("mirror_line", False)),
        )

        contents_layout.addLayout(input_layout)
        contents_layout.addWidget(camera_title)
        contents_layout.addLayout(acquisition_layout)
        contents_layout.addLayout(
            self._button_layout(
                test_text="MAC 기준 찾기",
                test_func=self.on_test_hyperspectral,
                apply_func=self.on_apply_hyperspectral,
            )
        )

    def _add_toggle(self, parent_layout, row, label, checked):
        name_label = QLabel(label)
        name_label.setObjectName("name_label")
        parent_layout.addWidget(name_label, row, 0)

        toggle = ToggleButton(None, 126, 48, "사용", "미사용")
        toggle.setChecked(bool(checked))
        parent_layout.addWidget(toggle, row, 1)
        parent_layout.setColumnStretch(2, 1)
        return toggle

    def _add_text_input(self, parent_layout, row, label, value, placeholder, unit=""):
        name_label = QLabel(label)
        name_label.setObjectName("name_label")
        parent_layout.addWidget(name_label, row, 0)

        text_input = QLineEdit(str(value or ""))
        text_input.setPlaceholderText(placeholder)
        text_input.setObjectName("input_field")
        text_input.setFixedSize(600, 40)
        parent_layout.addWidget(text_input, row, 1)
        if unit:
            unit_label = QLabel(unit)
            unit_label.setObjectName("unit_label")
            parent_layout.addWidget(unit_label, row, 2)
        parent_layout.setColumnStretch(2, 1)
        return text_input

    def _add_int_input(self, parent_layout, row, label, value, min_val, max_val, unit=""):
        input_field = self._add_text_input(parent_layout, row, label, value, f"{min_val} ~ {max_val}", unit)
        input_field.setValidator(QIntValidator(int(min_val), int(max_val), parent_layout))
        return input_field

    def _add_float_input(self, parent_layout, row, label, value, min_val, max_val, decimals, unit=""):
        input_field = self._add_text_input(parent_layout, row, label, value, f"{min_val} ~ {max_val}", unit)
        validator = QDoubleValidator(float(min_val), float(max_val), int(decimals), parent_layout)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        input_field.setValidator(validator)
        return input_field

    def _add_combo(self, parent_layout, row, label, options, current_value):
        name_label = QLabel(label)
        name_label.setObjectName("name_label")
        parent_layout.addWidget(name_label, row, 0)

        combo = QComboBox()
        combo.setObjectName("input_field")
        combo.setFixedSize(600, 40)
        for text, value in options:
            combo.addItem(text, value)
        current = str(current_value or "")
        for index in range(combo.count()):
            if str(combo.itemData(index)) == current:
                combo.setCurrentIndex(index)
                break
        parent_layout.addWidget(combo, row, 1)
        parent_layout.setColumnStretch(2, 1)
        return combo

    def _button_layout(self, test_text, test_func, apply_func):
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.setSpacing(20)

        test_btn = QPushButton(test_text)
        test_btn.setObjectName("test_btn")
        test_btn.setFixedSize(498, 60)
        test_btn.clicked.connect(test_func)
        layout.addWidget(test_btn)

        apply_btn = QPushButton("적용")
        apply_btn.setObjectName("apply_btn")
        apply_btn.setFixedSize(498, 60)
        apply_btn.clicked.connect(apply_func)
        layout.addWidget(apply_btn)
        return layout

    def _save_app_config(self):
        if hasattr(self.app, "_save_config"):
            self.app._save_config()

    def on_apply_rgb(self):
        try:
            config = self._rgb_config()
            config["enabled"] = bool(self.rgb_enabled.isChecked())
            config["camera_index"] = self._read_int_input(self.rgb_index, "RGB Device Index", 0, minimum=0)
            config["camera_ip"] = self.rgb_ip.text().strip()
            config["fallback_webcam"] = bool(self.rgb_fallback.isChecked())
            self._save_app_config()
            self.rgb_status.setText("적용됨")
            log("[INFO] RGB camera connection settings saved")
            self.app.on_popup("info", "카메라 설정", "RGB 카메라 연결 설정이 적용되었습니다.")
        except ValueError:
            self.rgb_status.setText("입력 오류")
            self.app.on_popup("warning", "카메라 설정", "RGB 카메라 입력값을 확인해주세요.")

    def on_apply_hyperspectral(self):
        try:
            config = self._hyper_config()
            camera_config = self._hyper_section("camera")
            lumo_config = self._hyper_section("lumo")
            breeze_compat = self._hyper_section("breeze_compat")
            config["enabled"] = bool(self.hyper_enabled.isChecked())
            config["connection_mode"] = str(self.hyper_mode.currentData() or "breeze")

            lumo_config["provider_mode"] = str(self.lumo_provider_mode.currentData() or "native")
            lumo_config["auto_from_local_network"] = bool(self.lumo_auto_network.isChecked())
            lumo_config["interface_name"] = self.lumo_interface.text().strip()
            lumo_config["mac_address"] = self.lumo_mac.text().strip()
            lumo_config["ip_address"] = self.lumo_ip.text().strip()
            lumo_config["serial_number"] = self.lumo_serial.text().strip()
            lumo_config["device_index"] = self._read_int_input(self.lumo_device_index, "Device Index", 0, minimum=0)
            lumo_config["grab_timeout_ms"] = self._read_int_input(self.lumo_timeout, "Grab Timeout", 5000, minimum=1)
            lumo_config["skip_scan"] = bool(self.lumo_skip_scan.isChecked())

            camera_config["band_count"] = self._read_int_input(self.lumo_band_count, "Band Count", 224, minimum=1)
            camera_config["spatial_width"] = self._read_int_input(self.lumo_spatial_width, "Spatial Width", 640, minimum=1)
            camera_config["integration_time_us"] = self._read_int_input(
                self.lumo_integration_time,
                "Integration Time",
                4000,
                minimum=1,
            )
            camera_config["line_rate_hz"] = self._read_float_input(self.lumo_line_rate, "Line Rate", 100.0, minimum=0.0)
            camera_config["rgb_bands"] = self._parse_rgb_bands(self.lumo_rgb_bands.text())
            breeze_compat["mirror_line"] = bool(self.lumo_mirror_line.isChecked())

            self._save_app_config()
            self.hyper_status.setText("적용됨")
            log("[INFO] hyperspectral camera connection settings saved")
            self.app.on_popup("info", "카메라 설정", "초분광 카메라 연결 설정이 적용되었습니다.")
        except ValueError as e:
            self.hyper_status.setText("입력 오류")
            self.app.on_popup("warning", "카메라 설정", f"초분광 카메라 입력값을 확인해주세요.\n{e}")

    def on_test_rgb(self):
        try:
            count = get_camera_count()
            index = self._read_int_input(self.rgb_index, "RGB Device Index", 0, minimum=0)
            if count > index:
                message = f"카메라 {count}대 확인, 인덱스 {index} 사용 가능"
                self.rgb_status.setText("확인됨")
                self.app.on_popup("info", "카메라 검색", message)
            else:
                message = f"카메라 {count}대 확인, 인덱스 {index} 사용 불가"
                self.rgb_status.setText("확인 필요")
                self.app.on_popup("warning", "카메라 검색", message)
            log(f"[INFO] RGB camera search: {message}")
        except Exception as e:
            self.rgb_status.setText("검색 실패")
            log(f"[ERROR] RGB camera search failed: {e}")
            self.app.on_popup("warning", "카메라 검색", f"카메라 검색 실패: {e}")

    def on_test_hyperspectral(self):
        try:
            self._parse_rgb_bands(self.lumo_rgb_bands.text())
            self._read_int_input(self.lumo_device_index, "Device Index", 0, minimum=0)
            self._read_int_input(self.lumo_timeout, "Grab Timeout", 5000, minimum=1)
        except ValueError as e:
            self.hyper_status.setText("입력 오류")
            self.app.on_popup("warning", "Lumo 장치 확인", str(e))
            return

        mac_address = self.lumo_mac.text().strip()
        interface_name = self.lumo_interface.text().strip() or None
        network = None
        devices = []
        errors = []

        if mac_address:
            try:
                network = self._find_lumo_network_by_mac(mac_address, interface_name)
            except Exception as e:
                errors.append(f"네트워크 검색 실패: {e}")
                log(f"[WARNING] Lumo network search failed: {e}")

        try:
            devices = self._list_lumo_devices()
        except Exception as e:
            errors.append(f"Native 장치 검색 실패: {e}")
            log(f"[WARNING] Lumo device check failed: {e}")

        if network:
            self.lumo_ip.setText(str(network.get("ip_address", "")))
            self.lumo_interface.setText(str(network.get("interface_alias", "")))
            self.lumo_auto_network.setChecked(True)

        device_index = self._find_lumo_device_index(
            devices,
            mac_address=mac_address,
            ip_address=str(network.get("ip_address", "")) if network else self.lumo_ip.text().strip(),
        )
        if device_index is not None:
            self.lumo_device_index.setText(str(device_index))

        if network or devices:
            self.hyper_status.setText("확인됨")
            message = self._build_lumo_search_message(network, devices, device_index, errors)
            self.app.on_popup("info", "Lumo MAC 검색", message)
        else:
            self.hyper_status.setText("확인 필요")
            message = "확인된 Lumo 장치가 없습니다."
            if errors:
                message += "\n" + "\n".join(errors)
            self.app.on_popup("warning", "Lumo MAC 검색", message)
        log(f"[INFO] Lumo network: {network}, devices: {devices}")

    def _parse_rgb_bands(self, text):
        try:
            values = [int(item.strip()) for item in str(text).split(",") if item.strip()]
        except ValueError as exc:
            raise ValueError("RGB Bands는 예: 32,96,160 형식으로 입력해주세요.") from exc
        if len(values) != 3:
            raise ValueError("RGB Bands는 3개 값을 입력해야 합니다.")
        return values

    def _read_int_input(self, input_field, label, default, *, minimum=None):
        text = input_field.text().strip()
        if not text:
            value = int(default)
            input_field.setText(str(value))
            return value
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{label} 값은 정수로 입력해주세요.") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{label} 값은 {minimum} 이상이어야 합니다.")
        return value

    def _read_float_input(self, input_field, label, default, *, minimum=None):
        text = input_field.text().strip()
        if not text:
            value = float(default)
            input_field.setText(str(value))
            return value
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} 값은 숫자로 입력해주세요.") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{label} 값은 {minimum} 이상이어야 합니다.")
        return value

    def _list_lumo_devices(self):
        self._ensure_lumo_module_path()
        from specim_lumo_camera_kit import SpecimLumoCameraModule
        devices = SpecimLumoCameraModule.list_devices()
        return devices if isinstance(devices, list) else []

    def _find_lumo_network_by_mac(self, mac_address, interface_name=None):
        self._ensure_lumo_module_path()
        from specim_lumo_camera_kit import (
            find_lumo_neighbor_by_mac,
            list_local_network_adapters,
            normalize_mac_address,
        )

        adapters = list_local_network_adapters(timeout_seconds=5.0)
        local_ips = [
            ip
            for adapter in adapters
            for ip in adapter.ipv4_addresses
            if adapter.media_connected and ip
        ]
        neighbor = find_lumo_neighbor_by_mac(
            mac_address=mac_address,
            interface_name=interface_name,
            local_ipv4_addresses=local_ips,
            timeout_seconds=5.0,
        )
        if neighbor is None and interface_name:
            neighbor = find_lumo_neighbor_by_mac(
                mac_address=mac_address,
                interface_name=None,
                local_ipv4_addresses=local_ips,
                timeout_seconds=5.0,
            )
        if neighbor is None:
            return None

        adapter = next((item for item in adapters if item.name == neighbor.interface_alias), None)
        return {
            "ip_address": neighbor.ip_address,
            "interface_alias": neighbor.interface_alias,
            "mac_address": normalize_mac_address(mac_address),
            "neighbor_state": neighbor.state,
            "local_ipv4_addresses": list(adapter.ipv4_addresses) if adapter else local_ips,
        }

    def _find_lumo_device_index(self, devices, *, mac_address="", ip_address=""):
        if not isinstance(devices, list):
            return None
        target_mac = self._compact_mac(mac_address)
        target_ip = str(ip_address or "").strip()
        for fallback_index, device in enumerate(devices):
            if not isinstance(device, dict):
                continue
            device_macs = [
                device.get("mac_address"),
                device.get("target_mac_address"),
                device.get("link_layer_address"),
                device.get("mac"),
            ]
            if target_mac and any(self._compact_mac(value) == target_mac for value in device_macs):
                return self._device_index(device, fallback_index)

        for fallback_index, device in enumerate(devices):
            if not isinstance(device, dict):
                continue
            device_ips = [
                device.get("ip_address"),
                device.get("ip"),
                device.get("camera_ip"),
            ]
            if target_ip and any(str(value or "").strip() == target_ip for value in device_ips):
                return self._device_index(device, fallback_index)

        if len(devices) == 1:
            return self._device_index(devices[0], 0)
        return None

    def _build_lumo_search_message(self, network, devices, device_index, errors):
        lines = []
        if network:
            lines.append(f"IP: {network.get('ip_address')}")
            lines.append(f"이더넷: {network.get('interface_alias')}")
            lines.append(f"MAC: {network.get('mac_address')}")
        if device_index is not None:
            lines.append(f"Device Index: {device_index}")
        lines.append(f"Native 장치: {len(devices) if isinstance(devices, list) else 0}대")
        if errors:
            lines.extend(errors)
        return "\n".join(lines)

    def _ensure_lumo_module_path(self):
        module_root = Path(__file__).resolve().parents[3] / "module" / "specim_lumo_camera_kit"
        module_path = str(module_root)
        if module_root.exists() and module_path not in sys.path:
            sys.path.insert(0, module_path)

    @staticmethod
    def _compact_mac(value):
        return "".join(ch for ch in str(value or "") if ch.isalnum()).lower()

    @staticmethod
    def _device_index(device, fallback_index):
        for key in ("device_index", "index", "id", "device_id"):
            value = device.get(key) if isinstance(device, dict) else None
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return int(fallback_index)

    def apply_styles(self):
        self.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background-color: transparent;
            }

            QScrollBar:vertical {
                border: none;
                background: #F3F4F6;
                width: 5px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background: #E2E2E2;
                min-height: 20px;
                border-radius: 5px;
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            #scroll_content {
                background-color: transparent;
            }

            #contents_box {
                background-color: #FAFAFA;
                border: 1px solid #E2E2E2;
                border-radius: 7px;
            }

            #title_label {
                color: #000000;
                font-size: 16px;
                font-weight: medium;
            }

            #name_label {
                color: #4B4B4B;
                font-size: 14px;
                font-weight: normal;
            }

            #input_field {
                background-color: #FFFFFF;
                border: 1px solid #D4D4D4;
                border-radius: 4px;
                padding: 10;
                color: #000000;
                font-size: 14px;
                font-weight: normal;
            }

            #input_field:focus {
                border-color: #AAAAAA;
            }

            QComboBox#input_field {
                padding-left: 10;
            }

            #apply_btn {
                background-color: #353535;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #apply_btn:hover {
                background-color: #8b949e;
            }

            #test_btn {
                background-color: #54B9DE;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                font-weight: medium;
            }

            #test_btn:hover {
                background-color: #58A6FF;
            }
            """
        )
