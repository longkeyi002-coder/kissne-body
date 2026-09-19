# -*- coding: utf-8 -*-
"""
Kissne 手机端低保真原型 · 素材生成器
------------------------------------------------------------
一次性生成统一的 assets/ 素材目录（占位实现，不重绘正式角色）：

  - 角色 / 插画占位  -> 灰阶标签盒 SVG
  - 背景占位        -> 半透明标签盒（透出底层 CSS 色块）
  - 动画占位        -> 轻量 CSS 动画 SVG，内嵌 prefers-reduced-motion 静态降级
  - 图标            -> 单个 SVG 文件 + 精灵 sprite（currentColor，host 主题可继承）
  - 特效占位        -> 轻量动画 SVG

产物（全部位于 prototype/assets/）：
  _manifest.js        运行时素材清单（window.KSN_ASSETS，无需 fetch，file:// 可用）
  manifest.json        人类可读清单（登记用）
  icons/sprite-data.js 精灵标记字符串（window.KSN_SPRITE）
  icons/sprites.svg    精灵文件（与 sprite-data 同步）
  icons/<name>.svg     每个图标单独文件（可替换的权威源）
  characters/...       角色占位
  animations/...       动画占位
  backgrounds/...      背景占位
  effects/...          特效占位
  placeholders/...     通用插画占位

成品图接入（可选）：
  把成品图按 assets/_inbox/README.md 里的文件名放进 assets/_inbox/，再运行本脚本，
  即可用真图替换对应占位盒；没提供的条目保持占位，互不影响。
  头像 / 角色还能按状态换图：<基础名>-<state>.png（思考一张、开心一张…）。

修改素材后重新运行：python tools/gen-assets.py
"""
import os
import sys

# 本机 Pillow 装在隔离目录（见 tools/img-probe.py 的同款处理）。
# 找不到也没关系：真图会退化为"原样复制"，只是不做防黑边缩放。
for _p in (
    r"C:/Users/LSY/.workbuddy/binaries/python/libs",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "libs"),
):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def w(rel, content):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    print("  +", rel)


# --------------------------------------------------------------------------
# 通用占位盒（角色 / 插画）
# --------------------------------------------------------------------------
def box_svg(title, sub):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" '
        'preserveAspectRatio="xMidYMid meet" width="100%" height="100%">\n'
        '  <rect x="3" y="3" width="114" height="114" rx="14" fill="#ECECF1" stroke="#CFCFD8" stroke-width="2"/>\n'
        '  <rect x="10" y="10" width="100" height="100" rx="10" fill="none" stroke="#CFCFD8" '
        'stroke-width="1" stroke-dasharray="4 4" opacity="0.7"/>\n'
        '  <text x="60" y="57" text-anchor="middle" font-family="-apple-system,Segoe UI,Roboto,sans-serif" '
        'font-size="13" font-weight="700" fill="#6B6B76">' + title + '</text>\n'
        '  <text x="60" y="76" text-anchor="middle" font-family="sans-serif" font-size="9" '
        'fill="#9A9AA3" letter-spacing="1.5">' + sub + '</text>\n'
        '</svg>\n'
    )


# --------------------------------------------------------------------------
# 背景占位（半透明，透出底层 CSS 色块）
# --------------------------------------------------------------------------
def bg_svg(title):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'preserveAspectRatio="none" width="100%" height="100%">\n'
        '  <rect x="0" y="0" width="100" height="100" fill="#000" opacity="0"/>\n'
        '  <rect x="2" y="2" width="96" height="96" rx="4" fill="none" stroke="#B9B9C4" '
        'stroke-width="1.5" stroke-dasharray="6 5" opacity="0.85"/>\n'
        '  <text x="50" y="52" text-anchor="middle" font-family="sans-serif" font-size="6" '
        'fill="#A6A6B0" letter-spacing="1">BG · ' + title + '</text>\n'
        '</svg>\n'
    )


# --------------------------------------------------------------------------
# 动画占位（轻量 CSS 动画 + 静态 fallback）
# 每个都内嵌 @media (prefers-reduced-motion: reduce) 关闭动画 = 静态首帧
# --------------------------------------------------------------------------
def anim_typing():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>\n'
        '  .d{fill:#9A9AA3;animation:ksnblink 1.2s infinite}\n'
        '  .d2{animation-delay:.2s}.d3{animation-delay:.4s}\n'
        '  @keyframes ksnblink{0%,60%,100%{opacity:.35}30%{opacity:1}}\n'
        '  @media (prefers-reduced-motion: reduce){.d{animation:none;opacity:.7}}\n'
        '</style>\n'
        '  <rect x="3" y="3" width="114" height="54" rx="12" fill="#ECECF1" stroke="#CFCFD8" stroke-width="2"/>\n'
        '  <circle class="d" cx="46" cy="28" r="5"/>\n'
        '  <circle class="d d2" cx="60" cy="28" r="5"/>\n'
        '  <circle class="d d3" cx="74" cy="28" r="5"/>\n'
        '  <text x="60" y="50" text-anchor="middle" font-family="sans-serif" font-size="8" '
        'fill="#9A9AA3" letter-spacing="1">typing · 占位</text>\n'
        '</svg>\n'
    )


def anim_spin(inner, label, dur=6):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>\n'
        '  .spin{transform-origin:60px 60px;animation:ksnspin ' + str(dur) + 's linear infinite}\n'
        '  @keyframes ksnspin{to{transform:rotate(360deg)}}\n'
        '  @media (prefers-reduced-motion: reduce){.spin{animation:none}}\n'
        '</style>\n'
        '  <rect x="3" y="3" width="114" height="114" rx="14" fill="#ECECF1" stroke="#CFCFD8" stroke-width="2"/>\n'
        + inner +
        '  <text x="60" y="108" text-anchor="middle" font-family="sans-serif" font-size="8" '
        'fill="#9A9AA3" letter-spacing="1">' + label + '</text>\n'
        '</svg>\n'
    )


def anim_orbit():
    inner = (
        '  <circle cx="60" cy="60" r="15" fill="#D7D7E0"/>\n'
        '  <g class="spin"><circle cx="60" cy="18" r="5" fill="#9A9AA3"/></g>\n'
    )
    return anim_spin(inner, "orbit · 占位", 6)


def anim_sync():
    inner = (
        '  <g class="spin" style="transform-origin:60px 60px">\n'
        '    <path d="M60 30 A30 30 0 0 1 90 60" fill="none" stroke="#9A9AA3" stroke-width="6" '
        'stroke-linecap="round"/>\n'
        '  </g>\n'
        '  <path d="M60 90 A30 30 0 0 1 30 60" fill="none" stroke="#D7D7E0" stroke-width="6" '
        'stroke-linecap="round"/>\n'
    )
    return anim_spin(inner, "sync · 占位", 1.4)


