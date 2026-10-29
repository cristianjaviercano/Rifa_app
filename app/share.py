"""Enlaces para compartir: página con metadatos Open Graph (WhatsApp, Facebook, LinkedIn, X, Telegram…)
y tarjeta de imagen dinámica. Los rastreadores no ejecutan JavaScript ni leen el `#`, por eso /r/{id}
responde HTML con las etiquetas y luego redirige a la aplicación."""
import io
import os
from html import escape
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw, ImageFont

from .db import get_conn

router = APIRouter()
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
GENERIC = ("Rifa App", "Rifas y sorteos transparentes: elige tu número y participa.")


def base_url(request: Request) -> str:
    return (os.environ.get("SGRS_PUBLIC_URL") or str(request.base_url)).rstrip("/")


def _raffle(conn, rid):
    return conn.execute(
        "SELECT r.title, r.ticket_price, r.currency, r.sales_close_at, r.status,"
        " (SELECT count(*) FROM tickets t WHERE t.raffle_id=r.id) AS total,"
        " (SELECT count(*) FROM tickets t WHERE t.raffle_id=r.id AND t.status IN ('PAGADO','GANADOR')) AS sold"
        " FROM raffles r WHERE r.id=%s AND r.status <> 'DRAFT'", (rid,)).fetchone()


def _money(n) -> str:
    return "$" + f"{int(n):,}".replace(",", ".")


def describe(r) -> tuple[str, str]:
    if not r:
        return GENERIC
    pct = round(100 * r["sold"] / r["total"]) if r["total"] else 0
    d = r["sales_close_at"]
    if r["status"] == "OPEN":
        txt = f"Boleta a {_money(r['ticket_price'])} · {pct}% vendido · cierra el {d.day} {MESES[d.month - 1]}. Elige tu número y participa."
    elif r["status"] == "DRAWN":
        txt = "Sorteo realizado. Mira el resultado y verifica los ganadores."
    else:
        txt = "Ventas cerradas. Pronto se realizará el sorteo."
    return r["title"], txt


@router.get("/r/{rid}", response_class=HTMLResponse)
def share_page(rid: UUID, request: Request, conn=Depends(get_conn)):
    title, desc = describe(_raffle(conn, rid))
    base = base_url(request)
    url, dest = f"{base}/r/{rid}", f"/#/r/{rid}"
    t, d = escape(f"{title} · Rifa App" if title != GENERIC[0] else title, quote=True), escape(desc, quote=True)
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title><meta name="description" content="{d}"><link rel="canonical" href="{escape(url)}">
<meta property="og:type" content="website"><meta property="og:site_name" content="Rifa App"><meta property="og:locale" content="es_CO">
<meta property="og:title" content="{t}"><meta property="og:description" content="{d}"><meta property="og:url" content="{escape(url)}">
<meta property="og:image" content="{escape(url)}/og.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{t}"><meta name="twitter:description" content="{d}"><meta name="twitter:image" content="{escape(url)}/og.png">
<meta http-equiv="refresh" content="0;url={dest}"></head><body><p><a href="{dest}">Abrir la rifa</a></p></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=60"})


FONTS = Path(__file__).resolve().parent / "fonts"


def _font(size, bold=False):
    """DejaVu Sans incluida en el repositorio: cubre tildes y ñ (la fuente interna de Pillow no)."""
    try:
        return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width, max_lines):
    lines, cur = [], ""
    for w in text.split():
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]; lines[-1] = lines[-1][: max(1, len(lines[-1]) - 1)].rstrip() + "…"
    return lines


@router.get("/r/{rid}/og.png")
def share_image(rid: UUID, conn=Depends(get_conn)):
    r = _raffle(conn, rid)
    title, _ = describe(r)
    img = Image.new("RGB", (1200, 630), "#0B6E4F")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 60, 1140, 570), radius=36, fill="#FFFFFF")
    d.text((110, 100), "Rifa", font=_font(40, True), fill="#0E1F19")
    d.text((110 + d.textlength("Rifa", font=_font(40, True)), 100), "App", font=_font(40, True), fill="#0B6E4F")
    y = 175
    for line in _wrap(d, title, _font(60, True), 980, 2):
        d.text((110, y), line, font=_font(60, True), fill="#0E1F19"); y += 78
    if r:
        d.text((110, 400), _money(r["ticket_price"]), font=_font(66, True), fill="#0B6E4F")
        d.text((110 + d.textlength(_money(r["ticket_price"]), font=_font(66, True)) + 20, 428), "por número", font=_font(34), fill="#587066")
        pct = (r["sold"] / r["total"]) if r["total"] else 0
        d.rounded_rectangle((110, 478, 1090, 500), radius=11, fill="#DAE3DE")
        if pct > 0:
            d.rounded_rectangle((110, 478, 110 + int(980 * pct), 500), radius=11, fill="#0B6E4F")
        d.text((110, 512), f"{round(pct * 100)}% vendido · elige tu número", font=_font(26), fill="#587066")
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=300"})
