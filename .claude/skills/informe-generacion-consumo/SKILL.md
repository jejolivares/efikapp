---
name: informe-generacion-consumo
description: Genera el "Informe de Generación vs Consumo" en PDF de Éfika Ingeniería para un cliente con sistema fotovoltaico, descargando sus datos de FusionSolar (Huawei) o Deye/SolarMan y redactando resumen, observaciones, conclusiones y recomendaciones. Usa este skill siempre que pidan "el reporte", "el informe", "el informe de generación" o "generación vs consumo" de un cliente, una residencia o un negocio (por ejemplo "hazme el reporte de Bandeja del Postre", "saca el informe de Res. Luis López", "cómo va la planta de CEDIMujer"), o cuando un cliente se queje de que paga mucha luz y haya que revisar si el sistema está generando bien, aunque no digan "PDF" ni "FusionSolar".
---

# Informe de Generación vs Consumo

Produce el informe en PDF que Éfika envía a sus clientes fotovoltaicos. El objetivo del informe
es responder con datos dos preguntas del cliente: **¿el sistema está generando lo prometido?**
y **¿por qué pago (o no pago) lo que pago?**. Los números los calcula el script; tu trabajo es
interpretarlos y redactar los textos con criterio de ingeniero.

Ejemplos ya entregados: `informes/luis_lopez/`, `informes/jimenez_olivares/`,
`informes/bandeja_del_postre/`. Úsalos como referencia de tono y profundidad.

## Flujo

### 1. Encontrar la planta y los datos del cliente

```bash
cd programa && python informes_clientes.py --listar | grep -i "<parte del nombre>"
```

Busca también al cliente en `programa/clientes.csv` (NIC, kWp, tarifa). El nombre puede
diferir entre el CSV y la plataforma (por ejemplo "Bandeja del Postre" vs
"Bandeja del Postre - STI - 34.83"): usa un fragmento distintivo. Si aparece en más de una
planta (MD Ojos tiene varios niveles, CEDIMujer tiene SDO y STI), pregunta cuál quiere.

- **kWp**: el de `clientes.csv`; si está vacío, el que trae la plataforma o el nombre.
- **Tarifa**: la columna `Tarifa`; si está vacía y el nombre empieza por Res., Flia o Familia,
  usa `BTS-1`. Para comercial/industrial sin tarifa, deja `"tarifa": null` (el informe muestra
  medición neta en kWh sin pesos) y dilo al usuario: con la tarifa se puede calcular el ahorro.
  Solo se pueden usar tarifas que existan como `[tarifa:X]` en `programa/config.ini`.

### 2. Descargar los datos

```bash
cd programa && python informes_clientes.py --planta "<fragmento>"
mkdir -p ../informes/<slug> && cp "salida/<carpeta de la planta>/datos.csv" ../informes/<slug>/
```

`<slug>` en minúsculas con guiones bajos (`bandeja_del_postre`, `luis_lopez`). Las credenciales
vienen de variables de entorno; si falta alguna o la red bloquea la plataforma, ve
`programa/LEEME.md` y avisa al usuario en lugar de inventar datos.

### 3. Analizar

Crea `informes/<slug>/informe.json` mínimo (`nombre`, `kwp`, `tarifa`, `hasta`) y ejecuta:

```bash
python .claude/skills/informe-generacion-consumo/scripts/informe.py analizar informes/<slug>
```

`hasta` es el último mes cerrado (normalmente el mes pasado, `AAAA-MM`); el mes en curso
siempre está incompleto. El JSON resultante trae: generación vs esperada (1,500 kWh/kWp/año
repartidos por mes), resumen por año, comparación del año actual con el primer año que tenga
los mismos meses completos, cobertura del consumo, autoconsumo e inyección, medición neta del
año (crédito reiniciado en enero) y, con tarifa, factura con y sin FV.

