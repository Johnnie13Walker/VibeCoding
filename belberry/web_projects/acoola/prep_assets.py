"""Pre-crop Unsplash photos to target aspect ratios so PowerPoint won't stretch."""

from PIL import Image, ImageFilter, ImageEnhance
import os

CROPS = [
    # (source, target, target_aspect, brightness)
    ("hero_dashboard.jpg", "hero_dashboard_169.jpg", 16/9, 1.0),
    ("banking.jpg",        "banking_portrait.jpg",  4.78/5.5, 1.0),
    ("team.jpg",           "team_portrait.jpg",     4.63/5.5, 1.0),
    ("handshake.jpg",      "handshake_169.jpg",     13.333/7.5, 1.0),
    ("meeting.jpg",        "meeting_169.jpg",       13.333/7.5, 1.0),
    ("code.jpg",           "code_169.jpg",          16/9, 1.0),
    ("analytics.jpg",      "analytics_wide.jpg",    13.333/2.5, 1.0),
    ("chart.jpg",          "chart_wide.jpg",        13.333/2.5, 1.0),
]

src_dir = "assets/photos"

for src, dst, target_aspect, brightness in CROPS:
    src_path = os.path.join(src_dir, src)
    dst_path = os.path.join(src_dir, dst)
    if not os.path.exists(src_path):
        print(f"SKIP {src} (missing)")
        continue
    img = Image.open(src_path)
    w, h = img.size
    img_aspect = w / h
    if img_aspect > target_aspect:
        # too wide — crop sides
        new_w = int(h * target_aspect)
        offset = (w - new_w) // 2
        cropped = img.crop((offset, 0, offset + new_w, h))
    else:
        # too tall — crop top/bottom
        new_h = int(w / target_aspect)
        offset = (h - new_h) // 2
        cropped = img.crop((0, offset, w, offset + new_h))
    if brightness != 1.0:
        cropped = ImageEnhance.Brightness(cropped).enhance(brightness)
    cropped.save(dst_path, quality=88, optimize=True)
    print(f"OK {dst}: {cropped.size}")

print("done")
