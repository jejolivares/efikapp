# -*- coding: utf-8 -*-
"""
Informes de Generacion FV para clientes - Efika Ingenieria
==========================================================

Recorre todas las plantas de Huawei FusionSolar y Deye Cloud y genera, por cliente,
un PDF sencillo: generacion al inicio vs. actual y ahorro estimado con los paneles.
Ademas deja un resumen interno en Excel con las alertas.

Uso:
  pip install requests openpyxl reportlab matplotlib
  python informes_clientes.py                      todas las plantas, hasta el mes pasado
  python informes_clientes.py --planta "Tania"     solo las plantas cuyo nombre contenga "Tania"
  python informes_clientes.py --hasta 2026-10      hasta un mes especifico
  python informes_clientes.py --sin-api            regenerar con los datos.csv guardados (tras corregirlos)
  python informes_clientes.py --listar             ver las plantas de cada plataforma

Credenciales (nunca en este archivo), en este orden:
  1. Variables de entorno (entorno en la nube de Claude):
       FUSIONSOLAR_USERNAME, FUSIONSOLAR_SYSTEM_CODE, FUSIONSOLAR_SUBDOMAIN
       DEYE_APP_ID, DEYE_APP_SECRET, DEYE_EMAIL, DEYE_PASSWORD, DEYE_API_BASE (opcional)
  2. credenciales.ini (servidor de oficina, FUERA de la carpeta de Drive).
"""

import argparse
import configparser
import csv
import datetime as dt
import hashlib
import io
import os
import re
import sys
import time
import unicodedata

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

BASE = os.path.dirname(os.path.abspath(__file__))
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MC = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

AZUL, NARANJA, GRIS = colors.HexColor("#1a3c5e"), colors.HexColor("#e8a33d"), colors.HexColor("#6b7280")
C_GEN, C_CONS = "#2e9e4f", "#c0392b"


# =============================================================== utilidades
def mk(y, m):
    return dt.date(y, m, 1)


def sig(d):
    return dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def ant(d, n=1):
    for _ in range(n):
        d = dt.date(d.year - (d.month == 1), (d.month - 2) % 12 + 1, 1)
    return d


def meses(desde, hasta):
    d = desde
    while d <= hasta:
        yield d
        d = sig(d)


def pmes(t):
    y, m = t.strip()[:7].split("-")
    return mk(int(y), int(m))


def clave(txt):
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def carpeta_segura(nombre):
    return re.sub(r'[\\/:*?"<>|]', "-", nombre).strip().rstrip(".")


def n(v, dec=0):
    return "—" if v is None else f"{v:,.{dec}f}"


def rd(v):
    return "—" if v is None else "RD$" + f"{v:,.0f}"


def pct(v, signo=True):
    return "—" if v is None else (f"{v*100:+.1f}%" if signo else f"{v*100:.1f}%")


def num(v):
    try:
        return None if v in (None, "") else float(str(v).replace(",", ""))
    except ValueError:
        return None


# ============================================================ credenciales
ENV = {
    "fusionsolar": {"usuario": "FUSIONSOLAR_USERNAME", "system_code": "FUSIONSOLAR_SYSTEM_CODE",
                    "subdominio": "FUSIONSOLAR_SUBDOMAIN"},
    "deye": {"app_id": "DEYE_APP_ID", "app_secret": "DEYE_APP_SECRET", "email": "DEYE_EMAIL",
             "password": "DEYE_PASSWORD", "api_base": "DEYE_API_BASE"},
}


def leer_credenciales():
    ruta = os.environ.get("EFIKA_CREDENCIALES", os.path.join(BASE, "credenciales.ini"))
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ruta, encoding="utf-8-sig")
    for sec, campos in ENV.items():
        for campo, var in campos.items():
            v = os.environ.get(var)
            if v:
                if not cp.has_section(sec):
                    cp.add_section(sec)
                cp[sec][campo] = v
    return cp


