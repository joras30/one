# Publicación gratuita para evaluación

El requisito es costo cero. Esta publicación utiliza GitHub Pages en el repositorio
público `joras30/one`, sin contratar servicios ni registrar una tarjeta. Se retiró
la propuesta de pago y su archivo render.yaml. No se ha contratado ningún servicio.

## Activar GitHub Pages una vez

1. Abre https://github.com/joras30/one/settings/pages con tu cuenta de GitHub.
2. En **Build and deployment → Source**, selecciona **Deploy from a branch**.
3. En **Branch**, selecciona **gh-pages** y la carpeta **/(root)**.
4. Pulsa **Save**. La rama `gh-pages` ya contiene la distribución preparada.
5. Espera a que GitHub termine de publicar y abre https://joras30.github.io/one/.
   Comparte el enlace después de comprobar que responde.

Estos pasos activan Pages, sin contratar un plan. El repositorio debe permanecer
público para utilizar esta modalidad gratuita. Las bases y documentos de empleados
no forman parte de la publicación.

## Qué incluye la demo

La interfaz y las reglas Python existentes se ejecutan dentro del navegador con
Pyodide y SQLite. Permite probar actividades, usuarios ficticios, formularios,
historial, filtros, importaciones, exportaciones y gráficos. La primera carga
descarga el motor de la demo; las siguientes aprovechan la caché del navegador.
Los accesos de prueba aparecen en pantalla y solo corresponden a datos ficticios.

La base se conserva en IndexedDB de ese navegador, en la misma dirección del sitio.
Actualizar la aplicación conserva esa prueba. Cada visitante tiene su propia base:
los cambios del jefe en su celular no aparecen automáticamente en tu PC.
Los perfiles de esta demo no protegen información frente a quien controla el
navegador. Utiliza únicamente datos ficticios.

## Respaldar y trasladar la prueba

Pulsa **Descargar respaldo** para guardar una copia completa de tu demo, incluidos
registros, actividades y usuarios de prueba. **Restaurar respaldo** permite cargarla
en otro navegador después de confirmar que reemplazará su prueba actual.
La restauración valida formato, checksum e integridad SQLite antes de aplicar cambios.
Al restaurar tendrás que iniciar sesión de nuevo.

Borrar los datos del sitio, cambiar de navegador o usar navegación privada puede
dejarte sin esa copia local; conserva respaldos descargados. Las exportaciones de
tablas y gráficos siguen disponibles para compartir resultados puntuales.
La demo admite una base de hasta 23 MB; un cambio que supere ese límite no se
confirma en el almacenamiento persistente y conserva la versión anterior.

## Actualizaciones sin descargar ZIP

Los commits en `demo-web` ejecutan **Actions → Construir demo gratuita**
(`.github/workflows/pages.yml`): instala las dependencias fijadas, construye y
verifica la distribución y guarda el artefacto `demo-github-pages` durante un día.
El workflow consulta el modo que ya esté configurado en Pages. Cuando es
**GitHub Actions**, publica ese mismo artefacto automáticamente. Cuando es
**Deploy from a branch**, deja la publicación a la rama configurada y evita
intentar un despliegue incompatible.

Para entregar una actualización, se construye la distribución y se actualiza su
contenido en la raíz de la rama `gh-pages`, incluido `.nojekyll`. GitHub Pages
publica los cambios de esa rama. Los evaluadores solo recargan el mismo enlace,
sin descargar un ZIP. El generador no incluye bases SQLite, documentos originales
ni empleados reales.

```sh
cd browser-demo
npm ci
npm run build
```

El resultado que se publica en `gh-pages` está en `dist/github-pages/`.
La capa gratuita reutiliza
`APLICACION_ACTUAL/` sin instalar Python ni abrir un servidor en el equipo evaluador.

## Datos compartidos a costo cero

El proyecto de referencia también publica una demo por navegador: su flujo Pages
fija `VITE_BACKEND=local`. Para sincronizar registros entre personas ofrece una
conexión opcional a Supabase. GitHub Pages con Supabase gratuito es una ruta posible
para la siguiente fase, dentro de los límites del proveedor.
Esa conexión central aún no está implementada aquí ni existe un proyecto creado
para ella. Requiere cuenta propia, migraciones y permisos del lado servidor.
Esta demo individual no debe presentarse como una base compartida.

Para compartir una base entre los equipos de la oficina ya está disponible el
servidor local documentado en [RED_LOCAL.md](RED_LOCAL.md): todos abren el enlace
de la PC principal y SQLite permanece en su disco. Este modo no usa el
almacenamiento individual de Pages ni requiere un proveedor de base de datos.

No se activarán planes de pago ni mejoras automáticas de facturación. El uso
operativo con empleados o datos reales requiere validar seguridad y respaldos.
