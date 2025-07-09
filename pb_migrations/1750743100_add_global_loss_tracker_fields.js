/// <reference path="../pb_data/types.d.ts" />

migrate((db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("global_loss_tracker")

  // Identification fields
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "bot_id",
    "name": "bot_id",
    "type": "text",
    "required": true,
    "presentable": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "account_id",
    "name": "account_id",
    "type": "text",
    "required": true,
    "presentable": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "symbol",
    "name": "symbol",
    "type": "text",
    "required": true,
    "presentable": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  // Loss tracking fields
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "total_accumulated_losses",
    "name": "total_accumulated_losses",
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

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "active_cycles_count",
    "name": "active_cycles_count",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "closed_cycles_count",
    "name": "closed_cycles_count",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  // Loss breakdown
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "initial_order_losses",
    "name": "initial_order_losses",
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

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "threshold_order_losses",
    "name": "threshold_order_losses",
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

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "recovery_order_losses",
    "name": "recovery_order_losses",
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

  // Cycle management
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "last_cycle_id",
    "name": "last_cycle_id",
    "type": "text",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "pattern": ""
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "last_loss_amount",
    "name": "last_loss_amount",
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

  // ACT specific fields
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "zone_based_losses",
    "name": "zone_based_losses",
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

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "direction_switch_count",
    "name": "direction_switch_count",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "batch_stop_loss_triggers",
    "name": "batch_stop_loss_triggers",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  // Risk management
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "max_single_cycle_loss",
    "name": "max_single_cycle_loss",
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

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "average_cycle_loss",
    "name": "average_cycle_loss",
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

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "loss_trend",
    "name": "loss_trend",
    "type": "select",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "maxSelect": 1,
      "values": ["increasing", "decreasing", "stable"]
    }
  }))

  // Performance tracking
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "total_cycles_processed",
    "name": "total_cycles_processed",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "profitable_cycles",
    "name": "profitable_cycles",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "loss_making_cycles",
    "name": "loss_making_cycles",
    "type": "number",
    "required": false,
    "presentable": false,
    "unique": false,
    "options": {
      "min": 0,
      "max": null,
      "noDecimal": true
    }
  }))

  return dao.saveCollection(collection)
}, (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("global_loss_tracker")

  // Remove all the fields we added (for rollback)
  collection.schema.removeField("bot_id")
  collection.schema.removeField("account_id")
  collection.schema.removeField("symbol")
  collection.schema.removeField("total_accumulated_losses")
  collection.schema.removeField("active_cycles_count")
  collection.schema.removeField("closed_cycles_count")
  collection.schema.removeField("initial_order_losses")
  collection.schema.removeField("threshold_order_losses")
  collection.schema.removeField("recovery_order_losses")
  collection.schema.removeField("last_cycle_id")
  collection.schema.removeField("last_loss_amount")
  collection.schema.removeField("zone_based_losses")
  collection.schema.removeField("direction_switch_count")
  collection.schema.removeField("batch_stop_loss_triggers")
  collection.schema.removeField("max_single_cycle_loss")
  collection.schema.removeField("average_cycle_loss")
  collection.schema.removeField("loss_trend")
  collection.schema.removeField("total_cycles_processed")
  collection.schema.removeField("profitable_cycles")
  collection.schema.removeField("loss_making_cycles")

  return dao.saveCollection(collection)
}) 