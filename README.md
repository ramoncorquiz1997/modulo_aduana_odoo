# modulo_aduana_odoo / mi_modulo

## Importacion de plantillas tecnicas (Odoo 18)

### 1) Actualizar modulo

Ejecuta upgrade para crear modelos `aduana.*` y cargar XML IDs base:

```bash
odoo -u mi_modulo -d <tu_db> --stop-after-init
```

### 2) Cargar tipos de registro (opcional por CSV)

Archivo ejemplo:

- `data/examples/layout_registro_tipo.csv`

Modelo destino:

- `aduana.layout_registro_tipo`

Notas:

- Ya existe una carga base por XML con XML IDs estables:
  - `modulo_aduana_odooaduana_layout_registro_tipo_500`
  - `modulo_aduana_odooaduana_layout_registro_tipo_501`
  - `modulo_aduana_odooaduana_layout_registro_tipo_510`
  - `modulo_aduana_odooaduana_layout_registro_tipo_700`
  - `modulo_aduana_odooaduana_layout_registro_tipo_801`

### 3) Cargar campos por registro (CSV tecnico)

Archivo ejemplo:

- `data/examples/layout_registro_campo.csv`

Modelo destino:

- `aduana.layout_registro_campo`

Clave para Many2one:

- La columna `registro_tipo_id/id` debe contener el XML ID completo del tipo de registro.
- Ejemplo: `modulo_aduana_odooaduana_layout_registro_tipo_500`

### 4) Flujo recomendado para catálogos

1. Importar catalogos de negocio (`aduana.catalogo.*`) por CSV.
2. Importar `layout_registro_campo.csv`.
3. Crear/editar pedimentos `aduana.pedimento`.
4. Capturar detalles en `partida/factura/documento`.

## Notas tecnicas

- El `crm.lead` solo conserva referencia ligera al pedimento:
  - `x_pedimento_id`
  - `x_pedimento_status`
  - `x_pedimento_last_error`
- Regla 1:1 garantizada por constraint SQL en `aduana.pedimento(lead_id)`.
- Existe esqueleto para mapeo TXT en `aduana.pedimento.action_prepare_txt_payload`.
