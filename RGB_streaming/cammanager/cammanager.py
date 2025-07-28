import cv2
from datetime import datetime

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
            return frame
        
        return None
    
    def capture_img(self, img, img_format):
        save_path = self.app.config_data["SAVE_PATH"]
        if save_path[-1] != "/":
            save_path += "/"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"RGB_capture_{timestamp}.{img_format}"
        save_path += file_name

        cv2.imwrite(save_path, img)
    
    def quit(self):
        self.cam.release()