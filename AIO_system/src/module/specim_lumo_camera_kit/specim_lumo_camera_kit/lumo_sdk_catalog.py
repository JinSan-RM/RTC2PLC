"""Specim Lumo SDK feature catalog used for capability checks.

The list is intentionally conservative: it contains features referenced by the
local Lumo Sensor SDK manual and the current FX17e bring-up docs. Runtime code
uses this catalog for diagnostics only; applying settings still requires an
explicit implementation per feature group.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class LumoSdkFeature:
    name: str
    category: str
    priority: str
    purpose: str
    implementation_status: str


FEATURES: tuple[LumoSdkFeature, ...] = (
    LumoSdkFeature("ExposureTime", "timing", "p0", "Line exposure/integration time.", "implemented"),
    LumoSdkFeature("Camera.ExposureTime", "timing", "p0", "Alternate exposure feature name.", "fallback implemented"),
    LumoSdkFeature("Camera.Exposure.Time", "timing", "p1", "Alternate exposure feature name.", "missing"),
    LumoSdkFeature("AcquisitionLineRate", "timing", "p0", "Requested acquisition line rate.", "implemented"),
    LumoSdkFeature("Acquisition.LineRate", "timing", "p0", "Alternate line-rate feature name.", "fallback implemented"),
    LumoSdkFeature("Camera.AcquisitionLineRate", "timing", "p1", "Alternate line-rate feature name.", "fallback implemented"),
    LumoSdkFeature("Camera.FrameRate", "timing", "p1", "Camera frame/line rate alias.", "missing"),
    LumoSdkFeature("Acquisition.CalculatedFrameRate", "timing", "p1", "Actual calculated frame rate.", "missing"),
    LumoSdkFeature("Acquisition.Timeout", "timing", "p1", "Camera acquisition timeout.", "missing"),
    LumoSdkFeature("Camera.Trigger.Mode", "trigger", "p0", "Free-run or trigger mode control.", "missing"),
    LumoSdkFeature("Trigger.Selector", "trigger", "p1", "Trigger selector control when present.", "missing"),
    LumoSdkFeature("Trigger.Source", "trigger", "p1", "Trigger source control when present.", "missing"),
    LumoSdkFeature("Trigger.Activation", "trigger", "p1", "Trigger edge/activation control.", "missing"),
    LumoSdkFeature("Trigger.Delay", "trigger", "p1", "Trigger delay control.", "missing"),
    LumoSdkFeature("Camera.Binning.Spectral", "binning", "p0", "Spectral binning factor.", "missing"),
    LumoSdkFeature("Camera.Binning.Spatial", "binning", "p0", "Spatial binning factor.", "missing"),
    LumoSdkFeature("Camera.Binning.Average", "binning", "p1", "Average binning mode.", "missing"),
    LumoSdkFeature("Camera.Binning.HardwareModes", "binning", "p1", "Hardware binning mode list.", "missing"),
    LumoSdkFeature("Camera.Gain.Analog", "gain", "p1", "Analog gain.", "missing"),
    LumoSdkFeature("Camera.Gain.Digital", "gain", "p1", "Digital gain.", "missing"),
    LumoSdkFeature("Acquisition.SimpleGainControl", "gain", "p1", "SDK simple gain control.", "missing"),
    LumoSdkFeature("Camera.ExposureTime.Auto", "gain", "p2", "Auto exposure enable/status.", "missing"),
    LumoSdkFeature("Camera.BitDepth", "image-format", "p1", "Camera bit depth.", "missing"),
    LumoSdkFeature("Camera.ByteDepth", "image-format", "p1", "Camera byte depth.", "missing"),
    LumoSdkFeature("Camera.Image.ByteDepth", "image-format", "p1", "Image byte depth.", "missing"),
    LumoSdkFeature("Camera.Image.Width", "image-format", "p0", "Runtime image width.", "read only"),
    LumoSdkFeature("Camera.Image.Height", "image-format", "p1", "Runtime image height/bands.", "missing"),
    LumoSdkFeature("Camera.Image.SizeBytes", "image-format", "p0", "Payload size bytes.", "read implemented"),
    LumoSdkFeature("Camera.Image.SizePixels", "image-format", "p1", "Payload size pixels.", "missing"),
    LumoSdkFeature("Camera.Image.ReadoutTime", "image-format", "p1", "Readout timing.", "missing"),
    LumoSdkFeature("Camera.Image.Transformation", "image-format", "p1", "Image transform/orientation.", "missing"),
    LumoSdkFeature("Camera.MROI.Enable", "roi", "p0", "Camera-side MROI enable.", "missing"),
    LumoSdkFeature("Camera.MROI.Clear", "roi", "p0", "Clear camera-side MROI.", "missing"),
    LumoSdkFeature("Camera.MROI.MultibandString", "roi", "p0", "Camera-side spectral ROI definition.", "missing"),
    LumoSdkFeature("Camera.MROI.IsHardware", "roi", "p1", "MROI hardware support flag.", "missing"),
    LumoSdkFeature("AcquisitionWindow.Width", "roi", "p1", "Acquisition window width.", "missing"),
    LumoSdkFeature("AcquisitionWindow.Height", "roi", "p1", "Acquisition window height.", "missing"),
    LumoSdkFeature("AcquisitionWindow.Left", "roi", "p1", "Acquisition window left offset.", "missing"),
    LumoSdkFeature("AcquisitionWindow.Top", "roi", "p1", "Acquisition window top offset.", "missing"),
    LumoSdkFeature("Camera.OpenShutter", "shutter", "p0", "Open shutter command.", "implemented"),
    LumoSdkFeature("Camera.CloseShutter", "shutter", "p0", "Close shutter command.", "implemented"),
    LumoSdkFeature("Camera.ToggleShutter", "shutter", "p2", "Toggle shutter command.", "missing"),
    LumoSdkFeature("Camera.Shutter.IsOpen", "shutter", "p0", "Shutter open status.", "implemented"),
    LumoSdkFeature("Camera.Shutter.IsConnected", "shutter", "p1", "Shutter connection status.", "missing"),
    LumoSdkFeature("Camera.Shutter.IsToggle", "shutter", "p2", "Shutter toggle capability.", "missing"),
    LumoSdkFeature("Acquisition.Start", "acquisition", "p0", "Start acquisition command.", "implemented"),
    LumoSdkFeature("Acquisition.Stop", "acquisition", "p0", "Stop acquisition command.", "implemented"),
    LumoSdkFeature("Acquisition.Acquiring", "acquisition", "p1", "Acquiring status.", "missing"),
    LumoSdkFeature("Acquisition.FrameCounter", "acquisition", "p1", "SDK frame counter.", "missing"),
    LumoSdkFeature("Acquisition.FrameCounter.Reset", "acquisition", "p1", "Reset SDK frame counter.", "missing"),
    LumoSdkFeature("Acquisition.DroppedFrames", "acquisition", "p0", "Dropped frame counter.", "read implemented"),
    LumoSdkFeature("Acquisition.RingBuffer.Lag", "acquisition", "p0", "Ring buffer lag.", "read implemented"),
    LumoSdkFeature("Acquisition.RingBuffer.Size", "acquisition", "p0", "Ring buffer size.", "read implemented"),
    LumoSdkFeature("Acquisition.RingBuffer.Sync", "acquisition", "p1", "Ring buffer sync command/status.", "missing"),
    LumoSdkFeature("Acquisition.Error", "acquisition", "p0", "Acquisition error signal/status.", "missing"),
    LumoSdkFeature("Acquisition.Encoding", "acquisition", "p2", "Acquisition encoding.", "missing"),
    LumoSdkFeature("Acquisition.SetupFilePath", "profile", "p0", "Setup file path.", "implemented"),
    LumoSdkFeature("Camera.Channel", "profile", "p0", "Camera channel selection.", "implemented"),
    LumoSdkFeature("Camera.Channels", "profile", "p0", "Camera channel enum/list.", "implemented"),
    LumoSdkFeature("Grabber.Channel", "profile", "p0", "Grabber channel selection.", "implemented"),
    LumoSdkFeature("Grabber.Channels", "profile", "p0", "Grabber channel enum/list.", "implemented"),
    LumoSdkFeature("Shutter.Channel", "profile", "p0", "Shutter channel selection.", "implemented"),
    LumoSdkFeature("Shutter.Channels", "profile", "p0", "Shutter channel enum/list.", "implemented"),
    LumoSdkFeature("Grabber.PlaybackFile", "profile", "p2", "SDK playback file path.", "missing"),
    LumoSdkFeature("Camera.NUC", "calibration", "p2", "Non-uniformity correction.", "missing"),
    LumoSdkFeature("Camera.AutoNUC", "calibration", "p2", "Auto NUC.", "missing"),
    LumoSdkFeature("Camera.BPR", "calibration", "p2", "Bad pixel replacement.", "missing"),
    LumoSdkFeature("Camera.BPR.CreateMap", "calibration", "p2", "Create BPR map.", "missing"),
    LumoSdkFeature("Camera.BPR.MapAvailable", "calibration", "p2", "BPR map availability.", "missing"),
    LumoSdkFeature("Camera.CalibrationPack", "calibration", "p2", "Calibration pack selection.", "missing"),
    LumoSdkFeature("Camera.CalibrationPack.IsLoaded", "calibration", "p2", "Calibration pack load state.", "missing"),
    LumoSdkFeature("Camera.Preprocessing.Enabled", "calibration", "p2", "Camera-side preprocessing.", "missing"),
    LumoSdkFeature("Camera.Wavelength.Start", "metadata", "p1", "Wavelength range start.", "missing"),
    LumoSdkFeature("Camera.Wavelength.Stop", "metadata", "p1", "Wavelength range stop.", "missing"),
    LumoSdkFeature("Camera.WavelengthTable", "metadata", "p1", "Wavelength table.", "missing"),
    LumoSdkFeature("Camera.WavelengthTable.Start", "metadata", "p1", "Wavelength table start.", "missing"),
    LumoSdkFeature("Camera.FWHM", "metadata", "p1", "Spectral FWHM metadata.", "missing"),
    LumoSdkFeature("Camera.Pixel.Width", "metadata", "p1", "Pixel width metadata.", "missing"),
    LumoSdkFeature("Camera.Pixel.Height", "metadata", "p1", "Pixel height metadata.", "missing"),
    LumoSdkFeature("Camera.FirmwareVersion", "diagnostics", "p1", "Firmware version.", "missing"),
    LumoSdkFeature("Camera.IsConnected", "diagnostics", "p1", "Camera connected status.", "missing"),
    LumoSdkFeature("Camera.Model", "diagnostics", "p1", "Camera model.", "read implemented"),
    LumoSdkFeature("Camera.SerialNumber", "diagnostics", "p1", "Camera serial number.", "read implemented"),
    LumoSdkFeature("Camera.Temperature", "diagnostics", "p1", "Camera temperature.", "missing"),
    LumoSdkFeature("Camera.Temperature.FPA", "diagnostics", "p1", "FPA temperature.", "missing"),
    LumoSdkFeature("Camera.Temperature.Board", "diagnostics", "p1", "Board temperature.", "missing"),
    LumoSdkFeature("Camera.TargetTemperature", "diagnostics", "p1", "Target temperature.", "missing"),
    LumoSdkFeature("Camera.Stabilization.Enabled", "diagnostics", "p1", "Stabilization setting.", "missing"),
    LumoSdkFeature("Camera.Stabilization.IsStable", "diagnostics", "p1", "Stabilization status.", "missing"),
    LumoSdkFeature("Sensor.SerialNumber", "diagnostics", "p1", "Sensor serial number.", "read implemented"),
    LumoSdkFeature("Sensor.Detector.Type", "diagnostics", "p2", "Detector type.", "missing"),
)


def iter_feature_names(*, priority: str | None = None) -> Iterable[str]:
    for feature in FEATURES:
        if priority is None or feature.priority == priority:
            yield feature.name


def feature_names() -> list[str]:
    return list(dict.fromkeys(iter_feature_names()))


def features_by_category() -> dict[str, list[LumoSdkFeature]]:
    grouped: dict[str, list[LumoSdkFeature]] = {}
    for feature in FEATURES:
        grouped.setdefault(feature.category, []).append(feature)
    return grouped
