# Evidencias del laboratorio · Persistencia, consistencia y observabilidad

Equipo: **ARSW-EQP-01** · Fecha: **30 de octubre de 2026**
Integrantes: Hever Barrera Batero, María Juliana Rodríguez Caicedo, Kevyn Daniel Forero Gonzalez
Todas las horas están en hora de Colombia (**UTC‑5**).

Aquí está lo que hicimos, **cómo lo hicimos** y **qué se vio**, con capturas.
Cada experimento se hizo dos veces: **ANTES** (código base, con los defectos) y
**DESPUÉS** (con los 3 TODO arreglados).

---

## 1. Resumen rápido

| # | Qué debe pasar | ANTES (código base) | DESPUÉS (arreglado) |
|---|---|---|---|
| 1 | Dos personas editan con la misma versión: una guarda y la otra recibe 409 | Las dos guardan (**200 y 200**). Se pierde el cambio de Ana | **200 y 409**. No se pierde nada |
| 2 | Si a Luis le quitan el permiso, no puede guardar (403) | Luis guarda igual (**200**) porque la caché dice que sí | **403**. El tablero no cambia |
| 3 | La presencia desaparece a los 20 s | A los 22 s Ana **sigue** en línea | A los 22 s la lista está **vacía** |
| 4 | Con Redis apagado se puede editar y el heartbeat responde 200 con `available:false` | Edita bien, pero el heartbeat da **503** | Edita bien y el heartbeat da **200** `available:false` |
| 5 | Con Gestión apagada no se puede guardar (503) | Guarda igual (**200**) con un permiso viejo de la caché | **503**. No guarda |

`acceptance` con el código arreglado: **4 de 4 `passed: true`** y código de salida 0.

---

## 2. Entorno

| Dato | Valor |
|---|---|
| Sistema | Windows 11 Pro, Docker Desktop |
| CPU / RAM de Docker | 16 CPUs / ≈ 15,5 GB |
| Docker / Compose | 29.6.1 / v5.2.0 |
| Servicios | PostgreSQL 16.6, MongoDB 7.0.16, Redis 7.4.2, Nginx 1.27.3, Prometheus 3.1.0, Grafana 11.5.1, k6 0.57.0 |

---

## 3. Qué cambiamos en el código

Solo se tocó `services/content/decisions.py`.

| TODO | Qué hicimos | Para qué |
|---|---|---|
| 1 · `save_board` | Pusimos la versión **dentro del filtro** de la misma operación de MongoDB: `{'_id': id, 'version': expected_version}` | Comparar y subir la versión pasa en **un solo paso**. Si dos llegan juntos, solo uno coincide; el otro recibe `None` y la API responde 409 |
| 2 · `permission_for_write` | Ahora devuelve `authoritative_permission(...)` en vez de `cached_permission(...)` | Para **guardar** se le pregunta a Gestión (PostgreSQL), no a la caché. Si Gestión no responde, sale 503 y no se guarda (no se deja pasar a nadie) |
| 3 · `touch_presence` | `client.set(key, 'online', ex=ttl)` dentro de un `try/except RedisError` que devuelve `False` | El valor y los 20 s se guardan **en la misma escritura**. Si Redis falla, no se cae todo: responde `available:false` |

**Costo del TODO 2:** cada `PUT` hace una llamada extra a Gestión. Las consultas de
permisos de la pantalla siguen usando la caché de 60 s.

---

## 4. Paso a paso

### Paso 1 · Levantar todo

```sh
docker compose up -d --build --wait --wait-timeout 300
docker compose ps
docker compose run --rm tools smoke
```

Resultado: los 8 servicios quedaron *healthy* y el smoke dio `arranque: passed` (`00-smoke.json`).

| Frontend recién abierto | Prometheus · Targets (content y management en UP) |
|---|---|
| <img src="capturas/00-frontend-inicio.png" width="420"> | <img src="capturas/00-prometheus-targets.png" width="420"> |

### Paso 2 · Medir la base antes de tocar nada

```sh
docker compose run --rm tools baseline
```

Hora: 21:39:17 → 21:39:40 · Archivo: `01-baseline.json`

Salieron los 3 defectos esperados (`passed: false`):

| Prueba | Lo que vimos |
|---|---|
| `ediciones_concurrentes` | Estados `[200, 200]`. Versión final **3** (debía ser 2). Quedó el título "Cambio de luis" |
| `permiso_revocado` | Permiso en caché `true`, escritura **200**, quedó "Cambio prohibido" |
| `presencia_expira` | A los 22 s `users: ["ana"]` (no expiró) |