def anim_pulse_arc():
    inner = (
        '  <circle cx="60" cy="60" r="26" fill="none" stroke="#9A9AA3" stroke-width="4">\n'
        '    <animate attributeName="r" values="20;40" dur="1.4s" repeatCount="indefinite"/>\n'
        '    <animate attributeName="opacity" values="0.8;0" dur="1.4s" repeatCount="indefinite"/>\n'
        '  </circle>\n'
        '  <circle cx="60" cy="60" r="14" fill="#D7D7E0"/>\n'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>@media (prefers-reduced-motion: reduce){circle>animate{display:none}}</style>\n'
        + inner +
        '  <text x="60" y="108" text-anchor="middle" font-family="sans-serif" font-size="8" '
        'fill="#9A9AA3" letter-spacing="1">pulse · 占位</text>\n'
        '</svg>\n'
    )


def anim_fade():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>\n'
        '  .m{opacity:0;animation:ksnfade 1.8s ease-in-out infinite}\n'
        '  @keyframes ksnfade{0%,100%{opacity:0}50%{opacity:1}}\n'
        '  @media (prefers-reduced-motion: reduce){.m{animation:none;opacity:1}}\n'
        '</style>\n'
        '  <rect x="3" y="3" width="114" height="54" rx="12" fill="#ECECF1" stroke="#CFCFD8" stroke-width="2"/>\n'
        '  <rect class="m" x="14" y="14" width="92" height="8" rx="4" fill="#CFCFD8"/>\n'
        '  <rect class="m" x="14" y="28" width="70" height="8" rx="4" fill="#CFCFD8" '
        'style="animation-delay:.15s"/>\n'
        '  <rect class="m" x="14" y="42" width="84" height="8" rx="4" fill="#CFCFD8" '
        'style="animation-delay:.3s"/>\n'
        '  <text x="60" y="56" text-anchor="middle" font-family="sans-serif" font-size="7" '
        'fill="#9A9AA3" letter-spacing="1">fade · 占位</text>\n'
        '</svg>\n'
    )


def anim_push():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>\n'
        '  .s{animation:ksnpush 1.8s ease-in-out infinite}\n'
        '  @keyframes ksnpush{0%{transform:translateX(40px);opacity:0}40%,100%{transform:translateX(0);opacity:1}}\n'
        '  @media (prefers-reduced-motion: reduce){.s{animation:none;opacity:1}}\n'
        '</style>\n'
        '  <rect x="3" y="3" width="114" height="54" rx="12" fill="#ECECF1" stroke="#CFCFD8" stroke-width="2"/>\n'
        '  <g class="s">\n'
        '    <rect x="14" y="14" width="92" height="8" rx="4" fill="#CFCFD8"/>\n'
        '    <rect x="14" y="28" width="70" height="8" rx="4" fill="#CFCFD8"/>\n'
        '    <rect x="14" y="42" width="84" height="8" rx="4" fill="#CFCFD8"/>\n'
        '  </g>\n'
        '  <text x="60" y="56" text-anchor="middle" font-family="sans-serif" font-size="7" '
        'fill="#9A9AA3" letter-spacing="1">push · 占位</text>\n'
        '</svg>\n'
    )


def anim_logo_morph():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>\n'
        '  .k{transform-origin:60px 60px;animation:ksnmorph 2.9s ease-in-out infinite}\n'
        '  @keyframes ksnmorph{0%{transform:scale(.4);opacity:0}30%{transform:scale(1);opacity:1}'
        '70%{transform:scale(1);opacity:1}100%{transform:scale(.96);opacity:.9}}\n'
        '  @media (prefers-reduced-motion: reduce){.k{animation:none;transform:scale(1);opacity:1}}\n'
        '</style>\n'
        '  <rect x="3" y="3" width="114" height="114" rx="14" fill="#fff" stroke="#CFCFD8" stroke-width="2"/>\n'
        '  <text class="k" x="60" y="70" text-anchor="middle" font-family="-apple-system,Segoe UI,sans-serif" '
        'font-size="34" font-weight="800" fill="#3A3A40">Kissne</text>\n'
        '</svg>\n'
    )


def anim_duo_reveal():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="100%" height="100%" '
        'preserveAspectRatio="xMidYMid meet">\n'
        '<style>\n'
        '  .a{animation:ksnup 2.6s ease-out infinite}\n'
        '  .b{animation:ksnup 2.6s ease-out .3s infinite}\n'
        '  @keyframes ksnup{0%{transform:translateY(14px);opacity:0}35%,100%{transform:translateY(0);opacity:1}}\n'
        '  @media (prefers-reduced-motion: reduce){.a,.b{animation:none;opacity:1}}\n'
        '</style>\n'
        '  <rect x="3" y="3" width="114" height="114" rx="14" fill="#ECECF1" stroke="#CFCFD8" stroke-width="2"/>\n'
        '  <circle class="a" cx="44" cy="60" r="20" fill="#CFE0F2"/>\n'
        '  <circle class="b" cx="76" cy="60" r="20" fill="#D7EBDD"/>\n'
        '  <text x="60" y="108" text-anchor="middle" font-family="sans-serif" font-size="8" '
        'fill="#9A9AA3" letter-spacing="1">duo · 占位</text>\n'
        '</svg>\n'
    )


# --------------------------------------------------------------------------
# 特效占位
# --------------------------------------------------------------------------
def fx_glow():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="100%" height="100%">\n'
        '<style>.g{animation:ksnglow 2s ease-in-out infinite}'
        '@keyframes ksnglow{0%,100%{opacity:.35}50%{opacity:.9}}'
        '@media (prefers-reduced-motion: reduce){.g{animation:none;opacity:.7}}</style>\n'
        '  <circle class="g" cx="40" cy="40" r="30" fill="#C9D6F2" opacity="0.5"/>\n'
        '</svg>\n'
    )


def fx_ripple():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="100%" height="100%">\n'
        '<style>.r{transform-origin:40px 40px;animation:ksnripple 1.6s ease-out infinite}'
        '@keyframes ksnripple{0%{transform:scale(.3);opacity:.9}100%{transform:scale(1.4);opacity:0}}'
        '@media (prefers-reduced-motion: reduce){.r{animation:none;opacity:.6}}</style>\n'
        '  <circle class="r" cx="40" cy="40" r="22" fill="none" stroke="#9A9AA3" stroke-width="3"/>\n'
        '</svg>\n'
    )


def fx_pulse():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="100%" height="100%">\n'
        '<style>.p{transform-origin:40px 40px;animation:ksnpls 1.4s ease-in-out infinite}'
        '@keyframes ksnpls{0%,100%{transform:scale(1)}50%{transform:scale(1.18)}}'
        '@media (prefers-reduced-motion: reduce){.p{animation:none}}</style>\n'
        '  <circle class="p" cx="40" cy="40" r="24" fill="#D7D7E0"/>\n'
        '</svg>\n'
    )


