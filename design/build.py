# -*- coding: utf-8 -*-
import pathlib
SRC = pathlib.Path(__file__).parent
NAVY="#1A1F36"; PINK="#E8475B"

I = {
 "check": '<path d="M5 12.5l4.2 4.2L19 7" />',
 "pin": '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
 "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
 "truck": '<path d="M3 6.5h10.5v9H3zM13.5 10h4l3 3v2.5h-7"/><circle cx="7" cy="17" r="1.8"/><circle cx="17" cy="17" r="1.8"/>',
 "card": '<rect x="3" y="5.5" width="18" height="13" rx="2.5"/><path d="M3 10h18M7 15h4"/>',
 "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.6 5.4 3.6 8.5s-1.1 5.9-3.6 8.5c-2.5-2.6-3.6-5.4-3.6-8.5s1.1-5.9 3.6-8.5z"/>',
 "insta": '<rect x="4" y="4" width="16" height="16" rx="5"/><circle cx="12" cy="12" r="3.6"/><circle cx="16.6" cy="7.4" r=".7" fill="currentColor"/>',
 "route": '<path d="M12 3l7.5 17-7.5-4-7.5 4z"/>',
 "down": '<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>',
 "up": '<path d="M6.5 14.5l5.5-5.5 5.5 5.5"/>',
 "left": '<path d="M14.5 6l-6 6 6 6"/>',
 "shield": '<path d="M12 3.5l7 2.8v5.2c0 4.4-3 7.7-7 9-4-1.3-7-4.6-7-9V6.3z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
 "store": '<path d="M4 9.5l1.5-5h13L20 9.5M4 9.5h16M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0M5.5 12v8h13v-8M10 20v-4.5h4V20"/>',
 "alert": '<path d="M12 4l9 15.5H3z"/><path d="M12 10v4.5M12 17v.3"/>',
 "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.3-4.3"/>',
 "heart": '<path d="M12 19.5s-7.5-4.4-7.5-10A4.2 4.2 0 0 1 12 7a4.2 4.2 0 0 1 7.5 2.5c0 5.6-7.5 10-7.5 10z"/>',
 "plus": '<path d="M12 5v14M5 12h14"/>',
 "user": '<circle cx="12" cy="8.5" r="3.8" fill="currentColor" stroke="none"/><path d="M4.8 19.5c1.2-3.6 4-5.3 7.2-5.3s6 1.7 7.2 5.3z" fill="currentColor" stroke="none"/>',
 "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8v.3"/>',
 "spark": '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z"/>',
 "sliders": '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
 "clip": '<path d="M19 11.5l-7 7a4.6 4.6 0 0 1-6.5-6.5l7.5-7.5a3 3 0 0 1 4.3 4.3l-7.4 7.4a1.5 1.5 0 0 1-2.2-2.1L14.5 7.3"/>',
 "gift": '<rect x="4" y="9" width="16" height="11" rx="2"/><path d="M3 9h18M12 9v11M12 9c-1.5-3-5-4-5-1.5S10 9 12 9zm0 0c1.5-3 5-4 5-1.5S14 9 12 9z"/>',
}
def ic(n, s=18, sw=1.7, col=None):
    st = f' style="color:{col}"' if col else ""
    return f'<svg width="{s}" height="{s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{st}>{I[n]}</svg>'

# soft "3D-ish" product illustrations (no logos)
def svg_fridge(w=64):
    return f'''<svg width="{w}" height="{w*1.35}" viewBox="0 0 64 86"><defs><linearGradient id="fg" x1="0" x2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#DADDE6"/></linearGradient></defs>
<ellipse cx="32" cy="82" rx="24" ry="3" fill="#000" opacity=".08"/><rect x="10" y="2" width="44" height="78" rx="7" fill="url(#fg)" stroke="#C9CDD8" stroke-width=".8"/>
<path d="M10 30h44" stroke="#C3C7D2" stroke-width="1"/><rect x="15" y="12" width="2.6" height="12" rx="1.3" fill="#9EA3B0"/><rect x="15" y="36" width="2.6" height="20" rx="1.3" fill="#9EA3B0"/></svg>'''
def svg_fridge_sbs(w=64):
    return f'''<svg width="{w}" height="{w*1.35}" viewBox="0 0 64 86"><defs><linearGradient id="fs" x1="0" x2="1"><stop offset="0" stop-color="#E9EBF0"/><stop offset="1" stop-color="#B9BECA"/></linearGradient></defs>
<ellipse cx="32" cy="82" rx="26" ry="3" fill="#000" opacity=".08"/><rect x="6" y="2" width="52" height="78" rx="6" fill="url(#fs)" stroke="#AEB3BF" stroke-width=".8"/>
<path d="M32 2v78" stroke="#A3A8B4" stroke-width="1"/><rect x="27" y="22" width="2.4" height="26" rx="1.2" fill="#7E8492"/><rect x="34.6" y="22" width="2.4" height="26" rx="1.2" fill="#7E8492"/><rect x="38" y="10" width="13" height="9" rx="2" fill="#8D93A0" opacity=".5"/></svg>'''
def svg_phone(w=46, c1="#E9ECF5", c2="#BFC6D9"):
    return f'''<svg width="{w}" height="{w*1.9}" viewBox="0 0 46 88"><defs><linearGradient id="pg{c1[1:]}" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>
<ellipse cx="23" cy="85" rx="16" ry="2.5" fill="#000" opacity=".08"/><rect x="3" y="2" width="40" height="80" rx="8" fill="url(#pg{c1[1:]})" stroke="#A9B0C2" stroke-width=".8"/>
<rect x="8" y="7" width="13" height="22" rx="5" fill="#fff" opacity=".55"/><circle cx="14.5" cy="13" r="3.3" fill="#3A3F52"/><circle cx="14.5" cy="22.5" r="3.3" fill="#3A3F52"/></svg>'''
def svg_laptop(w=74):
    return f'''<svg width="{w}" height="{w*.7}" viewBox="0 0 74 52"><defs><linearGradient id="lg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="#5B5F8A"/><stop offset="1" stop-color="#2B2E4A"/></linearGradient></defs>
<rect x="11" y="3" width="52" height="34" rx="3" fill="#C9CCD6"/><rect x="13.5" y="5.5" width="47" height="29" rx="1.5" fill="url(#lg)"/><path d="M3 39h68l-4 6H7z" fill="#D9DCE4" stroke="#B8BCC8" stroke-width=".6"/></svg>'''

