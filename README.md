RTC2PLC

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

카메라 시스템: 플라스틱 소재 이미지를 캡처.

Breeze Runtime: 소재를 분류하고 예측을 전송.

Specim2PLC.py:


커맨드 클라이언트: 카메라 초기화, 예측 시작 등의 명령을 Breeze Runtime으로 전송.

이벤트 리스너: 예측 이벤트를 처리하고 PLC 동작을 트리거.

데이터 스트림 리스너: 실시간 프레임 메타데이터를 처리.

PLC 컨트롤러: 소재별 신호를 PLC로 전송.

PLC 하드웨어: 물리적 동작(예: 분류)을 실행.

