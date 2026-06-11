# Spectral Runtime Full Kit

이 폴더는 외부 프로젝트에 그대로 복사해서 `Specim FX17e + Lumo live/replay + PLS-DA 모델 추론 + reflectance/absorbance + pixel-wise inference + objectization + dashboard/event 출력`을 호출하기 위한 런타임 키트입니다.

## 사용 방식

외부 프로젝트에서 이 폴더 전체를 복사한 뒤, 실행 프로세스의 `PYTHONPATH`에 이 폴더를 추가합니다. 예제 스크립트는 자동으로 자기 부모 폴더를 `sys.path`에 추가하므로 폴더 안에서 바로 실행할 수 있습니다.

```powershell
cd spectral_runtime_full_kit
python examples\run_replay_bundle.py --bundle C:\path\to\model_bundle --session C:\path\to\capture_session --output-root C:\path\to\reports
python examples\run_lumo_live_bundle.py --bundle C:\path\to\model_bundle --camera-config configs\camera.fx17e.example.yaml --max-frames 100 --output-root C:\path\to\reports
```

## 포함 범위

- `camera/`: Lumo provider, simulated provider, stream worker, frame filter, cube assembler
- `capture/`: replay/session writer/streaming helpers
- `calibration/`: dark/white reference, reflectance, absorbance, QC helpers
- `models/`: PLS-DA pipeline/model load/inference and model bundle manifest
- `runtime/`: replay runtime, live runtime, pixel inference, objectization, dashboard, stream output, ACK log
- `labeling/`: runtime-safe class schema/label schema helpers only
- `runtime_module.py`: 외부 프로젝트에서 쓰기 쉬운 facade
- `examples/`: replay bundle 실행과 Lumo live bundle 실행 예제

## 외부에서 따로 맞출 의존성

이 키트는 dependency를 vendoring하지 않습니다. 실행 환경에는 최소한 `numpy`, `scipy`, `scikit-learn`, `Pillow`, `pyyaml`이 필요합니다. Lumo live에는 Specim Lumo SDK/DLL, 라이선스, GenTL/CTI 경로가 장비 PC에 설정되어 있어야 합니다.

## Reference와 모델 번들

권장 흐름은 E2E 앱에서 dark/white reference와 학습 모델을 생성하고, `model_bundle.json`이 있는 bundle 폴더를 이 키트에 넘기는 방식입니다. 번들에 `training_metadata.model_input_kind`가 `reflectance` 또는 `absorbance`로 들어 있으면 런타임에서 raw cube에 dark/white를 적용한 뒤 추론합니다. `raw` 모델이면 calibration context는 생성되지만 변환은 적용하지 않습니다.

## Local Network Auto Resolve

Windows 장비 PC의 네트워크 어댑터 값을 읽어 Lumo 설정을 채우고 싶으면 camera config의 `lumo` 섹션에 `auto`를 사용합니다.

```yaml
lumo:
  auto_from_local_network: true
  interface_name: "이더넷 3"
  mac_address: "70-F8-E7-B0-11-1B"
  device_index: 2
  grab_timeout_ms: 5000
  skip_scan: false
  provider_mode: native
```

Use `examples/find_lumo_network.py` to check the current IP matched to `mac_address` before opening the camera. `ip_address` is not managed in config; pass `--lumo-ip` only for manual diagnostics.

## Python API

```python
from pathlib import Path
from runtime_module import LumoLiveConfig, SpectralRuntimeModule

module = SpectralRuntimeModule.from_bundle(
    Path(r"C:\path\to\model_bundle"),
    output_root=Path(r"C:\path\to\reports"),
)

replay_result = module.run_replay(session_dir=Path(r"C:\path\to\capture_session"))
print(replay_result.screen_outputs())
print(replay_result.data_outputs())

lumo_config = LumoLiveConfig.from_mapping({
    "camera": {"band_count": 224, "spatial_width": 640, "integration_time_us": 4000, "line_rate_hz": 100.0},
    "lumo": {"interface_name": "이더넷 3", "mac_address": "70-F8-E7-B0-11-1B", "device_index": 2, "grab_timeout_ms": 5000},
})
live_result = module.run_lumo_live(lumo_config=lumo_config, session_id="line-a-live")
```

## 출력

`RuntimeOutputResult`는 화면 출력 후보와 데이터 전달 후보를 분리해서 제공합니다.

- 화면: `dashboard.html`, `line_preview.png`, `line_overlay.png`, `line_class_map.png`
- 데이터: `events.jsonl`, `summary.json`, `ack-log.jsonl`, optional stream endpoint

`events.jsonl`의 object 결과는 class/confidence/bbox/frame/timestamp 기반으로 외부 Machine Controller나 상위 앱에서 바로 소비할 수 있는 구조입니다.

## 제외 범위

- Python package install용 packaging metadata
- dependency vendoring
- actuator/conveyor/PLC 제어
- PySide UI 코드
- YOLO/딥러닝 runtime