CSS = f"""
@font-face {{ font-family: 'Vazirmatn'; src: url('fonts/Vazirmatn-var.woff2') format('woff2'); font-weight: 100 900; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 390px; height: 844px; overflow: hidden; }}
body {{ font-family: 'Vazirmatn', sans-serif; direction: rtl; color: {NAVY}; font-size: 14px; line-height: 1.75; -webkit-font-smoothing: antialiased;
  background:
   radial-gradient(260px 220px at 82% 30%, rgba(255,218,228,.55), transparent 70%),
   radial-gradient(280px 260px at 12% 42%, rgba(214,222,255,.55), transparent 70%),
   radial-gradient(300px 260px at 75% 88%, rgba(234,224,255,.45), transparent 70%),
   radial-gradient(240px 200px at 10% 8%, rgba(225,236,255,.5), transparent 70%),
   #FCFCFE; }}
.app {{ position: relative; width: 390px; height: 844px; display:flex; flex-direction:column; }}
.status {{ height: 50px; display:flex; align-items:center; justify-content:space-between; padding: 8px 28px 0 30px; font-weight: 700; font-size: 15.5px; flex-shrink:0; direction:ltr; }}
.status .sys {{ display:flex; gap:6px; align-items:center; }}
.bat {{ width: 25px; height: 12px; border: 1.4px solid {NAVY}; border-radius: 4px; padding: 1.5px; opacity:.9 }} .bat i {{ display:block; height:100%; width:80%; background:{NAVY}; border-radius:1.5px; }}
.bars {{ display:flex; gap:2px; align-items:flex-end; height: 11px; }} .bars i {{ width:3px; background:{NAVY}; border-radius:1px; display:block; }}
.top {{ height: 62px; position: relative; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
.top .logo {{ position:absolute; left: 20px; top: 13px; width: 34px; height: 34px; }}
.top .rbtn {{ position:absolute; right: 20px; top: 12px; }}
.seg {{ display:flex; background: rgba(238,239,245,.85); border-radius: 22px; padding: 4px; width: 168px; height: 42px; box-shadow: inset 0 0 0 1px rgba(225,227,236,.7); }}
.seg span {{ flex:1; display:flex; align-items:center; justify-content:center; border-radius: 18px; font-size: 14.5px; color:#9A9DAC; font-weight: 500; }}
.seg span.on {{ background: linear-gradient(180deg,#FFFFFF, #FFF5F6); color:{NAVY}; font-weight: 800; box-shadow: 0 4px 14px rgba(232,120,140,.14), 0 1px 2px rgba(30,30,60,.06); }}
.scroll {{ flex:1; overflow:hidden; padding: 6px 18px 0; position:relative; }}
.fade {{ position:absolute; left:0; right:0; bottom:0; height: 36px; background: linear-gradient(rgba(252,252,254,0), rgba(252,252,254,.95)); }}
.composer {{ flex-shrink:0; padding: 8px 16px 30px; }}
.glass {{ background: rgba(255,255,255,.78); backdrop-filter: blur(14px); border: 1px solid rgba(228,230,240,.9); box-shadow: 0 12px 34px rgba(110,110,170,.12), 0 1px 2px rgba(30,30,60,.04); }}
.cbox {{ height: 58px; border-radius: 29px; display:flex; align-items:center; padding: 0 20px 0 9px; gap: 10px; }}
.cbox .ph {{ flex:1; color:#A6A9B7; font-size: 14px; }}
.round {{ width: 42px; height: 42px; border-radius: 50%; background:#fff; display:flex; align-items:center; justify-content:center; box-shadow: 0 4px 12px rgba(40,40,90,.08); color:{NAVY}; flex-shrink:0; }}
.homebar {{ position:absolute; bottom: 8px; left:50%; transform:translateX(-50%); width: 134px; height: 5px; border-radius: 3px; background:{NAVY}; }}
.urow {{ display:flex; gap: 10px; align-items:flex-start; margin: 4px 0 16px; }}
.uav {{ width: 36px; height: 36px; border-radius: 50%; background: #E9ECF8; color:#5E6683; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
.ububble {{ background: #EDF0FD; border-radius: 22px; padding: 11px 16px; font-size: 14.5px; line-height: 1.95; max-width: 78%; color:{NAVY}; }}
.arow {{ display:flex; gap: 10px; align-items:flex-start; justify-content:flex-end; margin-bottom: 14px; }}
.acol {{ display:flex; flex-direction:column; align-items:flex-start; max-width: 80%; }}
.abubble {{ background: #F4F5F8; border-radius: 22px; padding: 11px 16px; font-size: 14.5px; line-height: 1.95; color:{NAVY}; }}
.aav {{ width: 44px; height: 44px; border-radius: 50%; flex-shrink:0; position:relative; margin-top: 2px; }}
.aav::before {{ content:''; position:absolute; inset:-8px; border-radius:50%; background: radial-gradient(circle, rgba(255,200,215,.6), transparent 70%); }}
.aav img {{ position:relative; width:44px; height:44px; border-radius:50%; box-shadow: 0 4px 12px rgba(150,120,160,.18); background:#fff; }}
.pill {{ display:inline-flex; align-items:center; gap: 6px; border-radius: 16px; padding: 4px 8px 4px 12px; font-size: 12px; color:#5B6072; margin-bottom: 8px; background: rgba(255,255,255,.85); border:1px solid #ECEDF3; box-shadow: 0 2px 8px rgba(60,60,110,.05); }}
.pill .ok {{ width: 17px; height: 17px; border-radius: 50%; background:#E6F6EC; color:#24985A; display:flex; align-items:center; justify-content:center; }}
.pill .chev {{ color:#A0A3B1; display:flex; }}
.card {{ background:#fff; border-radius: 26px; box-shadow: 0 10px 34px rgba(40,44,90,.07), 0 1px 3px rgba(40,44,90,.03); border: 1px solid rgba(236,237,243,.8); }}
.pcard {{ display:flex; gap: 12px; padding: 14px 14px 10px 14px; margin-bottom: 14px; }}
.pcard .col {{ flex:1; min-width:0; }}
.ph {{ }}
.tile {{ width: 112px; height: 134px; border-radius: 20px; background:#F4F5F7; flex-shrink:0; overflow:hidden; display:flex; align-items:center; justify-content:center; align-self:flex-start; }}
.tile img {{ width:100%; height:100%; object-fit: cover; }}
.hrow {{ display:flex; gap: 8px; align-items:flex-start; }}
.ttl {{ font-size: 14.5px; font-weight: 800; line-height: 1.6; color:{NAVY}; }}
.mdl {{ font-size: 15px; font-weight: 700; line-height: 1.5; color:{NAVY}; letter-spacing: .1px; }}
.heart {{ width: 34px; height: 34px; border-radius: 50%; background:#FFF0F2; color:{PINK}; display:flex; align-items:center; justify-content:center; flex-shrink:0; margin-right:auto; }}
.prange {{ font-size: 12.5px; color:#4E5368; margin-top: 7px; font-weight: 500; }}
.prange b {{ font-weight: 700; color:{NAVY}; font-size: 13px; }}
.fresh {{ font-size: 10.5px; color:#A3A6B4; display:flex; align-items:center; gap: 4px; margin-top: 1px; }}
.rows {{ margin-top: 6px; }}
.row {{ display:flex; align-items:center; gap: 8px; height: 33px; border-top: 1px solid #F0F1F5; font-size: 12.5px; color:#5B6072; }}
.row .t {{ flex:1; white-space: nowrap; overflow:hidden; text-overflow: ellipsis; }}
.row .ic {{ color:#7C8194; display:flex; }}
.row .chev {{ color:#B3B6C3; display:flex; }}
.chips {{ display:flex; gap: 8px; flex-wrap: wrap; }}
.chip {{ background: rgba(255,255,255,.9); border: 1px solid #E8E9F0; border-radius: 999px; padding: 6px 14px; font-size: 13px; color:#3B4055; display:inline-flex; align-items:center; gap: 6px; white-space:nowrap; box-shadow: 0 2px 8px rgba(60,60,110,.04); }}
.chip.on {{ background: linear-gradient(180deg,#FFFFFF,#FFF2F4); border-color: #F7CDD4; color: #C93A50; font-weight: 700; }}
.badge {{ display:inline-flex; align-items:center; gap: 4px; font-size: 11.5px; font-weight: 600; padding: 3px 9px; border-radius: 10px; white-space:nowrap; }}
.b-green {{ background:#EAF7EF; color:#1F8A50; }} .b-pink {{ background:#FFF0F2; color:#C93A50; }} .b-lav {{ background:#EFF0FD; color:#4B54A8; }} .b-gray {{ background:#F3F4F7; color:#5B6072; }} .b-amber {{ background:#FFF5E5; color:#A2620B; }}
.btn {{ height: 40px; border-radius: 20px; display:flex; align-items:center; justify-content:center; gap: 6px; font-size: 13px; font-weight: 700; }}
.btn-navy {{ background: {NAVY}; color:#fff; box-shadow: 0 6px 16px rgba(26,31,54,.22); }}
.btn-soft {{ background:#F4F5F8; color:{NAVY}; }}
.sec {{ font-size: 12.5px; color:#8C90A0; font-weight: 600; margin: 2px 4px 10px; }}
.muted {{ color:#8C90A0; }}
"""
def status():
    return f'''<div class="status"><span>۹:۴۱</span><div class="sys"><div class="bars"><i style="height:4px"></i><i style="height:6px"></i><i style="height:8px"></i><i style="height:11px"></i></div>
<svg width="16" height="12" viewBox="0 0 16 12"><path d="M8 11.5l2.2-2.6a3.4 3.4 0 0 0-4.4 0zM3.4 6.6a7 7 0 0 1 9.2 0l1.4-1.6a9.2 9.2 0 0 0-12 0zM.6 3.4a11.3 11.3 0 0 1 14.8 0" fill="{NAVY}" stroke="{NAVY}" stroke-width=".4"/></svg><div class="bat"><i></i></div></div></div>'''
def top(active="chat", logo=True, right=""):
    a = ('on','') if active=="chat" else ('','on')
    lg = '<img class="logo" src="assets/logo.png">' if logo else ''
    return f'<div class="top">{lg}{right}<div class="seg"><span class="{a[0]}">چت</span><span class="{a[1]}">نقشه</span></div></div>'
