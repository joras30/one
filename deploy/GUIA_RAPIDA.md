# Guía rápida del Laboratorio de Medidas

El tablero permite pasar de una cifra a sus datos. Puedes consultar, buscar y
ordenar sin cambiar los registros guardados.

## 1. Entrar a los datos de un cuadro o gráfico

1. En **Resumen**, pulsa **Filtrar información**, elige las fechas y pulsa
   **Aplicar**. Puedes añadir actividad, colaborador, SAP u otros filtros.
2. Toca un cuadro, por ejemplo **Revisiones aprobadas**, para consultar qué
   registros forman esa cifra.
3. En un gráfico, toca el punto de una fecha o la categoría que quieras revisar.
   El detalle indica qué período y filtros está mostrando.
4. Abre un registro cuando necesites comprobar su información. Usa el botón de
   cerrar de la ventana para regresar y continuar la consulta.

Las fechas incluyen el día inicial y el final. Cambiar un campo de filtro no
actualiza las cifras hasta que aplicas la selección. Comprueba siempre el período
que aparece junto al cuadro o en su detalle.

## 2. Encontrar y ordenar filas

| Control | Para qué sirve |
|---|---|
| **Buscar en esta tabla** | Encontrar un texto entre las filas cargadas: una serie, un nombre, un SAP o un resultado. |
| Encabezado de una columna | Ordenar sus valores. Un segundo toque invierte el orden. |
| **Filas por página** | Elegir 10, 25, 50 o todas las filas encontradas. |
| **Anterior / Siguiente** | Recorrer las páginas de esa tabla. El contador indica cuántas filas hay. |
| **Restablecer tabla** | Quitar la búsqueda y el orden de esa tabla; conserva los registros guardados. |
| **Descargar CSV filtrado** | Guardar las filas encontradas, en el orden elegido, incluidas sus demás páginas locales. |

En celular, desliza la tabla hacia los lados para ver las columnas que quedan
fuera de la pantalla. También puedes usar las acciones disponibles de cada fila.
Consultar una fila no equivale a editarla: las correcciones requieren el permiso
correspondiente y conservan su historial.

**Dos búsquedas con alcances diferentes:** los filtros de la sección consultan
los datos del período; **Buscar en esta tabla** busca entre las filas que ya se
cargaron. En **Registros**, utiliza además la paginación de Registros para pedir
otra página de la base. Una búsqueda local vacía no demuestra que el dato no
exista en otra página.

Los totales generales de un informe conservan su período y filtros. Una búsqueda
dentro de la tabla sirve para localizar filas; no cambia esos totales generales.

## 3. Entender las cifras del resumen

| Indicador | Qué significa |
|---|---|
| **Revisiones realizadas** | Revisiones válidas del período. Revisar otra vez la misma serie cuenta como otra revisión. |
| **Revisiones aprobadas** | Revisiones cuyo resultado registrado es **Apto**. |
| **Revisiones rechazadas** | Revisiones cuyo resultado registrado es **No apto**. |
| **Tasa de aprobación** | Aprobadas divididas entre las revisiones con resultado Apto o No apto. |
| **Pendientes / Sin resultado** | Revisiones que aún no tienen un resultado concluido; quedan fuera de la tasa. |
| **Series identificadas** | Series diferentes presentes en la selección. Los lotes sin serie no permiten identificar equipos individuales. |
| **Reingresos de revisión** | Revisiones adicionales de una serie repetida dentro del período. Una revisión sin serie no demuestra un reingreso. |

Ejemplo: hay 8 revisiones aptas, 2 no aptas y 3 pendientes. La aprobación es
**8 de 10 evaluadas = 80 %**. Los 3 pendientes se muestran aparte.

Cada actividad conserva su unidad: **medidores**, **sellos**, **revisiones** u otra
unidad configurada. Limpiar y sellar el mismo equipo registra dos trabajos, sin
convertirlo en dos medidores físicos distintos.

## 4. Consultar el avance de una recepción

Toca el lote para ver su orden y las entregas registradas. Comprueba **esperado**,
**recibido** y **pendiente**. El saldo acumula las entregas hasta la fecha de corte;
la fecha **Desde** del período de producción no limita ese acumulado.

| Señal | Qué revisar |
|---|---|
| 🟢 Completa o cerrada | La cantidad está completa. Si está lista para cerrar, supervisión todavía debe realizar el cierre. |
| 🟡 Pendiente o por confirmar | Faltan entregas o falta confirmar la cantidad esperada. |
| 🔴 Vencida, con exceso o conflicto | Revisa la fecha, las entregas y los datos de la orden antes de cerrarla. |

Si una orden tiene 30 recibidos de 100 esperados, su avance es **30 %** y faltan
**70**. Sin cantidad esperada confirmada no se inventa un porcentaje. Un excedente
de una orden no compensa los faltantes de otra.

## 5. Revisar calidad y comparar períodos

En **Calidad y calibración**, consulta las revisiones, los resultados, las
mediciones y los hallazgos. El rojo indica resultados o mediciones que requieren
revisión; el amarillo, información o evaluaciones pendientes; el verde,
evaluaciones aprobadas. La señal describe los datos de calidad, no una
calificación personal del técnico.

En **Comparar períodos**, elige **A** como referencia y **B** como período que
quieres comparar. Selecciona el desglose y pulsa **Generar reporte**.

- **Variación absoluta:** cantidad de B menos cantidad de A.
- **Crecimiento:** esa diferencia dividida entre A, expresada en porcentaje.
- **Sin base:** A tiene cero y B tiene producción; no hay una base para calcular
  el crecimiento porcentual.

Ejemplo: A tiene 100 revisiones y B tiene 120. La diferencia es **+20** y el
crecimiento es **+20 %**. Si los períodos duran distinto, se comparan sus cantidades
totales, sin ajustar automáticamente por días.

Las metas se muestran cuando corresponden al mismo responsable, actividad,
unidad y período completo. **Sin meta exacta** no significa producción cero:
significa que no hay una meta compatible para esa selección.

## 6. Descargar lo que necesitas

**Descargar CSV filtrado** guarda las filas encontradas entre los datos cargados
en esa tabla, con el orden elegido. Incluye sus páginas locales, pero no pide
las páginas pendientes de cargar desde la base.

Para un informe del período y filtros de la sección, utiliza sus botones
**Excel** o **PDF**. En **Registros** también está disponible **CSV**. Si el sistema
indica que hay demasiadas filas, reduce el rango o añade un filtro y vuelve a
descargar. **PNG** y **SVG** guardan una imagen del gráfico para compartirla;
la consulta interactiva se realiza dentro de la aplicación.

## 7. Qué datos puedes ver y cómo conservarlos

La supervisión consulta los datos autorizados del equipo. Cada técnico ve su
propio alcance. El visitante consulta cantidades agrupadas; los nombres, las
series y los registros individuales requieren un perfil con permiso.

La **demo gratuita de Internet** conserva la prueba en el navegador donde la usas.
Los datos del celular no se comparten automáticamente con los de la PC. Utiliza
**Descargar respaldo** para guardar una copia de esa prueba.

En la **instalación de la oficina**, los equipos que abren el enlace de la PC
principal consultan la misma base. Las actualizaciones conservan los registros:
en el enlace web basta con recargar; la actualización del servidor local se
explica en [RED_LOCAL.md](RED_LOCAL.md).
