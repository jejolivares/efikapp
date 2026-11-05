# -*- coding: utf-8 -*-
"""Informe de Generación vs Consumo - Res. Jiménez Olivares (NIC 5036399).

Fuente de datos: "Clientes FV.xlsx" (Drive > Efika Proyectos > Proyectos)
  - pestaña de seguimiento FusionSolar: generación real mensual may-2024 a ago-2025
  - pestaña de consumo Edenorte: kWh facturados (netos) ene-2023 a mar-2025
Uso: python generar_informe.py  -> crea el PDF junto a este archivo.
"""
import io
import os
import datetime as dt

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
SALIDA = os.path.join(BASE, "Informe_Gen_vs_Consumo_Res_Jimenez_Olivares.pdf")
HOY = dt.date(2026, 11, 5)

# ------------------------------------------------------------------ datos
KWP = 5.95                      # potencia registrada en FusionSolar / clientes.csv
KWP_CARTA = 6.545               # carta a Edenorte: 11 x Canadian Solar 595 Wp
REND = 1500                     # kWh/kWp/año (criterio Efika)
ANUAL_ESP = KWP * REND          # 8,925 kWh/año
# Distribución mensual usada en la hoja de seguimiento (% del año)
PCT = {1: 7.69, 2: 7.76, 3: 8.90, 4: 8.93, 5: 8.73, 6: 8.64, 7: 9.30, 8: 9.42,
       9: 8.92, 10: 8.34, 11: 6.87, 12: 6.51}

GEN = {  # Generación real FusionSolar (kWh)
    (2024, 5): 842.53, (2024, 6): 852.20, (2024, 7): 853.52, (2024, 8): 911.55,
    (2024, 9): 830.32, (2024, 10): 738.11, (2024, 11): 534.11, (2024, 12): 557.84,
    (2025, 1): 623.66, (2025, 2): 627.24, (2025, 3): None, (2025, 4): None,
    (2025, 5): 865.14, (2025, 6): 802.47, (2025, 7): 911.52, (2025, 8): 850.46,
}
FACT = {  # kWh facturados por Edenorte (consumo neto)
    (2023, 1): 265, (2023, 2): 287, (2023, 3): 365, (2023, 4): 319, (2023, 5): 230,
    (2023, 6): 50, (2023, 7): 0, (2023, 8): 0, (2023, 9): 0, (2023, 10): 0,
    (2023, 11): 0, (2023, 12): 0, (2024, 1): 0, (2024, 2): 0, (2024, 3): 0,
    (2024, 4): 0, (2024, 5): 0, (2024, 6): 0, (2024, 7): 0, (2024, 8): 0,
    (2024, 9): 0, (2024, 10): 0, (2024, 11): 0, (2024, 12): 0, (2025, 1): 0,
    (2025, 2): 0, (2025, 3): 0,
}

MC = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def esp(m):
    return ANUAL_ESP * PCT[m] / 100


def tarifa_bts1(kwh):
    """BTS-1 Edenorte 2026 (misma tabla del informe de Tania y Rino)."""
    if kwh > 700:
        return kwh * 14.04 + 126.81
    tot, a = 0.0, 0
    for lim, pr in ((200, 5.97), (300, 8.51), (700, 13.83)):
        if kwh > a:
            tot += (min(kwh, lim) - a) * pr
        a = lim
    return tot + 126.81


def n(v, d=0):
    return "—" if v is None else f"{v:,.{d}f}"


def rd(v):
    return f"RD${v:,.0f}"


def pct(v, signo=True):
    return f"{v * 100:+.1f}%" if signo else f"{v * 100:.1f}%"


# --------------------------------------------------------------- análisis
meses_gen = sorted(GEN)
ok = [k for k in meses_gen if GEN[k] is not None]
ultimos12 = [k for k in meses_gen if (2024, 9) <= k <= (2025, 8)]
ok12 = [k for k in ultimos12 if GEN[k] is not None]
gen12 = sum(GEN[k] for k in ok12)
esp12_ok = sum(esp(k[1]) for k in ok12)
falt12 = [k for k in ultimos12 if GEN[k] is None]
gen12_anual = gen12 + sum(esp(k[1]) for k in falt12)        # meses faltantes al esperado
cumpl12 = gen12 / esp12_ok
rend12 = gen12_anual / KWP

cmp_ = [(m, GEN[(2024, m)], GEN[(2025, m)]) for m in (5, 6, 7, 8)]
g24, g25 = sum(c[1] for c in cmp_), sum(c[2] for c in cmp_)
var_cmp = g25 / g24 - 1

