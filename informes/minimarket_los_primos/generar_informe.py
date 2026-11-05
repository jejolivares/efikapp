# -*- coding: utf-8 -*-
"""Informe de Generación vs Consumo - Minimarket Los Primos (Vista Linda, Santiago), NIC 6689047.

Datos: datos.csv descargado de Huawei FusionSolar (la5.fusionsolar.huawei.com) con
programa/informes_clientes.py. kWh facturados por Edenorte: hoja "Clientes FV Nuevo" (Hoja 2),
reubicados al mes de consumo (la factura de un mes corresponde al consumo del mes anterior).
Tarifa BTS-2 Edenorte: factura BTS-2 de junio 2024 (cargo fijo RD$127.18 + RD$14.38/kWh).
Uso: python generar_informe.py
"""
import csv
import datetime as dt
import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

BASE = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE, "Informe_Gen_vs_Consumo_Minimarket_Los_Primos.pdf")
HOY = dt.date(2026, 11, 5)
HASTA = (2026, 9)
ULT = 8                                    # último mes completo de 2026 (agosto)

KWP = 23.21
REND = 1500
ANUAL_ESP = KWP * REND                     # 34,815 kWh/año
INCOMPLETOS = {(2021, 12): "Inicio de monitoreo, parcial",
               (2022, 1): "Puesta en marcha, parcial",
               (2023, 1): "Datos incompletos",
               (2024, 11): "Datos incompletos",
               (2026, 9): "Monitoreo interrumpido a mitad de mes"}
SIN_DATOS = [(2023, 2)]                    # octubre 2026 tampoco tiene datos
# Tarifa BTS-2 Edenorte (sin tramos)
FIJO, PRECIO = 127.18, 14.38
# kWh facturados por Edenorte por mes de consumo (hoja Clientes FV Nuevo)
FACT_EDE = {(2024, m): v for m, v in zip(range(1, 13),
                                         (725, 289, 343, 270, 491, 400, 628, 181, 433, 844, 1366, 1553))}

MC = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

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
    return max(kwh, 0) * PRECIO + FIJO


def facturar(anio, hasta_mes=12):
    """kWh facturados con medición neta (crédito se reinicia en enero)."""
    cred, filas = 0.0, []
    for m in range(1, hasta_mes + 1):
        k = (anio, m)
        if not ok(k):
            continue
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
    return sum(D[(anio, m)][campo] for m in meses if ok((anio, m)))


# --------------------------------------------------------------- análisis
anual = {}
for y in range(2022, 2027):
    ms = [m for m in range(1, 13) if ok((y, m))]
    g, c = suma("gen", y), suma("cons", y)
    anual[y] = {"meses": len(ms), "gen": g, "cons": c, "cob": g / c, "esp": ANUAL_ESP * len(ms) / 12}