También se guardó cómo falla la base con dependencias caídas:
`03-baseline-redis-down.json` (edición 200, heartbeat **503**) y
`04-baseline-authority-down.json` (edición **200** con Gestión apagada).

### Paso 3 · Restricciones de SQL

```sh
docker compose exec -T postgres psql -U lab -d boards -f /lab/evidence.sql
```

Hora: 21:39:53 · Archivo: `02-sql-restricciones.txt`

| Qué hace el script | Lo que se vio | Qué nos garantiza |
|---|---|---|
| Pone `can_edit=false` a Luis dentro de `BEGIN` y luego `ROLLBACK` | Dentro de la transacción: `f`. Después del rollback: `t` | Un cambio que no se confirma se deshace completo |
| Inserta otra vez `('board-1','ana')` | `ERROR: duplicate key value violates unique constraint "memberships_pkey"` | La **clave primaria** impide dos membresías iguales |
| Inserta un usuario que no existe | `ERROR: ... violates foreign key constraint "memberships_user_id_fkey"` | La **clave foránea** impide membresías de usuarios inexistentes |

Los dos `ERROR` son los esperados. No se quitó ninguna restricción.

### Paso 4 · Experimento 1: dos pestañas

**Cómo se hizo:** se abrieron dos pestañas del frontend. En las dos se pulsó
*Cargar versión* (versión 1). En la pestaña B se eligió **Luis**. Primero guardó
la pestaña A (Ana) y después la B (Luis).

| | Pestaña A (Ana guarda) | Pestaña B (Luis guarda) | Estado final |
|---|---|---|---|
| **ANTES** | <img src="capturas/antes-exp1-1-pestana-A-ana-guarda.png" width="280"> | <img src="capturas/antes-exp1-2-pestana-B-luis-guarda.png" width="280"> | <img src="capturas/antes-exp1-3-estado-final.png" width="280"> |
| **DESPUÉS** | <img src="capturas/despues-exp1-1-pestana-A-ana-guarda.png" width="280"> | <img src="capturas/despues-exp1-2-pestana-B-luis-guarda.png" width="280"> | <img src="capturas/despues-exp1-3-estado-final.png" width="280"> |

- **ANTES:** Luis también recibe **HTTP 200** y la versión queda en **3**. El cambio de Ana se pisó sin avisar.
- **DESPUÉS:** Luis recibe **HTTP 409** ("Versión obsoleta… recargue antes de editar"). La versión queda en 2 con el cambio de Ana.

**¿Por qué un 409 no es una caída?** Porque el servidor funcionó bien: detectó que
Luis tenía una versión vieja y se negó a pisar el cambio de otro. Es un 4xx (error
del cliente), no un 5xx (error del servidor). Por eso no sube el panel de errores técnicos.

También se reprodujo por consola con `curl` (`07-experimento1-409.txt`): ana → 200, luis → 409.

### Paso 5 · Permiso revocado y caché

**Cómo se hizo:** Luis pulsó *Consultar permiso en caché* (dio `can_edit: true`).
Después, en *Administración del escenario*, se pulsó *Revocar a Luis*. Luego Luis
intentó guardar.

| | Luis consulta (caché) | Se revoca a Luis | Luis intenta guardar | Luis consulta otra vez |
|---|---|---|---|---|
| **ANTES** | <img src="capturas/antes-rev-1-luis-permiso-en-cache.png" width="200"> | <img src="capturas/antes-rev-2-revocar-a-luis.png" width="200"> | <img src="capturas/antes-rev-3-luis-intenta-guardar.png" width="200"> | <img src="capturas/antes-rev-4-la-cache-sigue-diciendo-true.png" width="200"> |
| **DESPUÉS** | <img src="capturas/despues-rev-1-luis-permiso-en-cache.png" width="200"> | <img src="capturas/despues-rev-2-revocar-a-luis.png" width="200"> | <img src="capturas/despues-rev-3-luis-intenta-guardar.png" width="200"> | <img src="capturas/despues-rev-4-la-cache-sigue-diciendo-true.png" width="200"> |

- **ANTES:** Luis guarda con **HTTP 200** (título "Cambio prohibido de Luis", versión 2) aunque ya no tenía permiso.
- **DESPUÉS:** Luis recibe **HTTP 403** ("Permiso de edición revocado o inexistente") y el tablero sigue en versión 1.
- En la última columna se ve algo importante: la **consulta de la pantalla sigue diciendo `true`** (es la caché, dura 60 s), pero **guardar ya no depende de ella**. Por eso no basta con ocultar un botón ni con acortar el TTL.

