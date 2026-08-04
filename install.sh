#!/bin/bash
# install_fotomanager.sh
# Universele installatie voor Marktplaats Foto Manager (werkt op elke pc)

set -e

# Bepaal het pad waar dit script staat (dus waar de app staat)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "📦 Systeemafhankelijkheden installeren (GTK & Python)..."
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-3.0 python3-pip

# Zorg dat Pillow (voor fotobewerking) geïnstalleerd is
pip install --break-system-packages Pillow

# Icoon check
if [ -f "$APP_DIR/icon.png" ]; then
    echo "🖼️  Icoon gevonden"
else
    echo "⚠️  Geen icon.png gevonden - snelkoppeling krijgt geen custom icoon"
fi

# =========================================================
# Startscript aanmaken (DIT is de truc die het universeel maakt!)
# =========================================================
cat > "$APP_DIR/start-foto" << EOF
#!/bin/bash
# Dit bestand wordt dynamisch gegenereerd door install_fotomanager.sh
cd "\$(dirname "\$0")"
export GDK_BACKEND=x11
export XDG_SESSION_TYPE=x11
python3 marktplaats_manager.py
EOF
chmod +x "$APP_DIR/start-foto"
echo "✅ start-foto aangemaakt"

# =========================================================
# .desktop snelkoppeling aanmaken
# =========================================================
cat > "$APP_DIR/MarktplaatsFotoManager.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Marktplaats Foto Manager
Comment=Bewerk productfoto's voor Marktplaats
Exec=$APP_DIR/start-foto
Icon=$APP_DIR/icon.png
Terminal=false
StartupNotify=true
StartupWMClass=marktplaats_manager
Categories=Graphics;Photography;
EOF
chmod +x "$APP_DIR/MarktplaatsFotoManager.desktop"

# Kopieer naar het systeemmenu van de huidige gebruiker
mkdir -p ~/.local/share/applications
cp "$APP_DIR/MarktplaatsFotoManager.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications 2>/dev/null || true

echo ""
echo "✅ Klaar! De snelkoppeling is universeel toegevoegd."
echo "   Je kunt 'Marktplaats Foto Manager' nu vinden in je applicatiemenu."
echo ""
echo "📌 Alternatief: start vanuit terminal met:"
echo "   cd $APP_DIR && ./start-foto"
