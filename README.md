# Laboratorio de Medidas — Control de Producción

Aplicación web **local de pruebas**, adaptable a PC, tableta y celular. Amplía el
prototipo Python/SQLite conservando sus usuarios, revisiones e identificadores.
No requiere paquetes adicionales para ejecutarse: Python **3.11 o superior**.

## Compartir una demo mediante enlace

El perfil de evaluación web está preparado en [deploy/README.md](deploy/README.md)
y [render.yaml](render.yaml). Utiliza datos ficticios, acceso público de visitante
y colaborador de prueba, y una clave administrativa privada generada en el alojamiento.
El enlace HTTPS lo asigna Render después de crear la cuenta y desplegar el servicio.
Esta configuración necesita una instancia y disco persistente; revisa el plan y
su coste en el proveedor antes de contratarlo. No se ha creado un servicio ni
aceptado ningún cargo desde este entorno.

La publicación usa una lista explícita de fuentes. Los documentos originales,
empleados, bases locales y respaldos quedan fuera del repositorio de despliegue.
El perfil local y sus iniciadores siguen funcionando como se explica abajo.

## Probar en Windows

Haz clic derecho sobre el ZIP y elige **Extraer todo…**. Si usas WinRAR,
elige **Extraer en…**. Abre la carpeta extraída y después
`APLICACION_ACTUAL/probar_demo.bat`. `app.py`, `production.py`, `documents.py`
y las carpetas `static` y `assets` deben estar juntos dentro de `APLICACION_ACTUAL`.
El navegador abre una demostración con personas y producción ficticias:

| Perfil de prueba | Usuario | Contraseña de demostración |
|---|---|---|
| Administración/supervisión | `supervisor_demo` | `LaboratorioDemo2026!` |
| Colaborador | `90001` | `90001` |
| Otro colaborador | `90002` | `90002` |
| Visitante de solo lectura | `visitante_demo` | `VisitanteDemo2026!` |

La demo conserva sus cambios en `APLICACION_ACTUAL/datos_demo`, separado de los
registros normales. Las cuentas de esta tabla solo pertenecen a la demo.

La pantalla debe indicar **Demostración con datos ficticios**. Pulsa
**Usar acceso de supervisión** o **Usar acceso de colaborador** para completar
los campos y después **Entrar al sistema**. Si cambiaste una clave de la demo,
utiliza la clave actual. La instalación normal utiliza las cuentas creadas allí.

Desde la entrega 1.0.2, normal y demo usan direcciones locales distintas
(puertos 8765 y 8766, respectivamente) y sus sesiones pueden coexistir en el
mismo navegador. Si el iniciador dice que el puerto ya está en uso, cierra la
consola anterior de la aplicación y vuelve a abrirlo.

Después de seis intentos fallidos para un mismo usuario se bloquea el acceso
temporalmente durante 15 minutos. El mensaje muestra cuánto falta para volver
a intentarlo. Recargar la página no reinicia esa espera. En esta prueba local,
cerrar la consola de la aplicación y volver a abrir el mismo iniciador elimina
el contador temporal; mantiene usuarios, contraseñas y registros.
La supervisión también puede restablecer el acceso de un técnico: vuelve a su
código de empleado, cierra sus sesiones anteriores y elimina su bloqueo temporal.

Si aparece `can't open file ... app.py` y una ruta `Temp\Rar$…`, WinRAR abrió
solo el iniciador en una carpeta temporal. Extrae el paquete completo como se
indica arriba y ejecútalo desde esa carpeta. Ese error significa que falta el
archivo; no demuestra un problema de versión de Python. Los iniciadores revisados
en la entrega 1.0.1 comprueban los archivos antes de intentar abrir la aplicación.

En Linux/macOS, desde `APLICACION_ACTUAL`:

```sh
python3 app.py --demo
```

Para iniciar una base normal, abre `iniciar.bat` o ejecuta `python app.py`.
Si está vacía, crea en pantalla una cuenta administradora con clave propia.
Una base anterior conserva sus accesos; no se sustituye por datos de ejemplo.

## Funciones

- Seis actividades: limpieza o recuperación (una sola), revisión técnica,
  configuración, sellado, asignación y recepción.
