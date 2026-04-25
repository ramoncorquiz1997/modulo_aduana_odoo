"""
Post-migration 18.0.1.10.0
===========================
Recupera los valores de cfdi_termino_facturacion que estaban como texto libre
(ej. "CIF", "FOB", "EXW") buscando el ID correspondiente en account_incoterms
por código (code) o por nombre (name ILIKE).

La columna *_old_char fue preservada en el pre-migrate; la eliminamos al final.
"""
import logging

_logger = logging.getLogger(__name__)

_AFFECTED = [
    ("crm_lead_documento", "cfdi_termino_facturacion"),
    ("mx_ped_documento",   "cfdi_termino_facturacion"),
]


def migrate(cr, version):
    if not version:
        return  # instalación limpia — nada que rescatar

    for table, column in _AFFECTED:
        backup_col = column + "_old_char"

        # Verificar que el backup existe (lo creó el pre-migrate)
        cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, backup_col))
        if not cr.fetchone():
            _logger.info("post-migrate: no hay backup %s.%s, se omite.", table, backup_col)
            continue

        # Verificar que la nueva columna integer ya existe (la creó Odoo en init_models)
        cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table, column))
        row = cr.fetchone()
        if not row or row[0] not in ("integer", "int4", "int8", "bigint"):
            _logger.warning(
                "post-migrate: %s.%s no es integer aún (%s), se omite recuperación.",
                table, column, row[0] if row else "no existe",
            )
            continue

        # Recuperar: buscar en account_incoterms por código exacto (upper)
        # Primero intentamos match exacto por code, luego por name ILIKE
        cr.execute(f"""
            UPDATE "{table}" t
            SET "{column}" = ai.id
            FROM account_incoterms ai
            WHERE t."{backup_col}" IS NOT NULL
              AND t."{column}" IS NULL
              AND UPPER(TRIM(t."{backup_col}")) = UPPER(TRIM(ai.code))
        """)
        matched_code = cr.rowcount
        _logger.info("post-migrate: %s.%s — %d filas recuperadas por código.", table, column, matched_code)

        # Segundo intento: por nombre aproximado.
        # account_incoterms.name es JSONB en Odoo 18 (campo traducible),
        # hay que castearlo a text antes de comparar con ILIKE.
        cr.execute(f"""
            UPDATE "{table}" t
            SET "{column}" = ai.id
            FROM account_incoterms ai
            WHERE t."{backup_col}" IS NOT NULL
              AND t."{column}" IS NULL
              AND (ai.name::text) ILIKE '%' || TRIM(t."{backup_col}") || '%'
        """)
        matched_name = cr.rowcount
        _logger.info("post-migrate: %s.%s — %d filas recuperadas por nombre.", table, column, matched_name)

        # Log de filas que no pudieron recuperarse (quedan NULL)
        cr.execute(f"""
            SELECT COUNT(*) FROM "{table}"
            WHERE "{backup_col}" IS NOT NULL AND "{column}" IS NULL
        """)
        not_recovered = cr.fetchone()[0]
        if not_recovered:
            _logger.warning(
                "post-migrate: %s.%s — %d filas con valor '%s' no recuperado (incoterm no encontrado en catálogo). "
                "Quedan como NULL y deben seleccionarse manualmente.",
                table, column, not_recovered, backup_col,
            )
            # Mostrar los valores únicos que no pudieron recuperarse para diagnóstico
            cr.execute(f"""
                SELECT DISTINCT "{backup_col}", COUNT(*) as cnt
                FROM "{table}"
                WHERE "{backup_col}" IS NOT NULL AND "{column}" IS NULL
                GROUP BY "{backup_col}"
                ORDER BY cnt DESC
                LIMIT 20
            """)
            for val, cnt in cr.fetchall():
                _logger.warning("  -> valor no recuperado: '%s' (%d registros)", val, cnt)

        # Eliminar columna backup — ya no se necesita
        cr.execute(f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS "{backup_col}"')
        _logger.info("post-migrate: backup %s.%s eliminado.", table, backup_col)
