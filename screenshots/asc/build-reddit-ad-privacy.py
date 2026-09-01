from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np, os
B   = os.path.expanduser("~/pilot-medical-guardian-content/screenshots")
OUT = "/private/tmp/claude-501/-Users-ryan-pilot-medical-guardian/05b0ba34-5353-4d81-bb37-b09efca5a175/scratchpad/reddit"
S, SFP = 1080, "/System/Library/Fonts/SFNS.ttf"
MAC, PHONE = f"{B}/asc/mac-raw/03-medxpress-prep.png", f"{B}/medxpress.png"
W = {"Regular":400, "Medium":510, "Semibold":590, "Bold":700}

def sf(size, weight="Bold", optical=96):
    f = ImageFont.truetype(SFP, size)
    try:
        v=[]
        for a in f.get_variation_axes():
            n=a["name"].decode() if isinstance(a["name"],bytes) else a["name"]
            if n=="Optical Size": v.append(min(max(optical,a["minimum"]),a["maximum"]))
            elif n=="Weight":     v.append(W.get(weight,700))
            else:                 v.append(a["default"])
        f.set_variation_by_axes(v)
    except Exception: pass
    return f

def bg():
    yv=np.linspace(0,1,S)[:,None]; t=yv**0.85
    a=np.array([6,18,37],float)[None,None,:]*(1-t[:,:,None])+np.array([14,44,82],float)[None,None,:]*t[:,:,None]
    return Image.fromarray(np.repeat(a,S,axis=1).astype("uint8")).convert("RGBA")

def dev(p,w,r):
    im=Image.open(p).convert("RGB"); h=int(im.height*w/im.width); im=im.resize((w,h),Image.LANCZOS)
    m=Image.new("L",(w,h),0); ImageDraw.Draw(m).rounded_rectangle([0,0,w-1,h-1],r,fill=255)
    im=im.convert("RGBA"); im.putalpha(m); return im

def drop(c,im,pos,blur,alpha,dy):
    lay=Image.new("RGBA",c.size,(0,0,0,0))
    lay.paste(Image.new("RGBA",im.size,(0,0,0,255)),(pos[0],pos[1]+dy),
              im.getchannel("A").point(lambda v:int(v*alpha/255)))
    c=Image.alpha_composite(c,lay.filter(ImageFilter.GaussianBlur(blur))); c.alpha_composite(im,pos); return c

def build(l1, l2, out):
    c=bg(); d=ImageDraw.Draw(c)
    f1=sf(62,"Bold")
    while d.textlength(l1,font=f1)>S-120 and f1.size>40: f1=sf(f1.size-2,"Bold")
    f2=sf(40,"Medium",72)
    while d.textlength(l2,font=f2)>S-120 and f2.size>26: f2=sf(f2.size-2,"Medium",72)
    d.text(((S-d.textlength(l1,font=f1))/2, 60), l1, font=f1, fill=(255,255,255,255))
    d.text(((S-d.textlength(l2,font=f2))/2, 152), l2, font=f2, fill=(168,196,236,255))
    c=drop(c,dev(MAC,870,18),(105,250),30,180,18)
    c=drop(c,dev(PHONE,224,26),(800,562),24,200,12)
    c.convert("RGB").save(f"{OUT}/{out}")
    print(f"{out}\n  L1 {f1.size}px '{l1}'\n  L2 {f2.size}px '{l2}'")

build("Your FAA medical, in one place",
      "Records stay on your device and your iCloud",
      "reddit-ad-privacy.png")
