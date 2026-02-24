from odoo import fields, models


class MxPedDocumento(models.Model):
    _name = "mx.ped.documento"
    _description = "Pedimento - Documento"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )

    partida_id = fields.Many2one("mx.ped.partida", ondelete="set null")

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

    estatus = fields.Selection(
        [("pendiente", "Pendiente"), ("ok", "OK"), ("rechazado", "Rechazado")],
        default="pendiente",
        index=True,
    )

    notas = fields.Text()
