# BASECON v2.5 — Historial del trabajador y anexos de contrato

- **📁 Historial y documentos del trabajador** (pantalla Trabajadores): una carpeta por trabajador, también para los inactivos y finiquitados.
  - Se guardan **automáticamente** al generarlos: contratos, anexos, liquidaciones (una por mes; si se regenera, reemplaza a la anterior), comprobantes de vacaciones y finiquitos.
  - **Subir archivos:** licencias médicas en PDF, contratos o anexos firmados escaneados, certificados, cartas de aviso, etc. Se aceptan PDF, JPG, PNG, DOCX y XLSX, de hasta 5 MB.
  - Para cada documento hay filtro por tipo y botón de descarga.
  - Para eliminar: el administrador puede borrar cualquier documento; cada usuario puede borrar solo lo que él subió.
  - Los archivos se guardan dentro de la base de datos (Supabase), porque el disco de Streamlit Cloud se borra en cada reinicio. El administrador ve el espacio usado.
- **📝 Anexo de contrato** (pantalla Contratos):
  - Cambios posibles: sueldo base, cargo, jornada y horario, colación, movilización, lugar de trabajo, duración (pasa a indefinido o prórroga del plazo fijo) y cláusula libre.
  - Genera el documento Word, lo guarda en el historial y, si se marca, actualiza el contrato para las liquidaciones siguientes.
  - Validaciones: ingreso mínimo y jornada máxima. Avisa si el sueldo baja y si una segunda renovación de plazo fijo debe pasar a indefinido (art. 159 N°4).
- "Un millón" se escribía sin tilde en los montos en palabras; corregido.

# BASECON v2.4 — Mes activo y calculadora de sueldo

- **Mes activo destacado** arriba a la derecha (recuadro azul *MES ACTIVO · SEPTIEMBRE 2026*). Se cambia en el menú lateral (📅 Mes activo) o escribiendo otro periodo en cualquier pantalla. Movimientos, Liquidaciones, Libro, Previred e Indicadores se abren con ese mes. Al entrar, parte en el último mes con indicadores cargados.
- **🧮 Calculadora de sueldo** (para todos los usuarios): sueldo base → líquido, o líquido deseado → sueldo base. Muestra haberes, descuentos, aportes del empleador y costo empresa. Usa el mismo cálculo de las liquidaciones y no guarda nada.
- Manual actualizado.

# BASECON v2.3 — Contacto de ayuda, legibilidad y seguridad

- **Datos de contacto para ayuda.** El administrador los define en *Usuarios → Datos de contacto para ayuda* (nombre, teléfono, WhatsApp, correo, horario). Se muestran en la pantalla de ingreso, en el menú lateral y en *Ayuda*; WhatsApp y correo quedan como enlaces.
- **Letra más grande y colores más fuertes** en toda la app: títulos, etiquetas de cada campo, desplegables, pestañas, botones y menú lateral.
- **Liquidaciones:** la línea de indicadores (UF, UTM, tope, Ley 21.735) se veía con formato extraño; corregido.
- **BASECON_SECRET agregado después:** antes bloqueaba a todos los usuarios ya creados, incluido el administrador. Ahora, en el primer ingreso con el secreto, los usuarios sin firma se firman una sola vez. Una firma existente nunca se reescribe, así que una edición manual de la base se sigue detectando.
- Documentación: *Manual de operación* (usuarios), *Guía del administrador* y presentación comercial.

# BASECON v2.1 — Módulo Movimientos RRHH (reemplaza a Control RRHH)

- **Una sola app con permisos por módulo.** En *Usuarios*, cada usuario tiene sus empresas y sus módulos: **Movimientos RRHH** o **Remuneraciones**, o ambos. El administrador ve todo.
  - Un encargado del cliente con solo Movimientos RRHH ve: Dashboard, Trabajadores, Movimientos del mes, Conceptos adicionales y Ayuda.
- **Movimientos del mes.** Es una planilla por empresa y mes, con:
  - días trabajados, ausencias y licencia (días y fechas);
  - vacaciones y anticipo;
  - aguinaldo y bono de desempeño;
  - horas extra al 50% y al 100%, horas domingo y horas extra domingo (cantidad, o valor en pesos si el cliente lo informa);
  - colación y movilización del mes;
  - observación;
  - una columna por cada concepto propio de la empresa.
  
  Incluye totales, validaciones y exportación a Excel.
- **Estados del periodo:** Abierto → *Enviar a remuneraciones* (cliente) → Cerrado (oficina). Un periodo enviado ya no lo puede modificar el cliente; la oficina puede reabrirlo.
- **Conceptos adicionales por empresa.** Cada concepto tiene un tipo (haber imponible, no imponible o descuento) y un código LRE. Ejemplos: bono metas (2113), viático (2303), préstamo (3183).
- **Liquidaciones automáticas.** Al calcular, se toman los movimientos:
  - días trabajados;
  - horas extra (valor hora = sueldo ÷ (jornada × 30/7), con recargos de 1,5, 2,0, 0,3 en domingo (art. 38) y 2,0; editables en `remu/config.py`);
  - aguinaldo, bonos y conceptos imponibles, que entran también a la base de la gratificación del art. 50;
  - haberes no imponibles, anticipo y otros descuentos.
  
  La liquidación en Word muestra cada concepto.
