from fastapi import APIRouter, Depends
from enum import Enum
from pydantic import BaseModel
from src.api import auth
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
    print(f"potions delievered: {potions_delivered} order_id: {order_id}")

    return "OK"

@router.post("/plan")
def get_bottle_plan():
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("SELECT num_green_ml FROM global_inventory WHERE id = 1")).fetchone()
        if result is not None:
            num_green_ml = result.num_green_ml 
        else:
            num_green_ml = []
        potions_created = 0
        remaining_ml = 0      
        if num_green_ml > 0:
            potions_created = num_green_ml // 100
            remaining_ml = num_green_ml % 100
            
            connection.execute(sqlalchemy.text(
                "UPDATE global_inventory SET num_green_ml = :remaining_ml, num_green_potions = num_green_potions + :potions_created WHERE id = 1"
            ), {"remaining_ml": remaining_ml, "potions_created": potions_created})
    return [
        {
            "potion_type": [0, 0, 100, 0],
            "quantity": potions_created,
        }
    ]

    # Each bottle has a quantity of what proportion of red, blue, and
    # green potion to add.
    # Expressed in integers from 1 to 100 that must sum up to 100.

    # Initial logic: bottle all barrels into red potions.

    return [
            {
                "potion_type": [0, 0, 100, 0],
                "quantity": potions_created,
            }
        ]

        
if __name__ == "__main__":
    print(get_bottle_plan())