def fx_shimmer():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40" width="100%" height="100%">\n'
        '<style>.s{animation:ksnsh 1.8s linear infinite}'
        '@keyframes ksnsh{0%{transform:translateX(-60px)}100%{transform:translateX(120px)}}'
        '@media (prefers-reduced-motion: reduce){.s{animation:none;opacity:0}}</style>\n'
        '  <rect x="2" y="2" width="116" height="36" rx="8" fill="#ECECF1"/>\n'
        '  <rect class="s" x="0" y="2" width="40" height="36" rx="8" fill="#fff" opacity="0.7"/>\n'
        '</svg>\n'
    )


# --------------------------------------------------------------------------
# 图标（线性，currentColor，host 主题可继承）
# --------------------------------------------------------------------------
ICONS = {
    "home": '<path d="M4 10.4 12 4l8 6.4V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z"/>',
    "chat": '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7A2.5 2.5 0 0 1 17.5 16H10l-4.4 3.5a.3.3 0 0 1-.6-.2z"/>',
    "planet": '<circle cx="12" cy="12" r="5.5"/><ellipse cx="12" cy="12" rx="10.2" ry="3.4" transform="rotate(-18 12 12)"/>',
    "memory": '<ellipse cx="12" cy="6.2" rx="6.8" ry="2.8"/><path d="M5.2 6.2v11.6c0 1.6 3 2.8 6.8 2.8s6.8-1.2 6.8-2.8V6.2"/><path d="M5.2 12c0 1.6 3 2.8 6.8 2.8s6.8-1.2 6.8-2.8"/>',
    "back": '<path d="M14.5 5 8 12l6.5 7"/>',
    "chevron": '<path d="M9.5 5 16 12l-6.5 7"/>',
    "gear": '<path d="M4 7.5h9.2M17.4 7.5H20M4 16.5h5.2M13.4 16.5H20"/><circle cx="15.3" cy="7.5" r="2.3"/><circle cx="11.3" cy="16.5" r="2.3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="6.3"/><path d="M15.7 15.7 20.5 20.5"/>',
    "sync": '<path d="M20 12a8 8 0 0 1-13.6 5.7M4 12a8 8 0 0 1 13.6-5.7"/><path d="M17.6 3v3.6h-3.6M6.4 21v-3.6h3.6"/>',
    "check": '<path d="M5 12.6 10 17.5 19.2 7"/>',
    "alert": '<path d="M12 4.6 20.8 19.4H3.2z"/><path d="M12 10v4.2M12 17.1h.01"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "trash": '<path d="M4 7h16M9.2 7V4.8h5.6V7M6.2 7l.9 13h9.8l.9-13"/>',
    "edit": '<path d="M4 20h4L20 8l-4-4L4 16z"/>',
    "wifioff": '<path d="M3.2 3.2 20.8 20.8"/><path d="M5.2 12.4a10 10 0 0 1 4.6-2.3M18.8 12.4a10 10 0 0 0-3.2-2.1"/><path d="M8.6 15.9a5 5 0 0 1 6.8 0"/><path d="M12 19.6h.01"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 3.2v4.4h-4.4"/>',
    "clock": '<circle cx="12" cy="12" r="8"/><path d="M12 7.4V12l3.2 2"/>',
    "user": '<circle cx="12" cy="8.4" r="3.5"/><path d="M5.2 20a6.8 6.8 0 0 1 13.6 0"/>',
    "server": '<rect x="4" y="4.2" width="16" height="6" rx="2"/><rect x="4" y="13.8" width="16" height="6" rx="2"/><path d="M7.4 7.2h.01M7.4 16.8h.01"/>',
    "cpu": '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 3.2v2.2M14 3.2v2.2M10 18.6v2.2M14 18.6v2.2M3.2 10h2.2M3.2 14h2.2M18.6 10h2.2M18.6 14h2.2"/>',
    "info": '<circle cx="12" cy="12" r="8.4"/><path d="M12 11.2v4.6M12 7.9h.01"/>',
    "bell": '<path d="M6.2 16.2V11a5.8 5.8 0 1 1 11.6 0v5.2l1.4 2.4H4.8z"/><path d="M10.2 19.2a1.9 1.9 0 0 0 3.6 0"/>',
    "link": '<path d="M9.6 14.4 14.4 9.6"/><path d="M7.6 12 6.2 13.4a3.4 3.4 0 0 0 4.8 4.8L12.4 16.8"/><path d="M16.4 12l1.4-1.4a3.4 3.4 0 0 0-4.8-4.8L11.6 7.2"/>',
    "send": '<path d="M4 12 20 4.6 15.2 20l-3.4-5.6z"/><path d="M11.8 14.4 20 4.6"/>',
    "image": '<rect x="3.4" y="5" width="17.2" height="14" rx="2.4"/><circle cx="8.6" cy="10" r="1.6"/><path d="M4.4 17.4 9.6 12l4 4.2 2.8-2.6 3.2 3.4"/>',
    "file": '<path d="M13.4 3.4H7.2a2 2 0 0 0-2 2v13.2a2 2 0 0 0 2 2h9.6a2 2 0 0 0 2-2V9z"/><path d="M13.4 3.4V9h5.4"/>',
    "smile": '<circle cx="12" cy="12" r="8.4"/><path d="M8.6 14.4a4.4 4.4 0 0 0 6.8 0"/><path d="M9.4 9.7h.01M14.6 9.7h.01"/>',
    "call": '<path d="M5.2 4.6h3.4l1.6 4-2 1.4a11 11 0 0 0 5.8 5.8l1.4-2 4 1.6v3.4a1.6 1.6 0 0 1-1.8 1.6A15.6 15.6 0 0 1 3.6 6.4 1.6 1.6 0 0 1 5.2 4.6z"/>',
    "mic": '<rect x="9.2" y="3.4" width="5.6" height="10.2" rx="2.8"/><path d="M6.2 11.6a5.8 5.8 0 0 0 11.6 0"/><path d="M12 17.4v3.2"/>',
    "micoff": '<rect x="9.2" y="3.4" width="5.6" height="10.2" rx="2.8"/><path d="M6.2 11.6a5.8 5.8 0 0 0 11.6 0"/><path d="M12 17.4v3.2"/><path d="M4.2 4.2 19.8 19.8"/>',
    "speaker": '<path d="M4.6 9.4h3.6L12.6 5.6v12.8L8.2 14.6H4.6z"/><path d="M15.6 9.4a3.6 3.6 0 0 1 0 5.2M18.2 7a7.2 7.2 0 0 1 0 10"/>',
    "screen": '<rect x="3.2" y="4.6" width="17.6" height="12" rx="2.2"/><path d="M9 20.2h6"/><path d="M12 13.4V8.6M9.6 11l2.4-2.4L14.4 11"/>',
    "plug": '<path d="M9 3.2v5M15 3.2v5"/><path d="M6.6 8.2h10.8v3.4a5.4 5.4 0 0 1-10.8 0z"/><path d="M12 17v3.8"/>',
    "off": '<path d="M12 3.4v7.4"/><path d="M6.6 7.4a7.6 7.6 0 1 0 10.8 0"/>',
    "box": '<path d="M12 3.4 20 7.6v8.8L12 20.6 4 16.4V7.6z"/><path d="M4 7.6 12 12l8-4.4M12 12v8.6"/>',
    "paw": '<path d="M12 20.6c2.7 0 4.7-1.6 4.7-3.7 0-1.8-1.4-2.7-2.6-3.3-.9-.5-1.4-.9-2.1-.9s-1.2.4-2.1.9c-1.2.6-2.6 1.5-2.6 3.3 0 2.1 2 3.7 4.7 3.7Z"/>'
           + '<ellipse cx="6.8" cy="10.6" rx="1.9" ry="2.3"/><ellipse cx="10.3" cy="7.1" rx="1.9" ry="2.4"/>'
           + '<ellipse cx="14.4" cy="7.3" rx="1.9" ry="2.4"/><ellipse cx="18" cy="11" rx="1.9" ry="2.3"/>',
    "hoof": '<path d="M9 4.4C7.2 6.2 6.3 9.1 6.3 12.6c0 4 1.3 7 3 7 1.6 0 2.4-1.7 2.4-4.1V8.9c0-2.4-1.3-5.7-2.7-4.5Z"/>'
           + '<path d="M15 4.4c1.8 1.8 2.7 4.7 2.7 8.2 0 4-1.3 7-3 7-1.6 0-2.4-1.7-2.4-4.1V8.9c0-2.4 1.3-5.7 2.7-4.5Z"/>',
}


