# -*- coding: utf-8 -*-
"""社内説明用のインフォグラフィック（PNG）を作る。

    uv run scripts/make_infographic.py

「手袋を外さないとパソコンを操作できない」という手間を、このツールが
どう減らすのかを1枚にまとめる。文言や色はこのファイルを直せば変えられる。
出力は docs/images/gloves-infographic.png（PowerPointや印刷に貼れる解像度）。
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "gloves-infographic.png"

# 仕上がりサイズ（16:9）。描画は2倍で行い、最後に縮めて輪郭を滑らかにする
W, H = 2400, 1350
SCALE = 2
MARGIN = 100

# --- 色 ---
BG = "#ffffff"
INK = "#1f2937"          # 本文
SUB = "#6b7280"          # 補足
LINE = "#d7dce3"         # 罫線・枠
PANEL = "#f8fafc"        # 箱の下地
RED = "#c0392b"          # 「これまで」の強調
RED_BG = "#fdf0ee"
BLUE = "#0e6ba8"         # 「このツール」の強調
BLUE_BG = "#eef6fb"
GLOVE = "#2f7fd1"        # 手袋の色
SKIN = "#f0c9a4"         # 素手の色
GRAY_OUT = "#c9ced6"     # 不要になったもの

FONT_BOLD = "C:/Windows/Fonts/YuGothB.ttc"
FONT_MED = "C:/Windows/Fonts/YuGothM.ttc"


def font(path, size):
    return ImageFont.truetype(path, size * SCALE)


F_TITLE = font(FONT_BOLD, 62)
F_LEAD = font(FONT_MED, 30)
F_BADGE = font(FONT_BOLD, 30)
F_STEP = font(FONT_BOLD, 30)
F_STEP_SUB = font(FONT_MED, 23)
F_NOTE_BIG = font(FONT_BOLD, 36)
F_NOTE = font(FONT_MED, 27)
F_SEC = font(FONT_BOLD, 32)
F_GES = font(FONT_BOLD, 27)
F_GES_SUB = font(FONT_MED, 24)
F_FOOT = font(FONT_MED, 22)

img = Image.new("RGB", (W * SCALE, H * SCALE), BG)
d = ImageDraw.Draw(img)


# --- 座標を2倍にして描くための小道具 -------------------------------
def s(v):
    return int(round(v * SCALE))


def box(xy, radius=0, fill=None, outline=None, width=1):
    x0, y0, x1, y1 = (s(v) for v in xy)
    if radius:
        d.rounded_rectangle((x0, y0, x1, y1), s(radius), fill=fill,
                            outline=outline, width=s(width))
    else:
        d.rectangle((x0, y0, x1, y1), fill=fill, outline=outline, width=s(width))


def line(xy, fill, width=1):
    d.line([s(v) for v in xy], fill=fill, width=s(width))


def text(xy, body, fnt, fill=INK, anchor="la", spacing=8):
    d.multiline_text((s(xy[0]), s(xy[1])), body, font=fnt, fill=fill,
                     anchor=anchor, spacing=s(spacing), align="center"
                     if anchor[0] == "m" else "left")


def ellipse(xy, fill=None, outline=None, width=1):
    d.ellipse([s(v) for v in xy], fill=fill, outline=outline, width=s(width))


# --- 絵（線画） ---------------------------------------------------
def draw_glove(cx, cy, size, fill, outline, cuff=True):
    """手袋（または手）を正面から見た形。size は手のひらの幅。"""
    pw = size                      # 手のひらの幅
    ph = size * 0.78               # 手のひらの高さ
    fw = pw * 0.19                 # 指の幅
    fh = size * 0.62               # 指の長さ
    top = cy - ph * 0.35

    # 指4本
    for i in range(4):
        x = cx - pw * 0.42 + i * (pw * 0.28)
        length = fh * (0.86 if i in (0, 3) else 1.0)
        box((x - fw / 2, top - length, x + fw / 2, top + ph * 0.3),
            radius=fw / 2, fill=fill, outline=outline, width=3)
    # 親指（右下から斜めに）
    box((cx + pw * 0.30, cy - ph * 0.05, cx + pw * 0.30 + fw, cy + ph * 0.52),
        radius=fw / 2, fill=fill, outline=outline, width=3)
    # 手のひら
    box((cx - pw * 0.52, top, cx + pw * 0.40, cy + ph * 0.55),
        radius=pw * 0.18, fill=fill, outline=outline, width=3)
    if cuff:   # 手袋の袖口
        box((cx - pw * 0.56, cy + ph * 0.45, cx + pw * 0.44, cy + ph * 0.78),
            radius=pw * 0.08, fill=fill, outline=outline, width=3)


def draw_mouse(cx, cy, size, fill, outline):
    w = size * 0.62
    h = size
    box((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2),
        radius=w * 0.45, fill=fill, outline=outline, width=3)
    line((cx - w / 2 + 4, cy - h * 0.12, cx + w / 2 - 4, cy - h * 0.12), outline, 3)
    line((cx, cy - h / 2 + 6, cx, cy - h * 0.12), outline, 3)


def draw_camera(cx, cy, size, fill, outline):
    w, h = size * 1.05, size * 0.72
    box((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2),
        radius=h * 0.22, fill=fill, outline=outline, width=3)
    ellipse((cx - h * 0.26, cy - h * 0.26, cx + h * 0.26, cy + h * 0.26),
            fill=BG, outline=outline, width=3)
    ellipse((cx - h * 0.11, cy - h * 0.11, cx + h * 0.11, cy + h * 0.11),
            fill=outline)
    box((cx - w * 0.16, cy + h / 2, cx + w * 0.16, cy + h / 2 + size * 0.14),
        fill=fill, outline=outline, width=3)


def draw_gear(cx, cy, size, fill, outline):
    r = size * 0.42
    teeth = size * 0.12
    for i in range(8):
        import math
        a = math.pi * 2 * i / 8
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
        box((x - teeth, y - teeth, x + teeth, y + teeth), radius=teeth * 0.4,
            fill=fill, outline=outline, width=3)
    ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=3)
    ellipse((cx - r * 0.38, cy - r * 0.38, cx + r * 0.38, cy + r * 0.38),
            fill=BG, outline=outline, width=3)


def draw_arrow(x0, x1, y, color, width=5):
    head = 16
    line((x0, y, x1 - head, y), color, width)
    d.polygon([(s(x1), s(y)), (s(x1 - head), s(y - head * 0.55)),
               (s(x1 - head), s(y + head * 0.55))], fill=color)


def draw_updown(cx, cy, size, color):
    """上下の矢印（脱ぐ・着ける／スクロールを表す）。"""
    half = size * 0.42
    head = size * 0.16
    line((cx, cy - half, cx, cy + half), color, 5)
    d.polygon([(s(cx), s(cy - half)), (s(cx - head * 0.6), s(cy - half + head)),
               (s(cx + head * 0.6), s(cy - half + head))], fill=color)
    d.polygon([(s(cx), s(cy + half)), (s(cx - head * 0.6), s(cy + half - head)),
               (s(cx + head * 0.6), s(cy + half - head))], fill=color)


# --- ステップの箱 -------------------------------------------------
STEP_W, STEP_H = 340, 230
GAP = 125


def step_x(i):
    return MARGIN + i * (STEP_W + GAP)


def draw_step(i, y, label, sub, icon, accent=False, tone=BLUE):
    x0 = step_x(i)
    x1 = x0 + STEP_W
    fill = RED_BG if (accent and tone is RED) else (BLUE_BG if accent else PANEL)
    edge = tone if accent else LINE
    box((x0, y, x1, y + STEP_H), radius=22, fill=fill, outline=edge,
        width=4 if accent else 2)
    cx = (x0 + x1) / 2
    icon(cx, y + 74)
    text((cx, y + 142), label, F_STEP, tone if accent else INK, anchor="ma")
    if sub:
        text((cx, y + 184), sub, F_STEP_SUB, SUB, anchor="ma")
    return x1


def draw_cross_box(i, y, label):
    """もう要らなくなった手順（×印）。"""
    x0 = step_x(i)
    x1 = x0 + STEP_W
    box((x0, y, x1, y + STEP_H), radius=22, fill="#f4f6f8", outline=GRAY_OUT, width=2)
    pad = 74
    line((x0 + pad, y + pad * 0.7, x1 - pad, y + STEP_H - pad * 0.7), GRAY_OUT, 7)
    line((x1 - pad, y + pad * 0.7, x0 + pad, y + STEP_H - pad * 0.7), GRAY_OUT, 7)
    text(((x0 + x1) / 2, y + STEP_H - 62), label, F_STEP_SUB, GRAY_OUT, anchor="ma")


def badge(x, y, label, color):
    w = len(label) * 32 + 46
    box((x, y, x + w, y + 56), radius=28, fill=color)
    text((x + w / 2, y + 12), label, F_BADGE, "#ffffff", anchor="ma")
    return x + w


# ===================================================================
# 1. 見出し
# ===================================================================
text((MARGIN, 66), "手袋のまま、パソコンを操作する", F_TITLE, INK)
text((MARGIN, 170), "Webカメラが手の動きを読み取り、マウスの代わりになります。"
                    "画面を確認するたびに手袋を外す必要がなくなります。", F_LEAD, SUB)
line((MARGIN, 248, W - MARGIN, 248), LINE, 2)

# ===================================================================
# 2. これまでの流れ
# ===================================================================
BEFORE_Y = 352
badge(MARGIN, 284, "これまで", RED)
text((MARGIN + 250, 296), "画面をちょっと見るだけでも、脱いで・着けてが付いて回る",
     F_NOTE, SUB)

draw_step(0, BEFORE_Y, "作業中", "手袋をしている",
          lambda cx, cy: draw_glove(cx, cy, 86, GLOVE, INK))
draw_step(1, BEFORE_Y, "手袋を外す", "いちいち中断する",
          lambda cx, cy: (draw_glove(cx - 26, cy, 70, GLOVE, INK),
                          draw_updown(cx + 52, cy, 76, RED)),
          accent=True, tone=RED)
draw_step(2, BEFORE_Y, "素手で操作", "マウス・キーボード",
          lambda cx, cy: (draw_glove(cx - 30, cy, 64, SKIN, INK, cuff=False),
                          draw_mouse(cx + 52, cy, 82, PANEL, INK)))
draw_step(3, BEFORE_Y, "手袋を着け直す", "また中断する",
          lambda cx, cy: (draw_glove(cx - 26, cy, 70, GLOVE, INK),
                          draw_updown(cx + 52, cy, 76, RED)),
          accent=True, tone=RED)
draw_step(4, BEFORE_Y, "作業に戻る", "ようやく再開",
          lambda cx, cy: draw_gear(cx, cy, 92, PANEL, INK))

for i in range(4):
    draw_arrow(step_x(i) + STEP_W + 24, step_x(i + 1) - 24,
               BEFORE_Y + STEP_H / 2, SUB)

# ===================================================================
# 3. このツールを使った流れ
# ===================================================================
AFTER_Y = 812
badge(MARGIN, 744, "このツール", BLUE)
text((MARGIN + 290, 756), "手袋をしたまま、カメラに手をかざすだけ", F_NOTE, SUB)

draw_step(0, AFTER_Y, "作業中", "手袋をしている",
          lambda cx, cy: draw_glove(cx, cy, 86, GLOVE, INK))
draw_step(1, AFTER_Y, "手をかざす", "手袋のまま操作",
          lambda cx, cy: (draw_camera(cx - 58, cy, 92, PANEL, INK),
                          draw_glove(cx + 54, cy, 74, GLOVE, BLUE)),
          accent=True, tone=BLUE)
draw_step(2, AFTER_Y, "作業に戻る", "手を下ろすだけ",
          lambda cx, cy: draw_gear(cx, cy, 92, PANEL, INK))

for i in range(2):
    draw_arrow(step_x(i) + STEP_W + 24, step_x(i + 1) - 24,
               AFTER_Y + STEP_H / 2, BLUE)

# 無くなった2ステップを×で示す。本流の続きに見えないよう区切りを入れる
line((step_x(3) - 62, AFTER_Y - 16, step_x(3) - 62, AFTER_Y + STEP_H + 16), LINE, 3)
draw_cross_box(3, AFTER_Y, "手袋を外す")
draw_cross_box(4, AFTER_Y, "手袋を着け直す")
text(((step_x(3) + step_x(4) + STEP_W) / 2, AFTER_Y - 58),
     "この2つが要らなくなる", F_NOTE_BIG, RED, anchor="ma")

# ===================================================================
# 4. 操作のしかた
# ===================================================================
line((MARGIN, 1116, W - MARGIN, 1116), LINE, 2)
text((MARGIN, 1146), "操作のしかた", F_SEC, INK)

GESTURES = (
    ("手を動かす", "カーソルが動く"),
    ("親指＋人差し指", "左クリック"),
    ("親指＋薬指", "右クリック"),
    ("チョキを上下", "スクロール"),
    ("グーを2秒", "操作の入／切"),
)
gx = MARGIN + 250
gw = (W - MARGIN - gx) / len(GESTURES)
for i, (how, what) in enumerate(GESTURES):
    cx = gx + gw * i + gw / 2
    if i:
        line((gx + gw * i, 1142, gx + gw * i, 1226), LINE, 2)
    text((cx, 1140), how, F_GES, INK, anchor="ma")
    text((cx, 1184), what, F_GES_SUB, BLUE, anchor="ma")

text((MARGIN, 1266),
     "起動した直後はマウス操作が無効です（誤操作を防ぐため）。"
     "グーを2秒、またはCtrl+Alt+Hで開始します。手がカメラから3秒見えなければ自動で止まります。",
     F_FOOT, SUB)

# ===================================================================
OUT.parent.mkdir(parents=True, exist_ok=True)
img.resize((W, H), Image.LANCZOS).save(OUT)
print(f"書き出しました: {OUT}  ({W}x{H})")
