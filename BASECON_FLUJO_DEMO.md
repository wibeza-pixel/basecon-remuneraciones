\# BASECON — Flujo de demo y conversión



\*\*Última actualización:\*\* 07 de octubre de 2026

\*\*Responsable:\*\* William Benítez

\*\*Estado:\*\* Diseño cerrado, implementación pendiente



\---



\## 📋 RESUMEN EJECUTIVO



Cuando un cliente pide una demo en `apps.basecon.cl`, se le crea una \*\*empresa demo personalizada\*\* con:

\- 1 usuario administrador (con su email)

\- 2 usuarios adicionales

\- Vigencia de 7 días

\- Acceso a la app: `https://basecon.streamlit.app`



Al vencer:

\- Si contrata → se mantiene o se borra la base (según prefiera)

\- Si NO contrata → se bloquea, se guardan los datos 60 días



\---



\## 🎯 DECISIONES CLAVE



| Decisión | Valor |

|---|---|

| \*\*Días de demo\*\* | 7 días |

| \*\*Módulo ofrecido\*\* | Solo Remuneraciones |

| \*\*Usuarios por demo\*\* | 3 (1 admin + 2 usuarios) |

| \*\*Datos precargados\*\* | Ninguno (el cliente carga los suyos) |

| \*\*Alta de usuario\*\* | Manual (por William) |

| \*\*Al vencer (contrata)\*\* | Se consulta si mantiene o borra la base |

| \*\*Al vencer (NO contrata)\*\* | Bloqueo + guardar 60 días |

| \*\*Cobro\*\* | Por definir (transferencia + quizás Flow) |

| \*\*Quién responde\*\* | William (solo) |



\---



\## 🔄 FLUJO COMPLETO



\### Día 0 — Solicitud



1\. Cliente entra a `apps.basecon.cl`

2\. Click en \*\*"Pedir prueba"\*\*

3\. Llena formulario:

&#x20;  - Nombre completo

&#x20;  - Email

&#x20;  - Empresa / Razón Social

&#x20;  - RUT (opcional)

&#x20;  - Teléfono / WhatsApp

&#x20;  - \*\*¿Cuántos trabajadores manejas?\*\* (1-10 / 11-50 / 51+)

4\. Envía

5\. \*\*A William le llega:\*\*

&#x20;  - Email con los datos del cliente

&#x20;  - WhatsApp con los datos del cliente



\### Día 0 — Alta manual (William)



1\. William entra a `basecon.streamlit.app` con su usuario admin maestro

2\. \*\*Crea la empresa demo:\*\*

&#x20;  - Nombre: `DEMO - \[Nombre de la empresa del cliente]`

&#x20;  - RUT: el del cliente (o ficticio si no lo dio)

&#x20;  - Otros datos: los que tenga

3\. \*\*Crea el usuario admin:\*\*

&#x20;  - Nombre: `\[Nombre del cliente] (Admin)`

&#x20;  - Email: el del cliente

&#x20;  - Rol: \*\*Administrador\*\*

&#x20;  - Empresa: la demo recién creada

4\. \*\*Crea 2 usuarios extra:\*\*

&#x20;  - Usuario 2: `\[Empresa] - Usuario 2` (email ficticio)

&#x20;  - Usuario 3: `\[Empresa] - Usuario 3` (email ficticio)

&#x20;  - Rol: usuario normal

5\. \*\*Anota la fecha de vencimiento\*\* (7 días desde hoy)

6\. \*\*Envía las credenciales:\*\*

&#x20;  - Por email

&#x20;  - Por WhatsApp



\### Día 1 — Bienvenida



Enviar mensaje:

> "Hola \[nombre], ¿cómo va tu primera prueba con BASECON? Cualquier duda, avísame."



\### Día 3 — Seguimiento



Enviar mensaje:

> "Hola \[nombre], ya llevas 3 días. ¿Alguna duda o algo que mejorar?"



\### Día 5 — Aviso intermedio



Enviar mensaje:

> "Hola \[nombre], te quedan 2 días de prueba. ¿Ya probaste generar una liquidación?"



\### Día 6 — Último día



Enviar mensaje:

> "Hola \[nombre], tu prueba vence mañana. ¿Te gustó BASECON? ¿Seguimos?"



\### Día 7 — Cierre



1\. \*\*A las 00:00 se bloquea\*\* el acceso (manual o automático)

2\. \*\*Enviar mensaje final:\*\*

&#x20;  > "Hola \[nombre], tu prueba terminó. Quería saber:

&#x20;  > • ¿Qué te pareció BASECON?

&#x20;  > • ¿Algo te faltó?

&#x20;  > • ¿Cuántos usuarios necesitarías?

&#x20;  > • ¿Cuántos trabajadores manejas?

&#x20;  > • ¿Alguna función que te gustaría agregar?

&#x20;  > 

&#x20;  > Si te interesa continuar, te paso los planes."



\### Al contratar



1\. Cliente dice SÍ

2\. William le pregunta: \*\*¿mantener la base actual o empezar de cero?\*\*

3\. \*\*Si mantiene:\*\*

&#x20;  - Solo activar la cuenta

&#x20;  - Desbloquear el acceso

&#x20;  - Generar la primera factura

4\. \*\*Si borra:\*\*

&#x20;  - Exportar los datos actuales (por si acaso)

&#x20;  - Limpiar la empresa

&#x20;  - Crear cuenta nueva limpia

5\. \*\*Cobrar\*\* (transferencia o Flow)



\### Al NO contratar



