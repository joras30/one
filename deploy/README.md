# Publicar la demo para evaluación

La propuesta permite compartir un enlace HTTPS con el jefe y otros evaluadores.
La demo utiliza personas y producción ficticias. El enlace permite acceder como
visitante o colaborador de prueba; la administración tiene una clave privada.

El archivo [render.yaml](../render.yaml) está preparado para revisión. No se ha
creado un servicio de Render ni aceptado un cargo mediante estos archivos.
La cuenta de Render puede crearse sin desplegar un servicio de pago. La propuesta
usa el plan `starter` y un disco persistente de 1 GB: revisa los precios vigentes
que Render muestre antes de confirmar el despliegue. No se indica una tarifa
porque no se ha comprobado en una cuenta del proveedor.

## Cuenta nueva y conexión del repositorio

1. Abre [Render](https://dashboard.render.com/register) y crea tu cuenta. Puedes
   utilizar la opción de GitHub para conectar el repositorio con menos pasos.
2. En la conexión con GitHub, concede acceso al repositorio `joras30/one`.
   La publicación preparada utiliza exclusivamente la rama `demo-web`.
3. Comprueba que esa rama contenga `render.yaml` y
   `APLICACION_ACTUAL/web_demo.py`. La rama debe estar publicada en GitHub antes
   de que Render pueda leerla; preparar los archivos localmente no los publica.
4. En Render, elige **New → Blueprint**, selecciona el repositorio y la rama
   `demo-web`, y revisa la configuración detectada en `render.yaml`.
5. Verifica el plan, el disco de `/var/data`, una única instancia y el importe
   que indique el proveedor. La creación y cualquier coste se confirman aquí,
   desde la cuenta de su titular; todavía no se han aceptado.
6. Cuando decidas continuar, inicia el despliegue. Render construirá la app y
   asignará su enlace HTTPS. Comparte ese enlace una vez que el estado sea
   **Live** y se hayan completado las comprobaciones de abajo.

No compartas tu contraseña de GitHub o Render ni tokens de acceso. La conexión
del repositorio se realiza mediante las pantallas del proveedor. Para una revisión
del trabajo basta con compartir el enlace de la aplicación.

## Configuración preparada

| Ajuste | Valor y propósito |
|---|---|
| Ejecución | Python nativo, sin paquetes adicionales para la aplicación. |
| Construcción | `python3 -m compileall -q APLICACION_ACTUAL`. Comprueba sintaxis; no sustituye las pruebas funcionales. |
| Inicio | `python3 -u APLICACION_ACTUAL/web_demo.py`. |
| Disponibilidad | `/healthz`, con JSON de estado sin usuarios ni registros. |
| Dirección HTTPS | El perfil web utiliza `RENDER_EXTERNAL_URL`, asignada por Render. |
| Dirección alternativa | `LAB_PUBLIC_ORIGIN` permite configurar un origen HTTPS exacto si se prepara un dominio propio. |
| Puerto | `PORT`, proporcionado por Render. No hace falta introducirlo manualmente. |
| Datos | `LAB_DATA_DIR=/var/data/laboratorio-demo`, dentro del disco persistente. |
| Administración | Usuario `supervisor_demo` y `LAB_ADMIN_PASSWORD` inicial generada como secreto por Render. |
| Escala | Una instancia; esta demo usa SQLite en el disco local del servicio. |
| Actualizaciones | Los commits en `demo-web` activan un nuevo despliegue. |

El perfil web escucha en `0.0.0.0` dentro del servicio después de validar el origen
HTTPS. La aplicación local conserva su inicio mediante los archivos `.bat`.
El disco almacena la base y sus respaldos fuera del código que se reemplaza al
actualizar. Esta propuesta no monta la base en una carpeta de red.

El acceso de administración se consulta en la variable secreta del servicio desde
la cuenta de Render. Guárdalo de forma privada y compártelo solo con quienes deban
administrar la demo. La clave pública de la demo local no corresponde a esta
administración web. Si cambias la clave desde la aplicación, utiliza la nueva:
la variable es para la creación inicial, no una copia de la contraseña actual.

## Comprobar el enlace antes de compartirlo

1. Abre el enlace HTTPS asignado y confirma que se identifique como demo de
   evaluación con datos ficticios.
2. Entra mediante el acceso de visitante y revisa los indicadores; prueba el
   acceso de colaborador para evaluar la captura y sus permisos.
3. Verifica el acceso privado de administración y una exportación de prueba.
4. Crea un registro ficticio identificable, reinicia el servicio desde Render y
   comprueba que el registro siga allí. Esta comprobación confirma que el servicio
   está utilizando el disco que configuraste.
5. Abre el mismo enlace desde el celular y desde otro equipo. Los cambios
   guardados corresponden a la demo compartida.

El éxito de las pruebas locales no confirma por sí solo el funcionamiento en
Render. La disponibilidad externa, HTTPS, persistencia y acceso desde dispositivos
deben comprobarse después de desplegar en la cuenta elegida.

## Actualizar sin descargar archivos en los equipos

Los cambios de código se publican en la rama `demo-web` de GitHub. Render detecta
el commit y despliega esa versión; los evaluadores vuelven a cargar la página.
En el panel del servicio puedes comprobar qué commit se está ejecutando y revisar
los registros del despliegue.

Antes de actualizar, genera un respaldo desde la cuenta administradora. Las
migraciones del sistema conservan los registros y hacen una copia antes de cambiar
el esquema. Los registros de evaluación siguen en `/var/data/laboratorio-demo`;
no reemplaces ese directorio con archivos del repositorio ni recrees el disco para
una actualización normal. El servicio puede tener una interrupción durante el
despliegue de su única instancia.

Conserva además copias en otro destino autorizado. Los respaldos dentro del mismo
disco no protegen de la pérdida o eliminación de ese disco. Una reversión de código
debe comprobar su compatibilidad con el esquema de datos antes de ejecutarse.

## Qué se publica

La rama de despliegue debe contener solo los fuentes necesarios, los archivos de
inicio y la documentación de la demo. La lista en
[ARCHIVOS_PUBLICABLES.txt](ARCHIVOS_PUBLICABLES.txt) sirve para revisar esa selección.
Las bases, respaldos, sesiones, `.env`, documentos originales y archivos con
empleados reales quedan fuera de la publicación.

Esta configuración corresponde a una demo pequeña con datos ficticios. El uso
operativo con empleados o registros reales requiere su despliegue y revisión de TI,
política de respaldos y validación de concurrencia antes de ampliar su alcance.
