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
        result = connection.execute(sqlalchemy.text("SELECT num_green_potions FROM global_inventory WHERE id = 1")).fetchone()
        if result is not None:
            num_green_potions = result.num_green_potions
        else: num_green_potions = 0
    if num_green_potions >0 :
        return [
                {
                    "sku": "GREEN_POTION_0",
                    "name": "green potion",
                    "quantity": num_green_potions,
                    "price": 10,
                    "potion_type": [0, 100, 0, 0],
                }
            ]
    else: return []


