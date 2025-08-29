from kivy.config import Config

# 전체화면 세팅
Config.set("graphics", "fullscreen", "1")
Config.set("graphics", "borderless", "1")

from kivy.core.text import LabelBase
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, NoTransition

# 내부 모듈
from gpio.gpiocontroller import GPIOController
from comm_manager.tcp_server import TCPServer
from comm_manager.commandhandler import CommandHandler
from comm_manager.modbus_manager import ModbusManager
from comm_manager.ethernet_ip_manager import EthernetIPManager

# ui 모듈
from ui.screens.mainscreen import MainScreen
from ui.screens.manualscreen import ManualScreen
from ui.screens.timescreen import TimeScreen
from ui.screens.servoscreen import ServoScreen

# 각종 설정
from common.consts import (
    CommType,
    TCP_HOST,
    TCP_PORT,
    USE_SLAVE,
    SLAVE_IP,
    SLAVE_PORT,
    COMM_MODE
)
from common.config import (
    MODBUS_RTU_CONFIG,
    MODBUS_TCP_CONFIG,
    ETHERNET_IP_CONFIG,
    load_config,
    update_config,
    save_config
)
from common.utils import EventManager

# 로그
from common.logger import setup_logger

# 한글 폰트 등록
LabelBase.register(name="NanumGothic", fn_regular="/usr/share/fonts/truetype/nanum/NanumGothic.ttf")

class TouchApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.listener = setup_logger()
        self.config_data = load_config() # 시작 시 설정 불러오기
        self.event_manager = EventManager()

    def build(self):
        # GPIO 컨트롤러 설정
        if USE_SLAVE:
            self.gpio_controller = GPIOController(
                self.event_manager,
                slave_ip=SLAVE_IP,
                slave_port=SLAVE_PORT
            )
        else:
            self.gpio_controller = GPIOController(self.event_manager)

        # 통신 매니저
        match COMM_MODE:
            case CommType.MODBUS_RTU:
                # Modbus 매니저
                self.comm_manager = ModbusManager(self.event_manager, MODBUS_RTU_CONFIG)
            case CommType.MODBUS_TCP:
                # Modbus 매니저
                self.comm_manager = ModbusManager(self.event_manager, MODBUS_TCP_CONFIG)
            case CommType.ETHERNET_IP:
                # Ethernet/IP 매니저
                self.comm_manager = EthernetIPManager(self.event_manager, ETHERNET_IP_CONFIG)
            case _:
                raise ValueError(f"Communication type error: not registered type [{COMM_MODE.name}]")

        self.comm_manager.start()

        # PC로부터 받을 패킷에 대한 커맨드 핸들러
        self.cmd_handler = CommandHandler(self.gpio_controller, self.config_data)

        # TCP 서버 설정
        self.tcp_server = TCPServer(
            host = TCP_HOST,
            port = TCP_PORT,
            handler_func = self.handle_tcp_command
        )
        self.tcp_server.start()

        self.sm = ScreenManager()
        self.sm.transition = NoTransition()
        self.sm.add_widget(MainScreen(name='main', gpio=self.gpio_controller))
        self.sm.add_widget(ManualScreen(name='manual', gpio=self.gpio_controller))
        self.sm.add_widget(TimeScreen(name='time', gpio=self.gpio_controller))
        self.sm.add_widget(ServoScreen(name='servo', gpio=self.gpio_controller))

        return self.sm
    
    def setup_message_queues(self):
        self.event_manager.create_queue("gpio_queue")
        self.event_manager.create_queue("comm_queue")
        self.event_manager.create_queue("gpio_queue")

    # 패킷 처리하는 함수. 추후 패킷 구조 정하면 다시 짜야 함
    def handle_tcp_command(self, cmd):
        cmd = cmd.strip().upper()
        return self.cmd_handler.handle(cmd)
    
    def update_config(self, option_name, option_value):
        self.config_data = update_config(option_name, option_value)
        
    def on_stop(self):
        self.gpio_controller.stop()
        self.comm_manager.stop()
        save_config(self.config_data) # 종료 시 설정 저장
        self.listener.stop()

if __name__ == '__main__':
    TouchApp().run()