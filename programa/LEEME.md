# Informes de Generación FV (versión en la nube)

Corre en el entorno en la nube de Claude, sin PC de oficina.

- Claves: se leen de variables de entorno del entorno en la nube
  (`FUSIONSOLAR_USERNAME`, `FUSIONSOLAR_SYSTEM_CODE`, `FUSIONSOLAR_SUBDOMAIN`,
  `DEYE_APP_ID`, `DEYE_APP_SECRET`, `DEYE_EMAIL`, `DEYE_PASSWORD`). Nunca en el repositorio.
- Red: el entorno debe permitir `intl.fusionsolar.huawei.com` y `us1-developer.deyecloud.com`.
- Salida: carpeta `salida/` (una carpeta por planta con `datos.csv` y el PDF, más el Excel resumen).

Uso:

    python informes_clientes.py --listar
    python informes_clientes.py --planta "Luis Lopez"
    python informes_clientes.py --sin-api --planta "Luis Lopez"
