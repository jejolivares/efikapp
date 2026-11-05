# -*- coding: utf-8 -*-
"""Informe de Generación vs Consumo - Res. Luis López (Arroyo Hondo), NIC 8081412.

Datos: datos.csv descargado de Huawei FusionSolar (la5.fusionsolar.huawei.com) con
programa/informes_clientes.py. Consumo facturado Edenorte 2024-2025: hoja "Clientes FV.xlsx".
Uso: python generar_informe.py
"""
import csv
import datetime as dt
import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "Informe_Gen_vs_Consumo_Res_Luis_Lopez.pdf")
HOY = dt.date(2026, 11, 5)
HASTA = (2026, 10)

KWP = 9.56
REND = 1500
ANUAL_ESP = KWP * REND                     # 14,340 kWh/año
INCOMPLETOS = {(2021, 12): "Primer mes, parcial",
               (2025, 6): "Datos incompletos"}
# kWh facturados por Edenorte (hoja Clientes FV) para validar el modelo
FACT_EDE = {(2024, m): v for m, v in zip(range(1, 13), (243, 105, 135, 183, 358, 562, 432, 435, 326, 444, 753, 501))}
FACT_EDE.update({(2025, 1): 454, (2025, 2): 96, (2025, 3): 134, (2025, 4): 69})

MC = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]

# ------------------------------------------------------------------ datos
D = {}
with open(os.path.join(BASE, "datos.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(l for l in f if not l.startswith("#")):
        y, m = map(int, r["mes"].split("-"))
        if r["generacion_kwh"] and (y, m) <= HASTA:
            D[(y, m)] = {"gen": float(r["generacion_kwh"]), "cons": float(r["consumo_kwh"]),
                         "iny": float(r["inyectado_kwh"])}
MESES_ORD = sorted(D)


def ok(k):
    return k in D and k not in INCOMPLETOS


def tarifa(kwh):
    kwh = max(kwh, 0)
    if kwh > 700:
        return kwh * 14.04 + 126.81
    t, a = 0.0, 0
    for lim, pr in ((200, 5.97), (300, 8.51), (700, 13.83)):
        if kwh > a:
            t += (min(kwh, lim) - a) * pr
        a = lim
    return t + 126.81


def facturar(anio, hasta_mes=12):
    """kWh facturados con medición neta (crédito se reinicia en enero)."""
    cred, filas = 0.0, []
    for m in range(1, hasta_mes + 1):
        k = (anio, m)
        g, c = D[k]["gen"], D[k]["cons"]
        neto = c - g
        if neto <= 0:
            cred += -neto
            fac = 0.0
        else:
            u = min(cred, neto)
            cred -= u
            fac = neto - u
        filas.append((k, c, g, fac, cred, tarifa(c), tarifa(fac)))
    return filas


def n(v, d=0):
    return "—" if v is None else f"{v:,.{d}f}"


def rd(v):
    return f"RD${v:,.0f}"


def pct(v, s=True):
    return f"{v * 100:+.1f}%" if s else f"{v * 100:.1f}%"


def suma(campo, anio, meses=range(1, 13)):
    return sum(D[(anio, m)][campo] for m in meses if (anio, m) in D)


# --------------------------------------------------------------- análisis
anual = {}
for y in range(2022, 2027):
    ms = [m for m in range(1, 13) if (y, m) in D]
    g, c = suma("gen", y), suma("cons", y)
    anual[y] = {"meses": len(ms), "gen": g, "cons": c, "cob": g / c,
                "esp": ANUAL_ESP * len(ms) / 12}
g1 = anual[2022]["gen"]
rend1 = g1 / KWP
EO = range(1, 11)                                             # enero-octubre
gen22, gen26 = suma("gen", 2022, EO), suma("gen", 2026, EO)
con22, con26 = suma("cons", 2022, EO), suma("cons", 2026, EO)
var_gen, var_con = gen26 / gen22 - 1, con26 / con22 - 1
deficit26 = con26 - gen26
fac26 = facturar(2026, 10)
sin26, con_fv26 = sum(f[5] for f in fac26), sum(f[6] for f in fac26)
kwh_fac26 = sum(f[3] for f in fac26)
fac24 = facturar(2024)
modelo24 = sum(f[3] for f in fac24)
ede24 = sum(FACT_EDE[(2024, m)] for m in range(1, 13))
bajos = [(2024, 10), (2024, 11), (2024, 12), (2025, 7), (2025, 9)]
kwp_ampl = deficit26 / 10 * 12 / REND

# ----------------------------------------------------------------- estilo
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


def grafico(A):
    fig, ax = plt.subplots(figsize=(7.5, 3.1))
    x = list(range(len(MESES_ORD)))
    ax.bar(x, [D[k]["gen"] for k in MESES_ORD], 0.75,
           color=["#b8bfca" if k in INCOMPLETOS else "#2e9e4f" for k in MESES_ORD], label="Generación solar")
    ax.plot(x, [D[k]["cons"] if ok(k) else float("nan") for k in MESES_ORD], color="#c0392b", lw=1.6,
            marker="o", ms=2, label="Consumo de la vivienda")
    ax.axhline(ANUAL_ESP / 12, ls="--", color="#555", lw=1, label="Generación esperada (promedio)")
    paso = 3
    ax.set_xticks(x[::paso])
    ax.set_xticklabels([f"{MC[m]}-{y % 100}" for y, m in MESES_ORD][::paso], rotation=90, fontsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="y", labelsize=7)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("kWh", fontsize=8)
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.15), frameon=False)
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
    w, h = fig.get_size_inches()
    plt.close(fig)
    b.seek(0)
    return Image(b, width=A, height=A * h / w)


