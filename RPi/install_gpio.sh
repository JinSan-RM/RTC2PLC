#!/bin/bash

# 환경 설정
REPO_URL="https://github.com/joan2937/lg.git"
CLONE_DIR="$HOME/lg"
PYTHON_BIN=python3
VENV_SITE_PACKAGES=""
INSTALL_TO_VENV=false

# 가상환경 여부 감지
if [[ "$VIRTUAL_ENV" != "" ]]; then
    INSTALL_TO_VENV=true
    VENV_SITE_PACKAGES=$($PYTHON_BIN -c "import site; print(site.getsitepackages()[0])")
    echo "venv detected → copy to $VENV_SITE_PACKAGES"
else
    echo "not venv. install for all system..."
fi

# 소스 클론
if [[ -d "$CLONE_DIR" ]]; then
  echo "delete existing $CLONE_DIR directory"
  rm -rf "$CLONE_DIR"
fi

echo "clone lgpio source code from GitHub..."
git clone "$REPO_URL" "$CLONE_DIR"

# 빌드 및 설치
cd "$CLONE_DIR" || exit 1

echo "run make..."
make clean && make

echo "install library..."
python3 -m pip install .

# lgpio 모듈 위치 확인
LGPIO_SO=$(find /usr/local/lib -name "lgpio*.so" | head -n 1)

if [[ "$LGPIO_SO" == "" ]]; then
    echo "can't install lgpio .so file. make install failed..."
    exit 1
else
    echo "lgpio .so install directory: $LGPIO_SO"
fi

# 가상환경으로 복사 (선택)
if $INSTALL_TO_VENV; then
    echo "copy lgpio module to venv..."
    cp "$LGPIO_SO" "$VENV_SITE_PACKAGES/"
    echo "copy completed: $(basename "$LGPIO_SO") → $VENV_SITE_PACKAGES/"
fi

# GPIO에 대한 유저 권한 부여
echo "set user permission..."
sudo usermod -a -G gpio $USER

# 완료 메시지
echo "install completed. please reboot the system..."