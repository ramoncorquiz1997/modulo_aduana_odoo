# -*- coding: utf-8 -*-
from odoo import fields, models, _

class AduanaAuditMixin(models.AbstractModel):
    _name = "aduana.audit.mixin"
    _description = "Auditoria transversal para modelos aduanales"

    _AUDIT_EXCLUDED_FIELDS = {
        "__last_update",
        "message_main_attachment_id",
        "message_follower_ids",
        "message_partner_ids",
        "message_ids",
        "activity_ids",
        "activity_exception_decoration",
        "activity_exception_icon",
        "activity_state",
        "activity_summary",
        "activity_type_icon",
        "activity_type_id",
        "activity_user_id",
        "activity_date_deadline",
        "message_attachment_count",
        "message_has_error",
        "message_has_error_counter",
        "message_has_sms_error",
        "message_is_follower",
        "message_needaction",
        "message_needaction_counter",
        "message_unread",
        "message_unread_counter",
        "write_date",
        "write_uid",
    }

    def _audit_fields_from_vals(self, vals):
        result = []
        for name in (vals or {}).keys():
            if name in self._AUDIT_EXCLUDED_FIELDS:
                continue
            if name not in self._fields:
                continue
            result.append(name)
        return result

    def _audit_value_text(self, field, value):
        if field.type == "binary":
            return _("[archivo binario]")
        if field.type == "many2one":
            return value.display_name if value else ""
        if field.type in ("many2many", "one2many"):
            if not value:
                return ""
            names = value.mapped("display_name")
            if len(names) > 5:
                return "%s ... (+%s)" % (", ".join(names[:5]), len(names) - 5)
            return ", ".join(names)
        if field.type == "boolean":
            return _("Si") if value else _("No")
        if field.type == "date":
            return fields.Date.to_string(value) if value else ""
        if field.type == "datetime":
            return fields.Datetime.to_string(value) if value else ""
        txt = "" if value in (False, None) else str(value)
        return txt if len(txt) <= 300 else (txt[:300] + " ...")

    def _audit_snapshot(self, field_names):
        snap = {}
        for rec in self:
            rec_data = {}
            for name in field_names:
                field = rec._fields.get(name)
                if not field:
                    continue
                rec_data[name] = self._audit_value_text(field, rec[name])
            snap[rec.id] = rec_data
        return snap

    def _audit_post_message(self, body):
        self.with_context(skip_aduana_audit=True).message_post(
            body=body,
            subtype_xmlid="mail.mt_note",
        )

    @staticmethod
    def _audit_html_escape(text):
        txt = str(text or "")
        return (
            txt.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get("skip_aduana_audit"):
            return records
        for rec, vals in zip(records, vals_list):
            tracked = rec._audit_fields_from_vals(vals)
            if not tracked:
                rec._audit_post_message(_("Registro creado."))
                continue
            lines = []
            for name in tracked:
                field = rec._fields.get(name)
                value_txt = rec._audit_value_text(field, rec[name]) if field else ""
                lines.append("<li><b>%s</b>: %s</li>" % (self._audit_html_escape(name), self._audit_html_escape(value_txt)))
            rec._audit_post_message(_("Registro creado.<ul>%s</ul>") % "".join(lines))
        return records

    def write(self, vals):
        if self.env.context.get("skip_aduana_audit"):
            return super().write(vals)
        tracked = self._audit_fields_from_vals(vals)
        before = self._audit_snapshot(tracked) if tracked else {}
        result = super().write(vals)
        if not tracked:
            return result
        for rec in self:
            changes = []
            rec_before = before.get(rec.id, {})
            for name in tracked:
                field = rec._fields.get(name)
                if not field:
                    continue
                old_txt = rec_before.get(name, "")
                new_txt = rec._audit_value_text(field, rec[name])
                if old_txt == new_txt:
                    continue
                changes.append(
                    "<li><b>%s</b>: %s -> %s</li>"
                    % (
                        self._audit_html_escape(name),
                        self._audit_html_escape(old_txt),
                        self._audit_html_escape(new_txt),
                    )
                )
            if changes:
                rec._audit_post_message(_("Cambios guardados.<ul>%s</ul>") % "".join(changes))
        return result

    def unlink(self):
        if self.env.context.get("skip_aduana_audit"):
            return super().unlink()
        for rec in self:
            rec._audit_post_message(_("Registro eliminado por %s.") % self.env.user.display_name)
        return super().unlink()


# ====== EXTENSIONES DE MODELOS (HERENCIA DE CLASE) ======

class CrmLead(models.Model):
    _name = 'crm.lead'
    _inherit = ['crm.lead', 'aduana.audit.mixin']

class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'aduana.audit.mixin']

