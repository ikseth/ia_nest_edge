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
  error `SessionAlreadyExistsError`). Pendiente: verificacion EN VIVO en la
  visita de laboratorio, contra la version desplegada. Hasta entonces el rango
  queda declarado, no verificado.

- `ia_nest_core`, solo a traves de extended (garantia de transparencia de
  extended). El borde no llama al core directamente.

## Pendiente de entrega en otras capas

- `edge CR-0001` (core) y `edge CR-0002` (extended): hasta que se entreguen,
  `interlocutor_profile` se envia y extended lo descarta en silencio. No rompe
  nada; bloquea la entrada de la familia (meta ADR 0013).