def composer(ph="هر سؤالی دربارهٔ خرید داری بپرس…"):
    return f'<div class="composer"><div class="cbox glass"><div class="ph">{ph}</div><div class="round">{ic("plus",20,1.9)}</div></div></div>'
def user(t): return f'<div class="urow"><div class="uav">{ic("user",20)}</div><div class="ububble">{t}</div></div>'
def asst(t, pill=""):
    mt = ' style="margin-top:40px"' if pill else ''
    return f'<div class="arow"><div class="acol">{pill}<div class="abubble">{t}</div></div><div class="aav"{mt}><img src="assets/mascot_avatar.png"></div></div>'
def steps_pill(t="۴ مرحله انجام شد", warn=False):
    ok = f'<span class="ok" style="background:#FFF4E2;color:#B06A0C">{ic("alert",11,2.3)}</span>' if warn else f'<span class="ok">{ic("check",11,2.6)}</span>'
    return f'<div class="pill">{ok}{t}<span class="chev">{ic("down",14,2)}</span></div>'
def pcard(title, model, lo, hi, tile, rows, fresh="آخرین تغییر قیمت: ۲ روز پیش", extra="", tilebg="#F4F5F7"):
    rs = "".join(f'<div class="row"><span class="ic">{ic(i,16)}</span><span class="t">{t}</span><span class="chev">{ic("left",14,2)}</span></div>' for i,t in rows)
    return f'''<div class="card pcard"><div class="col">
<div class="hrow"><div><div class="ttl">{title}</div><div class="mdl"><span dir="ltr">{model}</span></div></div><div class="heart">{ic("heart",17,1.8)}</div></div>
<div class="prange"><b>{lo}</b> تا <b>{hi}</b> تومان</div><div class="fresh">{ic("clock",11)} {fresh}</div>{extra}
<div class="rows">{rs}</div></div><div class="tile" style="background:{tilebg}">{tile}</div></div>'''
def page(name, body, comp=True, topbar=None, ph=None, raw_after=""):
    tb = topbar if topbar is not None else top()
    c = (composer(ph) if ph else composer()) if comp else ""
    html = f'''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="app">{status()}{tb}
<div class="scroll">{body}<div class="fade"></div></div>{c}{raw_after}<div class="homebar"></div></div></body></html>'''
    (SRC/f"{name}.html").write_text(html, encoding="utf-8")

IMG = lambda f: f'<img src="assets/{f}">'

