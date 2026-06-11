"""Example config for the copyable Specim Lumo camera kit."""

CAMERA_CONFIG = {
    "camera": {
        "band_count": 224,
        "spatial_width": 640,
        "integration_time_us": 4000,
        "exposure_time_us": 4000,
        "line_rate_hz": 100.0,
        "rgb_bands": [32, 96, 160],
    },
    "lumo": {
        "auto_from_local_network": True,
        "serial_number": None,
        "interface_name": "이더넷 3",
        "mac_address": "70-F8-E7-B0-11-1B",
        "device_index": 2,
        "grab_timeout_ms": 5000,
        "skip_scan": False,
        "provider_mode": "native",
    },
    "breeze_compat": {
        "mirror_line": False,
    },
}
