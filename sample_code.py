import time
from CAMController import CAMController
from PLCController import XGTController
import conf

# 역매핑 생성 (분류 문자열 -> 클래스 ID)
INV_CLASS_MAPPING = {v: k for k, v in conf.CLASS_MAPPING.items()}

# 컨트롤러 초기화
cam = CAMController(conf.HOST, conf.EVENT_PORT, conf.CLASS_MAPPING)
plc = XGTController(conf.PLC_IP, conf.PLC_PORT)

# 콜백 함수 정의
def handle_classification(classification):
    class_id = INV_CLASS_MAPPING.get(classification, None)
    if class_id is not None:
        success = plc.write_d_and_set_m300(class_id)
        if success:
            print(f"Successfully wrote {class_id} to D00000 and set M300")
        else:
            print(f"Failed to write to PLC for classification: {classification}")
    else:
        print(f"Unknown classification: {classification}, skipping PLC write")

# 카메라 이벤트 수신 시작
cam.start_listening(handle_classification)
print("Started listening for camera events. Press Ctrl+C to stop.")

# 프로그램 지속 실행 및 중지 처리
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
    cam.stop_listening()
    plc.disconnect()
    print("Stopped.")