# ---------- 1 HOME ----------
def sug(icon, t1, t2):
    return f'''<div class="card" style="display:flex;align-items:center;gap:9px;padding:9px 9px 9px 8px;border-radius:22px">
<div style="width:46px;height:46px;border-radius:14px;overflow:hidden;flex-shrink:0">{icon}</div>
<div style="flex:1;font-size:12.5px;font-weight:700;line-height:1.75;color:{NAVY};white-space:nowrap">{t1}<br><span style="font-weight:500;color:#5B6072">{t2}</span></div>
<span style="width:22px;height:22px;border-radius:50%;background:#F3F4F8;color:#8C90A0;display:flex;align-items:center;justify-content:center;flex-shrink:0">{ic("left",12,2.2)}</span></div>'''
def svgtile(inner, bg, sz=46): return f'<div style="width:{sz}px;height:{sz}px;background:{bg};display:flex;align-items:center;justify-content:center">{inner}</div>'
home = f'''
<div style="text-align:center;position:relative;margin-top:8px">
 <div style="position:absolute;left:50%;top:40px;transform:translateX(-50%);width:300px;height:200px;border-radius:50%;background:radial-gradient(closest-side, rgba(255,214,226,.55), rgba(226,226,255,.35) 60%, transparent);"></div>
 <img src="assets/mascot_hero.png" style="position:relative;width:196px;height:196px;display:block;margin:0 auto">
 <div style="position:relative;width:170px;height:14px;margin:-12px auto 0;border-radius:50%;background:radial-gradient(closest-side, rgba(120,110,170,.16), transparent)"></div>
</div>
<div style="text-align:center;margin-top:14px">
 <div style="font-size:24px;font-weight:900;color:{NAVY};letter-spacing:-.2px">امروز دنبال چی می‌گردی؟</div>
 <div style="font-size:14px;color:#8C90A0;margin-top:6px">با هوش مصنوعی ترب، راحت‌تر و هوشمندتر خرید کن.</div>
</div>
<div class="glass" style="margin:24px 0 20px;border-radius:34px;padding:7px;background:rgba(255,255,255,.6);box-shadow:0 18px 44px rgba(130,120,220,.16)">
 <div style="background:#fff;border-radius:28px;height:58px;display:flex;align-items:center;padding:0 18px 0 8px;gap:10px;box-shadow:0 2px 8px rgba(40,40,90,.05)">
  <div style="flex:1;color:#A6A9B7;font-size:14.5px">هر چیزی برای خرید می‌خوای بنویس…</div>
  <div style="width:1px;height:26px;background:#ECEDF3"></div>
  <div class="round" style="width:42px;height:42px">{ic("plus",21,1.9)}</div></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
 {sug(IMG("ic_phone_in.png").replace("<img","<img style='width:46px;height:46px'"),"گوشی عکاسی","تا ۲۰ میلیون")}
 {sug(IMG("ic_headphone_in.png").replace("<img","<img style='width:46px;height:46px'"),"هدفون بی‌سیم","تا ۳ میلیون")}
 {sug(IMG("ic_pin_in.png").replace("<img","<img style='width:46px;height:46px'"),"فروشگاه‌های","نزدیک ونک")}
 {sug(IMG("ic_laptop_in.png").replace("<img","<img style='width:46px;height:46px'"),"لپ‌تاپ سبک","برای دانشجو")}
 {sug(svgtile(svg_fridge(26),"#F1F6F4"),"یخچال قسطی","با گارانتی")}
 {sug(svgtile(ic("spark",24,1.6,"#8B6FD6"),"#F4F0FD"),"نمی‌دونم","چی بخرم!")}
</div>
'''
page("01-home", home, comp=False, topbar=top(logo=False))

# ---------- 2 CHAT ----------
chat = f'''
{user("یه هدفون بی‌سیم خوب می‌خوام که نزدیک ونک بتونم تهیه کنم.")}
{asst("چند گزینهٔ مناسب با فروشنده در نزدیکی ونک برات پیدا کردم:", steps_pill())}
{pcard("هدفون بی‌سیم سونی","WH-1000XM5","۱۸٬۹۰۰٬۰۰۰","۲۲٬۵۰۰٬۰۰۰",IMG("headphone.png"),[("pin","ونک، مجتمع نور تهران"),("store","۳ فروشنده در نزدیکی ونک")])}
{pcard("هدفون بی‌سیم اپل","AirPods Pro 2","۱۳٬۷۰۰٬۰۰۰","۱۶٬۸۰۰٬۰۰۰",IMG("airpods.png"),[("pin","ونک، مرکز خرید سام سنتر"),("store","۴ فروشنده در نزدیکی ونک")],fresh="آخرین تغییر قیمت: امروز")}
'''
page("02-chat", chat)

# ---------- 3 AGENT STEPS ----------
def tstep(state, title, sub, last=False):
    if state=="done":
        dot = f'<span style="width:24px;height:24px;border-radius:50%;background:#E6F6EC;color:#24985A;display:flex;align-items:center;justify-content:center">{ic("check",13,2.6)}</span>'
        tc = NAVY; sc="#8C90A0"
    elif state=="run":
        dot = f'''<span style="width:24px;height:24px;border-radius:50%;background:conic-gradient(from 40deg, #F06A84, #B79BFF, #8FB2FF, rgba(143,178,255,0) 75%);display:flex;align-items:center;justify-content:center;box-shadow:0 0 0 6px rgba(240,106,132,.10)"><span style="width:16px;height:16px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center"><span style="width:7px;height:7px;border-radius:50%;background:#E8475B"></span></span></span>'''
        tc = NAVY; sc="#8C90A0"
    else:
        dot = '<span style="display:block;width:24px;height:24px;border-radius:50%;border:1.6px dashed #D4D6E0;background:#fff"></span>'
        tc = "#A6A9B7"; sc="#C2C4CE"
    line = "" if last else f'<span style="position:absolute;right:11.5px;top:30px;bottom:-6px;width:1.5px;background:{"#D9EFE2" if state=="done" else "#ECEDF3"}"></span>'
    shimmer = ""
    if state=="run":
        title = f'<span style="background:linear-gradient(90deg,{NAVY} 0%,{NAVY} 30%,#C9B6FF 50%,{NAVY} 70%,{NAVY} 100%);-webkit-background-clip:text;background-clip:text;color:transparent">{title}</span>'
        shimmer = '<div style="margin-top:8px;height:6px;border-radius:4px;background:#F1F2F7;overflow:hidden;width:92%"><div style="height:100%;width:62%;border-radius:4px;background:linear-gradient(90deg,#F7B7C4,#C7B5FF,#A9C3FF)"></div></div>'
    return f'''<div style="position:relative;display:flex;gap:12px;padding-bottom:16px">{line}<div style="flex-shrink:0;position:relative;z-index:1">{dot}</div>
<div style="flex:1;margin-top:1px"><div style="font-size:14px;font-weight:700;color:{tc};line-height:1.6">{title}</div><div style="font-size:12px;color:{sc};line-height:1.7">{sub}</div>{shimmer}</div></div>'''
def skel():
    sh = "background:linear-gradient(90deg,#F2F3F7 0%,#F2F3F7 35%,#FBFBFD 50%,#F2F3F7 65%,#F2F3F7 100%)"
    return f'''<div class="card" style="display:flex;gap:12px;padding:14px;border-radius:26px;margin-bottom:12px;opacity:.9">
<div style="flex:1"><div style="height:13px;width:70%;border-radius:7px;{sh}"></div><div style="height:13px;width:45%;border-radius:7px;margin-top:9px;{sh}"></div>
<div style="height:11px;width:80%;border-radius:7px;margin-top:18px;{sh}"></div><div style="height:1px;background:#F0F1F5;margin:16px 0 12px"></div><div style="height:11px;width:60%;border-radius:7px;{sh}"></div></div>
<div style="width:96px;height:104px;border-radius:18px;{sh}"></div></div>'''
steps = f'''
{user("یه لپ‌تاپ سبک برای دانشگاه می‌خوام، تا ۴۰ میلیون، نزدیک ونک.")}
<div class="arow" style="margin-bottom:12px"><div class="acol" style="max-width:84%;width:84%">
 <div class="card" style="padding:14px 16px 2px;border-radius:26px;width:100%">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px">
   <div style="font-size:14px;font-weight:800">دارم برات می‌گردم…</div>
   <div style="display:flex;align-items:center;gap:4px;font-size:12px;color:#8C90A0">۳ از ۵ {ic("up",14,2)}</div></div>
  {tstep("done","فهمیدن درخواست","لپ‌تاپ · سبک · تا ۴۰ میلیون · نزدیک ونک")}
  {tstep("done","جستجو بین محصولات","۳۱۲ لپ‌تاپ پیدا شد")}
  {tstep("done","فیلتر وزن و بودجه","۴۷ مدل زیر ۱٫۵ کیلو و تا ۴۰ میلیون")}
  {tstep("run","پیدا کردن فروشنده‌های نزدیک ونک","بررسی ۱۲۸ پیشنهاد از ۳۴ فروشگاه…")}
  {tstep("todo","مرتب‌سازی و انتخاب بهترین‌ها","بر اساس قیمت و فاصله", last=True)}
 </div></div><div class="aav"><img src="assets/mascot_avatar.png"></div></div>
{skel()}
'''
page("03-agent-steps", steps)

