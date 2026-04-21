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
  - `modulo_aduana_odoo.aduana_layout_registro_tipo_500`
  - `modulo_aduana_odoo.aduana_layout_registro_tipo_501`
  - `modulo_aduana_odoo.aduana_layout_registro_tipo_510`
  - `modulo_aduana_odoo.aduana_layout_registro_tipo_700`
  - `modulo_aduana_odoo.aduana_layout_registro_tipo_801`

### 3) Cargar campos por registro (CSV tecnico)

Archivo ejemplo:

- `data/examples/layout_registro_campo.csv`

Modelo destino:

- `aduana.layout_registro_campo`

Clave para Many2one:

- La columna `registro_tipo_id/id` debe contener el XML ID completo del tipo de registro.
- Ejemplo: `modulo_aduana_odoo.aduana_layout_registro_tipo_500`

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


## CHANGE LOG 18.0.1.7.2
- El buscador de aduana-seccion ahora funciona en orden de busqueda, no ignora el texto agregado
- La lista de proveedores incluye los contactos que tienen el checkbox de proveedor, no solo exige crear uno nuevo en cada operación
- Se agrega check de proveedores en perfil de contacto
- La columna de diferencia en documentos no se pone en rojo ni la muestra si hay diferencia de moneda de cambio


## CHANGE LOG 18.0.1.7.3
- El numero interior no debe de ser requerido nunca, porque puede que la direccion no la tenga

## CHANGE LOG 18.0.1.7.4
-Manejo de identificadores a nivel partida