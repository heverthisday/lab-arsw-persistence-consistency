"""ÚNICO archivo de código que deben modificar los estudiantes.
Consultar README y docs/CONTRATOS.md antes de cambiar cada función.
"""
from pymongo import ReturnDocument
from redis.exceptions import RedisError

def save_board(collection, board_id, expected_version, title):
    # TODO 1 (resuelto): la versión esperada forma parte del FILTRO de la misma
    # operación. MongoDB evalúa filtro + $set + $inc de forma atómica sobre un
    # documento, así que de dos escritores con la misma versión solo uno coincide;
    # el otro obtiene None (la API lo traduce a 409). Un find + update separado
    # dejaría una ventana entre la lectura y la escritura (ediciones perdidas).
    return collection.find_one_and_update(
        {'_id': board_id, 'version': expected_version},
        {'$set': {'title': title}, '$inc': {'version': 1}},
        return_document=ReturnDocument.AFTER,
    )

def permission_for_write(user, board_id, cached_permission, authoritative_permission):
    # TODO 2 (resuelto): una escritura es una operación crítica; la caché solo sirve
    # para la UI. Se consulta SIEMPRE la fuente autoritativa (Gestión/PostgreSQL).
    # - Revocación confirmada antes de iniciar la escritura -> can_edit=False -> 403.
    # - Si Gestión no responde, authoritative_permission lanza HTTPException(503);
    #   NO se captura aquí para no convertir una falla en una concesión (fail-closed).
    # `cached_permission` se recibe por contrato pero deliberadamente no se usa.
    # Costo: un viaje HTTP a Gestión (+ una lectura PK en PostgreSQL) por cada PUT.
    return authoritative_permission(user, board_id)

def touch_presence(client, key, ttl):
    # TODO 3 (resuelto): valor + expiración en UNA sola escritura (SET ... EX ttl).
    # Con SET y EXPIRE separados, un fallo entre ambos dejaría una clave eterna.
    # Cada heartbeat reescribe la clave y renueva el TTL. Si Redis falla se captura
    # solo RedisError (no errores de programación) y se devuelve False: la API
    # responde 200 con available:false e incrementa el contador de degradación.
    try:
        client.set(key, 'online', ex=ttl)
        return True
    except RedisError:
        return False