def bullets(s, items):
    for t in items:
        s.append(Paragraph(t, ST["b"], bulletText="•"))


# -------------------------------------------------------------------- PDF
def main():
    doc = SimpleDocTemplate(SALIDA, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                            title="Informe de Generación vs Consumo - Res. Luis López")
    A = doc.width
    s = [Paragraph("Informe de Generación vs Consumo", ST["t"]),
         Paragraph(f"Res. Luis López (Arroyo Hondo) · Período: diciembre 2021 – octubre 2026 · "
                   f"Fecha: {HOY:%d/%m/%Y}", ST["s"]), Spacer(1, 8)]

    s.append(Paragraph("Resumen", ST["h"]))
    s.append(Paragraph(
        "El sistema fotovoltaico funciona correctamente y en 2026 produce lo mismo que en su primer año. "
        "El pago de energía se debe al aumento del consumo de la vivienda, no a una baja de generación.", ST["p"]))
    s.append(Paragraph(
        f"En su primer año completo (2022) el sistema generó {n(g1)} kWh, un {pct(g1 / ANUAL_ESP, False)} de los "
        f"{n(ANUAL_ESP)} kWh prometidos, y produjo más energía de la que consumió la casa. De enero a octubre, "
        f"la generación de 2026 fue {pct(var_gen)} respecto a 2022, mientras el consumo subió {pct(var_con)} "
        f"({n(con22)} → {n(con26)} kWh).", ST["p"]))
    s.append(Paragraph(
        f"Aun con ese aumento, el sistema evitó un estimado de {rd(sin26 - con_fv26)} en facturas de energía de "
        f"enero a octubre 2026: sin él, la factura habría sido de unos {rd(sin26)}, frente a {rd(con_fv26)} con "
        f"el sistema.", ST["p"]))

    s.append(Paragraph("Datos del cliente y del sistema", ST["h"]))
    d = [["Dato", "Valor"],
         ["Cliente", "Res. Luis López (Arroyo Hondo) · titular: Luis Alberto López Veras"],
         ["NIC", "8081412"],
         ["Distribuidora", "Edenorte · Tarifa BTS-1 (residencial)"],
         ["Potencia instalada", f"{KWP} kWp"],
         ["Módulos", "21 paneles Q-Cells de 455 Wp"],
         ["Inversores", "2 inversores Huawei de 5 kW"],
         ["Puesta en marcha", "Septiembre 2021 (monitoreo completo desde enero 2022)"],
         ["Generación anual prometida", f"{n(ANUAL_ESP)} kWh/año ({REND:,} kWh/kWp)"],
         ["Período analizado", "Diciembre 2021 – Octubre 2026"]]
    s.append(tabla(d, [A * 0.32, A * 0.68], izq=2))

    s.append(Paragraph("Indicadores principales", ST["h"]))
    a24, a25 = anual[2024], anual[2025]
    d = [["Indicador", "Valor", "Lectura"],
         ["Generación año 1 (2022)", f"{n(g1)} kWh", f"{pct(g1 / ANUAL_ESP, False)} de lo prometido"],
         ["Rendimiento específico año 1", f"{n(rend1)} kWh/kWp", f"vs. {REND:,} esperados"],
         ["Cobertura del consumo año 1", pct(anual[2022]["cob"], False), "generó más de lo que consumió"],
         ["Generación 2024 / 2025", f"{n(a24['gen'])} / {n(a25['gen'])} kWh",
          f"{pct(a24['gen'] / ANUAL_ESP, False)} / {pct(a25['gen'] / ANUAL_ESP, False)} de lo prometido"],
         ["Variación generación ene–oct (2026 vs 2022)", pct(var_gen), "sistema recuperado y estable"],
         ["Variación consumo ene–oct (2026 vs 2022)", pct(var_con), "la casa consume más"],
         ["Cobertura del consumo ene–oct 2026", pct(gen26 / con26, False), f"déficit de {n(deficit26)} kWh"]]
    s.append(tabla(d, [A * 0.42, A * 0.24, A * 0.34]))

    s.append(KeepTogether([
        Paragraph("Generación vs consumo mensual", ST["h"]),
        Paragraph("La generación se mantiene alrededor de lo esperado casi todo el período. El consumo, en cambio, "
                  "pasó de unos 1,100 kWh/mes en 2022 a más de 1,800 kWh en julio y agosto de 2026. La barra gris "
                  "de junio 2025 tiene datos incompletos y se excluye de las comparaciones.", ST["p"]),
        grafico(A)]))

    d = [["Año", "Meses", "Generación (kWh)", "Consumo (kWh)", "Cobertura", "% de lo prometido"]]
    for y, a in anual.items():
        d.append([str(y), str(a["meses"]), n(a["gen"]), n(a["cons"]), pct(a["cob"], False),
                  pct(a["gen"] / a["esp"], False)])
    s.append(KeepTogether([Paragraph("Resumen por año", ST["h"]), tabla(d, [A * 0.12, A * 0.1] + [A * 0.195] * 4),
                           Spacer(1, 3),
                           Paragraph("Cobertura = generación ÷ consumo. 2026 incluye enero a octubre; 2025 incluye "
                                     "junio con datos incompletos.", ST["nota"])]))

    bl = [Paragraph("Baja de generación en 2024–2025", ST["h"]),
          Paragraph("En algunos meses de finales de 2024 y de 2025 el sistema generó bastante menos que en los "
                    "mismos meses de 2022. Desde enero 2026 la generación volvió a los niveles del primer año, lo que "
                    "indica una causa temporal (suciedad en los paneles, sombra o un inversor fuera de servicio parte "
                    "del tiempo) y no una degradación de los equipos.", ST["p"])]
    d = [["Mes", "2022 (kWh)", "Mes bajo (kWh)", "Variación", "2026 (kWh)"]]
    for y, m in bajos:
        d.append([f"{MC[m]}-{y % 100}", n(D[(2022, m)]["gen"]), n(D[(y, m)]["gen"]),
                  pct(D[(y, m)]["gen"] / D[(2022, m)]["gen"] - 1),
                  n(D[(2026, m)]["gen"]) if (2026, m) in D else "—"])
    bl.append(tabla(d, [A * 0.2] * 5))
    s.append(KeepTogether(bl))

    bl = [Paragraph("Impacto en la factura (enero – octubre 2026)", ST["h"]),
          Paragraph(f"Cuando la casa consume más de lo que genera, la diferencia se factura. En 2026 se facturaron "
                    f"unos {n(kwh_fac26)} kWh. Si un mes pasa de 700 kWh netos, todo se cobra al bloque más alto de "
                    f"la tarifa BTS-1 (RD$14.04/kWh); con el sistema, la casa se mantiene casi siempre por debajo de "
                    f"ese umbral.", ST["p"])]
    d = [["Mes", "Consumo (kWh)", "Gen. (kWh)", "kWh facturados", "Factura sin FV", "Factura con FV", "Ahorro"]]
    for k, c, g, fac, cred, sin, con in fac26:
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(c), n(g), n(fac), rd(sin), rd(con), rd(sin - con)])
    d.append(["Total", n(con26), n(gen26), n(kwh_fac26), rd(sin26), rd(con_fv26), rd(sin26 - con_fv26)])
    bl.append(tabla(d, [A * 0.1, A * 0.14, A * 0.12, A * 0.14, A * 0.17, A * 0.17, A * 0.16], total=True))
    bl.append(Spacer(1, 3))
    bl.append(Paragraph(
        "Estimado con la tarifa BTS-1 de Edenorte vigente en 2026 (0–200 kWh RD$5.97; 201–300 RD$8.51; 301–700 "
        "RD$13.83; más de 700 kWh todos a RD$14.04) y cargo fijo de RD$126.81. Se asume crédito acumulado en cero "
        "al iniciar 2026 por el cierre anual de medición neta. Los montos reales pueden variar; validar contra las "
        f"facturas de Edenorte. Como referencia, para 2024 este cálculo estima {n(modelo24)} kWh facturados y "
        f"Edenorte facturó {n(ede24)} kWh.", ST["nota"]))
    s.append(KeepTogether(bl))

    bl = [Paragraph("Tabla de datos completa", ST["h"])]
    d = [["Mes", "Generación (kWh)", "Consumo (kWh)", "Inyectado (kWh)", "Diferencia (kWh)", "Nota"]]
    for k in MESES_ORD:
        v = D[k]
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(v["gen"]), n(v["cons"]), n(v["iny"]),
                  f"{v['gen'] - v['cons']:+,.0f}", INCOMPLETOS.get(k, "")])
    bl.append(tabla(d, [A * 0.1, A * 0.15, A * 0.15, A * 0.15, A * 0.15, A * 0.30]))
    bl.append(Spacer(1, 3))
    bl.append(Paragraph("Datos de la plataforma Huawei FusionSolar (consumo total de la vivienda medido por el smart "
                        "meter). Diferencia = generación − consumo; positivo = excedente neto del mes. Inyectado = "
                        "energía enviada a la red en las horas en que la casa no la usó.", ST["nota"]))
    s.append(bl[0]); s.append(bl[1]); s.append(bl[2]); s.append(bl[3])

    s.append(Paragraph("Observaciones", ST["h"]))
    bullets(s, [
        f"El consumo de la vivienda aumentó de {n(anual[2022]['cons'])} kWh en 2022 a {n(anual[2024]['cons'])} kWh "
        f"en 2024; en 2026 sigue alto, sobre todo de mayo a septiembre (meses de más uso de aire acondicionado).",
        "Entre octubre y diciembre 2024 y en julio y septiembre 2025 la generación bajó entre 23% y 34% frente a "
        "2022. En 2026 se recuperó por completo.",
        "Junio 2025 muestra un consumo de solo 339 kWh y generación baja, lo que apunta a una falla de monitoreo; "
        "se excluye de las comparaciones.",
        "La plataforma registra datos desde diciembre 2021, aunque el medidor de medición neta se instaló en "
        "septiembre 2021.",
    ])

    s.append(Paragraph("Conclusiones", ST["h"]))
    bullets(s, [
        f"El sistema cumplió y superó la generación prometida en sus primeros dos años "
        f"({pct(g1 / ANUAL_ESP, False)} en 2022 y {pct(anual[2023]['gen'] / ANUAL_ESP, False)} en 2023).",
        "La baja de 2024–2025 fue temporal: en 2026 el sistema genera lo mismo que en su primer año.",
        f"El sistema fue dimensionado para el consumo de 2021–2022; hoy la casa consume cerca de "
        f"{pct(var_con, False).lstrip('+')} más.",
        f"El sistema sigue generando ahorros importantes: un estimado de {rd(sin26 - con_fv26)} de enero a octubre 2026.",
    ])

    bl = [Paragraph("Recomendaciones", ST["h"])]
    for t in [
        "Revisar en FusionSolar las alarmas de los dos inversores de octubre–diciembre 2024 y de mediados de 2025 "
        "para identificar la causa de la baja, y programar limpieza de paneles al menos dos veces al año.",
        "Gestionar el consumo en los meses de calor: termostatos o temporizadores en los aires acondicionados y "
        "revisar equipos de alto consumo.",
        f"Evaluar una ampliación de aproximadamente {kwp_ampl:.1f} kWp (unos {round(kwp_ampl * 1000 / 580)} módulos de "
        f"580 Wp) para cubrir el déficit observado en 2026, sujeta a validación técnica de la capacidad de los "
        f"inversores actuales (2 × 5 kW).",
        "Revisar las facturas de Edenorte de 2025 y 2026 junto al cliente para confirmar los créditos de medición "
        "neta aplicados.",
    ]:
        bl.append(Paragraph(t, ST["b"], bulletText="•"))
    bl += [Spacer(1, 30),
           Table([["______________________________", "______________________________"],
                  ["Ing. José Jiménez", "Ing. Fátima Jiménez"],
                  ["Gerente de Proyectos · 809.972.6625", "Gerente Comercial · 809.924.4525"]],
                 colWidths=[A / 2, A / 2],
                 style=[("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 9),
                        ("TEXTCOLOR", (0, 0), (-1, -1), AZUL), ("ALIGN", (0, 0), (-1, -1), "CENTER")])]
    s.append(KeepTogether(bl))
    doc.build(s, onFirstPage=marco, onLaterPages=marco)
    print(SALIDA)


if __name__ == "__main__":
    main()