a1 = anual[2022]                                               # feb-dic 2022 (11 meses)
g1 = a1["gen"]
rend1 = g1 / a1["meses"] * 12 / KWP
cumple1 = g1 / a1["esp"]
FA = range(2, ULT + 1)                                         # febrero-agosto (comparable con 2022)
gen22, gen26 = suma("gen", 2022, FA), suma("gen", 2026, FA)
con22, con26 = suma("cons", 2022, FA), suma("cons", 2026, FA)
var_gen, var_con = gen26 / gen22 - 1, con26 / con22 - 1
EA = range(1, ULT + 1)                                         # enero-agosto 2026
g26, c26 = suma("gen", 2026, EA), suma("cons", 2026, EA)
deficit26 = c26 - g26
fac26 = facturar(2026, ULT)
sin26, con_fv26 = sum(f[5] for f in fac26), sum(f[6] for f in fac26)
kwh_fac26 = sum(f[3] for f in fac26)
ahorro26 = sin26 - con_fv26
fac24 = facturar(2024)
meses24 = [f[0] for f in fac24]
modelo24 = sum(f[3] for f in fac24)
ede24 = sum(FACT_EDE[k] for k in meses24)
bajos = [(2023, 4), (2024, 10), (2024, 12), (2025, 4)]
var_bajos = [D[k]["gen"] / D[(2022, k[1])]["gen"] - 1 for k in bajos]
kwp_ampl = deficit26 / ULT * 12 / REND
anios_ok = [y for y in anual if y < 2026]

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
            marker="o", ms=2, label="Consumo del negocio")
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
    h, l = ax.get_legend_handles_labels()
    h[l.index("Generación solar")] = matplotlib.patches.Patch(color="#2e9e4f")
    ax.legend(h, l, fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.15), frameon=False)
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
                            title="Informe de Generación vs Consumo - Minimarket Los Primos")
    A = doc.width
    s = [Paragraph("Informe de Generación vs Consumo", ST["t"]),
         Paragraph(f"Minimarket Los Primos (Vista Linda, Santiago) · Período: diciembre 2021 – septiembre 2026 · "
                   f"Fecha: {HOY:%d/%m/%Y}", ST["s"]), Spacer(1, 8)]

    s.append(Paragraph("Resumen", ST["h"]))
    s.append(Paragraph(
        "El sistema fotovoltaico funciona correctamente: de enero a agosto 2026 generó lo prometido y prácticamente "
        "lo mismo que en su primer año. El consumo del negocio se ha mantenido estable, y el sistema cubre cerca del "
        "90% de la energía que usa el minimarket.", ST["p"]))
    s.append(Paragraph(
        f"En su primer año de operación (febrero a diciembre 2022) el sistema generó {n(g1)} kWh, un "
        f"{pct(cumple1, False)} de lo prometido para esos meses. De febrero a agosto, la generación de 2026 fue "
        f"{pct(var_gen)} respecto a 2022 y el consumo {pct(var_con)} ({n(con22)} → {n(con26)} kWh).", ST["p"]))
    s.append(Paragraph(
        f"De enero a agosto 2026 el sistema evitó un estimado de <b>{rd(ahorro26)}</b> en facturas de energía: sin "
        f"él, la factura habría sido de unos {rd(sin26)}, frente a {rd(con_fv26)} con el sistema.", ST["p"]))
    s.append(Paragraph(
        "<b>Atención:</b> la plataforma dejó de recibir datos a mediados de septiembre 2026 y no hay registros de "
        "octubre. Debe verificarse en sitio que los inversores estén encendidos y conectados a internet.", ST["p"]))

    s.append(Paragraph("Datos del cliente y del sistema", ST["h"]))
    d = [["Dato", "Valor"],
         ["Cliente", "Minimarket Los Primos · contacto: Jonavi Portorreal"],
         ["Ubicación", "Calle Penetración, Vista Linda, Santiago"],
         ["NIC", "6689047"],
         ["Distribuidora", "Edenorte · Tarifa BTS-2 (comercial)"],
         ["Potencia instalada", f"{KWP} kWp"],
         ["Módulos", "51 paneles Q-Cells de 455 Wp"],
         ["Inversores", "3 inversores Huawei de 6 kW"],
         ["Puesta en marcha", "Enero 2022 (monitoreo completo desde febrero 2022)"],
         ["Generación anual prometida", f"{n(ANUAL_ESP)} kWh/año ({REND:,} kWh/kWp)"],
         ["Período analizado", "Diciembre 2021 – Septiembre 2026"]]
    s.append(tabla(d, [A * 0.32, A * 0.68], izq=2))

    s.append(Paragraph("Indicadores principales", ST["h"]))
    a24, a25 = anual[2024], anual[2025]
    d = [["Indicador", "Valor", "Lectura"],
         ["Generación año 1 (feb–dic 2022)", f"{n(g1)} kWh", f"{pct(cumple1, False)} de lo prometido"],
         ["Rendimiento específico año 1", f"{n(rend1)} kWh/kWp", f"vs. {REND:,} esperados"],
         ["Cobertura del consumo año 1", pct(a1["cob"], False), "del consumo del negocio"],
         ["Generación 2024 / 2025", f"{n(a24['gen'])} / {n(a25['gen'])} kWh",
          f"{pct(a24['gen'] / a24['esp'], False)} / {pct(a25['gen'] / a25['esp'], False)} de lo prometido"],
         ["Variación generación feb–ago (2026 vs 2022)", pct(var_gen), "sistema estable"],
         ["Variación consumo feb–ago (2026 vs 2022)", pct(var_con), "consumo estable"],
         ["Cobertura del consumo ene–ago 2026", pct(g26 / c26, False), f"déficit de {n(deficit26)} kWh"]]
    s.append(tabla(d, [A * 0.42, A * 0.24, A * 0.34]))

    s.append(KeepTogether([
        Paragraph("Generación vs consumo mensual", ST["h"]),
        Paragraph("La generación se mantiene alrededor de lo esperado casi todo el período, con la caída habitual de "
                  "noviembre a febrero por menor radiación. El consumo del minimarket se mantiene entre 2,800 y "
                  "3,600 kWh/mes. Las barras grises son meses con datos incompletos y se excluyen de las "
                  "comparaciones.", ST["p"]),
        grafico(A)]))

    d = [["Año", "Meses", "Generación (kWh)", "Consumo (kWh)", "Cobertura", "% de lo prometido"]]
    for y, a in anual.items():
        d.append([str(y), str(a["meses"]), n(a["gen"]), n(a["cons"]), pct(a["cob"], False),
                  pct(a["gen"] / a["esp"], False)])
    s.append(KeepTogether([Paragraph("Resumen por año", ST["h"]), tabla(d, [A * 0.12, A * 0.1] + [A * 0.195] * 4),
                           Spacer(1, 3),
                           Paragraph("Cobertura = generación ÷ consumo. Solo se suman los meses con datos completos "
                                     "(columna Meses); 2022 empieza en febrero, 2023 excluye enero y febrero, 2024 "
                                     "excluye noviembre y 2026 incluye enero a agosto. % de lo prometido se calcula "
                                     "sobre esos mismos meses.", ST["nota"])]))

    bl = [Paragraph("Meses con generación baja", ST["h"]),
          Paragraph("En algunos meses de 2023 a 2025 el sistema generó bastante menos que en el mismo mes de 2022, "
                    "sobre todo de octubre 2024 a abril 2025. En 2026 la generación volvió a los niveles del primer "
                    "año, lo que indica una causa temporal (suciedad en los paneles, sombra o un inversor fuera de "
                    "servicio parte del tiempo) y no una degradación de los equipos.", ST["p"])]
    d = [["Mes", "2022 (kWh)", "Mes bajo (kWh)", "Variación", "2026 (kWh)"]]
    for (y, m), v in zip(bajos, var_bajos):
        d.append([f"{MC[m]}-{y % 100}", n(D[(2022, m)]["gen"]), n(D[(y, m)]["gen"]), pct(v),
                  n(D[(2026, m)]["gen"]) if ok((2026, m)) else "—"])
    bl.append(tabla(d, [A * 0.2] * 5))
    bl.append(Spacer(1, 3))
    bl.append(Paragraph("Octubre y diciembre 2026 todavía no tienen datos.", ST["nota"]))
    s.append(KeepTogether(bl))

    bl = [Paragraph("Impacto en la factura (enero – agosto 2026)", ST["h"]),
          Paragraph(f"El minimarket consume más de lo que genera casi todos los meses, y esa diferencia se factura. "
                    f"De enero a agosto 2026 se facturaron unos {n(kwh_fac26)} kWh. Con la tarifa BTS-2 cada kWh "
                    f"cuesta lo mismo (RD${PRECIO:.2f}), por lo que cada kWh generado por el sistema es un ahorro "
                    f"directo en la factura.", ST["p"])]
    d = [["Mes", "Consumo (kWh)", "Gen. (kWh)", "kWh facturados", "Factura sin FV", "Factura con FV", "Ahorro"]]
    for k, c, g, fac, cred, sin, con in fac26:
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(c), n(g), n(fac), rd(sin), rd(con), rd(sin - con)])
    d.append(["Total", n(c26), n(g26), n(kwh_fac26), rd(sin26), rd(con_fv26), rd(ahorro26)])
    bl.append(tabla(d, [A * 0.1, A * 0.14, A * 0.12, A * 0.14, A * 0.17, A * 0.17, A * 0.16], total=True))
    bl.append(Spacer(1, 3))
    bl.append(Paragraph(
        f"Estimado con la tarifa BTS-2 de Edenorte (RD${PRECIO:.2f}/kWh, sin tramos) y cargo fijo de "
        f"RD${FIJO:.2f}, según la factura BTS-2 de Edenorte más reciente disponible (junio 2024). Se asume crédito "
        f"acumulado en cero al iniciar 2026 por el cierre anual de medición neta. Los montos reales pueden variar; "
        f"validar contra las facturas de Edenorte. Como referencia, para 2024 (sin noviembre) este cálculo estima "
        f"{n(modelo24)} kWh facturados y Edenorte facturó {n(ede24)} kWh en esos mismos meses.", ST["nota"]))
    s.append(KeepTogether(bl))

    s.append(Paragraph("Tabla de datos completa", ST["h"]))
    d = [["Mes", "Generación (kWh)", "Consumo (kWh)", "Inyectado (kWh)", "Diferencia (kWh)", "Nota"]]
    for k in sorted(set(MESES_ORD) | set(SIN_DATOS)):
        if k not in D:
            d.append([f"{MC[k[1]]}-{k[0] % 100}", "—", "—", "—", "—", "Sin datos en la plataforma"])
            continue
        v = D[k]
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(v["gen"]), n(v["cons"]), n(v["iny"]),
                  f"{v['gen'] - v['cons']:+,.0f}", INCOMPLETOS.get(k, "")])
    s.append(tabla(d, [A * 0.1, A * 0.15, A * 0.15, A * 0.15, A * 0.15, A * 0.30]))
    s.append(Spacer(1, 3))
    s.append(Paragraph("Datos de la plataforma Huawei FusionSolar (consumo total del negocio medido por el smart "
                       "meter). Diferencia = generación − consumo; positivo = excedente neto del mes. Inyectado = "
                       "energía enviada a la red en las horas en que el negocio no la usó.", ST["nota"]))

    s.append(Paragraph("Observaciones", ST["h"]))
    bullets(s, [
        "La plataforma dejó de reportar a mediados de septiembre 2026 (solo 1,562 kWh registrados, frente a unos "
        "2,900 kWh normales) y no hay datos de octubre 2026. Puede ser una pérdida de conexión a internet del "
        "inversor o un equipo apagado.",
        f"El consumo del minimarket se ha mantenido estable: {n(anual[2022]['cons'] / anual[2022]['meses'])} kWh/mes "
        f"en promedio en 2022 y {n(c26 / ULT)} kWh/mes de enero a agosto 2026. Agosto 2026 fue el mes de mayor "
        f"consumo del período ({n(D[(2026, 8)]['cons'])} kWh).",
        f"Entre octubre 2024 y abril 2025, y en abril 2023, la generación bajó entre "
        f"{-max(var_bajos) * 100:.0f}% y {-min(var_bajos) * 100:.0f}% frente a los mismos meses de 2022. En 2026 se "
        f"recuperó por completo.",
        "Enero 2023, noviembre 2024 y septiembre 2026 muestran generación y consumo bajos a la vez, lo que apunta a "
        "fallas de monitoreo; febrero 2023 no tiene datos. Esos meses se excluyen de las comparaciones.",
    ])

    s.append(Paragraph("Conclusiones", ST["h"]))
    bullets(s, [
        f"El sistema cumplió la generación prometida en su primer año ({pct(cumple1, False)}) y la vuelve a cumplir "
        f"en 2026 ({pct(anual[2026]['gen'] / anual[2026]['esp'], False)} de enero a agosto).",
        f"La baja de 2024–2025 fue temporal ({pct(a24['gen'] / a24['esp'], False)} y "
        f"{pct(a25['gen'] / a25['esp'], False)} de lo prometido): en 2026 el sistema genera lo mismo que en su "
        f"primer año.",
        f"El sistema cubre alrededor del {pct(g26 / c26, False)} del consumo del negocio; el resto se paga a "
        f"Edenorte.",
        f"El sistema sigue generando ahorros importantes: un estimado de {rd(ahorro26)} de enero a agosto 2026.",
    ])

    bl = [Paragraph("Recomendaciones", ST["h"])]
    for t in [
        "<b>Urgente:</b> visitar el sitio para confirmar que los tres inversores están encendidos y restablecer la "
        "conexión con FusionSolar, ya que no hay datos desde mediados de septiembre 2026.",
        "Revisar en FusionSolar las alarmas de los inversores de octubre 2024 a abril 2025 para identificar la "
        "causa de la baja, y programar limpieza de paneles al menos dos veces al año.",
        f"Evaluar una ampliación de aproximadamente {kwp_ampl:.1f} kWp (unos {round(kwp_ampl * 1000 / 580)} módulos "
        f"de 580 Wp) para cubrir el déficit observado en 2026. Los inversores actuales (3 × 6 kW) ya trabajan con "
        f"{KWP} kWp, por lo que la ampliación requeriría un inversor adicional.",
        "Revisar las facturas de Edenorte de 2025 y 2026 junto al cliente para confirmar los créditos de medición "
        "neta aplicados y la tarifa BTS-2 vigente.",
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
