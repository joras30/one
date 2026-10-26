# V34.1 · Correcciones de actividades para revisión

Se retoma la validación por actividades. Esta entrega no constituye aprobación
de las fases posteriores ni del PDF integral, que deja de guiar el orden de trabajo.

- Botón flotante **Registrar actividad** disponible desde las pantallas autorizadas.
- Nombre **Registro de actividades del laboratorio**; captura individual y carga
  masiva accesibles en el mismo lugar.
- Revisión: fecha, técnico responsable, marca/modelo, serie, voltaje, condición,
  resultado de reutilización, observaciones y artículo SAP/valoración. Se retiran
  calibración, modelo adicional y otros campos señalados. SAP pasa a ser requerido,
  también en configuración y limpieza/recuperación.
- Resultados **Reutilizable / No reutilizable / Pendiente**. Los datos anteriores
  Apto/No apto se conservan y se interpretan en sus cálculos sin reescribirlos.
- Condiciones iniciales adicionales: Bueno, Condiciones óptimas y Dentro de lo
  establecido. Se administran en catálogo.
- Asignación de medidores/sellos retirada. Sellado solo se importa masivamente y
  tiene el panel **MEDIDORES SELLADOS EN EL LABORATORIO**. Se mantienen las reservas
  permanentes número de sello + color, aun tras anulaciones.
- **MEDIDORES RECUPERADOS CARGADOS EN SAP** registra archivos de movimientos,
  independientes de los sellados. No atribuye producción a técnicos: el importador
  queda identificado para auditoría. No contabiliza ni envía nada dentro de SAP.
- Cada fila de revisión o sellado se atribuye al empleado de la planilla, no al
  supervisor que la subió. El técnico solo puede importar su propia producción.
- Plantillas oficiales: revisión con nueve columnas (incluido SAP), sellado con
  diez y movimientos SAP con seis. Título, encabezados, guía y desplegables vigentes.
  No se agregan columnas de valoración o motivo; parámetros comunes fuera del
  archivo permiten resolver códigos con ambas valoraciones sin inventar datos.
- Si un código de sellado es ambiguo, se usa su Tipo cuando identifica valoración
  o se exige elegir la valoración común. Una ambigüedad no se guarda silenciosamente.
- Un archivo confirmado no se importa dos veces por repetir la carga. La vista
  previa, la confirmación y las decisiones de filas se revalidan en transacción.
- Bajas y piezas queda deshabilitado y conserva su historial. Provenía del punto
  12 del prompt V33; no se reactiva hasta una decisión posterior del solicitante.
- Catálogo con controles por fila para editar o retirar marcas, condiciones y
  otros valores. Los artículos se editan desde su selección. Retirar es lógico,
  para conservar registros. Cambiar identidad SAP implica crear otro artículo y
  retirar el anterior si corresponde; modificar descripción no cambia identidad.

## Estadísticas y documentos

Panel general y apartados propios de sellado y movimientos SAP. Contadores
separados por actividad/unidad, evolución por fecha, comparación con el período
anterior de igual duración, totales mensuales, ranking y matriz diaria por técnico.
SAP se excluye de ranking y producción individual. Fechas, unidades y denominadores
explícitos; crecimiento sin base se identifica sin inventar porcentajes.

Las tablas se despliegan por apartado; los gráficos y cantidades abren el origen
con el mismo filtro. Excel/PDF/CSV usan las mismas consultas. Los gráficos se pueden
compartir como PNG de alta resolución. La matriz diaria admite hasta 31 días;
mensual y ranking permiten rangos mayores. Promedio individual calculado sobre
días con producción efectiva; jornadas/incidencias aún no están integradas.

La comparación temporal no determina por sí sola cumplimiento de metas ni calidad.
Reutilización = reutilizables / evaluados (reutilizables + no reutilizables), con
pendientes separados. Se conserva la paleta aprobada y el acceso por rol.

## Actualizar

Cierra el servidor, conserva la instalación anterior y un respaldo. Extrae todo el
ZIP nuevo y copia **datos_produccion completa** junto al ejecutable nuevo. Inicia
INICIAR_PRODUCCION.bat. La actualización crea respaldo y versiona formularios sin
borrar producción. Si restauras una copia anterior se vuelven a aplicar los ajustes.

Para revisar: entrar, registrar una revisión delegada, descargar los tres modelos,
importar archivos ficticios, abrir el panel de sellado y el de movimientos SAP,
comprobar atribución, duplicados, detalle de cifras y exportaciones. La red real
se valida en la oficina; las pruebas de desarrollo solo usan loopback y datos ficticios.
