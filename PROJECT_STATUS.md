# Laboratorio de Medidas — Control de Producción

## Entrega actual

Versión 1.0 de pruebas locales, ampliada desde el prototipo Python/SQLite.
Python >= 3.11, biblioteca estándar, sin instalación de paquetes para ejecutar.
Interfaz en español para PC y móvil. Escucha exclusiva en loopback.

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
pago. Se prepara la demo estática completa en GitHub Pages con Python/WebAssembly,
SQLite persistida en IndexedDB por navegador y respaldo/restauración descargables.
Esta demo individual no equivale a una base central compartida. La conexión a
una base gratuita de servidor queda pendiente de proyecto, migraciones y permisos.

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
instancia anterior ocupa ese puerto. Esquema actual: 3.

La primera cuenta supervisora de una instalación antigua conserva su capacidad
administrativa mediante access_role, sin modificar el rol legado ni su clave.
La conservación en la instancia actual se comprobó contra la copia anterior.

## Archivos principales

- APLICACION_ACTUAL/app.py: HTTP, autenticación, usuarios, respaldo, CLI y demo.
- APLICACION_ACTUAL/production.py: actividades, eventos, métricas e importaciones.
- APLICACION_ACTUAL/documents.py: intercambio de archivos, sin dependencias externas.
- APLICACION_ACTUAL/static/: interfaz adaptable y gráficos exportables.
- APLICACION_ACTUAL/tests/test_application.py: integración HTTP y migración.
- tests/test_documents.py: archivos, límites y formatos de intercambio.

## Validación

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

Ejecutado en Linux, Python 3.12 y Chromium. No se ha ejecutado en Windows,
Python 3.15, Safari ni dispositivos físicos. La adaptación visual móvil está
comprobada en navegador emulado, sin afirmar un despliegue de red.

## Límites y trabajo posterior

- Iniciadores locales, perfil HTTPS propio y demo individual gratuita separados.
  GitHub Pages requiere activación de Actions en los ajustes del repositorio.
- Catálogo SAP completo pendiente del usuario; solo se precargó el ejemplo confirmado.
- Importación hasta 8 MB/5.000 filas y exportación hasta 10.000 filas por archivo,
  con rechazo explícito si se supera; no se truncan resultados silenciosamente.
- PDF admite español mediante WinAnsi; otros caracteres pueden aparecer como ?.
- Los respaldos locales deben complementarse con destino separado y política de
  retención en un despliegue real. No hay inventario integral de existencias.
- Validar con el usuario las plantillas reales y reglas operativas antes de cargar
  registros de trabajo. Las pruebas no importaron empleados ni registros reales.
