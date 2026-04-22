# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MxPedDesistimientoWizard(models.TransientModel):
    _name = "mx.ped.desistimiento.wizard"
    _description = "Wizard para generar pedimento de Eliminación o Desistimiento"

    # ── Operacion original ────────────────────────────────────────────────────
    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Pedimento original",
        required=True,
        readonly=True,
        ondelete="cascade",
    )

    # ── Datos de solo lectura del pedimento original (display) ────────────────
    orig_pedimento_numero = fields.Char(string="Núm. pedimento", readonly=True)
    orig_patente = fields.Char(string="Patente", readonly=True)
    orig_aduana = fields.Char(string="Aduana / Sección", readonly=True)
    orig_clave_pedimento = fields.Char(string="Clave", readonly=True)
    orig_tipo_operacion = fields.Char(string="Tipo de operación", readonly=True)
    orig_fecha_operacion = fields.Date(string="Fecha operación original", readonly=True)
    orig_fecha_pago = fields.Date(string="Fecha de pago original", readonly=True)
    orig_acuse_validacion = fields.Char(string="Acuse de validación original", readonly=True)

    # ── Datos del nuevo pedimento ─────────────────────────────────────────────
    tipo_movimiento = fields.Selection(
        [
            ("2", "Eliminación  (mov. 2)"),
            ("3", "Desistimiento  (mov. 3)"),
        ],
        string="Tipo de cancelación",
        required=True,
        default="3",
        help=(
            "Eliminación (2): el pedimento fue validado por el SAAI pero aún NO fue pagado.\n"
            "Desistimiento (3): el pedimento fue validado y pagado pero la mercancía "
            "no entró ni salió del país."
        ),
    )
    motivo = fields.Text(
        string="Motivo",
        required=True,
        help="Texto que se transmite en el campo 'motivo' del registro 800. "
             "Describe la razón de la cancelación/desistimiento.",
    )
    nueva_fecha_operacion = fields.Date(
        string="Fecha del nuevo pedimento",
        required=True,
        default=fields.Date.context_today,
        help="Fecha con la que se timbrará el nuevo pedimento de desistimiento/eliminación.",
    )
    nuevo_acuse_validacion = fields.Char(
        string="Acuse de validación (nuevo)",
        size=8,
        help="Código de 8 dígitos generado por el SAAI al presentar el nuevo pedimento. "
             "Puedes dejarlo vacío ahora y llenarlo después de la presentación.",
    )

    # ── Prefill desde la operación original ──────────────────────────────────
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        op_id = self.env.context.get("default_operacion_id") or res.get("operacion_id")
        if op_id:
            op = self.env["mx.ped.operacion"].browse(op_id)
            tipo_op_label = dict(
                op._fields["tipo_operacion"].selection
            ).get(op.tipo_operacion, op.tipo_operacion or "")
            res.update({
                "orig_pedimento_numero": op.pedimento_numero or "",
                "orig_patente": op.patente or "",
                "orig_aduana": (
                    op.aduana_seccion_despacho_id.display_name
                    or op.aduana_clave
                    or ""
                ),
                "orig_clave_pedimento": op.clave_pedimento or "",
                "orig_tipo_operacion": tipo_op_label,
                "orig_fecha_operacion": op.fecha_operacion,
                "orig_fecha_pago": op.fecha_pago,
                "orig_acuse_validacion": op.acuse_validacion or "",
                # Lineamiento SAAI VOCE M3 pág. 35: campo 6 del registro 500
                # en desistimiento/eliminación debe contener el acuse del
                # pedimento ORIGINAL (el código de 8 chars que devolvió el SAAI
                # al validar el pedimento que se va a cancelar).
                "nuevo_acuse_validacion": op.acuse_validacion or "",
            })
        return res

    # ── Acción principal ──────────────────────────────────────────────────────
    def action_crear_desistimiento(self):
        self.ensure_one()
        op = self.operacion_id

        # Validaciones previas
        if not op:
            raise UserError(_("No hay pedimento original seleccionado."))
        if not op.pedimento_numero:
            raise UserError(_(
                "El pedimento original no tiene número de pedimento asignado. "
                "Asigne el número antes de generar el desistimiento/eliminación."
            ))
        if not op.lead_id:
            raise UserError(_(
                "El pedimento original no tiene Lead/expediente asociado. "
                "El wizard necesita el Lead para copiar los datos del encabezado."
            ))
        if not (self.motivo or "").strip():
            raise UserError(_("El motivo es obligatorio para el registro 800."))

        tipo_label = dict(self._fields["tipo_movimiento"].selection).get(
            self.tipo_movimiento, self.tipo_movimiento
        )
        tipo_prefix = "ELIM" if self.tipo_movimiento == "2" else "DESIST"

        # Construir valores del nuevo pedimento
        vals = {
            "name": f"{tipo_prefix}/{op.pedimento_numero or op.name}",
            "lead_id": op.lead_id.id,
            "layout_id": op.layout_id.id if op.layout_id else False,
            "tipo_operacion": op.tipo_operacion,
            "regimen": op.regimen,
            "clave_pedimento_id": op.clave_pedimento_id.id if op.clave_pedimento_id else False,
            "aduana_seccion_despacho_id": (
                op.aduana_seccion_despacho_id.id if op.aduana_seccion_despacho_id else False
            ),
            "aduana_clave": op.aduana_clave,
            "agente_aduanal_id": op.agente_aduanal_id.id if op.agente_aduanal_id else False,
            "patente": op.patente,
            # En desist/eliminación el numero_pedimento referenciado en el TXT
            # ES el número del pedimento que se cancela.
            "pedimento_numero": op.pedimento_numero,
            "tipo_movimiento": self.tipo_movimiento,
            "fecha_operacion": self.nueva_fecha_operacion,
            "fecha_pago": self.nueva_fecha_operacion,
            "motivo_cancelacion": (self.motivo or "").strip(),
            "acuse_validacion": self.nuevo_acuse_validacion or False,
            # Campos rect_* para trazabilidad interna y posibles registros de referencia
            "rect_pedimento_original": op.pedimento_numero,
            "rect_patente_original": op.patente,
            "rect_aduana_original_id": (
                op.aduana_seccion_despacho_id.id if op.aduana_seccion_despacho_id else False
            ),
            "rect_clave_pedimento_original_id": (
                op.clave_pedimento_id.id if op.clave_pedimento_id else False
            ),
            "rect_fecha_pago_original": op.fecha_pago or op.fecha_operacion,
        }

        new_op = self.env["mx.ped.operacion"].with_context(
            skip_auto_generated_refresh=True,
            creating_desistimiento=True,   # salta constraint acuse en create
        ).create(vals)

        # Carga los registros desde el Lead.
        # El rulepack ya contiene process.rules "allow_only_records: [500, 800, 801]"
        # para tipo_movimiento 2 y 3, por lo que action_cargar_desde_lead solo
        # generará esos tres registros — sin partidas, sin contribuciones.
        new_op.action_cargar_desde_lead()

        # action_cargar_desde_lead puede sobrescribir acuse_validacion con el
        # del lead. Forzamos el valor correcto: el acuse del pedimento original,
        # que es lo que exige el lineamiento SAAI VOCE M3 (pág. 35, campo 6
        # del registro 500) para desistimiento/eliminación.
        acuse_correcto = (self.nuevo_acuse_validacion or "").strip() or False
        new_op.with_context(creating_desistimiento=True).write({
            "acuse_validacion": acuse_correcto,
        })

        # Registrar en el chatter del pedimento original para trazabilidad
        op.message_post(
            body=_(
                "Se generó pedimento de <b>%s</b> (mov. %s) a partir de esta operación.<br/>"
                "Nuevo pedimento ID: <b>%s</b> — Núm.: <b>%s</b>"
            ) % (
                tipo_label,
                self.tipo_movimiento,
                new_op.id,
                new_op.pedimento_numero or "—",
            ),
        )

        return {
            "type": "ir.actions.act_window",
            "name": tipo_label,
            "res_model": "mx.ped.operacion",
            "view_mode": "form",
            "res_id": new_op.id,
            "target": "current",
        }
