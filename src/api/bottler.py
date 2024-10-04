from fastapi import APIRouter, Depends
from enum import Enum
from pydantic import BaseModel
from src.api import auth
from typing import List
import sqlalchemy
from src import database as db

router = APIRouter(
    prefix="/bottler",
    tags=["bottler"],
    dependencies=[Depends(auth.get_api_key)],
)

class PotionInventory(BaseModel):
    potion_type: list[int]
    quantity: int

@router.post("/deliver/{order_id}")
def post_deliver_bottles(potions_delivered: list[PotionInventory], order_id: int):
    """ """
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    totalPotionsSQL ="SELECT num_green_potions FROM global_inventory"
    with db.engine.begin() as connection:
        total_potionsgrabber = connection.execute(sqlalchemy.text(totalPotionsSQL)).fetchone()
        total_mlgrabber = connection.execute(sqlalchemy.text("SELECT num_green_ml FROM global_inventory")).fetchone()

    total_potions = total_potionsgrabber.num_green_potions
    total_ml = total_mlgrabber.num_green_ml
    for potion in potions_delivered:
        total_potions += potion.delivered
        total_ml -= (100 * potion.quantity)

    with db.engine.begin() as connection:
        connection.execute(sqlalchemy.text(f"UPDATE global_inventory SET num_green_potions = {total_potions}"))
        connection.execute(sqlalchemy.text(f"UPDATE global_inventory SET num_green_ml = {total_ml}"))

    return "OK"

@router.post("/plan")
def get_bottle_plan():
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("SELECT num_green_ml FROM global_inventory")).fetchone()
    if result is None:
        num_green_ml = 0
    else:
        num_green_ml = result.num_green_ml
    potions_created = 0
    if num_green_ml > 0:
        potions_created = num_green_ml // 100        
    if potions_created > 0:
        return [
            {
                "potion_type": [0, 100, 0, 0],
                "quantity": potions_created,
            }
        ]
    return []

    # Each bottle has a quantity of what proportion of red, blue, and
    # green potion to add.
    # Expressed in integers from 1 to 100 that must sum up to 100.

    # Initial logic: bottle all barrels into red potions.
        
if __name__ == "__main__":
    print(get_bottle_plan())