from PySide6.QtCore import QDateTime
import inspect
import platform
import re

class Logger:
    """싱글톤 로거 클래스"""
    _instance = None
    _log_callback = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def set_callback(cls, callback):
        """UI의 로그 콜백 설정"""
        cls._log_callback = callback
    
    @classmethod
    def log(cls, message, skip_frames=1):  # ← skip_frames 추가
        """로그 메시지 출력"""
        # 호출 위치 정보 (skip_frames만큼 거슬러 올라감)
        frame = inspect.currentframe()
        for _ in range(skip_frames):
            frame = frame.f_back
        
        os_name = platform.system()
        sep = '\\' if os_name == "Windows" else '/'
        filename = frame.f_code.co_filename.split(sep)[-1]
        lineno = frame.f_lineno
        funcname = frame.f_code.co_name
        
        # 타임스탬프
        timestamp = QDateTime.currentDateTime().toString("HH:mm:ss.zzz")
        
        # 포맷팅
        level = re.search(r'\[([^\]]*)\]', message)
        if level is None:
            level = "INFO"
            message = f"[{level}] {message}"
        else:
            level = level.group(1)
        log_msg = f"[{timestamp}] [{filename}:{lineno} {funcname}()] {message}"
        print(log_msg)
        
        # UI 콜백 호출
        if cls._log_callback:
            try:
                cls._log_callback(log_msg, level)
            except Exception as e:
                print(f"로그 콜백 오류: {e}")
        
        return log_msg


# 편의 함수
def log(message):
    """로그 출력 (어디서든 사용 가능)"""
    return Logger.log(message, skip_frames=2)