class CrmLeadOperacionLine(models.Model):
    _name = 'crm.lead.operacion.line'
    _inherit = ['crm.lead.operacion.line', 'aduana.audit.mixin']

class MxPedOperacion(models.Model):
    _name = 'mx.ped.operacion'
    _inherit = ['mx.ped.operacion', 'aduana.audit.mixin']

class MxPedPartida(models.Model):
    _name = 'mx.ped.partida'
    _inherit = ['mx.ped.partida', 'aduana.audit.mixin']

class MxPedDocumento(models.Model):
    _name = 'mx.ped.documento'
    _inherit = ['mx.ped.documento', 'aduana.audit.mixin']

class MxPedRegistro(models.Model):
    _name = 'mx.ped.registro'
    _inherit = ['mx.ped.registro', 'aduana.audit.mixin']

class MxPedAduanaSeccion(models.Model):
    _name = 'mx.ped.aduana.seccion'
    _inherit = ['mx.ped.aduana.seccion', 'aduana.audit.mixin']

class MxPedClave(models.Model):
    _name = 'mx.ped.clave'
    _inherit = ['mx.ped.clave', 'aduana.audit.mixin']

class MxPedClaveReglaRegistro(models.Model):
    _name = 'mx.ped.clave.regla.registro'
    _inherit = ['mx.ped.clave.regla.registro', 'aduana.audit.mixin']

class MxPedEstructuraRegla(models.Model):
    _name = 'mx.ped.estructura.regla'
    _inherit = ['mx.ped.estructura.regla', 'aduana.audit.mixin']

class MxPedEstructuraReglaLine(models.Model):
    _name = 'mx.ped.estructura.regla.line'
    _inherit = ['mx.ped.estructura.regla.line', 'aduana.audit.mixin']

class MxPedRulepack(models.Model):
    _name = 'mx.ped.rulepack'
    _inherit = ['mx.ped.rulepack', 'aduana.audit.mixin']

class MxPedRulepackScenario(models.Model):
    _name = 'mx.ped.rulepack.scenario'
    _inherit = ['mx.ped.rulepack.scenario', 'aduana.audit.mixin']

class MxPedRulepackSelector(models.Model):
    _name = 'mx.ped.rulepack.selector'
    _inherit = ['mx.ped.rulepack.selector', 'aduana.audit.mixin']

class MxPedRulepackProcessRule(models.Model):
    _name = 'mx.ped.rulepack.process.rule'
    _inherit = ['mx.ped.rulepack.process.rule', 'aduana.audit.mixin']

class MxPedRulepackConditionRule(models.Model):
    _name = 'mx.ped.rulepack.condition.rule'
    _inherit = ['mx.ped.rulepack.condition.rule', 'aduana.audit.mixin']

class MxPedLayout(models.Model):
    _name = 'mx.ped.layout'
    _inherit = ['mx.ped.layout', 'aduana.audit.mixin']

class MxPedLayoutRegistro(models.Model):
    _name = 'mx.ped.layout.registro'
    _inherit = ['mx.ped.layout.registro', 'aduana.audit.mixin']

class MxPedLayoutCampo(models.Model):
    _name = 'mx.ped.layout.campo'
    _inherit = ['mx.ped.layout.campo', 'aduana.audit.mixin']

class MxPedFraccion(models.Model):
    _name = 'mx.ped.fraccion'
    _inherit = ['mx.ped.fraccion', 'aduana.audit.mixin']

class MxPedFraccionTasa(models.Model):
    _name = 'mx.ped.fraccion.tasa'
    _inherit = ['mx.ped.fraccion.tasa', 'aduana.audit.mixin']

class MxPedUm(models.Model):
    _name = 'mx.ped.um'
    _inherit = ['mx.ped.um', 'aduana.audit.mixin']

class MxNom(models.Model):
    _name = 'mx.nom'
    _inherit = ['mx.nom', 'aduana.audit.mixin']

class MxRrna(models.Model):
    _name = 'mx.rrna'
    _inherit = ['mx.rrna', 'aduana.audit.mixin']

