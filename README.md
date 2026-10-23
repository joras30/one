# Laboratorio de Medidas — Control de Producción

Aplicación web **2.0 de pruebas controladas**, con los requisitos del modelo V6,
adaptable a PC, tableta y celular. Amplía el prototipo Python/SQLite conservando
sus usuarios, revisiones e identificadores; el esquema de datos es **4**.
No requiere paquetes adicionales para ejecutarse: Python **3.11 o superior**.

La interfaz usa un tablero industrial oscuro con contadores, gráficos, tablas y
semáforos acompañados de texto. Puede ejecutarse en una sola PC o servir una
misma base a los navegadores de la red de oficina desde la PC principal.

## Compartir la instalación en la oficina

En la PC principal abre **`APLICACION_ACTUAL/iniciar_red.bat`** e introduce su IP
privada asignada, por ejemplo `192.168.1.20`. La consola muestra el enlace para
los otros equipos: **http://192.168.1.20:8765**. Utiliza tu IP real; el ejemplo no
asigna una dirección a la PC. El celular debe conectarse a la misma red de oficina.

Los clientes usan su navegador; Python y la base permanecen en la PC principal.
Esta modalidad comparte los registros entre los equipos que usan ese servidor.
La PC debe permanecer encendida. La guía de instalación, requisitos de red y
actualización está en [deploy/RED_LOCAL.md](deploy/RED_LOCAL.md).

El modo de red se activa explícitamente. `iniciar.bat` y `probar_demo.bat`
mantienen su acceso exclusivo a `127.0.0.1`. No se modifica el firewall ni la IP
del equipo. HTTP requiere una red privada de confianza; TI debe revisar el uso
institucional y los certificados HTTPS cuando corresponda.

## Compartir una demo mediante enlace

El presupuesto autorizado es **costo cero**. La demo para evaluación se publica
en **GitHub Pages**, sin servidor de pago, tarjeta ni cuenta adicional. La guía
está en [deploy/README.md](deploy/README.md). Se retiró la propuesta de pago.

En **Settings → Pages**, elige **Deploy from a branch → gh-pages → /(root) → Save**.
La distribución ya está en esa rama. GitHub publica sus cambios en
https://joras30.github.io/one/ después de activar Pages.
Para entregar mejoras se actualiza la distribución en `gh-pages`; los visitantes
solo recargan el enlace. El workflow **Construir demo gratuita** de `demo-web`
construye y verifica un artefacto. Detecta el modo de Pages: publica automáticamente
si está configurado con GitHub Actions; en modo de rama sirve la distribución
publicada en `gh-pages`.

La demo ejecuta las funciones del laboratorio en el navegador y guarda su SQLite
en IndexedDB. Mantiene los registros al recargar o actualizar el código en la misma
dirección. Cada navegador tiene una prueba independiente; PC y celular no comparten
los registros automáticamente. Los botones de respaldo permiten descargar la prueba
completa y restaurarla en otro navegador. Borrar los datos del sitio elimina esa copia.

Es una demo con personas ficticias; sus perfiles permiten evaluar las pantallas,
no protegen una base laboral compartida. Para compartir registros en la oficina
se utiliza el servidor local descrito arriba. La sincronización por Internet de
la demo Pages requeriría una base y permisos del lado servidor adicionales.

La publicación usa una lista explícita de fuentes. Los documentos originales,
empleados, bases locales y respaldos quedan fuera del repositorio de despliegue.
El perfil local y sus iniciadores siguen funcionando como se explica abajo.

## Probar en Windows

Haz clic derecho sobre el ZIP y elige **Extraer todo…**. Si usas WinRAR,
elige **Extraer en…**. Abre la carpeta extraída y después
`APLICACION_ACTUAL/probar_demo.bat`. `app.py`, `production.py`, `operational.py`,
`analytics.py`, `documents.py`, `catalogos.json` y las carpetas `static` y `assets`
deben estar juntos dentro de `APLICACION_ACTUAL`.
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
- SAP opcional en revisión; códigos, marcas, modelos, voltajes y clasificaciones
  independientes. Un SAP admite varias configuraciones seleccionables. Único
  ejemplo SAP precargado confirmado: `1003913`, `240V`, `Recuperado`.
- Sellado unificado con serie, SAP, marca y modelo; la configuración SAP elegida
  determina la clasificación de origen sin separar la actividad en dos.
- Formularios configurables con versiones y consulta del histórico original.
- Usuarios, actividades asignadas, cambio de clave y restablecimiento técnico al código.
- Filtros, historial, confirmación de reingreso el mismo día, correcciones,
  anulaciones/restauración y auditoría.
- Órdenes con proceso único y un SAP por proceso, entregas parciales, cantidades
  recibidas y pendientes, vencimientos, cierre con acta y reapertura con motivo.
- Calidad de revisión y calibración: resultados de reutilización, fallos, tasas
  y desviaciones por técnico con filtros de fecha.
- Comparativas A/B diarias, semanales, mensuales y anuales, con variación absoluta
  y porcentual por actividad y unidad, además de métricas y metas individuales.
- Importación supervisada de revisión/sellado, con validación previa y confirmación.
- Tablas CSV/XLSX/PDF y gráficos SVG/PNG, respetando filtros y permisos.
- Visitante limitado a estadísticas agregadas.

