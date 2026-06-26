# MÃ³dulo actual

## CÃ³digo

```text
DELIVERY
```

## Nombre

<<<<<<< HEAD
Delivery.
=======
ConfiguraciÃ³n.
>>>>>>> claude/intelligent-clarke-uq1ck7

## Estado

```text
IN_PROGRESS
```

## IteraciÃ³n

```text
<<<<<<< HEAD
1
=======
6
>>>>>>> claude/intelligent-clarke-uq1ck7
```

## Objetivo

<<<<<<< HEAD
Auditar y refactorizar el módulo de Productos contra el checklist de
`SPJ_REFACTOR_SKILL.md` (REGLA CERO UUIDv7 + capas + UI sin SQL).

## Hallazgos abiertos

(pendiente de auditoría FASE 7 PRODUCTOS)

## Tests requeridos

(pendiente)
=======
Auditar y refactorizar el mÃ³dulo de ConfiguraciÃ³n contra todo el checklist de `SPJ_REFACTOR_SKILL.md`, no solo identidad UUIDv7.

## Hallazgos abiertos

- `CONFIGURACION-06-DOMAIN_RULES`: pendiente auditar las reglas de dominio del catÃ¡logo de toggles por sucursal, su normalizaciÃ³n y sus defaults canÃ³nicos tras cerrar la mutaciÃ³n legacy de PyQt.

## Tests requeridos

- Proteger que el siguiente lote no reintroduzca claves de mÃ³dulo no canÃ³nicas ni defaults implÃ­citos fuera del servicio de configuraciÃ³n.
>>>>>>> claude/intelligent-clarke-uq1ck7

## Bloqueos

Ninguno.

## PrÃ³xima acciÃ³n

<<<<<<< HEAD
Cerrado el gap de identidad (legacy repo + compras_pro). Pendiente menor: unidad enum -> settings.
lastrowid, int(_id), SQL en UI).
=======
`CONFIGURACION-05-MUTATIONS` cerrado sin infracciones pendientes. Continuar `CONFIGURACION-06-DOMAIN_RULES` para auditar reglas de dominio del catÃ¡logo de toggles y consolidar validaciones canÃ³nicas fuera de PyQt.
>>>>>>> claude/intelligent-clarke-uq1ck7