### Paso 6 · La presencia expira a los 20 s

**Cómo se hizo:** *Registrar presencia* → *Consultar presencia* → esperar 22 s
(sin pulsar nada) → *Consultar presencia*.

| | Registrar | Consultar al instante | 22 s después |
|---|---|---|---|
| **ANTES** | <img src="capturas/antes-ttl-1-registrar-presencia.png" width="280"> | <img src="capturas/antes-ttl-2-presencia-ana-en-linea.png" width="280"> | <img src="capturas/antes-ttl-3-presencia-22s-despues.png" width="280"> |
| **DESPUÉS** | <img src="capturas/despues-ttl-1-registrar-presencia.png" width="280"> | <img src="capturas/despues-ttl-2-presencia-ana-en-linea.png" width="280"> | <img src="capturas/despues-ttl-3-presencia-22s-despues.png" width="280"> |

- **ANTES:** a los 22 s sigue `"users": ["ana"]`. La clave no tenía vencimiento.
- **DESPUÉS:** a los 22 s `"users": []`. Se borró sola.

### Paso 7 · Experimento 2: Redis detenido

```sh
docker compose run --rm tools reset
docker compose stop redis
docker compose run --rm tools redis-down
docker compose start redis        # siempre se vuelve a prender
```

En el navegador: con Redis apagado se pulsó *Registrar presencia* y luego se editó el título.

| | Heartbeat con Redis apagado | Edición con Redis apagado | Redis de vuelta |
|---|---|---|---|
| **ANTES** | <img src="capturas/antes-redis-1-heartbeat-con-redis-caido.png" width="280"> | <img src="capturas/antes-redis-2-edicion-con-redis-caido.png" width="280"> | <img src="capturas/antes-redis-3-redis-restaurado.png" width="280"> |
| **DESPUÉS** | <img src="capturas/despues-redis-1-heartbeat-con-redis-caido.png" width="280"> | <img src="capturas/despues-redis-2-edicion-con-redis-caido.png" width="280"> | <img src="capturas/despues-redis-3-redis-restaurado.png" width="280"> |

- **ANTES:** el heartbeat da **HTTP 503** ("Redis no disponible: implementar degradación"). Editar sí funciona.
- **DESPUÉS:** el heartbeat da **HTTP 200** con `"available": false`. Editar sigue funcionando (200). Ya no se cae toda la función por una dependencia opcional.
- Archivos de consola: `03-baseline-redis-down.json` (antes) y `08-redis-down-corregido.json` (después, `passed: true`).

> **Dato que midió el navegador:** con Redis apagado, cada heartbeat tardó **≈ 4 s**
> (4026 ms antes y 3982 ms después; está escrito en la franja negra de las capturas).
> O sea que "degradar bien" evita el error, pero **no evita la demora**. No comprobamos
> la causa; sospechamos que es el tiempo que tarda en fallar la conexión a un contenedor apagado.

**En Grafana** (ventana 22:05:00 → 22:08:40, después de arreglar): el panel *Dependencias* muestra
`content → redis` bajando a **0**, mientras los servicios siguen con `up = 1`; el panel
*Presencia degradada* sube aunque la respuesta HTTP fue 200.

### Paso 8 · Experimento 3: Gestión (autoridad de permisos) detenida

```sh
docker compose run --rm tools reset
# se consultó el permiso de Ana dos veces para que quede en la caché
docker compose stop management
docker compose run --rm tools authority-down
docker compose start management
docker compose restart frontend   # para que Nginx vuelva a encontrar el servicio
```

| | Permiso de Ana en caché | Guardar con Gestión apagada | Gestión de vuelta |
|---|---|---|---|
| **ANTES** | <img src="capturas/antes-aut-1-permiso-ana-en-cache.png" width="280"> | <img src="capturas/antes-aut-2-guardar-con-gestion-caida.png" width="280"> | <img src="capturas/antes-aut-3-gestion-restaurada.png" width="280"> |
| **DESPUÉS** | <img src="capturas/despues-aut-1-permiso-ana-en-cache.png" width="280"> | <img src="capturas/despues-aut-2-guardar-con-gestion-caida.png" width="280"> | <img src="capturas/despues-aut-3-gestion-restaurada.png" width="280"> |

