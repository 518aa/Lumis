"""
Lumis App Icon v2 - 现代简约风格
渐变背景 + 大写 L + 星星点缀 + 声波暗示
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

SIZE = 1024
output_dir = os.path.dirname(os.path.abspath(__file__))


def gradient_bg(size):
    """深蓝 → 靛紫 对角渐变"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    for y in range(size):
        for x in range(size):
            t = (x + y) / (size * 2)
            r = int(8 + t * 22)
            g = int(10 + t * 18)
            b = int(38 + t * 45)
            img.putpixel((x, y), (r, g, b, 255))
    return img


def draw_star(draw, cx, cy, r_out, r_in, points, **kwargs):
    coords = []
    for i in range(points * 2):
        angle = -math.pi / 2 + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        coords.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(coords, **kwargs)


def make_icon():
    img = gradient_bg(SIZE)
    draw = ImageDraw.Draw(img)
    cx, cy = SIZE // 2, SIZE // 2

    # === 装饰: 大光晕 (中心偏上, 衬托 L) ===
    glow = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(300, 0, -1):
        alpha = int(35 * (300 - r) / 300)
        glow_draw.ellipse([cx - r, cy - r - 30, cx + r, cy + r - 30],
                          fill=(80, 100, 200, alpha))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # === 装饰: 小星星散布 ===
    import random
    random.seed(77)
    stars_data = []
    for _ in range(25):
        sx = random.randint(80, SIZE - 80)
        sy = random.randint(80, SIZE - 80)
        sr = random.uniform(3, 8)
        sa = random.randint(60, 180)
        stars_data.append((sx, sy, sr, sa))

    for sx, sy, sr, sa in stars_data:
        draw_star(draw, sx, sy, sr, sr * 0.4, 4, fill=(255, 255, 255, sa))

    # === 主角: 金色五角星 (L 的左上角) ===
    star_x = cx - 140
    star_y = cy - 200
    # 星星光晕
    glow2 = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    glow2_draw = ImageDraw.Draw(glow2)
    for r in range(120, 0, -1):
        alpha = int(50 * (120 - r) / 120)
        glow2_draw.ellipse([star_x - r, star_y - r, star_x + r, star_y + r],
                           fill=(255, 209, 102, alpha))
    img = Image.alpha_composite(img, glow2)
    draw = ImageDraw.Draw(img)

    # 主星
    draw_star(draw, star_x, star_y, 70, 28, 5, fill=(255, 209, 102, 255))
    # 星内高光
    draw_star(draw, star_x - 5, star_y - 5, 45, 18, 5, fill=(255, 235, 170, 200))

    # === 声波弧线 (右下, 暗示语音) ===
    wave_cx = cx + 180
    wave_cy = cy + 170
    for i, (r, alpha) in enumerate([(60, 50), (90, 35), (120, 20)]):
        draw.arc([wave_cx - r, wave_cy - r, wave_cx + r, wave_cy + r],
                 start=200, end=340, fill=(0, 229, 255, alpha), width=5)

    # === 主角: 大写 L ===
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFNSDisplay-Bold.otf", 520)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 520)
        except:
            font = ImageFont.load_default()

    # L 的阴影
    draw.text((cx - 155 + 6, cy - 280 + 6), "L", fill=(0, 0, 0, 60), font=font)

    # L 主体 - 白色
    draw.text((cx - 155, cy - 280), "L", fill=(255, 255, 255, 255), font=font)

    # L 渐变叠加 (从顶到底 白→浅蓝)
    l_mask = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    l_draw = ImageDraw.Draw(l_mask)
    l_draw.text((cx - 155, cy - 280), "L", fill=(255, 255, 255, 255), font=font)

    gradient_overlay = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    for y in range(SIZE):
        t = y / SIZE
        alpha = int(40 * t)
        for x in range(SIZE):
            if l_mask.getpixel((x, y))[3] > 0:
                gradient_overlay.putpixel((x, y), (100, 160, 255, alpha))

    img = Image.alpha_composite(img, gradient_overlay)

    return img


def make_foreground(icon):
    """foreground 层 = 图标本身 (透明背景+内容)"""
    fg = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    fg.paste(icon, (0, 0), icon)
    return fg


def make_background():
    """background 层 = 纯渐变"""
    return gradient_bg(SIZE)


if __name__ == '__main__':
    res_dir = os.path.join(output_dir, 'app', 'src', 'main', 'res')

    icon = make_icon()
    foreground = make_foreground(icon)
    background = make_background()

    sizes = {
        'mdpi': 48,
        'hdpi': 72,
        'xhdpi': 96,
        'xxhdpi': 144,
        'xxxhdpi': 192,
    }

    for density, px in sizes.items():
        d = os.path.join(res_dir, f'mipmap-{density}')
        os.makedirs(d, exist_ok=True)

        foreground.resize((px, px), Image.LANCZOS).save(
            os.path.join(d, 'ic_launcher_foreground.png'))
        background.resize((px, px), Image.LANCZOS).save(
            os.path.join(d, 'ic_launcher_background.png'))

        # legacy 圆形图标
        bg = background.resize((px, px), Image.LANCZOS)
        fg = foreground.resize((px, px), Image.LANCZOS)
        composite = Image.alpha_composite(bg, fg)
        mask = Image.new('L', (px, px), 0)
        md = ImageDraw.Draw(mask)
        c = px // 2
        md.ellipse([0, 0, px, px], fill=255)
        rounded = Image.new('RGBA', (px, px), (0, 0, 0, 0))
        rounded.paste(composite, (0, 0), mask)
        rounded.save(os.path.join(d, 'ic_launcher.png'))
        print(f'  {density}: {px}x{px} ✓')

    # 预览
    icon.resize((512, 512), Image.LANCZOS).save(
        os.path.join(output_dir, 'ic_launcher_512.png'))
    print('  Preview: 512x512 ✓')
    print('Done!')