# ============================================================ FusionSolar
class FusionSolar:
    GEN = ["PVYield", "inverterYield", "inverter_power", "product_power"]
    CONS = ["use_power"]
    INY = ["ongrid_power"]

    def __init__(self, cred):
        c = cred["fusionsolar"]
        self.user, self.code = c.get("usuario"), c.get("system_code")
        sub = c.get("subdominio", "intl")
        host = sub if "." in sub else f"{sub}.fusionsolar.huawei.com"
        self.url = f"https://{host}/thirdData"
        self.s, self.token = requests.Session(), None

    def login(self):
        r = self.s.post(self.url + "/login", json={"userName": self.user, "systemCode": self.code}, timeout=30)
        r.raise_for_status()
        d = r.json()
        if not d.get("success"):
            raise RuntimeError(f"Login Huawei fallido: {d}")
        p = d.get("params")
        self.token = (p.get("xsrfToken") if isinstance(p, dict) else None) \
            or self.s.cookies.get("XSRF-TOKEN") or self.s.cookies.get("xsrf-token")
        if not self.token:
            raise RuntimeError("No se encontro el token XSRF de Huawei")

    def post(self, ep, payload):
        if not self.token:
            self.login()
        r = self.s.post(f"{self.url}/{ep}", json=payload, headers={"xsrf-token": self.token}, timeout=60)
        r.raise_for_status()
        d = r.json()
        if not d.get("success"):
            raise RuntimeError(f"Error Huawei en {ep}: {d}")
        time.sleep(3)
        return d.get("data") or []

    def plantas(self):
        vistos = {}
        for s in self.post("getStationList", {}):
            vistos.setdefault(s["stationCode"], s)
        out = []
        for s in vistos.values():
            cap = num(s.get("capacity"))
            if cap is not None and cap < 1:  # la API antigua reporta en MW
                cap *= 1000
            out.append({"plataforma": "Huawei", "id": s["stationCode"], "nombre": s.get("stationName", ""),
                        "kwp_api": cap})
        return out

    def historico(self, codigos, anio_desde, anio_hasta):
        """{codigo: {mes: {gen, cons, iny}}} para todos los codigos (lotes de 100)."""
        out = {c: {} for c in codigos}
        for i in range(0, len(codigos), 100):
            lote = codigos[i:i + 100]
            for y in range(anio_desde, anio_hasta + 1):
                ts = int(dt.datetime(y, 6, 15, 12).timestamp() * 1000)
                for it in self.post("getKpiStationMonth", {"stationCodes": ",".join(lote), "collectTime": ts}):
                    c, t = it.get("stationCode"), it.get("collectTime")
                    if c not in out or t is None:
                        continue
                    d = dt.datetime.fromtimestamp(t / 1000).date()
                    if d.year != y:
                        continue
                    m = it.get("dataItemMap") or {}
                    out[c][mk(d.year, d.month)] = {"gen": primero(m, self.GEN), "cons": primero(m, self.CONS),
                                                   "iny": primero(m, self.INY)}
        return out


def primero(m, campos):
    for c in campos:
        v = num(m.get(c))
        if v is not None:
            return v
    return None