# ---------- 4 MAP ----------
def mpin(x, y, label=None, big=False):
    s = 44 if big else 34
    lab = f'<div style="position:absolute;bottom:{s+10}px;left:50%;transform:translateX(-50%);white-space:nowrap;background:#fff;border-radius:14px;padding:4px 10px;font-size:12px;font-weight:700;box-shadow:0 6px 18px rgba(40,40,90,.14);color:{NAVY}">{label}</div>' if label else ""
    return f'''<div style="position:absolute;left:{x}px;top:{y}px;transform:translate(-50%,-100%)">{lab}
<svg width="{s}" height="{s*1.2}" viewBox="0 0 40 48"><defs><linearGradient id="pp{x}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF7A8C"/><stop offset="1" stop-color="#E23E55"/></linearGradient></defs>
<ellipse cx="20" cy="46" rx="7" ry="2" fill="#000" opacity=".15"/><path d="M20 45C9 33 4 27 4 18a16 16 0 0 1 32 0c0 9-5 15-16 27z" fill="url(#pp{x})"/><circle cx="20" cy="18" r="9" fill="#fff"/>
<g transform="translate(13.5,11.5) scale(.54)" stroke="#E23E55" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">{I["store"]}</g></svg></div>'''
mapsvg = f'''<svg width="390" height="844" viewBox="0 0 390 844" style="position:absolute;inset:0">
<rect width="390" height="844" fill="#F4F3F8"/>
<g fill="#ECEAF3">{''.join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>' for x,y,w,h in [(14,120,120,90),(150,110,96,70),(262,96,120,110),(20,236,90,120),(128,210,130,96),(278,226,104,80),(30,380,110,90),(160,330,90,110),(270,330,110,100),(10,500,130,90),(170,470,100,80),(290,460,90,90)])}</g>
<path d="M-10 300 C 120 280, 260 330, 400 300" stroke="#DCE6FB" stroke-width="20" fill="none"/>
<path d="M-10 300 C 120 280, 260 330, 400 300" stroke="#CFDDFB" stroke-width="2" fill="none" opacity=".6"/>
<g stroke="#FFFFFF" stroke-width="12" fill="none" stroke-linecap="round"><path d="M0 220 L390 196"/><path d="M0 460 L390 440"/><path d="M142 60 L160 640"/><path d="M262 60 L276 640"/><path d="M0 610 L390 590"/></g>
<rect x="290" y="236" width="80" height="60" rx="14" fill="#E3F1E6"/><rect x="24" y="390" width="96" height="62" rx="16" fill="#E3F1E6"/>
<text x="200" y="190" font-family="Vazirmatn" font-size="10" fill="#B6B9C8" text-anchor="middle">بزرگراه مدرس</text>
<text x="72" y="425" font-family="Vazirmatn" font-size="10" fill="#9DC0A6" text-anchor="middle">پارک ملت</text>
<path d="M190 392 C 205 360, 235 335, 266 318" stroke="#E8475B" stroke-width="3" stroke-dasharray="2 7" stroke-linecap="round" fill="none"/>
<circle cx="188" cy="398" r="26" fill="#6E8BFF" opacity=".14"/><circle cx="188" cy="398" r="8.5" fill="#5B79F5" stroke="#fff" stroke-width="3.5"/>
</svg>'''
mapbody = f'''<div style="position:absolute;inset:0">{mapsvg}
{mpin(268,318,"پارسیان · ۱٫۲ کیلومتر",True)}{mpin(72,300)}{mpin(340,410)}{mpin(96,428)}
<div style="position:absolute;left:188px;top:412px;transform:translateX(-50%);font-size:11px;font-weight:700;color:#4B5DD0;background:rgba(255,255,255,.9);padding:1px 8px;border-radius:10px">شما</div>
</div>'''
def shopcard(name, addr, dist, hours, fast, pays, inst=True, first=True):
    fb = f'<span class="badge b-pink">{ic("truck",13)} ارسال سریع</span>' if fast else ""
    ib = f'<span class="badge b-lav">{ic("card",13)} قسطی</span>' if inst else ""
    return f'''<div class="card" style="padding:14px;border-radius:24px;margin-bottom:12px;box-shadow:0 6px 22px rgba(40,44,90,.06)">
<div style="display:flex;gap:12px;align-items:center">
 <div style="width:48px;height:48px;border-radius:16px;background:#FFF1F3;color:#E23E55;display:flex;align-items:center;justify-content:center;flex-shrink:0">{ic("store",22,1.7)}</div>
 <div style="flex:1;min-width:0"><div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:15px;font-weight:800">{name}</b><span style="font-size:13px;font-weight:800;color:{NAVY}">{dist}</span></div>
 <div class="muted" style="font-size:12px">{addr}</div></div></div>
<div style="display:flex;gap:6px;margin:11px 0 8px;flex-wrap:wrap"><span class="badge b-green">{ic("clock",12)} {hours}</span>{fb}{ib}</div>
<div style="display:flex;align-items:center;gap:6px;font-size:12px;color:#5B6072;margin-bottom:12px">{ic("card",14,1.7,"#7C8194")} پرداخت: {pays}</div>
<div style="display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:8px"><div class="btn btn-navy">{ic("route",15,1.8)} مسیریابی</div><div class="btn btn-soft">{ic("globe",15)} وب‌سایت</div><div class="btn btn-soft">{ic("insta",15)} اینستاگرام</div></div></div>'''
sheet = f'''<div style="position:absolute;left:0;right:0;bottom:0;height:400px;background:rgba(255,255,255,.96);backdrop-filter:blur(16px);border-radius:30px 30px 0 0;box-shadow:0 -10px 40px rgba(40,44,90,.12);padding:10px 16px 0">
<div style="width:40px;height:5px;border-radius:3px;background:#DCDDE5;margin:0 auto 12px"></div>
<div style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:12px;padding:0 4px"><div><div style="font-size:17px;font-weight:900">۸ فروشگاه لپ‌تاپ نزدیک تو</div><div class="muted" style="font-size:12px">مرتب‌شده بر اساس فاصله از ونک</div></div><span class="chip" style="padding:4px 10px;font-size:12px">{ic("sliders",14)} فیلتر</span></div>
{shopcard("فروشگاه لپ‌تاپ پارسیان","ملاصدرا، نبش شیخ بهایی","۱٫۲ کیلومتر","باز است تا ۲۱:۰۰",True,"کارت‌خوان، آنلاین، اقساطی")}
{shopcard("رایان‌سیستم ونک","ونک، خیابان گاندی، مجتمع نگین","۲٫۴ کیلومتر","باز است تا ۲۰:۳۰",False,"کارت‌خوان، آنلاین",inst=False)}
</div>'''
search = f'''<div style="position:absolute;top:118px;left:16px;right:16px">
<div class="glass" style="height:50px;border-radius:25px;display:flex;align-items:center;gap:10px;padding:0 16px;font-size:14px;color:{NAVY}">{ic("search",18,1.8,"#8C90A0")}<span style="flex:1">لپ‌تاپ · نزدیک ونک</span><span class="muted" style="font-size:12px">۸ نتیجه</span></div>
<div class="chips" style="margin-top:10px;flex-wrap:nowrap"><span class="chip on">{ic("clock",13)} الان باز</span><span class="chip">{ic("truck",13)} ارسال سریع</span><span class="chip">{ic("card",13)} قسطی</span></div></div>'''
html = f'''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="app">{mapbody}
<div style="position:relative;z-index:2">{status()}{top("map")}</div>{search}{sheet}<div class="homebar"></div></div></body></html>'''
(SRC/"04-map.html").write_text(html, encoding="utf-8")

