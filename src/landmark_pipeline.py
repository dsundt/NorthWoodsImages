#!/usr/bin/env python3
"""
The Landmark – Turn-key photo pipeline for Red Canoe Lodging
Processes a photo ZIP into branded, captioned, watermarked outputs.

Features:
- Extracts ZIP archive of photos
- Applies Red Canoe logo watermark (bottom-right, 40% opacity)
- Renames with numeric prefix while preserving original filename
- Produces full-res + web-optimized watermarked sets
- Generates branded PDF + HTML caption tables
- Builds a clean caption list with thumbnails
- Zips both sets for download or deployment

Usage (local or via GitHub Actions):
  python src/landmark_pipeline.py \
    --zip "input/LandMark Photos Names.zip" \
    --logo "input/IMG_1496.jpeg" \
    --property-name "The Landmark" \
    --brand-name "Red Canoe Lodging" \
    --brand-email "info@redcanoelodging.com" \
    --brand-phone "715-351-9687" \
    --brand-site "redcanoelodging.com" \
    --outdir "output/landmark"
"""

import os, io, re, csv, zipfile, base64
from datetime import datetime
from argparse import ArgumentParser
from PIL import Image, ImageOps

# ---------- Brand colors ----------
BRAND_PRIMARY = "#8B1E24"  # Red Canoe red
BRAND_ACCENT  = "#2E4A3B"  # Forest green
BRAND_GREY    = "#4B5563"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# ---------- Helper functions ----------

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path

def extract_zip(zip_path, out_dir):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(out_dir)
    return out_dir

def collect_images(root):
    imgs = []
    for d, _, files in os.walk(root):
        for f in files:
            if f.lower().endswith(IMG_EXTS) and not f.startswith("._"):
                imgs.append(os.path.join(d, f))
    imgs.sort()
    return imgs

def keyword_rank(name):
    order = [
        ("exterior", 0), ("front", 1), ("aerial", 1), ("living", 2),
        ("fireplace", 3), ("kitchen", 4), ("dining", 5),
        ("bedroom", 6), ("bath", 7), ("deck", 8), ("dock", 9),
        ("lake", 10), ("twilight", 11), ("local", 12)
    ]
    n = name.lower()
    rank = 50
    for k, r in order:
        if k in n:
            rank = min(rank, r)
    return rank

def slug_to_caption(name):
    base = os.path.splitext(os.path.basename(name))[0]
    cap = re.sub(r"[_\-]+", " ", base).strip().title()
    if not cap.endswith("."):
        cap += "."
    return cap

def load_captions_csv(path):
    caps = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn = row.get("filename", "").strip()
            tx = row.get("caption", "").strip()
            if fn and tx:
                caps[fn] = tx
    return caps

def apply_logo_watermark(im, logo, opacity=0.4):
    base = im.convert("RGBA")
    lg = logo.convert("RGBA")
    target_w = int(base.width * 0.10)
    scale = target_w / lg.width
    lg = lg.resize((target_w, int(lg.height * scale)), Image.LANCZOS)
    a = lg.split()[-1].point(lambda x: int(x * opacity))
    lg.putalpha(a)
    x = base.width - lg.width - int(base.width * 0.02)
    y = base.height - lg.height - int(base.height * 0.02)
    base.alpha_composite(lg, (x, y))
    return base.convert("RGB")

def resize_for_web(im, max_side=2560):
    w, h = im.size
    if max(w, h) <= max_side:
        return im
    if w > h:
        new_w, new_h = max_side, int(h * max_side / w)
    else:
        new_h, new_w = max_side, int(w * max_side / h)
    return im.resize((new_w, new_h), Image.LANCZOS)

def embed_b64(path, width=150):
    try:
        with Image.open(path) as im:
            im.thumbnail((width, width))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except:
        return ""

# ---------- PDF generation ----------
from reportlab.platypus import SimpleDocTemplate, Paragraph, Image as RLImage, Table, TableStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def make_pdf(pdf_path, rows, brand, logo_path):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=72, bottomMargin=36)
    data = [["#", "Thumbnail", "Room/Area", "Caption"]]
    for i, thumb, room, caption in rows:
        try:
            img = RLImage(thumb, width=85, height=55)
        except:
            img = Paragraph("N/A", styles["Normal"])
        data.append([str(i), img, room, caption])
    table = Table(data, colWidths=[25, 95, 120, 300])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor(BRAND_ACCENT)),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE")
    ]))
    def header_footer(c, d):
        c.setFillColor(colors.white)
        c.rect(0, letter[1]-60, letter[0], 60, fill=1, stroke=0)
        try:
            c.drawImage(logo_path, d.leftMargin, letter[1]-56, width=90, height=36, mask='auto')
        except:
            pass
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(d.leftMargin+100, letter[1]-40, f"{brand['name']} — {brand['property']}")
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor(BRAND_GREY))
        c.drawString(d.leftMargin+100, letter[1]-54, datetime.now().strftime("%B %d, %Y"))
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor(BRAND_GREY))
        footer = f"{brand['name']} • {brand['email']} • {brand['phone']} • {brand['site']}"
        c.drawCentredString(letter[0]/2, 24, footer)
    doc.build([table], onFirstPage=header_footer, onLaterPages=header_footer)

