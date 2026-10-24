# Laboratorio de Medidas — Control de Producción

## Estado vigente: V34, fase 2 para validación

La fase 1 fue validada por el solicitante. La fase 2 habilita catálogo oficial por
importación local, actividades, captura rápida, Excel con validación previa,
sellado con unicidad permanente número+color, ciclos, bajas y piezas, permisos
temporales, recepciones parciales y resumen SAP. Fichas interactivas con datos
personales protegidos por rol; todos los supervisores gestionan todos los técnicos.
La producción nueva empieza vacía. No se publica el Excel ni personal real.

Guía vigente: `deploy/V34_FASE2.md`. Entrega Windows mediante
`windows-local.yml`, con prueba real del ejecutable y Python incluido.
Fase 3 (analítica avanzada) y fase 4 (extras) pendientes. Las secciones siguientes
son históricas y no certifican que toda la especificación V33 esté implementada.

## Entrega actual

Versión 2.1 de pruebas controladas, requisitos V6, ampliada desde el prototipo Python/SQLite.
Python >= 3.11, biblioteca estándar, sin instalación de paquetes para ejecutar.
Interfaz industrial oscura en español para PC y móvil. Loopback por defecto;
modo LAN explícito con `--lan-ip` privada y SQLite en el disco de la PC principal.

La entrega V6 incorpora configuraciones SAP múltiples por código, marca/modelo
independientes, clasificación automática del sellado, órdenes de recepción con
proceso único, entregas sucesivas, pendientes y seguimiento, cierre con acta
inmutable PDF/JSON y reapertura motivada. Las actas anteriores siguen consultables.
Incluye inspección/calibración con error porcentual calculado, tasas de calidad,
comparativas A/B por actividad y unidad en cuatro granularidades y Excel/PDF.
La auditoría encadena SHA-256 y bloquea actualización, borrado y reemplazo SQL.
Las versiones históricas de formularios, los registros y las claves se conservan.

La actualización visual 2.1 toma las referencias de tableros suministradas por el
usuario: contadores de revisiones, aprobación y rechazo, anillos con denominador
explícito, tendencia temporal por actividad/unidad con fechas y ceros, seguimiento
por orden y tablas de productividad y comparativas por técnico y actividad.
Las variaciones A/B y tasas provienen del mismo alcance de las exportaciones.
Las metas requieren coincidencia de período, responsable, actividad y unidad;
las órdenes sin esperado no se convierten en un avance ficticio. No existe todavía
un vínculo revisión–orden para atribuir tasas de calidad a un lote de recepción.

Entrega 1.0.1: iniciadores Windows con comprobación de archivos del paquete,
instrucciones de extracción completa y mensajes separados para archivos ausentes,
Python no disponible y errores de ejecución. Responde a una captura del usuario
con Python 3.15.1 ejecutándose y app.py ausente en una carpeta temporal de WinRAR.
Entrega 1.0.2: la demo usa por defecto 8766 y la instalación normal 8765;
sesiones independientes por modo, aviso visible del modo en el acceso,
botones para completar accesos ficticios y tiempo restante en el bloqueo
temporal tras seis intentos fallidos. Mensaje claro si el puerto está ocupado.
Se conservan usuarios, contraseñas, registros y esquema de datos.

Presupuesto exigido: costo cero. Se retiró render.yaml y la propuesta de plan de
pago. Se implementó la demo estática completa para GitHub Pages con Python/WebAssembly,
SQLite persistida en IndexedDB por navegador y respaldo/restauración descargables.
Esta demo individual de Internet no equivale a una base central compartida.
Para una base compartida entre equipos ya está implementado el servidor LAN,
documentado en `deploy/RED_LOCAL.md`, sin contratar servicios. La sincronización
por Internet mediante una base central externa sigue siendo una fase posterior.

GitHub confirmó la publicación inicial del enlace https://joras30.github.io/one/
en la ejecución 39851621070, con construcción y despliegue correctos. La
distribución de V6 conserva IndexedDB y se actualiza en `gh-pages`. El workflow
**Construir demo gratuita** consulta el modo configurado: despliega si Pages usa
Actions; si usa una rama, Pages publica los cambios de esa rama. El entorno de
desarrollo bloquea el acceso directo a github.io; la publicación se verifica por
los resultados y el enlace que emite GitHub, además de probar la distribución local.

## Funcionalidades terminadas

- Seis actividades: limpieza o recuperación (una sola), revisión técnica,
  configuración, sellado, asignación y recepción.
- Registro por lote o serie, responsable y capturador separados, actividad fijada.
- SAP opcional en revisión, marca independiente y clasificación nuevo/recuperado
  distinta de aptitud para reutilizar. Catálogo SAP editable.
