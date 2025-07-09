/// <reference path="../pb_data/types.d.ts" />

migrate((db) => {
    const dao = new Dao(db);
    
    // Add new order tracking fields to global_loss_tracker table
    const collection = dao.findCollectionByNameOrId("global_loss_tracker");
    
    if (collection) {
        collection.schema.addField(new SchemaField({
            "name": "last_order_ticket",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": null,
                "max": null
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "last_order_type",
            "type": "text",
            "required": false,
            "unique": false,
            "options": {
                "min": null,
                "max": 50
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "last_order_price",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": null,
                "max": null
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "last_order_lot_size",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": null,
                "max": null
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "last_order_source",
            "type": "text",
            "required": false,
            "unique": false,
            "options": {
                "min": null,
                "max": 100
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "total_orders_placed",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": 0,
                "max": null
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "initial_orders_placed",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": 0,
                "max": null
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "interval_orders_placed",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": 0,
                "max": null
            }
        }));
        
        collection.schema.addField(new SchemaField({
            "name": "reversal_orders_placed",
            "type": "number",
            "required": false,
            "unique": false,
            "options": {
                "min": 0,
                "max": null
            }
        }));
        
        dao.saveCollection(collection);
        console.log("Added order tracking fields to global_loss_tracker table");
    } else {
        console.log("Collection global_loss_tracker not found");
    }
}, (db) => {
    const dao = new Dao(db);
    
    // Revert changes
    const collection = dao.findCollectionByNameOrId("global_loss_tracker");
    
    if (collection) {
        collection.schema.removeField("last_order_ticket");
        collection.schema.removeField("last_order_type");
        collection.schema.removeField("last_order_price");
        collection.schema.removeField("last_order_lot_size");
        collection.schema.removeField("last_order_source");
        collection.schema.removeField("total_orders_placed");
        collection.schema.removeField("initial_orders_placed");
        collection.schema.removeField("interval_orders_placed");
        collection.schema.removeField("reversal_orders_placed");
        
        dao.saveCollection(collection);
        console.log("Removed order tracking fields from global_loss_tracker table");
    } else {
        console.log("Collection global_loss_tracker not found");
    }
}); 