def icon_svg(name):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
        'width="24" height="24">' + ICONS[name] + '</svg>\n'
    )


def sprite_svg():
    syms = "\n".join(
        '  <symbol id="ic-' + n + '" viewBox="0 0 24 24">' + p + "</symbol>"
        for n, p in ICONS.items()
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none" width="0" height="0" '
        'aria-hidden="true">\n' + syms + "\n</svg>\n"
    )


# --------------------------------------------------------------------------
# 运行时清单：占位标记代码 -> assets 路径
# --------------------------------------------------------------------------
PH_MAP = {
    "FOX_SPLASH_CHARACTER": "characters/yeqingxu/avatar/splash.svg",
    "SHEEP_SPLASH_CHARACTER": "characters/sheep/avatar/splash.svg",
    "FOX_CHAT_AVATAR": "characters/yeqingxu/avatar/chat.svg",
    "USER_AVATAR": "characters/duo/avatar/user.svg",
    "FOX_HOME_CHARACTER": "characters/yeqingxu/avatar/home-card.svg",
    "FOX_NOTIFICATION_AVATAR": "characters/yeqingxu/notifications/avatar.svg",
    "FOX_STATE_EMOTION": "characters/yeqingxu/expressions/state.svg",
    "EARTH_STATE": "backgrounds/earth.svg",
    "AI_WORLD_STATE": "backgrounds/aiworld.svg",
    "FOX_PIXEL_SPRITE": "characters/yeqingxu/actions/pixel.svg",
    "MEMORY_EMPTY_ILLUSTRATION": "placeholders/memory-empty.svg",
    "CONNECTION_SUCCESS_ILLUSTRATION": "placeholders/connection-success.svg",
    "OFFLINE_ILLUSTRATION": "placeholders/offline.svg",
    "SHEEP_CHARACTER_RESERVED": "characters/sheep/avatar/home-card.svg",
    "STICKER_PACK": "placeholders/sticker.svg",
}


# --------------------------------------------------------------------------
# 真图覆盖（可选）：_inbox/ 里放了成品图就自动接进来
# --------------------------------------------------------------------------
# 用法：按下面 REAL_NAMES 的文件名把成品图放进 assets/_inbox/，再运行本脚本。
#       有真图的条目用真图，其余继续用占位盒；真图被复制到 assets/real/，
#       清单路径自动切换，页面代码一行都不用改。
#       占位 SVG 一律保留不删 —— 把 _inbox/ 里的真图挪走再跑一次即可退回占位。
INBOX = os.path.join(ROOT, "_inbox")

REAL_NAMES = {
    "FOX_SPLASH_CHARACTER":            "fox-splash",
    "SHEEP_SPLASH_CHARACTER":          "sheep-splash",
    "FOX_CHAT_AVATAR":                 "fox-chat-avatar",
    "USER_AVATAR":                     "user-avatar",
    "FOX_HOME_CHARACTER":              "fox-home-card",
    "FOX_NOTIFICATION_AVATAR":         "fox-notification",
    "FOX_STATE_EMOTION":               "fox-state-emotion",
    "FOX_PIXEL_SPRITE":                "fox-pixel",
    "SHEEP_CHARACTER_RESERVED":        "sheep-home-card",
    "MEMORY_EMPTY_ILLUSTRATION":       "illust-memory-empty",
    "CONNECTION_SUCCESS_ILLUSTRATION": "illust-connection-success",
    "OFFLINE_ILLUSTRATION":            "illust-offline",
    "STICKER_PACK":                    "sticker-pack",
}

REAL_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# 角色 / 头像按**状态**换图（思考一个、开心一个…）。命名规则：
#     基础名.png            -> 兜底图（idle；也是"没给该状态图"时的回落）
#     基础名-<state>.png    -> 该状态专用的图
# state 名字是自由的（原型里目前用 screens-a.js 的 AVA_STATES 那 9 个），扫描是通用的。
PH_STATES = {}


def _first(base):
    for ext in REAL_EXTS:
        cand = os.path.join(INBOX, base + ext)
        if os.path.exists(cand):
            return cand
    return None


# 真图接入时允许的最大长边（None = 原样不缩放，像素图必须 None，缩放会糊）
REAL_MAX_SIDE = {
    "FOX_CHAT_AVATAR":          256,   # 聊天头像：最大只显示到 ~118px，256 足够
    "FOX_NOTIFICATION_AVATAR":  256,
    "USER_AVATAR":              256,
    "FOX_HOME_CHARACTER":       720,   # 首页星卡整幅插画（显示 ~176×152，720 已够 4x）
    "SHEEP_CHARACTER_RESERVED": 720,
    "FOX_PIXEL_SPRITE":         None,
}
DEFAULT_MAX_SIDE = 512

# 不透明大图转 JPEG 的质量（透明底素材一律仍存 PNG）
JPEG_QUALITY = 84

