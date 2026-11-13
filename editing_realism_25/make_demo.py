"""Create synthetic shapes for testing only. Never use these for real recruitment."""
from pathlib import Path
from PIL import Image, ImageDraw
from study_design import GROUPS

def make_demo(root='demo_images'):
    root=Path(root)
    if root.exists():raise ValueError('Demo output exists; choose an empty path.')
    for task,animal in GROUPS:
        for i in range(1,6):
            for kind in ['original','edited']:
                p=root/task/animal/kind;p.mkdir(parents=True,exist_ok=True)
                image=Image.new('RGB',(700,450),(119,161,174) if kind=='original' or task=='replace' else (176,190,154))
                d=ImageDraw.Draw(image);d.rectangle((0,280,700,450),fill=(75,116,111))
                if task=='replace' and kind=='edited':d.rectangle((180+i*15,220,330+i*15,300),fill='orange')
                else:d.ellipse((180+i*15,220,330+i*15,300),fill=(55,67,63))
                d.text((20,20),'DEMO ONLY - NOT A RESEARCH IMAGE',fill='white')
                image.save(p/f'{animal}_{i:02d}.png')
    return root

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',default='demo_images')
    print(make_demo(p.parse_args().output))
