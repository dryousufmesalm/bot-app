// Migration: Create updates collection for auto-update system
// Date: 2024-12-28

migrate((db) => {
  const collection = new Collection({
    "id": "updates_collection",
    "created": "2024-12-28 10:00:00.000Z",
    "updated": "2024-12-28 10:00:00.000Z",
    "name": "updates",
    "type": "base",
    "system": false,
    "schema": [
      {
        "system": false,
        "id": "platform",
        "name": "platform",
        "type": "select",
        "required": true,
        "presentable": true,
        "unique": false,
        "options": {
          "maxSelect": 1,
          "values": [
            "bot",
            "flutter",
            "web",
            "desktop"
          ]
        }
      },
      {
        "system": false,
        "id": "version",
        "name": "version",
        "type": "text",
        "required": true,
        "presentable": true,
        "unique": false,
        "options": {
          "min": null,
          "max": null,
          "pattern": ""
        }
      },
      {
        "system": false,
        "id": "update_type",
        "name": "update_type",
        "type": "select",
        "required": true,
        "presentable": false,
        "unique": false,
        "options": {
          "maxSelect": 1,
          "values": [
            "full",
            "patch",
            "hotfix"
          ]
        }
      },
      {
        "system": false,
        "id": "download_url",
        "name": "download_url",
        "type": "url",
        "required": true,
        "presentable": false,
        "unique": false,
        "options": {
          "exceptDomains": null,
          "onlyDomains": null
        }
      },
      {
        "system": false,
        "id": "file_size",
        "name": "file_size",
        "type": "number",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "min": 0,
          "max": null,
          "noDecimal": true
        }
      },
      {
        "system": false,
        "id": "auto_update",
        "name": "auto_update",
        "type": "bool",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {}
      },
      {
        "system": false,
        "id": "restart_required",
        "name": "restart_required",
        "type": "bool",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {}
      },
      {
        "system": false,
        "id": "restart_delay",
        "name": "restart_delay",
        "type": "number",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "min": 0,
          "max": 300,
          "noDecimal": true
        }
      },
      {
        "system": false,
        "id": "release_notes",
        "name": "release_notes",
        "type": "editor",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "convertUrls": false
        }
      },
      {
        "system": false,
        "id": "is_stable",
        "name": "is_stable",
        "type": "bool",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {}
      },
      {
        "system": false,
        "id": "created_by",
        "name": "created_by",
        "type": "text",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null,
          "pattern": ""
        }
      },
      {
        "system": false,
        "id": "build_info",
        "name": "build_info",
        "type": "json",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "maxSize": 2000000
        }
      },
      {
        "system": false,
        "id": "checksum",
        "name": "checksum",
        "type": "text",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "min": null,
          "max": null,
          "pattern": ""
        }
      },
      {
        "system": false,
        "id": "dependencies",
        "name": "dependencies",
        "type": "json",
        "required": false,
        "presentable": false,
        "unique": false,
        "options": {
          "maxSize": 1000000
        }
      }
    ],
    "indexes": [
      "CREATE INDEX `idx_updates_platform` ON `updates` (`platform`)",
      "CREATE INDEX `idx_updates_version` ON `updates` (`version`)",
      "CREATE INDEX `idx_updates_created` ON `updates` (`created`)",
      "CREATE UNIQUE INDEX `idx_updates_platform_version` ON `updates` (`platform`, `version`)"
    ],
    "listRule": "@request.auth.id != \"\"",
    "viewRule": "@request.auth.id != \"\"",
    "createRule": "@request.auth.role = \"admin\"",
    "updateRule": "@request.auth.role = \"admin\"",
    "deleteRule": "@request.auth.role = \"admin\"",
    "options": {}
  })

  return Dao(db).saveCollection(collection)
}, (db) => {
  const dao = new Dao(db);
  const collection = dao.findCollectionByNameOrId("updates");

  return dao.deleteCollection(collection);
}) 