import asyncio
import threading

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
from comm_manager.ethercat_manager import EtherCATManager

# ui 모듈
from ui.screens.mainscreen import MainScreen
from ui.screens.manualscreen import ManualScreen
from ui.screens.timescreen import TimeScreen
from ui.screens.servoscreen import ServoScreen

# 각종 설정
from common.consts import (
    TCP_HOST,
    TCP_PORT,
    MODBUS_TYPE,
)
from common.config import (
    MODBUS_RTU_CONFIG,
    MODBUS_TCP_CONFIG,
    EHTERCAT_CONFIG,
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
        self.gpio_controller = GPIOController(self.event_manager)

        # Modbus 매니저
        if MODBUS_TYPE == "RTU":
            self.modbus_manager = ModbusManager(self.event_manager, MODBUS_RTU_CONFIG)
        elif MODBUS_TYPE == "TCP":
            self.modbus_manager = ModbusManager(self.event_manager, MODBUS_TCP_CONFIG)
        self.modbus_manager.start()
        # EtherCAT 매니저
        self.ethercat_manager = EtherCATManager(self.event_manager, EHTERCAT_CONFIG)
        self.ethercat_manager.start()

        self.start_comm()

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
        self.event_manager.create_queue("modbus_queue")
        self.event_manager.create_queue("ethercat_queue")

    def start_comm(self):
        comm_thread = threading.Thread(target=self.start_comm_thread, daemon=True)
        comm_thread.start()
        
    def start_comm_thread(self):
        asyncio.create_task(self.process_main_loop())

    async def process_main_loop(self):
        await asyncio.gather(
            self.gpio_controller.process_task(),
            self.ethercat_manager.process_task(),
            self.modbus_manager.process_task()
        )

    # async def main_event_loop(self):
    #     """메인 이벤트 루프 - 우선순위 기반 처리"""
    #     self.running = True
    #     logging.info("통신 관리자 시작")
        
    #     while self.running:
    #         current_time = time.time()
            
    #         # 1단계: GPIO 인터럽트 즉시 처리 (최고 우선순위)
    #         if self.gpio_interrupt_event.is_set():
    #             await self._handle_gpio_interrupt()
    #             self.gpio_interrupt_event.clear()
    #             continue  # GPIO 처리 후 다시 루프 시작
            
    #         # 2단계: 주기적 GPIO 스캔
    #         if self._should_execute(current_time, self.gpio_state):
    #             await self._process_gpio_scan()
    #             self.gpio_state['last_scan'] = current_time
    #             continue  # GPIO 우선 처리
            
    #         # 3단계: GPIO 명령 큐 처리
    #         if self.task_queues[Priority.GPIO]:
    #             task = self.task_queues[Priority.GPIO].popleft()
    #             await self._execute_gpio_task(task)
    #             continue  # GPIO 명령 우선 처리
            
    #         # 4단계: EtherCAT 처리 (GPIO가 없을 때만)
    #         if self._should_execute(current_time, self.ethercat_state):
    #             await self._process_ethercat()
    #             self.ethercat_state['last_scan'] = current_time
    #             continue
            
    #         # 5단계: EtherCAT 명령 큐 처리
    #         if self.task_queues[Priority.ETHERCAT]:
    #             task = self.task_queues[Priority.ETHERCAT].popleft()
    #             await self._execute_ethercat_task(task)
    #             continue
            
    #         # 6단계: Modbus 처리 (다른 작업이 없을 때만)
    #         if self._should_execute(current_time, self.modbus_state):
    #             await self._process_modbus()
    #             self.modbus_state['last_scan'] = current_time
    #             continue
            
    #         # 7단계: Modbus 명령 큐 처리
    #         if self.task_queues[Priority.MODBUS]:
    #             task = self.task_queues[Priority.MODBUS].popleft()
    #             await self._execute_modbus_task(task)
    #             continue
            
    #         # 8단계: 모든 작업이 없으면 짧은 대기
    #         await asyncio.sleep(0.0001)  # 100μs 대기
    
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