@echo off
chcp 65001 > nul
echo RGB Camera Viewer 실행파일 생성 중...
echo.

REM Python과 pip 버전 확인
echo Python 환경 확인 중...
python --version
pip --version
echo.

REM PyInstaller 설치 확인 및 설치
echo PyInstaller 설치 확인 중...
python -c "import PyInstaller; print('PyInstaller 설치됨')" 2>nul
if errorlevel 1 (
    echo PyInstaller를 설치합니다...
    pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller 설치 실패. 관리자 권한으로 다시 시도합니다...
        pip install --user pyinstaller
    )
)

REM 이전 빌드 폴더 삭제
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

REM PyInstaller 실행 (python -m 방식 사용)
echo.
echo 실행파일 생성 중...
python -m PyInstaller --onefile --windowed ^
    --name "RGB_Camera_Viewer" ^
    --add-data "common/config.json;common/" ^
    --hidden-import pypylon ^
    --hidden-import cv2 ^
    --hidden-import PIL ^
    --hidden-import numpy ^
    --distpath "." ^
    app.py

REM 생성 확인
if exist "RGB_Camera_Viewer.exe" (
    echo.
    echo ✅ 빌드 성공! RGB_Camera_Viewer.exe 파일이 생성되었습니다.
    echo 파일 크기:
    dir "RGB_Camera_Viewer.exe" | find "RGB_Camera_Viewer.exe"
) else (
    echo.
    echo ❌ 빌드 실패. dist 폴더를 확인해주세요.
    if exist "dist\RGB_Camera_Viewer.exe" (
        echo dist 폴더에서 파일을 찾았습니다. 이동 중...
        move "dist\RGB_Camera_Viewer.exe" "RGB_Camera_Viewer.exe"
        echo ✅ 파일 이동 완료!
    )
)

REM 불필요한 파일 정리
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "RGB_Camera_Viewer.spec" del "RGB_Camera_Viewer.spec"

echo.
pause