1\. Cuenta bloqueada

2\. Datos conservados 60 días

3\. \*\*Recordatorios automáticos a los 15, 30 y 45 días\*\* (opcional)

4\. Al día 60: borrado automático



\---



\## 📧 PLANTILLAS DE MENSAJES



\### 📩 Día 0 — Credenciales



\*\*Asunto:\*\* 🔑 Tu acceso a BASECON — Prueba de 7 días



\*\*Cuerpo:\*\*



\### 📩 Día 1 — Bienvenida



\*\*Asunto:\*\* ¿Cómo va tu primera prueba?



\*\*Cuerpo:\*\*



\### 📩 Día 3 — Seguimiento



\*\*Asunto:\*\* ¿Cómo va tu prueba de BASECON?



\*\*Cuerpo:\*\*



\### 📩 Día 5 — Aviso intermedio



\*\*Asunto:\*\* Te quedan 2 días de prueba



\*\*Cuerpo:\*\*



\### 📩 Día 6 — Último día



\*\*Asunto:\*\* ⏰ Tu prueba vence mañana



\*\*Cuerpo:\*\*



\### 📩 Día 7 — Cierre y conversión



\*\*Asunto:\*\* ¿Cómo te fue con BASECON?



\*\*Cuerpo:\*\*



\---



\## 📊 PLANILLA DE TRACKING



| # | Fecha inicio | Cliente | Email | Empresa | RUT | Teléfono | # Trabaj. | Usuario admin | Clave | Vigencia | Día 1 | Día 3 | Día 5 | Día 6 | Día 7 | Estado | Contrata |

|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

| 1 | 07-10-26 | Juan Pérez | juan@abc.cl | ABC SpA | 76.543.210-9 | +56912345678 | 15 | juan@abc.cl | xxxxx | 14-10-26 | ✅ | ✅ | ⏳ | ⏳ | ⏳ | Activa | ⏳ |

| 2 | | | | | | | | | | | | | | | | | |



\*\*Estados posibles:\*\*

\- \*\*Activa:\*\* demo vigente

\- \*\*Vencida:\*\* pasó día 7, sin contratar

\- \*\*Contrató:\*\* se convirtió en cliente pago

\- \*\*Rechazó:\*\* dijo que no, esperando borrado

\- \*\*Borrada:\*\* pasaron 60 días sin respuesta



\---



\## ✅ CHECKLIST POR CLIENTE



\### Al recibir solicitud:

\- \[ ] Recibí email + WhatsApp con los datos

\- \[ ] Leí los datos (nombre, empresa, # trabajadores)

\- \[ ] Anoté en la planilla de tracking



\### Crear demo:

\- \[ ] Entré a BASECON con mi cuenta maestra

\- \[ ] Creé la empresa `DEMO - \[Nombre]`

\- \[ ] Creé el usuario admin (con email del cliente)

\- \[ ] Creé 2 usuarios extra

\- \[ ] Generé claves

\- \[ ] Anoté la fecha de vencimiento (7 días)

\- \[ ] Actualicé la planilla



\### Enviar credenciales:

\- \[ ] Envié email con credenciales

\- \[ ] Envié WhatsApp con credenciales

\- \[ ] Anoté la fecha de envío



\### Recordatorios:

\- \[ ] Día 1: envío bienvenida

\- \[ ] Día 3: seguimiento

\- \[ ] Día 5: aviso

\- \[ ] Día 6: último día

\- \[ ] Día 7: cierre + conversión



\### Cierre:

\- \[ ] Al día 7, bloqueo el acceso

\- \[ ] Envío mensaje final

\- \[ ] Actualizo planilla según respuesta

\- \[ ] Si contrata → activo cuenta

\- \[ ] Si no contrata → anoto "Vencida" + espero 60 días



\---



\## 🛠️ AUTOMATIZACIONES FUTURAS



\### FASE 1 — Manual (HOY)

\- Todo manual

\- Sin desarrollo



\### FASE 2 — Semi-automática

\- Worker de Cloudflare que reciba el formulario

\- Guarde el lead en Supabase

\- Envíe email a William con los datos

\- Genere el borrador del mensaje de bienvenida



\### FASE 3 — Automatización completa

\- Crear empresa demo automáticamente

\- Crear usuarios automáticamente

\- Enviar credenciales automáticamente

\- Recordatorios automáticos

\- Bloqueo automático al día 7

\- Borrado automático al día 67



\---



\## 💰 PLANES Y PRECIOS (por definir)



\*\*Borrador de planes:\*\*



| Plan | Usuarios | Trabajadores | Precio |

|---|---|---|---|

| \*\*Starter\*\* | 1 | Hasta 5 | $\_\_\_ / mes |

| \*\*Pyme\*\* | 3 | Hasta 25 | $\_\_\_ / mes |

| \*\*Business\*\* | 10 | Hasta 100 | $\_\_\_ / mes |

| \*\*Enterprise\*\* | Personalizado | Ilimitado | A convenir |



\*(A definir con más pruebas y feedback de clientes)\*



\---



\## 📌 NOTAS



\- La app en `basecon.streamlit.app` ya funciona ✅

\- El botón en `apps.basecon.cl` ya apunta correctamente ✅

\- Los mensajes se envían manualmente por ahora

\- La automatización se hará después de 5-10 clientes reales



\---



\## 📞 CONTACTO



\*\*William Benítez\*\* — Fundador BASECON

\- WhatsApp: +56 9 XXXX XXXX

\- Email: \[tu email]

\- Web: https://basecon.cl

