# Dependencias de ia_nest_edge

Politica: `ia_nest_meta/docs/REGISTRO_CAPAS.md` (regla de vinculo entre capas por
SemVer). Este fichero es el manifiesto de esta capa y es FUENTE DE VERDAD de sus
dependencias; el registro de capas del ente es un indice que lo refleja.

## Depende de

- `ia_nest_extended >=0.5 <0.6`. El borde usa su REST: `session.list` y
  `session.new` con identidad obligatoria (`extended ADR 0014` y `0015`),
  `prompt.*`, `reasoning.*` y `task.run` con sus parametros de extension
  (`domain`, `auto_domain`, `write_back`), y `domain.list` reenviado al core.

  **Verificacion.** Comprobado contra el CODIGO de `v0.5.2` al revisar la
  primera entrega (rutas, campos de peticion y respuesta, eventos de flujo,
  error `SessionAlreadyExistsError`).

  **Verificado EN VIVO** el 2026-10-26/27 en la visita de laboratorio: borde
  `v0.1.1` contra extended `v0.5.2` (core `v0.4.0` detras), los dos instalados
  desde su tag. Con Open WebUI como cliente real y sondas directas al borde:
  - `session.list` y `session.new` con identidad obligatoria: un chat es una
    sesion estable entre turnos y dos chats son dos sesiones;
  - `prompt.run` y `prompt.stream` (directo), `reasoning.run` y
    `reasoning.stream` (razonado) y `task.run` (iterativo), con `domain` fijo
    y automatico;
  - `write_back=false` en tareas de fondo: no dejan turno en la sesion;
  - `domain.list` reenviado al core: los dominios fijos del menu existen.

  Rango verificado: `v0.5.2`. El resto de `>=0.5 <0.6` sigue declarado, no
  medido.

- `ia_nest_core`, solo a traves de extended (garantia de transparencia de
  extended). El borde no llama al core directamente.

## Pendiente de entrega en otras capas

- `edge CR-0001` (core) y `edge CR-0002` (extended): hasta que se entreguen,
  `interlocutor_profile` se envia y extended lo descarta en silencio. No rompe
  nada; bloquea la entrada de la familia (meta ADR 0013).
