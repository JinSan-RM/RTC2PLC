pip install -r requirements.txt
set FLASK_APP=src/web/server.py
flask run --host=0.0.0.0 --port=5000

-----
PLC-카메라 통합 프로세스 흐름

이 문서는 카메라 이벤트를 처리하여 PLC(Programmable Logic Controller)를 제어하는 PLC-카메라 통합 시스템의 프로세스 흐름을 설명합니다.

이 시스템은 카메라의 객체 인식 이벤트를 PLC와 통합하여 소재별 작업을 자동화합니다. 카메라는 소켓 연결을 통해 분류 이벤트를 전송하며, 이를 처리하여 소재 유형을 결정합니다. 이후 소재에 따라 미리 정의된 작업을 실행하도록 PLC에 명령을 전송합니다.

프로세스 흐름

소재 그룹과 관련된 지연 시간 및 데이터 값을 정의합니다:
3초 그룹: PET, HDPE (데이터: 0x0101, 값: 257)
5초 그룹: PVC, LDPE (데이터: 0x0102, 값: 258)
7초 그룹: PP, PS (데이터: 0x0111, 값: 273)

2. 카메라 이벤트 리스너 설정

소켓 연결:
카메라의 IP(192.168.250.130)와 포트(2500)로 TCP 소켓 연결을 설정합니다.
즉시 재연결을
 허용하기 위해 SO_REUSEADDR를 사용합니다.

스레딩:
카메라 이벤트를 병렬로 처리하기 위해 별도의 데몬 스레드에서 이벤트 리스너를 실행합니다.

매핑:
카메라 디스크립터 값을 분류로 매핑하는 CLASS_MAPPING을 정의합니다(예: 1 → PET Bottle).
분류를 PLC 호환 소재 유형으로 변환하는 PLASTIC_MAPPING을 정의합니다(예: PET Bottle → PET).

3. 이벤트 처리

데이터 수신:
1초 타임아웃으로 카메라로부터 데이터를 수신합니다.
수받은 데이터를 버퍼링하고 \r\n으로 분리하여 완전한 메시지를 처리합니다.

JSON 파싱:
각 메시지를 JSON으로 파싱하여 Event와 Message 필드를 추출합니다.
PredictionObject 이벤트를 확인하고, 내부 Descriptors 필드에서 디스크립터 값을 추출합니다.

분류 및 소재 매핑:
디스크립터 값을 CLASS_MAPPING을 사용하여 분류로 매핑합니다.
분류를 PLASTIC_MAPPING을 통해 PLC 소재 유형으로 변환합니다.
소재 유형이 None인 경우(예: Background 또는 PC) 처리를 건너뜁니다.

4. PLC 통신

소재 작업 결정:
get_category_action을 호출하여 소재에 대한 지연 시간과 데이터 바이트를 가져옵니다.
알 수 없는 소재의 경우 ValueError를 발생시킵니다.


패킷 생성:
create_write_packet을 사용하여 PLC 통신용 바이너리 패킷을 생성합니다.
패킷 구조에는 헤더(LSIS-XGT), 명령 코드, 대상 주소(예: %DB0, %DB2) 및 데이터가 포함됩니다.


PLC에 쓰기:

단계 1: %DB0에 쓰기:
소재별 데이터(예: PET의 경우 0x0101)를 %DB0에 전송합니다.

단계 2: %DB2에 쓰기:
PLC 작업을 트리거하기 위해 값 1을 %DB2에 전송합니다.
send_packet_to_plc를 사용하여 최대 3회 재시도(시도 간 2초 지연)를 통해 통신 오류를 처리합니다.
각 단계의 성공 또는 실패를 기록합니다.



PLCController: 패킷 생성 및 소재별 작업을 포함한 PLC 통신을 관리합니다.

listen_for_events: 카메라 이벤트를 별도 스레드에서 처리하여 분류를 PLC 작업으로 매핑합니다.



RTC2PLC는 카메라 기반 실시간 분류(RTC) 시스템(Breeze Runtime)에서 생성된 플라스틱 소재 분류 결과를 PLC(Programmable Logic Controller)와 통합하여 자동화된 분류 또는 처리를 가능하게 하는 파이프라인 프로젝트

RTC2PLC 프로젝트는 PET, PVC, HDPE, LDPE, PP, PS와 같은 플라스틱 소재를 실시간으로 분류하고 PLC를 통해 자동화된 동작을 수행하는 시스템

