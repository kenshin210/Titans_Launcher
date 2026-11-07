#!/bin/bash

echo "Installing Arch Dependencies"


PACMAN=("python" "python-pip" "networkmanager" "networkmanager-openvpn" "wireguard-tools" "openvpn" "bluez" "bluez-utils" "pacman-contrib" "polkit")

for pkg in "${PACMAN[@]}"; do

    sudo pacman -S --needed --noconfirm "$pkg"

    if [ $? -eq 0 ]; then
        echo "Dependencies Installed"
    else
        echo "dev probably messed up dont worry about it"
        echo " Failed to install $pkg" >&2
        exit 1
    fi
done

python -m venv .venv
source .venv/bin/activate

PACKAGES=("opencv-python" "pygame-ce" "PyQt6" "psutil")

echo "Installing python modules.."

for pkg in "${PACKAGES[@]}"; do
    pip install "$pkg"

    if [ $? -eq 0 ]; then
        echo "Dependencies Installed"
    else
        echo "dev probably messed up dont worry about it"
        echo " Failed to install $pkg" >&2
        exit 1
    fi
done
