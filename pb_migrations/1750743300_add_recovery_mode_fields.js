// Migration: Add recovery mode fields for post-stop-loss recovery zone trading
// Date: 2024-12-28

migrate((db) => {
  // Add recovery mode fields to advanced_cycles_trader collection
  const collection = $app.dao().findCollectionByNameOrId("advanced_cycles_trader")
  
  // Recovery mode tracking
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "recovery_mode",
    "name": "in_recovery_mode",
    "type": "bool",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {}
  }))
  
  // Recovery zone base price (price where recovery zone was activated)
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "recovery_base",
    "name": "recovery_zone_base_price",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))
  
  // Initial stop loss price (price where initial order was stopped out)
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "initial_sl_price",
    "name": "initial_stop_loss_price", 
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))

  return $app.dao().saveCollection(collection)
}, (db) => {
  // Rollback: Remove recovery mode fields
  const collection = $app.dao().findCollectionByNameOrId("advanced_cycles_trader")
  
  // Remove the added fields
  collection.schema.removeField("recovery_mode")
  collection.schema.removeField("recovery_base")
  collection.schema.removeField("initial_sl_price")

  return $app.dao().saveCollection(collection)
}) 