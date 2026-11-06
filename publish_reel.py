import os
import time
import random
import hashlib
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont

def get_ayah():
    n = random.randint(1, 6236)
    url = f"https://api.alquran.cloud/v1/ayah/{n}/editions/quran-uthmani,ur.jalandhry"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()["data"]
    return data[0], data[1]

def make_video(arabic, urdu, reference):
    img = Image.new("RGB", (1080, 1920), (10, 55, 48))
    draw = ImageDraw.Draw(img)

    font_path = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
    title = ImageFont.truetype(font_path, 65)
    body = ImageFont.truetype(font_path, 55)

    draw.text((540, 250), "آج کی قرآنی یاددہانی",
              font=title, fill=(230, 195, 120), anchor="mm", direction="rtl")
    draw.text((540, 650), arabic,
              font=body, fill="white", anchor="mm", direction="rtl")
    draw.line((150, 950, 930, 950), fill=(230, 195, 120), width=3)
    draw.text((540, 1200), urdu,
              font=body, fill="white", anchor="mm", direction="rtl")
    draw.text((540, 1600), reference,
              font=title, fill=(230, 195, 120), anchor="mm", direction="rtl")

    img.save("reel.png")
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", "reel.png",
        "-t", "15", "-r", "30", "-vf", "scale=1080:1920,format=yuv420p",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "reel.mp4"
    ], check=True, capture_output=True)

def upload_cloudinary():
    cloud = os.environ["CLOUDINARY_CLOUD_NAME"]
    key = os.environ["CLOUDINARY_API_KEY"]
    secret = os.environ["CLOUDINARY_API_SECRET"]
    timestamp = str(int(time.time()))
    params = {"timestamp": timestamp, "folder": "islamic-reels"}
    signed = "&".join(f"{k}={params[k]}" for k in sorted(params)) + secret
    signature = hashlib.sha1(signed.encode()).hexdigest()

    with open("reel.mp4", "rb") as f:
        r = requests.post(
            f"https://api.cloudinary.com/v1_1/{cloud}/video/upload",
            data={**params, "api_key": key, "signature": signature},
            files={"file": f}, timeout=180
        )
    r.raise_for_status()
    return r.json()["secure_url"]

def publish(video_url, caption):
    base = "https://graph.facebook.com/" + os.environ["GRAPH_API_VERSION"]
    user = os.environ["IG_USER_ID"]
    token = os.environ["IG_ACCESS_TOKEN"]

    r = requests.post(
        f"{base}/{user}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token
        }, timeout=60
    )
    r.raise_for_status()
    creation_id = r.json()["id"]

    for _ in range(30):
        s = requests.get(
            f"{base}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30
        )
        s.raise_for_status()
        status = s.json().get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError("Instagram video processing failed")
        time.sleep(10)
    else:
        raise TimeoutError("Video processing timed out")

    r = requests.post(
        f"{base}/{user}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=60
    )
    r.raise_for_status()
    print("Instagram Reel published:", r.json())

def main():
    required = [
        "IG_USER_ID", "IG_ACCESS_TOKEN", "GRAPH_API_VERSION",
        "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET"
    ]
    for name in required:
        if not os.getenv(name):
            raise RuntimeError("Missing secret: " + name)

    arabic, urdu = get_ayah()
    reference = f"سورۃ {arabic['surah']['name']}، آیت {arabic['numberInSurah']}"
    make_video(arabic["text"], urdu["text"], reference)

    caption = (
        "آج کی قرآنی یاددہانی 🌿\n"
        + reference + "\n"
        "ترجمہ: فتح محمد جالندھری\n"
        "#Quran #IslamicReminder #IslamicReels #قرآن #اسلام"
    )

    video_url = upload_cloudinary()
    publish(video_url, caption)

if __name__ == "__main__":
    main()