- **ANTES:** guarda con **HTTP 200** en solo 43 ms, porque usa el permiso viejo de la caché y ni le pregunta a Gestión.
- **DESPUÉS:** **HTTP 503** ("No se puede validar el permiso; escritura no autorizada") tras ≈ 4 s, aunque la caché tenía el permiso. Cuando Gestión vuelve, se puede guardar otra vez.
- Archivos: `04-baseline-authority-down.json` (antes, 200) y `09-authority-down-corregido.json` (después, 503, `passed: true`).

**Preguntas del README:**

- *¿Qué se degradó de forma controlada?* La **presencia** (Redis): se pierde esa función, pero se sigue editando.
- *¿Qué dejó de estar disponible a propósito?* **Guardar** cuando no se puede confirmar el permiso (Gestión).
- *¿Qué garantía protege eso?* Que **nadie escriba con un permiso que no se pudo verificar**. Preferimos rechazar a dejar pasar.
- *¿Y si la falla fuera MongoDB?* No habría dónde leer ni guardar el tablero: leer y guardar darían 503. Es un dato crítico, no se puede degradar como la presencia.

### Paso 9 · Acceptance

```sh
docker compose restart content
docker compose run --rm tools acceptance
```

Hora: 21:43:07 → 21:43:31 · Archivo: `06-acceptance-corregido.json`

| Prueba | Resultado |
|---|---|
| `arranque` | ✅ passed |
| `ediciones_concurrentes` | ✅ passed (`[200, 409]`, versión 1 → 2) |
| `permiso_revocado` | ✅ passed (403, tablero sigue en versión 1) |
| `presencia_expira` | ✅ passed (a los 22 s `users: []`) |

Código de salida: **0**.

Se volvió a correr al final, con todo restaurado (22:21:04 → 22:21:28): **4/4 `passed: true`**, código 0
(`11-acceptance-final.json`).

### Paso 10 · Carga con k6 (100 s, 5 usuarios, solo lecturas)

```sh
docker compose run --rm k6
```

Se corrió dos veces y se guardó cada resumen antes de la siguiente (`05-k6-carga-base.json` y `10-k6-carga-solucion.json`).

| Medida | Código base | Código arreglado |
|---|---:|---:|
| Hora | 21:40:51 → 21:42:47 | 21:44:47 → 21:46:29 |
| Peticiones | 2000 | 1998 |
| Peticiones por segundo | 19,99 | 19,96 |
| P95 (visto por k6) | 7,01 ms | 7,00 ms |
| Mediana / promedio / máximo | 4,22 / 4,46 / 19,94 ms | 4,31 / 4,59 / 23,60 ms |
| Fallos | 0 % | 0 % |
| Umbrales (P95 < 500 ms, errores < 1 %) | ✅ cumplidos | ✅ cumplidos |
| P95 que mide el servidor `content` (Prometheus) | ≈ 4,85 ms | ≈ 4,9 ms |

| Grafana durante k6 · código base | Grafana durante k6 · código arreglado |
|---|---|
| <img src="capturas/grafana-2-k6-base.png" width="420"> | <img src="capturas/grafana-3-k6-solucion.png" width="420"> |

**Interpretación:** casi no hay diferencia. Es lo esperado: k6 solo hace **lecturas**,
y los cambios están en las **escrituras**, así que esta prueba mide velocidad de lectura,
**no** si los datos quedan bien. Eso lo prueban los experimentos de los pasos 4 a 9.

---

## 5. Dashboard de Grafana

Archivo exportado: **`entrega/dashboard.json`** (título `ARSW-EQP-01 · Persistencia`,
carpeta *ARSW* de Grafana). Tiene **8 paneles**: los 2 iniciales y los 6 pedidos.

| # | Panel | Qué mide |
|---|---|---|
| 1 | Servicios observables (`up`) | Si Prometheus pudo leer las métricas |
| 2 | Solicitudes por segundo | Cuánto tráfico llega |
| 3 | P95 por servicio | Tiempo en que responde el 95 % de las peticiones |
| 4 | Errores técnicos (5xx) | Solo fallos del servidor. **No** cuenta 403 ni 409 |
| 5 | Dependencias | 1 = responde, 0 = caída (Mongo, Redis, Gestión, Postgres) |
| 6 | Aciertos de caché | Cuántas consultas de permiso salieron de la caché |
| 7 | Conflictos de edición | Cuántos 409 por versión vieja |
| 8 | Presencia degradada | Heartbeats que dieron 200 pero sin registrar presencia |

**Capturas (cada una muestra la ventana de tiempo arriba a la derecha):**

