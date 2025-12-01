# coordinator.py
import socket
import json
import threading
import time
from XGT_run import XGTTester
from matcher import SkipOnTimeoutMatcher

class SkipBasedCoordinator:
    def __init__(self, belt_speed=1.0, camera_distance=0.5):
        self.xgt = XGTTester(ip="192.168.1.3", port=2004)
        self.xgt.connect()
        
        expected_delay = camera_distance / belt_speed
        
        self.matcher = SkipOnTimeoutMatcher(
            expected_delay=expected_delay,
            tolerance=0.2,  # 200ms 허용 오차
            timeout=2.0     # 2초 타임아웃
        )
        
        self.event_counter = 0
        self.running = True
    
    def start(self):
        # Vision 리스너
        threading.Thread(target=self.listen_vision, daemon=True).start()
        
        # Breeze 리스너
        threading.Thread(target=self.listen_breeze, daemon=True).start()
        
        # 청소 루프
        threading.Thread(target=self.cleanup_loop, daemon=True).start()
        
        # 통계 출력
        threading.Thread(target=self.stats_loop, daemon=True).start()
        
        print("Skip 방식 Coordinator 시작...")
        print(f"예상 지연: {self.matcher.expected_delay:.3f}s")
        print(f"허용 오차: ±{self.matcher.tolerance:.3f}s")
        print(f"타임아웃: {self.matcher.timeout:.1f}s")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n종료 중...")
            self.running = False
    
    def listen_vision(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', 5000))
        server.listen(1)
        
        print("Vision 리스너 대기 중 (port 5000)...")
        
        while self.running:
            try:
                conn, addr = server.accept()
                print(f"Vision 연결됨: {addr}")
                
                buffer = ""
                while self.running:
                    data = conn.recv(1024).decode('utf-8')
                    if not data:
                        break
                    
                    buffer += data
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        try:
                            event = json.loads(line)
                            self.event_counter += 1
                            
                            x_pos = event.get('x_position', 0)
                            self.matcher.on_vision_event(self.event_counter, x_pos)
                            
                        except json.JSONDecodeError:
                            continue
                
            except Exception as e:
                if self.running:
                    print(f"Vision 리스너 오류: {e}")
                    time.sleep(1)
    
    def listen_breeze(self):
        while self.running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect(('169.254.112.233', 2500))
                print("Breeze 연결 성공")
                
                buffer = ""
                while self.running:
                    data = sock.recv(1024).decode('utf-8')
                    if not data:
                        break
                    
                    buffer += data
                    while '\r\n' in buffer:
                        message, buffer = buffer.split('\r\n', 1)
                        try:
                            msg_json = json.loads(message)
                            
                            if msg_json.get('Event') == 'PredictionObject':
                                inner = json.loads(msg_json.get('Message', '{}'))
                                descriptors = inner.get('Descriptors', [])
                                
                                if descriptors:
                                    classification = self.map_descriptor(descriptors[0])
                                    result = self.matcher.on_breeze_event(classification)
                                    
                                    if result and result['matched']:
                                        self.send_to_xgt(classification)
                        
                        except json.JSONDecodeError:
                            continue
                
                sock.close()
                
            except Exception as e:
                if self.running:
                    print(f"Breeze 연결 실패: {e}")
                    time.sleep(2)
    
    def map_descriptor(self, descriptor_value):
        CLASS_MAPPING = {
            0: "_", 1: "PP", 2: "HDPE", 3: "PS",
            4: "LDPE", 5: "ABS", 6: "PET"
        }
        return CLASS_MAPPING.get(descriptor_value, "Unknown")
    
    def send_to_xgt(self, classification):
        """XGT PLC로 신호 전송"""
        ADDRESS_MAP = {
            'HDPE': 0x88, 'PS': 0x89, 'PP': 0x8A,
            'LDPE': 0x8B, 'ABS': 0x8C, 'PET': 0x8D
        }
        
        address = ADDRESS_MAP.get(classification)
        if address:
            self.xgt.process_bit_off()
            success = self.xgt.write_bit_packet(address=address, onoff=1)
            if success:
                self.xgt.schedule_bit_off(address=address, delay=0.1)
                print(f"[XGT] {classification} 신호 전송 (P{address:X})")
    
    def cleanup_loop(self):
        """주기적 정리"""
        while self.running:
            time.sleep(1)
            self.matcher.cleanup_old_events()
    
    def stats_loop(self):
        """통계 출력"""
        while self.running:
            time.sleep(10)  # 10초마다
            print(self.matcher.get_stats_report())

if __name__ == '__main__':
    coordinator = SkipBasedCoordinator(
        belt_speed=1.0,         # 실측값으로 조정
        camera_distance=0.5     # 실측값으로 조정
    )
    coordinator.start()