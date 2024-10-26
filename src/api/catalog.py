from fastapi import APIRouter
import sqlalchemy
from typing import List
from src import database as db

router = APIRouter()


@router.get("/catalog/", tags=["catalog"])
def get_catalog():
    print("Starting to fetch potion catalog.")
    catalog = []
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""
            SELECT sku, price, inventory, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """))
        rows = result.fetchall()
        print(f"Fetched {len(rows)} potions from the database.")
        
        skipped = 0
        for row in rows:
            if row.inventory < 1:
                skipped += 1
                print(f"Skipping SKU: {row.sku} due to insufficient inventory.")
                continue
            potion_type = [row.red_component, row.green_component, row.blue_component, row.dark_component]
            catalog.append({
                "sku": row.sku,
                "quantity": row.inventory,
                "price": row.price,
                "potion_type": potion_type 
            })
        print(f"Added {len(catalog)} potions to the catalog. Skipped {skipped} potions with zero inventory.")
    
    print("Completed fetching potion catalog.")
    print(f"Catalog to return: {catalog}")
    return catalog if catalog else []