- **LRE:** cada concepto va a su código (2110, 2113, 2107, 2303, 3183, 3188, etc.), con días de licencia (1116) y de vacaciones (1117).
- **Previred:** la licencia médica se informa como movimiento 3, con fechas y renta imponible del mes anterior (campo 92).
- **Libro y centralización:** columnas y líneas nuevas para bonos, no imponibles y otros descuentos. El asiento sigue cuadrando.
- **Importación de trabajadores desde Excel,** en el mismo formato de Control RRHH. Los trabajadores tienen ahora código, cargo y centro de costo.
- **Supabase compartido con Control RRHH.** BASECON crea sus tablas en el schema `basecon`, separado de las tablas de Control RRHH que están en `public`. Probado: no toca las tablas existentes.
  - Ese schema no se expone a la API pública de Supabase.
  - Cuando se deje de usar el `index.html` de Control RRHH, las tablas antiguas de prueba se pueden borrar con `supabase/limpiar_control_rrhh_antiguo.sql`.
- **Supabase siempre activo:** `.github/workflows/mantener-supabase-activo.yml` consulta la base cada 3 días. Requiere el secret `SUPABASE_DB_URL` en GitHub.
- **Pruebas:** 45 casos, que pasan en SQLite y en Postgres.

# BASECON v2.0 — Cambios respecto de la v1

Las correcciones están ordenadas según los 14 puntos de la revisión. Las pruebas automáticas (`pytest`, 39 casos) pasan en SQLite y en Postgres.

## Estructura (puntos 13 y 14)
El archivo único de 3.800 líneas quedó dividido así:

| Archivo | Contenido |
|---|---|
| `app.py` | Solo la interfaz Streamlit (pantallas). |
| `remu/config.py` | Parámetros legales, tablas de códigos (Previred, LRE, causales), feriados y utilidades. |
| `remu/db.py` | Conexión SQLite/Postgres con pool, esquema único, migraciones y upserts `ON CONFLICT`. |
| `remu/calculos.py` | Liquidación e impuesto único. Son funciones puras que se pueden probar. |
| `remu/finiquitos.py` | Motor de finiquitos. |
| `remu/documentos.py` | Contrato, liquidación, comprobante de feriado y finiquito (Word). |
| `remu/libros.py` | Libro Excel, centralización, LRE, Formulario 1887, CSV SII y certificados. |
| `remu/previred.py` | Archivo Previred de 105 campos. |
| `remu/seguridad.py` | Usuarios, claves y plazos de acceso. |
| `remu/procesos.py` | Cálculo del mes completo. |
| `tests/` | Pruebas automáticas. |

- En Postgres ya no se abre una conexión nueva por consulta: la app usa un pool y `close()` devuelve la conexión.
- Se eliminó la reescritura de SQL "por casos". Todos los upserts usan `INSERT … ON CONFLICT`, que funciona igual en ambos motores.
- La app crea y migra por sí sola las tablas en Postgres. `supabase/schema.sql` se generó desde el mismo esquema.
- Corregido: `read_sql_df` no adaptaba los `?` en Postgres, así que las pantallas con filtro fallaban en Supabase.
- Corregido: en Postgres fallaban `GROUP_CONCAT` y un `GROUP BY` incompleto del 1887.
- Corregido: el LRE consultaba la columna inexistente `t.tramo_af` y se caía siempre.

## 1. Impuesto único
- Se aplica la tabla mensual en UTM (8 tramos, factor y rebaja). La base es el imponible menos AFP, salud 7% y AFC del trabajador. El adicional de Isapre no rebaja la base, y en la v1 sí la rebajaba.
- El impuesto se guarda en la liquidación y se descuenta del líquido. Aparece en el Word, en el libro Excel, en la centralización (Haber "Impuesto único por pagar"), en el LRE (3161) y en el 1887.
- El 1887 informa ahora la renta total neta como base tributable actualizada, no como total imponible. El impuesto también va actualizado. La jornada ya no queda fija en 45 horas: se toma del contrato.
- La centralización ya no absorbe diferencias en "Remuneraciones por pagar": solo corrige redondeos de ±$2. Una diferencia mayor queda a la vista.

## 2. Previred
- Se generan los 105 campos del formato largo variable v82: códigos de AFP, Isapre, CCAF y mutual, movimiento de personal (contratación y retiro con fechas), tipo de trabajador, tramo y cargas, CCAF, mutual/ISL, AFC y tipo de jornada.
- Ley 21.735:
  - Hasta julio de 2026: campo 29 = SIS y campo 94 = expectativa de vida 0,9%.
  - Desde agosto de 2026: campo 29 = Seguro Social 2,5% y campo 95 = rentabilidad protegida 0,9%.
  - El 0,1% a cuenta individual se suma al campo 28.
- Antes de generar, valida el RUT (módulo 11) y los nombres, e informa los errores.
- **Validar con el validador de Previred antes de la primera carga.** Los destinos de la reforma están parametrizados al inicio de `remu/previred.py`.