# --------------------------------------------------------------------------
# 星卡插画的"构图整理"：进卡之前先摆一次位
# --------------------------------------------------------------------------
# 两张星卡并排时各占一半，插画进卡后被 cover 成 177.5×159 的横条
# （比例 1.116，和原图 1.138 几乎一样，所以实际上**横向没裁掉多少**）。
#
# 真正的元凶是卡的 18px 圆角：换算回源图是 133px 见方的一块，而太阳 / 月亮
# 正好就贴着画幅的角（日间在右上、夜间在左上）。圆角一啃，日间那张像"没有太阳"。
#   —— 所以只能把整幅内容往里收一点，把太阳 / 月亮挪离边角。
#
# 缩多少是量出来的，不是拍的：把 1.00 / 0.94 / 0.92 / 0.90 / 0.88 各渲染一遍
# 卡片（同一个 cover + 同一个圆角）对照，0.94 起脱离圆角、0.92 余量稳，
# 再往下缩（0.88）狐狸夜间那张底部会拉出一条发平的地面色带。取 0.92。
#
#   mirror : 左右翻，为的是让两张卡**脸对脸**。
#            ⚠ 判朝向要看**视线**（瞳孔偏哪边 / 低头看哪只手的手机），**不能看头的左右位置** ——
#            我第一轮就是按"头在左还是右"判的，结果把狐狸翻对了、把小羊判反了。
#            实际两张源图的视线**都是朝外的**：小羊朝左、狐狸朝右，
#            所以**两张都得翻**，翻完小羊朝右、狐狸朝左，正好对上。
#   margin : 内容缩到画幅的这个比例再居中，四周由边缘像素向外拉伸补齐。
CARD_COMPOSE = {
    "SHEEP_CHARACTER_RESERVED": {"mirror": True,  "margin": 0.92},   # 人人星（左卡·小羊）：朝左→翻成朝右
    "FOX_HOME_CHARACTER":       {"mirror": True,  "margin": 0.92},   # 小机星（右卡·叶青栩）：朝右→翻成朝左
}


def _edge_extend(im, factor):
    """内容缩到 factor 居中，四周用**最外一圈像素向外拉伸**补齐。

    注意：不是留白、也不是裁掉。用户要的是"整幅构图都在，同时太阳/月亮离边有余量"，
    所以做法是把画面整体往里收，外面那一圈由**画面自己的边缘像素往外拉**填上。

    为什么不用"把画面放大后模糊当底"：那样在内容边和延伸边之间会留下看得见的
    一圈方框接缝（试过，卡面上是淡淡一个矩形）。用最外一圈像素直接拉出去，
    边界处的像素和内容**完全一致**，天然无缝；而这类插画四边本来就是天空/地面，
    拉出去正好接得上，看不出是补的。

    （更早的版本给 resize 传了负的左/上偏移想一步搞定，Pillow 直接拒绝：
      "box offset can't be negative"。所以改成手动铺九宫格。）
    """
    from PIL import Image
    W, H = im.size
    if factor >= 0.999:
        return im

    sw, sh = max(1, int(round(W * factor))), max(1, int(round(H * factor)))
    small = im.resize((sw, sh), Image.LANCZOS)
    ox, oy = (W - sw) // 2, (H - sh) // 2     # 四周留出的带宽
    rw, bh = W - ox - sw, H - oy - sh
    if ox <= 0 and oy <= 0:
        return small.resize((W, H), Image.LANCZOS)

    def strip(box, size):
        return small.crop(box).resize(size, Image.BILINEAR)

    out = Image.new(im.mode, (W, H))
    out.paste(small, (ox, oy))
    # 四条边
    if ox > 0:
        out.paste(strip((0, 0, 1, sh), (ox, sh)), (0, oy))
    if rw > 0:
        out.paste(strip((sw - 1, 0, sw, sh), (rw, sh)), (ox + sw, oy))
    if oy > 0:
        out.paste(strip((0, 0, sw, 1), (sw, oy)), (ox, 0))
    if bh > 0:
        out.paste(strip((0, sh - 1, sw, sh), (sw, bh)), (ox, oy + sh))
    # 四个角：各用一个角像素铺满
    for (sx, sy), (dx, dy), w, h in [
            ((0, 0), (0, 0), ox, oy),
            ((sw - 1, 0), (ox + sw, 0), rw, oy),
            ((0, sh - 1), (0, oy + sh), ox, bh),
            ((sw - 1, sh - 1), (ox + sw, oy + sh), rw, bh)]:
        if w > 0 and h > 0:
            out.paste(strip((sx, sy, sx + 1, sy + 1), (w, h)), (dx, dy))
    return out


def _max_side(code):
    return REAL_MAX_SIDE[code] if code in REAL_MAX_SIDE else DEFAULT_MAX_SIDE


# --------------------------------------------------------------------------
# 表情包：白底抠成透明 + 统一画框
# --------------------------------------------------------------------------
# 用户给的这批源图是**白底、没有 alpha 通道**（四角 254/255 纯白，白底占七成画面）。
# 直接塞进聊天就是一个白方块，所以必须把白底抠掉。
#
# ⚠ 关键：狐狸和小羊**本身就大面积是白的** —— 不能"见白就抠"，
#   那会把身体和高光一起抠漏。做法是**只吃与画面四边相连的那片白**：
#   从边框往里做连通生长（膨胀 ∩ 白底掩膜），被轮廓围住的白一律保留。
#
# 抠完再**裁到主体外框**、补成正方、四周留 STICKER_MARGIN —— 20 张摆一起大小才一致。
STICKER_SRC_DIR = os.path.join(INBOX, "stickers")
STICKER_OUT_DIR = os.path.join(ROOT, "real", "stickers")
STICKER_MAX_SIDE = 256      # 页面上最大显示约 82px，256 已够 2x 高密度屏；360 会白多一半体积
STICKER_BG_TOL = 26         # 三通道都 ≥ 255-tol 才算"白底"
STICKER_WORK = 560          # 连通生长在缩小后的这个边长上做（够快，边缘精度也够）
STICKER_MARGIN = 0.07       # 裁到主体后四周补的比例
STICKERS = {}

