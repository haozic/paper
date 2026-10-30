# -*- coding: utf-8 -*-
"""生成 PWA 图标（P2-1 离线阅读 / 可安装）

产物（全部写进 assets/img/）：
    icon-192.png            192x192，标准图标（purpose=any）
    icon-512.png            512x512，标准图标（purpose=any）
    icon-maskable-512.png   512x512，可裁剪（purpose=maskable，图形收在安全区内）
    apple-touch-icon.png    180x180，iOS 添加到主屏用

图形：深红底 + 白色"党"字，与站点主色（--primary #8b0000）一致。
maskable 版本把字缩到安全区（约 40% 画布），避免被系统裁成圆形时切掉笔画。

用法：
    python scripts/make_icons.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE_DIR, 'assets', 'img')

PRIMARY = (139, 0, 0, 255)      # #8b0000
WHITE = (255, 255, 255, 255)

# 按优先级尝试的中文字体
FONT_CANDIDATES = [
    r'C:\Windows\Fonts\msyhbd.ttc',
    r'C:\Windows\Fonts\msyh.ttc',
    r'C:\Windows\Fonts\simhei.ttf',
    r'C:\Windows\Fonts\simsun.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
    '/System/Library/Fonts/PingFang.ttc',
]


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def render(path, size, glyph_ratio, corner_ratio=0.0):
    from PIL import Image, ImageDraw, ImageFont

    font_path = find_font()
    if font_path is None:
        raise SystemExit('找不到可用的中文字体，无法生成图标')

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景
    if corner_ratio > 0:
        draw.rounded_rectangle([0, 0, size - 1, size - 1],
                               radius=int(size * corner_ratio), fill=PRIMARY)
    else:
        draw.rectangle([0, 0, size - 1, size - 1], fill=PRIMARY)

    # "党"字：按画布比例定字号并垂直居中
    font_size = int(size * glyph_ratio)
    font = ImageFont.truetype(font_path, font_size)
    text = '党'
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=WHITE)

    img.save(path, 'PNG', optimize=True)
    return os.path.getsize(path)


def main():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print('需要 Pillow：pip install pillow')
        return 1

    os.makedirs(IMG_DIR, exist_ok=True)
    jobs = [
        ('icon-192.png', 192, 0.52, 0.18),
        ('icon-512.png', 512, 0.52, 0.18),
        # maskable：满幅背景，字缩到安全区
        ('icon-maskable-512.png', 512, 0.36, 0.0),
        ('apple-touch-icon.png', 180, 0.54, 0.0),
    ]
    for name, size, ratio, corner in jobs:
        path = os.path.join(IMG_DIR, name)
        n = render(path, size, ratio, corner)
        print('  %-26s %4dx%-4d %6d bytes' % (name, size, size, n))
    print('✅ 图标生成完成 -> assets/img/')
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
