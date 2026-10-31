# Evidencias · ARSW-EQP-01

Integrantes: Hever Barrera Batero, María Juliana Rodríguez Caicedo, Kevyn Daniel Forero Gonzalez

> El detalle completo, con el procedimiento paso a paso y **las capturas ANTES/DESPUÉS**, está en
> [`evidencias/README.md`](evidencias/README.md). Los JSON y capturas están en `evidencias/`.
> El dashboard exportado está en [`dashboard.json`](dashboard.json).

## Entorno

Windows 11 Pro 10.0.26200 (Docker Desktop) · 16 CPUs · ≈ 15,5 GB de RAM visibles para Docker · Docker 29.6.1 · Compose v5.2.0.
Imágenes: PostgreSQL 16.6, MongoDB 7.0.16, Redis 7.4.2, Nginx 1.27.3, Prometheus 3.1.0, Grafana 11.5.1, k6 0.57.0.
Todas las horas en **UTC‑5 (Colombia)**, 30 de octubre de 2026.

## Registro

| Experimento | Inicio / fin y zona horaria | Archivo / captura | Resultado observado | Interpretación |
|---|---|---|---|---|
| Baseline | 21:39:17 – 21:39:40 (UTC‑5) | `evidencias/01-baseline.json` | `ediciones_concurrentes` **200 y 200** (versión final 3); `permiso_revocado` **200**; `presencia_expira` seguía `ana` a los 22 s | Los 3 defectos reales de la base: se pierde un cambio, una caché vieja deja escribir y la presencia no expira |
| Restricciones SQL y rollback | 21:39:53 – 21:39:54 | `evidencias/02-sql-restricciones.txt` | `UPDATE` dentro de transacción: `f`; tras `ROLLBACK`: `t`. Error de clave duplicada y error de clave foránea | La transacción deshace cambios no confirmados; la clave primaria evita membresías repetidas y la foránea evita usuarios inexistentes |
| Dos pestañas (Experimento 1) | ANTES 21:52:48 – 21:52:56 · DESPUÉS 21:59:12 – 21:59:20 | `capturas/antes-exp1-*`, `capturas/despues-exp1-*`, `evidencias/07-experimento1-409.txt` | ANTES: Luis recibe **200** (versión 3). DESPUÉS: Luis recibe **409**, versión 2 | El 409 no es una caída: es una respuesta correcta que evita pisar un cambio |
| Permiso revocado | ANTES 21:52:56 – 21:53:07 · DESPUÉS 21:59:20 – 21:59:30 | `capturas/antes-rev-*`, `capturas/despues-rev-*` | ANTES: Luis guarda (**200**). DESPUÉS: **403**, tablero intacto. La consulta de la pantalla seguía en `true` (caché) | Guardar ya no depende de la caché; la caché solo sirve para mostrar |
| Presencia a los 20 s | ANTES 21:53:07 – 21:53:34 · DESPUÉS 21:59:30 – 21:59:58 | `capturas/antes-ttl-*`, `capturas/despues-ttl-*` | ANTES: a los 22 s sigue `["ana"]`. DESPUÉS: `[]` | El TTL de 20 s se aplica en la misma escritura |
| Acceptance corregido | 21:43:07 – 21:43:31 · repetido 22:21:04 – 22:21:28 | `evidencias/06-acceptance-corregido.json`, `evidencias/11-acceptance-final.json` | **4/4 `passed: true`**, código de salida 0 (las dos veces) | Los tres TODO cumplen los contratos |
| Redis detenido y recuperación | ANTES 22:08:36 – 22:09:19 · DESPUÉS 22:05:32 – 22:06:49 (consola: 21:43:44 – 21:43:58) | `evidencias/03-baseline-redis-down.json`, `evidencias/08-redis-down-corregido.json`, `capturas/*redis*`, `capturas/grafana-4*`, `capturas/grafana-5*` | ANTES: heartbeat **503**. DESPUÉS: heartbeat **200 `available:false`** y edición **200**. Redis restaurado (`PONG`). Cada heartbeat tardó ≈ 4 s | Redis es opcional: se degrada la presencia, no la edición. En Grafana `up` sigue en 1 pero la dependencia `content → redis` baja a 0 |
| Autoridad detenida y recuperación | ANTES 22:09:19 – 22:10:00 · DESPUÉS 22:06:49 – 22:08:12 (consola: 21:44:13 – 21:44:21) | `evidencias/04-baseline-authority-down.json`, `evidencias/09-authority-down-corregido.json`, `capturas/*aut*` | ANTES: edición **200** en 43 ms con permiso cacheado. DESPUÉS: **503** (≈ 4 s). Gestión restaurada y se vuelve a poder guardar | Se prefiere rechazar a escribir con un permiso que no se pudo verificar |
| Carga k6 | Base 21:40:51 – 21:42:47 · Solución 21:44:47 – 21:46:29 | `evidencias/05-k6-carga-base.json`, `evidencias/10-k6-carga-solucion.json`, `capturas/grafana-2*`, `capturas/grafana-3*` | Base: P95 **7,01 ms**, 2000 peticiones, 0 % fallos. Solución: P95 **7,00 ms**, 1998 peticiones, 0 % fallos. Umbrales cumplidos | Sin diferencia visible porque k6 solo hace lecturas; no prueba consistencia |