Las cantidades de distintas actividades representan operaciones: limpiar y sellar
el mismo equipo no crea dos medidores físicos diferentes. Los lotes sin series no
permiten calcular equipos únicos. Recuperado describe un medidor retornado de un
suministro, no una aprobación para reutilizarlo.

## Catálogo SAP, recepción y control de calidad

Un voltaje puede corresponder a varios códigos SAP y un código puede tener varias
configuraciones. La marca y el modelo no son vínculos exclusivos del código.
Si el SAP tiene configuraciones alternativas, selecciona la correspondiente al
medidor; el sistema no debe inferir una clasificación ambigua. El registro conserva
sus datos aunque después se actualice el catálogo.

En **Recepciones**, crea la orden indicando proceso único, número de orden, SAP,
cantidad esperada y, si corresponde, fecha de seguimiento. Cada entrega se registra
en la actividad Recepción con el mismo proceso, orden y SAP. Para otro SAP utiliza
otro proceso. El panel acumula las entregas válidas y muestra pendientes o excesos;
un saldo completo no cierra automáticamente la orden. La supervisión realiza el
cierre cuando la cantidad recibida coincide con la esperada y descarga el acta.
El acta conserva una instantánea y su huella SHA-256. Para cambiar entregas de una
orden cerrada primero debe reabrirse con un motivo registrado en la auditoría.

En **Revisión técnica**, SAP sigue siendo opcional. Los datos de inspección y
calibración también son opcionales; al informar mediciones se requiere referencia
distinta de cero, valor medido y tolerancia en porcentaje. La desviación es
`(medido - referencia) / abs(referencia) × 100`; la alerta compara su valor absoluto
con la tolerancia. Las tasas de aprobación y rechazo usan como denominador las
revisiones evaluadas (**Apto + No apto**); los pendientes y resultados ausentes se
muestran separados. Cada técnico consulta su propio alcance y el visitante solo
estadísticas agregadas.

## Comparar períodos y descargar informes

En **Comparativas**, selecciona los rangos inclusivos de A y B, la granularidad y
los filtros. Se muestran los totales de ambos rangos por actividad y unidad;
los registros y las cantidades son métricas diferentes. La variación absoluta
es **B − A**, y el crecimiento es **(B − A) / A × 100**. Si A es cero y B es mayor
que cero se muestra **Sin base**, sin inventar un porcentaje; si ambos son cero,
la variación es cero. Las semanas siguen el calendario ISO, de lunes a domingo.

Los reportes de calidad y comparativas pueden descargarse directamente en Excel
o PDF con los filtros y períodos utilizados. Las tablas y gráficos existentes
siguen disponibles en sus respectivos formatos. El historial de auditoría añade
las correcciones, anulaciones y reaperturas sin sobrescribir entradas: SQLite
bloquea la edición y eliminación de esas entradas y se puede verificar su cadena
de integridad SHA-256.

## Persistencia y actualizaciones

La base normal es `APLICACION_ACTUAL/datos_locales/laboratorio.db`. No la coloques
sobre unidades de red. Las tablas originales permanecen y sus revisiones se
incorporan una sola vez al registro ampliado. Se conservan códigos como texto.
Antes de la primera migración se crea una copia SQLite consistente y verificada
en `backups/` dentro de la carpeta de datos. No se cambian contraseñas existentes.
La cuenta supervisora original conserva su autoridad administrativa mediante
el nuevo perfil Administrador; su identificador, contraseña y rol legado se mantienen.

Para actualizar a la versión 2.0, genera un respaldo desde Administración y
conserva una copia en otro destino autorizado. Cierra la consola de la aplicación
antes de sustituir el código. Conserva intactas las carpetas `datos_locales`,
`datos_demo` y sus respaldos; no las reemplaces por una carpeta vacía del paquete.
Vuelve a abrir el mismo iniciador y la misma carpeta de datos. La migración al
esquema 4 conserva el histórico y las versiones anteriores de los formularios.
Los equipos clientes de la oficina solo recargan el mismo enlace.

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

Los iniciadores `iniciar.bat` y `probar_demo.bat` escuchan en `127.0.0.1`.
`iniciar_red.bat` utiliza exclusivamente la IPv4 privada que se indica; SQLite
permanece en el disco local de la PC principal. La publicación
gratuita se construye con `browser-demo/`; `.github/workflows/pages.yml` verifica
el artefacto y lo publica según el modo de Pages configurado. El perfil alternativo
`web_demo.py` sigue disponible para un servidor propio, sin contratar alojamiento.
El uso operativo con empleados o datos reales requiere despliegue revisado por TI.
No se ha modificado firewall ni importado nombres de empleados para estas pruebas.
Las comprobaciones realizadas aquí usan datos ficticios y loopback; no equivalen
a una prueba física de la red de la oficina o de los iniciadores en Windows.

`REFERENCIAS/` y la documentación original contienen material del paquete aportado
por el usuario; no se suben a servicios públicos ni se usan como datos de prueba.
`MANIFIESTO.md` corresponde al ZIP original, previo a estos cambios de desarrollo.