Breeze Runtime에서 TCP 소켓을 통해 분류 예측을 수신.

예측 결과를 소재별 PLC 동작(예: 3초, 5초, 7초 신호)으로 매핑.

PLC와 통신하여 동작 실행.

네트워크 설정 확인:

PLC가 192.168.250.120:2004에서 실행 중인지 확인.

Breeze Runtime 서버가 192.168.1.185에서 실행 중이며, 포트 2000(명령), 2500(이벤트), 3000(데이터 스트림)이 열려 있는지 확인.

Specim2PLC.py의 main() 함수에서 workflow_path가 Breeze 워크플로우 파일의 위치와 일치하는지 확인:

workflow_path = "C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml"

python Specim2PLC.py

스크립트 흐름:

카메라 초기화 및 Breeze 워크플로우 로드

예측 시작, 이벤트 및 데이터 스트림 수신.

소재 예측(예: PET, PVC)을 처리하고 해당 신호를 PLC로 전송.

시스템 아키텍처
```
      [Gram]    <--->   [카메라 시스템]
        |    Ethernet 연결  
        |
        | (예측 이벤트, 데이터 스트림)
        v
[Breeze Runtime]
        |
        | (예측 이벤트, 데이터 스트림)
        v           
   [Specim2PLC.py]
        |            
        |            
        |            
        |             
        |            
        | (소켓 통신) 
        v          
[커맨드 클라이언트]    
        | (TCP: 192.168.1.185:2000)
        v
[이벤트 리스너] <-> [Breeze Runtime]
        | (TCP: 192.168.1.185:2500)
        v
[데이터 스트림 리스너] <-> [Breeze Runtime]
        | (TCP: 192.168.1.185:3000)          
        |            
        v              
[PLC Controller] 
        | (TCP 소켓: 192.168.250.120:2004)          
        |            
        v
[PLC 하드웨어]
```
카메라 시스템: 플라스틱 소재 이미지를 캡처.

Breeze Runtime: 소재를 분류하고 예측을 전송.

Specim2PLC.py:


커맨드 클라이언트: 카메라 초기화, 예측 시작 등의 명령을 Breeze Runtime으로 전송.

이벤트 리스너: 예측 이벤트를 처리하고 PLC 동작을 트리거.

데이터 스트림 리스너: 실시간 프레임 메타데이터를 처리.

PLC 컨트롤러: 소재별 신호를 PLC로 전송.

PLC 하드웨어: 물리적 동작(예: 분류)을 실행.

25.05.13 Release
2. PLC 관련 신교진 담당자
- 1 D00000으로 신호는 주는게 맞다고함. ( ※ 사용 여부에 따라서 D00300에 보내도 괜찮다고함)
- 2 D00000으로 보내는 신호가 PLC에 도착할 때에 ASCII나 HEX등등 값이 아닌 정수형 1,2,3이 PLC D00000, D00300에 들어오면 된다고 전달해주셨습니다.
- 3 동작하지 않았던 이유중에 PLC 설정중 맨처음 들어가는 상시 전원이 OFF -> 되어있었던 부분이 존재. (무인오토의 인수인계 받으신 담당자가 현장에서 풀어주는 것을 확인해서 PLC 담당자에게도 전달하였습니다.)
- 4 신호를 보낸뒤에 맺음 비트 신호 꼭 발송해야한다. ( 정년이사님께 전달 받았음. )
- 5 기타 안되는 부분들 같은 경우나 실제로 현장에서 동작할 때에나 연락해서 수정 진행할 수 있도록 도와주겠다고 연락 받았습니다.
1. 카메라 상황 관련 내일 오전에 방문해서 회수 하기로 함.
- 이충민 주임의 말로는 광원에 문제가 있었을 확률이 큰 데, 현 시점에서는 잘나와 원인파악이 어려운 상황이라 내일 한번 더 설명해주겠다고 하였습니다.
[https://www.notion.so/1f0af8f5754b807c9d49e2fc8e253725?pvs=4](https://www.notion.so/1f0af8f5754b807c9d49e2fc8e253725?pvs=21)
1. Python Specim -> PLC 동작 Script 하드 코딩 형태가 아닌 config 파일 기반의 동작 방식으로 변경하였습니다. ( ※ PLC Controller, Camera Connection 모듈 분리 작업 진행중)