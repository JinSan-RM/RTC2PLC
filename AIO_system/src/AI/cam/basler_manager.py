from pypylon import pylon
import numpy as np
from typing import Optional


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
            
            self.camera.Open()
            self.setup_camera_parameters()
            
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            
            self.is_connected = True
            print(f"Basler 카메라 연결 성공!")
            return True
        except Exception as e:
            print(f"카메라 연결 실패: {e}")
            return False
    
    def setup_camera_parameters(self):
        """카메라 파라미터 설정 - FPS 최적화"""
        try:
            print("\n📷 Basler 카메라 설정 시작...")
            
            # 1. 버퍼 설정
            self.camera.MaxNumBuffer.Value = 5
            print("  ✓ 버퍼 크기: 5")
            
            # 2. 해상도 설정
            max_width = self.camera.Width.Max
            max_height = self.camera.Height.Max
            target_width = min(1280, max_width)
            target_height = min(720, max_height)
            
            self.camera.Width.Value = target_width
            self.camera.Height.Value = target_height
            print(f"  ✓ 해상도: {target_width}x{target_height}")
            
            # 3. ExposureAuto 끄기 (매우 중요!)
            try:
                if hasattr(self.camera, 'ExposureAuto'):
                    self.camera.ExposureAuto.SetValue('Off')
                    print(f"  ✓ 자동 노출: Off")
            except Exception as e:
                print(f"  ⚠ 자동 노출 설정 실패: {e}")
            
            # 4. ExposureTime 설정 (FPS의 핵심!)
            try:
                if hasattr(self.camera, 'ExposureTime'):
                    # 현재 노출 시간 확인
                    current_exposure = self.camera.ExposureTime.GetValue()
                    print(f"  • 현재 노출 시간: {current_exposure:.0f}μs ({1000000/current_exposure:.1f} fps 제한)")
                    
                    # 목표: 10ms (10000μs) = 최대 100fps 가능
                    target_exposure = 10000
                    
                    # 범위 확인
                    min_exposure = self.camera.ExposureTime.Min
                    max_exposure = self.camera.ExposureTime.Max
                    
                    # 안전한 값으로 설정
                    new_exposure = max(min_exposure, min(target_exposure, max_exposure))
                    self.camera.ExposureTime.SetValue(new_exposure)
                    
                    actual_exposure = self.camera.ExposureTime.GetValue()
                    max_fps = 1000000 / actual_exposure
                    print(f"  ✓ 새 노출 시간: {actual_exposure:.0f}μs (최대 {max_fps:.1f} fps)")
            except Exception as e:
                print(f"  ⚠ 노출 시간 설정 실패: {e}")
            
            # 5. GainAuto 끄기
            try:
                if hasattr(self.camera, 'GainAuto'):
                    self.camera.GainAuto.SetValue('Off')
                    print(f"  ✓ 자동 게인: Off")
            except Exception as e:
                print(f"  ⚠ 자동 게인 설정 실패: {e}")
            
            # 6. TriggerMode 끄기 (중요!)
            try:
                if hasattr(self.camera, 'TriggerMode'):
                    self.camera.TriggerMode.SetValue('Off')
                    print(f"  ✓ 트리거 모드: Off")
            except Exception as e:
                print(f"  ⚠ 트리거 모드 설정 실패: {e}")
            
            # 7. Acquisition Mode 설정
            try:
                if hasattr(self.camera, 'AcquisitionMode'):
                    self.camera.AcquisitionMode.SetValue('Continuous')
                    print(f"  ✓ Acquisition Mode: Continuous")
            except Exception as e:
                print(f"  ⚠ Acquisition 모드 설정 실패: {e}")
            
            print("📷 카메라 설정 완료!\n")
            
        except Exception as e:
            print(f"❌ 카메라 설정 오류: {e}")
    
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
            print(f"프레임 캡처 오류: {e}")
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
            print(f"카메라 해제 오류: {e}")
