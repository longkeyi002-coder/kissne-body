# -*- coding: utf-8 -*-
"""
Kissne 原型 · 图片体检工具
============================================================
用途：在**看不到图**的情况下，用数据判断一张素材能不能用、适合当什么用。

输出（每张图一段）：
  1. 基础信息：模式 / 尺寸 / 体积 / 是否真透明底 / 透明区底下的颜色
  2. 透明度诊断：最大 α、主体 α 峰值 —— 判断有没有"整体发灰/半透"
     透明区底色若是黑 (0,0,0)，大幅缩小时容易出脏边（接入前要做预乘缩放）
  3. 构图：内容包围盒、四边留白、是否贴边（贴边=被画面裁切）
  4. 圆切损失：不透明像素落在内切圆外的比例 —— 判断能不能切圆形头像
  5. 字符图：轮廓（不透明度）+ 配色（白/蓝/金/深色），用来"看"形状与锚点特征位置

用法：
  python tools/img-probe.py <图片路径或通配符> [更多...]
  python tools/img-probe.py "视觉资产/成品素材/通知与头像/_原始生成/*.png"
  python tools/img-probe.py a.png --quick        # 只出统计，不出字符图

依赖：Pillow（本机装在隔离目录，见 sys.path 那行）
============================================================
"""
import sys
import os
import glob

sys.path.insert(0, r"C:/Users/LSY/.workbuddy/binaries/python/libs")
from PIL import Image, ImageStat  # noqa: E402

COLS, ROWS = 68, 34
A_RAMP = " .:-=+*#%@"


def asset_rel(p):
    return p


def classify(r, g, b):
    """把一个像素归纳成锚点关心的几类：白(身体) / 蓝(耳内·蝴蝶结·眼睛) / 金(铃铛) / 深色(描边) / 中间调"""
    if b - r > 22 and b > 130:
        return "B"
    if r > 150 and g > 115 and b < 130 and (r - b) > 35:
        return "G"
    m, mn = max(r, g, b), min(r, g, b)
    if m < 95:
        return "D"
    if mn > 205:
        return "W"
    return "S"


def probe(path, quick=False):
    im = Image.open(path)
    W, H = im.size
    rgba = im.convert("RGBA")
    a = rgba.getchannel("A")
    hist = a.histogram()
    total = W * H
    n0, n255 = hist[0], hist[255]
    mx = max(i for i, v in enumerate(hist) if v > 0)
    peak = max(range(33, 256), key=lambda i: hist[i]) if any(hist[33:]) else 0

    print("=" * 78)
    print("%s   %s  %dx%d  %.1f KB" % (os.path.basename(path), im.mode, W, H, os.path.getsize(path) / 1024.0))

    if n0 > total * 0.03:
        print("  真透明底 OK：全透明 %.1f%% | 不透明 %.1f%% | 最大α %d（峰值 %d）"
              % (n0 * 100.0 / total, n255 * 100.0 / total, mx, peak))
        tr = a.point(lambda v: 255 if v == 0 else 0)
        under = tuple(int(x) for x in ImageStat.Stat(rgba.convert("RGB"), tr).mean)
        warn = "  ← 偏黑，缩小易出脏边，接入前建议预乘缩放+填白" if sum(under) < 120 else ""
        print("  透明区底色 %s%s" % (str(under), warn))
    else:
        print("  ⚠ 没有透明区（%.1f%% 全透明）—— 不是透明底素材，会带白/色底" % (n0 * 100.0 / total))

    bb = a.getbbox() or (0, 0, 0, 0)
    bx0, by0, bx1, by1 = bb
    margins = (bx0, by0, W - bx1, H - by1)
    touched = [n for n, v in zip(("左", "上", "右", "下"), margins) if v <= 1]
    print("  内容包围盒 %s  尺寸 %dx%d  四边留白 左%d 上%d 右%d 下%d"
          % (str(bb), bx1 - bx0, by1 - by0, margins[0], margins[1], margins[2], margins[3]))
    print("  贴边: %s" % ("、".join(touched) + " ← 内容被画面裁切" if touched else "无"))

    S = 256
    sc = float(S) / max(W, H)
    sw, sh = max(1, int(W * sc)), max(1, int(H * sc))
    d = list(a.resize((sw, sh), Image.BOX).getdata())
    cx, cy = sw / 2.0, sh / 2.0
    r2 = (min(sw, sh) / 2.0) ** 2
    n_in = n_out = 0
    for y in range(sh):
        base = y * sw
        dy = (y + 0.5 - cy) ** 2
        for x in range(sw):
            if d[base + x] <= 8:
                continue
            if (x + 0.5 - cx) ** 2 + dy <= r2:
                n_in += 1
            else:
                n_out += 1
    loss = 100.0 * n_out / max(1, n_in + n_out)
    print("  圆切损失 %.1f%% %s" % (loss, "（= 可切圆）" if loss < 0.5 else "（切圆会切掉内容）"))

    if quick:
        return

    print("  --- 轮廓（@=实心 空格=透明）---")
    am = a.resize((COLS, ROWS), Image.BOX)
    ad = list(am.getdata())
    for row in range(ROWS):
        print("  |" + "".join(A_RAMP[min(9, v * 10 // 256)] for v in ad[row * COLS:(row + 1) * COLS]) + "|")

    print("  --- 配色（. 透明 / W 白 / B 蓝 / G 金 / D 深色 / S 中间调）---")
    small = rgba.resize((COLS, ROWS), Image.BOX)
    sd = list(small.getdata())
    for row in range(ROWS):
        line = []
        for v in sd[row * COLS:(row + 1) * COLS]:
            line.append("." if v[3] < 45 else classify(v[0], v[1], v[2]))
        print("  |" + "".join(line) + "|")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quick = "--quick" in sys.argv
    files = []
    for a in args:
        g = glob.glob(a)
        files.extend(g if g else [a])
    if not files:
        print(__doc__)
        return
    for f in sorted(files):
        if os.path.exists(f):
            probe(f, quick)
        else:
            print("找不到: %s" % f)


if __name__ == "__main__":
    main()
