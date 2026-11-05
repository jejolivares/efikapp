# -*- coding: utf-8 -*-
"""Informe de Generación vs Consumo (Éfika Ingeniería) para cualquier planta FV.

La carpeta del cliente (informes/<slug>/) debe tener:
  datos.csv     descargado con programa/informes_clientes.py (mes, generacion_kwh, consumo_kwh, inyectado_kwh)
  informe.json  datos del cliente y textos del informe (ver SKILL.md)

Uso:
  python informe.py analizar informes/<slug>   -> imprime las métricas en JSON para redactar los textos
  python informe.py pdf informes/<slug>        -> crea el PDF y vista_previa/pagina-N.png
"""
import configparser
import csv
import datetime as dt
import glob
import io
import json
import os
import shutil
import subprocess
import sys

MC = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
# Distribución mensual de la generación esperada (% del año, hoja de seguimiento Éfika)
PCT = {1: 7.69, 2: 7.76, 3: 8.90, 4: 8.93, 5: 8.73, 6: 8.64, 7: 9.30, 8: 9.42,
       9: 8.92, 10: 8.34, 11: 6.87, 12: 6.51}


# ================================================================== utilidades
def etq(k):
    return f"{MC[k[1]]}-{k[0] % 100:02d}"


def pk(t):
    y, m = map(int, t.split("-"))
    return (y, m)


def n(v, d=0):
    return "—" if v is None else f"{v:,.{d}f}"


def rd(v):
    return "—" if v is None else f"RD${v:,.0f}"


def pct(v, s=True):
    return "—" if v is None else (f"{v * 100:+.1f}%" if s else f"{v * 100:.1f}%")


def raiz_repo(desde):
    d = os.path.abspath(desde)
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "programa", "config.ini")):
            return d
        d = os.path.dirname(d)
    return None


class Tarifa:
    """Tarifa escalonada de config.ini ([tarifa:NOMBRE])."""

    def __init__(self, nombre, sec):
        self.nombre = sec.get("nombre", nombre)
        self.tramos = [(float(a), float(b)) for a, b in
                       (p.split(":") for p in sec.get("tramos", "").split(",") if p.strip())]
        self.umbral = float(sec.get("umbral_todo_kwh", 0) or 0)
        self.ptodo = float(sec.get("precio_todo", 0) or 0)
        self.fijo = float(sec.get("cargo_fijo", 0) or 0)
        self.unico = float(sec["precio_unico"]) if sec.get("precio_unico") else None

    def factura(self, kwh):
        kwh = max(kwh or 0, 0)
        if self.unico is not None:
            return kwh * self.unico + self.fijo
        if self.umbral and kwh > self.umbral:
            return kwh * self.ptodo + self.fijo
        t, a = 0.0, 0.0
        for lim, pr in self.tramos:
            if kwh > a:
                t += (min(kwh, lim) - a) * pr
            a = lim
        if kwh > a and self.tramos:
            t += (kwh - a) * self.tramos[-1][1]
        return t + self.fijo

    def descripcion(self):
        if self.unico is not None:
            return f"precio único RD${self.unico:,.2f}/kWh"
        partes, a = [], 0
        for lim, pr in self.tramos:
            partes.append(f"{a:.0f}–{lim:.0f} kWh RD${pr:,.2f}")
            a = lim
        txt = "; ".join(partes)
        if self.umbral:
            txt += f"; más de {self.umbral:.0f} kWh todos a RD${self.ptodo:,.2f}"
        return txt + f"; cargo fijo RD${self.fijo:,.2f}"


