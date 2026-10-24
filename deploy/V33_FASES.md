# V33 · Entrega por fases y validación

La especificación vigente es la versión 33 entregada por el solicitante. Su
instrucción es construir y validar cada fase antes de pasar a la siguiente.

| Fase | Alcance | Estado de esta entrega |
|---|---|---|
| 1 · Base | Instalación local, accesos, roles, perfil, auditoría, respaldo y restauración | Implementada para revisión y prueba del solicitante |
| 2 · Operación | Catálogo oficial, actividades, plantillas, ciclos, repetidos, sellos únicos, bajas y permisos temporales | Pendiente de aprobación de fase 1 y desarrollo V33 |
| 3 · Análisis | Paneles por actividad, metas y jornadas, fichas, comparaciones y reportes V33 | Pendiente; se conservan las vistas anteriores de demostración |
| 4 · Extras | Cierre diario, etiquetas, conduce, muestreo, notificaciones y monitor | Pendiente |

## Instalar la base en Windows

1. Descarga la versión de revisión **V33 · Fase 1 local** desde Releases.
2. Extrae **todo** el ZIP en una carpeta del disco local de la PC principal.
3. Abre `INICIAR_PRODUCCION.bat`. El ejecutable incluye Python y funciona sin Internet.
4. La consola muestra `admin` y una clave temporal **una sola vez**. Entra con ella.
5. Cambia la clave, entra nuevamente y completa tu perfil.
6. En **Instalación y respaldos**, configura las dos carpetas externas y la hora.
7. Ejecuta una copia de prueba. **Correcto** significa que existen la copia local
   y las dos externas verificadas. **Incompleto** significa que falta atención.

El primer inicio no carga personas ni producción real. La base se crea en
`datos_produccion`, al lado del ejecutable. Esa carpeta se conserva al actualizar.
`INICIAR_PRUEBAS.bat` utiliza otra base y datos ficticios.

Para iniciar desde las fuentes con Python 3.11 o superior:

```sh
python APLICACION_ACTUAL/app.py --production
```

## Compartir la base por la red local

Usa `INICIAR_RED.bat` e introduce la IP privada fija de la PC principal. Los demás
equipos abren el enlace mostrado, por ejemplo `http://192.168.1.20:8765`.
La base permanece en el disco local de esa PC; no se coloca SQLite en una carpeta
compartida. La dirección y conectividad real deben corresponder a la red autorizada
de la oficina. Las pruebas de desarrollo utilizan exclusivamente `127.0.0.1`.

## Usuarios, claves y equipos

- Administración crea los perfiles permitidos y asigna el supervisor de un técnico.
- Un supervisor crea técnicos de su equipo y gestiona sus accesos; no gestiona los
  técnicos de otro supervisor ni perfiles privilegiados.
- Cada acceso nuevo recibe una clave temporal, mostrada al crearlo. Al entrar,
  cambia la clave y completa nombre, cédula, nacimiento, teléfono, flota y puesto.
- Restablecer un técnico genera otra clave temporal y cierra sus sesiones.
- La clave actual se almacena con hash PBKDF2, nunca de forma consultable.
- La auditoría general de producción está reservada a Administración.

Si se pierde la clave maestra, cierra el servidor y abre `RECUPERAR_ADMIN.bat`
directamente en la PC principal. Es obligatorio confirmar y explicar el motivo.
La recuperación queda auditada y genera otra clave temporal. No existe una ruta
HTTP de recuperación maestra. Otra instancia no puede ejecutarla con el servidor abierto.

## Respaldos y restauración

Configura dos carpetas en unidades distintas entre sí y distintas del disco de
la base: por ejemplo, un disco externo y una ubicación de red en otro equipo.
Dos carpetas del mismo disco se rechazan. El administrador debe confirmar que
corresponden a ubicaciones físicas diferentes; los identificadores de volumen no
permiten demostrar por sí solos cómo está construido el almacenamiento físico.