- Usuarios y roles, actividades habilitadas, cambio de clave opcional técnico,
  restablecimiento al código con invalidación de sesiones y contraseñas con hash.
- Actividades/formularios versionados; registros históricos conservan su versión.
- Historial, reingresos con alerta de misma fecha, correcciones, anulación,
  restauración y auditoría.
- Métricas por filtros y unidad, metas por persona/actividad/período, recepciones
  parciales con saldo global de la orden y aporte personal correctamente separados.
- Importación supervisada XLSX/CSV para revisión y sellado, vista previa,
  confirmación atómica y protección contra doble carga.
- Exportación de tablas CSV/XLSX/PDF, incluidos campos personalizados y operativos;
  gráficos PNG/SVG con título, filtros, período y unidades.
- Visitante de estadísticas agregadas sin detalle personal ni consulta por serie.
- Respaldo SQLite consistente antes de migrar y respaldo manual desde administración.
- Demo separada con personas y producción ficticias; primer inicio normal configura
  una cuenta administradora con contraseña elegida por su titular.

## Persistencia y migración

Se conservan tablas y registros originales, IDs, fechas, revisiones y verificadores
de contraseña. Las filas antiguas se incorporan por legacy_id y se reconcilian
inserciones tardías sin sobrescribir correcciones o eventos nuevos. El servidor
reserva el puerto antes de migrar para impedir un cambio de base cuando una
instancia anterior ocupa ese puerto. Esquema actual: 4.

La primera cuenta supervisora de una instalación antigua conserva su capacidad
administrativa mediante access_role, sin modificar el rol legado ni su clave.
La conservación en la instancia actual se comprobó contra la copia anterior.

## Archivos principales

- APLICACION_ACTUAL/app.py: HTTP, autenticación, usuarios, respaldo, CLI y demo.
- APLICACION_ACTUAL/production.py: actividades, eventos, métricas e importaciones.
- APLICACION_ACTUAL/documents.py: intercambio de archivos, sin dependencias externas.
- APLICACION_ACTUAL/operational.py: configuraciones SAP, órdenes, actas y cadena de auditoría.
- APLICACION_ACTUAL/analytics.py: calidad, calibraciones y comparativas por período.
- APLICACION_ACTUAL/static/: interfaz adaptable y gráficos exportables.
- APLICACION_ACTUAL/tests/test_application.py: integración HTTP y migración.
- tests/test_documents.py: archivos, límites y formatos de intercambio.

## Validación

- Analítica visual 2.1: **151 pruebas automatizadas correctas** en Linux/Python
  3.12: 74 de HTTP y 77 de dominio y documentos. Las 21 pruebas nuevas cubren
  intervalos con cero producción, unidades separadas, tasas, agrupación personal,
  metas compatibles incluso con producción cero, detalle de fallos, excedentes,
  corte histórico y privacidad. Las revisiones sin serie no se cuentan como reingresos.
- Interfaz 2.1: **145 comprobaciones de navegador** con datos ficticios, vistas a
  1440, 1280 y 390 píxeles, valores de curvas, anillo, avances, A/B por técnico,
  agrupaciones, fallos, filtros, plantillas, descargas SVG/PNG/Excel/PDF y roles.
- Distribución 2.1: **19 comprobaciones de Pages** y **16 de actualización desde
  el esquema 3**, conservando todas las 63 filas históricas y los verificadores de
  contraseña. Integridad SQLite y auditoría verificadas independientemente.

Las siguientes cifras documentan la entrega V6 anterior a la actualización visual:

- V6: **130 pruebas automatizadas correctas**: 74 de HTTP, permisos, migración,
  acceso LAN y perfil HTTPS; 56 de documentos, analítica y dominio.
- V6: **48 comprobaciones de navegador** en PC y móvil: SAP múltiple, sellado,
  importación, calibración, tasas, cuatro granularidades, órdenes, cierre,
  reapertura, acta PDF y huella, descargas, auditoría y alcance de cada rol.
- La distribución V6 de Pages pasó las 19 comprobaciones de persistencia,
  descargas, concurrencia entre pestañas y respaldo/restauración bajo una subruta.
- Actualización real de IndexedDB V3 a V4: **33 comprobaciones correctas**.
  Se conservaron las 63 filas históricas completas, sus versiones de formulario
  y todas las filas de usuarios, incluidos roles y verificadores de contraseña.
  Se comprobaron nuevas capturas, filtro Modelo, gráficos SVG/PNG, dos cierres,
  actas históricas PDF/JSON, recarga, integridad SQLite y ausencia de errores JS.
- Actualización con caché HTTP real: **21 comprobaciones correctas**. Los doce
  recursos antiguos permanecieron cacheados; al publicar y recargar, los nuevos
  recursos cargaron con una huella común, conservando sesión y 61 eventos.
