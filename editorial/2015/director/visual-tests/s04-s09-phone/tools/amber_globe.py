"""Render an original amber land-dot globe with a quiet cool rear plane."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def land_mask(source: Path) -> np.ndarray:
    mask = Image.new("L", (1441, 721))
    draw = ImageDraw.Draw(mask)
    for entry in json.loads(source.read_bytes())["features"]:
        outer, *holes = entry["geometry"]["coordinates"]
        project = lambda contour: [(round((lon + 180)*4), round((90 - lat)*4)) for lon, lat in contour]
        draw.polygon(project(outer), fill=255)
        for hole in holes:
            draw.polygon(project(hole), fill=0)
    return np.asarray(mask)


def atmosphere(which: str, size: tuple[int,int], landmap: np.ndarray) -> Image.Image:
    width, height = size
    scale = width / 720
    x, y = np.meshgrid(np.arange(width) / scale, np.arange(height) / scale)
    cx, cy, radius = 391, 580, 322
    norm = np.sqrt(((x-cx)/radius)**2 + ((y-cy)/radius)**2)
    warm_left = np.exp(-(x/225)**2 - (y/169)**2)
    warm_back = np.exp(-((x-439)/256)**2 - ((y-596)/324)**2)
    blue = np.exp(-((x-558)/312)**2 - ((y-730)/271)**2)
    blue_floor = np.exp(-((x-541)/303)**2 - ((y-1063)/108)**2)
    disk = np.clip((1.012 - norm)*56, 0, 1)
    spot = np.exp(-((x-482)/95)**2 - ((y-542)/101)**2) * disk
    balance = np.exp(-((x-270)/65)**2 - ((y-657)/91)**2) * disk
    rim = np.exp(-((norm-.991)/.018)**2) * np.exp(-((x-498)/381)**2 - ((y-775)/319)**2)
    cool_factor = 1.0 if which == "density" else .48
    rgba = np.empty((height,width,4), np.uint8)
    rgba[...,0] = np.clip(3 + 29*warm_left + 14*warm_back + 6*rim + 8*disk*warm_back
                         + 4*cool_factor*blue + 2*blue_floor + 19*spot + 7*balance, 0, 255).astype(np.uint8)
    rgba[...,1] = np.clip(4 + 13*warm_left + 8*warm_back + 5*rim + 3*disk*warm_back
                         + 11*cool_factor*blue + 6*blue_floor + 8*spot + 3*balance, 0, 255).astype(np.uint8)
    rgba[...,2] = np.clip(6 + 3*warm_left + 2*warm_back + 4*rim*cool_factor
                         + 23*cool_factor*blue + 12*blue_floor + 2*spot, 0, 255).astype(np.uint8)
    rgba[...,3] = 255
    bg = Image.fromarray(rgba)

    xs, ys = np.meshgrid(np.arange(40,712,4.8),np.arange(255,908,4.8))
    xx, yy = (xs-cx)/radius, (cy-ys)/radius
    r2 = xx*xx + yy*yy
    depth = np.sqrt(np.maximum(0,1-r2))
    lat0, lon0 = np.deg2rad([30, 99])
    lat = np.rad2deg(np.arcsin(np.clip(yy*np.cos(lat0)+depth*np.sin(lat0),-1,1)))
    lon = (np.rad2deg(lon0+np.arctan2(xx,depth*np.cos(lat0)-yy*np.sin(lat0)))+180)%360-180
    sampled = landmap[np.clip(np.rint((90-lat)*4).astype(int),0,720),
                      np.clip(np.rint((lon+180)*4).astype(int),0,1440)]>0
    rng=np.random.default_rng(127)
    random=rng.random(xs.shape)
    light=np.exp(-((xs-446)/243)**2-((ys-535)/209)**2)
    hot = np.zeros_like(light)
    for lon_city, lat_city, radius_city, weight in [
        (116.4,39.9,7,1.15),(121.5,31.2,6,.95),(114.1,22.5,6,.95),
        (104.1,30.6,7,.70),(139.7,35.7,6,.6),(127.0,37.5,6,.55),
        (103.8,1.3,5,.6),(77.2,28.6,8,.50),
    ]:
        hot += weight*np.exp(-((lon-lon_city)/radius_city)**2-((lat-lat_city)/radius_city)**2)
    illumination = (0.38+.62*depth)*(.32+.68*light)
    fade = np.clip((1-r2)*28,0,1)
    dots=Image.new("RGBA",size)
    d=ImageDraw.Draw(dots)
    halo=Image.new("RGBA",size)
    h=ImageDraw.Draw(halo)
    style_factor=1.0 if which=="density" else .85
    for j,i in np.argwhere((r2<.999) & (sampled | (random>.84))):
        value = illumination[j,i]*fade[j,i]
        region = float(hot[j,i])
        w = float(random[j,i])
        if sampled[j,i]:
            opacity = int(style_factor * min(205, (25+73*w+71*region)*value))
            side = .57 + .53*w + .28*min(1,region)
            chroma = (241,147 if region>.65 else 116,53 if region>.65 else 36)
        else:
            opacity = int((14+7*w)*value)
            side = .46
            chroma = (136,89,49)
        if opacity < 7: continue
        px,py=xs[j,i]*scale,ys[j,i]*scale
        d.rectangle((px-side*scale,py-side*scale,px+side*scale,py+side*scale),
                    fill=(*chroma,opacity))
        if region>.72 and w>.82 and opacity>85:
            spread=(4+region*2)*scale
            h.ellipse((px-spread,py-spread,px+spread,py+spread),
                      fill=(249,119,24,min(42,opacity//4)))
    bg.alpha_composite(halo.filter(ImageFilter.GaussianBlur(7*scale)))
    bg.alpha_composite(dots)
    return bg
