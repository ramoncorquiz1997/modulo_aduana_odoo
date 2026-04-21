# Changelog — Aduanex

## [18.0.1.7.6] — 2026-04-21

### Fixed
- **Registro 800 (Firma Electrónica)**: se generaba solo en pedimentos de cancelación/desistimiento.
  Corregido per lineamiento SAAI M3 v9.0: obligatorio en todos los tipos *excepto*
  Despacho Anticipado (mov=7) y Confirmación de Pago (mov=8).
- **Registro 505 (Documentos)**: solo se generaba con la casilla `send_505_contingency` activa.
  Ahora se genera siempre que existan documentos de tipo `factura/cove/otro`, independientemente del modo contingencia.
- **Duplicados 505**: el loop de layout ya no procesa el código 505 (se saltea igual que 509/510/557), evitando entradas duplicadas cuando el layout tiene configurado ese registro.

## [18.0.1.7.5] — anterior

### Fixed
- `record_separator`: almacenado como literal `\n` (2 chars); ahora se normaliza en `create`/`write` y via `init()` SQL.
  Añadido helper `_get_record_separator()` usado en los 3 puntos de generación del VOCE.
- Registro 800 ya no se inyecta desde el loop de layout (solo via `auto_single`); evita aparición en pedimentos normales.
- `action_generar_contribuciones_557`: fallback por `fraccion_arancelaria` cuando `fraccion_id` está vacío; guarda `fraccion_id` en la partida.
  Filtro cambiado a `amount > 0 OR rate > 0` para no omitir tasas con valor 0 en valor_mxn.
- Cargos adicionales (tab): domain del campo `partida_id` corregido para filtrar solo partidas de la operación actual.
- `action_cargar_desde_lead`: 505, 509, 510, 557, 514, 800, 801, 701, 702, 301, 302 se saltan en el loop de layout; se manejan por bloques propios.
- `pedimento_proforma_v2.py` `parse_txt`: normaliza `\n` literal antes de `splitlines()`.
