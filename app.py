import tkinter as tk
from tkinter import messagebox, scrolledtext
import binascii
import logging
import threading
import struct

from src.plc.PLCController import XGTController
from src.rtc.CAMController import CAMController
from src.rtc.breeze import BreezeController
from src.config import conf

logging.basicConfig(level=logging.INFO)

class TestToolApp:
    def __init__(self, root):
        self.root = root
        root.title("PLC/CAM/Breeze 통합 테스트툴")
        self.plc = None
        self.cam = None
        self.breeze = None
        self.cam_streaming = False

        # PLC 연결
        tk.Label(root, text="PLC IP:").grid(row=0, column=0)
        self.plc_ip = tk.Entry(root)
        self.plc_ip.insert(0, conf.PLC_IP)
        self.plc_ip.grid(row=0, column=1)
        tk.Label(root, text="Port:").grid(row=0, column=2)
        self.plc_port = tk.Entry(root)
        self.plc_port.insert(0, str(conf.PLC_PORT))
        self.plc_port.grid(row=0, column=3)
        self.plc_conn_btn = tk.Button(root, text="PLC Connect", command=self.connect_plc)
        self.plc_conn_btn.grid(row=0, column=4)
        self.plc_disc_btn = tk.Button(root, text="PLC Disconnect", command=self.disconnect_plc)
        self.plc_disc_btn.grid(row=0, column=5)

        # D값 쓰기
        tk.Label(root, text="D주소:").grid(row=1, column=0)
        self.d_addr = tk.Entry(root)
        self.d_addr.insert(0, conf.PLC_D_ADDRESS)
        self.d_addr.grid(row=1, column=1)
        tk.Label(root, text="값:").grid(row=1, column=2)
        self.d_value = tk.Entry(root)
        self.d_value.insert(0, "1")
        self.d_value.grid(row=1, column=3)
        self.d_write_btn = tk.Button(root, text="D값 쓰기", command=self.write_d_value)
        self.d_write_btn.grid(row=1, column=4)

        # M비트 제어
        tk.Label(root, text="M주소:").grid(row=2, column=0)
        self.m_addr = tk.Entry(root)
        self.m_addr.insert(0, conf.PLC_M_ADDRESS.replace("M", ""))
        self.m_addr.grid(row=2, column=1)
        self.m_on_btn = tk.Button(root, text="M ON", command=lambda: self.write_m_bit(1))
        self.m_on_btn.grid(row=2, column=2)
        self.m_off_btn = tk.Button(root, text="M OFF", command=lambda: self.write_m_bit(0))
        self.m_off_btn.grid(row=2, column=3)
        self.m_read_btn = tk.Button(root, text="M 상태확인", command=self.read_m_bit)
        self.m_read_btn.grid(row=2, column=4)

        # 패킷 직접 전송
        tk.Label(root, text="패킷(hex):").grid(row=3, column=0)
        self.packet_entry = tk.Entry(root, width=60)
        self.packet_entry.grid(row=3, column=1, columnspan=3)
        tk.Label(root, text="설명:").grid(row=3, column=4)
        self.packet_desc = tk.Entry(root, width=15)
        self.packet_desc.grid(row=3, column=5)
        self.packet_send_btn = tk.Button(root, text="패킷 전송", command=self.send_custom_packet)
        self.packet_send_btn.grid(row=3, column=6)
        self.packet_response = tk.Label(root, text="응답: -", fg="blue")
        self.packet_response.grid(row=4, column=0, columnspan=7)

        # Breeze 제어
        self.breeze_start_btn = tk.Button(root, text="Breeze 켜기", command=self.start_breeze)
        self.breeze_start_btn.grid(row=5, column=0)
        self.breeze_stop_btn = tk.Button(root, text="Breeze 끄기", command=self.stop_breeze)
        self.breeze_stop_btn.grid(row=5, column=1)

        # CAM 제어
        self.cam_conn_btn = tk.Button(root, text="CAM Streaming Connect", command=self.connect_cam)
        self.cam_conn_btn.grid(row=6, column=0)
        self.cam_disc_btn = tk.Button(root, text="CAM Streaming Disconnect", command=self.disconnect_cam)
        self.cam_disc_btn.grid(row=6, column=1)
        
        # 실시간 로그/결과 표시용 ScrolledText 추가
        self.log_widget = scrolledtext.ScrolledText(root, width=100, height=15, state='disabled')
        self.log_widget.grid(row=8, column=0, columnspan=7, padx=5, pady=5)

        self.status = tk.Label(root, text="상태: 대기중")
        self.status.grid(row=7, column=0, columnspan=7)

    # ---------- PLC ----------
    def connect_plc(self):
        ip = self.plc_ip.get()
        port = int(self.plc_port.get())
        self.plc = XGTController(ip, port)
        if self.plc.connect():
            self.status.config(text="PLC 연결됨")
        else:
            self.status.config(text="PLC 연결 실패")

    def disconnect_plc(self):
        if self.plc:
            self.plc.disconnect()
            self.status.config(text="PLC 연결 해제")

    def write_d_value(self):
        if not self.plc or not self.plc.connected:
            messagebox.showerror("오류", "PLC가 연결되어 있지 않습니다.")
            return
        value = int(self.d_value.get())
        addr = self.d_addr.get()
        # address_ascii 생성 (예: 'D00001' → b'%DB1')
        if addr.startswith("D"):
            num = int(addr[1:])
            address_ascii = b'\x25\x44\x42' + str(num).encode()
        else:
            address_ascii = addr.encode()
        data_bytes = struct.pack('=h', value)
        packet = self.plc.create_write_packet(address_ascii, data_bytes)
        self.append_log(f"[TX] D값 쓰기 패킷(hex): {packet.hex()}")
        success, response = self.plc.send_packet_to_plc(packet, description="D값 쓰기")
        if isinstance(response, bytes):
            self.append_log(f"[RX] 응답 패킷(hex): {response.hex()}")
        else:
            self.append_log(f"[RX] 응답 없음 또는 오류")
        if success:
            self.status.config(text=f"{addr} 쓰기 성공")
        else:
            self.status.config(text=f"{addr} 쓰기 실패 (재연결 필요)")

    def write_m_bit(self, value):
        if not self.plc or not self.plc.connected:
            messagebox.showerror("오류", "PLC가 연결되어 있지 않습니다.")
            return
        m_addr = int(self.m_addr.get())
        # 반드시 비트 쓰기 전용 함수 사용
        success = self.plc.write_mx_bit(m_addr, value)
        self.append_log(f"M{m_addr} {'ON' if value else 'OFF'} 요청")
        if success:
            self.append_log(f"M{m_addr} {'ON' if value else 'OFF'} 성공")
            self.status.config(text=f"M{m_addr} {'ON' if value else 'OFF'} 성공")
        else:
            self.append_log(f"M{m_addr} {'ON' if value else 'OFF'} 실패")
            self.status.config(text=f"M{m_addr} {'ON' if value else 'OFF'} 실패")

    def read_m_bit(self):
        if not self.plc or not self.plc.connected:
            messagebox.showerror("오류", "PLC가 연결되어 있지 않습니다.")
            return
        addr = int(self.m_addr.get())
        val = self.plc.read_mx_bit(addr)
        self.append_log(f"M{addr} 상태: {'ON' if val else 'OFF'}")
        if val is not None:
            self.status.config(text=f"M{addr} 상태: {'ON' if val else 'OFF'}")
        else:
            self.status.config(text=f"M{addr} 상태 읽기 실패")

    def send_custom_packet(self):
        if not self.plc or not self.plc.connected:
            messagebox.showerror("오류", "PLC가 연결되어 있지 않습니다.")
            return
        hex_str = self.packet_entry.get().replace(" ", "")
        description = self.packet_desc.get()
        try:
            packet = binascii.unhexlify(hex_str)
        except Exception as e:
            messagebox.showerror("오류", f"Hex 변환 실패: {e}")
            return
        success, response = self.plc.send_packet_to_plc(packet, description)
        self.append_log(f"[TX] 패킷 전송: {packet.hex()}")
        if response:
            self.append_log(f"[RX] 응답 패킷(hex): {response.hex()}")
        if success:
            self.packet_response.config(text=f"성공: {binascii.hexlify(response).decode()}")
        else:
            self.packet_response.config(text=f"실패: {binascii.hexlify(response).decode() if response else 'No response'}")

    # ---------- Breeze ----------
    def start_breeze(self):
        try:
            self.breeze = BreezeController()
            self.breeze.start()
            self.status.config(text="Breeze 실행됨")
        except Exception as e:
            self.status.config(text=f"Breeze 실행 실패: {e}")

    def stop_breeze(self):
        if self.breeze:
            self.breeze.stop()
            self.status.config(text="Breeze 종료")

    # ---------- Breeze ----------
    def start_breeze(self):
        try:
            self.breeze = BreezeController()
            self.breeze.start()
            self.status.config(text="Breeze 실행됨")
        except Exception as e:
            self.status.config(text=f"Breeze 실행 실패: {e}")

    def stop_breeze(self):
        if self.breeze:
            self.breeze.stop()
            self.status.config(text="Breeze 종료")

    # ---------- CAM ----------
    # def connect_cam(self):
    #     def cam_thread():
    #         try:
    #             self.cam = CAMController(
    #                 host=conf.HOST,
    #                 command_port=2000,
    #                 event_port=conf.EVENT_PORT,
    #                 data_stream_port=3000,
    #                 class_mapping=conf.CLASS_MAPPING
    #             )
    #             self.cam.start_command_client()
    #             self.cam_streaming = True
    #             self.status.config(text="CAM Streaming 연결됨")
    #         except Exception as e:
    #             self.status.config(text=f"CAM 연결 실패: {e}")
    #     threading.Thread(target=cam_thread, daemon=True).start()
    
    def connect_cam(self):
        if self.cam_streaming:
            self.append_log("이미 CAM이 연결되어 있습니다.")
            return
        self.cam = CAMController(
            host=conf.HOST,
            command_port=2000,
            event_port=conf.EVENT_PORT,
            data_stream_port=3000,
            class_mapping=conf.CLASS_MAPPING
        )
        try:
            self.cam.initialize_and_start(
                conf.WORKFLOW_PATH,
                self.handle_classification_gui,   # 아래 함수와 연결
                batch_interval=1.0,
                min_predictions=3
            )
            self.cam_streaming = True
            self.append_log("CAM 스트리밍 연결됨")
            self.status.config(text="CAM 스트리밍 연결됨")
        except Exception as e:
            self.append_log(f"CAM 연결 실패: {e}")
            self.status.config(text="CAM 연결 실패")
            
    def disconnect_cam(self):
        if self.cam:
            self.cam.close_command_client()
            self.cam_streaming = False
            self.status.config(text="CAM Streaming 해제")
    
    def handle_classification_gui(self, classification, details):
        msg = (f"[{details['start_time']}] 분류: {classification}, "
            f"Line: {details['start_line']}")
        self.append_log(msg)
        if self.plc and self.plc.connected:
            class_id = {v: k for k, v in conf.CLASS_MAPPING.items()}.get(classification, None)
            if class_id is not None:
                addr = conf.PLC_D_ADDRESS
                num = int(addr[1:])
                address_ascii = b'\x25\x44\x42' + str(num).encode()
                import struct
                data_bytes = struct.pack('=h', class_id)
                packet = self.plc.create_write_packet(address_ascii, data_bytes)
                self.append_log(f"[TX] D00000 쓰기 요청: 값={class_id}")
                self.append_log(f"[TX] D00000 쓰기 패킷(hex): {packet.hex()}")
                success, response = self.plc.send_packet_to_plc(packet, description="D00000 쓰기")
                if isinstance(response, bytes):
                    self.append_log(f"[RX] D00000 응답 패킷(hex): {response.hex()}")
                else:
                    self.append_log(f"[RX] D00000 응답 없음 또는 오류")
                if success:
                    # M300 ON
                    self.append_log("M300 ON 요청")
                    m_packet = self.plc.write_mx_bit(300, 1)
                    # self.append_log(f"[TX] M300 ON 패킷(hex): {m_packet.hex()}")
                    m_success, m_response = self.plc.send_packet_to_plc(m_packet, description="M300 ON")
                    if m_success:
                        self.append_log("M300 ON 성공")
                    # else:
                    #     self.append_log("M300 ON 실패")
                else:
                    self.append_log("D00000 쓰기 실패, M300 설정 건너뜀")
            else:
                self.append_log(f"→ PLC 연동 불필요 (분류: {classification})")
        else:
            self.append_log("PLC가 연결되어 있지 않아 동작 생략")


    #---------- 로그 출력 ----------
    def append_log(self, msg):
        def _append():
            self.log_widget.config(state='normal')
            self.log_widget.insert(tk.END, msg + '\n')
            self.log_widget.see(tk.END)
            self.log_widget.config(state='disabled')
        self.root.after(0, _append)

if __name__ == "__main__":
    root = tk.Tk()
    app = TestToolApp(root)
    root.mainloop()
