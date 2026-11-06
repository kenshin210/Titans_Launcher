#!/bin/bash

echo "Installing Arch Dependencies"


PACMAN=("python" "python-pip")

for pkg in "${PACMAN[@]}"; do

    sudo pacman -S --noconfirm "$pkg"

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

PACKAGES=("opencv-python" "pygame-ce" "PyQt6")

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
