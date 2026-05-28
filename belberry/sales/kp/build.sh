#!/usr/bin/env bash
#
# build.sh — собирает презентацию КП Belberry из kp.html в PDF и PPTX.
#
# Использование:
#   bash build.sh <папка-клиента> ["Имя выходного файла без расширения"]
#
# Примеры:
#   bash build.sh clients/gutaclinic
#   bash build.sh clients/gutaclinic "КП Belberry — gutaclinic.ru"
#
# На выходе в папке клиента появятся:
#   <Имя>.pdf, <Имя>.pptx, slides_png/ (промежуточные кадры)
#
# Требования (macOS):
#   - Google Chrome (headless рендер HTML→PDF)
#   - poppler: pdftoppm (brew install poppler)
#   - python3 + python-pptx (pip install python-pptx)

set -euo pipefail

CLIENT_DIR="${1:?Укажите папку клиента, напр.: bash build.sh clients/gutaclinic}"
CLIENT_DIR="${CLIENT_DIR%/}"
HTML="$CLIENT_DIR/kp.html"

if [[ ! -f "$HTML" ]]; then
  echo "❌ Не найден $HTML" >&2
  exit 1
fi

# Имя выходного файла: 2-й аргумент или из <title>, иначе по имени папки
if [[ -n "${2:-}" ]]; then
  OUT="$2"
else
  OUT="$(grep -oE '<title>[^<]+</title>' "$HTML" | sed -E 's/<\/?title>//g' | head -1)"
  [[ -z "$OUT" ]] && OUT="КП Belberry — $(basename "$CLIENT_DIR")"
fi

ABS_DIR="$(cd "$CLIENT_DIR" && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

echo "▸ Рендер PDF…"
"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$ABS_DIR/$OUT.pdf" --virtual-time-budget=2000 \
  "file://$ABS_DIR/kp.html" 2>/dev/null
PAGES=$(pdfinfo "$ABS_DIR/$OUT.pdf" 2>/dev/null | awk '/Pages/{print $2}')
echo "  ✓ $OUT.pdf ($PAGES стр.)"

echo "▸ Растеризация слайдов (200 dpi)…"
mkdir -p "$ABS_DIR/slides_png"
rm -f "$ABS_DIR/slides_png"/*.png
pdftoppm -png -r 200 "$ABS_DIR/$OUT.pdf" "$ABS_DIR/slides_png/slide"

echo "▸ Сборка PPTX…"
python3 - "$ABS_DIR" "$OUT" <<'PYEOF'
import sys, glob
from pptx import Presentation
from pptx.util import Emu
abs_dir, out = sys.argv[1], sys.argv[2]
prs = Presentation()
prs.slide_width  = Emu(int(13.333 * 914400))   # 16:10 под наши слайды 1280×800
prs.slide_height = Emu(int(8.333 * 914400))
blank = prs.slide_layouts[6]
for png in sorted(glob.glob(f"{abs_dir}/slides_png/slide-*.png")):
    s = prs.slides.add_slide(blank)
    s.shapes.add_picture(png, 0, 0, width=prs.slide_width, height=prs.slide_height)
prs.save(f"{abs_dir}/{out}.pptx")
print(f"  ✓ {out}.pptx ({len(prs.slides.__iter__.__self__._sldIdLst)} слайдов)")
PYEOF

echo "✅ Готово: $ABS_DIR/$OUT.{pdf,pptx}"
