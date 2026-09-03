# Reddit 1080x1080, poster crop. Spec: Ryan 2026-09-03.
#   Keep the navy field + the two lines of type. One device: iPhone Home, the 130.
#   No Mac in this square. No "Download". No support screens. No unreadable sidebar sliver.
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, os

B    = os.path.expanduser("~/pilot-medical-guardian-content/screenshots")
OUT  = os.path.expanduser("~/pilot-medical-guardian-content/screenshots/asc")
S    = 1080
SFP  = "/System/Library/Fonts/SFNS.ttf"
PHONE = f"{B}/home.png"                     # raw iPhone Home, the 130, same dummy pilot
W = {"Regular":400, "Medium":510, "Semibold":590, "Bold":700}

L1 = "Your FAA medical, in one place"
L2 = "Records stay on your device and your iCloud"

def sf(size, weight="Bold", optical=96):
    f = ImageFont.truetype(SFP, size)
    try:
        v=[]
        for a in f.get_variation_axes():
            n=a["name"].decode() if isinstance(a["name"],bytes) else a["name"]
            if   n=="Optical Size": v.append(min(max(optical,a["minimum"]),a["maximum"]))
            elif n=="Weight":       v.append(W.get(weight,700))
            else:                   v.append(a["default"])
        f.set_variation_by_axes(v)
    except Exception: pass
    return f

def bg():
    yv=np.linspace(0,1,S)[:,None]; t=yv**0.85
    a=(np.array([6,18,37],float)[None,None,:]*(1-t[:,:,None])
      +np.array([14,44,82],float)[None,None,:]*t[:,:,None])
    return Image.fromarray(np.repeat(a,S,axis=1).astype("uint8")).convert("RGBA")

def rounded(im, r):
    m=Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0,0,im.size[0]-1,im.size[1]-1], r, fill=255)
    im=im.convert("RGBA"); im.putalpha(m); return im

def drop(c, im, pos, blur, alpha, dy):
    lay=Image.new("RGBA", c.size, (0,0,0,0))
    lay.paste(Image.new("RGBA", im.size, (0,0,0,255)), (pos[0], pos[1]+dy),
              im.getchannel("A").point(lambda v:int(v*alpha/255)))
    c=Image.alpha_composite(c, lay.filter(ImageFilter.GaussianBlur(blur)))
    c.alpha_composite(im, pos); return c

def type_block(c, l2_size, y1=58, y2=150):
    d=ImageDraw.Draw(c)
    f1=sf(62,"Bold")
    while d.textlength(L1,font=f1) > S-120 and f1.size>40: f1=sf(f1.size-2,"Bold")
    f2=sf(l2_size,"Medium",72)
    while d.textlength(L2,font=f2) > S-110 and f2.size>26: f2=sf(f2.size-2,"Medium",72)
    d.text(((S-d.textlength(L1,font=f1))/2,  y1), L1, font=f1, fill=(255,255,255,255))
    d.text(((S-d.textlength(L2,font=f2))/2, y2), L2, font=f2, fill=(168,196,236,255))
    return f1.size, f2.size

def variant_full(out):
    """A -- full phone, larger, centred. THE ONE RYAN PICKED (2026-09-03).
    'In one place' has to show more than one thing: certificate clock, BasicMed,
    MedXPress, tab bar. Two fixes over the first cut, both about the tab bar:
      * bottom margin 8px -> 30px, so the bar is not jammed on the canvas edge
      * corner radius 30 -> 18. A real iPhone's radius scaled to this width is
        ~17px; 30 was rounder than the device and the curve was clipping the
        ENDS of the tab pill, which sits only ~19px in from the screen edge."""
    c=bg(); s1,s2 = type_block(c, 46, y1=52, y2=142)
    src=Image.open(PHONE).convert("RGB")
    h = 828; w = int(src.width * h/src.height)
    top = 222
    ph = rounded(src.resize((w,h), Image.LANCZOS), 18)
    c = drop(c, ph, ((S-w)//2, top), 34, 190, 20)
    c.convert("RGB").save(f"{OUT}/{out}", quality=95)
    print(f"  {out}: full phone {w}x{h} at y={top}, bottom={top+h}, margin={S-(top+h)}px, "
          f"L1 {s1}px, L2 {s2}px, phone {w/S*400:.0f}px at 400 wide")

def variant_crop(out):
    """B -- poster crop through the 130 card, bleeding off the bottom edge."""
    c=bg(); s1,s2 = type_block(c, 46)
    src=Image.open(PHONE).convert("RGB")
    src=src.crop((0, 0, src.width, 1420))          # top of phone through the 130 card
    w = 690; h = int(src.height * w/src.width)
    ph = src.resize((w,h), Image.LANCZOS)
    m=Image.new("L",(w,h),0)                        # round the TOP corners only; bottom bleeds
    dr=ImageDraw.Draw(m); dr.rounded_rectangle([0,0,w-1,h+60], 34, fill=255)
    ph=ph.convert("RGBA"); ph.putalpha(m)
    c = drop(c, ph, ((S-w)//2, 268), 38, 195, 22)
    c.convert("RGB").save(f"{OUT}/{out}", quality=95)
    print(f"  {out}: poster crop {w}x{h}, L1 {s1}px, L2 {s2}px, '130' ~{145*(w/1206)*400/S:.0f}px at 400 wide")

variant_full("reddit-ad-poster-A-fullphone.png")
variant_crop("reddit-ad-poster-B-crop.png")