# ---------- 5 PRODUCT DETAIL SHEET ----------
def offer(seller, price, warranty, dist, fresh, badges="", stale=False):
    warn = f'''<div style="margin-top:10px;background:#FFF8EC;border-radius:16px;padding:9px 12px;font-size:12px;line-height:1.85;color:#8E5A10;display:flex;gap:8px;align-items:flex-start">
<span style="flex-shrink:0;margin-top:3px">{ic("alert",15,1.9)}</span><div>این قیمت ۴۵ روز پیش ثبت شده؛ قبل از رفتن، قیمت رو تو وب‌سایت یا اینستاگرام فروشگاه چک کن.
<div style="display:flex;gap:6px;margin-top:6px"><span class="badge" style="background:#fff;color:#8E5A10;border:1px solid #F3DDB5">{ic("globe",12)} وب‌سایت</span><span class="badge" style="background:#fff;color:#8E5A10;border:1px solid #F3DDB5">{ic("insta",12)} اینستاگرام</span></div></div></div>''' if stale else ""
    fc = "#B07418" if stale else "#A3A6B4"
    return f'''<div style="padding:12px 2px;border-top:1px solid #F0F1F5">
<div style="display:flex;justify-content:space-between;align-items:center"><div style="display:flex;align-items:center;gap:6px"><b style="font-size:14.5px;font-weight:800">{seller}</b>{badges}</div><span style="font-size:15px;font-weight:800">{price} <span style="font-size:11px;font-weight:500;color:#8C90A0">تومان</span></span></div>
<div style="display:flex;gap:12px;font-size:12px;color:#5B6072;margin-top:3px"><span style="display:flex;align-items:center;gap:4px">{ic("shield",14,1.7,"#7C8194")} {warranty}</span><span style="display:flex;align-items:center;gap:4px">{ic("pin",14,1.7,"#7C8194")} {dist}</span></div>
<div class="fresh" style="color:{fc};margin-top:3px">{ic("clock",11)} آخرین تغییر قیمت: {fresh}</div>{warn}</div>'''
bg = f'''<div style="filter:blur(1.5px);opacity:.9">{user("یه هدفون بی‌سیم خوب می‌خوام که نزدیک ونک بتونم تهیه کنم.")}{asst("چند گزینهٔ مناسب با فروشنده در نزدیکی ونک برات پیدا کردم:")}</div>'''
dsheet = f'''<div style="position:absolute;inset:0;background:rgba(26,31,54,.28)"></div>
<div style="position:absolute;left:0;right:0;bottom:0;top:150px;background:#fff;border-radius:30px 30px 0 0;padding:10px 18px 0;box-shadow:0 -10px 40px rgba(40,44,90,.15)">
<div style="width:40px;height:5px;border-radius:3px;background:#DCDDE5;margin:0 auto 14px"></div>
<div style="display:flex;gap:14px;align-items:center">
 <div class="tile" style="width:92px;height:106px;border-radius:20px">{IMG("headphone.png")}</div>
 <div style="flex:1"><div class="hrow"><div><div class="ttl" style="font-size:15.5px">هدفون بی‌سیم سونی</div><div class="mdl" style="font-size:16px"><span dir="ltr">WH-1000XM5</span></div></div><div class="heart">{ic("heart",17,1.8)}</div></div>
 <div class="prange"><b>۱۸٬۹۰۰٬۰۰۰</b> تا <b>۲۲٬۵۰۰٬۰۰۰</b> تومان</div>
 <div style="display:flex;gap:6px;margin-top:5px"><span class="badge b-gray">{ic("store",12)} ۶ فروشنده</span><span class="badge b-gray">روگوشی · نویزگیر</span></div></div></div>
<div style="display:flex;justify-content:space-between;align-items:center;margin:16px 0 6px">
 <div class="seg" style="width:auto;height:38px"><span class="on" style="padding:0 14px;font-size:13px">ارزان‌ترین</span><span style="padding:0 12px;font-size:13px">نزدیک‌ترین</span><span style="padding:0 12px;font-size:13px">قسطی</span></div>
 <span class="muted" style="font-size:12px">۶ پیشنهاد</span></div>
{offer("صوتی‌تصویری آوا","۱۸٬۹۰۰٬۰۰۰","گارانتی ۱۸ ماهه","۳٫۸ کیلومتر","۴۵ روز پیش",stale=True)}
{offer("هدفون‌شاپ ونک","۱۹٬۶۵۰٬۰۰۰","گارانتی ۱۸ ماهه","۰٫۹ کیلومتر","۲ روز پیش",f'<span class="badge b-pink" style="font-size:10.5px">{ic("truck",11)} ارسال سریع</span>')}
{offer("دیجی‌صدا","۲۰٬۱۰۰٬۰۰۰","گارانتی ۱۲ ماهه","۱٫۶ کیلومتر","امروز",f'<span class="badge b-lav" style="font-size:10.5px">قسطی</span>')}
{offer("گجت‌سنتر ملاصدرا","۲۰٬۸۰۰٬۰۰۰","گارانتی ۱۸ ماهه","۱٫۱ کیلومتر","۳ روز پیش")}
</div>'''
html = f'''<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>{CSS}</style></head><body><div class="app">{status()}{top()}
<div class="scroll">{bg}</div>{dsheet}<div class="homebar"></div></div></body></html>'''
(SRC/"05-offers-sheet.html").write_text(html, encoding="utf-8")

