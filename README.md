# RTC2PLC: 카메라-PLC 통합 시스템

**RTC2PLC**는 카메라로 플라스틱 소재(PET, PVC, HDPE 등)를 실시간으로 분류하고, PLC(Programmable Logic Controller)를 통해 자동화된 분류 작업을 수행하는 시스템입니다. TCP 소켓을 사용하여 카메라 이벤트와 PLC를 연동합니다.

## 시스템 개요

이 시스템은 카메라로 촬영한 플라스틱 소재를 Breeze Runtime으로 분류한 뒤, 결과를 PLC에 전송하여 물리적 동작(예: 소재 분류)을 실행합니다.

### 주요 구성 요소
- **카메라 시스템**: 플라스틱 소재 이미지를 촬영.
- **Breeze Runtime**: 소재를 분류하고 예측 결과를 TCP 소켓으로 전송.
- **Specim2PLC 스크립트**: 카메라 이벤트를 처리하고 PLC 동작으로 매핑.
- **PLC 컨트롤러**: PLC 하드웨어에 신호를 보내 물리적 동작 실행.

## 설치 방법

### 요구 사항
- **Python**: 3.x 버전
- **필수 패키지** (`requirements.txt`):
  - `pyautogui`
  - `psutil`
  - `tkinter`
- **Breeze Runtime**: 워크플로우 파일이 `C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml`에 있어야 함.
- **PLC 하드웨어**: `192.168.250.120:2004`에서 실행.
- **Breeze Runtime 서버**: `127.0.0.1`에서 실행, 포트 2000(명령), 2500(이벤트), 3000(데이터 스트림) 개방.

### 설치 단계
1. 프로젝트 파일을 복사하거나 저장소를 클론.
2. 의존성 설치:
   ```
   pip install -r requirements.txt
   ```
3. 네트워크 설정 확인:
   - PLC: `192.168.250.120:2004`에서 접근 가능.
   - Breeze Runtime: `127.0.0.1`에서 실행, 포트 2000, 2500, 3000 개방.
4. `conf.py`에서 워크플로우 경로 확인:
   ```
   WORKFLOW_PATH = "C:/Users/withwe/breeze/Data/Runtime/Plastic_Classification_1.xml"
   ```

### 실행 방법

1. GUI 테스트 도구 (선택):
   ```
   python app.py
   ```


## 동작 흐름

1. **카메라 초기화**:
   - 카메라를 초기화하고 Breeze 워크플로우를 로드.
   - TCP 포트 2000을 통해 예측 시작 명령 전송.

2. **이벤트 처리**:
   - 포트 2500에서 카메라 이벤트를 수신.
   - JSON 데이터를 파싱하여 분류(예: "PET Bottle")와 세부 정보(시작/종료 라인, 시간 등) 추출.
   - `conf.py`의 `CLASS_MAPPING`과 `PLASTIC_MAPPING`으로 소재 유형 매핑.

3. **PLC 통신**:
   - 소재 분류를 PLC 동작으로 매핑:
     - **3초 그룹**: PET, HDPE (데이터: 0x0101, 값: 257)
     - **5초 그룹**: PVC, LDPE (데이터: 0x0102, 값: 258)
     - **7초 그룹**: PP, PS (데이터: 0x0111, 값: 273)
   - 클래스 ID를 `D00000`(또는 `D00300`)에 쓰고 `M300` 비트를 설정.
   - PLC 통신은 `192.168.250.120:2004`로 수행.

4. **오류 처리**:
   - PLC 쓰기 실패 시 0.5초 간격으로 최대 3회 재시도.
   - Breeze 또는 PLC 연결 끊김 시 재연결 시도.

## 시스템 구조

```
[카메라 시스템] <--> [Breeze Runtime]
        | (TCP: 127.0.0.1:2000, 2500, 3000)
        v
[Specim2PLC.py]
        | (커맨드 클라이언트, 이벤트 리스너, 데이터 스트림 리스너)
        v
[PLC 컨트롤러] <--> [PLC 하드웨어]
        | (TCP: 192.168.250.120:2004)
```

- **커맨드 클라이언트**: Breeze Runtime에 초기화 및 예측 명령 전송.
- **이벤트 리스너**: 분류 이벤트를 처리하여 PLC 동작 매핑.
- **데이터 스트림 리스너**: 실시간 프레임 메타데이터 처리.
- **PLC 컨트롤러**: 소재별 신호를 PLC로 전송.

## 설정

`conf.py`에서 주요 설정 정의:
- `HOST`: 카메라 IP (`127.0.0.1`)
- `EVENT_PORT`: 이벤트 리스너 포트 (`2500`)
- `PLC_IP`/`PLC_PORT`: PLC 주소 (`192.168.250.120:2004`)
- `PLC_D_ADDRESS`: PLC 데이터 주소 (`D00000`)
- `PLC_M_ADDRESS`: PLC 비트 주소 (`M300`)
- `CLASS_MAPPING`: 디스크립터 값을 분류로 매핑 (예: `1: "PET Bottle"`)
- `PLASTIC_MAPPING`: 분류를 소재로 매핑 (예: `"PET Bottle": "PET"`)

## 참고 사항
- PLC 동작 완료를 위해 `D00000` 쓰기 후 `M300` 비트를 설정해야 함.
- PLC 응답 없음 시 초기 전원 설정(ON) 확인.
- 카메라 문제 발생 시 광원 상태 점검 및 지원 팀 문의.
- `D00000` 또는 `D00300`에는 정수 값(예: 1, 2, 3) 사용.

## 문제 해결
- **PLC 연결 실패**: PLC IP/포트 및 네트워크 연결 확인.
- **Breeze 실행 실패**: Breeze 바로 가기 경로 확인 (`C:\Users\withwe\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Prediktera\Breeze\Breeze.lnk`).
- **카메라 문제**: 워크플로우 파일 경로 및 광원 상태 확인.
- **문의**: 현장 문제는 PLC/카메라 지원 팀에 연락 ([Notion 링크](https://www.notion.so/1f0af8f5754b807c9d49e2fc8e253725?pvs=4)).

## 릴리스 정보
- **2025-05-13**: `conf.py` 기반 설정 도입, PLC 및 카메라 모듈 분리.