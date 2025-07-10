from rpiconfig.rpiconfig import MANUAL_PARTS

class CommandHandler:
    def __init__(self, gpio, cfg):
        self.gpio = gpio
        self.cfg = cfg
        # 패킷 받아서 처리해야 하는 건 플라스틱 분류 별 블로워 처리이므로, 분류 별로 커맨드 추가 필요
        # 일단 구체적으로 정해놓지 않았으므로 임의로 만들어놓겠다.
        self.commands = {
            "TYPE_1" : self.on_first_blower,
            "TYPE_2" : self.on_second_blower,
            "TYPE_3" : self.on_third_blower,
        }

    def on_first_blower(self):
        self.gpio.pulse(MANUAL_PARTS["sol"][1], self.cfg["BLOWER_1"]["delay"], self.cfg["BLOWER_1"]["duration"])
        return "BLOWER 1"

    def on_second_blower(self):
        self.gpio.pulse(MANUAL_PARTS["sol"][2], self.cfg["BLOWER_2"]["delay"], self.cfg["BLOWER_2"]["duration"])
        return "BLOWER 2"
    
    def on_third_blower(self):
        self.gpio.pulse(MANUAL_PARTS["sol"][3], self.cfg["BLOWER_3"]["delay"], self.cfg["BLOWER_3"]["duration"])
        return "BLOWER 3"

    def handle(self, cmd):
        action = self.commands.get(cmd.strip().upper())
        if action:
            return action()
        return "UNKNOWN COMMAND"