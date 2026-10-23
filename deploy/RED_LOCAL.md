# Usar la misma base en la red de la oficina

La PC principal ejecuta Python y guarda SQLite en su propio disco. Las otras PCs,
tabletas o celulares abren el mismo enlace en el navegador. Así todos consultan
la misma instalación y las operaciones se guardan en una base compartida por el
servidor. No instales Python en los equipos clientes ni copies allí la base.
Este modo no contrata servicios y no depende de GitHub Pages.

## Preparar la PC principal

1. Extrae el paquete completo en una carpeta local de la PC principal, por ejemplo
   `C:\Laboratorio`. No ejecutes el iniciador dentro de WinRAR.
2. Comprueba `py --version`: se requiere Python 3.11 o superior, sin paquetes
   adicionales para ejecutar la aplicación.
3. Solicita a TI una reserva DHCP para esta PC o utiliza la IP fija que ya tenga
   asignada. Con `ipconfig` identifica su **Dirección IPv4** de la red de oficina.
   `192.168.1.20` es solo un ejemplo; debes utilizar la IP real de tu PC.
4. Abre `APLICACION_ACTUAL\iniciar.bat` primero en la PC principal y crea la cuenta
   administradora si es una instalación nueva. Conserva la carpeta
   `APLICACION_ACTUAL\datos_locales` de una instalación anterior y sus respaldos:
   contiene los usuarios, contraseñas y registros que se deben actualizar.
5. Cierra esa consola antes de iniciar el modo de red para liberar el puerto.

## Iniciar y compartir

En la PC principal abre **`APLICACION_ACTUAL\iniciar_red.bat`** e introduce su IP
privada cuando el iniciador la solicite. También puedes ejecutar desde esa carpeta:

```sh
py app.py --lan-ip 192.168.1.20
```

La consola muestra el enlace real, por ejemplo **http://192.168.1.20:8765**.
Abre ese mismo enlace en las PCs de la oficina y en el celular conectado a su
Wi-Fi. Mantén la PC principal encendida y la consola abierta. Cada persona entra
con su propio usuario; el rol y los permisos se verifican en el servidor.

La dirección usa HTTP en una red privada de confianza. HTTP no cifra contraseñas
ni registros durante el tránsito; un despliegue institucional debe usar la red
autorizada y, cuando TI lo disponga, un proxy HTTPS con certificado. No compartas
este enlace mediante Internet, reenvío de puertos o una Wi-Fi pública.

## Prueba separada con datos ficticios

Para una evaluación en oficina sin mezclar registros laborales, ejecuta:

```sh
py app.py --demo --lan-ip 192.168.1.20
```

El enlace de esa demostración usa el puerto **8766** y una carpeta `datos_demo`
separada. Todas las PCs que abran ese enlace verán la misma base de demostración
de la PC principal. La versión GitHub Pages sigue teniendo una base independiente
por navegador; sus respaldos y accesos de prueba no sustituyen la instalación LAN.

## Si no abre desde otro equipo

- Verifica que la consola indique la IP correcta y que la PC esté encendida.
- Incluye el puerto `:8765` (o `:8766` en demo) en el enlace y usa **http://**.
- Asegúrate de que el celular use la Wi-Fi de oficina, no los datos móviles ni una
  red de invitados que aísle los dispositivos.
- Si la consola informa que la IP no está asignada, comprueba `ipconfig`. El
  programa no asigna IPs ni cambia la configuración del equipo.
- Si el puerto ya está ocupado, cierra la consola anterior de la aplicación.
- Si la red o Windows bloquea el acceso, pide a TI revisar la conexión autorizada.
  El iniciador no modifica el firewall ni las políticas de la oficina.

El servidor escucha exclusivamente en la IP privada indicada; rechaza direcciones
públicas, `0.0.0.0`, nombres DNS y orígenes distintos. En modo LAN las solicitudes
que modifican datos requieren el origen exacto del enlace y el token CSRF de la
sesión. La dirección `localhost` no sustituye al enlace LAN en este modo.

## Base y actualizaciones

SQLite permanece en `APLICACION_ACTUAL\datos_locales\laboratorio.db`, en el disco
de la PC principal. No pongas esa carpeta en unidades compartidas `F:`, `H:`, `I:`,
`W:`, rutas `\\servidor\carpeta` ni carpetas sincronizadas mientras se usa.
El modo LAN rechaza rutas UNC y unidades que Windows identifica como remotas.
Los navegadores acceden por HTTP: nunca abren directamente el archivo SQLite.

Para utilizar otra carpeta **local** puedes ejecutar:

```sh
py app.py --lan-ip 192.168.1.20 --data-dir C:\DatosLaboratorio
```

Antes de actualizar, genera un respaldo desde Administración y conserva una copia
en un destino separado autorizado. Detén la consola, actualiza el código de la PC
principal y conserva intactas las carpetas de datos. Vuelve a iniciar el mismo
modo y la misma carpeta; la migración conserva registros y accesos. Los clientes
solo recargan su navegador. Para volver al modo exclusivo de esa PC, cierra el
modo de red y abre `iniciar.bat`.

Las pruebas automatizadas de esta entrega usan datos ficticios y sockets
`127.0.0.1`. No se ha probado ni modificado la red física de la oficina, Windows
ni sus reglas de firewall desde este entorno.
