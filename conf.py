HOST = '192.168.250.130'  # 카메라 IP 주소
EVENT_PORT = 2500

CLASS_MAPPING = {
        0: "-",
        1: "PET Bottle",
        2: "PET sheet",
        3: "PET G",
        4: "PVC",
        5: "PC",
        6: "Background"
    }

# 플라스틱 타입 매핑
PLASTIC_MAPPING = {
        "PET Bottle": "PET",
        "PET sheet": "PET",
        "PET G": "PET",
        "PVC": "PVC",
        "PC": None,
        "Background": None,
        "-": None
    }

PLC_IP = '192.168.250.120'
PLC_PORT = 2004
PLC_D_ADDRESS = 'D00000'
PLC_M_ADDRESS = 'M300'