# ================================================================== Deye
class Deye:
    def __init__(self, cred):
        c = cred["deye"]
        self.app_id, self.secret = c.get("app_id"), c.get("app_secret")
        self.email, self.pwd = c.get("email"), c.get("password")
        self.url = c.get("api_base", "https://us1-developer.deyecloud.com/v1.0")
        self.token = None

    def _login(self, company_id=None):
        body = {"appSecret": self.secret, "email": self.email,
                "password": hashlib.sha256(self.pwd.encode("utf-8")).hexdigest()}
        if company_id is not None:
            body["companyId"] = company_id
        r = requests.post(self.url + "/account/token", params={"appId": self.app_id}, json=body, timeout=30)
        r.raise_for_status()
        d = r.json()
        if not d.get("success", False):
            raise RuntimeError(f"Login Deye fallido: {d}")
        return d["accessToken"]

    def h(self):
        if not self.token:
            tok = self._login()
            r = requests.post(self.url + "/account/info", headers={"Authorization": "Bearer " + tok},
                              json={}, timeout=30)
            r.raise_for_status()
            orgs = r.json().get("orgInfoList") or []
            self.token = self._login(orgs[0]["companyId"]) if orgs else tok
        return {"Authorization": "Bearer " + self.token}

    def post(self, ep, body):
        r = requests.post(self.url + ep, headers=self.h(), json=body, timeout=60)
        r.raise_for_status()
        d = r.json()
        time.sleep(1.5)
        if not d.get("success", False):
            raise RuntimeError(f"Error Deye {ep}: {d}")
        return d

    def plantas(self):
        out, pag = [], 1
        while True:
            lst = self.post("/station/list", {"page": pag, "size": 100}).get("stationList") or []
            for s in lst:
                out.append({"plataforma": "Deye", "id": s["id"], "nombre": str(s.get("name", "")),
                            "kwp_api": num(s.get("installedCapacity")) or num(s.get("capacity"))})
            if len(lst) < 100:
                return out
            pag += 1

    def historico(self, station_id, desde, hasta):
        """{mes: {gen, cons, iny}}. Intenta granularidad mensual; si falla, suma los dias."""
        out = {}
        try:
            y = desde.year
            while y <= hasta.year:
                d = self.post("/station/history", {"stationId": station_id, "granularity": 3,
                                                   "startAt": f"{y}-01", "endAt": f"{y}-12"})
                for it in d.get("stationDataItems") or []:
                    if it.get("year") and it.get("month"):
                        out[mk(int(it["year"]), int(it["month"]))] = {
                            "gen": num(it.get("generationValue")), "cons": num(it.get("consumptionValue")),
                            "iny": num(it.get("gridValue"))}
                y += 1
            if out:
                return out
        except Exception:
            pass
        ini, fin = desde, (sig(hasta) - dt.timedelta(days=1))
        while ini <= fin:
            f2 = min(ini + dt.timedelta(days=29), fin)
            d = self.post("/station/history", {"stationId": station_id, "granularity": 2,
                                               "startAt": ini.isoformat(), "endAt": f2.isoformat()})
            for it in d.get("stationDataItems") or []:
                k = mk(int(it["year"]), int(it["month"]))
                acc = out.setdefault(k, {"gen": None, "cons": None, "iny": None})
                for campo, fuente in (("gen", "generationValue"), ("cons", "consumptionValue"),
                                      ("iny", "gridValue")):
                    v = num(it.get(fuente))
                    if v is not None:
                        acc[campo] = (acc[campo] or 0) + v
            ini = f2 + dt.timedelta(days=1)
        return out


# ========================================================= base de clientes
def leer_clientes(ruta):
    """CSV exportado de 'Clientes FV Nuevo' (+ columnas opcionales Tarifa y Enviar)."""
    base = {}
    if not ruta or not os.path.exists(ruta):
        return base
    with open(ruta, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip(): v for k, v in row.items()}
            nombre = (row.get("Nombre Proyecto Fusion Solar") or row.get("Nombre Proyecto") or "").strip()
            if nombre:
                base[clave(nombre)] = {"nic": (row.get("NIC") or "").strip(), "kwp": num(row.get("KWP")),
                                       "tarifa": (row.get("Tarifa") or "").strip(),
                                       "enviar": (row.get("Enviar") or "si").strip().lower() not in ("no", "n")}
    return base


# ================================================================= tarifa
class Tarifa:
    def __init__(self, nombre, sec):
        self.nombre = sec.get("nombre", nombre)
        self.unico = num(sec.get("precio_unico"))
        self.tramos = [(float(a), float(b)) for a, b in
                       (p.split(":") for p in sec.get("tramos", "").split(",") if p.strip())]
        self.umbral = num(sec.get("umbral_todo_kwh")) or 0
        self.ptodo = num(sec.get("precio_todo")) or 0
        self.fijo = num(sec.get("cargo_fijo")) or 0

    def factura(self, kwh):
        kwh = max(kwh or 0, 0)
        if self.unico is not None:
            return kwh * self.unico + self.fijo
        if self.umbral and kwh > self.umbral:
            return kwh * self.ptodo + self.fijo
        tot, a = 0.0, 0.0
        for lim, pr in self.tramos:
            if kwh > a:
                tot += (min(kwh, lim) - a) * pr
            a = lim
        if kwh > a:
            tot += (kwh - a) * self.tramos[-1][1]
        return tot + self.fijo


