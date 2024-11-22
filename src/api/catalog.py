from fastapi import APIRouter
import sqlalchemy
from typing import List
from src import database as db

router = APIRouter()


@router.get("/catalog/", tags=["catalog"])
def get_catalog():
    print("Starting to fetch potion catalog.")
    catalog = []
    catalog_limit = 6  
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""
            SELECT id, sku, name, price, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
            ORDER BY price DESC
        """))
        rows = result.fetchall()
        print(f"Fetched {len(rows)} potions from the database.")
        
        for row in rows:
            if len(catalog) >= catalog_limit:
                print("Reached catalog SKU limit.")
                break  

            ledger_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(change), 0) as total_inventory
                FROM potion_inventory_ledger_entries
                WHERE potion_catalog_id = :catalog_id
            """), {"catalog_id": row.id})
            total_inventory = ledger_result.fetchone().total_inventory or 0

            if total_inventory < 1:
                print(f"Skipping SKU: {row.sku} due to insufficient inventory.")
                continue

            potion_type = [row.red_component, row.green_component, row.blue_component, row.dark_component]
            catalog.append({
                "sku": row.sku,
                "name": row.name,
                "quantity": total_inventory,
                "price": row.price,
                "potion_type": potion_type 
            })
            print(f"Added Potion to Catalog: SKU {row.sku}, Quantity {total_inventory}, Price {row.price}")

        print(f"Added {len(catalog)} potions to the catalog.")
    
    print("Completed fetching potion catalog.")
    return catalog if catalog else []