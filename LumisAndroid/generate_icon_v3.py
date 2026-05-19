"""
Lumis App Icon v3 — 高品质现代简约风格

技术亮点:
- 径向渐变背景（中心微亮，边缘深邃）
- 多层高斯模糊光晕
- 精确几何五角星
- 金属质感字母 L
- 声波弧线
- 星尘粒子系统
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import math
import os
import random

SIZE = 1024
CENTER = SIZE // 2
output_dir = os.path.dirname(os.path.abspath(__file__))


def radial_gradient_bg(size, c_center=(18, 22, 68), c_edge=(8, 10, 38)):
    """径向渐变: 中心稍亮 → 边缘深邃"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    max_r = math.sqrt(2) * size / 2
    for y in range(size):
        for x in range(size):
            dx = x - size / 2
            dy = y - size / 2
            r = math.sqrt(dx * dx + dy * dy)
            t = min(r / max_r, 1.0)
            # 非线性过渡，让中心区域更均匀
            t2 = t * t
            cr = int(c_center[0] + (c_edge[0] - c_center[0]) * t2)
            cg = int(c_center[1] + (c_edge[1] - c_center[1]) * t2)
            cb = int(c_center[2] + (c_edge[2] - c_center[2]) * t2)
            img.putpixel((x, y), (cr, cg, cb, 255))
    return img


def diagonal_gradient_overlay(size, c1=(15, 12, 50), c2=(10, 18, 55)):
    """对角线方向微妙渐变叠加，增加层次"""
    overlay = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    for y in range(size):
        for x in range(size):
            t = (x * 0.6 + y * 0.4) / size
            t = max(0, min(1, t))
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            overlay.putpixel((x, y), (r, g, b, 30))
    return overlay


def make_glow(size, cx, cy, radius, color, intensity=0.8):
    """创建高斯模糊光晕"""
    glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    for r in range(radius, 0, -2):
        alpha = int(intensity * 255 * ((radius - r) / radius) ** 1.5)
        alpha = min(255, max(0, alpha))
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(color[0], color[1], color[2], alpha)
        )
    return glow.filter(ImageFilter.GaussianBlur(radius=radius // 4))


def draw_star_polygon(draw, cx, cy, r_out, r_in, points, **kwargs):
    """绘制精确多角星"""
    coords = []
    for i in range(points * 2):
        angle = -math.pi / 2 + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        coords.append((
            cx + r * math.cos(angle),
            cy + r * math.sin(angle)
        ))
    draw.polygon(coords, **kwargs)


def make_star_with_glow(img, cx, cy, r_out, r_in, points,
                        color=(255, 209, 102),
                        glow_radius=150, glow_intensity=0.5):
    """星星 + 光晕"""
    # 外层光晕
    glow = make_glow(SIZE, cx, cy, glow_radius, color, glow_intensity)
    img = Image.alpha_composite(img, glow)

    # 星星主体
    draw = ImageDraw.Draw(img)
    draw_star_polygon(draw, cx, cy, r_out, r_in, points, fill=(*color, 255))

    # 星星高光（偏移 + 缩小 + 半透明）
    highlight_color = (255, 240, 190)
    draw_star_polygon(draw, cx - 3, cy - 3,
                      r_out * 0.65, r_in * 0.65, points,
                      fill=(*highlight_color, 180))

    return img


def draw_sound_waves(draw, cx, cy, color=(0, 229, 255)):
    """绘制声波弧线"""
    wave_specs = [
        (55, 200, 330, 45, 4),
        (85, 210, 320, 30, 3),
        (115, 220, 310, 18, 3),
    ]
    for r, start, end, alpha, width in wave_specs:
        draw.arc(
            [cx - r, cy - r, cx + r, cy + r],
            start=start, end=end,
            fill=(*color, alpha), width=width
        )


def make_dust_particles(size, count=80, seed=42):
    """星尘粒子层"""
    random.seed(seed)
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    for _ in range(count):
        x = random.randint(20, size - 20)
        y = random.randint(20, size - 20)
        r = random.uniform(1, 4)
        alpha = random.randint(30, 160)
        # 颜色微变
        white_var = random.randint(200, 255)
        draw.ellipse([x - r, y - r, x + r, y + r],
                     fill=(white_var, white_var, 255, alpha))

    # 少量较大的亮星（十字形）
    for _ in range(8):
        x = random.randint(60, size - 60)
        y = random.randint(60, size - 60)
        length = random.randint(6, 14)
        alpha = random.randint(80, 200)
        draw.line([x - length, y, x + length, y],
                  fill=(255, 255, 255, alpha), width=1)
        draw.line([x, y - length, x, y + length],
                  fill=(255, 255, 255, alpha), width=1)

    return layer


def make_letter_l(size, font_path=None):
    """创建金属质感字母 L"""
    # 获取字体
    font = None
    font_size = 480
    candidates = [
        "/System/Library/Fonts/SFNSDisplay-Bold.otf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFProDisplay-Bold.otf",
        "/System/Library/Fonts/Arial Bold.ttf",
    ]
    for path in candidates:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    # L 文字层（白色）
    l_layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(l_layer)

    # 计算文字位置使其居中
    bbox = draw.textbbox((0, 0), "L", font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0] + 10
    ty = (size - th) // 2 - bbox[1] - 30

    # 阴影层（偏移 + 模糊）
    shadow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text((tx + 8, ty + 8), "L", fill=(0, 0, 0, 80), font=font)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=12))

    # L 主体（纯白）
    draw.text((tx, ty), "L", fill=(255, 255, 255, 255), font=font)

    # 渐变叠加：顶部白 → 底部微蓝，增加金属感
    gradient = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    for y in range(size):
        t = y / size
        for x in range(size):
            if l_layer.getpixel((x, y))[3] > 0:
                blue_amount = int(30 * t)
                alpha = int(50 * t)
                gradient.putpixel((x, y), (80, 140, 255, alpha))

    l_layer = Image.alpha_composite(l_layer, gradient)

    # 顶部高光（细条白色半透明）
    highlight = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    hl_draw = ImageDraw.Draw(highlight)
    hl_draw.text((tx - 2, ty - 2), "L", fill=(255, 255, 255, 40), font=font)

    l_layer = Image.alpha_composite(l_layer, highlight)

    return shadow, l_layer


