from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
import threading

# 내부 모듈
from gpio.controller import GPIOController
from tcpserver.tcp_server import TCPServer
from tcpserver.commandhandler import CommandHandler

# ui 모듈
from ui.screens.mainscreen import MainScreen
from ui.screens.manualscreen import ManualScreen
from ui.screens.timescreen import TimeScreen
from ui.screens.servoscreen import ServoScreen

from common.config import TCP_HOST, TCP_PORT, USE_TCP_SLAVE, TCP_SLAVE_1, load_config, save_config

class TouchApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config_data = load_config() # 시작 시 설정 불러오기

    def build(self):
        # GPIO 컨트롤러 설정
        if USE_TCP_SLAVE:
            self.gpio_controller = GPIOController(slave_ip = TCP_SLAVE_1)
        else:
            self.gpio_controller = GPIOController()

        self.cmd_handler = CommandHandler(self.gpio_controller, self.config_data)

        # TCP 서버 설정
        self.tcp_server = TCPServer(
            host = TCP_HOST,
            port = TCP_PORT,
            handler_func = self.handle_tcp_command
        )
        threading.Thread(target = self.tcp_server.run_server, daemon = True).start()

        self.sm = ScreenManager()
        self.sm.add_widget(MainScreen(name='main', gpio = self.gpio_controller))
        self.sm.add_widget(ManualScreen(name='manual', gpio = self.gpio_controller))
        self.sm.add_widget(TimeScreen(name='time', gpio = self.gpio_controller))
        self.sm.add_widget(ServoScreen(name='servo', gpio = self.gpio_controller))

        return self.sm
    
    # 패킷 처리하는 함수. 추후 패킷 구조 정하면 다시 짜야 함
    def handle_tcp_command(self, cmd):
        cmd = cmd.strip().upper()
        return self.cmd_handler.handle(cmd)
    
    def update_config(self, option_name, option_value):
        names = option_name.split(" ")
        changed = False
        if len(names) == 1:
            if self.config_data[option_name]:
                self.config_data[option_name] = option_value
                changed = True
        elif len(names) == 2:
            if self.config_data[names[0]][names[1]]:
                self.config_data[names[0]][names[1]] = option_value
                changed = True
        if changed:
            save_config(self.config_data)
        
    def on_stop(self):
        self.gpio_controller.cleanup()
        save_config(self.config_data) # 종료 시 설정 저장

if __name__ == '__main__':
    TouchApp().run()