# ================================================================ analisis
def analizar(meta, datos, hasta, cfg, tarifa):
    kwp = meta["kwp"]
    rend = cfg.getfloat("general", "rendimiento_kwh_kwp", fallback=1500)
    umbral = cfg.getfloat("general", "umbral_incompleto", fallback=0.35)
    cierre = cfg.getint("general", "mes_cierre_credito", fallback=1)
    esperado = kwp * rend / 12 if kwp else None

    con_gen = sorted(k for k, v in datos.items() if (v.get("gen") or 0) > 0 and k <= hasta)
    if not con_gen:
        return None
    inicio = con_gen[0]
    filas = []
    for k in meses(inicio, hasta):
        v = datos.get(k, {})
        g, c = v.get("gen"), v.get("cons")
        inc = g is None or (esperado and g < umbral * esperado)
        filas.append({"mes": k, "gen": g, "cons": c, "inc": bool(inc)})
    idx = {f["mes"]: f for f in filas}
    ok = [f for f in filas if not f["inc"]]
    medidor = any((f["cons"] or 0) > 0 for f in ok)

    # Primer anio vs ultimo anio, mismos meses calendario
    inicio_util = inicio if not idx[inicio]["inc"] else sig(inicio)
    v1 = [k for k in meses(inicio_util, ant(mk(inicio_util.year + 1, inicio_util.month)))]
    v2 = [k for k in meses(ant(hasta, 11), hasta)]
    cmp = []
    for k2 in v2:
        k1 = next((k for k in v1 if k.month == k2.month), None)
        if k1 and k1.year < k2.year and not idx.get(k1, {"inc": True})["inc"] and not idx[k2]["inc"]:
            cmp.append({"m": k2.month, "k1": k1, "k2": k2, "g1": idx[k1]["gen"], "g2": idx[k2]["gen"]})
    g1, g2 = sum(c["g1"] for c in cmp), sum(c["g2"] for c in cmp)
    var = (g2 / g1 - 1) if cmp and g1 else None

    ult12 = [idx[k] for k in v2 if k in idx and not idx[k]["inc"]]
    esp12 = (sum(f["gen"] for f in ult12) / len(ult12) * 12 / kwp) if (ult12 and kwp) else None

    # Ahorro (credito de medicion neta arrastrado; se reinicia en el mes de cierre)
    anual, credito, ahorro_tot = {}, 0.0, None
    if medidor and tarifa:
        ahorro_tot = 0.0
        for f in filas:
            if f["mes"].month == cierre:
                credito = 0.0
            if f["inc"] or f["cons"] is None:
                continue
            neto = f["cons"] - f["gen"]
            if neto <= 0:
                credito += -neto
                fact = 0.0
            else:
                uso = min(credito, neto)
                credito -= uso
                fact = neto - uso
            sin, con = tarifa.factura(f["cons"]), tarifa.factura(fact)
            a = anual.setdefault(f["mes"].year, {"gen": 0, "cons": 0, "sin": 0, "con": 0, "meses": 0})
            a["gen"] += f["gen"]; a["cons"] += f["cons"]; a["sin"] += sin; a["con"] += con; a["meses"] += 1
            ahorro_tot += sin - con

    return {"inicio": inicio, "hasta": hasta, "filas": filas, "idx": idx, "esperado": esperado,
            "medidor": medidor, "cmp": cmp, "g1": g1, "g2": g2, "var": var, "esp12": esp12,
            "gen_total": sum(f["gen"] or 0 for f in filas), "anual": anual, "ahorro": ahorro_tot,
            "inc": [f["mes"] for f in filas if f["inc"]], "rend": rend}


def alertas(meta, r):
    al = []
    if not meta["kwp"]:
        al.append("kWp desconocido")
    if r["var"] is not None and r["var"] < -0.05:
        al.append(f"Generación {pct(r['var'])} vs primer año")
    if r["esp12"] is not None and r["esp12"] < 0.85 * r["rend"]:
        al.append(f"Rendimiento bajo: {r['esp12']:,.0f} kWh/kWp en 12 meses")
    rec = [k for k in r["inc"] if k >= ant(r["hasta"], 2)]
    if rec:
        al.append("Sin datos completos en " + ", ".join(f"{MC[k.month]}-{k.year % 100}" for k in rec))
    if r["medidor"] and r["ahorro"] is None:
        al.append("Sin tarifa asignada: no se calculó ahorro")
    return al


