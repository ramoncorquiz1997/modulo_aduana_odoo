"""
Generador de Proforma de Pedimento Aduanal
Fiel al Formato Oficial — Anexo 22 RGCE / SAAI M3 v9.0
Fuente de referencia: Formato-Pedimento-Aduanal (SAT/SHCP)

Tipografía oficial:
  Encabezados de Bloque : Arial 9 Negrita  (Helvetica-Bold 9)  + sombreado 15%
  Nombre del Campo       : Arial 8 Negrita  (Helvetica-Bold 8)
  Información Declarada  : Arial 9          (Helvetica     9)
  Fechas                 : DD/MM/AAAA
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import io
from dataclasses import dataclass, field
from typing import List, Optional


# ══════════════════════════════════════════════
#  CONSTANTES DE DISEÑO OFICIAL
# ══════════════════════════════════════════════
PW, PH = letter          # 612 × 792 pts  (carta)
ML = 8 * mm              # margen izquierdo
MR = 8 * mm              # margen derecho
MT = 8 * mm              # margen superior
MB = 22 * mm             # margen inferior (pie de página)
CW = PW - ML - MR        # ancho de contenido

# Fuentes
FN  = "Helvetica"
FB  = "Helvetica-Bold"

# Tamaños oficiales
SZ_BLOCK_HDR  = 9   # encabezado de bloque negrita
SZ_FIELD_NAME = 7   # nombre del campo negrita  (usamos 7 para compactar)
SZ_DATA       = 8   # información declarada

# Colores
SHADE15  = colors.HexColor("#D9D9D9")   # sombreado ~15% gris
WHITE    = colors.white
BLACK    = colors.black
WM_COLOR = colors.HexColor("#E0E0E0")   # marca de agua

# Alturas de fila
ROW_H    = 9  * mm    # fila estándar de datos
HDR_H    = 6  * mm    # encabezado de bloque
SUBHDR_H = 5  * mm    # sub-encabezado de columnas en tabla


# ══════════════════════════════════════════════
#  ESTRUCTURAS DE DATOS
# ══════════════════════════════════════════════
@dataclass
class AgenteAduanal:
    nombre: str = ""
    rfc: str = ""
    curp: str = ""
    patente: str = ""
    mandatario_nombre: str = ""
    mandatario_rfc: str = ""
    mandatario_curp: str = ""
    num_serie_cert: str = ""
    firma_electronica: str = ""

@dataclass
class Contribucion:
    clave: str = ""
    tipo_tasa: str = ""
    tasa: str = ""
    importe: str = ""
    forma_pago: str = ""

@dataclass
class Identificador:
    clave: str = ""
    comp1: str = ""
    comp2: str = ""
    comp3: str = ""

@dataclass
class Guia:
    numero: str = ""
    identificador: str = ""

@dataclass
class Contenedor:
    numero: str = ""
    tipo: str = ""

@dataclass
class Partida:
    secuencia: str = ""
    fraccion: str = ""
    subdivision: str = ""
    vinculacion: str = ""
    met_valoracion: str = ""
    umc: str = ""
    cantidad_umc: str = ""
    umt: str = ""
    cantidad_umt: str = ""
    pais_venta: str = ""
    pais_origen: str = ""
    descripcion: str = ""
    val_aduana_usd: str = ""
    imp_precio_pag: str = ""
    precio_pagado: str = ""
    precio_unit: str = ""
    val_agregado: str = ""
    marca: str = ""
    modelo: str = ""
    codigo_producto: str = ""
    contribuciones: List[Contribucion] = field(default_factory=list)
    identificadores: List[Identificador] = field(default_factory=list)
    observaciones: str = ""

@dataclass
class Pedimento:
    # ── Encabezado principal (500) ──────────────
    num_pedimento: str = ""
    tipo_operacion: str = ""
    clave_pedimento: str = ""
    regimen: str = ""
    destino_origen: str = ""
    tipo_cambio: str = ""
    peso_bruto: str = ""
    aduana_es: str = ""
    medio_transporte_entrada: str = ""
    medio_transporte_arribo: str = ""
    medio_transporte_salida: str = ""
    valor_dolares: str = ""
    valor_aduana: str = ""
    precio_pagado_valor_comercial: str = ""
    # Importador
    rfc: str = ""
    nombre_razon_social: str = ""
    curp: str = ""
    domicilio: str = ""
    # Incrementables
    val_seguros: str = ""
    seguros: str = ""
    fletes: str = ""
    embalajes: str = ""
    otros_incrementables: str = ""
    # Códigos
    codigo_aceptacion: str = ""
    codigo_barras: str = ""
    clave_seccion_aduanera: str = ""
    marcas_numeros_bultos: str = ""
    # Fechas
    fecha_entrada: str = ""
    fecha_pago: str = ""
    fecha_presentacion: str = ""
    fecha_extraccion: str = ""
    # Tasas nivel pedimento
    tasas: List[Contribucion] = field(default_factory=list)
    # Cuadro de liquidación
    contribuciones_liq: List[Contribucion] = field(default_factory=list)
    total_efectivo: str = ""
    total_otros: str = ""
    total_total: str = ""
    # ── Proveedor/Comprador (505) ────────────────
    num_acuse_valor: str = ""
    vinculacion_505: str = ""
    incoterm: str = ""
    # ── Transporte ──────────────────────────────
    transporte_id: str = ""
    transporte_pais: str = ""
    transportista_nombre: str = ""
    transportista_rfc: str = ""
    transportista_curp: str = ""
    transportista_domicilio: str = ""
    candado1: str = ""
    candado2: str = ""
    # ── Guías ───────────────────────────────────
    guias: List[Guia] = field(default_factory=list)
    # ── Contenedores ────────────────────────────
    contenedores: List[Contenedor] = field(default_factory=list)
    # ── Identificadores nivel pedimento ─────────
    identificadores: List[Identificador] = field(default_factory=list)
    # ── Observaciones ───────────────────────────
    observaciones: str = ""
    # ── Partidas ────────────────────────────────
    partidas: List[Partida] = field(default_factory=list)
    # ── Agente aduanal ──────────────────────────
    agente: AgenteAduanal = field(default_factory=AgenteAduanal)


# ══════════════════════════════════════════════
#  PARSER TXT  (registros separados por |)
# ══════════════════════════════════════════════
def parse_txt(txt: str) -> Pedimento:
    ped = Pedimento()
    partida_actual: Optional[Partida] = None

    for linea in txt.strip().splitlines():
        linea = linea.strip()
        if not linea:
            continue
        c = linea.split("|")
        def g(i, d=""): return c[i].strip() if len(c) > i else d

        reg = g(0)

        if reg == "500":
            ped.num_pedimento               = g(1)
            ped.tipo_operacion              = g(2)
            ped.clave_pedimento             = g(3)
            ped.rfc                         = g(5)
            ped.curp                        = g(6)
            ped.nombre_razon_social         = g(7)
            ped.domicilio                   = g(9)
            ped.tipo_cambio                 = g(12)
            ped.total_efectivo              = g(13)
            ped.fletes                      = g(16)
            ped.seguros                     = g(17)
            ped.embalajes                   = g(18)
            ped.otros_incrementables        = g(19)
            ped.valor_aduana                = g(21)
            ped.precio_pagado_valor_comercial = g(22)
            ped.valor_dolares               = g(15)
            ped.fecha_entrada               = g(26)
            ped.fecha_pago                  = g(27)
            ped.aduana_es                   = g(28)
            ped.clave_seccion_aduanera      = g(30)
            ped.agente.patente              = g(31)
            ped.num_pedimento               = g(32) or g(1)
            ped.regimen                     = g(33)
            ped.destino_origen              = g(34)
            ped.tipo_cambio                 = g(35)
            ped.peso_bruto                  = g(36)

        elif reg == "502":
            contrib = Contribucion(g(2), g(3), g(4), g(5), g(6))
            ped.contribuciones_liq.append(contrib)
            ped.tasas.append(contrib)

        elif reg == "503":
            ped.identificadores.append(Identificador(g(2), g(3), g(4), g(5)))

        elif reg == "505":
            ped.fecha_entrada               = ped.fecha_entrada or g(2)
            ped.num_acuse_valor             = g(3)
            ped.incoterm                    = g(4)

        elif reg == "501":
            ped.guias.append(Guia(g(2), g(4)))

        elif reg == "510":
            if partida_actual:
                ped.partidas.append(partida_actual)
            partida_actual = Partida()
            partida_actual.secuencia        = g(2)
            partida_actual.fraccion         = g(3)
            partida_actual.subdivision      = g(4)
            partida_actual.vinculacion      = g(5)
            partida_actual.met_valoracion   = g(6)
            partida_actual.pais_origen      = g(7)
            partida_actual.descripcion      = g(8)
            partida_actual.cantidad_umc     = g(9)
            partida_actual.umc              = g(10)
            partida_actual.precio_unit      = g(11)
            partida_actual.cantidad_umt     = g(12)
            partida_actual.umt              = g(13)
            partida_actual.val_aduana_usd   = g(14)
            partida_actual.precio_pagado    = g(16)

        elif reg == "512" and partida_actual:
            partida_actual.contribuciones.append(
                Contribucion(g(2), g(3), g(4), g(5), g(6)))

        elif reg == "513" and partida_actual:
            partida_actual.identificadores.append(
                Identificador(g(2), g(3), g(4), g(5)))

    if partida_actual:
        ped.partidas.append(partida_actual)

    return ped


# ══════════════════════════════════════════════
#  BUILDER DE PDF — LAYOUT OFICIAL ANEXO 22
# ══════════════════════════════════════════════
class PedimentoPDF:
    def __init__(self, ped: Pedimento):
        self.ped     = ped
        self.buf     = io.BytesIO()
        self.c       = canvas.Canvas(self.buf, pagesize=letter)
        self.y       = 0.0
        self.pg      = 0          # número de página
        self.total_pages = "N"    # se actualiza al final (placeholder)

    # ─────────────────────────────────────────
    #  UTILIDADES BÁSICAS
    # ─────────────────────────────────────────
    def _new_page(self):
        if self.pg > 0:
            self._footer()
            self.c.showPage()
        self.pg += 1
        self.y = PH - MT
        self._watermark()

    def _watermark(self):
        self.c.saveState()
        self.c.setFont(FB, 72)
        self.c.setFillColor(WM_COLOR)
        self.c.setFillAlpha(0.18)
        self.c.translate(PW / 2, PH / 2)
        self.c.rotate(40)
        self.c.drawCentredString(0, 0, "PROFORMA")
        self.c.restoreState()

    def _need(self, h: float) -> bool:
        """True si hay espacio; False (y hace nueva página) si no hay."""
        if self.y - h < MB:
            self._new_page()
            return False
        return True

    def _fmt_fecha(self, f: str) -> str:
        f = (f or "").strip()
        if len(f) == 8 and f.isdigit():
            return f"{f[0:2]}/{f[2:4]}/{f[4:8]}"
        return f

    def _fmt_num(self, v: str) -> str:
        try:
            return f"{float(v):,.2f}"
        except Exception:
            return v or ""

    # ─────────────────────────────────────────
    #  PRIMITIVAS DE DIBUJO
    # ─────────────────────────────────────────
    def _rect(self, x, y, w, h, fill=None, stroke=True):
        self.c.saveState()
        if fill:
            self.c.setFillColor(fill)
        self.c.setStrokeColor(BLACK)
        self.c.setLineWidth(0.4)
        self.c.rect(x, y, w, h,
                    fill=1 if fill else 0,
                    stroke=1 if stroke else 0)
        self.c.restoreState()

    def _text(self, x, y, txt, size=SZ_DATA, bold=False, color=BLACK, align="left"):
        self.c.saveState()
        self.c.setFont(FB if bold else FN, size)
        self.c.setFillColor(color)
        s = str(txt) if txt else ""
        if align == "center":
            self.c.drawCentredString(x, y, s)
        elif align == "right":
            self.c.drawRightString(x, y, s)
        else:
            self.c.drawString(x, y, s)
        self.c.restoreState()

    def _block_header(self, label: str, x=None, w=None, h=HDR_H):
        """Encabezado de bloque: sombreado gris + texto Arial 9 Negrita."""
        x = x if x is not None else ML
        w = w if w is not None else CW
        top = self.y
        bot = top - h
        self._rect(x, bot, w, h, fill=SHADE15)
        self.c.saveState()
        self.c.setFont(FB, SZ_BLOCK_HDR)
        self.c.setFillColor(BLACK)
        self.c.drawString(x + 2, bot + (h - SZ_BLOCK_HDR) / 2, label)
        self.c.restoreState()
        self.y = bot

    def _field_cell(self, x, y, w, h, field_name: str, value: str, shade=False):
        """
        Celda con:
          - borde
          - nombre del campo en Arial 8 Bold arriba-izquierda
          - valor en Arial 9 abajo-izquierda
          - sombreado opcional
        """
        fill = SHADE15 if shade else None
        self._rect(x, y, w, h, fill=fill)
        # nombre del campo
        self.c.saveState()
        self.c.setFont(FB, SZ_FIELD_NAME)
        self.c.setFillColor(BLACK)
        self.c.drawString(x + 1.5, y + h - SZ_FIELD_NAME - 0.5, field_name)
        # valor declarado
        self.c.setFont(FN, SZ_DATA)
        # clip al ancho de la celda para no desbordarse
        self.c.clipPath(
            self.c.beginPath(), stroke=0, fill=0)
        self.c.drawString(x + 1.5, y + 1.5, str(value) if value else "")
        self.c.restoreState()

    def _row_of_cells(self, y, h, cells):
        """
        cells = list of (field_name, value, width_fraction)
        width_fraction: fracción de CW
        """
        x = ML
        for fname, fval, frac in cells:
            w = CW * frac
            self._field_cell(x, y, w, h, fname, fval)
            x += w

    # ─────────────────────────────────────────
    #  ENCABEZADO PÁGINA 1  (Anexo 22, pág 1)
    # ─────────────────────────────────────────
    def _header_pag1(self):
        """
        PEDIMENTO                                    Página 1 de N
        NUM. PEDIMENTO | T. OPER | CVE. PEDIMENTO | REGIMEN | CERTIFICACIONES
        DESTINO | TIPO CAMBIO | PESO BRUTO | ADUANA E/S               (col der)
        MEDIOS DE TRANSPORTE  | VALOR DOLARES:
        ENTRADA/SALIDA | ARRIBO | SALIDA | VALOR ADUANA:
                                          PRECIO PAGADO/VALOR COMERCIAL:
        """
        p = self.ped
        c = self.c
        TOP = self.y

        # ── Fila 0: título "PEDIMENTO" + página
        H0 = 5 * mm
        self._rect(ML, TOP - H0, CW * 0.75, H0, fill=SHADE15)
        self._text(ML + CW * 0.375, TOP - H0 + 1.5,
                   "PEDIMENTO", SZ_BLOCK_HDR, bold=True, align="center")
        self._rect(ML + CW * 0.75, TOP - H0, CW * 0.25, H0)
        self._text(ML + CW * 0.75 + 2, TOP - H0 + 1.5,
                   f"Página 1 de {self.total_pages}", SZ_DATA)
        self.y = TOP - H0

        # ── Fila 1: NUM.PEDIMENTO | T.OPER | CVE.PEDIMENTO | REGIMEN | CERTIF
        H1 = ROW_H
        y1 = self.y - H1
        cols1 = [
            ("NUM. PEDIMENTO",   p.num_pedimento,        0.22),
            ("T. OPER",          p.tipo_operacion,       0.10),
            ("CVE. PEDIMENTO",   p.clave_pedimento,      0.13),
            ("REGIMEN",          p.regimen,              0.10),
        ]
        x = ML
        for fn, fv, fr in cols1:
            w = CW * fr
            self._field_cell(x, y1, w, H1, fn, fv)
            x += w
        # Columna CERTIFICACIONES (ocupa el resto, doble alto → filas 1 y 2)
        certif_w = CW * (1 - 0.22 - 0.10 - 0.13 - 0.10)
        certif_h = H1 * 3   # abarca filas 1, 2 y 3 del encabezado
        self._field_cell(x, y1 - H1 * 2, certif_w, certif_h,
                         "CERTIFICACIONES", "")
        self.y = y1

        # ── Fila 2: DESTINO | TIPO CAMBIO | PESO BRUTO | ADUANA E/S
        H2 = ROW_H
        y2 = self.y - H2
        cw2 = 1 - certif_w / CW
        cols2 = [
            ("DESTINO",       p.destino_origen,   0.18),
            ("TIPO CAMBIO",   p.tipo_cambio,       0.18),
            ("PESO BRUTO",    p.peso_bruto,        0.18),
            ("ADUANA E/S",    p.aduana_es,         cw2 - 0.18 - 0.18 - 0.18),
        ]
        x = ML
        for fn, fv, fr in cols2:
            w = CW * fr
            self._field_cell(x, y2, w, H2, fn, fv)
            x += w
        self.y = y2

        # ── Fila 3: MEDIOS DE TRANSPORTE | VALOR DOLARES
        H3 = ROW_H
        y3 = self.y - H3
        w_transp = CW * 0.54
        # sub-celdas transporte
        self._rect(ML, y3, w_transp, H3)
        self._text(ML + 2, y3 + H3 - SZ_FIELD_NAME - 0.5,
                   "MEDIOS DE TRANSPORTE", SZ_FIELD_NAME, bold=True)
        sub_w = w_transp / 3
        for i, (lbl, val) in enumerate([
            ("ENTRADA/SALIDA", p.medio_transporte_entrada),
            ("ARRIBO",         p.medio_transporte_arribo),
            ("SALIDA",         p.medio_transporte_salida),
        ]):
            sx = ML + sub_w * i
            c.setFont(FB, 6)
            c.setFillColor(BLACK)
            c.drawString(sx + 2, y3 + 2, f"{lbl}: {val}")

        # valor dolares / aduana / precio pagado (columna derecha triple)
        vx = ML + w_transp
        vw = CW - w_transp - certif_w
        vh3 = H3 * 3
        self._rect(vx, y3 - H3 * 2, vw, vh3)
        for i, (lbl, val) in enumerate([
            ("VALOR DOLARES:",             self._fmt_num(p.valor_dolares)),
            ("VALOR ADUANA:",              self._fmt_num(p.valor_aduana)),
            ("PRECIO PAGADO/VALOR COMERCIAL:", self._fmt_num(p.precio_pagado_valor_comercial)),
        ]):
            ry = y3 - H3 * i
            c.setFont(FB, SZ_FIELD_NAME)
            c.setFillColor(BLACK)
            c.drawString(vx + 2, ry - SZ_FIELD_NAME - 0.5, lbl)
            c.setFont(FN, SZ_DATA)
            c.drawString(vx + 2, ry - SZ_FIELD_NAME * 2 - 1, val)

        self.y = y3 - H3 * 3   # bajar 3 filas

    # ─────────────────────────────────────────
    #  DATOS DEL IMPORTADOR/EXPORTADOR
    # ─────────────────────────────────────────
    def _bloque_importador(self):
        p = self.ped
        H = HDR_H
        self._need(HDR_H + ROW_H * 3)
        self._block_header("DATOS DEL IMPORTADOR /EXPORTADOR")

        # RFC | NOMBRE
        y = self.y - ROW_H
        self._field_cell(ML,            y, CW * 0.25, ROW_H, "RFC",  p.rfc)
        self._field_cell(ML + CW * 0.25, y, CW * 0.75, ROW_H,
                         "NOMBRE, DENOMINACION O RAZON SOCIAL",
                         p.nombre_razon_social)
        self.y = y

        # CURP
        y = self.y - ROW_H
        self._field_cell(ML, y, CW, ROW_H, "CURP", p.curp)
        self.y = y

        # DOMICILIO
        y = self.y - ROW_H
        self._field_cell(ML, y, CW, ROW_H, "DOMICILIO", p.domicilio)
        self.y = y

        # VAL.SEGUROS | SEGUROS | FLETES | EMBALAJES | OTROS INCREMENTABLES
        y = self.y - ROW_H
        self._row_of_cells(y, ROW_H, [
            ("VAL. SEGUROS",          p.val_seguros,         0.15),
            ("SEGUROS",               p.seguros,             0.15),
            ("FLETES",                p.fletes,              0.20),
            ("EMBALAJES",             p.embalajes,           0.20),
            ("OTROS INCREMENTABLES",  p.otros_incrementables,0.30),
        ])
        self.y = y

    # ─────────────────────────────────────────
    #  BLOQUE CÓDIGOS + MARCAS/BULTOS
    # ─────────────────────────────────────────
    def _bloque_codigos(self):
        p = self.ped
        self._need(ROW_H * 2)

        y = self.y - ROW_H
        self._row_of_cells(y, ROW_H, [
            ("CODIGO DE ACEPTACION",                p.codigo_aceptacion,     0.30),
            ("CODIGO DE BARRAS",                    p.codigo_barras,         0.40),
            ("CLAVE DE LA SECCION ADUANERA DE DESPACHO",
                                                    p.clave_seccion_aduanera,0.30),
        ])
        self.y = y

        y = self.y - ROW_H
        self._field_cell(ML, y, CW, ROW_H,
                         "MARCAS, NUMEROS Y TOTAL DE BULTOS",
                         p.marcas_numeros_bultos)
        self.y = y

    # ─────────────────────────────────────────
    #  FECHAS + TASAS NIVEL PEDIMENTO
    # ─────────────────────────────────────────
    def _bloque_fechas_tasas(self):
        p = self.ped
        self._need(HDR_H + ROW_H * 3)

        # Encabezados de sub-sección en la misma fila
        y0 = self.y - HDR_H
        # "FECHAS"
        self._rect(ML, y0, CW * 0.35, HDR_H, fill=SHADE15)
        self._text(ML + 2, y0 + 1, "FECHAS", SZ_BLOCK_HDR, bold=True)
        # "TASAS A NIVEL PEDIMENTO"
        self._rect(ML + CW * 0.35, y0, CW * 0.65, HDR_H, fill=SHADE15)
        self._text(ML + CW * 0.35 + 2, y0 + 1,
                   "TASAS A NIVEL PEDIMENTO", SZ_BLOCK_HDR, bold=True)
        self.y = y0

        # Sub-headers columnas de tasas
        y1 = self.y - HDR_H
        self._rect(ML, y1, CW * 0.35, HDR_H)   # espacio fechas
        tx = ML + CW * 0.35
        for lbl, fr in [("CONTRIB.", 0.20), ("CVE. T. TASA", 0.25), ("TASA", 0.20)]:
            w = CW * fr
            self._rect(tx, y1, w, HDR_H, fill=SHADE15)
            self._text(tx + 2, y1 + 1, lbl, SZ_FIELD_NAME, bold=True)
            tx += w
        self.y = y1

        # Filas de fechas vs tasas
        fechas = [
            ("Entrada/Presentación", self._fmt_fecha(p.fecha_entrada)),
            ("Pago",                 self._fmt_fecha(p.fecha_pago)),
        ]
        tasas_list = p.tasas[:max(len(fechas), len(p.tasas))]

        rows = max(len(fechas), len(tasas_list), 2)
        for i in range(rows):
            self._need(ROW_H)
            yr = self.y - ROW_H
            # fecha
            fl, fv = fechas[i] if i < len(fechas) else ("", "")
            self._field_cell(ML, yr, CW * 0.35, ROW_H, fl, fv)
            # tasa
            if i < len(tasas_list):
                t = tasas_list[i]
                tx = ML + CW * 0.35
                for val, fr in [(t.clave, 0.20), (t.tipo_tasa, 0.25), (t.tasa, 0.20)]:
                    w = CW * fr
                    self._field_cell(tx, yr, w, ROW_H, "", val)
                    tx += w
            else:
                self._rect(ML + CW * 0.35, yr, CW * 0.65, ROW_H)
            self.y = yr

    # ─────────────────────────────────────────
    #  CUADRO DE LIQUIDACIÓN
    # ─────────────────────────────────────────
    def _bloque_liquidacion(self):
        p = self.ped
        self._need(HDR_H + ROW_H * (len(p.contribuciones_liq) + 2))
        self._block_header("CUADRO DE LIQUIDACION")

        # Header de columnas
        yh = self.y - HDR_H
        cols_liq = [
            ("CONCEPTO", 0.18), ("F.P.", 0.07), ("IMPORTE", 0.15),
            ("CONCEPTO", 0.18), ("F.P.", 0.07), ("IMPORTE", 0.15),
            ("TOTALES",  0.20),
        ]
        tx = ML
        for lbl, fr in cols_liq:
            w = CW * fr
            self._rect(tx, yh, w, HDR_H, fill=SHADE15)
            self._text(tx + 2, yh + 1, lbl, SZ_FIELD_NAME, bold=True)
            tx += w
        self.y = yh

        # Filas de contribuciones (2 por renglón: izq y der)
        contribs = p.contribuciones_liq
        pares = []
        for i in range(0, max(len(contribs), 1), 2):
            izq = contribs[i] if i < len(contribs) else Contribucion()
            der = contribs[i + 1] if i + 1 < len(contribs) else Contribucion()
            pares.append((izq, der))

        for izq, der in pares:
            self._need(ROW_H)
            yr = self.y - ROW_H
            tx = ML
            # izquierda
            for val, fr in [(izq.clave, 0.18), (izq.forma_pago, 0.07),
                            (self._fmt_num(izq.importe), 0.15)]:
                w = CW * fr
                self._field_cell(tx, yr, w, ROW_H, "", val)
                tx += w
            # derecha
            for val, fr in [(der.clave, 0.18), (der.forma_pago, 0.07),
                            (self._fmt_num(der.importe), 0.15)]:
                w = CW * fr
                self._field_cell(tx, yr, w, ROW_H, "", val)
                tx += w
            # Totales (primera fila: EFECTIVO)
            w_tot = CW * 0.20
            self._rect(tx, yr, w_tot, ROW_H)
            self.y = yr

        # Filas EFECTIVO / OTROS / TOTAL
        for lbl, val in [
            ("EFECTIVO", p.total_efectivo),
            ("OTROS",    p.total_otros),
            ("TOTAL",    p.total_total),
        ]:
            self._need(ROW_H * 0.8)
            yr = self.y - ROW_H * 0.8
            # celdas izq/der vacías
            self._rect(ML, yr, CW * 0.80, ROW_H * 0.8)
            # celda totales
            tx = ML + CW * 0.80
            self._field_cell(tx, yr, CW * 0.10, ROW_H * 0.8, lbl, "")
            self._field_cell(tx + CW * 0.10, yr, CW * 0.10, ROW_H * 0.8,
                             "", self._fmt_num(val))
            self.y = yr

    # ─────────────────────────────────────────
    #  ENCABEZADO PÁGINA 2..N  (Anexo 22, pág 2)
    # ─────────────────────────────────────────
    def _header_pagN(self):
        p = self.ped
        H = HDR_H
        top = self.y

        # "ANEXO DEL PEDIMENTO   Página M de N"
        self._rect(ML, top - H, CW * 0.75, H, fill=SHADE15)
        self._text(ML + CW * 0.375, top - H + 1.5,
                   "ANEXO DEL PEDIMENTO", SZ_BLOCK_HDR, bold=True, align="center")
        self._rect(ML + CW * 0.75, top - H, CW * 0.25, H)
        self._text(ML + CW * 0.75 + 2, top - H + 1.5,
                   f"Página {self.pg} de {self.total_pages}", SZ_DATA)
        self.y = top - H

        # NUM.PEDIMENTO | TIPO OPER | CVE.PEDIM | RFC | CURP
        yr = self.y - ROW_H
        self._row_of_cells(yr, ROW_H, [
            ("NUM. PEDIMENTO", p.num_pedimento,     0.22),
            ("TIPO OPER",      p.tipo_operacion,    0.10),
            ("CVE. PEDIM",     p.clave_pedimento,   0.13),
            ("RFC",            p.rfc,               0.30),
            ("CURP",           p.curp,              0.25),
        ])
        self.y = yr

    # ─────────────────────────────────────────
    #  PIE DE PÁGINA — TODAS LAS HOJAS
    # ─────────────────────────────────────────
    def _footer(self):
        p = self.ped
        a = p.agente
        c = self.c

        fy = MB - 2    # base del pie

        # Borde superior del pie
        c.setStrokeColor(BLACK)
        c.setLineWidth(0.5)
        c.line(ML, fy + 14 * mm, ML + CW, fy + 14 * mm)

        # Encabezado pie
        c.setFont(FB, SZ_FIELD_NAME)
        c.setFillColor(BLACK)
        c.drawString(ML, fy + 12.5 * mm,
                     "AGENTE ADUANAL, APODERADO ADUANAL O DE ALMACEN")

        # Fila: NOMBRE | RFC | CURP | PATENTE
        fila1_y = fy + 9 * mm
        for x, w, lbl, val in [
            (ML,              CW * 0.40, "NOMBRE O RAZ. SOC", a.nombre),
            (ML + CW * 0.40,  CW * 0.20, "RFC",              a.rfc),
            (ML + CW * 0.60,  CW * 0.20, "CURP",             a.curp),
            (ML + CW * 0.80,  CW * 0.20, "PATENTE O AUTORIZACION", a.patente),
        ]:
            self._field_cell(x, fila1_y, w, 5 * mm, lbl, val)

        # Mandatario
        c.setFont(FB, SZ_FIELD_NAME)
        c.drawString(ML, fila1_y - 1.5 * mm, "MANDATARIO/PERSONA AUTORIZADA")
        fila2_y = fila1_y - 5 * mm
        for x, w, lbl, val in [
            (ML,             CW * 0.40, "NOMBRE", a.mandatario_nombre),
            (ML + CW * 0.40, CW * 0.20, "RFC",   a.mandatario_rfc),
            (ML + CW * 0.60, CW * 0.40, "CURP",  a.mandatario_curp),
        ]:
            self._field_cell(x, fila2_y, w, 5 * mm, lbl, val)

        # Leyenda protesta + FIEL
        leyenda_y = fila2_y - 0.5 * mm
        c.setFont(FN, 5.5)
        c.drawString(ML, leyenda_y,
            "DECLARO BAJO PROTESTA DE DECIR VERDAD, EN LOS TERMINOS DE LO DISPUESTO"
            " POR EL ARTICULO 81 DE LA LEY ADUANERA:")
        c.setFont(FB, SZ_FIELD_NAME)
        c.drawString(ML, leyenda_y - 3.5 * mm,
            f"NUMERO DE SERIE DEL CERTIFICADO: {a.num_serie_cert or ''}")
        c.drawString(ML, leyenda_y - 6.5 * mm,
            f"FIRMA ELECTRONICA AVANZADA: {a.firma_electronica or ''}")

    # ─────────────────────────────────────────
    #  BLOQUE PROVEEDOR/COMPRADOR  (505)
    # ─────────────────────────────────────────
    def _bloque_proveedor(self):
        p = self.ped
        self._need(HDR_H + ROW_H)
        self._block_header("DATOS DEL PROVEEDOR O COMPRADOR")

        yr = self.y - ROW_H
        self._row_of_cells(yr, ROW_H, [
            ("NUMERO DE ACUSE DE VALOR", p.num_acuse_valor,  0.50),
            ("VINCULACION",              p.vinculacion_505,  0.20),
            ("INCOTERM",                 p.incoterm,         0.30),
        ])
        self.y = yr

    # ─────────────────────────────────────────
    #  BLOQUE TRANSPORTE / CANDADOS / GUÍAS
    # ─────────────────────────────────────────
    def _bloque_transporte(self):
        p = self.ped
        self._need(HDR_H + ROW_H * 4)
        self._block_header("DATOS DEL TRANSPORTE Y TRANSPORTISTA")

        yr = self.y - ROW_H
        self._row_of_cells(yr, ROW_H, [
            ("TRANSPORTE IDENTIFICACION", p.transporte_id,   0.50),
            ("PAIS",                      p.transporte_pais, 0.50),
        ])
        self.y = yr

        yr = self.y - ROW_H
        self._row_of_cells(yr, ROW_H, [
            ("TRANSPORTISTA",  p.transportista_nombre,   0.25),
            ("RFC",            p.transportista_rfc,      0.25),
            ("CURP",           p.transportista_curp,     0.25),
            ("DOMICILIO/CIUDAD/ESTADO", p.transportista_domicilio, 0.25),
        ])
        self.y = yr

        # Candados
        self._need(HDR_H + ROW_H * 2)
        self._block_header("CANDADOS")
        yr = self.y - ROW_H
        self._field_cell(ML,            yr, CW * 0.33, ROW_H,
                         "NUMERO DE CANDADO", "")
        self._field_cell(ML + CW * 0.33, yr, CW * 0.33, ROW_H,
                         "1RA. REVISION", p.candado1)
        self._field_cell(ML + CW * 0.66, yr, CW * 0.34, ROW_H,
                         "2DA. REVISION", p.candado2)
        self.y = yr

    # ─────────────────────────────────────────
    #  GUÍAS / MANIFIESTOS / CONOCIMIENTOS
    # ─────────────────────────────────────────
    def _bloque_guias(self):
        p = self.ped
        if not p.guias:
            return
        self._need(HDR_H + ROW_H)
        self._block_header("GUIAS, MANIFIESTOS O CONOCIMIENTOS DE EMBARQUE")
        for g in p.guias:
            self._need(ROW_H)
            yr = self.y - ROW_H
            self._row_of_cells(yr, ROW_H, [
                ("NUMERO (GUIA/ORDEN EMBARQUE)/ID", g.numero, 0.70),
                ("ID",                              g.identificador, 0.30),
            ])
            self.y = yr

    # ─────────────────────────────────────────
    #  IDENTIFICADORES NIVEL PEDIMENTO
    # ─────────────────────────────────────────
    def _bloque_identificadores_ped(self):
        p = self.ped
        if not p.identificadores:
            return
        self._need(HDR_H + ROW_H)
        self._block_header("IDENTIFICADORES (NIVEL PEDIMENTO)")

        # sub-headers
        yh = self.y - HDR_H
        for lbl, fr in [("CLAVE/COMPL. IDENTIFICADOR", 0.25),
                        ("COMPLEMENTO 1", 0.25),
                        ("COMPLEMENTO 2", 0.25),
                        ("COMPLEMENTO 3", 0.25)]:
            w = CW * fr
            self._rect(ML + CW * [0, 0.25, 0.50, 0.75][[
                "CLAVE/COMPL. IDENTIFICADOR", "COMPLEMENTO 1",
                "COMPLEMENTO 2", "COMPLEMENTO 3"].index(lbl)],
                       yh, w, HDR_H, fill=SHADE15)
        # re-draw with correct x
        tx = ML
        for lbl, fr in [("CLAVE/COMPL. IDENTIFICADOR", 0.25),
                        ("COMPLEMENTO 1", 0.25),
                        ("COMPLEMENTO 2", 0.25),
                        ("COMPLEMENTO 3", 0.25)]:
            w = CW * fr
            self._rect(tx, yh, w, HDR_H, fill=SHADE15)
            self._text(tx + 2, yh + 1, lbl, SZ_FIELD_NAME, bold=True)
            tx += w
        self.y = yh

        for idf in p.identificadores:
            self._need(ROW_H)
            yr = self.y - ROW_H
            self._row_of_cells(yr, ROW_H, [
                ("", idf.clave, 0.25), ("", idf.comp1, 0.25),
                ("", idf.comp2, 0.25), ("", idf.comp3, 0.25),
            ])
            self.y = yr

    # ─────────────────────────────────────────
    #  OBSERVACIONES PEDIMENTO
    # ─────────────────────────────────────────
    def _bloque_observaciones(self):
        p = self.ped
        if not p.observaciones:
            return
        self._need(HDR_H + ROW_H)
        self._block_header("OBSERVACIONES")
        yr = self.y - ROW_H * 2
        self._field_cell(ML, yr, CW, ROW_H * 2, "", p.observaciones)
        self.y = yr

    # ─────────────────────────────────────────
    #  ENCABEZADO DE PARTIDAS (Anexo 22, pág 5)
    # ─────────────────────────────────────────
    def _bloque_encabezado_partidas(self):
        self._need(HDR_H)
        self._block_header("PARTIDAS")

        # Sub-header de columnas exacto según Anexo 22
        # FRACCION | SUBD | VINC | MET VAL | UMC | CANT UMC | UMT | CANT UMT |
        # P.V/C | P.O/D | SEC | DESCRIPCION | CON | TASA | T.T | F.P | IMPORTE
        # VAL ADU/USD | IMP. PRECIO PAG. | PRECIO UNIT. | VAL. AGREG.
        yh = self.y - HDR_H
        cols_part = [
            ("FRACCION",   0.09), ("SUBD.",  0.04), ("VINC.", 0.04),
            ("MET VAL",    0.05), ("UMC",    0.05), ("CANTIDAD UMC", 0.07),
            ("UMT",        0.05), ("CANTIDAD UMT", 0.07),
            ("P. V/C",     0.04), ("P. O/D", 0.04),
            ("SEC",        0.04), ("DESCRIPCION", 0.17),
            ("CON.",       0.04), ("TASA",   0.04), ("T.T.", 0.04),
            ("F.P.",       0.04), ("IMPORTE",0.09),
        ]
        tx = ML
        for lbl, fr in cols_part:
            w = CW * fr
            self._rect(tx, yh, w, HDR_H, fill=SHADE15)
            self._text(tx + 1, yh + 1, lbl, 5.5, bold=True)
            tx += w
        self.y = yh

        # Segunda sub-fila
        yh2 = self.y - HDR_H
        cols_part2 = [
            ("VAL ADU/USD", 0.15), ("IMP. PRECIO PAG.", 0.15),
            ("PRECIO UNIT.", 0.15), ("VAL. AGREG.", 0.15),
            ("MARCA", 0.13), ("MODELO", 0.13), ("CODIGO PRODUCTO", 0.14),
        ]
        tx = ML
        for lbl, fr in cols_part2:
            w = CW * fr
            self._rect(tx, yh2, w, HDR_H, fill=SHADE15)
            self._text(tx + 1, yh2 + 1, lbl, 5.5, bold=True)
            tx += w
        self.y = yh2

    # ─────────────────────────────────────────
    #  UNA PARTIDA COMPLETA
    # ─────────────────────────────────────────
    def _bloque_partida(self, part: Partida):
        # Fila 1 — fracción, cantidades, descripción, contribuciones
        H = ROW_H
        self._need(H * 2 + HDR_H)

        # Fila principal
        yr1 = self.y - H
        cols_p1 = [
            ("",  part.fraccion,        0.09),
            ("",  part.subdivision,     0.04),
            ("",  part.vinculacion,     0.04),
            ("",  part.met_valoracion,  0.05),
            ("",  part.umc,             0.05),
            ("",  self._fmt_num(part.cantidad_umc), 0.07),
            ("",  part.umt,             0.05),
            ("",  self._fmt_num(part.cantidad_umt), 0.07),
            ("",  part.pais_venta,      0.04),
            ("",  part.pais_origen,     0.04),
            ("",  part.secuencia,       0.04),
            ("",  part.descripcion,     0.17),
        ]
        # contribuciones en la misma fila (primera contrib)
        contrib0 = part.contribuciones[0] if part.contribuciones else Contribucion()
        cols_p1 += [
            ("", contrib0.clave,                    0.04),
            ("", contrib0.tasa,                     0.04),
            ("", contrib0.tipo_tasa,                0.04),
            ("", contrib0.forma_pago,               0.04),
            ("", self._fmt_num(contrib0.importe),   0.09),
        ]
        tx = ML
        for fn, fv, fr in cols_p1:
            w = CW * fr
            self._field_cell(tx, yr1, w, H, fn, fv)
            tx += w
        self.y = yr1

        # Fila 2 — valores
        yr2 = self.y - H
        self._row_of_cells(yr2, H, [
            ("VAL ADU/USD",       self._fmt_num(part.val_aduana_usd),  0.15),
            ("IMP. PRECIO PAG.",  self._fmt_num(part.imp_precio_pag),  0.15),
            ("PRECIO UNIT.",      self._fmt_num(part.precio_unit),     0.15),
            ("VAL. AGREG.",       self._fmt_num(part.val_agregado),    0.15),
            ("MARCA",             part.marca,                          0.13),
            ("MODELO",            part.modelo,                         0.13),
            ("CODIGO PRODUCTO",   part.codigo_producto,                0.14),
        ])
        self.y = yr2

        # Contribuciones adicionales (fila 2 en adelante)
        for contrib in part.contribuciones[1:]:
            self._need(H)
            yr = self.y - H * 0.7
            tx = ML + CW * (0.09+0.04+0.04+0.05+0.05+0.07+0.05+0.07+0.04+0.04+0.04+0.17)
            for val, fr in [
                (contrib.clave,                  0.04),
                (contrib.tasa,                   0.04),
                (contrib.tipo_tasa,              0.04),
                (contrib.forma_pago,             0.04),
                (self._fmt_num(contrib.importe), 0.09),
            ]:
                w = CW * fr
                self._field_cell(tx, yr, w, H * 0.7, "", val)
                tx += w
            self.y = yr

        # Identificadores de partida
        if part.identificadores:
            self._need(HDR_H + ROW_H * len(part.identificadores))
            yh = self.y - HDR_H
            self._rect(ML, yh, CW, HDR_H, fill=SHADE15)
            self._text(ML + 2, yh + 1,
                       "IDENTIFICADORES (NIVEL PARTIDA)", SZ_FIELD_NAME, bold=True)
            self.y = yh
            for idf in part.identificadores:
                yr = self.y - ROW_H * 0.8
                self._row_of_cells(yr, ROW_H * 0.8, [
                    ("IDENTIF.",      idf.clave, 0.15),
                    ("COMPLEMENTO 1", idf.comp1, 0.28),
                    ("COMPLEMENTO 2", idf.comp2, 0.28),
                    ("COMPLEMENTO 3", idf.comp3, 0.29),
                ])
                self.y = yr

        # Observaciones de partida
        if part.observaciones:
            self._need(HDR_H + ROW_H)
            yh = self.y - HDR_H
            self._rect(ML, yh, CW, HDR_H, fill=SHADE15)
            self._text(ML + 2, yh + 1,
                       "OBSERVACIONES A NIVEL PARTIDA", SZ_FIELD_NAME, bold=True)
            self.y = yh
            yr = self.y - ROW_H
            self._field_cell(ML, yr, CW, ROW_H, "", part.observaciones)
            self.y = yr

        self.y -= 1 * mm   # separador entre partidas

    # ─────────────────────────────────────────
    #  FIN DE PEDIMENTO
    # ─────────────────────────────────────────
    def _fin_pedimento(self):
        self._need(8 * mm)
        yr = self.y - 8 * mm
        txt = (f"**********FIN DE PEDIMENTO "
               f"******NUM. TOTAL DE PARTIDAS: {len(self.ped.partidas):03d} "
               f"******CLAVE PREVALIDADOR: **********")
        self._text(ML + CW / 2, yr + 2, txt, SZ_DATA, bold=True, align="center")
        self.c.setStrokeColor(BLACK)
        self.c.setLineWidth(0.8)
        self.c.line(ML, yr + 8 * mm, ML + CW, yr + 8 * mm)
        self.c.line(ML, yr,          ML + CW, yr)
        self.y = yr

    # ─────────────────────────────────────────
    #  ENSAMBLE COMPLETO
    # ─────────────────────────────────────────
    def build(self) -> bytes:
        # ── Página 1 ─────────────────────────────
        self._new_page()
        self._header_pag1()
        self.y -= 1 * mm
        self._bloque_importador()
        self._bloque_codigos()
        self._bloque_fechas_tasas()
        self._bloque_liquidacion()
        self.y -= 2 * mm

        # ── Bloques generales ─────────────────────
        # (si no caben en pág 1, _need abre pág 2 con encabezado secundario)
        def _ensure_secondary_header():
            """Llama al encabezado de pág 2..N cuando se abre una nueva página."""
            pass  # se maneja en _new_page via override abajo

        self._bloque_proveedor()
        self._bloque_transporte()
        self._bloque_guias()
        self._bloque_identificadores_ped()
        self._bloque_observaciones()

        # ── Partidas ─────────────────────────────
        if self.ped.partidas:
            self._need(HDR_H * 2 + ROW_H * 3)
            self._bloque_encabezado_partidas()
            for part in self.ped.partidas:
                # Si hay salto de página dentro de partidas, reimprimir encabezado
                if self.y - ROW_H * 3 < MB:
                    self._new_page()
                    self._header_pagN()
                    self._bloque_encabezado_partidas()
                self._bloque_partida(part)

        self._fin_pedimento()
        self._footer()
        self.c.save()
        return self.buf.getvalue()

    # Override _new_page para insertar encabezado secundario en pág 2+
    def _new_page(self):
        if self.pg > 0:
            self._footer()
            self.c.showPage()
        self.pg += 1
        self.y = PH - MT
        self._watermark()
        if self.pg > 1:
            self._header_pagN()


# ══════════════════════════════════════════════
#  API PÚBLICA
# ══════════════════════════════════════════════
def generar_proforma(txt_pedimento: str,
                     agente: dict = None,
                     output_path: str = None) -> bytes:
    """
    Genera la proforma PDF de un pedimento.

    Args:
        txt_pedimento : string TXT con campos separados por '|'
        agente        : dict opcional con datos del agente aduanal:
                        {'nombre', 'rfc', 'curp', 'patente',
                         'mandatario_nombre', 'mandatario_rfc', 'mandatario_curp',
                         'num_serie_cert', 'firma_electronica'}
        output_path   : si se indica, guarda el PDF en esa ruta

    Returns:
        bytes del PDF generado
    """
    ped = parse_txt(txt_pedimento)

    if agente:
        a = ped.agente
        a.nombre             = agente.get("nombre", "")
        a.rfc                = agente.get("rfc", "")
        a.curp               = agente.get("curp", "")
        a.patente            = agente.get("patente", "")
        a.mandatario_nombre  = agente.get("mandatario_nombre", "")
        a.mandatario_rfc     = agente.get("mandatario_rfc", "")
        a.mandatario_curp    = agente.get("mandatario_curp", "")
        a.num_serie_cert     = agente.get("num_serie_cert", "")
        a.firma_electronica  = agente.get("firma_electronica", "")

    builder = PedimentoPDF(ped)
    pdf_bytes = builder.build()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes


# ══════════════════════════════════════════════
#  DEMO
# ══════════════════════════════════════════════
DEMO_TXT = """500|0000001|IMP|A1|0000001|XAXX010101000||IMPORTADORA DEMO SA DE CV|CLIENTE DEMO SA|AV REFORMA 123 COL JUAREZ CDMX||USA|19.50|150000.00|5000.00|7500.00|800.00|200.00|100.00|0.00|8600.00|167700.00|150000.00|7692.31|01|FACTURA||15032026|16032026|240|240|1|3026|25 48 3026 0000001|IMD|MEX|19.50|1250.00|4
501|0000001|MAWB-1234567890||CAJ
502|0000001|DTA|AD|0.08|2500.00|1
502|0000001|IVA|AD|16.00|26832.00|1
503|0000001|MX|2||
505|0000001|15032026|UUID-CFDI-DEMO-1234-ABCDEF|FOB|USD|7500.00|7500.00|USA||12-3456789|SUPPLIER INC USA|123 MAIN ST||456|90210|LOS ANGELES CA
510|0000001|1|84713012|0|0|1|USA|COMPUTADORAS PERSONALES PORTATILES|10|PZA|750.00|10|KGM|7500.00|146250.00|7500.00|146250.00
512|0000001|DTA|AD|0.08|2500.00|1
512|0000001|IVA|AD|16.00|26832.00|1
513|0000001|MX|2||
510|0000001|2|85171200|0|0|1|CHN|TELEFONOS INTELIGENTES (SMARTPHONES)|5|PZA|200.00|5|KGM|1000.00|19500.00|1000.00|19500.00
512|0000001|DTA|AD|0.08|500.00|1
512|0000001|IVA|AD|16.00|3000.00|1
"""

DEMO_AGENTE = {
    "nombre":            "AGENCIA ADUANAL DEMO SA DE CV",
    "rfc":               "AAD900101AAA",
    "curp":              "",
    "patente":           "3026",
    "mandatario_nombre": "JUAN PEREZ LOPEZ",
    "mandatario_rfc":    "PELJ800101XXX",
    "mandatario_curp":   "PELJ800101HDFRZN00",
    "num_serie_cert":    "00001000000403432466",
    "firma_electronica": "ABCD1234EFGH5678...",
}

if __name__ == "__main__":
    out = "/mnt/user-data/outputs/proforma_pedimento_v2.pdf"
    generar_proforma(DEMO_TXT, DEMO_AGENTE, out)
    print(f"✅  Proforma v2 generada: {out}")
