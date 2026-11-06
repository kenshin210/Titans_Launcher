echo "Installing Arch Dependencies"

echo "Installing Python"
sudo pacman -S Python

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
