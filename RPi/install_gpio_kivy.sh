#!/bin/bash

echo "update system packages and install basic requirements..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    build-essential \
    git \
    python3-dev \
    python3-pip

echo "remove existing lg directory..."
rm -rf ~/lg

echo "clone lg library from GitHub..."
git clone https://github.com/joan2937/lg.git ~/lg
cd ~/lg

echo "build and install library..."
make
sudo make install

echo "upgrade pip for Python..."
python3 -m pip install --upgrade pip

echo "check installation of Python modules..."
python3 -c "import lgpio, rgpio; print('lgpio, rgpio import succeeded')"

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

echo "install Python packages..."
pip3 install \
    kivy \
    cython \
    pillow \
    pygame \
    docutils \
    pygments

echo "set user permission..."
sudo usermod -a -G gpio $USER

echo "install completed. please reboot the system..."