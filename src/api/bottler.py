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
    """Update the potion inventory based on delivered potions"""
    print(f"potions delivered: {potions_delivered} order_id: {order_id}")

    with db.engine.begin() as connection:
        potion_data = connection.execute(sqlalchemy.text("""
            SELECT num_green_potions, num_red_potions, num_blue_potions,
                   num_green_ml, num_red_ml, num_blue_ml
            FROM global_inventory
        """)).fetchone()


        total_green_potions = potion_data.num_green_potions
        total_red_potions = potion_data.num_red_potions
        total_blue_potions = potion_data.num_blue_potions
        total_green_ml = potion_data.num_green_ml
        total_red_ml = potion_data.num_red_ml
        total_blue_ml = potion_data.num_blue_ml

        for potion in potions_delivered:
            if potion.potion_type == [0, 100, 0, 0]:
                total_green_potions += potion.quantity
                total_green_ml -= (100 * potion.quantity)
            elif potion.potion_type == [100, 0, 0, 0]:
                total_red_potions += potion.quantity
                total_red_ml -= (100 * potion.quantity)
            elif potion.potion_type == [0, 0, 100, 0]:
                total_blue_potions += potion.quantity
                total_blue_ml -= (100 * potion.quantity)
      
        connection.execute(sqlalchemy.text(f"""
            UPDATE global_inventory 
            SET num_green_potions = {total_green_potions}, 
                num_red_potions = {total_red_potions}, 
                num_blue_potions = {total_blue_potions},
                num_green_ml = {total_green_ml}, 
                num_red_ml = {total_red_ml}, 
                num_blue_ml = {total_blue_ml}
        """))

    return "OK"

@router.post("/plan")
def get_bottle_plan():
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""
            SELECT num_green_ml, num_red_ml, num_blue_ml
            FROM global_inventory
        """)).fetchone()

    num_green_ml = result.num_green_ml
    num_red_ml = result.num_red_ml
    num_blue_ml = result.num_blue_ml

    potions_created_green = num_green_ml // 100 if num_green_ml > 0 else 0
    potions_created_red = num_red_ml // 100 if num_red_ml > 0 else 0
    potions_created_blue = num_blue_ml // 100 if num_blue_ml > 0 else 0

    potion_plan = []
    if potions_created_green > 0:
        potion_plan.append({
            "potion_type": [0, 100, 0, 0],
            "quantity": potions_created_green,
        })
    if potions_created_red > 0:
        potion_plan.append({
            "potion_type": [100, 0, 0, 0],
            "quantity": potions_created_red,
        })
 
    if potions_created_blue > 0:
        potion_plan.append({
            "potion_type": [0, 0, 0, 100],
            "quantity": potions_created_blue,
        })

    return potion_plan if potion_plan else []

if __name__ == "__main__":
    print(get_bottle_plan())
