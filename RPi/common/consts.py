import os

from enum import Enum, auto

class DeviceRole(Enum):
    MASTER = auto()
    SLAVE = auto()

class PinRole(Enum):
    INPUT = auto()
    OUTPUT = auto()

class MessageType(Enum):
    GPIO_COMMAND = "gpio_command"
    COMM_INPUT = "comm_input"
    COMM_OUTPUT = "comm_output"
    EMERGENCY_STOP = "emergency_stop"

class CommType(Enum):
    MODBUS_RTU = auto()
    MODBUS_TCP = auto()
    ETHERNET_IP = auto()

class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
USE_SLAVE = False
SLAVE_PORT = 8889

TCP_HOST = "0.0.0.0"
TCP_PORT = 8999
SLAVE_IP = "192.168.0.21" # slave rpi의 ip주소. 이거 별도의 설정 파일에서 조정 가능하던지 아니면 다른 방법을 강구해야 한다.

COMM_MODE = CommType.MODBUS_RTU

ETHERNET_IP_DEF = {
    'Implicit': {
        'Input': [
            {
                'Instance': 70,
                'Bytes': [
                    'Mask',
                    'Speed Actual - RPM unit'
                ],
                'Mask': {
                    'Running1(Fwd)': 0b00000100,
                    'Faulted': 0b00000001
                }
            },
            {
                'Instance': 71,
                'Bytes': [
                    'Mask',
                    'Speed Actual - RPM unit'
                ],
                'Mask': {
                    'At Reference': 0b10000000,
                    'Ref From Net': 0b01000000,
                    'Ctrl From Net': 0b00100000,
                    'Ready': 0b00010000,
                    'Running2(Rev)': 0b00001000,
                    'Running1(Fwd)': 0b00000100,
                    'Warning': 0b00000010,
                    'Faulted': 0b00000001
                }
            },
            {
                'Instance': 110,
                'Bytes': [
                    'Mask',
                    'Speed Actual - Hz unit'
                ],
                'Mask': {
                    'Running1(Fwd)': 0b00000100,
                    'Faulted': 0b00000001
                }
            },
            {
                'Instance': 111,
                'Bytes': [
                    'Mask',
                    'Speed Actual - Hz unit'
                ],
                'Mask': {
                    'At Reference': 0b10000000,
                    'Ref From Net': 0b01000000,
                    'Ctrl From Net': 0b00100000,
                    'Ready': 0b00010000,
                    'Running2(Rev)': 0b00001000,
                    'Running1(Fwd)': 0b00000100,
                    'Warning': 0b00000010,
                    'Faulted': 0b00000001
                }
            },
            {
                'Instance': 141,
                'Bytes': [
                    'Status Parameter - 1 data'
                ]
            },
            {
                'Instance': 142,
                'Bytes': [
                    'Status Parameter - 1 data',
                    'Status Parameter - 2 data'
                ]
            },
            {
                'Instance': 143,
                'Bytes': [
                    'Status Parameter - 1 data',
                    'Status Parameter - 2 data',
                    'Status Parameter - 3 data'
                ]
            },
            {
                'Instance': 144,
                'Bytes': [
                    'Status Parameter - 1 data',
                    'Status Parameter - 2 data',
                    'Status Parameter - 3 data',
                    'Status Parameter - 4 data'
                ]
            }
        ],
        'Output': [
            {
                'Instance': 20,
                'Bytes': [
                    'Mask',
                    'Speed Reference - RPM unit (not supported)'
                ],
                'Mask': {
                    'Fault Reset': 0b00000100,
                    'Run Fwd': 0b00000001
                }
            },
            {
                'Instance': 21,
                'Bytes': [
                    'Mask',
                    'Speed Reference - RPM unit (not supported)'
                ],
                'Mask': {
                    'Net Ref': 0b01000000,
                    'Net Ctrl': 0b00100000,
                    'Fault Reset': 0b00000100,
                    'Run Rev': 0b00000010,
                    'Run Fwd': 0b00000001
                }
            },
            {
                'Instance': 100,
                'Bytes': [
                    'Mask',
                    'Speed Reference - Hz unit'
                ],
                'Mask': {
                    'Fault Reset': 0b00000100,
                    'Run Fwd': 0b00000001
                }
            },
            {
                'Instance': 101,
                'Bytes': [
                    'Mask',
                    'Speed Reference - Hz unit'
                ],
                'Mask': {
                    'Net Ref': 0b01000000,
                    'Net Ctrl': 0b00100000,
                    'Fault Reset': 0b00000100,
                    'Run Rev': 0b00000010,
                    'Run Fwd': 0b00000001
                }
            },
            {
                'Instance': 121,
                'Bytes': [
                    'Control Parameter - 1 data'
                ]
            },
            {
                'Instance': 122,
                'Bytes': [
                    'Control Parameter - 1 data',
                    'Control Parameter - 2 data'
                ]
            },
            {
                'Instance': 123,
                'Bytes': [
                    'Control Parameter - 1 data',
                    'Control Parameter - 2 data',
                    'Control Parameter - 3 data'
                ]
            },
            {
                'Instance': 124,
                'Bytes': [
                    'Control Parameter - 1 data',
                    'Control Parameter - 2 data',
                    'Control Parameter - 3 data',
                    'Control Parameter - 4 data'
                ]
            },
        ]
    },
    'Explicit': {
        'Identity Object': {
            'Class': 0x01,
            'Instance': 1,
            'Attribute': {
                'Vendor ID': 1,
                'Device Type': 2,
                'Product Code': 3,
                'Revision': 4,
                'Status': 5,
                'Serial Number': 6,
                'Product Name': 7
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Reset': 0x05,
                'Set Attribute Single': 0x10
            }
        },
        'Motor Data Object': {
            'Class': 0x28,
            'Instance': 1,
            'Attribute': {
                'Motor Type': 3,
                'Motor Rated Current': 6,
                'Motor Rated Voltage': 7
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'Control Supervisor Object': {
            'Class': 0x29,
            'Instance': 1,
            'Attribute': {
                'Forward Run Cmd': 3,
                'Reverse Run Cmd': 4,
                'NetCtrl': 5,
                'Drive State': 6,
                'Running Forward': 7,
                'Running Reverse': 8,
                'Drive Ready': 9,
                'Drive Fault': 10,
                'Drive Fault Reset': 12,
                'Drive Fault Code': 13,
                'Control From Net': 14,
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'AC Drive Object': {
            'Class': 0x2A,
            'Instance': 1,
            'Attribute': {
                'At Reference': 3,
                'Net Reference': 4,
                'Drive Mode': 6,
                'Speed Actual': 7,
                'Speed Ref': 8,
                'Actual Current': 9,
                'RefFromNet': 29,
                'Actual Hz': 100,
                'Reference Hz': 101,
                'Acceleration Time': 102,
                'Deceleration Time': 103
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'D Group Object': { # 운전 그룹
            'Class': 0x64,
            'Instance': 1,
            'Attribute': {
                'Frequency': 0xA100, # 지령 주파수
                'Acceleration Time': 0xA101, # 가속 시간
                'Deceleration Time': 0xA102, # 감속 시간
                'Set Drive': 0xA103, # 운전 지령 방법
                'Set Frequency': 0xA104, # 주파수 설정 방법
                'St1': 0xA105, # 다단속 주파수 1
                'St2': 0xA106, # 다단속 주파수 2
                'St3': 0xA107, # 다단속 주파수 3
                'Current Output': 0xA108, # 출력 전류
                'RPM': 0xA109, # 전동기 회전수
                'DC Voltage': 0xA10A, # 인버터 직류전압
                'User Select': 0xA10B, # 사용자 선택 표시(출력 전압/출력 파워/토크)
                'Drive Fault': 0xA10C, # 현재 고장 표시
                'Set Rotate Direction': 0xA10D, # 회전 방향 선택
                'Set Drive 2': 0xA10E, # 운전 지령 방법
                'Set Frequency 2': 0xA10F, # 주파수 설정 방법
                'Set Reference Frequency': 0xA110, # PID 제어 기준 값 설정
                'Feedback': 0xA111 # PID 제어 피드백 양
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'F Group Object': { # 기능 그룹 1
            'Class': 0x64,
            'Instance': 2,
            'Attribute': {
                'F0': 0xA200, # 점프 코드
                'F1': 0xA201, # 정/역회전 금지
                'F2': 0xA202, # 가속 패턴
                'F3': 0xA203, # 감속 패턴
                'F4': 0xA204, # 정지 방법 선택
                'F8': 0xA208, # 직류 제동 주파수
                'F9': 0xA209, # 직류 제동 동작 전 출력 차단 시간
                'F10': 0xA20A, # 직류 제동량
                'F11': 0xA20B, # 직류 제동 시간
                'F12': 0xA20C, # 시동 시 직류 제동량
                'F13': 0xA20D, # 시동 시 직류 제동 시간
                'F14': 0xA20E, # 전동기 여자 시간
                'F20': 0xA214, # 조그 주파수
                'F21': 0xA215, # 최대 주파수
                'F22': 0xA216, # 기저 주파수
                'F23': 0xA217, # 시작 주파수
                'F24': 0xA218, # 주파수 상/하한 선택
                'F25': 0xA219, # 주파수 상한 리미트
                'F26': 0xA21A, # 주파수 하한 리미트
                'F27': 0xA21B, # 토크 부스트 선택
                'F28': 0xA21C, # 정방향 토크 부스트 양
                'F29': 0xA21D, # 역방향 토크 부스트 양
                'F30': 0xA21E, # V/F 패턴
                'F31': 0xA21F, # 사용자 V/F 주파수 1
                'F32': 0xA220, # 사용자 V/F 전압 1
                'F33': 0xA221, # 사용자 V/F 주파수 2
                'F34': 0xA222, # 사용자 V/F 전압 2
                'F35': 0xA223, # 사용자 V/F 주파수 3
                'F36': 0xA224, # 사용자 V/F 전압 3
                'F37': 0xA225, # 사용자 V/F 주파수 4
                'F38': 0xA226, # 사용자 V/F 전압 4
                'F39': 0xA227, # 출력 전압 조정
                'F40': 0xA228, # 에너지 절약 운전
                'F50': 0xA232, # 전자 써멀 선택
                'F51': 0xA233, # 전자 써멀 1분 레벨
                'F52': 0xA234, # 전자 써멀 연속 운전 레벨
                'F53': 0xA235, # 전동기 냉각 방식
                'F54': 0xA236, # 과부하 경보 레벨
                'F55': 0xA237, # 과부하 경보 시간
                'F56': 0xA238, # 과부하 트립 선택
                'F57': 0xA239, # 과부하 트립 레벨
                'F58': 0xA23A, # 과부하 트립 시간
                'F59': 0xA23B, # 스톨 방지 선택
                'F60': 0xA23C, # 스톨 방지 레벨
                'F61': 0xA23D, # 감속 중 스톨 방지 시 전압 제한 선택
                'F63': 0xA23F, # 업/다운 주파수 저장 선택
                'F64': 0xA240, # 업/다운 주파수 저장
                'F65': 0xA241, # 업/다운 모드 선택
                'F66': 0xA242, # 업/다운 스텝 주파수
                'F70': 0xA246, # 드로우 운전 모드 선택
                'F71': 0xA247 # 드로우 비율
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'H Group Object': { # 기능 그룹 2
            'Class': 0x64,
            'Instance': 3,
            'Attribute': {
                'H0': 0xA300, # 점프 코드
                'H1': 0xA301, # 고장 이력 1
                'H2': 0xA302, # 고장 이력 2
                'H3': 0xA303, # 고장 이력 3
                'H4': 0xA304, # 고장 이력 4
                'H5': 0xA305, # 고장 이력 5
                'H6': 0xA306, # 고장 이력 지우기
                'H7': 0xA307, # 드웰 주파수
                'H8': 0xA308, # 드웰 시간
                'H10': 0xA30A, # 주파수 점프 선택
                'H11': 0xA30B, # 주파수 점프 하한 1
                'H12': 0xA30C, # 주파수 점프 상한 1
                'H13': 0xA30D, # 주파수 점프 하한 2
                'H14': 0xA30E, # 주파수 점프 상한 2
                'H15': 0xA30F, # 주파수 점프 하한 3
                'H16': 0xA310, # 주파수 점프 상한 3
                'H17': 0xA311, # S자 곡선 시점 기울기
                'H18': 0xA312, # S자 곡선 종점 기울기
                'H19': 0xA313, # 입/출력 결상 보호 선택
                'H20': 0xA314, # 전원 투입과 동시에 기동 선택
                'H21': 0xA315, # 트립 발생 후 리셋 시 기동 선택
                'H22': 0xA316, # 속도 서치 선택
                'H23': 0xA317, # 속도 서치 전류 레벨
                'H24': 0xA318, # 속도 서치 P 게인
                'H25': 0xA319, # 속도 서치 I 게인
                'H26': 0xA31A, # 트립 후 자동 재시동 횟수
                'H27': 0xA31B, # 트립 후 자동 재시동 대기 시간
                'H30': 0xA31E, # 전동기 용량 선택
                'H31': 0xA31F, # 전동기 극수
                'H32': 0xA320, # 전동기 정격 슬립 주파수
                'H33': 0xA321, # 전동기 정격 전류
                'H34': 0xA322, # 전동기 무부하 전류
                'H36': 0xA324, # 전동기 효율
                'H37': 0xA325, # 부하 관성비
                'H39': 0xA327, # 캐리어 주파수 선택(운전음 선택)
                'H40': 0xA328, # 제어 방식 선택
                'H41': 0xA329, # 오토 튜닝
                'H42': 0xA32A, # 고정자 저항(Rs)
                'H44': 0xA32C, # 누설 인덕턴스(Lσ)
                'H45': 0xA32D, # 센서리스 P 게인
                'H46': 0xA32E, # 센서리스 I 게인
                'H47': 0xA32F, # 센서리스 토크 리미트
                'H48': 0xA330, # PWM 모드 선택
                'H49': 0xA331, # PID 제어 선택
                'H50': 0xA332, # PID 피드백 선택
                'H51': 0xA333, # PID 제어기 P 게인
                'H52': 0xA334, # PID 제어기 적분 시간(I 게인)
                'H53': 0xA335, # PID 제어기 미분 시간(D 게인)
                'H54': 0xA336, # PID 제어 모드 선택
                'H55': 0xA337, # PID 출력 주파수 상한 제한
                'H56': 0xA338, # PID 출력 주파수 하한 제한
                'H57': 0xA339, # PID 기준 값 선택
                'H58': 0xA33A, # PID 제어 단위 선택
                'H59': 0xA33B, # PID 출력 반전
                'H60': 0xA33C, # 자기 진단 기능 선택
                'H61': 0xA33D, # 슬립 지연 시간
                'H62': 0xA33E, # 슬립 주파수
                'H63': 0xA33F, # 웨이크 업 레벨
                'H64': 0xA340, # KEB 운전
                'H65': 0xA341, # KEB 동작 시작 레벨
                'H66': 0xA342, # KEB 동작 정지 레벨
                'H67': 0xA343, # KEB 동작 게인
                'H70': 0xA346, # 가/감속 기준 주파수
                'H71': 0xA347, # 가/감속 시간 설정 단위
                'H72': 0xA348, # 전원 투입 시 표시 선택
                'H73': 0xA349, # 모니터 항목 선택
                'H74': 0xA34A, # 전동기 회전수 표시 게인
                'H75': 0xA34B, # 제동 저항 사용률 제한 선택
                'H76': 0xA34C, # 제동 저항 사용률
                'H77': 0xA34D, # 냉각팬 제어
                'H78': 0xA34E, # 냉각팬 이상 시 운전 방법 선택
                'H79': 0xA34F, # 소프트웨어 버전
                'H81': 0xA351, # 제 2 전동기 가속 시간
                'H82': 0xA352, # 제 2 전동기 감속 시간
                'H83': 0xA353, # 제 2 전동기 기저 주파수
                'H84': 0xA354, # 제 2 전동기 V/F 패턴
                'H85': 0xA355, # 제 2 전동기 정방향 토크 부스트
                'H86': 0xA356, # 제 2 전동기 역방향 토크 부스트
                'H87': 0xA357, # 제 2 전동기 스톨 방지 레벨
                'H88': 0xA358, # 제 2 전동기 전자 써멀 1분 레벨
                'H89': 0xA359, # 제 2 전동기 전자 써멀 연속 운전 레벨
                'H90': 0xA35A, # 제 2 전동기 정격 전류
                'H91': 0xA35B, # 파라미터 읽기
                'H92': 0xA35C, # 파라미터 쓰기
                'H93': 0xA35D, # 파라미터 초기화
                'H94': 0xA35E, # 암호 등록
                'H95': 0xA35F, # 파라미터 변경 금지
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'I Group Object': { # 입출력 그룹
            'Class': 0x64,
            'Instance': 4,
            'Attribute': {
                'I0': 0xA400, # 점프 코드
                'I2': 0xA402, # NV 입력 최소 전압
                'I3': 0xA403, # NV 입력 최소 전압에 대응되는 주파수
                'I4': 0xA404, # NV 입력 최대 전압
                'I5': 0xA405, # NV 입력 최대 전압에 대응되는 주파수
                'I6': 0xA406, # V1 입력 필터 시정수
                'I7': 0xA407, # V1 입력 최소 전압
                'I8': 0xA408, # V1 입력 최소 전압에 대응되는 주파수
                'I9': 0xA409, # V1 입력 최대 전압
                'I10': 0xA40A, # V1 입력 최대 전압에 대응되는 주파수
                'I11': 0xA40B, # I 입력 필터 시정수
                'I12': 0xA40C, # I 입력 최소 전류
                'I13': 0xA40D, # I 입력 최소 전류에 대응되는 주파수
                'I14': 0xA40E, # I 입력 최대 전류
                'I15': 0xA40F, # I 입력 최대 전류에 대응되는 주파수
                'I16': 0xA410, # 아날로그 속도 지령의 상실 기준 선택
                'I17': 0xA411, # 다기능 입력 단자 P1 기능 선택
                'I18': 0xA412, # 다기능 입력 단자 P2 기능 선택
                'I19': 0xA413, # 다기능 입력 단자 P3 기능 선택
                'I20': 0xA414, # 다기능 입력 단자 P4 기능 선택
                'I21': 0xA415, # 다기능 입력 단자 P5 기능 선택
                'I22': 0xA416, # 다기능 입력 단자 P6 기능 선택
                'I23': 0xA417, # 다기능 입력 단자 P7 기능 선택
                'I24': 0xA418, # 다기능 입력 단자 P8 기능 선택
                'I25': 0xA419, # 입력 단자대 상태 표시
                'I26': 0xA41A, # 출력 단자대 상태 표시
                'I27': 0xA41B, # 다기능 입력 단자 필터 시정수
                'I30': 0xA41E, # 다단속 주파수 4
                'I31': 0xA41F, # 다단속 주파수 5
                'I32': 0xA420, # 다단속 주파수 6
                'I33': 0xA421, # 다단속 주파수 7
                'I34': 0xA422, # 다단 가속 시간 1
                'I35': 0xA423, # 다단 감속 시간 1
                'I36': 0xA424, # 다단 가속 시간 2
                'I37': 0xA425, # 다단 감속 시간 2
                'I38': 0xA426, # 다단 가속 시간 3
                'I39': 0xA427, # 다단 감속 시간 3
                'I40': 0xA428, # 다단 가속 시간 4
                'I41': 0xA429, # 다단 감속 시간 4
                'I42': 0xA42A, # 다단 가속 시간 5
                'I43': 0xA42B, # 다단 감속 시간 5
                'I44': 0xA42C, # 다단 가속 시간 6
                'I45': 0xA42D, # 다단 감속 시간 6
                'I46': 0xA42E, # 다단 가속 시간 7
                'I47': 0xA42F, # 다단 감속 시간 7 
                'I50': 0xA432, # 아날로그 출력 항목 선택
                'I51': 0xA433, # 아날로그 출력 레벨 조정
                'I52': 0xA434, # 검출 주파수
                'I53': 0xA435, # 검출 주파수 폭
                'I54': 0xA436, # 다기능 출력 단자 기능 선택
                'I55': 0xA437, # 다기능 릴레이 기능 선택
                'I56': 0xA438, # 고장 출력 선택
                'I57': 0xA439, # 로더 통신 에러 시 출력 단자 선택
                'I59': 0xA43B, # 통신 프로토콜 선택
                'I60': 0xA43C, # 인버터 국번
                'I61': 0xA43D, # 통신 속도
                'I62': 0xA43E, # 속도 지령 상실 시 운전 방법 선택
                'I63': 0xA43F, # 속도 지령 상실 판정 시간
                'I64': 0xA440, # 통신 시간 설정
                'I65': 0xA441, # 패리티/스톱 비트 설정
                'I66': 0xA442, # 읽기 주소 등록 1
                'I67': 0xA443, # 읽기 주소 등록 2
                'I68': 0xA444, # 읽기 주소 등록 3
                'I69': 0xA445, # 읽기 주소 등록 4
                'I70': 0xA446, # 읽기 주소 등록 5
                'I71': 0xA447, # 읽기 주소 등록 6
                'I72': 0xA448, # 읽기 주소 등록 7
                'I73': 0xA449, # 읽기 주소 등록 8
                'I74': 0xA44A, # 쓰기 주소 등록 1
                'I75': 0xA44B, # 쓰기 주소 등록 2
                'I76': 0xA44C, # 쓰기 주소 등록 3
                'I77': 0xA44D, # 쓰기 주소 등록 4
                'I78': 0xA44E, # 쓰기 주소 등록 5
                'I79': 0xA44F, # 쓰기 주소 등록 6
                'I80': 0xA450, # 쓰기 주소 등록 7
                'I81': 0xA451, # 쓰기 주소 등록 8
                'I82': 0xA452, # 브레이크 개방 전류
                'I83': 0xA453, # 브레이크 개방 지연 시간
                'I84': 0xA454, # 브레이크 개방 정방향 주파수
                'I85': 0xA455, # 브레이크 개방 역방향 주파수
                'I86': 0xA456, # 브레이크 닫힘 지연 시간
                'I87': 0xA457, # 브레이크 닫힘 주파수
                'I88': 0xA458, # 속도 지령 상실 시 운전 주파수
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        },
        'C Group Object': { # 통신 그룹
            'Class': 0x64,
            'Instance': 5,
            'Attribute': {
                'FieldBus Option Name': 0xA501,
                'S/W Version': 0xA502,
                'FieldBus Baudrate': 0xA504,
                'FieldBus LED Status': 0xA505,
                'IP Address 1': 0xA60A,
                'IP Address 2': 0xA60B,
                'IP Address 3': 0xA60C,
                'IP Address 4': 0xA60D,
                'Subnet Mask 1': 0xA60E,
                'Subnet Mask 2': 0xA60F,
                'Subnet Mask 3': 0xA610,
                'Subnet Mask 4': 0xA611,
                'Gateway 1': 0xA612,
                'Gateway 2': 0xA613,
                'Gateway 3': 0xA614,
                'Gateway 4': 0xA615,
                'In Instance': 0xA61D,
                'Parameter Status Number': 0xA61E,
                'Parameter Status 1': 0xA61F,
                'Parameter Status 2': 0xA620,
                'Parameter Status 3': 0xA621,
                'Parameter Status 4': 0xA622,
                'Out Instance': 0xA631,
                'Parameter Control Number': 0xA632,
                'Parameter Control 1': 0xA633,
                'Parameter Control 2': 0xA634,
                'Parameter Control 3': 0xA635,
                'Parameter Control 4': 0xA636,
                'Communication Update': 0xA663
            },
            'Service': {
                'Get Attribute Single': 0x0E,
                'Set Attribute Single': 0x10
            }
        }
    },
    'Drive Fault Code': {
        'None': 0x0000,
        'Something wrong': 0x1000,
        'Overload': 0x2200,
        'Overcurrent': 0x2310,
        'Ground fault': 0x2330,
        'Overcurrent2': 0x2340,
        'Over voltage': 0x3210,
        'Low voltage': 0x3220,
        'NTC Open': 0x4000,
        'Inverter overheat': 0x4200,
        'Inverter hardware fault': 0x5000,
        'Cooling fan fault': 0x7000,
        'External fault/Instant cut off': 0x9000
    }
}