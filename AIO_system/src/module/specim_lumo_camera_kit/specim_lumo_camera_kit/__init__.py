"""Copyable Specim FX17e/Lumo camera kit.

Copy the outer `specim_lumo_camera_kit` folder into another project root, then:

    from specim_lumo_camera_kit import SpecimLumoCameraModule
"""

from .base import CameraInfo, CameraProvider, CameraSettings, FrameSource, LineFrame
from .local_network import (
    LocalNetworkAdapter,
    LocalNetworkNeighbor,
    find_lumo_neighbor_by_mac,
    list_ipv4_neighbors,
    list_local_network_adapters,
    list_lumo_remote_neighbors,
    merge_lumo_network_auto_settings,
    normalize_mac_address,
    parse_ipconfig_all,
    parse_net_neighbor_json,
    select_lumo_local_adapter,
)
from .module import (
    CameraCaptureResult,
    CameraSessionResult,
    SpecimLumoCameraModule,
    SpecimLumoModuleConfig,
    build_lumo_camera_settings,
    build_lumo_module_config,
)
from .version import BUILD_DATE, GIT_COMMIT, GIT_DESCRIBE, VERSION, __version__, version_payload

__all__ = [
    "BUILD_DATE",
    "CameraCaptureResult",
    "CameraInfo",
    "CameraProvider",
    "CameraSessionResult",
    "CameraSettings",
    "FrameSource",
    "GIT_COMMIT",
    "GIT_DESCRIBE",
    "LineFrame",
    "LocalNetworkAdapter",
    "LocalNetworkNeighbor",
    "SpecimLumoCameraModule",
    "SpecimLumoModuleConfig",
    "VERSION",
    "__version__",
    "build_lumo_camera_settings",
    "build_lumo_module_config",
    "find_lumo_neighbor_by_mac",
    "list_ipv4_neighbors",
    "list_local_network_adapters",
    "list_lumo_remote_neighbors",
    "merge_lumo_network_auto_settings",
    "normalize_mac_address",
    "parse_ipconfig_all",
    "parse_net_neighbor_json",
    "select_lumo_local_adapter",
    "version_payload",
]
