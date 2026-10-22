# Publicación gratuita para evaluación

El requisito es costo cero. Esta publicación utiliza GitHub Pages en el repositorio
público `joras30/one`, sin contratar servicios ni registrar una tarjeta. Se retiró
la propuesta de pago y su archivo render.yaml. No se ha contratado ningún servicio.

## Activar GitHub Pages una vez

1. Abre https://github.com/joras30/one/settings/pages con tu cuenta de GitHub.
2. En **Build and deployment → Source**, selecciona **GitHub Actions**.
3. Abre **Actions → Publicar demo gratuita**. Si una ejecución anterior falló
   porque Pages todavía no estaba activado, pulsa **Re-run all jobs** o inicia
   **Run workflow** sobre la rama `demo-web`.
4. Cuando termine `deploy`, GitHub mostrará el enlace real de la demo.
   La dirección prevista es https://joras30.github.io/one/; compártela después
   de comprobar que el despliegue terminó y el enlace responde.

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

Los commits en `demo-web` ejecutan `.github/workflows/pages.yml`: instala las
dependencias fijadas, construye solo los archivos permitidos y publica en Pages.
Los evaluadores recargan el enlace. El generador no incluye bases SQLite,
documentos originales ni empleados reales.

```sh
cd browser-demo
npm ci
npm run build
```

El resultado está en `dist/github-pages/`. La capa gratuita reutiliza
`APLICACION_ACTUAL/` sin instalar Python ni abrir un servidor en el equipo evaluador.

## Datos compartidos a costo cero

El proyecto de referencia también publica una demo por navegador: su flujo Pages
fija `VITE_BACKEND=local`. Para sincronizar registros entre personas ofrece una
conexión opcional a Supabase. GitHub Pages con Supabase gratuito es una ruta posible
para la siguiente fase, dentro de los límites del proveedor.
Esa conexión central aún no está implementada aquí ni existe un proyecto creado
para ella. Requiere cuenta propia, migraciones y permisos del lado servidor.
Esta demo individual no debe presentarse como una base compartida.

No se activarán planes de pago ni mejoras automáticas de facturación. El uso
operativo con empleados o datos reales requiere validar seguridad y respaldos.
