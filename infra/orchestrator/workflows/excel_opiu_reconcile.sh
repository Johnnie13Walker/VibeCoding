#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT_DIR/infra/orchestrator/lib.sh"

INPUT_PATH="${INPUT_PATH:-/Users/pro2kuror/Downloads/Копия ДДС_2026.xlsx}"
OUTPUT_PATH="${OUTPUT_PATH:-$INPUT_PATH}"

log "excel_opiu_reconcile: входной файл: $INPUT_PATH"
log "excel_opiu_reconcile: выходной файл: $OUTPUT_PATH"

python3 - "$INPUT_PATH" "$OUTPUT_PATH" <<'PY'
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)

if len(sys.argv) != 3:
    raise SystemExit("Ожидалось 2 аргумента: INPUT_PATH OUTPUT_PATH")

input_path, output_path = sys.argv[1], sys.argv[2]


def qn(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def get_cell(sheet_root: ET.Element, ref: str) -> ET.Element:
    cell = sheet_root.find(f".//{qn('c')}[@r='{ref}']")
    if cell is None:
        raise RuntimeError(f"Не найдена ячейка {ref}")
    return cell


def set_formula_and_value(sheet_root: ET.Element, ref: str, formula: str, value: str) -> None:
    cell = get_cell(sheet_root, ref)
    if cell.get("t") == "str":
        del cell.attrib["t"]

    f = cell.find(qn("f"))
    if f is None:
        f = ET.SubElement(cell, qn("f"))
    f.attrib.clear()
    f.text = formula

    v = cell.find(qn("v"))
    if v is None:
        v = ET.SubElement(cell, qn("v"))
    v.text = value


with zipfile.ZipFile(input_path, "r") as zin:
    payload = {name: zin.read(name) for name in zin.namelist()}

sheet_path = "xl/worksheets/sheet11.xml"
sheet_root = ET.fromstring(payload[sheet_path])

# Выручка: учитываем Service из строки 373, а депозит убираем из выручки.
set_formula_and_value(
    sheet_root,
    "C4",
    "'ОПиУ 2026'!H185+'ОПиУ 2026'!H373",
    "72450.5",
)
set_formula_and_value(sheet_root, "C5", "0", "0")

# Добавляем пропущенный Бюджет клиента в производственные расходы.
set_formula_and_value(
    sheet_root,
    "C7",
    "SUM(C8:C25)+'ОПиУ 2026'!H502",
    "2341061.5",
)

# Админблок должен включать C54 (Прочее).
set_formula_and_value(sheet_root, "C43", "SUM(C44:C54)", "1064374")

# Финансы и налоги: включаем аренду ИП.
set_formula_and_value(sheet_root, "C72", "SUM(C73:C76)", "714428.2633")

# Пересчитываем агрегаты.
set_formula_and_value(sheet_root, "C2", "SUM(C3:C5)", "9796364.5")
set_formula_and_value(sheet_root, "C78", "C7+C27+C32+C43+C56+C72", "6133514.813")
set_formula_and_value(sheet_root, "C79", "C2-(C7+C27)", "6625732")
set_formula_and_value(
    sheet_root,
    "C80",
    "C2-(C7+C27+C32+C43+C56+C74+C76)",
    "4352192.95",
)
set_formula_and_value(sheet_root, "C81", "C2-C78", "3662849.687")

payload[sheet_path] = ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True)

with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
    for name, data in payload.items():
        zout.writestr(name, data)
PY

log "excel_opiu_reconcile: формулы обновлены"
