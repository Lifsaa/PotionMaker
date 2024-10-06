from fastapi import APIRouter
import sqlalchemy
from typing import List
from src import database as db

router = APIRouter()


@router.get("/catalog/", tags=["catalog"])
def get_catalog():
    """
    Each unique item combination must have only a single price.
    """
    with db.engine.begin() as connection:
        # Fetch potion quantities from global_inventory
        result = connection.execute(sqlalchemy.text("""
            SELECT num_green_potions, num_red_potions, num_dark_potions, num_blue_potions
            FROM global_inventory
        """)).fetchone()

    num_green_potions = result.num_green_potions
    num_red_potions = result.num_red_potions
    num_dark_potions = result.num_dark_potions
    num_blue_potions = result.num_blue_potions

    catalog = []
    # Add green potion to the catalog
    if num_green_potions > 0:
        catalog.append({
            "sku": "GREEN_POTION_0",
            "name": "green potion",
            "quantity": num_green_potions,
            "price": 25,
            "potion_type": [0, 100, 0, 0],  
        })

    if num_red_potions > 0:
        catalog.append({
            "sku": "RED_POTION_0",
            "name": "red potion",
            "quantity": num_red_potions,
            "price": 30,
            "potion_type": [100, 0, 0, 0],  #
        })
    if num_dark_potions > 0:
        catalog.append({
            "sku": "DARK_POTION_0",
            "name": "dark potion",
            "quantity": num_dark_potions,
            "price": 40,
            "potion_type": [0, 0, 100, 0],  
        })

    if num_blue_potions > 0:
        catalog.append({
            "sku": "BLUE_POTION_0",
            "name": "blue potion",
            "quantity": num_blue_potions,
            "price": 35,
            "potion_type": [0, 0, 0, 100], 
        })

    return catalog if catalog else []