## Observabilidad

Dashboard: **ARSW-EQP-01 · Persistencia**, en [`dashboard.json`](dashboard.json), con 8 paneles (los 2 iniciales y los 6 de `docs/OBSERVABILIDAD.md`).
Capturas con la ventana de tiempo visible: `evidencias/capturas/grafana-1` a `grafana-6`.

**1. ¿Por qué puede subir el contador de conflictos mientras baja la pérdida de cambios?**
Porque cada conflicto es un cambio que el sistema **rechazó** (409) en vez de pisar el de otra persona. Antes había 0 conflictos pero se perdían cambios sin avisar (200 y 200). Ahora hay conflictos, pero ya no se pierde nada: el conflicto indica que la protección funcionó.

**2. ¿Por qué el panel de caché no demuestra que una escritura fue autorizada?**
Porque solo cuenta las consultas de permiso de la pantalla, y un acierto puede ser un permiso viejo. Además, las escrituras ya no usan la caché: le preguntan a Gestión. Que la caché acierte mucho no dice si se guardó con permiso.

**3. ¿Qué ve Grafana cuando Redis cae pero la API sigue respondiendo 200?**
`up` sigue en 1 (Prometheus aún lee las métricas), pero el panel *Dependencias* muestra `content → redis` en 0 y *Presencia degradada* sube. También sube el P95 (≈ 4 s por heartbeat). Por eso `up = 1` no significa que todo funcione.

**4. ¿Por qué el P95 de k6 y el del backend no tienen el mismo valor?**
k6 mide desde el cliente (incluye Nginx y la red). El backend mide solo su procesamiento y lo estima con buckets, así que es aproximado. En nuestras pruebas: k6 ≈ 7,0 ms y backend ≈ 4,9 ms.

## Problemas pendientes

No hay pruebas de aceptación fallidas. Lo que **no está resuelto**, con su evidencia:

1. **Carrera de revocación (límite de diseño).** Si se revoca un permiso justo entre la validación y el guardado, la escritura puede pasar. Gestión y Contenido no comparten transacción. Está documentado en el ADR con alternativas; no se implementó ni se probó.
2. **Degradación lenta.** Con Redis o Gestión apagados cada petición tardó ≈ 4 s (`capturas/despues-redis-1…` 3982 ms, `capturas/despues-aut-2…` 4028 ms; P95 de 4–5 s en `capturas/grafana-5`). Se evita el error pero no la demora. No comprobamos la causa; falta probar un *timeout* más corto.
3. **No medimos el costo de la llamada extra a Gestión en escrituras**, porque k6 solo hace lecturas.

La distribución de responsabilidades entre los tres integrantes está en `ADR-001.md` (sección *Participación y herramientas*).

Hechos del proceso que conviene saber (detalle en `evidencias/README.md`, §8): una corrida de DESPUÉS se descartó porque `content` seguía con el código base en memoria, y se repitió después de reiniciarlo y comprobarlo con `curl`; por eso el Grafana de todo el laboratorio muestra actividad adicional. Las capturas se tomaron con un script de Chrome automático; la franja negra con la hora la agrega el script.
