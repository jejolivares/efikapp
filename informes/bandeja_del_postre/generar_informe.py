# -*- coding: utf-8 -*-
"""Informe de Generación vs Consumo - Bandeja del Postre (Santiago), NIC 6077632.

Datos: datos.csv descargado de Huawei FusionSolar (planta "Bandeja del Postre - STI - 34.83")
con programa/informes_clientes.py. Período: diciembre 2025 (puesta en marcha) a octubre 2026.
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
SALIDA = os.path.join(BASE, "Informe_Gen_vs_Consumo_Bandeja_del_Postre.pdf")
HOY = dt.date(2026, 11, 5)
HASTA = (2026, 10)

KWP = 34.80                                # clientes.csv (FusionSolar: 34.83 kWp)
REND = 1500                                # kWh/kWp/año (criterio Efika)
ANUAL_ESP = KWP * REND                     # 52,200 kWh/año
# Distribución mensual de la generación esperada (% del año, hoja de seguimiento Efika)
PCT = {1: 7.69, 2: 7.76, 3: 8.90, 4: 8.93, 5: 8.73, 6: 8.64, 7: 9.30, 8: 9.42,
       9: 8.92, 10: 8.34, 11: 6.87, 12: 6.51}
INCOMPLETOS = {(2025, 12): "Puesta en marcha, mes parcial"}

MC = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# ------------------------------------------------------------------ datos
D = {}
with open(os.path.join(BASE, "datos.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(l for l in f if not l.startswith("#")):
        y, m = map(int, r["mes"].split("-"))
        if r["generacion_kwh"] and (y, m) <= HASTA:
            g, c, i = float(r["generacion_kwh"]), float(r["consumo_kwh"]), float(r["inyectado_kwh"])
            D[(y, m)] = {"gen": g, "cons": c, "iny": i, "auto": g - i, "red": c - (g - i),
                         "esp": ANUAL_ESP * PCT[m] / 100}
MESES_ORD = sorted(D)
COMP = [k for k in MESES_ORD if k not in INCOMPLETOS]        # ene-oct 2026
ESTABLE = [k for k in COMP if k >= (2026, 3)]                 # mar-oct 2026


def tot(campo, ks):
    return sum(D[k][campo] for k in ks)


def n(v, d=0):
    return "—" if v is None else f"{v:,.{d}f}"


def pct(v, s=True):
    return f"{v * 100:+.1f}%" if s else f"{v * 100:.1f}%"


# --------------------------------------------------------------- análisis
gen, cons, iny = tot("gen", COMP), tot("cons", COMP), tot("iny", COMP)
auto, red, esp = tot("auto", COMP), tot("red", COMP), tot("esp", COMP)
cumpl = gen / esp
cob = gen / cons
gen_e, esp_e = tot("gen", ESTABLE), tot("esp", ESTABLE)
rend_anual = gen / KWP * 100 / sum(PCT[k[1]] for k in COMP)   # kWh/kWp/año equivalente
excedente = gen - cons
mejor = max(COMP, key=lambda k: D[k]["gen"])

# Medición neta mes a mes (crédito se reinicia en enero)
NETO, cred = [], 0.0
for k in COMP:
    neto = D[k]["cons"] - D[k]["gen"]
    if neto <= 0:
        cred += -neto
        fac = 0.0
    else:
        u = min(cred, neto)
        cred -= u
        fac = neto - u
    NETO.append((k, neto, fac, cred))
kwh_fac = sum(x[2] for x in NETO)
cred_final = NETO[-1][3]

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


def _fmt(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="y", labelsize=7)
    ax.tick_params(axis="x", labelsize=7.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylabel("kWh", fontsize=8)


def _img(fig, A):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
    w, h = fig.get_size_inches()
    plt.close(fig)
    b.seek(0)
    return Image(b, width=A, height=A * h / w)


def grafico(A):
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    x = list(range(len(MESES_ORD)))
    ax.bar(x, [D[k]["gen"] for k in MESES_ORD], 0.65,
           color=["#b8bfca" if k in INCOMPLETOS else "#2e9e4f" for k in MESES_ORD], label="Generación solar")
    ax.plot(x, [D[k]["cons"] for k in MESES_ORD], color="#c0392b", lw=1.8, marker="o", ms=3,
            label="Consumo del negocio")
    ax.plot(x, [D[k]["esp"] for k in MESES_ORD], ls="--", color="#555", lw=1, label="Generación esperada")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{MC[m]}-{y % 100}" for y, m in MESES_ORD])
    _fmt(ax)
    ax.legend(fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.15), frameon=False)
    return _img(fig, A)


def grafico_origen(A):
    """Origen de la energía consumida: solar directa vs red."""
    fig, ax = plt.subplots(figsize=(7.5, 2.6))
    x = list(range(len(COMP)))
    a = [D[k]["auto"] for k in COMP]
    r = [D[k]["red"] for k in COMP]
    ax.bar(x, a, 0.65, color="#e8a33d", label="Solar consumida directamente")
    ax.bar(x, r, 0.65, bottom=a, color="#1a3c5e", label="Tomada de la red")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{MC[m]}-{y % 100}" for y, m in COMP])
    _fmt(ax)
    ax.legend(fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.17), frameon=False)
    return _img(fig, A)


def bullets(s, items):
    for t in items:
        s.append(Paragraph(t, ST["b"], bulletText="•"))


# -------------------------------------------------------------------- PDF
def main():
    doc = SimpleDocTemplate(SALIDA, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                            title="Informe de Generación vs Consumo - Bandeja del Postre")
    A = doc.width
    s = [Paragraph("Informe de Generación vs Consumo", ST["t"]),
         Paragraph(f"Bandeja del Postre (Santiago) · Período: diciembre 2025 – octubre 2026 · "
                   f"Fecha: {HOY:%d/%m/%Y}", ST["s"]), Spacer(1, 8)]

    s.append(Paragraph("Resumen", ST["h"]))
    s.append(Paragraph(
        f"El sistema fotovoltaico de {KWP:.2f} kWp funciona correctamente y cumple lo prometido. De enero a octubre "
        f"2026 generó {n(gen)} kWh, un {pct(cumpl, False)} de la generación esperada para esos meses "
        f"({n(esp)} kWh). Desde marzo, con el sistema ya estabilizado, la generación va un "
        f"{pct(gen_e / esp_e - 1)} por encima de lo esperado.", ST["p"]))
    s.append(Paragraph(
        f"En el mismo período el negocio consumió {n(cons)} kWh, por lo que el sistema produjo el "
        f"{pct(cob, False)} de la energía consumida: un excedente neto de {n(excedente)} kWh. Con medición neta, "
        f"solo enero tuvo energía a facturar ({n(kwh_fac)} kWh); de febrero a octubre el consumo neto fue cero y "
        f"se acumuló un crédito de unos {n(cred_final)} kWh.", ST["p"]))

    s.append(Paragraph("Datos del cliente y del sistema", ST["h"]))
    d = [["Dato", "Valor"],
         ["Cliente", "Bandeja del Postre (Santiago)"],
         ["NIC", "6077632"],
         ["Distribuidora", "Edenorte · Tarifa comercial"],
         ["Potencia instalada", f"{KWP:.2f} kWp (FusionSolar registra 34.83 kWp)"],
         ["Plataforma de monitoreo", "Huawei FusionSolar, con smart meter (mide el consumo total)"],
         ["Puesta en marcha", "Diciembre 2025"],
         ["Generación anual esperada", f"{n(ANUAL_ESP)} kWh/año ({REND:,} kWh/kWp)"],
         ["Período analizado", "Diciembre 2025 – Octubre 2026"]]
    s.append(tabla(d, [A * 0.32, A * 0.68], izq=2))

    s.append(Paragraph("Indicadores principales (enero – octubre 2026)", ST["h"]))
    d = [["Indicador", "Valor", "Lectura"],
         ["Generación", f"{n(gen)} kWh", f"{pct(cumpl, False)} de lo esperado"],
         ["Generación marzo – octubre", f"{n(gen_e)} kWh", f"{pct(gen_e / esp_e, False)} de lo esperado"],
         ["Rendimiento anual equivalente", f"{n(rend_anual)} kWh/kWp", f"vs. {REND:,} esperados"],
         ["Mejor mes", f"{MC[mejor[1]]}-{mejor[0] % 100}: {n(D[mejor]['gen'])} kWh",
          f"{pct(D[mejor]['gen'] / D[mejor]['esp'], False)} de lo esperado"],
         ["Consumo del negocio", f"{n(cons)} kWh", f"promedio {n(cons / len(COMP))} kWh/mes"],
         ["Cobertura del consumo", pct(cob, False), f"excedente de {n(excedente)} kWh"],
         ["Solar consumida directamente", f"{n(auto)} kWh", f"{pct(auto / cons, False)} del consumo"],
         ["Energía inyectada a la red", f"{n(iny)} kWh", f"{pct(iny / gen, False)} de lo generado"]]
    s.append(tabla(d, [A * 0.36, A * 0.28, A * 0.36]))

    s.append(KeepTogether([
        Paragraph("Generación vs consumo mensual", ST["h"]),
        Paragraph("Desde febrero el sistema genera más de lo que consume el negocio. La generación sigue de cerca "
                  "la curva esperada y la supera de mayo a septiembre. Diciembre 2025 (gris) es el mes de puesta en "
                  "marcha y se excluye de las comparaciones.", ST["p"]),
        grafico(A)]))

    d = [["Mes", "Generación (kWh)", "Esperada (kWh)", "% esperado", "Consumo (kWh)", "Cobertura"]]
    for k in COMP:
        v = D[k]
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(v["gen"]), n(v["esp"]), pct(v["gen"] / v["esp"], False),
                  n(v["cons"]), pct(v["gen"] / v["cons"], False)])
    d.append(["Total", n(gen), n(esp), pct(cumpl, False), n(cons), pct(cob, False)])
    s.append(KeepTogether([Paragraph("Generación real vs esperada", ST["h"]),
                           tabla(d, [A * 0.12] + [A * 0.176] * 5, total=True), Spacer(1, 3),
                           Paragraph(f"Esperada = {n(ANUAL_ESP)} kWh/año repartidos según la distribución mensual "
                                     "típica de radiación usada por Éfika. Cobertura = generación ÷ consumo.",
                                     ST["nota"])]))

    s.append(KeepTogether([
        Paragraph("¿De dónde viene la energía que consume el negocio?", ST["h"]),
        Paragraph(f"Durante el día el negocio usa directamente cerca de la mitad de lo que generan los paneles; el "
                  f"resto ({n(iny)} kWh) se inyecta a la red y queda como crédito. En la noche y en horas de poco sol "
                  f"el negocio toma energía de la red ({n(red)} kWh en el período), que se compensa con ese "
                  f"crédito.", ST["p"]),
        grafico_origen(A)]))

    bl = [Paragraph("Medición neta (enero – octubre 2026)", ST["h"]),
          Paragraph("Edenorte factura la diferencia entre el consumo y la generación de cada mes. Cuando la "
                    "generación es mayor, el sobrante se guarda como crédito para los meses siguientes.", ST["p"])]
    d = [["Mes", "Consumo (kWh)", "Generación (kWh)", "Neto (kWh)", "kWh a facturar", "Crédito acumulado"]]
    for k, neto, fac, cr in NETO:
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(D[k]["cons"]), n(D[k]["gen"]), f"{neto:+,.0f}", n(fac), n(cr)])
    d.append(["Total", n(cons), n(gen), f"{cons - gen:+,.0f}", n(kwh_fac), n(cred_final)])
    bl.append(tabla(d, [A * 0.12] + [A * 0.176] * 5, total=True))
    bl.append(Spacer(1, 3))
    bl.append(Paragraph(
        "Neto = consumo − generación (negativo = sobrante del mes). Cálculo con los datos del smart meter, asumiendo "
        "crédito en cero al inicio de 2026 por el cierre anual de medición neta. Validar contra las facturas de "
        "Edenorte; la factura mantiene los cargos fijos y, en tarifa comercial, el cargo por demanda.", ST["nota"]))
    s.append(KeepTogether(bl))

    bl = [Paragraph("Tabla de datos completa", ST["h"])]
    d = [["Mes", "Generación (kWh)", "Consumo (kWh)", "Inyectado (kWh)", "De la red (kWh)", "Nota"]]
    for k in MESES_ORD:
        v = D[k]
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(v["gen"]), n(v["cons"]), n(v["iny"]), n(v["red"]),
                  INCOMPLETOS.get(k, "")])
    bl.append(tabla(d, [A * 0.1, A * 0.15, A * 0.15, A * 0.15, A * 0.15, A * 0.30]))
    bl.append(Spacer(1, 3))
    bl.append(Paragraph("Datos de la plataforma Huawei FusionSolar. Inyectado = energía solar enviada a la red. "
                        "De la red = consumo − (generación − inyectado).", ST["nota"]))
    s.append(KeepTogether(bl))

    s.append(Paragraph("Observaciones", ST["h"]))
    bullets(s, [
        "Diciembre 2025 es el mes de puesta en marcha (624 kWh registrados) y no representa un mes completo.",
        f"Enero 2026 generó {pct(D[(2026, 1)]['gen'] / D[(2026, 1)]['esp'], False)} de lo esperado y febrero "
        f"{pct(D[(2026, 2)]['gen'] / D[(2026, 2)]['esp'], False)}. Puede deberse a ajustes posteriores a la puesta "
        f"en marcha o a días nublados; conviene revisar las alarmas de esas semanas en FusionSolar. Desde marzo la "
        f"generación está en línea o por encima de lo esperado.",
        f"El consumo del negocio subió de {n(D[(2026, 2)]['cons'])} kWh en febrero a {n(D[(2026, 9)]['cons'])} kWh "
        f"en septiembre, propio de los meses de más calor (refrigeración y aire acondicionado).",
        f"Con el consumo actual, el sistema produce más energía de la que el negocio usa: al cierre de octubre hay "
        f"unos {n(cred_final)} kWh de crédito acumulado.",
    ])

    s.append(Paragraph("Conclusiones", ST["h"]))
    bullets(s, [
        f"El sistema cumple la generación prometida: {pct(cumpl, False)} de lo esperado de enero a octubre y "
        f"{pct(gen_e / esp_e, False)} desde marzo.",
        f"Cubre el {pct(cob, False)} del consumo del negocio; desde febrero el consumo neto facturable de energía "
        f"es cero.",
        "No se observan fallas ni pérdida de rendimiento.",
    ])

    bl = [Paragraph("Recomendaciones", ST["h"])]
    for t in [
        "Programar limpieza de paneles al menos dos veces al año (antes y después de la temporada de lluvias) para "
        "mantener el rendimiento.",
        "El negocio tiene margen para crecer su consumo (por ejemplo, nuevos equipos de refrigeración) sin pagar "
        "energía adicional, aprovechando el crédito acumulado antes del cierre anual de medición neta.",
        "Revisar con el cliente las facturas de Edenorte de 2026 para confirmar que los créditos de medición neta "
        "se están aplicando correctamente.",
        "Confirmar la tarifa comercial del contrato para incluir en el próximo informe el ahorro estimado en pesos.",
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
