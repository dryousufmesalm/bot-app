/// <reference path="../pb_data/types.d.ts" />
migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("advanced_cycles_trader_cycles")

  // Add new fields for reversal trading
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "reversal_threshold_pips",
    "name": "reversal_threshold_pips",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": 10000,
      "noDecimal": false
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "highest_buy_price",
    "name": "highest_buy_price",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": false
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "lowest_sell_price",
    "name": "lowest_sell_price",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": false
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "reversal_count",
    "name": "reversal_count",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "closed_orders_pl",
    "name": "closed_orders_pl",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "open_orders_pl",
    "name": "open_orders_pl",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "total_cycle_pl",
    "name": "total_cycle_pl",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "last_reversal_time",
    "name": "last_reversal_time",
    "type": "date",
    "required": false,
    "unique": false,
    "options": {
      "min": "",
      "max": ""
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "reversal_history",
    "name": "reversal_history",
    "type": "json",
    "required": false,
    "unique": false,
    "options": {}
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("advanced_cycles_trader_cycles")

  // Remove fields added for reversal trading
  collection.schema.removeField("reversal_threshold_pips")
  collection.schema.removeField("highest_buy_price")
  collection.schema.removeField("lowest_sell_price")
  collection.schema.removeField("reversal_count")
  collection.schema.removeField("closed_orders_pl")
  collection.schema.removeField("open_orders_pl")
  collection.schema.removeField("total_cycle_pl")
  collection.schema.removeField("last_reversal_time")
  collection.schema.removeField("reversal_history")

  return dao.saveCollection(collection)
}) 