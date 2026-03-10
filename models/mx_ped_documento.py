from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedDocumento(models.Model):
    _name = "mx.ped.documento"
    _description = "Pedimento - Documento"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )
    remesa_id = fields.Many2one(
        "mx.ped.consolidado.remesa",
        string="Remesa consolidada",
        ondelete="set null",
        index=True,
    )
    es_documento_principal = fields.Boolean(
        string="Documento principal",
        default=False,
        help="Marca el documento principal o la relacion de facturas que acompana fisicamente a la remesa.",
    )

    partida_id = fields.Many2one("mx.ped.partida", ondelete="set null")
    aplica_partida_especifica = fields.Boolean(
        string="Aplica a una partida especifica",
        default=False,
        help="Marca esta opcion solo cuando el documento corresponda a una partida concreta dentro de la remesa.",
    )

    tipo = fields.Selection(
        [
            ("factura", "Factura"),
            ("packing", "Packing List"),
            ("bl_awb", "BL/AWB"),
            ("cove", "COVE"),
            ("edocument", "e-Document"),
            ("coo", "Certificado de Origen"),
            ("nom", "NOM / Permiso"),
            ("otro", "Otro"),
        ],
        default="otro",
        required=True,
        index=True,
    )
    registro_codigo = fields.Selection(
        [
            ("510", "510 - Contribuciones cabecera"),
            ("514", "514 - Documentos virtuales"),
            ("557", "557 - Contribuciones partida"),
            ("otro", "Otro"),
        ],
        string="Registro SAAI",
        default="otro",
        required=True,
        index=True,
    )
    forma_pago_id = fields.Many2one(
        "mx.forma.pago",
        string="Forma de pago",
        domain="[('active','=',True), '|', ('scope','=','all'), ('scope','=','514')]",
        ondelete="restrict",
    )
    forma_pago_code = fields.Char(
        string="Forma de pago (clave)",
        related="forma_pago_id.code",
        store=True,
        readonly=True,
    )

    folio = fields.Char()
    fecha = fields.Datetime()

    # Usa ir.attachment para subir archivos
    attachment_id = fields.Many2one("ir.attachment", string="Archivo")
    archivo_file = fields.Binary(string="Archivo")
    archivo_filename = fields.Char(string="Nombre archivo")

    estatus = fields.Selection(
        [("pendiente", "Pendiente"), ("ok", "OK"), ("rechazado", "Rechazado")],
        default="pendiente",
        index=True,
    )

    notas = fields.Text()

    @api.onchange("aplica_partida_especifica")
    def _onchange_aplica_partida_especifica(self):
        for rec in self:
            if not rec.aplica_partida_especifica:
                rec.partida_id = False

    @api.onchange("partida_id")
    def _onchange_partida_id(self):
        for rec in self:
            if rec.partida_id:
                rec.aplica_partida_especifica = True

    @api.constrains("remesa_id", "operacion_id", "partida_id")
    def _check_remesa_integrity(self):
        for rec in self:
            if rec.remesa_id and rec.remesa_id.operacion_id != rec.operacion_id:
                raise ValidationError("La remesa del documento debe pertenecer a la misma operacion.")
            if rec.partida_id and rec.partida_id.operacion_id != rec.operacion_id:
                raise ValidationError("La partida del documento debe pertenecer a la misma operacion.")
            if not rec.aplica_partida_especifica and rec.partida_id:
                raise ValidationError("Si el documento tiene partida, marca que aplica a una partida especifica.")

    @api.constrains("remesa_id", "es_documento_principal")
    def _check_single_documento_principal(self):
        for rec in self.filtered(lambda r: r.remesa_id and r.es_documento_principal):
            duplicate = self.search_count([
                ("id", "!=", rec.id),
                ("remesa_id", "=", rec.remesa_id.id),
                ("es_documento_principal", "=", True),
            ])
            if duplicate:
                raise ValidationError("Solo puede existir un documento principal por remesa.")
