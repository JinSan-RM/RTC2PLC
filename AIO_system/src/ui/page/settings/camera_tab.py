"""
Camera connection settings tab.
"""
import copy
import json
import sys
from pathlib import Path

import numpy as np

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QScrollArea,
    QComboBox, QFileDialog,
)

from src.AI.cam.basler_manager import get_camera_count
from src.utils.config_util import (
    DEFAULT_LUMO_MAC_ADDRESS,
    DEFAULT_SPECTRAL_MODEL_BUNDLE_PATH,
    DEFAULT_SPECTRAL_MODEL_PATH,
    ToggleButton,
    build_default_camera_connection_config,
)
from src.utils.lumo_camera_service import (
    find_lumo_device_index,
    find_lumo_network,
    is_low_quality_lumo_device,
    list_lumo_devices,
    sanitize_lumo_interface_name,
)
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


class SpectralInferenceTestWorker(QThread):
    """Run a short replay inference test without blocking the settings UI."""

    result_ready = Signal(object)
    error_ready = Signal(str)

    def __init__(self, *, model_info, session_dir, app_config, max_frames=256):
        super().__init__()
        self.model_info = dict(model_info)
        self.session_dir = Path(session_dir)
        self.app_config = copy.deepcopy(app_config or {})
        self.max_frames = int(max_frames)

    def run(self):
        try:
            kit_root = Path(__file__).resolve().parents[3] / "module" / "spectral_runtime_full_kit"
            kit_path = str(kit_root)
            if kit_path not in sys.path:
                sys.path.insert(0, kit_path)

            from runtime.calibration import RuntimeCalibrationContext
            from runtime_module import SpectralRuntimeModule

            model_path = Path(self.model_info["model_path"]).resolve()
            input_kind = str(self.model_info.get("input_kind") or "raw").strip().lower()
            reference_paths = dict(self.model_info.get("reference_paths") or {})

            calibration_context = None
            if input_kind in {"reflectance", "absorbance"}:
                dark_path = Path(reference_paths.get("dark_mean", "")).resolve()
                white_path = Path(reference_paths.get("white_mean", "")).resolve()
                dark = np.load(dark_path, allow_pickle=False).astype(np.float32, copy=False)
                white = np.load(white_path, allow_pickle=False).astype(np.float32, copy=False)
                calibration_context = RuntimeCalibrationContext(
                    input_kind=input_kind,
                    dark_reference=np.ascontiguousarray(dark),
                    white_reference=np.ascontiguousarray(white),
                    reference_paths={
                        "dark_mean": str(dark_path),
                        "white_mean": str(white_path),
                    },
                )

            output_root = kit_root / "reports" / "ui-inference-test" / input_kind
            module = SpectralRuntimeModule.from_model(
                model_path=model_path,
                app_config=self.app_config,
                output_root=output_root,
                calibration_context=calibration_context,
            )
            params = module.default_params().with_updates(max_frames=max(1, self.max_frames), dashboard=False)
            result = module.run_replay(
                session_dir=self.session_dir,
                params=params,
                output_label_prefix=f"ui-{input_kind}-inference-test",
            )
            self.result_ready.emit(
                {
                    "ok": bool(result.ok),
                    "return_code": int(result.return_code),
                    "input_kind": input_kind,
                    "model_path": str(model_path),
                    "session_dir": str(self.session_dir.resolve()),
                    "summary_path": str(result.summary_path),
                    "events_path": str(result.events_path),
                    "screen_outputs": result.screen_outputs(),
                    "window_count": int(result.runtime_summary.get("window_count", 0)),
                    "total_objects": int(result.runtime_summary.get("total_objects", 0)),
                    "objects_per_class": dict(result.runtime_summary.get("objects_per_class", {})),
                    "calibration": result.summary_payload.get("calibration", {}),
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.error_ready.emit(str(exc))


class CameraTab(QWidget):
    """Camera connection controls."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.inference_test_worker = None
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
        inference_config = self._hyper_section("inference")
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
            sanitize_lumo_interface_name(lumo_config.get("interface_name")) or "",
            "Windows 네트워크 어댑터 이름",
        )
        self.lumo_mac = self._add_text_input(
            input_layout,
            5,
            "MAC Address (고정)",
            DEFAULT_LUMO_MAC_ADDRESS,
            DEFAULT_LUMO_MAC_ADDRESS,
        )
        self.lumo_mac.setReadOnly(True)
        self.lumo_mac.setToolTip("고정된 Lumo 카메라 MAC 주소입니다.")
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

        model_title = QLabel("초분광 추론 모델")
        model_title.setObjectName("title_label")

        model_layout = QGridLayout()
        model_layout.setSpacing(10)
        self.model_inference_enabled = self._add_toggle(
            model_layout,
            0,
            "모델 추론",
            bool(inference_config.get("enabled", True)),
        )
        initial_model_path = (
            inference_config.get("model_path")
            or inference_config.get("model_bundle_path")
            or DEFAULT_SPECTRAL_MODEL_PATH
        )
        self.model_bundle_path = self._add_text_input(
            model_layout,
            1,
            "Model Path",
            initial_model_path,
            "raw는 .pkl, reflectance는 .pkl + reference",
        )
        browse_btn = QPushButton("경로 선택")
        browse_btn.setObjectName("test_btn")
        browse_btn.setFixedSize(160, 40)
        browse_btn.clicked.connect(self.on_browse_model_bundle)
        model_layout.addWidget(browse_btn, 1, 2)

        self.model_use_bundle_params = self._add_toggle(
            model_layout,
            2,
            "Bundle Params",
            bool(inference_config.get("use_bundle_runtime_params", True)),
        )
        self.model_input_kind = self._add_combo(
            model_layout,
            3,
            "Model Input Kind",
            [
                ("raw", "raw"),
                ("reflectance", "reflectance"),
                ("absorbance", "absorbance"),
            ],
            inference_config.get("model_input_kind", "raw"),
        )
        self.model_input_kind.currentIndexChanged.connect(self.on_model_input_kind_changed)
        self.model_bundle_path.textChanged.connect(lambda *_args: self._sync_reference_controls())

        self.model_reference_mode = self._add_text_input(
            model_layout,
            4,
            "Reference 사용",
            "사용" if bool(inference_config.get("reference_required", False)) else "미사용",
            "모델 종류에 따라 자동",
        )
        self.model_reference_mode.setReadOnly(True)

        reference_paths = inference_config.get("reference_paths", {})
        if not isinstance(reference_paths, dict):
            reference_paths = {}
        self.dark_reference_path = self._add_text_input(
            model_layout,
            5,
            "Dark Reference Path",
            reference_paths.get("dark_mean", ""),
            "dark reference 폴더 또는 mean.npy",
        )
        self.dark_ref_btn = QPushButton("경로 선택")
        self.dark_ref_btn.setObjectName("test_btn")
        self.dark_ref_btn.setFixedSize(160, 40)
        self.dark_ref_btn.clicked.connect(
            lambda: self.on_browse_reference_path(self.dark_reference_path, "Dark reference 선택")
        )
        model_layout.addWidget(self.dark_ref_btn, 5, 2)

        self.white_reference_path = self._add_text_input(
            model_layout,
            6,
            "White Reference Path",
            reference_paths.get("white_mean", ""),
            "white reference 폴더 또는 mean.npy",
        )
        self.white_ref_btn = QPushButton("경로 선택")
        self.white_ref_btn.setObjectName("test_btn")
        self.white_ref_btn.setFixedSize(160, 40)
        self.white_ref_btn.clicked.connect(
            lambda: self.on_browse_reference_path(self.white_reference_path, "White reference 선택")
        )
        model_layout.addWidget(self.white_ref_btn, 6, 2)

        model_check_btn = QPushButton("모델 확인")
        model_check_btn.setObjectName("test_btn")
        model_check_btn.setFixedSize(375, 50)
        model_check_btn.clicked.connect(self.on_test_model_bundle)
        model_layout.addWidget(model_check_btn, 7, 1)

        self.inference_test_btn = QPushButton("추론 테스트")
        self.inference_test_btn.setObjectName("test_btn")
        self.inference_test_btn.setFixedSize(375, 50)
        self.inference_test_btn.clicked.connect(self.on_test_model_inference)
        model_layout.addWidget(self.inference_test_btn, 7, 2)
        self._pin_model_layout_left(model_layout)
        self._sync_reference_controls()

        contents_layout.addLayout(input_layout)
        contents_layout.addWidget(camera_title)
        contents_layout.addLayout(acquisition_layout)
        contents_layout.addWidget(model_title)
        contents_layout.addLayout(model_layout)
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

    @staticmethod
    def _pin_model_layout_left(layout):
        for column in (0, 1, 2):
            layout.setColumnStretch(column, 0)
        layout.setColumnStretch(3, 1)

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
            inference_config = self._hyper_section("inference")
            config["enabled"] = bool(self.hyper_enabled.isChecked())
            config["connection_mode"] = str(self.hyper_mode.currentData() or "breeze")

            lumo_config["provider_mode"] = str(self.lumo_provider_mode.currentData() or "native")
            lumo_config["auto_from_local_network"] = bool(self.lumo_auto_network.isChecked())
            interface_name = sanitize_lumo_interface_name(self.lumo_interface.text()) or ""
            lumo_config["interface_name"] = interface_name
            self.lumo_interface.setText(interface_name)
            lumo_config["mac_address"] = DEFAULT_LUMO_MAC_ADDRESS
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

            inference_enabled = bool(self.model_inference_enabled.isChecked())
            inference_config["enabled"] = inference_enabled
            model_value = self.model_bundle_path.text().strip()
            if inference_enabled:
                model_info = self._validate_model_input_path(
                    model_value,
                    model_input_kind=self._selected_model_input_kind(),
                    dark_reference_path=self.dark_reference_path.text().strip(),
                    white_reference_path=self.white_reference_path.text().strip(),
                )
                model_value = str(model_info["display_path"])
                inference_config["model_path"] = str(model_info["model_path"])
                inference_config["model_bundle_path"] = str(model_info["bundle_path"] or "")
                inference_config["model_input_kind"] = str(model_info["input_kind"])
                inference_config["reference_required"] = bool(model_info["reference_required"])
                inference_config["model_source"] = str(model_info["source"])
                inference_config["use_bundle_runtime_params"] = (
                    bool(self.model_use_bundle_params.isChecked()) and model_info["source"] == "bundle"
                )
                inference_config["reference_paths"] = dict(model_info["reference_paths"])
                self.model_reference_mode.setText("사용" if model_info["reference_required"] else "미사용")
                self._set_reference_inputs(model_info["reference_paths"])
            else:
                inference_config["model_path"] = ""
                inference_config["model_bundle_path"] = ""
                inference_config["model_input_kind"] = self._selected_model_input_kind()
                inference_config["reference_required"] = self._selected_model_input_kind() in {"reflectance", "absorbance"}
                inference_config["reference_paths"] = (
                    self._reference_input_values() if inference_config["reference_required"] else {}
                )
                inference_config["model_source"] = "disabled"
                inference_config["use_bundle_runtime_params"] = False
            self.model_bundle_path.setText(model_value)
            self._sync_reference_controls()

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

        mac_address = DEFAULT_LUMO_MAC_ADDRESS
        self.lumo_mac.setText(DEFAULT_LUMO_MAC_ADDRESS)
        interface_name = sanitize_lumo_interface_name(self.lumo_interface.text())
        if self.lumo_interface.text().strip() and interface_name is None:
            self.lumo_interface.setText("")
        network = None
        network_candidates = []
        devices = []
        errors = []

        try:
            network, network_candidates = self._find_lumo_network(mac_address, interface_name)
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
            self.lumo_interface.setText(sanitize_lumo_interface_name(network.get("interface_alias")) or "")
            self.lumo_mac.setText(DEFAULT_LUMO_MAC_ADDRESS)
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
            message = self._build_lumo_search_message(network, devices, device_index, errors, network_candidates)
            self.app.on_popup("info", "Lumo MAC 검색", message)
        else:
            self.hyper_status.setText("확인 필요")
            message = "확인된 Lumo 장치가 없습니다."
            if errors:
                message += "\n" + "\n".join(errors)
            self.app.on_popup("warning", "Lumo MAC 검색", message)
        log(f"[INFO] Lumo network: {network}, candidates: {network_candidates}, devices: {devices}")

    def on_browse_model_bundle(self):
        current = self.model_bundle_path.text().strip() or DEFAULT_SPECTRAL_MODEL_PATH
        current_path = self._resolve_path(current)
        if current_path.is_file():
            current_path = current_path.parent
        start_dir = str(current_path if current_path.exists() else Path(DEFAULT_SPECTRAL_MODEL_PATH).parent)
        selected = ""
        if self._selected_model_input_kind() == "raw":
            selected, _filter = QFileDialog.getOpenFileName(
                self,
                "raw 모델 파일 선택",
                start_dir,
                "PLS-DA model (*.pkl);;All files (*.*)",
            )
        else:
            selected, _filter = QFileDialog.getOpenFileName(
                self,
                "초분광 모델 파일 선택",
                start_dir,
                "PLS-DA model (*.pkl);;Model bundle manifest (model_bundle.json);;All files (*.*)",
            )
        if selected:
            self.model_bundle_path.setText(selected)

    def on_browse_reference_path(self, input_field, title):
        current = input_field.text().strip()
        if current:
            current_path = self._resolve_path(current)
            if current_path.is_file():
                current_path = current_path.parent
        else:
            bundle_path = self._resolve_path(self.model_bundle_path.text().strip() or DEFAULT_SPECTRAL_MODEL_BUNDLE_PATH)
            current_path = bundle_path if bundle_path.exists() else Path(DEFAULT_SPECTRAL_MODEL_BUNDLE_PATH)

        selected = QFileDialog.getExistingDirectory(
            self,
            title,
            str(current_path if current_path.exists() else Path(DEFAULT_SPECTRAL_MODEL_BUNDLE_PATH)),
        )
        if selected:
            input_field.setText(selected)

    def on_model_input_kind_changed(self, *_args):
        self._sync_reference_controls()

    def on_test_model_bundle(self):
        try:
            model_info = self._validate_model_input_path(
                self.model_bundle_path.text().strip(),
                model_input_kind=self._selected_model_input_kind(),
                dark_reference_path=self.dark_reference_path.text().strip(),
                white_reference_path=self.white_reference_path.text().strip(),
            )
        except ValueError as e:
            self.hyper_status.setText("모델 확인 실패")
            self.app.on_popup("warning", "초분광 모델", str(e))
            return

        self.model_bundle_path.setText(str(model_info["display_path"]))
        self.model_reference_mode.setText("사용" if model_info["reference_required"] else "미사용")
        self._set_reference_inputs(model_info["reference_paths"])
        self._sync_reference_controls()
        self.hyper_status.setText("모델 확인됨")
        self.app.on_popup(
            "info",
            "초분광 모델",
            f"Source: {model_info['source']}\n"
            f"Model: {model_info['model_path'].name}\n"
            f"Input: {model_info['input_kind']}\n"
            f"Reference: {'required' if model_info['reference_required'] else 'not required'}",
        )
        log(f"[INFO] spectral model verified: {model_info}")

    def on_test_model_inference(self):
        worker = self.inference_test_worker
        if worker is not None and worker.isRunning():
            self.app.on_popup("warning", "초분광 추론 테스트", "이미 추론 테스트가 실행 중입니다.")
            return

        try:
            model_info = self._validate_model_input_path(
                self.model_bundle_path.text().strip(),
                model_input_kind=self._selected_model_input_kind(),
                dark_reference_path=self.dark_reference_path.text().strip(),
                white_reference_path=self.white_reference_path.text().strip(),
            )
        except ValueError as e:
            self.hyper_status.setText("모델 확인 실패")
            self.app.on_popup("warning", "초분광 추론 테스트", str(e))
            return

        selected = QFileDialog.getExistingDirectory(
            self,
            "추론 테스트 raw 세션 선택",
            str(self._default_replay_session_root()),
        )
        if not selected:
            return

        try:
            session_dir = self._validate_replay_session_path(selected)
        except ValueError as e:
            self.hyper_status.setText("세션 확인 실패")
            self.app.on_popup("warning", "초분광 추론 테스트", str(e))
            return

        self.inference_test_btn.setEnabled(False)
        self.hyper_status.setText("추론 테스트 중")
        worker = SpectralInferenceTestWorker(
            model_info=model_info,
            session_dir=session_dir,
            app_config=self.app.config,
            max_frames=256,
        )
        self.inference_test_worker = worker
        worker.result_ready.connect(self.on_inference_test_result)
        worker.error_ready.connect(self.on_inference_test_error)
        worker.finished.connect(self.on_inference_test_finished)
        worker.start()

    def on_inference_test_result(self, result):
        ok = bool(result.get("ok", False))
        status_text = "추론 테스트 완료" if ok else "추론 테스트 실패"
        self.hyper_status.setText(status_text)

        objects_per_class = result.get("objects_per_class", {})
        class_text = ", ".join(f"{name}: {count}" for name, count in objects_per_class.items()) or "없음"
        message = (
            f"Input: {result.get('input_kind')}\n"
            f"Windows: {result.get('window_count')}\n"
            f"Objects: {result.get('total_objects')}\n"
            f"Classes: {class_text}\n"
            f"Summary: {result.get('summary_path')}\n"
            f"Events: {result.get('events_path')}"
        )
        if ok:
            self.app.on_popup("info", "초분광 추론 테스트", message)
            log(f"[INFO] spectral inference test passed: {result}")
        else:
            self.app.on_popup("warning", "초분광 추론 테스트", message)
            log(f"[WARNING] spectral inference test failed: {result}")

    def on_inference_test_error(self, message):
        self.hyper_status.setText("추론 테스트 실패")
        self.app.on_popup("warning", "초분광 추론 테스트", message)
        log(f"[ERROR] spectral inference test failed: {message}")

    def on_inference_test_finished(self):
        self.inference_test_worker = None
        self.inference_test_btn.setEnabled(True)
        self._sync_reference_controls()

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

    def _validate_model_input_path(
        self,
        value,
        *,
        model_input_kind=None,
        dark_reference_path="",
        white_reference_path="",
    ):
        if not value:
            raise ValueError("Model Path를 입력해주세요.")

        selected_path = self._resolve_path(value)
        requested_input_kind = self._normalize_model_input_kind(model_input_kind)
        if requested_input_kind == "raw" and not (
            selected_path.is_file() and selected_path.suffix.lower() == ".pkl"
        ):
            raise ValueError("raw 입력 타입은 .pkl 모델 파일만 선택할 수 있습니다.")

        if selected_path.is_file() and selected_path.suffix.lower() == ".pkl":
            return self._validate_direct_model_path(
                selected_path,
                model_input_kind=requested_input_kind,
                dark_reference_path=dark_reference_path,
                white_reference_path=white_reference_path,
            )

        bundle_path = selected_path
        if bundle_path.is_file() and bundle_path.name == "model_bundle.json":
            bundle_path = bundle_path.parent
        manifest_path = bundle_path / "model_bundle.json"
        if not manifest_path.exists():
            raise ValueError(
                "모델은 .pkl 파일이거나 model_bundle.json이 있는 폴더여야 합니다.\n"
                f"{selected_path}"
            )

        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except Exception as exc:
            raise ValueError(f"model_bundle.json을 읽을 수 없습니다.\n{exc}") from exc

        model_section = manifest.get("model", {}) if isinstance(manifest, dict) else {}
        model_relpath = model_section.get("path") if isinstance(model_section, dict) else None
        if not model_relpath:
            raise ValueError("model_bundle.json에 model.path가 없습니다.")
        model_path = (bundle_path / str(model_relpath)).resolve()
        if not model_path.exists():
            raise ValueError(f"모델 파일을 찾을 수 없습니다.\n{model_path}")

        training_metadata = manifest.get("training_metadata", {}) if isinstance(manifest, dict) else {}
        if not isinstance(training_metadata, dict):
            training_metadata = {}
        manifest_input_kind = str(
            training_metadata.get(
                "model_input_kind",
                training_metadata.get("input_kind", training_metadata.get("training_input_kind", "raw")),
            )
            or "raw"
        ).strip().lower()
        input_kind = self._normalize_model_input_kind(model_input_kind or manifest_input_kind)
        if input_kind not in {"raw", "reflectance", "absorbance"}:
            raise ValueError(f"지원하지 않는 model input kind입니다: {input_kind}")

        bundle_reference_paths = self._bundle_reference_paths(bundle_path, manifest)
        reference_paths = {}
        if input_kind in {"reflectance", "absorbance"}:
            reference_paths["dark_mean"] = str(
                self._resolve_reference_mean_path(
                    dark_reference_path,
                    fallback=bundle_reference_paths.get("dark_mean", ""),
                    side="dark",
                )
            )
            reference_paths["white_mean"] = str(
                self._resolve_reference_mean_path(
                    white_reference_path,
                    fallback=bundle_reference_paths.get("white_mean", ""),
                    side="white",
                )
            )

        return {
            "source": "bundle",
            "display_path": bundle_path.resolve(),
            "bundle_path": bundle_path.resolve(),
            "manifest_path": manifest_path.resolve(),
            "model_path": model_path,
            "bundle_id": str(manifest.get("bundle_id", bundle_path.name)),
            "input_kind": input_kind,
            "manifest_input_kind": manifest_input_kind,
            "reference_required": input_kind in {"reflectance", "absorbance"},
            "reference_paths": reference_paths,
            "bundle_reference_paths": bundle_reference_paths,
        }

    def _validate_direct_model_path(
        self,
        model_path,
        *,
        model_input_kind=None,
        dark_reference_path="",
        white_reference_path="",
    ):
        model_path = Path(model_path).resolve()
        if not model_path.exists():
            raise ValueError(f"모델 파일을 찾을 수 없습니다.\n{model_path}")
        if model_path.suffix.lower() != ".pkl":
            raise ValueError(f"직접 선택 모델은 .pkl 파일이어야 합니다.\n{model_path}")

        input_kind = self._normalize_model_input_kind(model_input_kind)
        reference_paths = {}
        if input_kind in {"reflectance", "absorbance"}:
            reference_paths["dark_mean"] = str(
                self._resolve_reference_mean_path(dark_reference_path, side="dark")
            )
            reference_paths["white_mean"] = str(
                self._resolve_reference_mean_path(white_reference_path, side="white")
            )

        return {
            "source": "model_file",
            "display_path": model_path,
            "bundle_path": "",
            "manifest_path": None,
            "model_path": model_path,
            "bundle_id": "",
            "input_kind": input_kind,
            "manifest_input_kind": "",
            "reference_required": input_kind in {"reflectance", "absorbance"},
            "reference_paths": reference_paths,
            "bundle_reference_paths": {},
        }

    def _validate_replay_session_path(self, value):
        session_dir = self._resolve_path(value)
        if not session_dir.exists() or not session_dir.is_dir():
            raise ValueError(f"세션 폴더를 찾을 수 없습니다.\n{session_dir}")
        required_files = ("manifest.json", "lines.npy", "timestamps.npy")
        missing = [name for name in required_files if not (session_dir / name).exists()]
        if missing:
            raise ValueError(
                "추론 테스트 세션에는 manifest.json, lines.npy, timestamps.npy가 필요합니다.\n"
                f"누락: {', '.join(missing)}\n{session_dir}"
            )
        return session_dir

    def _default_replay_session_root(self):
        candidates = [
            Path(__file__).resolve().parents[6] / "spectral-runtime" / "data" / "projects" / "default" / "raw",
            Path(DEFAULT_SPECTRAL_MODEL_PATH).parent,
            Path.cwd(),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return Path.cwd().resolve()

    def _selected_model_input_kind(self):
        value = self.model_input_kind.currentData()
        return self._normalize_model_input_kind(value)

    def _normalize_model_input_kind(self, value):
        kind = str(value or "raw").strip().lower()
        if kind not in {"raw", "reflectance", "absorbance"}:
            return "raw"
        return kind

    def _sync_reference_controls(self):
        reference_required = self._selected_model_input_kind() in {"reflectance", "absorbance"}
        self.model_reference_mode.setText("사용" if reference_required else "미사용")
        self.model_use_bundle_params.setEnabled(self._is_bundle_path_selected())
        for widget in (
            self.dark_reference_path,
            self.white_reference_path,
            self.dark_ref_btn,
            self.white_ref_btn,
        ):
            widget.setEnabled(reference_required)

    def _is_bundle_path_selected(self):
        value = self.model_bundle_path.text().strip()
        if not value:
            return False
        if self._selected_model_input_kind() == "raw":
            return False
        path = self._resolve_path(value)
        return path.is_dir() or path.name == "model_bundle.json"

    def _set_reference_inputs(self, reference_paths):
        if not isinstance(reference_paths, dict):
            reference_paths = {}
        if reference_paths.get("dark_mean"):
            self.dark_reference_path.setText(str(reference_paths["dark_mean"]))
        if reference_paths.get("white_mean"):
            self.white_reference_path.setText(str(reference_paths["white_mean"]))

    def _reference_input_values(self):
        paths = {}
        dark_path = self.dark_reference_path.text().strip()
        white_path = self.white_reference_path.text().strip()
        if dark_path:
            paths["dark_mean"] = dark_path
        if white_path:
            paths["white_mean"] = white_path
        return paths

    def _bundle_reference_paths(self, bundle_path, manifest):
        calibration = manifest.get("calibration", {}) if isinstance(manifest, dict) else {}
        if not isinstance(calibration, dict):
            return {}
        reference_paths = {}
        for side in ("dark", "white"):
            side_section = calibration.get(side, {})
            mean_section = side_section.get("mean", {}) if isinstance(side_section, dict) else {}
            mean_relpath = mean_section.get("path") if isinstance(mean_section, dict) else None
            if not mean_relpath:
                continue
            mean_path = (bundle_path / str(mean_relpath)).resolve()
            if mean_path.exists():
                reference_paths[f"{side}_mean"] = str(mean_path)
        return reference_paths

    def _resolve_reference_mean_path(self, value, *, fallback="", side="reference"):
        raw_value = str(value or "").strip() or str(fallback or "").strip()
        if not raw_value:
            raise ValueError(f"{side} reference 경로를 입력해주세요.")

        path = self._resolve_path(raw_value)
        if path.is_dir():
            path = path / "mean.npy"
        if not path.exists():
            raise ValueError(f"{side} reference mean 파일을 찾을 수 없습니다.\n{path}")
        if path.suffix.lower() != ".npy":
            raise ValueError(f"{side} reference는 mean.npy 파일이거나 mean.npy가 있는 폴더여야 합니다.\n{path}")
        return path.resolve()

    @staticmethod
    def _resolve_path(value):
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    def _list_lumo_devices(self):
        return list_lumo_devices()

    def _find_lumo_network(self, mac_address="", interface_name=None):
        return find_lumo_network(interface_name=interface_name)

    def _find_lumo_device_index(self, devices, *, mac_address="", ip_address=""):
        return find_lumo_device_index(devices, mac_address=mac_address, ip_address=ip_address)

    def _build_lumo_search_message(self, network, devices, device_index, errors, network_candidates=None):
        lines = []
        if network:
            lines.append(f"IP: {network.get('ip_address')}")
            lines.append(f"이더넷: {network.get('interface_alias')}")
            lines.append(f"MAC: {network.get('mac_address')}")
        elif network_candidates:
            lines.append(f"네트워크 후보: {len(network_candidates)}개")
            for candidate in network_candidates[:3]:
                lines.append(
                    f"- {candidate.get('ip_address')} / {candidate.get('link_layer_address')} / "
                    f"{candidate.get('interface_alias')}"
                )
        if device_index is not None:
            lines.append(f"Device Index: {device_index}")
        lines.append(f"Native 장치: {len(devices) if isinstance(devices, list) else 0}대")
        if errors:
            lines.extend(errors)
        return "\n".join(lines)

    @staticmethod
    def _is_low_quality_lumo_device(device):
        return is_low_quality_lumo_device(device)

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
