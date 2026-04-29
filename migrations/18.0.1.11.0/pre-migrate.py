"""
Pre-migration 18.0.1.11.0
==========================
Limpieza del modelo mx.nico:
  - Elimina la columna fraccion_id (FK a mx.ped.fraccion, modelo obsoleto)
  - Elimina el constraint único fraccion+code y lo reemplaza por unique(code)

Cambios relacionados:
  - mx.ped.fraccion ya NO es la referencia de fracciones arancelarias.
    Fue reemplazado por mx.tigie.maestra (modelo plano).
  - mx_ped_rulepack ahora referencia mx.tigie.maestra en lugar de mx.ped.fraccion.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return  # instalación limpia, la columna nunca existió

    # 1. Eliminar constraint único viejo (fraccion_id, code)
    cr.execute("""
        ALTER TABLE mx_nico
        DROP CONSTRAINT IF EXISTS mx_nico_fraccion_code_uniq
    """)
    _logger.info("pre-migrate 11.0: constraint mx_nico_fraccion_code_uniq eliminado.")

    # 2. Eliminar la columna fraccion_id si existe
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mx_nico' AND column_name = 'fraccion_id'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE mx_nico DROP COLUMN fraccion_id")
        _logger.info("pre-migrate 11.0: columna mx_nico.fraccion_id eliminada.")
    else:
        _logger.info("pre-migrate 11.0: mx_nico.fraccion_id no existe, omitiendo.")

    # 3. Asegurarse de que el nuevo constraint único (code) no cause conflictos
    #    por registros duplicados — si hubiera varios NICOs con el mismo code
    #    pero diferente fraccion, quedarse solo con el de menor id.
    cr.execute("""
        DELETE FROM mx_nico
        WHERE id NOT IN (
            SELECT MIN(id) FROM mx_nico GROUP BY code
        )
    """)
    dupes = cr.rowcount
    if dupes:
        _logger.warning(
            "pre-migrate 11.0: eliminados %d registros duplicados de mx_nico "
            "(mismo code, diferente fraccion). Se conservó el de menor id.", dupes
        )

    # 4. Limpiar también la FK en mx_ped_rulepack_field_rule si apuntaba a mx.ped.fraccion
    #    (el campo fraccion_id ahora apunta a mx.tigie.maestra, diferente tabla)
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'mx_ped_rulepack_field_rule' AND column_name = 'fraccion_id'
    """)
    if cr.fetchone():
        # Verificar a qué tabla apunta la FK actual
        cr.execute("""
            SELECT ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            JOIN information_schema.referential_constraints rc
              ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = rc.constraint_name
            WHERE tc.table_name = 'mx_ped_rulepack_field_rule'
              AND kcu.column_name = 'fraccion_id'
              AND tc.constraint_type = 'FOREIGN KEY'
        """)
        row = cr.fetchone()
        if row and row[0] == 'mx_ped_fraccion':
            # Nullificar valores que apuntaban al modelo viejo y eliminar FK
            cr.execute("""
                ALTER TABLE mx_ped_rulepack_field_rule
                DROP CONSTRAINT IF EXISTS mx_ped_rulepack_field_rule_fraccion_id_fkey
            """)
            cr.execute("UPDATE mx_ped_rulepack_field_rule SET fraccion_id = NULL")
            _logger.info(
                "pre-migrate 11.0: FK mx_ped_rulepack_field_rule.fraccion_id "
                "(mx.ped.fraccion) eliminada. Odoo recreará la FK a mx.tigie.maestra."
            )
