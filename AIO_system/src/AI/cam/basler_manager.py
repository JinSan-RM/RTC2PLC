from pypylon import pylon
import numpy as np
from typing import Optional

from src.utils.logger import log


class BaslerCameraManager:
    """Basler 산업용 카메라 관리"""
    
    def __init__(self, camera_index: int = 0):
        self.camera = None
        self.converter = None
        self.camera_index = camera_index
        self.is_connected = False
    
    def initialize(self, camera_ip: str = None) -> bool:
        try:
            tlFactory = pylon.TlFactory.GetInstance()
            
            if camera_ip:
                device_info = pylon.DeviceInfo()
                device_info.SetIpAddress(camera_ip)
                self.camera = pylon.InstantCamera(tlFactory.CreateDevice(device_info))
            else:
                devices = tlFactory.EnumerateDevices()
                if not devices:
                    return False
                if self.camera_index >= len(devices):
                    return False
                self.camera = pylon.InstantCamera(tlFactory.CreateDevice(devices[self.camera_index]))
                
                device = devices[self.camera_index]
                log(f"선택된 카메라: {device.GetModelName()} - {device.GetSerialNumber()}")
                log(f"  • IP 주소: {device.GetIpAddress()}")
                log(f"  • 맥 주소: {device.GetMacAddress()}")
                self.camera = pylon.InstantCamera(tlFactory.CreateDevice(device))
            
            self.camera.Open()
            self.setup_camera_parameters()
            
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            
            self.is_connected = True
            log(f"Basler 카메라 연결 성공!")
            return True
        except Exception as e:
            log(f"카메라 연결 실패: {e}")
            return False
    
    def setup_camera_parameters(self):
        """
        카메라별 옵션 상세 설정 필요함.
        
        카메라 인덱스 받아서 각 카메라별 설정값 명백히 맵핑해서 동작해야함.
        """
        try:
            log("\n📷 Basler 카메라 설정 시작...")

            # 1) 버퍼 최소화
            self.camera.MaxNumBuffer.Value = 10
            log("  ✓ MaxNumBuffer = 10")

            # 2) PixelFormat RAW 설정
            try:
                if self.camera.PixelFormat.IsWritable():
                    self.camera.PixelFormat.SetValue("BayerBG8")
                    log("PixelFormat = BayerBG8 (RAW)")
                else:
                    current_format = self.camera.PixelFormat.GetValue()
                    log(f" PixelFormat 변경 불가, 현재 값: {current_format}")
            except Exception as e:
                log(f"PixelFormat 설정 실패: {e}")
                
            # 3) 해상도
            self.camera.Width.Value = min(1280, self.camera.Width.Max)
            self.camera.Height.Value = min(720, self.camera.Height.Max)
            log(f"  ✓ 해상도: {self.camera.Width.Value}x{self.camera.Height.Value}")

            # 4) 자동 노출 끄기
            self.camera.ExposureAuto.SetValue("Off")
            log("  ✓ ExposureAuto: Off")
            try:
                target_fps = 60
                exposure_us = int(1_000_000 / target_fps)
                exposure_us = max(self.camera.ExposureTimeRaw.Min, 
                                min(exposure_us, self.camera.ExposureTimeRaw.Max))
                self.camera.ExposureTimeRaw.SetValue(exposure_us)
                log(f"  ✓ ExposureTimeRaw = {exposure_us} us (≈{1_000_000/exposure_us:.1f} FPS 제한)")
            except Exception as e:
                log(f"  ⚠ ExposureTime 설정 실패: {e}")

            # GainAuto 끄기
            try:
                if hasattr(self.camera, "GainAuto"):
                    self.camera.GainAuto.SetValue("Off")
                    log("  ✓ GainAuto: Off")
            except Exception as e:
                log(f"  ⚠ GainAuto 설정 실패: {e}")

            # TriggerMode off
            try:
                if hasattr(self.camera, "TriggerMode"):
                    self.camera.TriggerMode.SetValue("Off")
                    log("  ✓ TriggerMode: Off")
            except Exception as e:
                log(f"  ⚠ TriggerMode 설정 실패: {e}")

            # Continuous 모드
            try:
                if hasattr(self.camera, "AcquisitionMode"):
                    self.camera.AcquisitionMode.SetValue("Continuous")
                    log("  ✓ AcquisitionMode: Continuous")
            except Exception as e:
                log(f"  ⚠ AcquisitionMode 설정 실패: {e}")

            if hasattr(self.camera, "AcquisitionFrameRateEnable"):
                self.camera.AcquisitionFrameRateEnable.SetValue(True)
                log("  ✓ AcquisitionFrameRateEnable: On")
            if hasattr(self.camera, "AcquisitionFrameRateAbs"):
                target_fps = 60.0
                self.camera.AcquisitionFrameRateAbs.SetValue(target_fps)
                log(f"  ✓ AcquisitionFrameRateAbs = {target_fps} Hz")


            log("📷 Basler 설정 완료!\n")

        except Exception as e:
            log(f"❌ Basler 설정 오류: {e}")


    
    def grab_frame(self) -> Optional[np.ndarray]:
        if not self.is_connected or not self.camera:
            return None
        try:
            if self.camera and self.camera.IsGrabbing():
                grabResult = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
                if grabResult.GrabSucceeded():
                    image = self.converter.Convert(grabResult)
                    frame = image.GetArray()
                    grabResult.Release()
                    return frame
                else:
                    grabResult.Release()
        except Exception as e:
            log(f"프레임 캡처 오류: {e}")
        return None
    
    def start_grabbing(self):
        if self.camera and self.is_connected:
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    
    def stop_grabbing(self):
        if self.camera and self.is_connected:
            self.camera.StopGrabbing()
    
    def close(self):
        try:
            if self.camera and self.camera.IsOpen():
                if self.camera.IsGrabbing():
                    self.camera.StopGrabbing()
                self.camera.Close()
            self.is_connected = False
        except Exception as e:
            log(f"카메라 해제 오류: {e}")
