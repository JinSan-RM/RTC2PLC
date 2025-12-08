import cv2
import os
from pypylon import pylon
from common.utils import generate_next_filename, get_basename

class CamManager:
    is_error = False

    def __init__(self, app, camera_ip="192.168.100.201", timeout=10000):  # Timeout 증가
        self.app = app
        self.camera = None
        self.converter = pylon.ImageFormatConverter()
        self.converter.OutputPixelFormat = pylon.PixelType_RGB8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        try:
            # IP-based connection with device enumeration as fallback
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if not devices:
                raise Exception("No camera devices found")

            print(f"[DEBUG] Found {len(devices)} devices:")
            for i, device in enumerate(devices):
                info = pylon.CDeviceInfo(device)
                device_ip_raw = info.GetPropertyValue("IpAddress")
                device_name_raw = info.GetPropertyValue("FriendlyName")
                device_model_raw = info.GetPropertyValue("ModelName")
                
                # 튜플에서 실제 값 추출
                device_ip = device_ip_raw[1] if isinstance(device_ip_raw, (list, tuple)) and len(device_ip_raw) > 1 else device_ip_raw
                device_name = device_name_raw[1] if isinstance(device_name_raw, (list, tuple)) and len(device_name_raw) > 1 else device_name_raw
                device_model = device_model_raw[1] if isinstance(device_model_raw, (list, tuple)) and len(device_model_raw) > 1 else device_model_raw
                
                print(f"  Device {i}: IP={device_ip}, Name={device_name}, Model={device_model}")
            
            # IP 기반 검색
            target_camera = None
            for device in devices:
                info = pylon.CDeviceInfo(device)
                current_ip_raw = info.GetPropertyValue("IpAddress")
                
                # 튜플에서 실제 IP 주소 추출
                current_ip = current_ip_raw[1] if isinstance(current_ip_raw, (list, tuple)) and len(current_ip_raw) > 1 else current_ip_raw
                
                print(f"[DEBUG] Checking device IP: {current_ip} vs target: {camera_ip}")
                if current_ip == camera_ip:
                    target_camera = device
                    break
            
            if target_camera:
                self.camera = pylon.InstantCamera(tl_factory.CreateDevice(target_camera))
                print(f"[DEBUG] Found target camera at {camera_ip}")
            else:
                # IP를 찾지 못한 경우 첫 번째 카메라 사용
                print(f"[WARN] Camera with IP {camera_ip} not found, using first available device")
                if devices:
                    self.camera = pylon.InstantCamera(tl_factory.CreateDevice(devices[0]))
                    info = pylon.CDeviceInfo(devices[0])
                    actual_ip_raw = info.GetPropertyValue("IpAddress")
                    actual_ip = actual_ip_raw[1] if isinstance(actual_ip_raw, (list, tuple)) and len(actual_ip_raw) > 1 else actual_ip_raw
                    print(f"[INFO] Using camera at IP: {actual_ip}")
                else:
                    raise Exception(f"Camera with IP {camera_ip} not found and no fallback devices available")

            if not self.camera:
                raise Exception(f"Failed to create camera instance")

            print(f"[DEBUG] Opening camera...")
            self.camera.Open()

            # Get node map
            nodemap = self.camera.GetNodeMap()

            # Print supported PixelFormats
            pixel_format_node = nodemap.GetNode("PixelFormat")
            if pixel_format_node is None:
                raise Exception("PixelFormat node is not available")
            else:
                current_format = pixel_format_node.GetValue()
                print(f"[INFO] Current PixelFormat: {current_format}")
                
                # 포맷에 따른 컨버터 자동 설정
                if "Mono" in current_format:
                    if "12" in current_format or "16" in current_format:
                        self.converter.OutputPixelFormat = pylon.PixelType_Mono16
                    else:
                        self.converter.OutputPixelFormat = pylon.PixelType_Mono8
                else:
                    # 컬러 포맷은 BGR로 변환
                    self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
                    
                print(f"[INFO] Converter set for: {current_format}")

            print("[INFO] Supported PixelFormats:")
            formats = pixel_format_node.GetSymbolics()
            for fmt in formats:
                print("  -", fmt)

            # Set PixelFormat
            try:
                pixel_format_node.SetValue("BayerBG8")  # Mono8 대신 BayerBG8 (컬러 지원)
                print("[INFO] PixelFormat set to BayerBG8")
            except Exception as e:
                print(f"[WARN] Failed to set PixelFormat to BayerBG8: {e}")

            # Set TriggerMode
            trigger_mode_node = nodemap.GetNode("TriggerMode")
            if trigger_mode_node:
                try:
                    trigger_mode_node.SetValue("Off")
                    print("[INFO] TriggerMode set to Off")
                except Exception as e:
                    print(f"[WARN] Failed to set TriggerMode to Off: {e}")

            # Set ExposureAuto
            exposure_auto_node = nodemap.GetNode("ExposureAuto")
            if exposure_auto_node:
                try:
                    exposure_auto_node.SetValue("Continuous")
                    print("[INFO] ExposureAuto set to Continuous")
                except Exception as e:
                    print(f"[WARN] Failed to set ExposureAuto to Continuous: {e}")

            # GigE settings
            if self.camera.IsGigE():
                try:
                    # 패킷 크기 최적화 (작게 시작)
                    packet_size = min(1500, self.camera.GevSCPSPacketSize.GetMax())
                    self.camera.GevSCPSPacketSize.SetValue(packet_size)
                    
                    # 프레임 전송 지연 설정 (대역폭 제한)
                    self.camera.GevSCPD.SetValue(1000)  # Inter-packet delay (microseconds)
                    
                    # 하트비트 타임아웃 증가
                    self.camera.GevHeartbeatTimeout.SetValue(timeout)
                    
                    # Frame retention 설정
                    if hasattr(self.camera, 'GevStreamChannelSelector'):
                        self.camera.GevStreamChannelSelector.SetValue(0)
                        if hasattr(self.camera, 'GevSCDA'):
                            self.camera.GevSCDA.SetValue(self.camera.GevSCDA.GetMax())
                    
                    print(f"[INFO] GigE settings applied: PacketSize={packet_size}, InterPacketDelay=1000, Timeout={timeout}")
                    
                except Exception as e:
                    print(f"[WARN] Failed to apply GigE settings: {e}")

            # 버퍼 설정 최적화
            try:
                self.camera.MaxNumBuffer = 50  # 버퍼 수 증가
                # Grab 전략을 One by One으로 변경 (안정성 우선)
                self.camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
                print(f"[INFO] Buffer settings: MaxNumBuffer=50, Strategy=OneByOne")
            except Exception as e:
                print(f"[WARN] Failed to apply buffer settings: {e}")

            # 프레임 레이트 제한 (선택사항)
            try:
                acquisition_framerate_node = nodemap.GetNode("AcquisitionFrameRateEnable")
                if acquisition_framerate_node:
                    acquisition_framerate_node.SetValue(True)
                    framerate_node = nodemap.GetNode("AcquisitionFrameRate")
                    if framerate_node:
                        framerate_node.SetValue(10.0)  # 10 FPS로 제한
                        print("[INFO] FrameRate limited to 10 FPS")
            except Exception as e:
                print(f"[WARN] Failed to set FrameRate: {e}")
        except Exception as e:
            print(f"[WARN] Failed to CAM : {e}")

    def grab_frame(self):
        if self.is_error or not self.camera.IsGrabbing():
            print("[WARN] Camera is not grabbing, cannot grab frame")
            return None
        try:
            grab_result = self.camera.RetrieveResult(10000, pylon.TimeoutHandling_ThrowException)
            if grab_result.GrabSucceeded():
                image = self.converter.Convert(grab_result)
                frame = image.GetArray()
                frame = self.convert_frame_for_display(frame)
                print("[INFO] Frame grabbed successfully")
                grab_result.Release()
                return frame
            else:
                print(f"[WARN] Grab failed: ErrorCode={grab_result.ErrorCode}, ErrorDescription={grab_result.ErrorDescription}")
                grab_result.Release()
                return None
        except Exception as e:
            print(f"[ERROR] Grab failed with exception: {e}")
            return None

    def read_cam(self):
        if self.is_error or not self.camera.IsGrabbing():
            print("[WARN] Camera is not grabbing, cannot read frame")
            return None, None
        try:
            # 타임아웃을 더 길게 설정하고 여러 번 시도
            for attempt in range(3):
                grab_result = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_Return)
                if grab_result.GrabSucceeded():
                    image = self.converter.Convert(grab_result)
                    frame = image.GetArray()
                    frame = self.convert_frame_for_display(frame)
                    frame2 = frame.copy()
                    grab_result.Release()
                    return frame, frame2
                else:
                    if grab_result.ErrorCode != 0:
                        # 에러가 있을 때만 로그 출력 (스팸 방지)
                        if attempt == 2:  # 마지막 시도에서만 출력
                            print(f"[WARN] Grab failed after 3 attempts: ErrorCode={grab_result.ErrorCode}")
                    grab_result.Release()
            return None, None
        except Exception as e:
            print(f"[ERROR] Grab failed with exception: {e}")
            return None, None
        
    def capture_img(self, img, img_format):
        save_path = self.app.config_data["SAVE_PATH"]
        if not save_path.endswith("\\"):
            save_path += "\\"
        img = self.convert_frame_for_display(img)
        os.makedirs(save_path, exist_ok=True)

        base_name = get_basename(save_path)
        file_name = generate_next_filename(save_path, f"{base_name}_", f".{img_format}")
        full_path = save_path + file_name

        try:
            cv2.imwrite(full_path, img)
            return True, file_name
        except Exception as e:
            return False, e

    def convert_frame_for_display(self, frame):
        """OpenCV 디스플레이용으로 프레임 변환"""
        if len(frame.shape) == 3:  # 컬러 이미지인 경우
            # RGB를 BGR로 변환 (OpenCV는 BGR 순서를 사용)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            # print("[DEBUG] Applied RGB to BGR conversion")
        return frame
    
    def quit(self):
        if self.camera:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
            self.camera.Close()