# key -> (中文名, 分组)。分组用来把 20 张分三段摆（表情包页）。
# 没登记的 key 会自动落到 ("<key>", "其他")，加新表情不必改代码。
STICKER_META = {
    "duo-cry-laugh":    ("叶青栩哭 · 小羊笑",     "双人"),
    "duo-sleep-alarm":  ("叶青栩睡 · 小羊叫早",   "双人"),
    "duo-panic-tea":    ("叶青栩慌 · 小羊递茶",   "双人"),
    "duo-smug-facepalm": ("叶青栩得意 · 小羊捂脸", "双人"),
    "duo-beg-ignore":   ("叶青栩求 · 小羊不理",   "双人"),
    "duo-hide-protect": ("叶青栩躲 · 小羊罩着",   "双人"),
    "duo-dance-deadpan": ("叶青栩嗨 · 小羊面无表情", "双人"),
    "duo-hungry-snack": ("叶青栩饿 · 小羊投喂",   "双人"),
    "fox-cheer":      ("叶青栩 · 欢呼",  "叶青栩"),
    "fox-confused":   ("叶青栩 · 疑惑",  "叶青栩"),
    "fox-ok":         ("叶青栩 · 没问题", "叶青栩"),
    "fox-speechless": ("叶青栩 · 无语",  "叶青栩"),
    "fox-surprised":  ("叶青栩 · 惊讶",  "叶青栩"),
    "fox-wave":       ("叶青栩 · 挥手",  "叶青栩"),
    "lamb-cheer":      ("小羊 · 欢呼",  "小羊"),
    "lamb-confused":   ("小羊 · 疑惑",  "小羊"),
    "lamb-ok":         ("小羊 · 没问题", "小羊"),
    "lamb-speechless": ("小羊 · 无语",  "小羊"),
    "lamb-surprised":  ("小羊 · 惊讶",  "小羊"),
    "lamb-wave":       ("小羊 · 挥手",  "小羊"),
    # ↓ 2026-09-19 新到的一批「配文」表情（画面底部烧了一句中文，可以直接当回话发出去）
    #   ⚠ 用户给的源文件名与画面/字幕是**错位**的（例如 01-lamb-you-continue 画面其实是
    #   「叶青栩 + 字幕 好的」）。下表是按**看图核对过的字幕**重命名的键，不要按源文件名改回来。
    "cap-okay":        ("叶青栩 · 好的",     "配文"),
    "cap-help":        ("叶青栩 · 救命",     "配文"),
    "cap-no-way":      ("小羊 · 不是吧",     "配文"),
    "cap-laugh":       ("叶青栩 · 哈哈",     "配文"),
    "cap-received":    ("叶青栩 · 收到",     "配文"),
    "cap-speechless":  ("叶青栩 · 无语",     "配文"),
    "cap-thanks":      ("小羊 · 谢谢",       "配文"),
    "cap-hard-work":   ("小羊 · 辛苦了",     "配文"),
    "cap-you-continue": ("小羊 · 你继续",    "配文"),
    "cap-no-thanks":   ("小羊 · 不约",       "配文"),
    "cap-goodnight":   ("叶青栩 · 晚安",     "配文"),
    "cap-let-me-see":  ("小羊 · 让我看看",   "配文"),
}
STICKER_GROUP_ORDER = ["双人", "叶青栩", "小羊", "配文", "其他"]


def sticker_meta(key):
    return STICKER_META.get(key) or (key, "其他")


def _cut_white_bg(im, tol=STICKER_BG_TOL, work=STICKER_WORK):
    """把**与画面四边相连**的白底抠成透明，返回 RGBA。"""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    W, H = im.size
    sc = min(1.0, float(work) / max(W, H))
    w, h = max(2, int(round(W * sc))), max(2, int(round(H * sc)))
    sm = im.convert("RGB").resize((w, h), Image.LANCZOS)

    r, g, b = sm.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)          # 每像素三通道最小值
    allow = mn.point(lambda v: 255 if v >= 255 - tol else 0)    # 够白的地方才允许生长

    seed = Image.new("L", (w, h), 0)
    ImageDraw.Draw(seed).rectangle([0, 0, w - 1, h - 1], outline=255, width=1)
    seed = ImageChops.multiply(seed, allow)                     # 种子 = 边框上的白
    for _ in range(w + h):
        grown = ImageChops.multiply(seed.filter(ImageFilter.MaxFilter(3)), allow)
        if ImageChops.difference(grown, seed).getbbox() is None:
            break
        seed = grown

    alpha = ImageChops.invert(seed)                             # 背景 0 / 主体 255
    alpha = alpha.filter(ImageFilter.MinFilter(3))              # 内缩 1px，去掉白毛边
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))         # 别是硬切边
    if (w, h) != (W, H):
        alpha = alpha.resize((W, H), Image.LANCZOS)
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out