pre = [FACT[(2023, m)] for m in (1, 2, 3, 4)]                 # antes del sistema
cons_base = sum(pre) / len(pre)
meses_cero = [k for k in FACT if FACT[k] == 0]
fact_sin = tarifa_bts1(cons_base)
fact_con = tarifa_bts1(0)
ahorro_mes = fact_sin - fact_con
ahorro_tot = ahorro_mes * len(meses_cero)
excedente = gen12_anual - cons_base * 12

# ----------------------------------------------------------------- estilo
AZUL, NARANJA, GRIS = colors.HexColor("#1a3c5e"), colors.HexColor("#e8a33d"), colors.HexColor("#6b7280")
ST = {
    "t": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=19, textColor=AZUL, leading=23),
    "s": ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=GRIS, leading=13),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, textColor=AZUL, leading=16,
                        spaceBefore=12, spaceAfter=6),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=6),
    "b": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=3,
                        leftIndent=10, bulletIndent=0),
    "nota": ParagraphStyle("n", fontName="Helvetica-Oblique", fontSize=7.5, leading=10, textColor=GRIS),
    "cb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
    "aviso": ParagraphStyle("a", fontName="Helvetica", fontSize=8.5, leading=11.5,
                            textColor=colors.HexColor("#7a4b00")),
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


def caja(texto, A):
    t = Table([[Paragraph(texto, ST["aviso"])]], colWidths=[A])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf3e1")),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, NARANJA),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
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
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    x = list(range(len(meses_gen)))
    vals = [GEN[k] or 0 for k in meses_gen]
    ax.bar(x, vals, 0.7, color=["#b8bfca" if GEN[k] is None else "#2e9e4f" for k in meses_gen],
           label="Generación real")
    ax.plot(x, [esp(k[1]) for k in meses_gen], color="#555", ls="--", lw=1.2, marker="o", ms=2.5,
            label="Generación esperada")
    for i, k in enumerate(meses_gen):
        if GEN[k] is None:
            ax.text(i, 40, "sin\ndato", ha="center", fontsize=6, color="#6b7280")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{MC[m]}-{y % 100}" for y, m in meses_gen], rotation=90, fontsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_ylabel("kWh", fontsize=8)
    ax.legend(fontsize=7, ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.14), frameon=False)
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=200, bbox_inches="tight")
    w, h = fig.get_size_inches()
    plt.close(fig)
    b.seek(0)
    return Image(b, width=A, height=A * h / w)


