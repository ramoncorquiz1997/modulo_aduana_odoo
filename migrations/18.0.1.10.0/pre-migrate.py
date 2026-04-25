"""
Pre-migration 18.0.1.10.0
==========================
Maneja el cambio de tipo de columna cfdi_termino_facturacion:
  Char (texto libre como "CIF", "FOB") -> Many2one(account.incoterms) (integer FK)

Postgres no puede hacer CAST automático de varchar a integer, así que:
1. Renombramos la columna char a *_old_char (backup)
2. Odoo creará la nueva columna integer vacía en el init_models normal
3. El post-migrate recuperará los valores haciendo lookup en account_incoterms
"""
import logging

_logger = logging.getLogger(__name__)

# Tablas y columnas afectadas por el cambio de tipo
_AFFECTED = [
    ("crm_lead_documento", "cfdi_termino_facturacion"),
    ("mx_ped_documento",   "cfdi_termino_facturacion"),
]


def migrate(cr, version):
    if not version:
        return  # instalación limpia — no hay nada que rescatar

    for table, column in _AFFECTED:
        # Verificar si la tabla y columna existen
        cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, column))
        row = cr.fetchone()
        if not row:
            _logger.info("pre-migrate: %s.%s no existe, nada que hacer.", table, column)
            continue

        data_type = row[0]
        if data_type in ("integer", "int4", "int8", "bigint"):
            _logger.info(
                "pre-migrate: %s.%s ya es tipo entero (%s), no requiere migración.",
                table, column, data_type,
            )
            continue

        # Columna es varchar/char — renombrar para que Odoo la recree como integer
        backup_col = column + "_old_char"
        # Borrar backup previo si existe (de una migración fallida anterior)
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, backup_col))
        if cr.fetchone():
            cr.execute(f'ALTER TABLE "{table}" DROP COLUMN "{backup_col}"')
            _logger.info("pre-migrate: eliminado backup previo %s.%s", table, backup_col)

        cr.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{column}" TO "{backup_col}"')
        _logger.info(
            "pre-migrate: renombrado %s.%s -> %s para migración de tipo varchar->integer.",
            table, column, backup_col,
        )
