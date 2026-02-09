
{
    "name": "Aduana - Operaciones y Pedimentos",
    "version": "18.0.1.2.0",
    "category": "CRM",
    "summary": "Gestión de operaciones aduanales y pedimentos desde CRM",
    "depends": ["crm", "mail", "base", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/mx_ped_operacion_views.xml",
        "views/mx_ped_clave_views.xml",
        "views/mx_ped_layout_views.xml",
        "views/crm_lead_views.xml",
        
    ],
    "application": False,
    "installable": True,
}
