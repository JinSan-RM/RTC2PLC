1. 라이브러리 설치
    - pip install pysoem
    - pip install PyQt5
    - pip install pymodbus
    - pip install datetime

- pip install -r requirements.txt


2. 네트워크 인터페이스 이름 검색
    - search_ifname.py 실행
    - 윈도우의 경우 \\Device\\NPF_{82D71BA4-0710-4E4A-9ED2-4FD7DA4F0FD3} 과 같은 형식으로 된 값을 확인해야 함

3. 연결된 EtherCAT 슬레이브 장치 검색
    - search_slave.py 실행
    - 슬레이브 장치가 있다면 제조사 ID, 장치 Product Code, 현재 EtherCAT State를 출력

4. 가상환경 생성
    python -m venv (가상환경 이름)

5. 가상환경 접속
    mac:
        source 가상환경 이름/Script/Activate
   
    win:


6. 앱 실행
    - python src/app.py

