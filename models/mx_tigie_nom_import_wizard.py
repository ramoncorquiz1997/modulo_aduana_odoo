# -*- coding: utf-8 -*-
import base64
import csv
import io
import re
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Regex para extraer códigos NOM de texto libre
# Ejemplos: NOM-186-SSA1/SCFI-2013, NOM-013-SEMARNAT-2020, NOM-003-SCFI-2014
_NOM_REGEX = re.compile(r'NOM-[\w/]+-\d{4}', re.IGNORECASE)


class MxTigieNomImportWizard(models.TransientModel):
    _name = "mx.tigie.nom.import.wizard"
    _description = "Importar NOMs por fraccion arancelaria"

    archivo = fields.Binary(string="CSV de NOMs por fraccion", required=True)
    archivo_filename = fields.Char(string="Nombre del archivo")
    resultado = fields.Text(string="Resultado", readonly=True)
    estado = fields.Selection(
        [("pendiente", "Pendiente"), ("ok", "Completado"), ("error", "Error")],
        default="pendiente",
        readonly=True,
    )

    def action_open_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_importar(self):
        self.ensure_one()
        if not self.archivo:
            raise UserError(_("Debes subir un archivo CSV."))

        # Decodificar CSV
        try:
            contenido = base64.b64decode(self.archivo).decode("utf-8-sig")
        except Exception:
            try:
                contenido = base64.b64decode(self.archivo).decode("latin-1")
            except Exception as e:
                raise UserError(_("No se pudo leer el archivo: %s") % str(e))

        reader = csv.DictReader(io.StringIO(contenido))

        # Detectar columnas — soporta el formato del archivo oficial
        campos = reader.fieldnames or []
        col_fraccion = next(
            (c for c in campos if "fraccion" in c.lower() or "fracción" in c.lower()), None
        )
        col_nom = next(
            (c for c in campos if "nom" in c.lower() or "acotacion" in c.lower()), None
        )
        if not col_fraccion or not col_nom:
            raise UserError(
                _("El CSV debe tener columnas de fraccion y NOM. Columnas encontradas: %s")
                % ", ".join(campos)
            )

        TigieMaestra = self.env["mx.tigie.maestra"]
        MxNom = self.env["mx.nom"]

        stats = {
            "filas": 0,
            "fracciones_encontradas": 0,
            "fracciones_no_encontradas": 0,
            "noms_creadas": 0,
            "noms_existentes": 0,
            "links_creados": 0,
            "sin_nom": 0,
        }
        fracciones_no_encontradas = []

        for row in reader:
            stats["filas"] += 1
            fraccion_raw = (row.get(col_fraccion) or "").strip()
            nom_texto = (row.get(col_nom) or "").strip()

            if not fraccion_raw:
                continue

            # Convertir formato: "1806.10.01" → "18061001" (quitar puntos)
            fraccion_8 = fraccion_raw.replace(".", "")
            # Asegurarse de que sea exactamente 8 dígitos
            if len(fraccion_8) != 8 or not fraccion_8.isdigit():
                _logger.warning("Fraccion con formato inesperado: %s", fraccion_raw)
                continue

            # Extraer códigos NOM del texto con regex
            noms_encontrados = _NOM_REGEX.findall(nom_texto)
            if not noms_encontrados:
                stats["sin_nom"] += 1
                continue

            # Buscar todos los registros TIGIE con esta fraccion_8
            tigies = TigieMaestra.search([("fraccion_8", "=", fraccion_8)])
            if not tigies:
                stats["fracciones_no_encontradas"] += 1
                fracciones_no_encontradas.append(fraccion_8)
                continue

            stats["fracciones_encontradas"] += 1

            # Crear o encontrar cada NOM y vincular
            nom_records = self.env["mx.nom"]
            for nom_code in noms_encontrados:
                nom_code = nom_code.upper().strip()
                nom = MxNom.search([("code", "=", nom_code)], limit=1)
                if not nom:
                    nom = MxNom.create({
                        "code": nom_code,
                        "name": nom_code,
                    })
                    stats["noms_creadas"] += 1
                else:
                    stats["noms_existentes"] += 1
                nom_records |= nom

            # Vincular NOMs a todos los registros TIGIE de esa fraccion_8
            # (puede haber varios NICOs para la misma fraccion)
            for tigie in tigies:
                noms_nuevas = nom_records - tigie.nom_ids
                if noms_nuevas:
                    tigie.nom_ids = [(4, n.id) for n in noms_nuevas]
                    stats["links_creados"] += len(noms_nuevas)

        # Construir resumen
        lines = [
            "✓ Importación completada",
            f"  Filas procesadas:           {stats['filas']}",
            f"  Fracciones encontradas:     {stats['fracciones_encontradas']}",
            f"  Fracciones no encontradas:  {stats['fracciones_no_encontradas']}",
            f"  NOMs nuevas creadas:        {stats['noms_creadas']}",
            f"  NOMs ya existentes:         {stats['noms_existentes']}",
            f"  Vínculos TIGIE→NOM creados: {stats['links_creados']}",
            f"  Filas sin NOM (saltadas):   {stats['sin_nom']}",
        ]
        if fracciones_no_encontradas:
            lines.append("")
            lines.append("Fracciones del CSV no encontradas en TIGIE:")
            for f in fracciones_no_encontradas[:20]:
                lines.append(f"  - {f}")
            if len(fracciones_no_encontradas) > 20:
                lines.append(f"  ... y {len(fracciones_no_encontradas) - 20} más")

        self.write({
            "resultado": "\n".join(lines),
            "estado": "ok",
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