# ---------- 6 COMPARE ----------
def crow(label, a, b, win=None, same=False):
    def v2(x, w):
        if same: return f'<div style="flex:1;text-align:center;font-size:12.5px;color:#9A9DAC">{x}</div>'
        if w: return f'<div style="flex:1;display:flex;justify-content:center"><span style="background:#EFF0FD;color:#3E479B;border-radius:11px;padding:2px 9px;font-size:12.5px;font-weight:700;display:inline-flex;align-items:center;gap:4px;white-space:nowrap">{ic("check",11,2.6)} {x}</span></div>'
        return f'<div style="flex:1;text-align:center;font-size:12.5px;color:{NAVY};white-space:nowrap">{x}</div>'
    return f'''<div style="display:flex;align-items:center;height:38px;border-top:1px solid #F0F1F5">{v2(a, win=="a")}<div style="width:78px;text-align:center;font-size:11px;color:#9A9DAC;line-height:1.4">{label}</div>{v2(b, win=="b")}</div>'''
    def v(x, w): 
        if same: return f'<div style="flex:1;text-align:center;font-size:13px;color:#8C90A0">{x}</div>'
        if w: return f'<div style="flex:1;display:flex;justify-content:center"><span style="background:#EFF0FD;color:#3E479B;border-radius:12px;padding:3px 10px;font-size:13px;font-weight:700;display:inline-flex;align-items:center;gap:4px">{ic("check",12,2.6)} {x}</span></div>'
        return f'<div style="flex:1;text-align:center;font-size:13px;color:{NAVY}">{x}</div>'
    tag = '<span style="font-size:10.5px;color:#B3B6C3;font-weight:500"> · یکسان</span>' if same else ''
    return f'''<div style="padding:9px 0 8px;border-top:1px solid #F0F1F5"><div style="text-align:center;font-size:11.5px;color:#9A9DAC;margin-bottom:3px">{label}{tag}</div>
<div style="display:flex">{v(a, win=="a")}{v(b, win=="b")}</div></div>'''
cmpb = f'''
{user("سونی XM5 رو با ایرپادز پرو ۲ مقایسه کن.")}
{asst("<b>پیشنهاد من:</b> برای خونه و کار سونی؛ برای بیرون و ورزش ایرپادز.", steps_pill("۳ مرحله انجام شد"))}
<div class="card" style="padding:14px 14px 4px;border-radius:28px;margin-bottom:14px">
<div style="display:flex;gap:10px;margin-bottom:10px">
 {''.join(f"""<div style="flex:1;text-align:center"><div class="tile" style="width:100%;height:84px;border-radius:18px;margin-bottom:6px">{IMG(f).replace("<img","<img style='object-fit:contain'")}</div><div style="font-size:13px;font-weight:800;line-height:1.5">{t}</div><div style="font-size:13px;font-weight:700;color:#5B6072"><span dir="ltr">{m}</span></div></div>""" for f,t,m in [("headphone.png","هدفون سونی","WH-1000XM5"),("airpods.png","هدفون اپل","AirPods Pro 2")])}
</div>
{crow("نوع","روگوشی","توگوشی")}
{crow("عمر باتری","۳۰ ساعت","۶ ساعت (۳۰ با کیس)")}
{crow("وزن","۲۵۰ گرم","۵٫۳ گرم","b")}
{crow("نویزگیر فعال","دارد","دارد",same=True)}
{crow("کمترین قیمت","۱۸٬۹۰۰٬۰۰۰","۱۳٬۷۰۰٬۰۰۰","b")}
{crow("فروشنده نزدیک ونک","۳ فروشنده","۴ فروشنده","b")}
{crow("گارانتی","۱۸ ماهه","۱۸ ماهه",same=True)}
</div>
'''
page("06-compare", cmpb)

# ---------- 7 INSTALLMENT ----------
inst = f'''
{user("یه یخچال فریزر قسطی تا ۴۰ میلیون می‌خوام.")}
{asst("۹ پیشنهاد قسطی پیدا کردم؛ این‌ها ارزون‌ترین‌هاشن:", steps_pill("۵ مرحله انجام شد"))}
<div class="chips" style="flex-wrap:nowrap;margin:-2px 0 14px"><span class="chip on">{ic("check",13,2.4)} قسطی</span><span class="chip on">تا ۴۰ میلیون</span><span class="chip on">گارانتی‌دار</span><span class="chip">{ic("sliders",13)} فیلتر</span></div>
{pcard("یخچال فریزر دوقلو","Model RF-24","۳۲٬۴۰۰٬۰۰۰","۳۵٬۱۰۰٬۰۰۰",svg_fridge(62),[("card","۵ فروشندهٔ قسطی"),("shield","گارانتی ۱۸ ماهه")],extra=f'<div style="margin-top:6px"><span class="badge b-lav">{ic("card",12)} قسطی</span></div>',tilebg="#F2F5F8")}
{pcard("یخچال ساید بای ساید","Model SBS-68","۳۶٬۸۰۰٬۰۰۰","۳۹٬۵۰۰٬۰۰۰",svg_fridge_sbs(66),[("card","۳ فروشندهٔ قسطی"),("shield","گارانتی ۲۴ ماهه")],extra=f'<div style="margin-top:6px"><span class="badge b-lav">{ic("card",12)} قسطی</span></div>',fresh="آخرین تغییر قیمت: امروز",tilebg="#F1F2F6")}
'''
page("07-installment", inst)