Revisa los datos antes de escribir:
- `incompletos`: el script marca automáticamente el primer mes si es parcial y cualquier mes
  con generación < 35 % de lo esperado o consumo en cero. Mira la tabla `mensual` y agrega o
  quita meses en `informe.json` → `"incompletos": {"2025-06": "Datos incompletos", "2024-03": null}`
  (`null` quita la marca). Un consumo anormalmente bajo con generación normal suele ser falla del
  smart meter.
- `meses_bajos`: meses completos por debajo del 80 % de lo esperado. Si son varios seguidos,
  probablemente hay una causa (inversor apagado, suciedad, sombra) y merece sección propia.
- Si `medidor` es false, la planta no tiene smart meter: el informe será solo de generación.

### 4. Redactar los textos en `informe.json`

Ver `references/ejemplo_informe.json` para un caso completo. Campos:

| Campo | Contenido |
|---|---|
| `nombre`, `kwp`, `tarifa`, `hasta` | obligatorios |
| `plataforma` | "Huawei FusionSolar" o "Deye Cloud" (va en las notas) |
| `archivo` | nombre del PDF, p. ej. `Informe_Gen_vs_Consumo_Res_Luis_Lopez.pdf` |
| `etiqueta_consumo` | "Consumo de la vivienda" / "Consumo del negocio" |
| `datos_cliente` | filas `[dato, valor]`: Cliente, NIC, Distribuidora y tarifa, Potencia, Módulos, Inversores, Puesta en marcha. Potencia, generación esperada y período se agregan solas si faltan |
| `resumen` | 2–3 párrafos: veredicto primero, luego cifras que lo sostienen |
| `indicadores_lectura` | opcional: `{"<texto del indicador>": "<lectura>"}` para cambiar la columna "Lectura" |
| `texto_grafico`, `texto_origen` | 1 párrafo cada uno, explicando qué se ve |
| `texto_meses_bajos` (+ `titulo_meses_bajos`) | solo si hay meses bajos que explicar; si es `null` la sección no aparece |
| `texto_medicion_neta`, `nota_medicion_neta`, `nota_tabla` | opcionales; tienen texto por defecto |
| `observaciones`, `conclusiones`, `recomendaciones` | listas de viñetas |

Cómo escribir (el lector es el cliente, no un ingeniero):
- Empieza el resumen con la conclusión: "El sistema funciona correctamente y…" o "La generación
  bajó X % por…". Si el cliente paga más, di claramente si la causa es el sistema o su consumo.
- Usa cifras concretas del análisis (kWh, %, RD$) y redondea como en el PDF (`45,042 kWh`, `99.6%`).
  Copia los números del JSON de `analizar`; no los recalcules a mano.
- Separa hechos de hipótesis: "puede deberse a… conviene revisar las alarmas en FusionSolar".
- Recomendaciones accionables: limpieza, revisar alarmas de meses concretos, gestión de consumo,
  ampliación (kWp ≈ déficit anual ÷ 1,500, en módulos de 580 Wp, sujeta a capacidad del inversor),
  revisar facturas de la distribuidora para confirmar créditos.
- Español dominicano neutro, sin jerga ("smart meter" y "medición neta" sí se usan).

### 5. Generar y revisar

```bash
python .claude/skills/informe-generacion-consumo/scripts/informe.py pdf informes/<slug>
```

Crea el PDF y `vista_previa/pagina-N.png`. Mira todas las páginas: títulos huérfanos al final
de página, tablas cortadas, textos que no cuadran con los números. Ajusta textos y regenera.

### 6. Entregar

1. `git add informes/<slug>` (datos.csv, informe.json, PDF y vista_previa), commit
   "Agregar informe de generación vs consumo de <cliente>" y push a la rama de trabajo.
2. Envía el PDF al usuario y resume en pocas líneas: veredicto, 3–4 cifras clave y lo que
   necesita confirmar (tarifa faltante, distribuidora supuesta, datos de equipos que no se
   tenían, meses dudosos).

Si falta información que no está en el repo (modelo de paneles/inversores, distribuidora,
tarifa comercial, facturas), no la inventes: omite la fila o márcala "por confirmar" y menciónalo
al entregar.
