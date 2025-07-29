import cv2

import os

from common.utils import generate_next_filename, get_basename

class CamManager:
    is_error = False

    def __init__(self, app):
        self.app = app
        self.cam = cv2.VideoCapture(0)
        if not self.cam.isOpened():
            print("can't open camera")
            self.is_error = True
            return
        
    def read_cam(self):
        ret, frame = self.cam.read()
        if ret:
            frame2 = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return frame, frame2
        
        return None, None
    
    def capture_img(self, img, img_format):
        save_path = self.app.config_data["SAVE_PATH"]
        if save_path[-1] != "\\":
            save_path += "\\"

        os.makedirs(save_path, exist_ok=True)

        # 폴더명_000000.확장자명 으로 파일 생성할 것
        base_name = get_basename(save_path)
        file_name = generate_next_filename(save_path, f"{base_name}_", f".{img_format}")
        save_path += file_name

        try:
            cv2.imwrite(save_path, img)
            return True, file_name
        except Exception as e:
            return False, e
    
    def quit(self):
        self.cam.release()