# ---------- 8 GUIDED ----------
def opt(img, t, on=False):
    st = "border:1.5px solid #F4B9C4;background:linear-gradient(180deg,#fff,#FFF4F6);" if on else "border:1px solid #EDEEF3;background:#fff;"
    ck = f'<span style="position:absolute;top:8px;left:8px;width:18px;height:18px;border-radius:50%;background:{PINK};color:#fff;display:flex;align-items:center;justify-content:center">{ic("check",11,2.8)}</span>' if on else ""
    return f'<div style="position:relative;{st}border-radius:20px;padding:8px 6px 6px;text-align:center">{ck}<div style="width:48px;height:48px;border-radius:14px;overflow:hidden;margin:0 auto 4px">{img}</div><div style="font-size:12.5px;font-weight:700">{t}</div></div>'
im = lambda f: f"<img src='assets/{f}' style='width:48px;height:48px'>"
guided = f'''
{user("نمی‌دونم چی بخرم!")}
{asst("اشکالی نداره! با سه تا سؤال کوتاه کمکت می‌کنم انتخاب کنی.")}
<div class="card" style="padding:16px 16px 18px;border-radius:28px">
 <div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:15px;font-weight:800">دنبال چه وسیله‌ای هستی؟</b><span class="muted" style="font-size:11.5px">۱ از ۳</span></div>
 <div style="display:flex;gap:5px;margin:8px 0 14px"><span style="flex:1;height:4px;border-radius:3px;background:linear-gradient(90deg,#C7B5FF,#F28AA0)"></span><span style="flex:1;height:4px;border-radius:3px;background:#EEEFF4"></span><span style="flex:1;height:4px;border-radius:3px;background:#EEEFF4"></span></div>
 <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
  {opt(im("ic_headphone_in.png"),"هدفون",True)}{opt(im("ic_phone_in.png"),"گوشی")}{opt(im("ic_laptop_in.png"),"لپ‌تاپ")}{opt(svgtile(svg_fridge(24),"#F1F6F4").replace("50px","48px"),"لوازم خانه")}
 </div>
 <div style="height:1px;background:#F0F1F5;margin:12px 0 10px"></div>
 <b style="font-size:14px;font-weight:800;display:block;margin-bottom:8px">بودجه‌ات حدوداً چقدره؟</b>
 <div class="chips"><span class="chip">تا ۳ میلیون</span><span class="chip on">{ic("check",13,2.4)} ۳ تا ۸ میلیون</span><span class="chip">۸ تا ۲۰ میلیون</span><span class="chip">فرقی نداره</span></div>
 <b style="font-size:14px;font-weight:800;display:block;margin:12px 0 8px">بیشتر کجا ازش استفاده می‌کنی؟</b>
 <div class="chips"><span class="chip">باشگاه و ورزش</span><span class="chip on">{ic("check",13,2.4)} مترو و بیرون</span><span class="chip">خونه و کار</span></div>
 <div style="display:flex;gap:8px;margin-top:14px"><div class="btn btn-navy" style="flex:1;height:44px;border-radius:22px">بعدی {ic("left",15,2.2)}</div><div class="btn btn-soft" style="padding:0 18px;height:44px;border-radius:22px">رد شو</div></div>
</div>
'''
page("08-guided", guided, ph="یا خودت بنویس چی می‌خوای…")

# ---------- 9 NO RESULT ----------
def mini(title, price, where, fresh, c1, c2):
    return f'''<div class="card" style="display:flex;gap:12px;align-items:center;padding:10px 12px 10px 14px;border-radius:22px;margin-bottom:10px">
<div style="flex:1;min-width:0"><div style="font-size:13.5px;font-weight:800">{title}</div>
<div style="font-size:12.5px;color:#4E5368;margin-top:1px">از <b style="color:{NAVY}">{price}</b> تومان</div>
<div style="display:flex;justify-content:space-between;align-items:center"><span class="fresh">{ic("clock",11)} {fresh}</span><span style="font-size:11.5px;color:#7C8194;display:flex;align-items:center;gap:3px">{ic("pin",13)} {where}</span></div></div>
<div style="width:64px;height:70px;border-radius:16px;background:#F4F5F8;display:flex;align-items:center;justify-content:center;flex-shrink:0">{svg_phone(28,c1,c2)}</div></div>'''
nores = f'''
{user("آیفون ۱۵ زیر ۱۰ میلیون نزدیک تجریش می‌خوام.")}
{asst("با این شرایط چیزی پیدا نکردم. کمترین قیمت آیفون ۱۵ تو تهران <b>۴۸٬۹۰۰٬۰۰۰ تومان</b>ـه.", steps_pill("۳ مرحله · نتیجه‌ای نبود", warn=True))}
<div style="display:flex;gap:8px;align-items:flex-start;background:rgba(239,240,253,.7);border-radius:18px;padding:10px 14px;font-size:12px;color:#4B54A8;line-height:1.85;margin-bottom:14px">
<span style="flex-shrink:0;margin-top:3px">{ic("info",15)}</span><span>ترب اطلاعات موجودی انبار رو نداره؛ حدس نمی‌زنم و فقط پیشنهادهای ثبت‌شده رو نشونت می‌دم.</span></div>
<div class="sec">گزینه‌های نزدیک به خواسته‌ات، زیر ۱۰ میلیون</div>
{mini("گوشی سامسونگ گلکسی A25","۹٬۷۰۰٬۰۰۰","تجریش، ۰٫۸ کیلومتر","آخرین تغییر قیمت: ۲ روز پیش","#E6EAF7","#B7C0DC")}
{mini("گوشی شیائومی ردمی نوت ۱۳","۹٬۲۰۰٬۰۰۰","تجریش، ۱٫۴ کیلومتر","آخرین تغییر قیمت: امروز","#EAE6F7","#C3B7DE")}
<div class="chips" style="margin-top:4px"><span class="chip">بودجه رو بیشتر کن</span><span class="chip">{ic("card",13)} آیفون ۱۵ قسطی</span><span class="chip">کل تهران رو بگرد</span></div>
'''
page("09-no-result", nores)
print("ok")
