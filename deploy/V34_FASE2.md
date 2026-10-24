# V34: fase 2 para validación

La fase 1 fue validada por el solicitante. Esta entrega habilita la operación;
las fases 3 y 4 requieren su validación posterior. Conserva la paleta aprobada.

## Instalar o actualizar

Extrae el paquete Windows completo y abre `INICIAR_PRODUCCION.bat`. Python está
incluido y la ejecución es local, sin alojamiento de pago ni Internet.
Desde las fuentes: `python APLICACION_ACTUAL/app.py --production` (Python >=3.11).

Para actualizar, detén el programa, conserva la instalación anterior y copia
**toda** su carpeta `datos_produccion` junto al nuevo ejecutable antes de iniciarlo.
No sobreescribas esa carpeta con otra vacía. La migración es aditiva, conserva
usuarios, formularios históricos y registros y crea un respaldo antes de actualizar
las actividades. Una restauración de fase 1 se adapta a fase 2 al restaurar.

Una instalación nueva crea `admin` y muestra una clave temporal una vez. Cambia
la clave y completa el perfil. `RECUPERAR_ADMIN.bat`, ejecutado físicamente en la
PC principal, permite recuperar al administrador maestro con auditoría.

## Comenzar la operación

1. En **Catálogo maestro**, importa el Excel oficial del laboratorio. Se lee
   exclusivamente **DATOS**: marcas, tensiones, condiciones y artículos SAP.
   Revisa cantidades y confirma; el archivo y las personas no se publican.
   También puedes configurar las listas manualmente y confirmarlas.
2. Opcionalmente importa **PERSONAL** mediante su botón independiente.
   Revisa nombres, códigos y puestos; los usuarios existentes no cambian de clave
   ni se sobrescriben. Las nuevas claves temporales aparecen una sola vez.
3. En **Asignaciones**, da a cada técnico las actividades y permisos necesarios.
   Todos los supervisores pueden gestionar todos los técnicos. El supervisor
   responsable identifica a quién se reporta directamente, sin restringir acceso.
4. En **Captura**, elige actividad, responsable y fecha. El registro delegado
   requiere un motivo. En carga rápida fija los parámetros y captura las series.
5. En **Carga masiva**, descarga la plantilla actual, llena las filas y vuelve
   a cargarla. Revisa errores, quita filas o justifica repetidos y revalida.
   No se escribe producción hasta confirmar; la confirmación revalida todo y
   guarda el conjunto de manera atómica.
6. Configura **Instalación y respaldos** con una o dos carpetas autorizadas
   de la operativa. No se exige USB ni que las carpetas estén en discos distintos.
   La base activa se guarda localmente; las carpetas de red reciben copias.

## Reglas implementadas

- Artículos identificados por **SAP + valoración** (Nuevo / Recuperado-Reparado).
  Marca y voltaje no quedan atados rígidamente al código. La descripción se
  administra en catálogo. El sellado toma su valoración del artículo elegido.
- Excel real con desplegables vivos y guía de referencia. Series, sellos y
  códigos se generan como texto; las cargas rechazan identificadores numéricos
  de Excel para evitar pérdida silenciosa de ceros iniciales.
- Un repetido solo avisa en la misma actividad, serie, condición y fecha.
  Requiere quitarlo o escribir una justificación. Ambas decisiones se auditan.
- **Número de sello + color** se reserva permanentemente. También se revisan
  duplicados entre filas del mismo archivo. Un sello anulado sigue reservado.
  Los dos sellos de un medidor no pueden ser iguales. No se permite corregir un
  sellado cambiando su identidad; corresponde anular y registrar los correctos.
- Historial por serie y ciclos. Cambiar de día no crea por sí solo otra llegada:
  revisión y sellado pueden abarcar varios días del mismo ingreso. Una revisión
  posterior a un sellado, o un nuevo sellado tras uno anterior, abre otro ciclo
  automáticamente; “Nuevo ingreso” permite indicar una llegada distinta.
  Al resellar se conservan los sellos anteriores como retirados.
- Permisos temporales por actividad: ver, capturar, cargar, proponer bajas y
  consultar panel. Vencen según el horario configurado; revocación inmediata.
  Las actividades nuevas usan campos y catálogos configurables y generan su
  formulario, plantilla y panel básico. No generan código arbitrario nuevo.
- Bajas individuales y masivas con piezas y cantidades. El técnico autorizado
  propone; el supervisor autoriza o rechaza con motivo. La serie solo se inactiva
  al autorizar, permanece consultable y no recibe nuevas actividades. Solo admin
  revierte, con motivo. Las solicitudes pendientes siguen en su bandeja.
- Recepción por proceso, proveedor, entregas parciales, pendientes, cierre con
  acta y reapertura motivada. Las actas anteriores permanecen consultables.
- Resumen **MEDIDORES RECUPERADOS CARGADOS A SAP** desde sellados válidos,
  por fecha y valoración, almacenes 3001/3007 y movimiento 501. Fecha de
  contabilización editable, cantidades con consulta de series y Excel/PDF/CSV.
  El sistema genera el archivo; no se conecta a SAP ni confirma carga efectiva.

## Fichas y captura sin conexión

**Personal** ofrece tarjetas seleccionables y búsqueda. Supervisores consultan
los datos generales de todos los técnicos; administradores, todos los perfiles.
La pestaña “Técnicos a cargo” muestra el equipo directo del supervisor.
Los técnicos ven su propia ficha y no el directorio. Foto opcional, avatares y
colores se conservan. Estadísticas avanzadas se identifican como fase 3 pendiente.

El formulario individual conserva un borrador local y, si falla el envío, una
cola vinculada a usuario e instalación. “Revisar y sincronizar” revalida permisos,
bajas, repetidos y sellos; muestra conflictos sin guardar en silencio. Los reintentos
conservan el identificador de operación para evitar duplicar una escritura cuya
respuesta se perdió. Se conserva la fecha seleccionada al capturar. La carga
masiva requiere conexión al servidor para validar y confirmar. No borres datos
del navegador mientras haya pendientes sin sincronizar.

## Respaldar y recuperar

“Crear copia local ahora” crea un `.db` en el servidor; la lista identifica la
más reciente y permite descargarla. Para una recuperación normal, elige la copia
más reciente anterior al problema. Guarda la descarga en una carpeta segura;
no necesita estar junto al programa. Para restaurar usa el formulario integrado,
revisa su vista previa y confirma con contraseña y motivo. **Restaura el estado
completo de esa copia**, no combina datos. Conserva otro respaldo del estado
actual antes de restaurar. Los archivos de respaldo contienen información del
personal: aplica permisos de carpeta de la empresa, además de los de la app.

## Pendiente de fases siguientes

- **Fase 3:** analítica completa, metas y alertas, jornadas/asistencia, estadísticas
  y radar de fichas, comparativas y constructor de reportes a medida.
- **Fase 4:** cierre diario, etiquetas, acta de conduce, muestreo, scanner avanzado,
  notificaciones en vivo y monitor de pared.

Los paneles operativos básicos de fase 2 no equivalen a esos módulos completos.
La demo pública sigue siendo de evaluación, con datos separados por navegador;
la producción y su base central corresponden al paquete local.
