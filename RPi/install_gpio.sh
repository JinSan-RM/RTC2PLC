#!/bin/bash

# 시스템 업데이트 & 업그레이드
echo "update system packages and install basic requirements..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    build-essential \
    git \
    python3-dev \
    python3-pip

# pip 업그레이드
echo "upgrade pip for Python..."
python3 -m pip install --upgrade pip

pip3 install lgpio
pip3 install rgpio

# GPIO에 대한 유저 권한 부여
echo "set user permission..."
sudo usermod -a -G gpio $USER

# 완료 메시지
echo "install completed. please reboot the system..."