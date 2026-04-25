# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class MxPedValidacionLinea(models.TransientModel):
    _name = "mx.ped.validacion.linea"
    _description = "Línea de resultado de validación"
    _order = "severidad_order asc, categoria asc, sequence asc, id asc"

    wizard_id = fields.Many2one("mx.ped.validacion.wizard", required=True, ondelete="cascade")
    severidad = fields.Selection(
        [("error", "Error"), ("advertencia", "Advertencia"), ("info", "Info")],
        required=True,
        default="error",
    )
    severidad_order = fields.Integer(compute="_compute_severidad_order", store=True)
    categoria = fields.Selection(
        [
            ("general", "Datos generales"),
            ("partidas", "Partidas"),
            ("documentos", "Documentos"),
            ("contribuciones", "Contribuciones"),
            ("estructura", "Estructura de registros"),
            ("regulatorio", "NOM / Permisos / RRNA"),
            ("rectificacion", "Rectificación"),
        ],
        required=True,
        default="general",
    )
    sequence = fields.Integer(default=10)
    mensaje = fields.Char(string="Descripción", required=True)
    referencia = fields.Char(string="Referencia")

    @api.depends("severidad")
    def _compute_severidad_order(self):
        orden = {"error": 1, "advertencia": 2, "info": 3}
        for rec in self:
            rec.severidad_order = orden.get(rec.severidad, 9)


