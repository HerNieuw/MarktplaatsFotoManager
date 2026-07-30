import os
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from tqdm import tqdm

def auto_enhance(image_path, output_path):
    img = cv2.imread(image_path)
    if img is None:
        return

    # BGR -> RGB
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # PIL
    image = Image.fromarray(img)

    # ---------------------------------
    # 1. Auto contrast
    # ---------------------------------
    image = ImageEnhance.Contrast(image).enhance(1.15)

    # ---------------------------------
    # 2. Kleuren verbeteren
    # ---------------------------------
    image = ImageEnhance.Color(image).enhance(1.20)

    # ---------------------------------
    # 3. Lichte helderheid correctie
    # ---------------------------------
    image = ImageEnhance.Brightness(image).enhance(1.08)

    # ---------------------------------
    # 4. Detail/scherpte verbeteren
    # ---------------------------------
    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=1.5,
            percent=130,
            threshold=3
        )
    )

    # PIL -> OpenCV
    img = np.array(image)

    # ---------------------------------
    # 5. CLAHE
    # haalt donkere delen omhoog
    # zonder alles overbelichten
    # ---------------------------------
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    l = clahe.apply(l)

    lab = cv2.merge((l, a, b))
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)

    # ---------------------------------
    # 6. Kleine ruisreductie
    # ---------------------------------
    img = cv2.fastNlMeansDenoisingColored(img, None, 3, 3, 7, 21)

    # opslaan
    result = Image.fromarray(img)
    result.save(output_path, quality=95, optimize=True)


def process_directory(input_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    for filename in tqdm(files, desc="Foto verbeteren"):
        src = os.path.join(input_dir, filename)
        dst = os.path.join(output_dir, filename)
        auto_enhance(src, dst)


if __name__ == "__main__":
    # === DRAAIBAAR GEMAAKT ===
    # Deze paden zijn nu relatief aan de map waar het script zelf staat!
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # De input en output mappen worden dus:
    # /pad/naar/uitgepakte_map/input
    # /pad/naar/uitgepakte_map/output
    
    input_dir = os.path.join(script_dir, "input")
    output_dir = os.path.join(script_dir, "output")

    print(f"📂 Enhancer Input:  {input_dir}")
    print(f"📂 Enhancer Output: {output_dir}")

    if not os.path.exists(input_dir):
        os.makedirs(input_dir, exist_ok=True)
        print("⚠️  Input map bestaat nog niet. Aangemaakt.")

    process_directory(input_dir, output_dir)