# ================================================================== cálculo
def cargar(carpeta):
    with open(os.path.join(carpeta, "informe.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    D = {}
    with open(os.path.join(carpeta, "datos.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(l for l in f if not l.startswith("#")):
            if not r.get("generacion_kwh"):
                continue
            k = pk(r["mes"])
            g = float(r["generacion_kwh"])
            c = float(r["consumo_kwh"]) if r.get("consumo_kwh") else None
            i = float(r["inyectado_kwh"]) if r.get("inyectado_kwh") else None
            D[k] = {"gen": g, "cons": c, "iny": i}
    return cfg, D


def calcular(cfg, D):
    hoy = dt.date.today()
    hasta = pk(cfg["hasta"]) if cfg.get("hasta") else ((hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12))
    D = {k: v for k, v in D.items() if k <= hasta}
    if not D:
        sys.exit("datos.csv no tiene generación hasta " + f"{hasta[0]}-{hasta[1]:02d}")
    kwp = float(cfg["kwp"])
    rend = float(cfg.get("rendimiento", 1500))
    anual_esp = kwp * rend
    for k, v in D.items():
        v["esp"] = anual_esp * PCT[k[1]] / 100
        if v["iny"] is not None and v["cons"] is not None:
            v["auto"] = v["gen"] - v["iny"]
            v["red"] = v["cons"] - v["auto"]
    orden = sorted(D)

    # meses incompletos: detección automática + lo que diga informe.json ("AAAA-MM": nota, o null para quitar)
    inc = {}
    if D[orden[0]]["gen"] < 0.6 * D[orden[0]]["esp"]:
        inc[orden[0]] = "Primer mes, parcial"
    for k in orden[1:]:
        if D[k]["gen"] < 0.35 * D[k]["esp"] or (D[k]["cons"] is not None and D[k]["cons"] <= 0):
            inc[k] = "Datos incompletos"
    for t, nota in (cfg.get("incompletos") or {}).items():
        if nota is None:
            inc.pop(pk(t), None)
        else:
            inc[pk(t)] = nota
    ok = [k for k in orden if k not in inc]
    medidor = any((D[k]["cons"] or 0) > 0 for k in ok)
    autoc = medidor and any("auto" in D[k] for k in ok)

    def suma(c, ks):
        return sum(D[k][c] or 0 for k in ks)

    # por año
    anios = {}
    for y in sorted({k[0] for k in orden}):
        ks = [k for k in orden if k[0] == y]
        kok = [k for k in ks if k in ok]
        g, c, e = suma("gen", ks), suma("cons", ks) if medidor else None, suma("esp", ks)
        anios[y] = {"meses": len(ks), "incompletos": len(ks) - len(kok), "gen": g, "cons": c,
                    "cob": (g / c) if c else None, "pct_esperado": g / e if e else None}

    # año actual (enero..hasta) y comparación con el primer año que tenga los mismos meses completos
    ya, mh = hasta
    act = [k for k in ok if k[0] == ya]
    base = None
    for y in sorted(anios):
        if y < ya and all((y, m) in ok for m in range(1, mh + 1)):
            base = y
            break
    comp = None
    if base and act:
        ms = [k[1] for k in act]
        kb = [(base, m) for m in ms]
        comp = {"anio_base": base, "meses": f"{MC[ms[0]]}–{MC[ms[-1]]}",
                "gen_base": suma("gen", kb), "gen_actual": suma("gen", act)}
        comp["var_gen"] = comp["gen_actual"] / comp["gen_base"] - 1
        if medidor:
            comp["cons_base"], comp["cons_actual"] = suma("cons", kb), suma("cons", act)
            comp["var_cons"] = comp["cons_actual"] / comp["cons_base"] - 1

    # primer año completo (12 meses ok) y últimos 12 meses
    primer = next((y for y in sorted(anios) if all((y, m) in ok for m in range(1, 13))), None)
    u12 = [k for k in orden[-12:] if k in ok]
    rend12 = suma("gen", u12) / suma("esp", u12) * rend if u12 else None

    # año actual frente a lo esperado
    gen_a, esp_a = suma("gen", act), suma("esp", act)
    actual = {"anio": ya, "meses": len(act), "gen": gen_a, "esp": esp_a,
              "pct_esperado": gen_a / esp_a if esp_a else None}
    if medidor and act:
        c = suma("cons", act)
        actual.update({"cons": c, "cob": gen_a / c if c else None, "excedente": gen_a - c})
        if autoc:
            actual.update({"auto": suma("auto", act), "iny": suma("iny", act), "red": suma("red", act)})

    # meses bajos (completos, < 80 % de lo esperado)
    bajos = [{"mes": etq(k), "gen": D[k]["gen"], "esp": D[k]["esp"], "pct": D[k]["gen"] / D[k]["esp"]}
             for k in ok if D[k]["gen"] < 0.8 * D[k]["esp"]]

    # medición neta del año actual (crédito en cero en enero) y factura estimada
    tarifa = None
    if cfg.get("tarifa"):
        raiz = raiz_repo(os.path.dirname(os.path.abspath(__file__))) or raiz_repo(os.getcwd())
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(os.path.join(raiz, "programa", "config.ini"), encoding="utf-8-sig")
        sec = f"tarifa:{cfg['tarifa']}"
        if cp.has_section(sec):
            tarifa = Tarifa(cfg["tarifa"], cp[sec])
        else:
            print(f"AVISO: tarifa {cfg['tarifa']} no está en programa/config.ini; no se calcula ahorro", file=sys.stderr)
    neta, cred = [], 0.0
    if medidor:
        for k in act:
            neto = D[k]["cons"] - D[k]["gen"]
            if neto <= 0:
                cred += -neto
                fac = 0.0
            else:
                u = min(cred, neto)
                cred -= u
                fac = neto - u
            f = {"mes": etq(k), "cons": D[k]["cons"], "gen": D[k]["gen"], "neto": neto, "fac": fac, "credito": cred}
            if tarifa:
                f["sin_fv"], f["con_fv"] = tarifa.factura(D[k]["cons"]), tarifa.factura(fac)
            neta.append(f)
    tot_neta = None
    if neta:
        tot_neta = {"kwh_fac": sum(f["fac"] for f in neta), "credito_final": neta[-1]["credito"]}
        if tarifa:
            tot_neta["sin_fv"] = sum(f["sin_fv"] for f in neta)
            tot_neta["con_fv"] = sum(f["con_fv"] for f in neta)
            tot_neta["ahorro"] = tot_neta["sin_fv"] - tot_neta["con_fv"]

    mejor = max(ok, key=lambda k: D[k]["gen"] / D[k]["esp"]) if ok else None
    return {
        "hasta": f"{ya}-{mh:02d}", "inicio": f"{orden[0][0]}-{orden[0][1]:02d}", "kwp": kwp, "rendimiento": rend,
        "anual_esperado": anual_esp, "medidor": medidor, "autoconsumo": autoc,
        "incompletos": {etq(k): v for k, v in inc.items()}, "anios": anios, "actual": actual,
        "comparacion": comp, "primer_anio_completo": primer,
        "primer_anio": ({"anio": primer, "gen": anios[primer]["gen"], "pct_esperado": anios[primer]["gen"] / anual_esp,
                         "rend_kwh_kwp": anios[primer]["gen"] / kwp, "cob": anios[primer]["cob"]} if primer else None),
        "rend_ultimos_12_kwh_kwp": rend12, "mejor_mes": etq(mejor) if mejor else None,
        "meses_bajos": bajos, "medicion_neta": neta, "medicion_neta_total": tot_neta,
        "tarifa": tarifa.descripcion() if tarifa else None,
        "mensual": [{"mes": etq(k), **{c: round(v, 1) for c, v in D[k].items() if v is not None},
                     "nota": inc.get(k, "")} for k in orden],
        "_D": D, "_orden": orden, "_ok": ok, "_act": act, "_inc": inc, "_tarifa": tarifa,
    }


# ====================================================================== PDF
def pdf(carpeta, cfg, R):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    D, orden, ok, act, inc = R["_D"], R["_orden"], R["_ok"], R["_act"], R["_inc"]
    nombre = cfg["nombre"]
    AZUL, NARANJA, GRIS = colors.HexColor("#1a3c5e"), colors.HexColor("#e8a33d"), colors.HexColor("#6b7280")
    ST = {
        "t": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=19, textColor=AZUL, leading=23),
        "s": ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=GRIS, leading=13),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, textColor=AZUL, leading=16,
                            spaceBefore=12, spaceAfter=6),
        "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=6),
        "b": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=3, leftIndent=10),
        "nota": ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=7.5, leading=10, textColor=GRIS),
        "cb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
        "c": ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=10.5),
    }

    def tabla(d, anchos, total=False, izq=1, nota_izq=False):
        filas = [[Paragraph(str(c), ST["cb"]) for c in d[0]]]
        for f in d[1:]:
            filas.append([Paragraph(c, ST["c"]) if isinstance(c, str) and len(c) > 45 else c for c in f])
        t = Table(filas, colWidths=anchos, repeatRows=1)
        e = [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f8")]),
             ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
             ("ALIGN", (izq, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if nota_izq:
            e.append(("ALIGN", (-1, 1), (-1, -1), "LEFT"))
        if total:
            e += [("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
                  ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e5e9f0"))]
        t.setStyle(TableStyle(e))
        return t

    def marco(c, doc):
        c.saveState()
        w, h = letter
        c.setFont("Helvetica-Bold", 10); c.setFillColor(AZUL)
        c.drawString(0.75 * inch, h - 0.55 * inch, "ÉFIKA INGENIERÍA")
        c.setFont("Helvetica", 8.5); c.setFillColor(GRIS)
        c.drawRightString(w - 0.75 * inch, h - 0.55 * inch, "Informe de Generación vs Consumo")
        c.setStrokeColor(NARANJA); c.setLineWidth(1.5)
        c.line(0.75 * inch, h - 0.63 * inch, w - 0.75 * inch, h - 0.63 * inch)
        c.setStrokeColor(colors.HexColor("#d1d5db")); c.setLineWidth(0.5)
        c.line(0.75 * inch, 0.6 * inch, w - 0.75 * inch, 0.6 * inch)
        c.setFont("Helvetica", 7.5)
        c.drawString(0.75 * inch, 0.45 * inch, "Éfika Ingeniería SRL · RNC 1-32-08706-2 · Santiago, RD")
        c.drawRightString(w - 0.75 * inch, 0.45 * inch, f"Página {doc.page}")
        c.restoreState()

    def fmt(ax):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="y", labelsize=7)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.set_ylabel("kWh", fontsize=8)

    def img(fig, A):
        b = io.BytesIO()
        fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
        w, h = fig.get_size_inches()
        plt.close(fig)
        b.seek(0)
        return Image(b, width=A, height=A * h / w)

    def graf_mensual(A):
        fig, ax = plt.subplots(figsize=(7.5, 3.1))
        x = list(range(len(orden)))
        ax.bar(x, [D[k]["gen"] for k in orden], 0.75 if len(orden) > 18 else 0.65,
               color=["#b8bfca" if k in inc else "#2e9e4f" for k in orden], label="Generación solar")
        if R["medidor"]:
            ax.plot(x, [D[k]["cons"] if k in ok else float("nan") for k in orden], color="#c0392b", lw=1.6,
                    marker="o", ms=2 if len(orden) > 18 else 3, label=cfg.get("etiqueta_consumo", "Consumo"))
        ax.plot(x, [D[k]["esp"] for k in orden], ls="--", color="#555", lw=1, label="Generación esperada")
        paso = 1 if len(orden) <= 18 else 3
        ax.set_xticks(x[::paso])
        ax.set_xticklabels([etq(k) for k in orden][::paso], rotation=0 if paso == 1 else 90,
                           fontsize=7.5 if paso == 1 else 7)
        fmt(ax)
        ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.15), frameon=False)
        return img(fig, A)

    def graf_origen(A):
        fig, ax = plt.subplots(figsize=(7.5, 2.6))
        x = list(range(len(act)))
        a = [D[k]["auto"] for k in act]
        ax.bar(x, a, 0.65, color="#e8a33d", label="Solar consumida directamente")
        ax.bar(x, [D[k]["red"] for k in act], 0.65, bottom=a, color="#1a3c5e", label="Tomada de la red")
        ax.set_xticks(x)
        ax.set_xticklabels([etq(k) for k in act], fontsize=7.5)
        fmt(ax)
        ax.legend(fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.17), frameon=False)
        return img(fig, A)

    def parrafos(lst):
        return [Paragraph(t, ST["p"]) for t in (lst or [])]

    def vinetas(lst):
        return [Paragraph(t, ST["b"], bulletText="•") for t in (lst or [])]

    hoy = dt.date.today()
    salida = os.path.join(carpeta, cfg.get("archivo") or f"Informe_Gen_vs_Consumo_{os.path.basename(os.path.abspath(carpeta))}.pdf")
    doc = SimpleDocTemplate(salida, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                            title=f"Informe de Generación vs Consumo - {nombre}")
    A = doc.width
    i0, h0 = pk(R["inicio"]), pk(R["hasta"])
    periodo = f"{MESES[i0[1]]} {i0[0]} – {MESES[h0[1]]} {h0[0]}"
    s = [Paragraph("Informe de Generación vs Consumo", ST["t"]),
         Paragraph(f"{nombre} · Período: {periodo} · Fecha: {hoy:%d/%m/%Y}", ST["s"]), Spacer(1, 8)]

    s += [Paragraph("Resumen", ST["h"])] + parrafos(cfg.get("resumen"))

    s.append(Paragraph("Datos del cliente y del sistema", ST["h"]))
    datos = [["Dato", "Valor"]] + [list(x) for x in cfg.get("datos_cliente", [])]
    claves = {x[0] for x in datos}
    for dato, valor in (("Potencia instalada", f"{R['kwp']:,.2f} kWp"),
                        ("Generación anual esperada", f"{n(R['anual_esperado'])} kWh/año ({R['rendimiento']:,.0f} kWh/kWp)"),
                        ("Período analizado", periodo[0].upper() + periodo[1:])):
        if dato not in claves:
            datos.append([dato, valor])
    s.append(tabla(datos, [A * 0.32, A * 0.68], izq=2))

    # indicadores
    a, c, p1 = R["actual"], R["comparacion"], R["primer_anio"]
    ma = f"{MC[act[0][1]]}–{MC[act[-1][1]]} {a['anio']}" if act else str(a["anio"])
    ind = [["Indicador", "Valor", "Lectura"]]
    if p1 and p1["anio"] != a["anio"]:
        ind.append([f"Generación año {p1['anio']}", f"{n(p1['gen'])} kWh", f"{pct(p1['pct_esperado'], False)} de lo esperado"])
    ind.append([f"Generación {ma}", f"{n(a['gen'])} kWh", f"{pct(a['pct_esperado'], False)} de lo esperado"])
    if R["rend_ultimos_12_kwh_kwp"] and len(ok) >= 12:
        ind.append(["Rendimiento últimos 12 meses", f"{n(R['rend_ultimos_12_kwh_kwp'])} kWh/kWp",
                    f"vs. {R['rendimiento']:,.0f} esperados"])
    if c:
        ind.append([f"Variación generación {c['meses']} ({a['anio']} vs {c['anio_base']})", pct(c["var_gen"]), ""])
        if "var_cons" in c:
            ind.append([f"Variación consumo {c['meses']} ({a['anio']} vs {c['anio_base']})", pct(c["var_cons"]), ""])
    if R["medidor"] and a.get("cons"):
        ind.append([f"Consumo {ma}", f"{n(a['cons'])} kWh", f"promedio {n(a['cons'] / a['meses'])} kWh/mes"])
        ex = a["excedente"]
        ind.append(["Cobertura del consumo", pct(a["cob"], False),
                    f"{'excedente' if ex >= 0 else 'déficit'} de {n(abs(ex))} kWh"])
    if R["autoconsumo"] and a.get("auto") is not None and a.get("cons"):
        ind.append(["Solar consumida directamente", f"{n(a['auto'])} kWh", f"{pct(a['auto'] / a['cons'], False)} del consumo"])
        ind.append(["Energía inyectada a la red", f"{n(a['iny'])} kWh", f"{pct(a['iny'] / a['gen'], False)} de lo generado"])
    tn = R["medicion_neta_total"]
    if tn and "ahorro" in tn:
        ind.append([f"Ahorro estimado {ma}", rd(tn["ahorro"]), f"factura {rd(tn['sin_fv'])} → {rd(tn['con_fv'])}"])
    lect = cfg.get("indicadores_lectura") or {}
    for fila in ind[1:]:
        if fila[0] in lect:
            fila[2] = lect[fila[0]]
    s += [Paragraph(f"Indicadores principales", ST["h"]), tabla(ind, [A * 0.42, A * 0.24, A * 0.34])]

    # gráfico mensual
    s.append(KeepTogether([Paragraph("Generación vs consumo mensual" if R["medidor"] else "Generación mensual", ST["h"])]
                          + parrafos(cfg.get("texto_grafico")) + [graf_mensual(A)]))

    # resumen por año (varios años) o real vs esperada (un solo año)
    if len(R["anios"]) > 2 or (len(R["anios"]) == 2 and len(orden) > 14):
        d = [["Año", "Meses", "Generación (kWh)", "Consumo (kWh)", "Cobertura", "% de lo esperado"]]
        for y, v in R["anios"].items():
            d.append([str(y), str(v["meses"]), n(v["gen"]), n(v["cons"]), pct(v["cob"], False),
                      pct(v["pct_esperado"], False)])
        s.append(KeepTogether([Paragraph("Resumen por año", ST["h"]), tabla(d, [A * 0.12, A * 0.1] + [A * 0.195] * 4),
                               Spacer(1, 3), Paragraph(
            "Cobertura = generación ÷ consumo. % de lo esperado según los meses con datos de cada año."
            + (f" El último año incluye {MESES[1]} a {MESES[h0[1]]}." if h0[1] < 12 else ""), ST["nota"])]))
    else:
        d = [["Mes", "Generación (kWh)", "Esperada (kWh)", "% esperado", "Consumo (kWh)", "Cobertura"]]
        ks = act or ok
        for k in ks:
            v = D[k]
            d.append([etq(k), n(v["gen"]), n(v["esp"]), pct(v["gen"] / v["esp"], False), n(v["cons"]),
                      pct(v["gen"] / v["cons"] if v["cons"] else None, False)])
        g, e = sum(D[k]["gen"] for k in ks), sum(D[k]["esp"] for k in ks)
        cc = sum(D[k]["cons"] or 0 for k in ks)
        d.append(["Total", n(g), n(e), pct(g / e, False), n(cc), pct(g / cc if cc else None, False)])
        s.append(KeepTogether([Paragraph("Generación real vs esperada", ST["h"]),
                               tabla(d, [A * 0.12] + [A * 0.176] * 5, total=True), Spacer(1, 3),
                               Paragraph(f"Esperada = {n(R['anual_esperado'])} kWh/año repartidos según la distribución "
                                         "mensual típica de radiación usada por Éfika. Cobertura = generación ÷ consumo.",
                                         ST["nota"])]))

    # meses bajos (opcional, si informe.json trae texto)
    if cfg.get("texto_meses_bajos") and R["meses_bajos"]:
        d = [["Mes", "Generación (kWh)", "Esperada (kWh)", "% esperado"]]
        for b in R["meses_bajos"]:
            d.append([b["mes"], n(b["gen"]), n(b["esp"]), pct(b["pct"], False)])
        s.append(KeepTogether([Paragraph(cfg.get("titulo_meses_bajos", "Meses con generación baja"), ST["h"])]
                              + parrafos(cfg["texto_meses_bajos"]) + [tabla(d, [A * 0.25] * 4)]))

    # origen de la energía
    if R["autoconsumo"] and act:
        s.append(KeepTogether([Paragraph("¿De dónde viene la energía consumida?", ST["h"])]
                              + parrafos(cfg.get("texto_origen")) + [graf_origen(A)]))

    # medición neta / factura
    if R["medicion_neta"]:
        con_t = R["_tarifa"] is not None
        bl = [Paragraph(f"Medición neta{' e impacto en la factura' if con_t else ''} ({ma})", ST["h"])]
        bl += parrafos(cfg.get("texto_medicion_neta") or [
            "La distribuidora factura la diferencia entre el consumo y la generación de cada mes. Cuando la "
            "generación es mayor, el sobrante se guarda como crédito para los meses siguientes."])
        if con_t:
            d = [["Mes", "Consumo (kWh)", "Gen. (kWh)", "kWh facturados", "Factura sin FV", "Factura con FV", "Ahorro"]]
            for f in R["medicion_neta"]:
                d.append([f["mes"], n(f["cons"]), n(f["gen"]), n(f["fac"]), rd(f["sin_fv"]), rd(f["con_fv"]),
                          rd(f["sin_fv"] - f["con_fv"])])
            d.append(["Total", n(a["cons"]), n(a["gen"]), n(tn["kwh_fac"]), rd(tn["sin_fv"]), rd(tn["con_fv"]),
                      rd(tn["ahorro"])])
            bl.append(tabla(d, [A * 0.1, A * 0.14, A * 0.12, A * 0.14, A * 0.17, A * 0.17, A * 0.16], total=True))
            nota = (f"Estimado con la tarifa {cfg['tarifa']} ({R['tarifa']}). Se asume crédito acumulado en cero al "
                    f"iniciar {a['anio']} por el cierre anual de medición neta. Los montos reales pueden variar; validar "
                    "contra las facturas de la distribuidora.")
        else:
            d = [["Mes", "Consumo (kWh)", "Generación (kWh)", "Neto (kWh)", "kWh a facturar", "Crédito acumulado"]]
            for f in R["medicion_neta"]:
                d.append([f["mes"], n(f["cons"]), n(f["gen"]), f"{f['neto']:+,.0f}", n(f["fac"]), n(f["credito"])])
            d.append(["Total", n(a["cons"]), n(a["gen"]), f"{a['cons'] - a['gen']:+,.0f}", n(tn["kwh_fac"]),
                      n(tn["credito_final"])])
            bl.append(tabla(d, [A * 0.12] + [A * 0.176] * 5, total=True))
            nota = (f"Neto = consumo − generación (negativo = sobrante del mes). Se asume crédito en cero al iniciar "
                    f"{a['anio']} por el cierre anual de medición neta. Validar contra las facturas de la distribuidora.")
        bl += [Spacer(1, 3), Paragraph(cfg.get("nota_medicion_neta") or nota, ST["nota"])]
        s.append(KeepTogether(bl))

    # tabla completa
    d = [["Mes", "Generación (kWh)", "Consumo (kWh)", "Inyectado (kWh)", "Diferencia (kWh)", "Nota"]]
    for k in orden:
        v = D[k]
        d.append([etq(k), n(v["gen"]), n(v["cons"]), n(v["iny"]),
                  f"{v['gen'] - v['cons']:+,.0f}" if v["cons"] is not None else "—", inc.get(k, "")])
    s += [Paragraph("Tabla de datos completa", ST["h"]),
          tabla(d, [A * 0.1, A * 0.15, A * 0.15, A * 0.15, A * 0.15, A * 0.30], nota_izq=True), Spacer(1, 3),
          Paragraph(cfg.get("nota_tabla") or (
              f"Datos de la plataforma {cfg.get('plataforma', 'de monitoreo')}. Diferencia = generación − consumo; "
              "positivo = excedente neto del mes. Inyectado = energía solar enviada a la red."), ST["nota"])]

    if cfg.get("observaciones"):
        s += [Paragraph("Observaciones", ST["h"])] + vinetas(cfg["observaciones"])
    if cfg.get("conclusiones"):
        s += [Paragraph("Conclusiones", ST["h"])] + vinetas(cfg["conclusiones"])
    bl = []
    if cfg.get("recomendaciones"):
        bl = [Paragraph("Recomendaciones", ST["h"])] + vinetas(cfg["recomendaciones"])
    bl += [Spacer(1, 30),
           Table([["______________________________", "______________________________"],
                  ["Ing. José Jiménez", "Ing. Fátima Jiménez"],
                  ["Gerente de Proyectos · 809.972.6625", "Gerente Comercial · 809.924.4525"]],
                 colWidths=[A / 2, A / 2],
                 style=[("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 9),
                        ("TEXTCOLOR", (0, 0), (-1, -1), AZUL), ("ALIGN", (0, 0), (-1, -1), "CENTER")])]
    s.append(KeepTogether(bl))
    doc.build(s, onFirstPage=marco, onLaterPages=marco)

    # vista previa
    vp = os.path.join(carpeta, "vista_previa")
    os.makedirs(vp, exist_ok=True)
    for f in glob.glob(os.path.join(vp, "pagina-*.png")):
        os.remove(f)
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-r", "80", "-png", salida, os.path.join(vp, "pagina")], check=False)
    return salida


def publico(R):
    def r(o):
        if isinstance(o, float):
            return round(o, 3) if abs(o) < 10 else round(o, 1)
        if isinstance(o, dict):
            return {str(k): r(v) for k, v in o.items()}
        if isinstance(o, list):
            return [r(v) for v in o]
        return o
    return r({k: v for k, v in R.items() if not k.startswith("_")})


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("analizar", "pdf"):
        sys.exit(__doc__)
    carpeta = sys.argv[2]
    cfg, D = cargar(carpeta)
    R = calcular(cfg, D)
    if sys.argv[1] == "analizar":
        print(json.dumps(publico(R), ensure_ascii=False, indent=1))
    else:
        print(pdf(carpeta, cfg, R))


if __name__ == "__main__":
    main()
