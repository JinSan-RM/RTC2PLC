import socket
import threading

class TCPServer:
    def __init__(self, host, port, handler_func):
        self.host = host
        self.port = port
        self.handler = handler_func  # 예: lambda cmd: gpio_controller.process(cmd)

    def start(self):
        threading.Thread(target = self.run_server, daemon = True).start()

    def run_server(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"[TCP] 서버 대기 중: {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                with conn:
                    print(f"[TCP] 연결됨: {addr}")
                    while True:
                        data = conn.recv(1024)
                        if not data:
                            break
                        cmd = data.decode().strip().upper()
                        result = self.handler(cmd)
                        conn.sendall(result.encode())