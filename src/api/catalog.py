from fastapi import APIRouter
import sqlalchemy
from typing import List
from src import database as db

router = APIRouter()


@router.get("/catalog/", tags=["catalog"])
def get_catalog():
    """
    Fetch the catalog of available potions with their unique mixture, price, and inventory.
    Each unique potion combination has a single price.
    """
    catalog = []
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""
            SELECT sku, price, inventory, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """))
        
        for row in result:
            potion_type = [row.red_component, row.green_component, row.blue_component, row.dark_component]
            catalog.append({
                "sku": row.sku,
                "quantity": row.inventory,
                "price": row.price,
                "potion_type": potion_type 
            })

    return catalog if catalog else []