La copia programada se ejecuta mientras la PC y la aplicación están encendidas.
Si la PC estaba apagada a la hora programada, el sistema recupera la copia pendiente al volver a iniciar la aplicación.
Cada copia utiliza un snapshot consistente de SQLite y compara su SHA-256. Si un
destino falla se conserva la copia local, se intenta el otro y se informa
**Incompleto**. No se declara éxito de dos copias si falta una. Los fallos se
reintentan sin convertir carpetas de un montaje desconectado en destinos válidos.

Para restaurar, elige un archivo de las carpetas configuradas, verifica la vista
previa y revisa las cantidades. Confirma con tu contraseña, un motivo y la palabra
`RESTAURAR`. Se guarda una copia previa, se reemplaza la base con las solicitudes
pausadas y se cierran las sesiones. Entra con las credenciales del respaldo.
Se rechaza restaurar una demo sobre producción.

## Apariencia y explicación

El selector del encabezado cambia entre modo claro y oscuro. En **Mi cuenta → Mi
avatar** puedes elegir azul, naranja, verde o violeta. El patrón deriva del perfil
y no acredita una profesión ni concede permisos. El color se guarda en la base y
se incluye en los respaldos. Cada pantalla incluye ayuda contextual.

## Excel recibido

`CONSOLIDACION DE DATOS 2026.xlsx` contiene siete hojas: registro diario, sellado,
recuperados cargados a SAP, listas, datos, referencia de tablas y personal. Se
analizó su estructura sin publicar el archivo ni nombres del personal. Su catálogo
y formatos se incorporarán en la fase 2: la identidad SAP será código + valoración.
Las fotos sirven como referencia visual; los cálculos se basarán en los registros.

## Validación que corresponde al solicitante

1. Abrir el ejecutable en la PC principal y completar el primer ingreso.
2. Crear un supervisor y un técnico ficticio; comprobar el cambio obligatorio de
   clave y que el supervisor solo gestiona su equipo.
3. Conectar los dos destinos reales y comprobar una copia **Correcta**.
4. En una instalación de prueba, verificar y restaurar una copia conocida.
5. Abrir el enlace LAN desde otro equipo autorizado y revisar la lectura en móvil.

Después de esa revisión se solicita la validación de la fase 1. La captura real,
el bloqueo de sellos y las bajas V33 se implementarán y validarán en la fase 2.

## Ajuste 33.0.1 después de la prueba del solicitante

- El cierre de sesión elimina el formulario personal de la pantalla. Al cambiar de cuenta se vuelve a consultar únicamente el perfil de su titular; una respuesta pendiente de otra cuenta se descarta. Los nuevos accesos conservan su propio nombre y puesto, y sus demás datos personales empiezan vacíos.
- «Crear copia local ahora» funciona sin destinos externos. El mensaje indica la ruta y permite descargar la copia desde «Copias locales disponibles». «Protección dual incompleta» significa que faltan las dos copias externas; no significa que la copia local falló.
- Las unidades F:, H:, I: y W: de un mismo servidor no prueban que sean medios físicos independientes. Para la protección dual se requieren dos ubicaciones independientes de la PC principal y entre sí; por ejemplo, una carpeta de red autorizada y un disco externo diferente. La aplicación no cambia permisos ni configura carpetas del servidor.
- Galería de avatar: clásico, cabello corto y cabello largo, además de cuatro colores. El rol y sus permisos siguen asignados por administración; elegir dibujo no cambia el rol.
- Fichas básicas de identificación en Mi cuenta y Colaboradores, con nombre, puesto, usuario y estado de acceso. Las fichas completas con métricas, jornadas, ranking y comparaciones siguen pendientes de la fase 3.
- Mejor contraste en textos, información del perfil, controles y selector de avatar en modo claro.

Para actualizar: cerrar la aplicación anterior, extraer el nuevo ZIP en otra carpeta y copiar la carpeta completa `datos_produccion` de la instalación anterior junto al nuevo ejecutable. No sobrescribir esa carpeta con datos de prueba. Los usuarios y perfiles ya guardados se conservan. La base de datos debe seguir en el disco local de la PC principal.
