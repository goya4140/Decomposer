#!/usr/bin/env python3
"""Generate an original sample image, without downloading research data."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def make_example(path):
    image = Image.new('RGB', (720, 260), 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 24)
    except OSError:
        font = ImageFont.load_default(size=24)
    draw.rounded_rectangle((40, 70, 240, 190), radius=14, fill='#DBEAFE', outline='#2563EB', width=3)
    draw.rounded_rectangle((480, 70, 680, 190), radius=14, fill='#DCFCE7', outline='#16A34A', width=3)
    draw.text((140, 130), 'Input', font=font, fill='#1E293B', anchor='mm')
    draw.text((580, 130), 'Output', font=font, fill='#1E293B', anchor='mm')
    draw.line((265, 130, 450, 130), fill='#475569', width=4)
    draw.polygon([(450, 130), (436, 122), (436, 138)], fill='#475569')
    image.save(path)
    return image


if __name__ == '__main__':
    path = Path(__file__).with_name('example.png')
    make_example(path)
    print(path)
