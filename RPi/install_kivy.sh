#!/bin/bash

# 시스템 의존성 먼저 설치
echo "install kivy dependency..."
sudo apt install -y \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    zlib1g-dev \
    libgl1-mesa-dev \
    libgles2-mesa-dev

# 패키지 설치
echo "install Python packages..."
pip3 install \
    kivy \
    cython \
    pillow \
    pygame \
    docutils \
    pygments

echo "install completed..."