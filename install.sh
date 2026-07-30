#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
APP_NAME="marktplaats_manager.py"
ICON_NAME="icon.png"

echo "📦 Stap 1: Controleren en installeren van systeem-tools (ImageMagick)..."
if ! command -v mogrify &> /dev/null; then
    echo "   ImageMagick niet gevonden. Installeren..."
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y imagemagick
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y imagemagick
    elif command -v yum &> /dev/null; then
        sudo yum install -y imagemagick
    else
        echo "⚠️  Kan ImageMagick niet installeren. Installeer het handmatig via je package manager."
    fi
else
    echo "   ✅ ImageMagick is aanwezig."
fi

echo "📦 Stap 2: Controleren en installeren van Python packages (zonder systeem te breken)..."
# Gebruik --user om nooit systeem-packages te breken!
pip3 install --user --upgrade pip > /dev/null 2>&1
pip3 install --user Pillow psutil transparent-background rembg opencv-python opencv-contrib-python tqdm > /dev/null 2>&1

# Zorg dat ~/.local/bin in de PATH zit (anders werkt 'mp-foto' niet)
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    echo "   🔄 PATH bijgewerkt. Herstart je terminal of voer 'source ~/.bashrc' uit."
fi

# Zorg dat ALLE scripts uitvoerbaar zijn
chmod +x "$SCRIPT_DIR/$APP_NAME"
chmod +x "$SCRIPT_DIR/image_enhancer.py"

mkdir -p "$HOME/.local/bin"
LAUNCHER_SCRIPT="$HOME/.local/bin/marktplaats-launcher.sh"

cat > "$LAUNCHER_SCRIPT" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
python3 "$SCRIPT_DIR/$APP_NAME"
EOF
chmod +x "$LAUNCHER_SCRIPT"

# Terminal commando 'mp-foto'
SYMLINK="$HOME/.local/bin/mp-foto"
if [ -L "$SYMLINK" ]; then
    rm "$SYMLINK"
fi
ln -s "$LAUNCHER_SCRIPT" "$SYMLINK"
chmod +x "$SYMLINK"

# Desktop entry
DESKTOP_FILE="$HOME/.local/share/applications/MarktplaatsFotoManager.desktop"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Marktplaats Foto Manager
Comment=Verwerk productfoto's voor Marktplaats
Exec=$LAUNCHER_SCRIPT
Icon=$SCRIPT_DIR/$ICON_NAME
Path=$SCRIPT_DIR
Terminal=false
Categories=Graphics;Utility;
EOF

# Kopieer naar bureaublad
if [ -d "$HOME/Bureaublad" ]; then
    cp "$DESKTOP_FILE" "$HOME/Bureaublad/MarktplaatsFotoManager.desktop"
elif [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$HOME/Desktop/MarktplaatsFotoManager.desktop"
fi
chmod +x "$HOME/Bureaublad/MarktplaatsFotoManager.desktop" 2>/dev/null || chmod +x "$HOME/Desktop/MarktplaatsFotoManager.desktop" 2>/dev/null

echo ""
echo "=================================================="
echo "✅ Installatie volledig en veilig voltooid!"
echo "=================================================="
echo "📍 Menu & Bureaublad: Snelkoppeling geplaatst"
echo "💻 Terminal: Typ 'mp-foto' (in een NIEUWE terminal)"
echo "📦 Python packages: Geïnstalleerd als gebruiker (geen systeem-breuk!)"
echo "=================================================="
