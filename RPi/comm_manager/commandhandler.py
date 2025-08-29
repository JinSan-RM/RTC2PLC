from common.config import PIN_MAPPING

class CommandHandler:
    _instance = None
    _initialized = False

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, gpio, cfg):
        if not self._initialized:
            self.gpio = gpio
            self.cfg = cfg
            # 패킷 받아서 처리해야 하는 건 플라스틱 분류 별 블로워 처리이므로, 분류 별로 커맨드 추가 필요
            # 일단 구체적으로 정해놓지 않았으므로 임의로 만들어놓겠다.
            self.commands = {
                "BLOWER_1" : (self.on_blower, 1),
                "BLOWER_2" : (self.on_blower, 2),
                "BLOWER_3" : (self.on_blower, 3)
            }

            self._initialized = True

    def on_blower(self, k, n):
        self.gpio.pulse(PIN_MAPPING["sol"][n][1], PIN_MAPPING["sol"][n][2], self.cfg[k]["delay"], self.cfg[k]["duration"])
        return k

    def handle(self, cmd):
        k = cmd.strip().upper()
        tpl = self.commands.get(k)
        action = tpl[0]
        args = tpl[1:]
        if action:
            return action(k, *args)
        return "UNKNOWN COMMAND"