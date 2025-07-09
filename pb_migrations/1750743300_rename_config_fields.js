migrate(async (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("advanced_cycles_trader")

  // rename fields
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "reversal_threshold_pips",
    "name": "reversal_threshold_pips",
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
    "id": "cycle_interval",
    "name": "cycle_interval",
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
    "id": "initial_order_stop_loss",
    "name": "initial_order_stop_loss",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))

  // copy data from old fields to new fields
  const records = await dao.findRecordsByFilter('advanced_cycles_trader', '')
  for (const record of records) {
    record.set('reversal_threshold_pips', record.get('zone_threshold_pips'))
    record.set('cycle_interval', record.get('zone_range'))
    record.set('initial_order_stop_loss', record.get('batch_stop_loss'))
    await dao.saveRecord(record)
  }

  // remove old fields
  collection.schema.removeField('zone_threshold_pips')
  collection.schema.removeField('zone_range')
  collection.schema.removeField('batch_stop_loss')

  return dao.saveCollection(collection)
}, async (db) => {
  const dao = new Dao(db)
  const collection = dao.findCollectionByNameOrId("advanced_cycles_trader")

  // revert changes
  collection.schema.addField(new SchemaField({
    "system": false,
    "id": "zone_threshold_pips",
    "name": "zone_threshold_pips",
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
    "id": "zone_range",
    "name": "zone_range",
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
    "id": "batch_stop_loss",
    "name": "batch_stop_loss",
    "type": "number",
    "required": false,
    "unique": false,
    "options": {
      "min": null,
      "max": null,
      "noDecimal": false
    }
  }))

  // copy data back from new fields to old fields
  const records = await dao.findRecordsByFilter('advanced_cycles_trader', '')
  for (const record of records) {
    record.set('zone_threshold_pips', record.get('reversal_threshold_pips'))
    record.set('zone_range', record.get('cycle_interval'))
    record.set('batch_stop_loss', record.get('initial_order_stop_loss'))
    await dao.saveRecord(record)
  }

  // remove new fields
  collection.schema.removeField('reversal_threshold_pips')
  collection.schema.removeField('cycle_interval')
  collection.schema.removeField('initial_order_stop_loss')

  return dao.saveCollection(collection)
}) 