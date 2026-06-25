# -*- coding: utf-8 -*-
"""Иллюстрация: датчик протечки в углублении (заподлицо) под подвесной раковиной
   vs датчик плашмя в закрытой зоне. Для согласования с прорабом по ЖК SOUL."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, FancyArrowPatch, Circle, Polygon

plt.rcParams["font.family"] = "DejaVu Sans"

TILE   = "#e7ddc9"   # плитка
GROUT  = "#b9ab8e"   # затирка/шов
SCREED = "#cfcfcf"   # стяжка
SENSOR = "#3a3a3a"   # датчик
WATER  = "#3d8bd4"   # вода
WOOD   = "#8a5a36"   # мебель (Эггер Каселла)
ROBOT  = "#5a5a5a"
ACCENT = "#2f6f3e"

fig = plt.figure(figsize=(13, 7.5), dpi=130)
fig.suptitle("Датчик протечки в углублении заподлицо — как это выглядит",
             fontsize=16, fontweight="bold", y=0.975)

# ============================================================== ПАНЕЛЬ A — РАЗРЕЗ
axA = fig.add_axes([0.04, 0.07, 0.56, 0.83])
axA.set_xlim(0, 10); axA.set_ylim(0, 10); axA.axis("off")
axA.set_title("РАЗРЕЗ — под подвесной раковиной (с углублением)",
              fontsize=11.5, fontweight="bold")

# стена слева
axA.add_patch(Rectangle((0, 0), 0.5, 10, facecolor="#d8d2c4", edgecolor="none"))

# подвесная тумба с раковиной (вверху)
axA.add_patch(FancyBboxPatch((0.5, 7.0), 6.6, 1.7,
              boxstyle="round,pad=0.02,rounding_size=0.12",
              facecolor=WOOD, edgecolor="#5c3c22", linewidth=1.5))
axA.text(3.8, 7.85, "подвесная тумба с раковиной", ha="center", va="center",
         color="white", fontsize=10, fontweight="bold")
# раковина (намёк сверху)
axA.add_patch(FancyBboxPatch((2.4, 8.7), 2.8, 0.45,
              boxstyle="round,pad=0.02,rounding_size=0.2",
              facecolor="#f5f3ee", edgecolor="#bbb", linewidth=1))

# просвет под тумбой
axA.annotate("", xy=(6.9, 6.9), xytext=(6.9, 2.05),
             arrowprops=dict(arrowstyle="<->", color="#888", lw=1.2))
axA.text(7.15, 4.5, "просвет\n~30–40 см", ha="left", va="center",
         fontsize=9, color="#555")

# пол: стяжка + плитка
axA.add_patch(Rectangle((0.5, 0.0), 9.5, 1.6, facecolor=SCREED, edgecolor="none"))
axA.add_patch(Rectangle((0.5, 1.6), 9.5, 0.42, facecolor=TILE,
              edgecolor=GROUT, linewidth=1.4))
# швы плитки
for x in (2.0, 3.5, 6.5, 8.0, 9.4):
    axA.plot([x, x], [1.6, 2.02], color=GROUT, lw=1.4)
axA.text(9.85, 1.8, "плитка", ha="right", va="center", fontsize=8.5,
         color="#6b5d40", rotation=0)
axA.text(9.85, 0.7, "стяжка", ha="right", va="center", fontsize=8.5, color="#777")

# УГЛУБЛЕНИЕ (карман) + датчик заподлицо
# вырез в стяжке/плитке
axA.add_patch(Rectangle((4.15, 0.55), 1.7, 1.47, facecolor="white", edgecolor="none"))
axA.add_patch(Rectangle((4.15, 0.55), 1.7, 1.47, facecolor=SCREED, edgecolor=GROUT,
              linewidth=1.0, hatch=None))
# датчик в кармане, верх заподлицо с плиткой (y=2.02)
axA.add_patch(FancyBboxPatch((4.35, 0.7), 1.3, 1.32,
              boxstyle="round,pad=0.02,rounding_size=0.06",
              facecolor=SENSOR, edgecolor="black", linewidth=1.2))
axA.text(5.0, 1.36, "датчик", ha="center", va="center", color="white",
         fontsize=9, fontweight="bold", rotation=90)
# провод уходит в стяжку
axA.plot([4.35, 3.2, 3.2], [1.0, 1.0, 0.2], color="#c0392b", lw=2.0)
axA.text(2.9, 0.35, "провод\nв стяжке", ha="right", va="center",
         fontsize=8.5, color="#c0392b")

# щель по периметру + вода
for sx in (4.18, 5.79):
    axA.add_patch(Rectangle((sx, 0.7), 0.16, 1.32, facecolor=WATER, alpha=0.35,
                  edgecolor="none"))
axA.add_patch(FancyArrowPatch((5.0, 2.95), (5.0, 2.1),
              arrowstyle="-|>", mutation_scale=16, color=WATER, lw=2))
axA.add_patch(Rectangle((4.0, 2.05), 2.0, 0.12, facecolor=WATER, alpha=0.6,
              edgecolor="none"))
axA.text(5.0, 3.15, "при протечке вода затекает\nв щель по периметру → датчик срабатывает",
         ha="center", va="bottom", fontsize=9, color=WATER, fontweight="bold")

# заподлицо — выноска
axA.annotate("верх датчика ЗАПОДЛИЦО с плиткой",
             xy=(5.0, 2.02), xytext=(0.7, 3.7),
             fontsize=9, color="black",
             arrowprops=dict(arrowstyle="->", color="black", lw=1.1))

# робот едет над датчиком
rb = FancyBboxPatch((7.4, 2.05), 1.7, 0.55,
              boxstyle="round,pad=0.02,rounding_size=0.25",
              facecolor=ROBOT, edgecolor="black", linewidth=1.2)
axA.add_patch(rb)
axA.add_patch(Circle((8.25, 2.62), 0.12, facecolor="#cce0f5", edgecolor="black", lw=0.8))
axA.text(8.25, 2.32, "робот", ha="center", va="center", color="white", fontsize=8.5)
axA.add_patch(FancyArrowPatch((7.3, 2.32), (6.1, 2.32),
              arrowstyle="-|>", mutation_scale=16, color="black", lw=1.6))
axA.text(7.0, 2.78, "едет НАД датчиком,\nне задевает", ha="center", va="bottom",
         fontsize=8.5, color="#333")

# ============================================================== ПАНЕЛЬ B — ВИД СВЕРХУ
axB = fig.add_axes([0.65, 0.55, 0.32, 0.35])
axB.set_xlim(0, 10); axB.set_ylim(0, 6); axB.axis("off")
axB.set_title("ВИД СВЕРХУ", fontsize=10.5, fontweight="bold")
# плитка с швами
axB.add_patch(Rectangle((0, 0), 10, 6, facecolor=TILE, edgecolor=GROUT, linewidth=1.5))
for x in (3.33, 6.66):
    axB.plot([x, x], [0, 6], color=GROUT, lw=1.4)
for y in (3.0,):
    axB.plot([0, 10], [y, y], color=GROUT, lw=1.4)
# датчик-карман заподлицо
axB.add_patch(FancyBboxPatch((4.0, 2.0), 2.0, 2.0,
              boxstyle="round,pad=0.02,rounding_size=0.12",
              facecolor=SENSOR, edgecolor="black", linewidth=1.2))
axB.text(5.0, 3.0, "датчик", ha="center", va="center", color="white",
         fontsize=8.5, fontweight="bold")
axB.text(5.0, 0.6, "аккуратный прямоугольник\nв уровень пола, в цвет шва",
         ha="center", va="center", fontsize=8.2, color="#555")

# ============================================================== ПАНЕЛЬ C — БЕЗ УГЛУБЛЕНИЯ
axC = fig.add_axes([0.65, 0.07, 0.32, 0.38])
axC.set_xlim(0, 10); axC.set_ylim(0, 6); axC.axis("off")
axC.set_title("БЕЗ УГЛУБЛЕНИЯ — плашмя\n(за экраном ванны / за коробом инсталляции)",
              fontsize=10, fontweight="bold")
# короб/экран
axC.add_patch(Rectangle((0.5, 0.0), 0.5, 6, facecolor=WOOD, edgecolor="#5c3c22"))
axC.add_patch(Rectangle((9.0, 0.0), 0.6, 6, facecolor=WOOD, edgecolor="#5c3c22"))
axC.add_patch(Rectangle((1.0, 5.4), 8.0, 0.6, facecolor=WOOD, edgecolor="#5c3c22"))
axC.text(5.0, 5.7, "экран / мебельный короб (закрыто)", ha="center", va="center",
         color="white", fontsize=8.5, fontweight="bold")
# пол
axC.add_patch(Rectangle((1.0, 0.0), 8.0, 1.0, facecolor=TILE, edgecolor=GROUT, linewidth=1.3))
# датчик плашмя
axC.add_patch(FancyBboxPatch((4.2, 1.0), 1.6, 0.5,
              boxstyle="round,pad=0.02,rounding_size=0.1",
              facecolor=SENSOR, edgecolor="black", linewidth=1.2))
axC.text(5.0, 1.25, "датчик", ha="center", va="center", color="white", fontsize=8)
axC.text(5.0, 2.4, "лежит на полу плашмя.\nРобот сюда не заезжает —\nуглубление не нужно.",
         ha="center", va="center", fontsize=9, color="#333")

out = "/Users/pro2kuror/Desktop/VibeCoding/personal/SOUL/Проект/датчик_углубление_схема.png"
fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="white")
print("saved:", out)
