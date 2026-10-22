# Decision 0001: genesis del borde

Fecha: 2026-10-22

## Decision

Se siembra `ia_nest_edge` como semilla documental, sin codigo ni contrato
publico. Su razon de ser, su zona (Exterior), su orden en el plan de apertura y
su criterio de salida estan decididos en meta ADR 0013; este repo no los repite.

## Motivo

La familia del operador es el primer consumidor que no es el operador: dispara
meta ADR 0011, que fijo el hogar de la autenticacion en el borde y difirio el
mecanismo hasta que existiera ese consumidor.

## Consecuencia

- La fila del borde en `meta docs/REGISTRO_CAPAS.md` pasa a semilla.
- El mecanismo de autenticacion, la traduccion de conversaciones a sesiones y
  la aplicacion del perfil se deciden aqui, una a una (`docs/PLAN.md`), antes
  del primer brief.
- Sin SemVer ni tag hasta que exista contrato publico.

## Impacto de version

Ninguno: no hay contrato publico.

## Estado posterior

2026-10-22: existe contrato publico (la piel OpenAI de edge ADR 0002). Que
cuenta como contrato, en `docs/VERSIONADO.md`; primera version, `v0.1.0`.
