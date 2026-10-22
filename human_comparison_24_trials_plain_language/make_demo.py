"""Create synthetic UI-check inputs. These are not experimental data."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

root = Path('demo_images')
if root.exists():
    raise SystemExit('demo_images already exists; use another working folder.')
for animal, y in [('seal', 95), ('whale', 135), ('dolphin', 115)]:
    for i in range(4):
        image = Image.new('RGB', (960,600), '#839ea4')
        draw = ImageDraw.Draw(image)
        for band in range(0,600,12):
            draw.line((0,band,960,band+75),fill=('#93aeb4' if band%24 else '#76989e'),width=4)
        draw.ellipse((160+i*40,y+110,540+i*40,y+260),fill='#354b52')
        mask=Image.new('L',image.size,0)
        ImageDraw.Draw(mask).ellipse((160+i*40,y+110,540+i*40,y+260),fill=255)
        background=Image.new('RGB',image.size,'#839ea4')
        variants={
            'original':image.copy(),
            'remove':Image.composite(background,image,mask),
            'black_mask':Image.composite(Image.new('RGB',image.size,'black'),image,mask),
            'blurring':Image.composite(image.filter(ImageFilter.GaussianBlur(35)),image,mask),
        }
        for method, variant in variants.items():
            folder=root/animal/method
            folder.mkdir(parents=True,exist_ok=True)
            variant.save(folder/f'scene_{i:03d}_{method}.png')
print('Synthetic demonstration images saved in demo_images. Do not use these for your study.')