| Todo el laboratorio (21:36 → 22:11) | ANTES · Redis y Gestión caídos (22:08 → 22:10) |
|---|---|
| <img src="capturas/grafana-1-sesion-completa.png" width="420"> | <img src="capturas/grafana-4-antes-codigo-base.png" width="420"> |

| DESPUÉS · Redis y Gestión caídos (22:05 → 22:08) | DESPUÉS · conflicto 409 (21:58 → 22:00) |
|---|---|
| <img src="capturas/grafana-5-despues-corregido.png" width="420"> | <img src="capturas/grafana-6-despues-conflicto-409.png" width="420"> |

**Qué se ve en cada una:**

- **ANTES, Redis caído:** *Dependencias* baja a 0 para `content → redis`. El heartbeat sí dio 503 (se ve en la captura del navegador), pero fue **un solo evento**, así que el panel de errores casi no lo muestra (ver §8, punto 3). El pico que aparece al inicio de ese panel es de la prueba anterior (la de DESPUÉS), no de ésta.
- **ANTES, Gestión caída:** *Dependencias* y `up` de management bajan, pero **no hay errores 5xx**: el código base seguía guardando. Eso es lo malo: el sistema "se ve sano" mientras escribe sin verificar.
- **DESPUÉS, Redis caído (22:05:50 – 22:06:20):** *Dependencias* en 0 para redis, *Presencia degradada* sube y los errores **siguen en 0** (todo fue 200).
- **DESPUÉS, Gestión caída (desde 22:07:00):** `up` de management y *Dependencias* bajan a 0, *Errores técnicos* sube (son los 503 a propósito) y el *P95* se mantiene en ~4–5 s.
- **DESPUÉS, conflicto:** *Conflictos de edición* sube cuando Luis recibe el 409.

---

## 6. Las cuatro preguntas de observabilidad

**1. ¿Por qué puede subir el contador de conflictos mientras baja la pérdida de cambios?**
Porque cada conflicto es un cambio que el sistema **rechazó** (409) en vez de pisar el de otra persona. Antes había 0 conflictos pero se perdían cambios sin que nadie se enterara (200 y 200). Ahora hay conflictos, pero ya no se pierde nada: el conflicto es la señal de que la protección funcionó.

**2. ¿Por qué el panel de caché no demuestra que una escritura fue autorizada?**
Porque ese panel solo cuenta las **consultas de permiso de la pantalla**. Un acierto (*hit*) puede ser un permiso viejo. Además, las escrituras ahora **no usan la caché**: le preguntan a Gestión. Que la caché acierte mucho no dice nada sobre si se pudo guardar con permiso.

**3. ¿Qué ve Grafana cuando Redis cae pero la API sigue respondiendo 200?**
`up` sigue en **1** (Prometheus todavía puede leer las métricas), pero el panel *Dependencias* muestra `content → redis` en **0**, y *Presencia degradada* sube. Por eso `up = 1` no significa que todo funcione. También sube el P95 (≈ 4 s por heartbeat).

**4. ¿Por qué el P95 de k6 y el del servidor no son iguales?**
k6 mide **desde el cliente**: incluye Nginx y el viaje de red. El servidor mide solo lo que tarda **adentro** y además lo **estima con buckets** (rangos), así que es aproximado. En nuestras pruebas: k6 ≈ 7,0 ms y servidor ≈ 4,9 ms.

---

## 7. Qué NO demuestran estas pruebas

- **No se prueba la revocación que ocurre justo después de validar y antes de guardar.** Gestión (PostgreSQL) y Contenido (MongoDB) no comparten transacción, así que existe una ventana pequeña donde se puede validar un permiso que se revoca un instante después. Solo se garantiza el rechazo cuando la revocación **termina antes** de empezar la escritura.
- **No hay réplicas ni CAP.** Es un Compose con una instancia de cada cosa. Apagar Redis es una falla de dependencia, no una partición de red.
- **k6 solo lee.** No prueba consistencia.
- Los datos y usuarios (`ana`, `luis`) son ficticios y se simulan con un header; no hay login real.

---

## 8. Cosas que pasaron durante las pruebas (para ser transparentes)