def _sticker(im):
    """抠底 -> 裁到主体 -> 补正方 -> 缩放。返回处理好的 RGBA。"""
    from PIL import Image
    cut = _cut_white_bg(im)
    bbox = cut.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if bbox:
        span = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
        pad = int(round(span * STICKER_MARGIN))
        cut = cut.crop((bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad))
    side = max(cut.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cut, ((side - cut.size[0]) // 2, (side - cut.size[1]) // 2))
    if side > STICKER_MAX_SIDE:
        canvas = canvas.resize((STICKER_MAX_SIDE, STICKER_MAX_SIDE), Image.LANCZOS)
    return canvas


def build_stickers():
    """扫 _inbox/stickers/*.png -> real/stickers/<key>.png，填充 STICKERS。"""
    try:
        from PIL import Image
    except Exception:
        print("    ! 没装 Pillow，表情包跳过")
        return
    if not os.path.isdir(STICKER_SRC_DIR):
        return
    os.makedirs(STICKER_OUT_DIR, exist_ok=True)
    for fn in sorted(os.listdir(STICKER_SRC_DIR)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in REAL_EXTS:
            continue
        try:
            im = Image.open(os.path.join(STICKER_SRC_DIR, fn))
            _sticker(im).save(os.path.join(STICKER_OUT_DIR, stem + ".png"),
                              "PNG", optimize=True)
        except Exception as e:
            print("    ! 表情包处理失败", fn, e)
            continue
        STICKERS[stem] = "real/stickers/" + stem + ".png"
        print("  * 表情包", stem, "->", STICKERS[stem])


def _normalize(src, out_dir, base, max_side, code=None):
    """把源图处理成"可直接上线"的文件。返回 (是否成功, 输出扩展名)。

    分两种情况，判据是**素材本身带不带透明**：

    A. 透明底素材（头像 / 角色）→ 存 PNG
       - **防黑边**：这类图的透明区 RGB 常是纯黑 (0,0,0)，缩放时黑会混进轮廓
         边缘（小尺寸头像上就是一圈脏边）。做法是先让内容颜色向外"渗"一圈
         再缩放；alpha 全程不动，透明底依然是透明底。
       - **居中方形留白**：方形画布才好放进方形/圆形的位置，不会被拉变形。

    B. 不透明整幅图（星卡插画这种自带背景的）→ 存 JPEG
       - 没有透明通道，存 PNG 纯属浪费（200 万像素一张要 2MB，JPEG 只要百来 KB）。
       - **不留方形白边**：整幅铺满才是它的用法，留白反而是多余的透明框。

    Pillow 不可用时返回 (False, '')，调用方原样复制。
    """
    try:
        from PIL import Image, ImageFilter
    except Exception:
        print("    ! 没装 Pillow，改为原样复制（不做缩放与防黑边处理）：", os.path.basename(src))
        return (False, "")
    try:
        im = Image.open(src).convert("RGBA")
    except Exception as e:
        print("    ! 打开失败，改为原样复制：", src, e)
        return (False, "")

    W, H = im.size
    a = im.getchannel("A")
    total = W * H
    hist = a.histogram()
    n_transparent = hist[0]                       # 真·全透明像素
    n_opaque = hist[255]                          # 真·全不透明像素

    # —— 坏 alpha 通道识别 ——
    # 正常素材要么"背景一大片全透明"（抠好的角色图），要么"整幅全不透明"（插画）。
    # 两头都没有 = alpha 是坏数据（常见于出图/导出环节写坏），
    # 表现是整幅蒙一层白雾、且在任何非白背景上都能透出底色。
    # 判据：几乎没有全透明的（<0.5%），同时几乎没有全不透明的（<1%）→ 拍平为不透明。
    broken_alpha = n_transparent < total * 0.005 and n_opaque < total * 0.01
    if broken_alpha:
        print("    ~ 修坏 alpha：%s（全透明 %.2f%% / 全不透明 %.2f%%）→ 拍平为不透明"
              % (os.path.basename(src), n_transparent * 100.0 / total, n_opaque * 100.0 / total))
        im = Image.merge("RGBA", im.convert("RGB").split() + (Image.new("L", (W, H), 255),))
        a = im.getchannel("A")

    has_alpha = (not broken_alpha) and a.getextrema()[0] < 250

    # —— 星卡插画：先摆位（左右翻 / 缩进去留边）——
    compose = CARD_COMPOSE.get(code) or {}
    if compose and not has_alpha:
        if compose.get("mirror"):
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
            print("    > 左右翻（让它朝着另一张卡）")
        mg = float(compose.get("margin") or 1.0)
        if mg < 0.999:
            im = _edge_extend(im, mg)
            print("    > 缩小到 %.0f%% 居中，四周用背景延伸补上（给太阳/月亮留余量）" % (mg * 100))
        a = im.getchannel("A")
        W, H = im.size

    sc = 1.0 if not max_side else min(1.0, float(max_side) / max(W, H))
    tw, th = max(1, int(round(W * sc))), max(1, int(round(H * sc)))
    resized = (tw, th) != (W, H)

    if has_alpha:
        if resized:
            solid = a.point(lambda v: 255 if v > 0 else 0)
            rgb = im.convert("RGB")
            rad = max(4.0, max(W, H) / 64.0)
            rgb = Image.composite(rgb, rgb.filter(ImageFilter.GaussianBlur(rad)), solid)
            im = Image.merge("RGBA", rgb.split() + (a,)).resize((tw, th), Image.LANCZOS)
            tw, th = im.size
        side = max(tw, th)                        # 正方形透明画布居中
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(im, ((side - tw) // 2, (side - th) // 2))
        canvas.save(os.path.join(out_dir, base + ".png"), "PNG", optimize=True)
        return (True, ".png")

    rgb = im.convert("RGB")
    if resized:
        rgb = rgb.resize((tw, th), Image.LANCZOS)
    rgb.save(os.path.join(out_dir, base + ".jpg"), "JPEG",
             quality=JPEG_QUALITY, optimize=True, progressive=True)
    return (True, ".jpg")


def _copy_to_real(src, base, code=None):
    """接一张真图进 assets/real/，返回相对 assets/ 的路径。"""
    out_dir = os.path.join(ROOT, "real")
    os.makedirs(out_dir, exist_ok=True)
    ok, ext = _normalize(src, out_dir, base, _max_side(code), code)
    if not ok:
        import shutil
        ext = os.path.splitext(src)[1].lower()
        shutil.copyfile(src, os.path.join(out_dir, base + ext))
    _purge_other(out_dir, base, ext)   # 换了格式就把旧格式的残留删掉，别越积越大
    return "real/" + base + ext


def _purge_other(out_dir, base, keep_ext):
    """同一个 base 只留一个文件：输出格式变了（png<->jpg）时清掉上一次的残留。"""
    if not os.path.isdir(out_dir):
        return
    for fn in os.listdir(out_dir):
        stem, ext = os.path.splitext(fn)
        if stem == base and ext.lower() != keep_ext.lower():
            os.remove(os.path.join(out_dir, fn))
            print("    - 清掉旧格式残留", fn)


def _scan_states(base):
    """找 _inbox/ 里所有「基础名-<state>.<ext>」，返回 {state: 源文件路径}。"""
    found = {}
    if not os.path.isdir(INBOX):
        return found
    for fn in sorted(os.listdir(INBOX)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in REAL_EXTS:
            continue
        if not stem.startswith(base + "-"):
            continue
        st = stem[len(base) + 1:]
        if st and st not in found:
            found[st] = os.path.join(INBOX, fn)
    return found


def apply_real_overrides():
    """把 _inbox/ 里的成品图接进 assets/ 并改写清单路径。返回被替换的逻辑码列表。

    每个占位码支持两种文件：
        <基础名>.png            该码的兜底图（缺状态图时用它）
        <基础名>-<state>.png    按状态换图（思考一张、开心一张…）
    """
    if not os.path.isdir(INBOX):
        return []
    hit = []
    for code, base in REAL_NAMES.items():
        src = _first(base)
        if src is not None:
            PH_MAP[code] = _copy_to_real(src, base, code)   # 只改值，dict 顺序不变 -> 清单输出稳定
            hit.append(code)
            print("  * 真图", code, "->", PH_MAP[code], "(来源 _inbox/" + os.path.basename(src) + ")")

        states = _scan_states(base)
        if states:
            PH_STATES[code] = {}
            for st in sorted(states):
                PH_STATES[code][st] = _copy_to_real(states[st], base + "-" + st, code)
                print("    · 状态", code + "." + st, "->", PH_STATES[code][st])
    return hit

BG_MAP = {
    "room-living": "backgrounds/room-living.svg",
    "room-study": "backgrounds/room-study.svg",
    "room-kitchen": "backgrounds/room-kitchen.svg",
    "room-bedroom": "backgrounds/room-bedroom.svg",
    "room-bath": "backgrounds/room-bath.svg",
    "outdoor-yard": "backgrounds/outdoor-yard.svg",
    "outdoor-street": "backgrounds/outdoor-street.svg",
    "outdoor-park": "backgrounds/outdoor-park.svg",
    "scene-room": "backgrounds/scene-room.svg",
    "scene-outdoor": "backgrounds/scene-outdoor.svg",
    "earth": "backgrounds/earth.svg",
    "aiworld": "backgrounds/aiworld.svg",
}

ANIM_MAP = {
    "entry/logo-morph": "animations/entry/logo-morph.svg",
    "entry/duo-reveal": "animations/entry/duo-reveal.svg",
    "chat/typing": "animations/chat/typing.svg",
    "chat/sending": "animations/chat/sending.svg",
    "aiworld/orbit": "animations/aiworld/orbit.svg",
    "memory/sync": "animations/memory/sync.svg",
    "transitions/page-fade": "animations/transitions/page-fade.svg",
    "transitions/route-push": "animations/transitions/route-push.svg",
}

FX_MAP = {
    "glow": "effects/glow.svg",
    "ripple": "effects/ripple.svg",
    "pulse": "effects/pulse.svg",
    "shimmer": "effects/shimmer.svg",
}


# --------------------------------------------------------------------------
# 生成
# --------------------------------------------------------------------------
def main():
    print("生成 assets/ 占位素材 ->", ROOT)

    # 角色 / 插画
    w(PH_MAP["FOX_SPLASH_CHARACTER"], box_svg("叶青栩", "开屏角色"))
    w(PH_MAP["SHEEP_SPLASH_CHARACTER"], box_svg("小羊羔", "开屏角色"))
    w(PH_MAP["FOX_CHAT_AVATAR"], box_svg("叶青栩", "聊天头像"))
    w(PH_MAP["USER_AVATAR"], box_svg("用户", "用户头像"))
    w(PH_MAP["FOX_HOME_CHARACTER"], box_svg("叶青栩", "星卡图"))
    w(PH_MAP["FOX_NOTIFICATION_AVATAR"], box_svg("叶青栩", "通知头像"))
    w(PH_MAP["FOX_STATE_EMOTION"], box_svg("叶青栩", "状态表情"))
    w(PH_MAP["FOX_PIXEL_SPRITE"], box_svg("叶青栩", "像素小人"))
    w(PH_MAP["SHEEP_CHARACTER_RESERVED"], box_svg("小羊羔", "星卡图(保留)"))
    w(PH_MAP["MEMORY_EMPTY_ILLUSTRATION"], box_svg("空状态", "记忆插画"))
    w(PH_MAP["CONNECTION_SUCCESS_ILLUSTRATION"], box_svg("连接成功", "插画"))
    w(PH_MAP["OFFLINE_ILLUSTRATION"], box_svg("离线", "插画"))
    w(PH_MAP["STICKER_PACK"], box_svg("表情包", "用户上传"))

    # 背景
    for name, path in BG_MAP.items():
        w(path, bg_svg(name))

    # 动画
    w(ANIM_MAP["entry/logo-morph"], anim_logo_morph())
    w(ANIM_MAP["entry/duo-reveal"], anim_duo_reveal())
    w(ANIM_MAP["chat/typing"], anim_typing())
    w(ANIM_MAP["chat/sending"], anim_pulse_arc())
    w(ANIM_MAP["aiworld/orbit"], anim_orbit())
    w(ANIM_MAP["memory/sync"], anim_sync())
    w(ANIM_MAP["transitions/page-fade"], anim_fade())
    w(ANIM_MAP["transitions/route-push"], anim_push())

    # 特效
    w(FX_MAP["glow"], fx_glow())
    w(FX_MAP["ripple"], fx_ripple())
    w(FX_MAP["pulse"], fx_pulse())
    w(FX_MAP["shimmer"], fx_shimmer())

    # 图标
    for name in ICONS:
        w("icons/" + name + ".svg", icon_svg(name))
    w("icons/sprites.svg", sprite_svg())
    w("icons/sprite-data.js", "window.KSN_SPRITE=" + _json(sprite_svg()) + ";\n")

    # 真图覆盖：_inbox/ 里有成品图就接进来（没有则全部维持占位盒，输出不变）
    apply_real_overrides()

    # 表情包：_inbox/stickers/ 里的白底图抠成透明，落到 real/stickers/
    build_stickers()

    # 运行时清单（无需 fetch，file:// 可用）
    #   chars[code]      该码的图（有状态图时 = 兜底图）
    #   charStates[code] {state: 路径} —— 头像/角色按状态换图用；缺的 state 页面自动回落 chars[code]
    #   stickers[key]    表情包（已抠掉白底）；stickerMeta 给中文名与分组
    sticker_meta_map = {k: {"label": sticker_meta(k)[0], "group": sticker_meta(k)[1]}
                        for k in STICKERS}
    manifest_js = (
        "/* 自动生成，请勿手改。改素材请改 assets/_inbox/ 后运行 tools/gen-assets.py */\n"
        "window.KSN_ASSETS = " + _json({
            "chars": PH_MAP,
            "charStates": PH_STATES,
            "stickers": STICKERS,
            "stickerMeta": sticker_meta_map,
            "stickerGroups": STICKER_GROUP_ORDER,
            "backgrounds": BG_MAP,
            "animations": ANIM_MAP,
            "effects": FX_MAP,
            "icons": {n: "icons/" + n + ".svg" for n in ICONS},
        }) + ";\n"
    )
    w("_manifest.js", manifest_js)

    # 人类可读清单
    w("manifest.json", _json({
        "version": "20260919k",
        "note": "统一素材目录占位实现。正式素材确认后按此路径替换同名文件即可，页面结构不变。",
        "tree": {
            "characters": {
                "yeqingxu": ["avatar", "expressions", "actions", "notifications"],
                "sheep": ["avatar", "expressions", "actions"],
                "duo": ["(avatar/duo 单文件)"],
            },
            "animations": ["entry", "chat", "aiworld", "memory", "transitions"],
            "backgrounds": list(BG_MAP.keys()),
            "icons": list(ICONS.keys()),
            "effects": list(FX_MAP.keys()),
            "placeholders": ["memory-empty", "connection-success", "offline", "sticker"],
        },
        "mappings": {"chars": PH_MAP, "backgrounds": BG_MAP, "animations": ANIM_MAP, "effects": FX_MAP},
        "charStates": PH_STATES,
        "stickers": {k: {"path": v, "label": sticker_meta(k)[0], "group": sticker_meta(k)[1]}
                     for k, v in STICKERS.items()},
        "rules": [
            "动画占位一律带 prefers-reduced-motion 静态降级（关动画即静态首帧）。",
            "角色 / 插画用灰阶标签盒，不重绘正式角色。",
            "背景占位半透明，透出底层 CSS 色块。",
            "头像 / 角色按状态换图：_inbox/<基础名>-<state>.png；缺该状态自动回落 <基础名>.png。",
            "透明底素材接入时先做防黑边处理再缩放（见 tools/gen-assets.py 的 _normalize）。",
            "头像不切圆形：狐狸耳朵是尖的，切圆会吃掉耳朵和蝴蝶结。",
            "表情包源图是白底无 alpha，接入时**只抠与四边相连的白底**"
            "（见 _cut_white_bg）—— 角色身体本身就是白的，不能全局抠白。",
        ],
    }, indent=2))

    print("完成。共生成目录：", ROOT)


def _json(obj, indent=None):
    import json
    return json.dumps(obj, ensure_ascii=False, indent=indent)


if __name__ == "__main__":
    main()