## 3. Finiquitos
- Base del art. 172: sueldo, gratificación, promedio de variables, colación y movilización. Tope de 90 UF.
- Años de servicio: se cuentan completos y se suma uno si la fracción supera 6 meses. Tope de 11 años. Se exige un año como mínimo.
- Aviso previo en las causales del art. 161 cuando no se dio aviso. Se agregó el desahucio (161 inc. 2), además de otras causales, con su código LRE.
- Feriado proporcional desde el último aniversario, más los días pendientes informados, convertidos a días corridos con la tabla de feriados (editable).
- Descuento del aporte AFC del empleador, con tope en la indemnización por años de servicio. La app sugiere el monto a partir de las liquidaciones.
- **Vista previa antes de confirmar.** El contrato y el trabajador se cierran solo al confirmar. El trabajador se desactiva únicamente si no tiene otro contrato activo.
- El finiquito se registra en el LRE del mes (1103, 1104, 2313, 2314 y 2315).

## 4. Indicadores que se pisaban
`init_db()` corre una sola vez (`st.cache_resource`) y usa `ON CONFLICT DO NOTHING`, así que ya no reescribe agosto 2026. Guardar desde el PDF conserva los valores que no se pudieron leer, y ya no se inventa una UTM por defecto.

## 5 a 9. Parámetros y validaciones
- **Jornada:** la máxima legal depende de la fecha (Ley 21.561: 44, 42 y 40 horas). El valor por defecto es 42 horas. La app avisa si un contrato o una liquidación la supera.
- **Gratificación por contrato:**
  - art. 50 (25% con tope de 4,75 IMM al año, pagada mensualmente);
  - monto fijo;
  - sin gratificación.
- **Asignación familiar:** se usa el tramo que asigna el IPS o la CCAF, registrado en la ficha del trabajador. Los montos se editan por periodo en Indicadores.
- **Ley 21.735:**
  - Desde agosto de 2026 el SIS va dentro del 2,5%. Ya no se duplica: en la v1 el 2,5% se contaba dos veces en el libro y en la centralización.
  - Pensionados y trabajadores de 65 años o más no pagan SIS ni cotización del empleador.
- **Seguro de cesantía:**
  - Contratos de obra o faena pagan 3% del empleador, igual que plazo fijo; en la v1 se les cobraba la tasa de contrato indefinido.
  - Pensionados y menores de 18 años están exentos.
  - Con más de 11 años de relación laboral, el empleador paga 0,8%.
- **CCAF:** se separa la parte del 7% Fonasa que va a la caja. La tasa es editable y por defecto es 5,2%, según el campo 90 del instructivo Previred.
- **Advertencias:** sueldo bajo el ingreso mínimo (proporcional en jornada parcial), jornada sobre la máxima, líquido negativo, tramo de asignación familiar estimado y falta de UTM.

## 10. Documentos
- Fechas en español sin depender del idioma del servidor.
- El finiquito incluye:
  - detalle de cada concepto y del descuento AFC;
  - declaración de cotizaciones pagadas (art. 162);
  - reserva de derechos;
  - ratificación ante ministro de fe (art. 177).
- La liquidación muestra el impuesto único y separa los haberes imponibles de los no imponibles.
- Contrato con cláusula de gratificación art. 50 y jornada vigente.

## 11 y 12. Seguridad
- No hay claves por defecto. En el primer uso se crea el administrador.
- Usuarios con clave PBKDF2 con sal, rol y empresas asignadas. Cada usuario ve solo sus empresas.
- Plazo de acceso por usuario: por días desde el primer acceso o hasta una fecha.
- Se detecta si el reloj del equipo se retrocede.
- Tras 5 intentos fallidos, el login se bloquea 30 segundos.
- Con `BASECON_SECRET` definido, cualquier cambio manual en la base a permisos o plazos invalida el acceso.
- En Streamlit Cloud sin `DATABASE_URL`, la app muestra una alerta porque los datos se pierden al reiniciar.
- Se eliminó la carga automática de las dos empresas reales de ejemplo en instalaciones nuevas.

## Pendiente de validar con la fuente oficial
- La asignación del 0,1% de la cuenta individual y del Seguro Social en Previred (campos 28, 29, 94 y 95) y en el LRE (4155 y 4157). No hay instrucción publicada; se usa el criterio de los proveedores de software.
- Las tasas AFP, el valor del IMM, los tramos de asignación familiar y la tabla de feriados deben revisarse cada periodo en la pantalla Indicadores.

## Migración desde la v1
Copie la carpeta `remu/` y `app.py` sobre la instalación actual y conserve `data/`. Al iniciar, la app agrega las columnas nuevas sin borrar datos. El primer ingreso pide crear el administrador.

Después, en cada empresa, complete:
- el código de región y el de comuna (LRE);
- la CCAF.

Y en cada contrato, el tipo de gratificación. **Vuelva a calcular las liquidaciones de agosto 2026 en adelante:** las de la v1 no tienen impuesto único y duplican el 2,5%.
