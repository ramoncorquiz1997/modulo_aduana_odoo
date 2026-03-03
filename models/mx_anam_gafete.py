# -*- coding: utf-8 -*-
import base64
import io
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from urllib.parse import urlsplit, urlunsplit

import requests

from odoo import api, fields, models
from odoo.exceptions import ValidationError

try:
    from PIL import Image
    from pyzbar.pyzbar import decode as qr_decode
except Exception:  # pragma: no cover
    Image = None
    qr_decode = None

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception:  # pragma: no cover
    webdriver = None
    ChromeService = None
    ChromeOptions = None
    By = None
    WebDriverWait = None
    EC = None

_logger = logging.getLogger(__name__)


class MxAnamGafete(models.Model):
    _name = "mx.anam.gafete"
    _description = "Gafete ANAM de Chofer"
    _order = "write_date desc, id desc"

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    chofer_id = fields.Many2one(
        "res.partner",
        string="Chofer",
        domain="[('x_contact_role','=','chofer')]",
        ondelete="cascade",
        index=True,
    )
    transportista_id = fields.Many2one(
        "res.partner",
        string="Transportista",
        related="chofer_id.parent_id",
        store=True,
        readonly=True,
    )
    numero_gafete = fields.Char(string="Numero de gafete", index=True)
    qr_url = fields.Char(string="URL QR")
    estado = fields.Selection(
        [
            ("vigente", "Vigente"),
            ("vencido", "Vencido"),
            ("indeterminado", "Indeterminado"),
            ("error", "Error de validacion"),
        ],
        string="Estado",
        default="indeterminado",
        index=True,
        required=True,
    )
    vencido_desde = fields.Date(string="Vencido desde")
    validado_el = fields.Datetime(string="Validado el", readonly=True)
    mensaje_validacion = fields.Text(string="Mensaje de validacion", readonly=True)
    html_snippet = fields.Text(string="Fragmento HTML", readonly=True)

    _sql_constraints = [
        (
            "mx_anam_gafete_numero_uniq",
            "unique(numero_gafete)",
            "El numero de gafete ya existe.",
        )
    ]

    @api.depends("numero_gafete", "chofer_id")
    def _compute_name(self):
        for rec in self:
            chofer = rec.chofer_id.name or "Chofer"
            numero = rec.numero_gafete or "Sin numero"
            rec.name = f"{numero} - {chofer}"

    @api.constrains("chofer_id")
    def _check_chofer_parent(self):
        for rec in self:
            if rec.chofer_id and rec.chofer_id.x_contact_role != "chofer":
                raise ValidationError("El contacto seleccionado debe tener rol Chofer.")
            if rec.chofer_id and not rec.chofer_id.parent_id:
                raise ValidationError("El chofer debe estar ligado a un transportista (contacto padre).")

    @api.constrains("numero_gafete")
    def _check_numero_gafete_when_active(self):
        # Se permite activo sin numero cuando apenas se escanea QR.
        # El numero puede llenarse posteriormente al validar.
        return

    @api.constrains("active", "chofer_id")
    def _check_active_requires_chofer(self):
        for rec in self:
            if rec.active and not rec.chofer_id:
                raise ValidationError("Selecciona un chofer para activar el gafete.")

    @api.constrains("qr_url")
    def _check_qr_url(self):
        for rec in self:
            txt = (rec.qr_url or "").strip().lower()
            if txt and not (txt.startswith("http://") or txt.startswith("https://")):
                raise ValidationError("La URL del QR debe iniciar con http:// o https://")

    def _parse_estado_desde_html(self, html_text):
        txt = (html_text or "").strip()
        compact = " ".join(txt.split())
        low = compact.lower()

        m = re.search(r"vencido\s+desde\s+(\d{4}-\d{2}-\d{2})", low)
        if m:
            return {
                "estado": "vencido",
                "vencido_desde": fields.Date.to_date(m.group(1)),
                "mensaje": f"VENCIDO DESDE {m.group(1)}",
                "snippet": compact[:1500],
            }

        m = re.search(r"vencido\s+desde\s+(\d{2}/\d{2}/\d{4})", low)
        if m:
            raw = m.group(1)
            d, mth, y = raw.split("/")
            iso = f"{y}-{mth}-{d}"
            return {
                "estado": "vencido",
                "vencido_desde": fields.Date.to_date(iso),
                "mensaje": f"VENCIDO DESDE {iso}",
                "snippet": compact[:1500],
            }

        if "vigente" in low and "vencido" not in low:
            return {
                "estado": "vigente",
                "vencido_desde": False,
                "mensaje": "Gafete vigente",
                "snippet": compact[:1500],
            }

        return {
            "estado": "indeterminado",
            "vencido_desde": False,
            "mensaje": "No se pudo determinar vigencia con el contenido recibido.",
            "snippet": compact[:1500],
        }

    def _extract_folio_and_nombre(self, html_text):
        txt = html_text or ""
        folio = False
        nombre = False

        m = re.search(r'id=["\']folio["\'][^>]*>\s*([^<]+?)\s*<', txt, flags=re.IGNORECASE)
        if m:
            folio = (m.group(1) or "").strip()
        if not folio:
            m = re.search(r"folio[^0-9]*([0-9]{3,})", txt, flags=re.IGNORECASE)
            if m:
                folio = (m.group(1) or "").strip()

        m = re.search(r"nombre\s*:\s*([^<\r\n]{5,})", txt, flags=re.IGNORECASE)
        if m:
            nombre = " ".join((m.group(1) or "").strip().split())

        return folio or False, nombre or False

    def _looks_like_anam_shell_html(self, html_text):
        txt = (html_text or "").lower()
        if not txt:
            return False
        shell_signals = [
            "<!doctype html",
            "consultaqrgafete.anam.gob.mx",
            "js-1/lib/main.js",
        ]
        has_shell = sum(1 for s in shell_signals if s in txt) >= 2
        has_data = any(
            marker in txt
            for marker in [
                "vencido desde",
                "gafete vigente",
                "id=\"folio\"",
                "nombre:",
            ]
        )
        return has_shell and not has_data

    def _fetch_html_with_selenium(self, url):
        if not webdriver or not ChromeOptions:
            return False, "Selenium no disponible en servidor."
        driver = None
        tmp_profile_dir = None
        driver_log_file = None
        try:
            # Prefer explicit server-proven binaries.
            chrome_bin = (
                os.environ.get("ANAM_CHROME_BIN")
                or ("/usr/bin/google-chrome" if os.path.exists("/usr/bin/google-chrome") else None)
                or shutil.which("google-chrome")
                or shutil.which("google-chrome-stable")
                or shutil.which("chromium-browser")
                or shutil.which("chromium")
            )
            chromedriver_bin = (
                os.environ.get("ANAM_CHROMEDRIVER_BIN")
                or ("/usr/local/bin/chromedriver" if os.path.exists("/usr/local/bin/chromedriver") else None)
                or shutil.which("chromedriver")
            )
            if not chrome_bin:
                return False, "No se encontro binario de Chrome/Chromium en servidor."
            if not chromedriver_bin:
                return False, "No se encontro chromedriver en servidor."

            _logger.info("ANAM Selenium bins chrome=%s driver=%s", chrome_bin, chromedriver_bin)

            start_errors = []
            for headless_arg in ("--headless=new", "--headless"):
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
                if tmp_profile_dir and os.path.isdir(tmp_profile_dir):
                    shutil.rmtree(tmp_profile_dir, ignore_errors=True)
                tmp_profile_dir = tempfile.mkdtemp(prefix="odoo-chrome-profile-")
                driver_log_file = tempfile.NamedTemporaryFile(prefix="chromedriver-", suffix=".log", delete=False)
                driver_log_path = driver_log_file.name
                driver_log_file.close()

                try:
                    options = ChromeOptions()
                    options.binary_location = chrome_bin
                    options.add_argument(headless_arg)
                    options.add_argument("--disable-gpu")
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--disable-software-rasterizer")
                    options.add_argument("--disable-extensions")
                    options.add_argument("--disable-background-networking")
                    options.add_argument("--disable-crash-reporter")
                    options.add_argument("--no-first-run")
                    options.add_argument("--no-default-browser-check")
                    options.add_argument("--remote-debugging-pipe")
                    options.add_argument(f"--user-data-dir={tmp_profile_dir}")
                    options.add_argument("--window-size=1365,1024")
                    options.add_argument("--lang=es-MX")

                    service = ChromeService(executable_path=chromedriver_bin, log_output=driver_log_path)
                    driver = webdriver.Chrome(service=service, options=options)
                    driver.set_page_load_timeout(20)
                    driver.get(url)
                    break
                except Exception as err:
                    log_tail = ""
                    if os.path.exists(driver_log_path):
                        try:
                            with open(driver_log_path, "r", encoding="utf-8", errors="ignore") as fh:
                                lines = fh.readlines()[-20:]
                            log_tail = "".join(lines).strip()
                        except Exception:
                            log_tail = ""
                    start_errors.append(f"{headless_arg}: {err} | driver_log: {log_tail[:800]}")
                    if driver:
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = None

            if not driver:
                return False, "No se pudo iniciar ChromeDriver. " + " || ".join(start_errors)

            if WebDriverWait and EC and By:
                WebDriverWait(driver, 12).until(
                    lambda d: (
                        d.find_elements(By.CSS_SELECTOR, "div.alert-danger")
                        or d.find_elements(By.CSS_SELECTOR, "div.alert-success")
                        or d.find_elements(By.CSS_SELECTOR, "#folio")
                        or ("nombre:" in (d.page_source or "").lower())
                    )
                )
            html = driver.page_source or ""
            return html, False
        except Exception as err:
            return False, str(err)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            if tmp_profile_dir and os.path.isdir(tmp_profile_dir):
                shutil.rmtree(tmp_profile_dir, ignore_errors=True)
            if driver_log_file and os.path.exists(driver_log_file.name):
                try:
                    os.unlink(driver_log_file.name)
                except Exception:
                    pass

    @staticmethod
    def _normalize_person_name(name):
        txt = (name or "").strip().upper()
        if not txt:
            return ""
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        txt = re.sub(r"[^A-Z0-9 ]+", " ", txt)
        txt = " ".join(txt.split())
        return txt

    def _match_chofer_from_nombre(self, nombre):
        """Intenta resolver chofer por nombre sin arriesgar asignaciones ambiguas."""
        target = self._normalize_person_name(nombre)
        if not target:
            return False, "Nombre vacio"

        chofer_model = self.env["res.partner"]
        candidates = chofer_model.search([("x_contact_role", "=", "chofer"), ("active", "=", True)])
        if not candidates:
            return False, "No hay choferes activos en catalogo."

        exact = candidates.filtered(lambda c: self._normalize_person_name(c.name) == target)
        if len(exact) == 1:
            return exact, "Match exacto por nombre."
        if len(exact) > 1:
            return False, "Nombre ambiguo: existe mas de un chofer con el mismo nombre."

        partial = candidates.filtered(lambda c: target in self._normalize_person_name(c.name))
        if len(partial) == 1:
            return partial, "Match aproximado unico por nombre."
        if len(partial) > 1:
            return False, "Nombre ambiguo: hay multiples coincidencias aproximadas."

        return False, "No se encontro chofer por nombre."

    def action_validar_qr_url(self):
        for rec in self:
            url = (rec.qr_url or "").strip()
            if not url:
                raise ValidationError("Captura la URL QR antes de validar.")
            try:
                resp = None
                urls_to_try = [url]
                parts = urlsplit(url)
                if parts.scheme.lower() == "http":
                    https_url = urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
                    if https_url not in urls_to_try:
                        urls_to_try.append(https_url)

                for target_url in urls_to_try:
                    for _attempt in range(2):
                        try:
                            resp = requests.get(target_url, timeout=12, allow_redirects=True)
                            if resp.status_code < 500:
                                break
                        except requests.exceptions.Timeout:
                            continue
                        except requests.exceptions.RequestException:
                            continue
                    if resp is not None:
                        break

                if resp is None:
                    rec.write({
                        "estado": "error",
                        "validado_el": fields.Datetime.now(),
                        "mensaje_validacion": "No fue posible consultar el verificador ANAM (timeout/conexion).",
                        "html_snippet": False,
                    })
                    continue
                if resp.status_code >= 400:
                    rec.write({
                        "estado": "error",
                        "validado_el": fields.Datetime.now(),
                        "mensaje_validacion": f"HTTP {resp.status_code}: {resp.text[:500]}",
                        "html_snippet": False,
                    })
                    continue
                html_text = resp.text or ""
                selenium_used = False
                if self._looks_like_anam_shell_html(html_text):
                    rendered_html, s_err = rec._fetch_html_with_selenium(resp.url or url)
                    if rendered_html:
                        html_text = rendered_html
                        selenium_used = True
                    else:
                        rec.write({
                            "estado": "indeterminado",
                            "validado_el": fields.Datetime.now(),
                            "mensaje_validacion": f"Se recibio HTML base de ANAM y no se pudo renderizar con Selenium: {s_err}",
                            "html_snippet": (html_text or "")[:1500],
                        })
                        continue

                parsed = rec._parse_estado_desde_html(html_text)
                folio, nombre = rec._extract_folio_and_nombre(html_text)
                vals = {
                    "estado": parsed["estado"],
                    "vencido_desde": parsed["vencido_desde"],
                    "validado_el": fields.Datetime.now(),
                    "mensaje_validacion": parsed["mensaje"] + (" (render Selenium)" if selenium_used else ""),
                    "html_snippet": parsed["snippet"],
                }
                if folio:
                    vals["numero_gafete"] = folio
                if nombre and not rec.chofer_id:
                    chofer, reason = rec._match_chofer_from_nombre(nombre)
                    if chofer:
                        vals["chofer_id"] = chofer.id
                        vals["mensaje_validacion"] = f"{vals['mensaje_validacion']} | Chofer asignado: {chofer.name} ({reason})"
                    else:
                        vals["mensaje_validacion"] = f"{vals['mensaje_validacion']} | Nombre detectado: {nombre}. {reason} Selecciona chofer manualmente."
                rec.write(vals)
            except Exception as err:
                rec.write({
                    "estado": "error",
                    "validado_el": fields.Datetime.now(),
                    "mensaje_validacion": str(err),
                    "html_snippet": False,
                })
        return True

    def action_open_qr_camera(self):
        self.ensure_one()
        rec = self
        if not rec.id:
            if not rec.chofer_id or not rec.chofer_id.id:
                raise ValidationError("Guarda primero el chofer para poder escanear el gafete.")
            rec = self.create({
                "chofer_id": rec.chofer_id.id,
                "active": True,
            })
        return {
            "type": "ir.actions.client",
            "tag": "mx_qr_camera_scanner",
            "params": {
                "model": rec._name,
                "resId": rec.id,
                "res_id": rec.id,
                "title": "Escanear QR de Gafete ANAM",
            },
        }

    def action_set_qr_url_from_camera(self, qr_url, auto_validate=True):
        for rec in self:
            value = (qr_url or "").strip()
            if not value:
                raise ValidationError("No se recibió un valor de QR.")
            # Permite escanear primero sin bloquear por campos que aún no se conocen.
            rec.write({"qr_url": value, "active": True})
            if auto_validate:
                try:
                    with self.env.cr.savepoint():
                        rec.action_validar_qr_url()
                except Exception as err:
                    _logger.exception("Fallo validacion automatica de QR (gafete id=%s)", rec.id)
                    rec.write({
                        "estado": "error",
                        "validado_el": fields.Datetime.now(),
                        "mensaje_validacion": f"Error en validacion automatica: {err}",
                    })
            if rec.chofer_id and not rec.active:
                rec.active = True
        return True

    def action_decode_qr_image_from_camera(self, image_data):
        self.ensure_one()
        if not qr_decode or not Image:
            return False
        if not image_data:
            return False
        raw = image_data
        if "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            binary = base64.b64decode(raw)
            img = Image.open(io.BytesIO(binary))
            result = qr_decode(img)
            if not result:
                return False
            return result[0].data.decode("utf-8", errors="ignore")
        except Exception:
            return False

    def action_qr_decoder_status(self):
        self.ensure_one()
        missing = []
        if not Image:
            missing.append("Pillow")
        if not qr_decode:
            missing.append("pyzbar/zbar")
        if missing:
            return {
                "ready": False,
                "message": "Faltan dependencias de decoder servidor: %s." % ", ".join(missing),
            }
        return {
            "ready": True,
            "message": "Decoder servidor listo.",
        }

    @api.model
    def cron_validar_gafetes_anam(self, limit=300):
        gafetes = self.search(
            [("active", "=", True), ("qr_url", "!=", False)],
            order="write_date asc, id asc",
            limit=limit,
        )
        gafetes.action_validar_qr_url()
        return True