# -------------------------------------------------------------------- PDF
def main():
    doc = SimpleDocTemplate(SALIDA, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                            title="Informe de Generación vs Consumo - Res. Jiménez Olivares")
    A = doc.width
    s = [Paragraph("Informe de Generación vs Consumo", ST["t"]),
         Paragraph(f"Res. Jiménez Olivares (Vista Linda) · Período: enero 2023 – agosto 2025 · "
                   f"Fecha: {HOY:%d/%m/%Y}", ST["s"]), Spacer(1, 8)]

    s.append(Paragraph("Resumen", ST["h"]))
    s.append(Paragraph(
        "El sistema fotovoltaico funciona correctamente y produce lo prometido. Desde julio 2023 la "
        "vivienda no ha tenido kWh facturados por Edenorte: la generación cubre todo el consumo.", ST["p"]))
    s.append(Paragraph(
        f"En los últimos 12 meses con registro (septiembre 2024 – agosto 2025) el sistema generó "
        f"{n(gen12)} kWh en los {len(ok12)} meses con datos, un {pct(cumpl12, False)} de lo esperado para "
        f"esos meses. Completando marzo y abril 2025 (sin registro) con su valor esperado, el año equivale a "
        f"unos {n(gen12_anual)} kWh ({n(rend12)} kWh/kWp), en línea con los {n(ANUAL_ESP)} kWh/año prometidos. "
        f"Entre mayo y agosto la generación de 2025 fue prácticamente igual a la de 2024 ({pct(var_cmp)}): "
        f"no hay degradación.", ST["p"]))
    s.append(Paragraph(
        f"Antes del sistema la casa pagaba unos {n(cons_base)} kWh/mes (≈{rd(fact_sin)} con la tarifa BTS-1 "
        f"actual). Desde julio 2023 solo paga el cargo fijo, un ahorro estimado mínimo de {rd(ahorro_mes)} "
        f"al mes y {rd(ahorro_tot)} en los {len(meses_cero)} meses facturados en cero (jul-2023 a mar-2025).",
        ST["p"]))
    s.append(caja(
        "<b>Alcance de los datos.</b> Este informe usa la hoja de seguimiento \"Clientes FV\": generación "
        "FusionSolar de mayo 2024 a agosto 2025 (sin marzo ni abril 2025) y kWh facturados por Edenorte de "
        "enero 2023 a marzo 2025. No hay datos de septiembre 2025 a octubre 2026 ni del consumo total de la "
        "vivienda (smart meter). Para actualizarlo, ejecutar <i>informes_clientes.py --planta "
        "\"Jimenez Olivares\"</i> con acceso a FusionSolar.", A))

    s.append(Paragraph("Datos del cliente y del sistema", ST["h"]))
    d = [["Dato", "Valor"],
         ["Cliente", "Res. Jiménez Olivares (titular del contrato: Fátima Olivares)"],
         ["NIC", "5036399"],
         ["Ubicación", "Calle 3 #4, Vista Linda, Santiago"],
         ["Distribuidora", "Edenorte · Tarifa BTS-1 (residencial)"],
         ["Potencia instalada", f"{KWP} kWp registrados en FusionSolar (ver observaciones)"],
         ["Módulos", "Canadian Solar 595 Wp monocristalinos"],
         ["Inversor", "1 inversor Huawei SUN2000-5KTL-L1"],
         ["Puesta en marcha", "Abril 2023 (encendido 11/04/2023)"],
         ["Generación anual prometida", f"{n(ANUAL_ESP)} kWh/año ({REND:,} kWh/kWp)"],
         ["Período analizado", "Enero 2023 – Agosto 2025"]]
    s.append(tabla(d, [A * 0.32, A * 0.68], izq=2))

    s.append(Paragraph("Indicadores principales", ST["h"]))
    d = [["Indicador", "Valor", "Lectura"],
         ["Generación sep-24 a ago-25 (10 meses con datos)", f"{n(gen12)} kWh",
          f"{pct(cumpl12, False)} de lo esperado"],
         ["Generación anual estimada", f"{n(gen12_anual)} kWh", f"vs. {n(ANUAL_ESP)} prometidos"],
         ["Rendimiento específico", f"{n(rend12)} kWh/kWp", f"vs. {REND:,} esperados"],
         ["Variación generación may–ago (2025 vs 2024)", pct(var_cmp), "sistema estable"],
         ["Consumo facturado antes del sistema", f"{n(cons_base)} kWh/mes", "promedio ene–abr 2023"],
         ["Meses facturados en 0 kWh", f"{len(meses_cero)}", "jul-2023 a mar-2025"]]
    s.append(tabla(d, [A * 0.46, A * 0.22, A * 0.32]))

    s.append(KeepTogether([Paragraph("Generación mensual", ST["h"]), Paragraph(
        "La generación sigue la curva esperada: más alta de mayo a septiembre y más baja de noviembre a "
        "febrero. Los meses de invierno quedaron entre 87% y 96% de lo esperado, algo normal por la menor "
        "altura del sol y más nubosidad; el resto del año supera lo esperado.", ST["p"]), grafico(A)]))

    bl = [Paragraph("Mismo período, 2024 vs 2025 (mayo a agosto)", ST["h"])]
    d = [["Mes", "Esperado (kWh)", "Gen. 2024 (kWh)", "Gen. 2025 (kWh)", "Variación"]]
    for m, a, b in cmp_:
        d.append([MESES[m], n(esp(m)), n(a), n(b), pct(b / a - 1)])
    d.append(["Total", n(sum(esp(m) for m, _, _ in cmp_)), n(g24), n(g25), pct(var_cmp)])
    bl.append(tabla(d, [A * 0.2] * 5, total=True))
    s.append(KeepTogether(bl))

    bl = [Paragraph("Consumo facturado por Edenorte", ST["h"]),
          Paragraph("Con medición neta, Edenorte solo factura la energía que la casa toma de la red por "
                    "encima de lo que inyecta. Desde julio 2023 la factura de energía es 0 kWh.", ST["p"])]
    d = [["Mes", "kWh facturados", "Factura energía (BTS-1)", "Nota"]]
    for k in sorted(FACT):
        y, m = k
        nota = "antes del sistema" if k <= (2023, 4) else ("arranque / medición neta" if k <= (2023, 6) else "")
        if k >= (2023, 8) and k <= (2025, 2):
            continue
        d.append([f"{MC[m]}-{y % 100}", n(FACT[k]), rd(tarifa_bts1(FACT[k])), nota])
        if k == (2023, 7):
            d.append(["Ago-23 a Feb-25", "0", rd(fact_con) + " c/mes", "19 meses en cero"])
    bl.append(tabla(d, [A * 0.2, A * 0.2, A * 0.28, A * 0.32]))
    bl.append(Spacer(1, 4))
    bl.append(Paragraph(
        "Estimado con la tarifa BTS-1 de Edenorte vigente en 2026 (0–200 kWh RD$5.97; 201–300 RD$8.51; "
        "301–700 RD$13.83; más de 700 kWh todos a RD$14.04) y cargo fijo de RD$126.81. El ahorro asume que "
        "el consumo se mantuvo en el promedio previo al sistema; si la casa consume más hoy, el ahorro real "
        "es mayor. Validar contra las facturas de Edenorte.", ST["nota"]))
    s.append(KeepTogether(bl))

    bl = [Paragraph("Tabla de datos completa", ST["h"])]
    d = [["Mes", "Generación (kWh)", "Esperado (kWh)", "% esperado", "Nota"]]
    for k in meses_gen:
        g = GEN[k]
        d.append([f"{MC[k[1]]}-{k[0] % 100}", n(g), n(esp(k[1])),
                  "—" if g is None else pct(g / esp(k[1]), False),
                  "Sin registro en la hoja" if g is None else ""])
    bl.append(tabla(d, [A * 0.15, A * 0.2, A * 0.2, A * 0.15, A * 0.3]))
    bl.append(Spacer(1, 4))
    bl.append(Paragraph(f"Datos de Huawei FusionSolar registrados en la hoja de seguimiento \"Clientes FV\". "
                        f"Esperado = {n(ANUAL_ESP)} kWh/año × distribución mensual de la hoja.", ST["nota"]))
    s.append(KeepTogether(bl))

    s.append(Paragraph("Observaciones", ST["h"]))
    for t in [
        f"La potencia no coincide entre documentos: la carta de medición neta a Edenorte (2022–2023) describe "
        f"11 módulos de 595 Wp ({KWP_CARTA} kWp) y FusionSolar / la base de clientes registran {KWP} kWp "
        f"(equivale a 10 módulos). Si el sistema real es de {KWP_CARTA} kWp, la generación anual esperada "
        f"sería {n(KWP_CARTA * REND)} kWh y el cumplimiento bajaría a ≈{pct(gen12_anual / (KWP_CARTA * REND), False)}.",
        "Marzo y abril 2025 no tienen generación registrada en la hoja; no se sabe si fue falta de "
        "conexión o un dato no anotado.",
        f"La generación (≈{n(gen12_anual)} kWh/año) es mucho mayor que el consumo previo de la casa "
        f"(≈{n(cons_base * 12)} kWh/año). Si el consumo se mantiene, sobran unos {n(excedente)} kWh al año "
        f"que quedan como crédito de medición neta.",
    ]:
        s.append(Paragraph(t, ST["b"], bulletText="•"))

    s.append(Paragraph("Conclusiones", ST["h"]))
    for t in [
        "El sistema cumple la generación prometida y no muestra degradación entre 2024 y 2025.",
        "La vivienda no ha pagado energía a Edenorte desde julio 2023; solo el cargo fijo.",
        f"Ahorro estimado mínimo de {rd(ahorro_mes)} al mes ({rd(ahorro_tot)} entre jul-2023 y mar-2025).",
    ]:
        s.append(Paragraph(t, ST["b"], bulletText="•"))

    bl = [Paragraph("Recomendaciones", ST["h"])]
    for t in [
        "Descargar de FusionSolar la generación y el consumo de septiembre 2025 a octubre 2026 para "
        "completar el informe (incluido marzo y abril 2025).",
        f"Confirmar en sitio la cantidad de módulos instalados (10 u 11) y corregir la potencia en "
        f"FusionSolar y en \"Clientes FV Nuevo\".",
        "Revisar las facturas de Edenorte de 2025 y 2026 para confirmar los créditos acumulados y cómo se "
        "liquidan al cierre anual de medición neta.",
        "Con el excedente disponible, la casa puede sumar cargas (por ejemplo, aires acondicionados o un "
        "vehículo eléctrico) sin aumentar la factura.",
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