class MxPedValidacionWizard(models.TransientModel):
    _name = "mx.ped.validacion.wizard"
    _description = "Validación de operación aduanera antes de exportar"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, readonly=True)
    linea_ids = fields.One2many("mx.ped.validacion.linea", "wizard_id", string="Resultados")
    tiene_errores = fields.Boolean(compute="_compute_resumen")
    tiene_advertencias = fields.Boolean(compute="_compute_resumen")
    total_errores = fields.Integer(compute="_compute_resumen")
    total_advertencias = fields.Integer(compute="_compute_resumen")
    resumen = fields.Char(compute="_compute_resumen")

    @api.depends("linea_ids", "linea_ids.severidad")
    def _compute_resumen(self):
        for rec in self:
            errores = rec.linea_ids.filtered(lambda l: l.severidad == "error")
            advertencias = rec.linea_ids.filtered(lambda l: l.severidad == "advertencia")
            rec.tiene_errores = bool(errores)
            rec.tiene_advertencias = bool(advertencias)
            rec.total_errores = len(errores)
            rec.total_advertencias = len(advertencias)
            if errores:
                rec.resumen = _("%d error(es) — corrija antes de exportar.") % len(errores)
            elif advertencias:
                rec.resumen = _("%d advertencia(s) — puede exportar pero revise.") % len(advertencias)
            else:
                rec.resumen = _("Todo en orden. La operación está lista para exportar.")

    def action_exportar_txt(self):
        self.ensure_one()
        if self.tiene_errores:
            raise UserError(_("No se puede exportar: existen %d error(es) pendientes de corregir.") % self.total_errores)
        return self.operacion_id.action_export_txt()

    def action_exportar_proforma(self):
        self.ensure_one()
        if self.tiene_errores:
            raise UserError(_("No se puede generar proforma: existen %d error(es) pendientes de corregir.") % self.total_errores)
        return self.operacion_id.action_export_proforma()

    # ------------------------------------------------------------------
    # Lógica central de validación
    # ------------------------------------------------------------------

    def _add(self, lineas, severidad, categoria, mensaje, referencia=None, seq=10):
        lineas.append({
            "severidad": severidad,
            "categoria": categoria,
            "mensaje": mensaje,
            "referencia": referencia or "",
            "sequence": seq,
        })

    def _run_validacion(self):
        """Ejecuta todas las validaciones y devuelve lista de dicts."""
        self.ensure_one()
        op = self.operacion_id
        lineas = []
        e = lambda msg, ref=None, cat="general", seq=10: self._add(lineas, "error", cat, msg, ref, seq)
        w = lambda msg, ref=None, cat="general", seq=10: self._add(lineas, "advertencia", cat, msg, ref, seq)
        i = lambda msg, ref=None, cat="general", seq=10: self._add(lineas, "info", cat, msg, ref, seq)

        # Determina si es un pedimento de cancelación (eliminación o desistimiento).
        # Para estos tipos la estructura válida es 500/800/801 sin partidas.
        is_cancel_desist = op._get_tipo_movimiento_effective() in {"2", "3"}

        # ── 1. DATOS GENERALES ──────────────────────────────────────────
        if not op.layout_id:
            e(_("Falta seleccionar el Layout técnico."), cat="general", seq=10)
        if not op.clave_pedimento_id:
            e(_("Falta la Clave de Pedimento (ej. A1, V1)."), cat="general", seq=20)
        if not op.aduana_seccion_despacho_id:
            e(_("Falta la Aduana / Sección de despacho."), cat="general", seq=30)
        if not op.agente_aduanal_id:
            e(_("Falta el Agente Aduanal."), cat="general", seq=40)
        if not op.fecha_operacion:
            e(_("Falta la Fecha de operación."), cat="general", seq=50)
        if not op.incoterm and op.tipo_operacion == "importacion" and not is_cancel_desist:
            # Para eliminación/desistimiento no aplica incoterm: la mercancía
            # no llegó a entrar o salir del país.
            w(_("No se indicó el Incoterm. Recomendado para importaciones."), cat="general", seq=60)

        tipo_cambio = op.lead_id.x_tipo_cambio if op.lead_id else 0.0
        if not tipo_cambio or tipo_cambio <= 0:
            e(_("El Tipo de cambio en el Lead es 0 o no está definido. Los valores en MXN serán incorrectos."), cat="general", seq=70)
        elif tipo_cambio < 10 or tipo_cambio > 30:
            w(_("Tipo de cambio inusual: %.5f MXN/USD. Verifique que sea correcto.") % tipo_cambio, cat="general", seq=71)

        if op.es_rectificacion:
            if not (op.rect_pedimento_original or "").strip():
                e(_("Es rectificación pero falta el número de pedimento original."), cat="rectificacion", seq=10)
            if not op.rect_fecha_pago_original:
                e(_("Es rectificación pero falta la fecha de pago del pedimento original."), cat="rectificacion", seq=20)
            if not op.rect_aduana_original_id:
                w(_("Es rectificación: se recomienda indicar la aduana del pedimento original."), cat="rectificacion", seq=30)

        # ── 2. PARTIDAS ─────────────────────────────────────────────────
        partidas = op.partida_ids
        if not partidas and not is_cancel_desist:
            # Eliminación/desistimiento nunca tienen partidas — es lo correcto.
            e(_("La operación no tiene partidas capturadas."), cat="partidas", seq=10)
        if partidas and not is_cancel_desist:
            for p in partidas:
                ref = _("Partida %s") % (p.numero_partida or p.id)
                if not p.fraccion_id:
                    e(_("Sin fracción arancelaria."), ref=ref, cat="partidas", seq=20)
                if not p.quantity or p.quantity <= 0:
                    e(_("Cantidad debe ser mayor a cero."), ref=ref, cat="partidas", seq=30)
                if not p.value_usd or p.value_usd <= 0:
                    e(_("Valor USD debe ser mayor a cero."), ref=ref, cat="partidas", seq=40)
                if not p.factura_documento_id:
                    e(_("Sin factura / CFDI asignado."), ref=ref, cat="partidas", seq=50)
                if op.tipo_operacion == "importacion" and not p.pais_origen_id:
                    w(_("Sin país de origen declarado."), ref=ref, cat="partidas", seq=60)
                if not p.descripcion or len((p.descripcion or "").strip()) < 5:
                    w(_("Descripción de mercancía muy corta o vacía."), ref=ref, cat="partidas", seq=70)

                # Regulaciones desde fracción (mx.tigie.maestra es modelo plano;
                # no existen nom_default_ids/permiso_default_ids/rrna_default_ids).
                # Si la fracción tiene texto de regulaciones, advertimos cuando la
                # partida no tiene ningún NOM/permiso/RRNA capturado.
                if p.fraccion_id:
                    frac = p.fraccion_id
                    frac_code = frac.fraccion_8 or frac.llave_10 or ""
                    if (frac.regulaciones_economia or "").strip() and not p.nom_ids and not p.permiso_ids and not p.rrna_ids:
                        w(
                            _("La fracción %s tiene regulaciones de economía en TIGIE. Verifique si aplican NOM/permisos/RRNA en la partida.")
                            % frac_code,
                            ref=ref, cat="regulatorio", seq=10,
                        )

        # ── 3. DOCUMENTOS 505 ───────────────────────────────────────────
        docs_505 = op.documento_ids.filtered(
            lambda d: (d.tipo or "") in ("factura", "e_document") or (d.registro_codigo or "").strip() == "505"
        )
        if not docs_505 and partidas:
            e(_("No hay documentos tipo Factura / CFDI capturados (registro 505)."), cat="documentos", seq=10)
        else:
            for doc in docs_505:
                ref_doc = _("Doc. %s") % (doc.folio or doc.id)
                linked = partidas.filtered(lambda p: p.factura_documento_id == doc)
                if not linked:
                    w(_("Documento sin partidas asignadas — no se usará en el pedimento."), ref=ref_doc, cat="documentos", seq=20)
                    continue
                total_usd = sum(linked.mapped("value_usd"))
                doc_usd = doc.cfdi_valor_usd or 0.0
                if doc_usd > 0 and abs(total_usd - doc_usd) > 0.01:
                    e(
                        _("Valor USD de partidas (%.2f) no coincide con el 505 (%.2f).") % (total_usd, doc_usd),
                        ref=ref_doc, cat="documentos", seq=30,
                    )
                total_comercial = sum(linked.mapped("valor_comercial"))
                doc_moneda = doc.cfdi_valor_moneda or 0.0
                if doc_moneda > 0 and abs(total_comercial - doc_moneda) > 0.01:
                    w(
                        _("Valor comercial de partidas (%.2f) no coincide con valor en moneda del 505 (%.2f).") % (total_comercial, doc_moneda),
                        ref=ref_doc, cat="documentos", seq=40,
                    )

        # ── 4. CONTRIBUCIONES ────────────────────────────────────────────
        contribuciones = op.contribucion_global_ids
        if not contribuciones and partidas:
            w(_("No se han generado contribuciones (557/510). Use 'Generar contribuciones 557' primero."), cat="contribuciones", seq=10)
        else:
            sin_forma_pago = contribuciones.filtered(
                lambda l: (l.importe or 0.0) > 0 and not ((l.forma_pago_code or "").strip())
            )
            for line in sin_forma_pago:
                label = (
                    (line.contribucion_id.abbreviation or "").strip()
                    or (line.tipo_contribucion or "").strip()
                    or str(line.id)
                )
                e(
                    _("Falta forma de pago en el registro 510 para la contribución: %s") % label,
                    cat="contribuciones", seq=20,
                )

            # Verificar 508 si hay formas de pago 4 o 15
            declared_fp = op._get_declared_formas_pago_codes() if hasattr(op, "_get_declared_formas_pago_codes") else set()
            if ("4" in declared_fp or "15" in declared_fp) and not op.cuenta_aduanera_ids:
                e(
                    _("Formas de pago 4 o 15 declaradas pero no hay cuentas aduaneras (508)."),
                    cat="contribuciones", seq=30,
                )
            if "12" in declared_fp and not op.compensacion_line_ids:
                e(
                    _("Forma de pago 12 (Compensación) declarada pero no hay líneas de compensación (513)."),
                    cat="contribuciones", seq=40,
                )

            # Verificar 514 para formas de pago virtuales
            required_fp_virtual = {"2", "4", "7", "12", "15", "19", "22"}
            needed = declared_fp & required_fp_virtual
            docs_514 = op.documento_ids.filtered(lambda d: (d.registro_codigo or "").strip() == "514")
            if needed and not docs_514:
                e(
                    _("Formas de pago virtuales (%s) declaradas pero no hay documentos 514.") % ", ".join(sorted(needed)),
                    cat="contribuciones", seq=50,
                )
            else:
                for code in sorted(needed):
                    if not docs_514.filtered(lambda d: (d.forma_pago_code or "").strip() == code):
                        e(
                            _("Falta documento 514 para la forma de pago %s.") % code,
                            cat="contribuciones", seq=55,
                        )

        # ── 5. ESTRUCTURA DE REGISTROS ───────────────────────────────────
        if not op.estructura_regla_id and not op.rulepack_id:
            e(_("No hay estructura ni rulepack configurado — no se puede generar el archivo TXT."), cat="estructura", seq=10)
        elif not op.registro_ids:
            w(_("No hay registros técnicos generados. Use 'Preparar estructura' para generarlos."), cat="estructura", seq=20)
        elif is_cancel_desist:
            # Para eliminación/desistimiento solo se valida la estructura mínima 500/800/801.
            # La validación completa de rulepack (que exige 502, partidas, etc.) no aplica.
            try:
                op._validate_cancel_desist_structure()
            except (UserError, ValidationError) as exc:
                for linea_msg in str(exc.args[0]).split("\n"):
                    linea_msg = linea_msg.strip()
                    if linea_msg:
                        e(linea_msg, cat="estructura", seq=30)
            # Validar campos de registro 800/801 pero tratar acuse vacío como advertencia,
            # ya que el SAAI lo asigna después de presentar el TXT.
            try:
                op._validate_field_rules_on_registros()
            except (UserError, ValidationError) as exc:
                for linea_msg in str(exc.args[0]).split("\n"):
                    linea_msg = linea_msg.strip()
                    if not linea_msg:
                        continue
                    if "acuse" in linea_msg.lower():
                        w(
                            linea_msg + _(" — puede dejarse vacío ahora y llenarse después de que el SAAI valide el TXT."),
                            cat="estructura", seq=35,
                        )
                    else:
                        e(linea_msg, cat="estructura", seq=35)
        else:
            # Intentar la validación real de estructura y capturar sus errores
            try:
                op._validate_registros_vs_estructura()
            except (UserError, ValidationError) as exc:
                for linea_msg in str(exc.args[0]).split("\n"):
                    linea_msg = linea_msg.strip()
                    if linea_msg:
                        e(linea_msg, cat="estructura", seq=30)
            try:
                op._validate_field_rules_on_registros()
            except (UserError, ValidationError) as exc:
                for linea_msg in str(exc.args[0]).split("\n"):
                    linea_msg = linea_msg.strip()
                    if linea_msg:
                        e(linea_msg, cat="estructura", seq=35)

        # ── 6. CONSOLIDADO ───────────────────────────────────────────────
        if op.es_consolidado:
            # ── 6.0 Pago del pedimento principal ────────────────────────
            if not op.fecha_pago:
                e(
                    _("El pedimento consolidado no tiene fecha de pago registrada. "
                      "Las remesas solo pueden exportarse (TXT y AVC) una vez que "
                      "el pedimento principal esté pagado."),
                    cat="general", seq=79,
                )
            # ── 6.1 Remesas con COVE pero sin e-document ─────────────────
            remesas = op.remesa_ids.filtered("active") if op.remesa_ids else op.env["mx.ped.consolidado.remesa"]
            for rem in remesas.filtered(lambda r: r.cove_id and not r.acuse_valor):
                w(
                    _("La remesa tiene COVE ligado pero aún no tiene e-document de VUCEM. "
                      "Consulta el resultado del COVE antes de exportar."),
                    ref=_("Remesa %s") % (rem.folio or rem.id),
                    cat="general", seq=79,
                )
            if not remesas:
                w(_("Es operación consolidada pero no tiene remesas capturadas."), cat="partidas", seq=80)
            else:
                remesas_sin_partidas = remesas.filtered(lambda r: r.partida_count == 0)
                for r in remesas_sin_partidas:
                    w(
                        _("Remesa sin partidas asignadas."),
                        ref=_("Remesa %s") % (r.folio or r.id),
                        cat="partidas", seq=85,
                    )

                # ── 6a. Cobertura de partidas en remesas ─────────────────
                # Cada partida debe estar asignada a por lo menos una remesa.
                # La suma de cantidades y valores asignados no debe exceder el
                # total de la partida (los constraints del modelo ya lo impiden,
                # pero verificamos aqui para darlo como error de validacion).
                for partida in op.partida_ids:
                    ref_p = _("Partida %s") % (partida.numero_partida or partida.id)
                    asignaciones = partida.remesa_assignment_ids.filtered(
                        lambda a: a.remesa_id.active
                    )
                    if not asignaciones:
                        e(
                            _("La partida no está asignada a ninguna remesa activa."),
                            ref=ref_p, cat="partidas", seq=87,
                        )
                        continue

                    total_asignado_qty = sum(a.quantity or 0.0 for a in asignaciones)
                    total_asignado_usd = sum(a.value_usd or 0.0 for a in asignaciones)
                    partida_qty = partida.quantity or 0.0
                    partida_usd = partida.value_usd or 0.0

                    if partida_qty > 0 and abs(total_asignado_qty - partida_qty) > 0.001:
                        w(
                            _("Cantidad asignada a remesas (%.6f) difiere de la cantidad de la partida (%.6f).") % (
                                total_asignado_qty, partida_qty
                            ),
                            ref=ref_p, cat="partidas", seq=88,
                        )
                    if partida_usd > 0 and abs(total_asignado_usd - partida_usd) > 0.01:
                        w(
                            _("Valor USD asignado a remesas (%.2f) difiere del valor de la partida (%.2f).") % (
                                total_asignado_usd, partida_usd
                            ),
                            ref=ref_p, cat="partidas", seq=89,
                        )

                # ── 6b. Balance 557 por remesa vs 510 del pedimento ──────
                # Solo aplica en modo por_remesa. Verifica que la suma de los
                # importes de contribucion prorrateados en todas las remesas
                # cuadra con el total de 557 del pedimento, tipo por tipo.
                # Una diferencia indica edicion manual de montos.
                if op.modo_export_consolidado == "por_remesa":
                    # Acumular importes prorrateados por tipo de contribucion
                    suma_prorrateada: dict = {}   # key: tipo_str -> float
                    for remesa in remesas:
                        for rel in remesa.partida_rel_ids:
                            partida = rel.partida_id
                            if not partida:
                                continue
                            pv = partida.value_usd or 0.0
                            qv = partida.quantity or 0.0
                            rv = rel.value_usd or 0.0
                            rq = rel.quantity or 0.0
                            ratio = (rv / pv) if pv > 0 else ((rq / qv) if qv > 0 else 1.0)
                            for contrib in partida.contribucion_ids.filtered(
                                lambda c: c.operacion_id == op
                            ):
                                key = (
                                    (contrib.tipo_contribucion or "").strip()
                                    or str(contrib.contribucion_code or contrib.id)
                                )
                                suma_prorrateada[key] = (
                                    suma_prorrateada.get(key, 0.0)
                                    + round((contrib.importe or 0.0) * ratio, 2)
                                )

                    # Total real de 557 por tipo de contribucion
                    suma_real: dict = {}
                    for contrib in op.partida_contribucion_ids:
                        key = (
                            (contrib.tipo_contribucion or "").strip()
                            or str(contrib.contribucion_code or contrib.id)
                        )
                        suma_real[key] = suma_real.get(key, 0.0) + (contrib.importe or 0.0)

                    # Comparar tipo por tipo con tolerancia de 1 centavo por remesa
                    tolerancia = len(remesas) * 0.01
                    todos_los_tipos = set(suma_real) | set(suma_prorrateada)
                    for tipo in sorted(todos_los_tipos):
                        real = round(suma_real.get(tipo, 0.0), 2)
                        prorrateado = round(suma_prorrateada.get(tipo, 0.0), 2)
                        if abs(real - prorrateado) > tolerancia:
                            e(
                                _(
                                    "Contribución %(tipo)s: la suma prorrateada en remesas (%(pro)s) "
                                    "no cuadra con el total 557 del pedimento (%(real)s). "
                                    "Posible edición manual de importes."
                                ) % {
                                    "tipo": tipo,
                                    "pro": "%.2f" % prorrateado,
                                    "real": "%.2f" % real,
                                },
                                cat="contribuciones", seq=60,
                            )

        # Si no hay ningún problema, agregar línea de confirmación
        if not lineas:
            i(_("Validación completada sin problemas. La operación está lista para exportar."), cat="general", seq=1)

        return lineas

    @api.model
    def ejecutar_para_operacion(self, operacion):
        """Crea el wizard, ejecuta las validaciones y lo devuelve listo para mostrarse."""
        wizard = self.create({"operacion_id": operacion.id})
        lineas_data = wizard._run_validacion()
        lineas_vals = [dict(d, wizard_id=wizard.id) for d in lineas_data]
        self.env["mx.ped.validacion.linea"].create(lineas_vals)
        return wizard
