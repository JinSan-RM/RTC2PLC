from pypylon import pylon
import numpy as np
from typing import Optional

from src.utils.logger import log


def get_camera_count() -> int:
    """
    연결된 카메라 개수 확인
    """
    
    try:
        tlFactory = pylon.TlFactory.GetInstance()
        devices = tlFactory.EnumerateDevices()
        count = len(devices)
        log(f"카메라 {count}대 확인")
        
        for idx, device in enumerate(devices):
            log(f"[{idx}] {device.GetModelName()} - {device.GetIpAddress()}")
        return count
    
    except Exception as e:
        log(f" 카메라 검색 실패 : {e}")
        return 0

class BaslerCameraManager:
    """Basler 산업용 카메라 관리"""
    
    def __init__(self, camera_index: int = 0, roi:dict = None):
        self.camera = None
        self.converter = None
        self.camera_index = camera_index
        self.is_connected = False
        self.roi = roi
    
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
            log("\n" + "="*50)
            log(f"Basler 카메라 {self.camera_index} 설정 시작...")
            log("="*50)

            # 카메라 최대 해상도 및 제약사항 확인
            max_width = self.camera.Width.Max
            max_height = self.camera.Height.Max
            min_width = self.camera.Width.Min
            min_height = self.camera.Height.Min
            width_inc = self.camera.Width.GetInc()
            height_inc = self.camera.Height.GetInc()
            
            log(f"📏 카메라 해상도 제약:")
            log(f"  Width: {min_width} ~ {max_width} (증분: {width_inc})")
            log(f"  Height: {min_height} ~ {max_height} (증분: {height_inc})")

            # 1) 버퍼 최소화
            self.camera.MaxNumBuffer.Value = 3
            log(f"✓ MaxNumBuffer = {self.camera.MaxNumBuffer.Value}")

            # 2) PixelFormat RAW 설정
            try:
                from pypylon import genicam
                if self.camera.PixelFormat.GetAccessMode() == genicam.RW:
                    self.camera.PixelFormat.SetValue("BayerBG8")
                    log("✓ PixelFormat = BayerBG8 (RAW)")
                else:
                    current_format = self.camera.PixelFormat.GetValue()
                    log(f"⚠️ PixelFormat 변경 불가, 현재: {current_format}")
            except Exception as e:
                log(f"❌ PixelFormat 설정 실패: {e}")
                    
            # 3) ROI 설정
            if self.roi:
                try:
                    offset_x = self.roi.get('x', 0)
                    offset_y = self.roi.get('y', 0)
                    width = self.roi.get('width', 1280)
                    height = self.roi.get('height', 1080)
                    
                    log(f"\n🎯 요청 ROI:")
                    log(f"  Offset: ({offset_x}, {offset_y})")
                    log(f"  Size: {width} x {height}")
                    
                    # Step 1: Offset을 0으로 초기화
                    from pypylon import genicam
                    if hasattr(self.camera, 'OffsetX') and self.camera.OffsetX.GetAccessMode() == genicam.RW:
                        self.camera.OffsetX.SetValue(0)
                        log("✓ OffsetX = 0 (초기화)")
                        
                    if hasattr(self.camera, 'OffsetY') and self.camera.OffsetY.GetAccessMode() == genicam.RW:
                        self.camera.OffsetY.SetValue(0)
                        log("✓ OffsetY = 0 (초기화)")
                    
                    # Step 2: Width 설정
                    adjusted_width = (width // width_inc) * width_inc
                    
                    # 최소/최대값 검증
                    if adjusted_width < min_width:
                        adjusted_width = min_width
                        log(f"⚠️ Width가 최소값({min_width})보다 작음. 조정함")
                        
                    if adjusted_width > max_width:
                        adjusted_width = max_width
                        log(f"⚠️ Width가 최대값({max_width})보다 큼. 조정함")
                    
                    # Offset 고려
                    if offset_x + adjusted_width > max_width:
                        adjusted_width = max_width - offset_x
                        adjusted_width = (adjusted_width // width_inc) * width_inc
                        log(f"⚠️ OffsetX 고려하여 Width 재조정: {adjusted_width}")
                    
                    self.camera.Width.SetValue(adjusted_width)
                    log(f"✓ Width = {adjusted_width}")
                    
                    # Step 3: Height 설정
                    adjusted_height = (height // height_inc) * height_inc
                    
                    # 최소/최대값 검증
                    if adjusted_height < min_height:
                        adjusted_height = min_height
                        log(f"⚠️ Height가 최소값({min_height})보다 작음. 조정함")
                        
                    if adjusted_height > max_height:
                        adjusted_height = max_height
                        log(f"⚠️ Height가 최대값({max_height})보다 큼. 조정함")
                    
                    # Offset 고려
                    if offset_y + adjusted_height > max_height:
                        adjusted_height = max_height - offset_y
                        adjusted_height = (adjusted_height // height_inc) * height_inc
                        log(f"⚠️ OffsetY 고려하여 Height 재조정: {adjusted_height}")
                    
                    self.camera.Height.SetValue(adjusted_height)
                    log(f"✓ Height = {adjusted_height}")
                    
                    # Step 4: Offset 설정
                    if hasattr(self.camera, 'OffsetX') and self.camera.OffsetX.GetAccessMode() == genicam.RW:
                        offset_x_inc = self.camera.OffsetX.GetInc()
                        adjusted_offset_x = (offset_x // offset_x_inc) * offset_x_inc
                        
                        # 범위 검증
                        current_width = self.camera.Width.Value
                        if adjusted_offset_x + current_width > max_width:
                            adjusted_offset_x = max_width - current_width
                            adjusted_offset_x = (adjusted_offset_x // offset_x_inc) * offset_x_inc
                            log(f"⚠️ OffsetX 재조정: {adjusted_offset_x}")
                        
                        self.camera.OffsetX.SetValue(adjusted_offset_x)
                        log(f"✓ OffsetX = {adjusted_offset_x}")

                    if hasattr(self.camera, 'OffsetY') and self.camera.OffsetY.GetAccessMode() == genicam.RW:
                        offset_y_inc = self.camera.OffsetY.GetInc()
                        adjusted_offset_y = (offset_y // offset_y_inc) * offset_y_inc
                        
                        # 범위 검증
                        current_height = self.camera.Height.Value
                        if adjusted_offset_y + current_height > max_height:
                            adjusted_offset_y = max_height - current_height
                            adjusted_offset_y = (adjusted_offset_y // offset_y_inc) * offset_y_inc
                            log(f"⚠️ OffsetY 재조정: {adjusted_offset_y}")
                        
                        self.camera.OffsetY.SetValue(adjusted_offset_y)
                        log(f"✓ OffsetY = {adjusted_offset_y}")
                    
                    # 최종 확인
                    final_offset_x = self.camera.OffsetX.Value if hasattr(self.camera, 'OffsetX') else 0
                    final_offset_y = self.camera.OffsetY.Value if hasattr(self.camera, 'OffsetY') else 0
                    final_width = self.camera.Width.Value
                    final_height = self.camera.Height.Value
                    
                    log(f"\n✅ 최종 ROI 설정:")
                    log(f"  Offset: ({final_offset_x}, {final_offset_y})")
                    log(f"  Size: {final_width} x {final_height}")
                    log(f"  영역: X[{final_offset_x}~{final_offset_x+final_width}], Y[{final_offset_y}~{final_offset_y+final_height}]")
                    
                except Exception as e:
                    log(f"❌ ROI 설정 실패: {e}")
                    import traceback
                    traceback.print_exc()
                    # ROI 실패 시 기본 해상도
                    self.camera.Width.SetValue(min(1280, max_width))
                    self.camera.Height.SetValue(min(720, max_height))
            else:
                # ROI 없으면 기본 해상도
                self.camera.Width.SetValue(min(1280, max_width))
                self.camera.Height.SetValue(min(720, max_height))
                log(f"✓ 기본 해상도: {self.camera.Width.Value}x{self.camera.Height.Value}")
            
                
            # 4) 자동 노출 끄기
            self.camera.ExposureAuto.SetValue("Off")
            log("ExposureAuto: Off")
            try:
                target_fps = 60
                exposure_us = int(1_000_000 / target_fps)
                exposure_us = max(self.camera.ExposureTimeRaw.Min, 
                                min(exposure_us, self.camera.ExposureTimeRaw.Max))
                self.camera.ExposureTimeRaw.SetValue(exposure_us)
                log(f"ExposureTimeRaw = {exposure_us} us (≈{1_000_000/exposure_us:.1f} FPS 제한)")
            except Exception as e:
                log(f"ExposureTime 설정 실패: {e}")

            # GainAuto 끄기
            try:
                if hasattr(self.camera, "GainAuto"):
                    self.camera.GainAuto.SetValue("Off")
                    log("GainAuto: Off")
            except Exception as e:
                log(f"GainAuto 설정 실패: {e}")

            # TriggerMode off
            try:
                if hasattr(self.camera, "TriggerMode"):
                    self.camera.TriggerMode.SetValue("Off")
                    log("TriggerMode: Off")
            except Exception as e:
                log(f"TriggerMode 설정 실패: {e}")

            # Continuous 모드
            try:
                if hasattr(self.camera, "AcquisitionMode"):
                    self.camera.AcquisitionMode.SetValue("Continuous")
                    log("AcquisitionMode: Continuous")
            except Exception as e:
                log(f"AcquisitionMode 설정 실패: {e}")

            if hasattr(self.camera, "AcquisitionFrameRateEnable"):
                self.camera.AcquisitionFrameRateEnable.SetValue(True)
                log("AcquisitionFrameRateEnable: On")
            if hasattr(self.camera, "AcquisitionFrameRateAbs"):
                target_fps = 60.0
                self.camera.AcquisitionFrameRateAbs.SetValue(target_fps)
                log(f"AcquisitionFrameRateAbs = {target_fps} Hz")


            log("Basler 설정 완료!\n")

        except Exception as e:
            log(f"Basler 설정 오류: {e}")


    
    def grab_frame(self) -> Optional[np.ndarray]:
        if not self.is_connected or not self.camera:
            return None
        try:
            if self.camera and self.camera.IsGrabbing():
                grabResult = self.camera.RetrieveResult(100, pylon.TimeoutHandling_ThrowException)
                if grabResult.GrabSucceeded():
                    image = self.converter.Convert(grabResult)
                    frame = image.GetArray()
                    if not hasattr(self, '_frame_size_logged'):
                        log(f"[카메라 {self.camera_index}] 실제 프레임 크기: {frame.shape}")
                        log(f"[카메라 {self.camera_index}] 설정된 Width: {self.camera.Width.Value}")
                        log(f"[카메라 {self.camera_index}] 설정된 Height: {self.camera.Height.Value}")
                        log(f"[카메라 {self.camera_index}] 설정된 OffsetX: {self.camera.OffsetX.Value if hasattr(self.camera, 'OffsetX') else 0}")
                        log(f"[카메라 {self.camera_index}] 설정된 OffsetY: {self.camera.OffsetY.Value if hasattr(self.camera, 'OffsetY') else 0}")
                        self._frame_size_logged = True
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
