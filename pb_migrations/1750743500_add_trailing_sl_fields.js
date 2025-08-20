// Migration: Add trailing stop-loss and price tracking fields to MoveGuard cycles
// Date: 2024-12-25

migrate((db) => {
  const collection = db.getCollection('mg_cycles');

  // Add trailing stop-loss field
  collection.addField('trailing_stop_loss', {
    type: 'number',
    required: false,
    min: 0,
    max: 999999,
    decimal: 5,
    default: 0
  });

  // Add highest buy price field
  collection.addField('highest_buy_price', {
    type: 'number',
    required: false,
    min: 0,
    max: 999999,
    decimal: 5,
    default: 0
  });

  // Add lowest sell price field
  collection.addField('lowest_sell_price', {
    type: 'number',
    required: false,
    min: 0,
    max: 999999,
    decimal: 5,
    default: 0
  });

  console.log('✅ Added trailing stop-loss and price tracking fields to mg_cycles collection');
}, (db) => {
  const collection = db.getCollection('mg_cycles');

  // Remove the fields in reverse order
  collection.removeField('lowest_sell_price');
  collection.removeField('highest_buy_price');
  collection.removeField('trailing_stop_loss');

  console.log('✅ Removed trailing stop-loss and price tracking fields from mg_cycles collection');
});