# ---------- HTML outputs ----------
def make_html(html_path, rows, brand, logo_path):
    logo64 = embed_b64(logo_path, width=200)
    header = f"""
<html><head><meta charset='utf-8'><title>{brand['property']} – Photo Order</title>
<style>
body{{font-family:Arial,sans-serif;margin:0}}
.header{{background:#fff;border-bottom:2px solid {BRAND_PRIMARY};padding:12px 20px;display:flex;align-items:center;gap:16px}}
.title{{font-size:18px;font-weight:700;color:#111827}}
.sub{{font-size:12px;color:{BRAND_GREY}}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #e5e7eb;padding:8px;text-align:left;vertical-align:middle}}
th{{background:{BRAND_ACCENT};color:#fff}}
tr:nth-child(even) td{{background:#f9fafb}}
.thumb{{width:150px;height:auto}}
.footer{{color:{BRAND_GREY};font-size:12px;padding:12px 20px;border-top:1px solid #e5e7eb}}
.brand{{color:{BRAND_PRIMARY};font-weight:700}}
</style></head><body>
<div class='header'>
  {'<img src="data:image/jpeg;base64,'+logo64+'" height="40"/>' if logo64 else ''}
  <div><div class='title'>{brand['name']} — {brand['property']}</div>
  <div class='sub'>{datetime.now():%B %d, %Y}</div></div>
</div>
<table><tr><th>#</th><th>Thumbnail</th><th>Room/Area</th><th>Caption</th></tr>
"""
    rows_html = ""
    for i, thumb, room, caption in rows:
        data_uri = embed_b64(thumb)
        img_tag = f'<img class="thumb" src="data:image/jpeg;base64,{data_uri}"/>' if data_uri else ""
        rows_html += f"<tr><td>{i}</td><td>{img_tag}</td><td>{room}</td><td>{caption}</td></tr>"
    footer = f"""
</table>
<div class='footer'><span class='brand'>{brand['name']}</span> • {brand['email']} • {brand['phone']} • {brand['site']}</div>
</body></html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(header + rows_html + footer)

def make_list_html(html_path, rows, brand, logo_path):
    logo64 = embed_b64(logo_path, width=150)
    body = [f"<h2>{brand['name']} — {brand['property']}</h2><ol>"]
    for i, thumb, room, caption in rows:
        data_uri = embed_b64(thumb)
        img_tag = f'<img src="data:image/jpeg;base64,{data_uri}" style="width:140px;height:auto;border:1px solid #e5e7eb"/>' if data_uri else ""
        body.append(f"<li><div style='display:flex;gap:10px;align-items:flex-start'><div>{img_tag}</div><div><strong>{i}. {room}</strong><br>{caption}</div></div></li>")
    body.append("</ol>")
    body.append(f"<hr><div style='font-size:12px;color:{BRAND_GREY}'>{brand['name']} • {brand['email']} • {brand['phone']} • {brand['site']}</div>")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<html><body>" + "".join(body) + "</body></html>")

# ---------- Main ----------
def main():
    ap = ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--logo", required=True)
    ap.add_argument("--property-name", required=True)
    ap.add_argument("--brand-name", required=True)
    ap.add_argument("--brand-email", required=True)
    ap.add_argument("--brand-phone", required=True)
    ap.add_argument("--brand-site", required=True)
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--order-file")
    ap.add_argument("--captions-csv")
    ap.add_argument("--max-web-width", type=int, default=2560)
    args = ap.parse_args()

    brand = {
        "property": args.property_name,
        "name": args.brand_name,
        "email": args.brand_email,
        "phone": args.brand_phone,
        "site": args.brand_site,
    }

    work = ensure_dir(args.outdir)
    extract_dir = os.path.join(work, "extracted")
    extract_zip(args.zip, extract_dir)

    srcs = collect_images(extract_dir)
    if not srcs:
        raise SystemExit("No images found in ZIP")

    if args.order_file and os.path.exists(args.order_file):
        with open(args.order_file) as f:
            names = [ln.strip() for ln in f if ln.strip()]
        ordered = [s for name in names for s in srcs if os.path.basename(s) == name]
        remaining = [s for s in srcs if s not in ordered]
        remaining.sort(key=lambda x: (keyword_rank(x), os.path.basename(x)))
        srcs = ordered + remaining
    else:
        srcs.sort(key=lambda x: (keyword_rank(x), os.path.basename(x)))

    caps = load_captions_csv(args.captions_csv) if args.captions_csv and os.path.exists(args.captions_csv) else {}
    logo = Image.open(args.logo)
    full_dir = ensure_dir(os.path.join(work, "photos_full_res_watermarked"))
    web_dir  = ensure_dir(os.path.join(work, "photos_web_optimized_watermarked"))
    thumbs_dir = ensure_dir(os.path.join(work, "thumbnails"))

    rows = []
    for i, src in enumerate(srcs, start=1):
        base = os.path.basename(src)
        caption = caps.get(base, slug_to_caption(base))
        room = re.sub(r"[_\-]+", " ", os.path.splitext(base)[0]).strip().title()
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            wm = apply_logo_watermark(im, logo, 0.4)
            new_name = f"{i:02d}_{base}"
            full_path = os.path.join(full_dir, new_name)
            wm.save(full_path, quality=95)
            web = resize_for_web(wm, args.max_web_width)
            web.save(os.path.join(web_dir, new_name), quality=85)
            thumb_path = os.path.join(thumbs_dir, f"thumb_{i:02d}.jpg")
            t = wm.copy()
            t.thumbnail((600, 400))
            t.save(thumb_path, quality=85)
        rows.append((i, thumb_path, room, caption))

    pdf = os.path.join(work, f"{brand['property'].replace(' ','_')}_Photo_Order_Branded.pdf")
    html = os.path.join(work, f"{brand['property'].replace(' ','_')}_Photo_Order_Branded.html")
    lst = os.path.join(work, f"{brand['property'].replace(' ','_')}_Clean_Captions_List.html")

    make_pdf(pdf, rows, brand, args.logo)
    make_html(html, rows, brand, args.logo)
    make_list_html(lst, rows, brand, args.logo)
    print(f"✅ Done. Outputs in: {work}")

if __name__ == "__main__":
    main()