# ================================================================== graficos
def img(fig, ancho):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
    w, h = fig.get_size_inches()
    plt.close(fig)
    b.seek(0)
    return Image(b, width=ancho, height=ancho * h / w)


def graf_mensual(r):
    f = r["filas"]
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    x = list(range(len(f)))
    ax.bar(x, [v["gen"] or 0 for v in f], 0.7, color=[("#b8bfca" if v["inc"] else C_GEN) for v in f],
           label="Generación solar")
    if r["medidor"]:
        ax.plot(x, [v["cons"] if (v["cons"] and not v["inc"]) else float("nan") for v in f],
                color=C_CONS, lw=1.8, marker="o", ms=2.5, label="Consumo de la propiedad")
    if r["esperado"]:
        ax.axhline(r["esperado"], ls="--", color="#555", lw=1, label="Generación esperada")
    paso = max(1, len(f) // 18)
    ax.set_xticks(x[::paso])
    ax.set_xticklabels([f"{MC[v['mes'].month]}-{v['mes'].year % 100}" for v in f][::paso], rotation=90, fontsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="y", labelsize=7)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("kWh", fontsize=8)
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.14), frameon=False)
    return fig


# ======================================================================= PDF
ST = {
    "t": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=19, textColor=AZUL, leading=23),
    "s": ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=GRIS, leading=13),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, textColor=AZUL, leading=16,
                        spaceBefore=12, spaceAfter=6),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=6),
    "nota": ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=7.5, leading=10, textColor=GRIS),
    "kv": ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=15, textColor=AZUL, leading=18, alignment=1),
    "kl": ParagraphStyle("kl", fontName="Helvetica", fontSize=8, textColor=GRIS, leading=10, alignment=1),
    "cb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
}