1. **Una corrida de DESPUÉS se descartó y se repitió.** El contenedor `content` seguía con el código base en memoria (no se había reiniciado) y el panel de conflictos no mostraba ningún 409. Se reinició, se comprobó con `curl` que daba 200 y 409, y se repitió. Por eso el Grafana de "todo el laboratorio" muestra actividad extra entre 21:52 y 22:11.
2. **Se repitieron capturas que salieron antes de que llegara la respuesta.** Con Redis o Gestión apagados el servidor tarda ~4 s; las primeras capturas mostraban la respuesta anterior. Se rehicieron esperando la respuesta real.
3. **Un solo evento no se ve en Grafana.** Con un único 503 o un único heartbeat degradado, `rate()` no muestra nada porque Prometheus no alcanza a ver el contador *subir*. Por eso en esos experimentos se repitió la acción varias veces.
4. **Los picos extra de conflictos** (≈ 22:03, ≈ 22:05 y ≈ 22:10) vienen de comprobaciones manuales con `curl` (200 y 409) para confirmar qué código estaba activo, no de los experimentos.
5. **Cómo se tomaron las capturas:** con un script que abre Chrome automáticamente y hace los mismos clics del procedimiento. La **franja negra con la hora** (arriba a la derecha) la agrega el script; el resto es la página real.

---

## 9. Archivos de esta carpeta

| Archivo | Qué es | Hora |
|---|---|---|
| `00-smoke.json` | Smoke | 21:39:17 |
| `01-baseline.json` | Baseline con los 3 defectos | 21:39:17 – 21:39:40 |
| `02-sql-restricciones.txt` | Salida del script SQL | 21:39:53 |
| `03-baseline-redis-down.json` | Base con Redis apagado (503) | 21:39:59 – 21:40:14 |
| `04-baseline-authority-down.json` | Base con Gestión apagada (200) | 21:40:26 – 21:40:30 |
| `05-k6-carga-base.json` | k6 con el código base | 21:40:51 – 21:42:47 |
| `06-acceptance-corregido.json` | Acceptance 4/4 | 21:43:07 – 21:43:31 |
| `07-experimento1-409.txt` | 200 y 409 con `curl` | 21:43:37 |
| `08-redis-down-corregido.json` | Redis apagado, arreglado | 21:43:44 – 21:43:58 |
| `09-authority-down-corregido.json` | Gestión apagada, arreglado (503) | 21:44:13 – 21:44:21 |
| `10-k6-carga-solucion.json` | k6 con el código arreglado | 21:44:47 – 21:46:29 |
| `11-acceptance-final.json` | Acceptance final con todo restaurado (4/4) | 22:21:04 – 22:21:28 |
| `capturas/` | Capturas del frontend, Prometheus y Grafana | ver franja negra de cada una |
| `../dashboard.json` | Dashboard exportado de Grafana (8 paneles) | — |

Horas de las capturas del navegador:

| Escena | ANTES | DESPUÉS |
|---|---|---|
| Dos pestañas, permiso revocado, presencia | 21:52:48 – 21:53:34 | 21:59:12 – 21:59:58 |
| Redis detenido y Gestión detenida | 22:08:36 – 22:10:00 | 22:05:32 – 22:08:12 |

---

## 10. Cómo repetirlo

```sh
# 1. Levantar
docker compose up -d --build --wait --wait-timeout 300
docker compose run --rm tools smoke

# 2. Medir la base ANTES de editar
docker compose run --rm tools baseline

# 3. Arreglar los 3 TODO en services/content/decisions.py y aplicar
docker compose restart content
docker compose run --rm tools acceptance        # 4/4 passed, código 0

# 4. Redis detenido (siempre volver a prenderlo)
docker compose run --rm tools reset
docker compose stop redis
docker compose run --rm tools redis-down
docker compose start redis

# 5. Gestión detenida (primero consultar el permiso de Ana en la pantalla)
docker compose run --rm tools reset
docker compose stop management
docker compose run --rm tools authority-down
docker compose start management
docker compose restart frontend

# 6. Carga (guardar el resumen antes de repetir)
docker compose run --rm k6
```

En **Git Bash de Windows**, los comandos con rutas de Linux necesitan
`MSYS_NO_PATHCONV=1` delante, por ejemplo:
`MSYS_NO_PATHCONV=1 docker compose exec -T postgres psql -U lab -d boards -f /lab/evidence.sql`.

**Importante:** después de editar `decisions.py` hay que hacer `docker compose restart content`.
Si no, el contenedor sigue con el código viejo en memoria (nos pasó, ver §8).

---

## 11. Lo que falta

Ya están completos: `entrega/MATRIZ.md`, `entrega/ADR-001.md`, `entrega/EVIDENCIAS.md` y `entrega/dashboard.json`.

Solo queda entregar en Teams el enlace del repositorio y el commit final.