class MxPermiso(models.Model):
    _name = 'mx.permiso'
    _inherit = ['mx.permiso', 'aduana.audit.mixin']

class MxNico(models.Model):
    _name = 'mx.nico'
    _inherit = ['mx.nico', 'aduana.audit.mixin']

class MxFormaPago(models.Model):
    _name = 'mx.forma.pago'
    _inherit = ['mx.forma.pago', 'aduana.audit.mixin']

class MxPedContribucionGlobal(models.Model):
    _name = 'mx.ped.contribucion.global'
    _inherit = ['mx.ped.contribucion.global', 'aduana.audit.mixin']

class MxPedPartidaContribucion(models.Model):
    _name = 'mx.ped.partida.contribucion'
    _inherit = ['mx.ped.partida.contribucion', 'aduana.audit.mixin']

class MxPedTipoMovimiento(models.Model):
    _name = 'mx.ped.tipo.movimiento'
    _inherit = ['mx.ped.tipo.movimiento', 'aduana.audit.mixin']

class MxPedTipoContenedor(models.Model):
    _name = 'mx.ped.tipo.contenedor'
    _inherit = ['mx.ped.tipo.contenedor', 'aduana.audit.mixin']

class MxPedNumeroControl(models.Model):
    _name = 'mx.ped.numero.control'
    _inherit = ['mx.ped.numero.control', 'aduana.audit.mixin']

class MxPedNumeroControlLog(models.Model):
    _name = 'mx.ped.numero.control.log'
    _inherit = ['mx.ped.numero.control.log', 'aduana.audit.mixin']

class AduanaCatalogoTipoOperacion(models.Model):
    _name = 'aduana.catalogo.tipo_operacion'
    _inherit = ['aduana.catalogo.tipo_operacion', 'aduana.audit.mixin']

class AduanaCatalogoRegimen(models.Model):
    _name = 'aduana.catalogo.regimen'
    _inherit = ['aduana.catalogo.regimen', 'aduana.audit.mixin']

class AduanaCatalogoAduana(models.Model):
    _name = 'aduana.catalogo.aduana'
    _inherit = ['aduana.catalogo.aduana', 'aduana.audit.mixin']

class AduanaCatalogoClavePedimento(models.Model):
    _name = 'aduana.catalogo.clave_pedimento'
    _inherit = ['aduana.catalogo.clave_pedimento', 'aduana.audit.mixin']

class AduanaLayoutRegistroTipo(models.Model):
    _name = 'aduana.layout_registro_tipo'
    _inherit = ['aduana.layout_registro_tipo', 'aduana.audit.mixin']

class AduanaLayoutRegistroCampo(models.Model):
    _name = 'aduana.layout_registro_campo'
    _inherit = ['aduana.layout_registro_campo', 'aduana.audit.mixin']

class AduanaPedimento(models.Model):
    _name = 'aduana.pedimento'
    _inherit = ['aduana.pedimento', 'aduana.audit.mixin']

class AduanaPartida(models.Model):
    _name = 'aduana.partida'
    _inherit = ['aduana.partida', 'aduana.audit.mixin']

class AduanaPartidaIdentificador(models.Model):
    _name = 'aduana.partida.identificador'
    _inherit = ['aduana.partida.identificador', 'aduana.audit.mixin']

class AduanaPartidaContribucion(models.Model):
    _name = 'aduana.partida.contribucion'
    _inherit = ['aduana.partida.contribucion', 'aduana.audit.mixin']

class AduanaFactura(models.Model):
    _name = 'aduana.factura'
    _inherit = ['aduana.factura', 'aduana.audit.mixin']

class AduanaDocumento(models.Model):
    _name = 'aduana.documento'
    _inherit = ['aduana.documento', 'aduana.audit.mixin']

class AduanaContenedor(models.Model):
    _name = 'aduana.contenedor'
    _inherit = ['aduana.contenedor', 'aduana.audit.mixin']

class AduanaContribucionGlobal(models.Model):
    _name = 'aduana.contribucion.global'
    _inherit = ['aduana.contribucion.global', 'aduana.audit.mixin']

class AduanaPedimentoRegistroTecnico(models.Model):
    _name = 'aduana.pedimento.registro_tecnico'
    _inherit = ['aduana.pedimento.registro_tecnico', 'aduana.audit.mixin']