- Captura por lote o por serie, actividad fijada, responsable distinto de capturador.
- SAP opcional en revisión; marca independiente del SAP. Único ejemplo SAP
  precargado confirmado: `1003913`, `240V`, `Recuperado`.
- Formularios configurables con versiones y consulta del histórico original.
- Usuarios, actividades asignadas, cambio de clave y restablecimiento técnico al código.
- Filtros, historial, confirmación de reingreso el mismo día, correcciones,
  anulaciones/restauración y auditoría.
- Recepciones parciales, métricas por actividad/unidad y metas individuales.
- Importación supervisada de revisión/sellado, con validación previa y confirmación.
- Tablas CSV/XLSX/PDF y gráficos SVG/PNG, respetando filtros y permisos.
- Visitante limitado a estadísticas agregadas.

Las cantidades de distintas actividades representan operaciones: limpiar y sellar
el mismo equipo no crea dos medidores físicos diferentes. Los lotes sin series no
permiten calcular equipos únicos. Recuperado describe un medidor retornado de un
suministro, no una aprobación para reutilizarlo.

## Persistencia y actualizaciones

La base normal es `APLICACION_ACTUAL/datos_locales/laboratorio.db`. No la coloques
sobre unidades de red. Las tablas originales permanecen y sus revisiones se
incorporan una sola vez al registro ampliado. Se conservan códigos como texto.
Antes de la primera migración se crea una copia SQLite consistente y verificada
en `backups/` dentro de la carpeta de datos. No se cambian contraseñas existentes.
La cuenta supervisora original conserva su autoridad administrativa mediante
el nuevo perfil Administrador; su identificador, contraseña y rol legado se mantienen.

Administración puede generar más respaldos desde la aplicación. Se requiere una
política de copias en otro destino autorizado para protegerse de pérdida del disco.
Para recuperar una copia: detén todas las instancias, preserva la carpeta de datos
actual completa, restaura la copia en una **carpeta nueva**, y verifica primero:

```sh
python app.py --data-dir RUTA_LOCAL_DE_LA_COPIA --no-browser
```

El archivo restaurado debe llamarse `laboratorio.db`. Nunca mezcles archivos WAL
antiguos con otra copia. Verifica cuentas, fechas y cantidades antes de utilizarla.
La suite prueba restauración de una copia de migración en un directorio nuevo.

## Importaciones y exportaciones

Descarga una plantilla de Revisión técnica o Sellado. Series, SAP y códigos de
empleado deben conservarse como texto; no es posible recuperar ceros que Excel
ya haya eliminado. La vista previa identifica errores por fila y responsables.
Confirma solo después de revisarla. Repetir una carga confirmada no añade registros.
Un reingreso legítimo requiere confirmación y conserva una revisión independiente.

Entrada máxima: 8 MB, 5.000 filas por importación de actividad y 100 columnas.
Exportación máxima: 10.000 filas por archivo; reduce el rango o filtra por actividad
si se supera, sin truncado silencioso. XLSX y CSV conservan Unicode. PDF utiliza
fuente española WinAnsi; caracteres ajenos a ella se representan como `?`.

## Comprobaciones de desarrollo

Desde la raíz del repositorio:

```sh
python -m unittest discover -s APLICACION_ACTUAL/tests -v
python -m unittest discover -s tests -v
```

Las pruebas usan bases temporales y personas ficticias. `openpyxl` es opcional para
una comprobación adicional independiente de XLSX; no se necesita para la aplicación.
El detalle de resultados y límites de validación está en `PROJECT_STATUS.md`.

## Alcance de la versión de prueba

Los iniciadores locales escuchan exclusivamente en `127.0.0.1`. El perfil web
se activa solo mediante `web_demo.py`, con origen HTTPS exacto y carpeta de datos
exclusiva. Permite alojar la demo ficticia que el usuario solicitó para evaluación.
El uso operativo con empleados o datos reales requiere despliegue revisado por TI.
No se ha modificado firewall ni importado nombres de empleados para estas pruebas.

`REFERENCIAS/` y la documentación original contienen material del paquete aportado
por el usuario; no se suben a servicios públicos ni se usan como datos de prueba.
`MANIFIESTO.md` corresponde al ZIP original, previo a estos cambios de desarrollo.