def make_icon():
    """组装最终图标"""
    # 1. 径向渐变背景
    print("  [1/7] 径向渐变背景...")
    img = radial_gradient_bg(SIZE, c_center=(22, 25, 75), c_edge=(8, 10, 38))

    # 2. 对角渐变叠加
    print("  [2/7] 对角渐变叠加...")
    diag = diagonal_gradient_overlay(SIZE)
    img = Image.alpha_composite(img, diag)

    # 3. 星尘粒子
    print("  [3/7] 星尘粒子...")
    dust = make_dust_particles(SIZE, count=80, seed=42)
    img = Image.alpha_composite(img, dust)

    # 4. 中心光晕（衬托 L）
    print("  [4/7] 中心光晕...")
    center_glow = make_glow(SIZE, CENTER, CENTER - 20, 320,
                            (70, 90, 180), intensity=0.4)
    img = Image.alpha_composite(img, center_glow)

    # 5. 金色五角星
    print("  [5/7] 金色五角星...")
    star_x = CENTER - 130
    star_y = CENTER - 190
    img = make_star_with_glow(img, star_x, star_y,
                              r_out=60, r_in=24, points=5,
                              color=(255, 209, 102),
                              glow_radius=130, glow_intensity=0.45)

    # 6. 声波弧线
    print("  [6/7] 声波弧线...")
    draw = ImageDraw.Draw(img)
    wave_cx = CENTER + 180
    wave_cy = CENTER + 180
    draw_sound_waves(draw, wave_cx, wave_cy, color=(0, 229, 255))

    # 7. 字母 L
    print("  [7/7] 金属字母 L...")
    shadow, l_letter = make_letter_l(SIZE)
    img = Image.alpha_composite(img, shadow)
    img = Image.alpha_composite(img, l_letter)

    return img


def make_foreground(icon):
    """Adaptive Icon foreground 层"""
    fg = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    fg.paste(icon, (0, 0), icon)
    return fg


def make_background():
    """Adaptive Icon background 层"""
    bg = radial_gradient_bg(SIZE, c_center=(22, 25, 75), c_edge=(8, 10, 38))
    diag = diagonal_gradient_overlay(SIZE)
    return Image.alpha_composite(bg, diag)


if __name__ == '__main__':
    res_dir = os.path.join(output_dir, 'app', 'src', 'main', 'res')

    print("🎨 生成 Lumis 图标 v3...")
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

        fg = foreground.resize((px, px), Image.LANCZOS)
        bg = background.resize((px, px), Image.LANCZOS)
        fg.save(os.path.join(d, 'ic_launcher_foreground.png'))
        bg.save(os.path.join(d, 'ic_launcher_background.png'))

        # Legacy 圆形图标
        composite = Image.alpha_composite(bg, fg)
        mask = Image.new('L', (px, px), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse([0, 0, px, px], fill=255)
        rounded = Image.new('RGBA', (px, px), (0, 0, 0, 0))
        rounded.paste(composite, (0, 0), mask)
        rounded.save(os.path.join(d, 'ic_launcher.png'))
        print(f'  {density}: {px}x{px} ✓')

    # 预览
    preview_path = os.path.join(output_dir, 'ic_launcher_512.png')
    icon.resize((512, 512), Image.LANCZOS).save(preview_path)
    print(f'  Preview: {preview_path}')

    # 原始尺寸保存
    full_path = os.path.join(output_dir, 'ic_launcher_1024.png')
    icon.save(full_path)
    print(f'  Full: {full_path}')
    print('✅ Done!')
