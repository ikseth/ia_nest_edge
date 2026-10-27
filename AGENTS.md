# Instrucciones para agentes de IA en ia_nest_edge

Las reglas transversales del ente (texto ASCII, identificadores en ingles
snake_case, citas `<repo> ADR NNNN`, repo publico, modo ciego, regla del
registro) viven en `ia_nest_meta` y no se repiten aqui. Lee antes:

1. `meta docs/CONVENCIONES_TRANSVERSALES.md` y `meta docs/DOCTRINA_MULTI_IA.md`
2. `meta docs/REGISTRO_CAPAS.md` y `meta docs/ARQUITECTURA_DE_CAPAS.md`
3. `meta ADR 0011` (quien autentica) y `meta ADR 0013` (por que existe este repo)
4. `core ADR 0033` (que es el ente y que es exterior)
5. `extended docs/EXTENDED_CONTRACT.md`, `extended ADR 0014` y `0015` (identidad
   y sesiones que este repo tiene que producir)
6. `README.md` y `docs/PLAN.md` de este repo

Orden entre capas: la hoja de ruta del ente, en `meta docs/plan/HOJA_DE_RUTA.md`
(meta ADR 0014). Los hilos de un hito salen de meta; el plan de este repo lleva
solo su detalle interno.

## Reglas propias de este repo

- **El borde no piensa.** No infiere, no recuerda, no delibera ni presenta
  (`core ADR 0033`). Si una pieza nueva hace alguna de las cuatro, no es de aqui.
- **Autentica una vez, aqui.** Las capas interiores consumen identidad afirmada
  y no reautentican (meta ADR 0011).
- **Contrato uniforme.** Lo de extended se reenvia con un mecanismo generico; la
  piel OpenAI es extension aditiva, nunca un catalogo espejo escrito a mano
  (meta ADR 0007).
- **Perfil infantil: falla cerrado.** Si no se puede determinar el perfil, se
  aplica el infantil. Como se aplica es provisional: su destino es conscience
  (meta ADR 0013).
- **Sin pantallas.** Lo que se ve es de `ia_nest_web`. Sustituir el webchat no
  debe editar ningun fichero de este repo (meta ADR 0013).
- **Credenciales fuera del repo.** Se versiona solo el `.example`.
- Mientras el repo sea semilla, todo documento nuevo nace `Estado: propuesta`.