- Compatibilidad verificada en CI: **130 pruebas en Windows/Python 3.15.1** y
  **130 en Linux/Python 3.12.15**, sin fallos, errores ni pruebas omitidas.
  Ejecución 39901295747: construcción y despliegue correctos. La publicación
  queda bloqueada si falla una plataforma. Se corrigieron la exclusividad del
  puerto en Windows y el cierre explícito de conexiones SQLite de respaldos.
- Regresiones V6: correcciones de entregas tras modificar el maestro, anulados
  en migración, conflicto de procesos históricos, saldos al corte, cálculos no
  finitos, formularios históricos ampliados y reemplazos SQL bloqueados.

Las siguientes comprobaciones corresponden a las entregas anteriores conservadas:

- 50 pruebas HTTP/migración/web correctas, incluidas seis actividades, permisos,
  reintentos concurrentes, campos históricos, respaldos restaurables y puerto ocupado.
- Las 10 pruebas de perfil web cubren dominio y origen HTTPS, cookies Secure,
  administración privada, cuentas compartidas, directorio exclusivo y reinicio.
- 22 pruebas de documentos correctas: CSV/XLSX/PDF, ceros iniciales, fechas,
  fórmulas y archivos malformados; lectura independiente de XLSX/PDF.
- 67 comprobaciones de navegador correctas: recorridos de interfaz, permisos,
  importación, versiones, cambio/restablecimiento de clave, respaldos y descargas.
- 28 comprobaciones adicionales de acceso 1.0.2 en navegador: modo visible,
  botones demo, setup normal, sesiones de ambos modos en el mismo navegador,
  cierre de sesión independiente y bloqueo con tiempo restante.
- 25 comprobaciones de la demo web con proxy HTTPS y certificado temporales
  exclusivamente locales: visitante, captura, administración privada y móvil.
  No equivalen a un despliegue comprobado en Render.
- 19 comprobaciones de la publicación gratuita real en navegador: acceso,
  captura, CSV/XLSX/PDF/SVG, persistencia al recargar, dos pestañas concurrentes,
  respaldo SQLite comprobado independientemente, restauración en otro navegador,
  rechazo de respaldo inválido y diseño móvil. Motor sin servidor de pago.
  Se repitió el recorrido bajo una subruta para verificar el alojamiento de Pages.
- Regresiones de bloqueo con reloj simulado, desbloqueo al vencer la espera,
  reinicio sin perder eventos, sesiones separadas y puertos por defecto distintos.
- Caso de restablecimiento repetido tras el ajuste final: desbloquea al técnico,
  revoca sus sesiones y conserva sus registros sin quitar el bloqueo de otro usuario.
- 26 comprobaciones adicionales del ZIP extraído en una carpeta nueva: configuración
  inicial por formulario, administrador elegido, seis actividades, demo de 60 eventos
  separada, acceso técnico y diseño a 390 px. Procesos temporales cerrados al terminar.
- Verificación específica adicional de título/filtros en los gráficos exportados.
- Vistas examinadas a 1440 y 390 px sin desbordamiento horizontal ni excepciones JS.
- Sintaxis Python y JavaScript comprobadas.

Las pruebas locales se ejecutaron en Linux/Python 3.12 y Chromium. La integración
continua verificó Windows/Python 3.15.1 y Linux/Python 3.12.15. No se ha ejecutado
en Safari ni dispositivos físicos. La adaptación visual móvil está
comprobada en navegador emulado; no equivale a una prueba física de la red de oficina.

## Límites y trabajo posterior

- Iniciadores locales, servidor LAN, perfil HTTPS propio y demo individual
  gratuita separados. La IP y la conectividad física de oficina las configura
  el usuario con su red autorizada; las pruebas de servidor usan loopback.
- Cada proceso de recepción identifica una orden de un SAP. Las entregas de
  ese proceso pueden ser sucesivas. Un material distinto requiere otro proceso.
- El acta verifica un cierre interno mediante su huella; no es una firma
  digital institucional. La auditoría append-only no sustituye permisos del
  sistema operativo ni un respaldo externo frente al dueño del archivo SQLite.
- Catálogo SAP completo pendiente del usuario; solo se precargó el ejemplo confirmado.
- Importación hasta 8 MB/5.000 filas y exportación hasta 10.000 filas por archivo,
  con rechazo explícito si se supera; no se truncan resultados silenciosamente.
- PDF admite español mediante WinAnsi; otros caracteres pueden aparecer como ?.
- Los respaldos locales deben complementarse con destino separado y política de
  retención en un despliegue real. No hay inventario integral de existencias.
- Validar con el usuario las plantillas reales y reglas operativas antes de cargar
  registros de trabajo. Las pruebas no importaron empleados ni registros reales.
