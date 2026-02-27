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


class CrmLeadAudit(models.Model):
    _inherit = ["crm.lead", "aduana.audit.mixin"]


class ResPartnerAudit(models.Model):
    _inherit = ["res.partner", "aduana.audit.mixin"]


class CrmLeadOperacionLineAudit(models.Model):
    _inherit = ["crm.lead.operacion.line", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedOperacionAudit(models.Model):
    _inherit = ["mx.ped.operacion", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedPartidaAudit(models.Model):
    _inherit = ["mx.ped.partida", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedDocumentoAudit(models.Model):
    _inherit = ["mx.ped.documento", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedRegistroAudit(models.Model):
    _inherit = ["mx.ped.registro", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedAduanaSeccionAudit(models.Model):
    _inherit = ["mx.ped.aduana.seccion", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedClaveAudit(models.Model):
    _inherit = ["mx.ped.clave", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedClaveReglaRegistroAudit(models.Model):
    _inherit = ["mx.ped.clave.regla.registro", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedEstructuraReglaAudit(models.Model):
    _inherit = ["mx.ped.estructura.regla", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedEstructuraReglaLineAudit(models.Model):
    _inherit = ["mx.ped.estructura.regla.line", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedRulepackAudit(models.Model):
    _inherit = ["mx.ped.rulepack", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedRulepackScenarioAudit(models.Model):
    _inherit = ["mx.ped.rulepack.scenario", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedRulepackSelectorAudit(models.Model):
    _inherit = ["mx.ped.rulepack.selector", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedRulepackProcessRuleAudit(models.Model):
    _inherit = ["mx.ped.rulepack.process.rule", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedRulepackConditionRuleAudit(models.Model):
    _inherit = ["mx.ped.rulepack.condition.rule", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedLayoutAudit(models.Model):
    _inherit = ["mx.ped.layout", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedLayoutRegistroAudit(models.Model):
    _inherit = ["mx.ped.layout.registro", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedLayoutCampoAudit(models.Model):
    _inherit = ["mx.ped.layout.campo", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedFraccionAudit(models.Model):
    _inherit = ["mx.ped.fraccion", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedFraccionTasaAudit(models.Model):
    _inherit = ["mx.ped.fraccion.tasa", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedUmaAudit(models.Model):
    _inherit = ["mx.ped.um", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxNomAudit(models.Model):
    _inherit = ["mx.nom", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxRrnaAudit(models.Model):
    _inherit = ["mx.rrna", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPermisoAudit(models.Model):
    _inherit = ["mx.permiso", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxNicoAudit(models.Model):
    _inherit = ["mx.nico", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxFormaPagoAudit(models.Model):
    _inherit = ["mx.forma.pago", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedContribucionGlobalAudit(models.Model):
    _inherit = ["mx.ped.contribucion.global", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedPartidaContribucionAudit(models.Model):
    _inherit = ["mx.ped.partida.contribucion", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedTipoMovimientoAudit(models.Model):
    _inherit = ["mx.ped.tipo.movimiento", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedTipoContenedorAudit(models.Model):
    _inherit = ["mx.ped.tipo.contenedor", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedNumeroControlAudit(models.Model):
    _inherit = ["mx.ped.numero.control", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class MxPedNumeroControlLogAudit(models.Model):
    _inherit = ["mx.ped.numero.control.log", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaCatalogoTipoOperacionAudit(models.Model):
    _inherit = ["aduana.catalogo.tipo_operacion", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaCatalogoRegimenAudit(models.Model):
    _inherit = ["aduana.catalogo.regimen", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaCatalogoAduanaAudit(models.Model):
    _inherit = ["aduana.catalogo.aduana", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaCatalogoClavePedimentoAudit(models.Model):
    _inherit = ["aduana.catalogo.clave_pedimento", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaLayoutRegistroTipoAudit(models.Model):
    _inherit = ["aduana.layout_registro_tipo", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaLayoutRegistroCampoAudit(models.Model):
    _inherit = ["aduana.layout_registro_campo", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaPedimentoAudit(models.Model):
    _inherit = ["aduana.pedimento", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaPartidaAudit(models.Model):
    _inherit = ["aduana.partida", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaPartidaIdentificadorAudit(models.Model):
    _inherit = ["aduana.partida.identificador", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaPartidaContribucionAudit(models.Model):
    _inherit = ["aduana.partida.contribucion", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaFacturaAudit(models.Model):
    _inherit = ["aduana.factura", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaDocumentoAudit(models.Model):
    _inherit = ["aduana.documento", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaContenedorAudit(models.Model):
    _inherit = ["aduana.contenedor", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaContribucionGlobalAudit(models.Model):
    _inherit = ["aduana.contribucion.global", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]


class AduanaPedimentoRegistroTecnicoAudit(models.Model):
    _inherit = ["aduana.pedimento.registro_tecnico", "aduana.audit.mixin", "mail.thread", "mail.activity.mixin"]