def tabla(d, anchos, total=False, izq=1):
    t = Table([[Paragraph(str(c), ST["cb"]) for c in d[0]]] + d[1:], colWidths=anchos, repeatRows=1)
    e = [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
         ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f8")]),
         ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
         ("ALIGN", (izq, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
         ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if total:
        e += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
              ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e5e9f0"))]
    t.setStyle(TableStyle(e))
    return t


def tarjetas(items, ancho):
    celdas = [[Paragraph(v, ST["kv"]) for v, _ in items], [Paragraph(l, ST["kl"]) for _, l in items]]
    t = Table(celdas, colWidths=[ancho / len(items)] * len(items))
    t.setStyle(TableStyle([("BOX", (i, 0), (i, 1), 0.6, colors.HexColor("#d1d5db")) for i in range(len(items))] +
                          [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f9fb")),
                           ("LINEABOVE", (0, 0), (-1, 0), 2.5, NARANJA),
                           ("TOPPADDING", (0, 0), (-1, 0), 9), ("BOTTOMPADDING", (0, 1), (-1, 1), 9)]))
    return t


def marco(pie):
    def f(c, doc):
        c.saveState()
        w, h = letter
        c.setFont("Helvetica-Bold", 10); c.setFillColor(AZUL)
        c.drawString(0.75 * inch, h - 0.55 * inch, "ÉFIKA INGENIERÍA")
        c.setFont("Helvetica", 8.5); c.setFillColor(GRIS)
        c.drawRightString(w - 0.75 * inch, h - 0.55 * inch, "Informe de Generación Solar")
        c.setStrokeColor(NARANJA); c.setLineWidth(1.5)
        c.line(0.75 * inch, h - 0.63 * inch, w - 0.75 * inch, h - 0.63 * inch)
        c.setStrokeColor(colors.HexColor("#d1d5db")); c.setLineWidth(0.5)
        c.line(0.75 * inch, 0.6 * inch, w - 0.75 * inch, 0.6 * inch)
        c.setFont("Helvetica", 7.5)
        c.drawString(0.75 * inch, 0.45 * inch, pie)
        c.drawRightString(w - 0.75 * inch, 0.45 * inch, f"Página {doc.page}")
        c.restoreState()
    return f


def pdf(meta, r, tarifa, ruta, cfg, hoy):
    doc = SimpleDocTemplate(ruta, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                            title=f"Informe de Generación Solar - {meta['nombre']}")
    A = doc.width
    ini, fin = r["inicio"], r["hasta"]
    s = [Paragraph("Informe de Generación Solar", ST["t"]),
         Paragraph(f"{meta['nombre']} · {MESES[ini.month].capitalize()} {ini.year} – "
                   f"{MESES[fin.month]} {fin.year} · Fecha: {hoy:%d/%m/%Y}", ST["s"]), Spacer(1, 10)]

    datos = [["Potencia instalada", f"{meta['kwp']:g} kWp" if meta["kwp"] else "—",
              "Inicio de operación", f"{MESES[ini.month].capitalize()} {ini.year}"],
             ["Generación esperada", f"{n(meta['kwp'] * r['rend'])} kWh/año" if meta["kwp"] else "—",
              "NIC", meta.get("nic") or "—"]]
    t = Table(datos, colWidths=[A * 0.22, A * 0.28, A * 0.22, A * 0.28])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
                           ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 9), ("TEXTCOLOR", (0, 0), (-1, -1), AZUL),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    s += [t, Spacer(1, 14)]

    kp = [(f"{n(r['gen_total'])} kWh", "Energía generada desde el inicio")]
    if r["ahorro"] is not None:
        kp.append((rd(r["ahorro"]), "Ahorro estimado acumulado"))
    if r["var"] is not None:
        kp.append((pct(r["var"]), "Generación actual vs. primer año"))
    elif r["esp12"] is not None:
        kp.append((f"{n(r['esp12'])} kWh/kWp", "Rendimiento últimos 12 meses"))
    s += [tarjetas(kp, A), Spacer(1, 6)]

    s.append(Paragraph("Generación mensual", ST["h"]))
    s.append(img(graf_mensual(r), A))

    # Primer anio vs ultimo anio
    if r["cmp"]:
        bl = [Paragraph("Primer año vs. último año", ST["h"])]
        v = r["var"]
        txt = (f"En los mismos meses, el sistema generó {n(r['g2'])} kWh en el último año, frente a "
               f"{n(r['g1'])} kWh en su primer año ({pct(v)}).")
        if abs(v) <= 0.05:
            txt += " La producción se mantiene estable."
        elif v > 0.05:
            txt += " La producción es mayor que al inicio."
        bl.append(Paragraph(txt, ST["p"]))
        d = [["Mes", "Primer año (kWh)", "Último año (kWh)", "Variación"]]
        for c in r["cmp"]:
            d.append([MESES[c["m"]].capitalize(), n(c["g1"]), n(c["g2"]), pct(c["g2"] / c["g1"] - 1)])
        d.append(["Total", n(r["g1"]), n(r["g2"]), pct(v)])
        bl.append(tabla(d, [A * 0.28, A * 0.24, A * 0.24, A * 0.24], total=True))
        s.append(KeepTogether(bl))

    # Ahorro por anio
    if r["ahorro"] is not None and r["anual"]:
        bl = [Paragraph("Ahorro con los paneles", ST["h"])]
        d = [["Año", "Generación (kWh)", "Consumo (kWh)", "Factura sin paneles", "Factura con paneles", "Ahorro"]]
        tot = {"gen": 0, "cons": 0, "sin": 0, "con": 0}
        for y in sorted(r["anual"]):
            a = r["anual"][y]
            et = f"{y}" + (f" ({a['meses']} meses)" if a["meses"] < 12 else "")
            d.append([et, n(a["gen"]), n(a["cons"]), rd(a["sin"]), rd(a["con"]), rd(a["sin"] - a["con"])])
            for k in tot:
                tot[k] += a[k]
        d.append(["Total", n(tot["gen"]), n(tot["cons"]), rd(tot["sin"]), rd(tot["con"]), rd(tot["sin"] - tot["con"])])
        bl.append(tabla(d, [A * 0.16] + [A * 0.168] * 5, total=True))
        s.append(KeepTogether(bl))

    nota = ["Datos de la plataforma de monitoreo del sistema."]
    if r["inc"]:
        nota.append("Los meses sin datos completos se excluyen de las comparaciones y del ahorro.")
    if r["ahorro"] is not None:
        nota.append(f"Ahorro estimado con la tarifa {tarifa.nombre} vigente, en cargo por energía. El cargo por "
                    f"potencia, si aplica, no se incluye porque los paneles no lo eliminan. Puede variar respecto a "
                    f"las facturas reales.")
    s += [Spacer(1, 10), Paragraph(" ".join(nota), ST["nota"])]
    pie = cfg.get("empresa", "pie", fallback="Éfika Ingeniería SRL")
    doc.build(s, onFirstPage=marco(pie), onLaterPages=marco(pie))


# =================================================================== cache
def guardar_datos(ruta, meta, datos):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        f.write(f"# plataforma={meta['plataforma']};id={meta['id']};kwp={meta['kwp'] or ''}\n")
        w = csv.writer(f)
        w.writerow(["mes", "generacion_kwh", "consumo_kwh", "inyectado_kwh"])
        for k in sorted(datos):
            v = datos[k]
            w.writerow([k.strftime("%Y-%m")] + ["" if v.get(c) is None else round(v[c], 2) for c in ("gen", "cons", "iny")])


def leer_datos(ruta):
    meta, datos = {}, {}
    with open(ruta, encoding="utf-8") as f:
        prim = f.readline()
        if prim.startswith("#"):
            meta = dict(p.split("=", 1) for p in prim[1:].strip().split(";") if "=" in p)
        else:
            f.seek(0)
        for row in csv.DictReader(f):
            datos[pmes(row["mes"])] = {"gen": num(row.get("generacion_kwh")), "cons": num(row.get("consumo_kwh")),
                                       "iny": num(row.get("inyectado_kwh"))}
    return meta, datos


# ==================================================================== main
def main():
    ap = argparse.ArgumentParser(description="Informes de generación FV para clientes - Efika")
    ap.add_argument("--config", default=os.path.join(BASE, "config.ini"))
    ap.add_argument("--planta", help="texto contenido en el nombre de la planta")
    ap.add_argument("--hasta", help="último mes a incluir (AAAA-MM); por defecto el mes pasado")
    ap.add_argument("--sin-api", action="store_true", help="usar los datos.csv ya guardados")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--salida", help="carpeta de salida (anula carpeta_salida de config.ini)")
    a = ap.parse_args()

    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(a.config, encoding="utf-8-sig")
    salida = a.salida or os.environ.get("EFIKA_SALIDA") or cfg.get(
        "empresa", "carpeta_salida", fallback=os.path.join(BASE, "salida"))
    if not os.path.isabs(salida):
        salida = os.path.join(BASE, salida)
    rc = cfg.get("empresa", "clientes_csv", fallback="clientes.csv")
    clientes = leer_clientes(rc if os.path.isabs(rc) else os.path.join(BASE, rc))
    tarifas = {sec.split(":", 1)[1]: Tarifa(sec.split(":", 1)[1], cfg[sec]) for sec in cfg.sections()
               if sec.startswith("tarifa:")}
    t_res = cfg.get("general", "tarifa_residencial", fallback="")
    prefijos = [clave(p) for p in cfg.get("general", "prefijos_residencial", fallback="Res.,Flia,Familia").split(",")]

    hoy = dt.date.today()
    hasta = pmes(a.hasta) if a.hasta else ant(mk(hoy.year, hoy.month))
    anio_desde = cfg.getint("general", "anio_desde", fallback=2019)
    filtro = clave(a.planta) if a.planta else None

    # ---- obtener plantas y datos
    plantas = []  # (meta, datos)
    if a.sin_api:
        for d in sorted(os.listdir(salida)) if os.path.isdir(salida) else []:
            ruta = os.path.join(salida, d, "datos.csv")
            if os.path.exists(ruta) and (not filtro or filtro in clave(d)):
                m, datos = leer_datos(ruta)
                plantas.append(({"plataforma": m.get("plataforma", ""), "id": m.get("id", ""), "nombre": d,
                                 "kwp_api": num(m.get("kwp"))}, datos))
    else:
        cred = leer_credenciales()
        plats = []
        if cred.has_section("fusionsolar") and cred["fusionsolar"].get("usuario"):
            try:
                fs = FusionSolar(cred)
                hw = [p for p in fs.plantas() if not filtro or filtro in clave(p["nombre"])]
                plats.append(("Huawei", hw))
            except Exception as e:
                print(f"ERROR FusionSolar (no se pudo conectar a {fs.url}): {e}")
        if cred.has_section("deye") and cred["deye"].get("app_id"):
            try:
                dy = Deye(cred)
                de = [p for p in dy.plantas() if not filtro or filtro in clave(p["nombre"])]
                plats.append(("Deye", de))
            except Exception as e:
                print(f"ERROR Deye: {e}")
        if a.listar:
            for nom, lst in plats:
                for p in lst:
                    print(f"{nom}\t{p['id']}\t{p['nombre']}\t{p['kwp_api'] or ''} kWp")
            return
        for nom, lst in plats:
            print(f"{nom}: {len(lst)} plantas. Descargando datos...")
            if nom == "Huawei" and lst:
                hist = fs.historico([p["id"] for p in lst], anio_desde, hasta.year)
                plantas += [(p, hist.get(p["id"], {})) for p in lst]
            elif nom == "Deye":
                for p in lst:
                    try:
                        plantas.append((p, dy.historico(p["id"], mk(anio_desde, 1), hasta)))
                    except Exception as e:
                        print(f"  Error Deye {p['nombre']}: {e}")

    # ---- generar informes
    os.makedirs(salida, exist_ok=True)
    resumen = []
    for p, datos in plantas:
        info = clientes.get(clave(p["nombre"]), {})
        if info and not info["enviar"]:
            continue
        meta = {**p, "kwp": info.get("kwp") or p.get("kwp_api"), "nic": info.get("nic", "")}
        tname = info.get("tarifa") or (t_res if any(clave(p["nombre"]).startswith(x) for x in prefijos) else "")
        tarifa = tarifas.get(tname)
        carpeta = os.path.join(salida, carpeta_segura(p["nombre"]))
        os.makedirs(carpeta, exist_ok=True)
        if not a.sin_api:
            guardar_datos(os.path.join(carpeta, "datos.csv"), meta, datos)
        r = analizar(meta, datos, hasta, cfg, tarifa)
        if r is None:
            resumen.append([p["plataforma"], p["nombre"], meta["kwp"], "", "", "", "", "", "", "",
                            "Sin generación registrada", ""])
            continue
        archivo = os.path.join(carpeta, f"Informe de generación - {carpeta_segura(p['nombre'])} - {hasta:%Y-%m}.pdf")
        try:
            pdf(meta, r, tarifa, archivo, cfg, hoy)
        except Exception as e:
            print(f"  Error generando {p['nombre']}: {e}")
            archivo = ""
        al = alertas(meta, r)
        resumen.append([p["plataforma"], p["nombre"], meta["kwp"], f"{r['inicio']:%Y-%m}",
                        "Sí" if r["medidor"] else "No", round(r["gen_total"]), round(r["g1"]) if r["cmp"] else "",
                        round(r["g2"]) if r["cmp"] else "", round(r["var"] * 100, 1) if r["var"] is not None else "",
                        round(r["ahorro"]) if r["ahorro"] is not None else "", "; ".join(al),
                        os.path.basename(archivo)])
        print(f"  {'!' if al else 'OK'} {p['nombre']}" + (f"  -> {'; '.join(al)}" if al else ""))

    # ---- resumen interno
    wb = Workbook()
    ws = wb.active
    ws.title = f"Resumen {hasta:%Y-%m}"
    enc = ["Plataforma", "Planta", "kWp", "Inicio", "Smart meter", "Generación total (kWh)",
           "Gen. primer año (kWh)", "Gen. último año (kWh)", "Variación %", "Ahorro acumulado (RD$)",
           "Alertas", "Archivo"]
    ws.append(enc)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", start_color="1A3C5E")
    rojo = PatternFill("solid", start_color="F8CBAD")
    for fila in sorted(resumen, key=lambda x: (x[10] == "", x[1])):
        ws.append(fila)
        if fila[10]:
            for c in ws[ws.max_row]:
                c.fill = rojo
    for i, w in enumerate([11, 40, 8, 9, 8, 14, 14, 14, 10, 14, 50, 55], start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    rres = os.path.join(salida, f"Resumen informes {hasta:%Y-%m}.xlsx")
    wb.save(rres)
    print(f"\nListo: {len(resumen)} plantas. Resumen interno: {rres}")


if __name__ == "__main__":
    main()
