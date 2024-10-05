from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from src.api import auth
import sqlalchemy
from src import database as db
router = APIRouter(
    prefix="/barrels",
    tags=["barrels"],
    dependencies=[Depends(auth.get_api_key)],
)

class Barrel(BaseModel):
    sku: str

    ml_per_barrel: int
    potion_type: list[int]
    price: int

    quantity: int

@router.post("/deliver/{order_id}")
def post_deliver_barrels(barrels_delivered: list[Barrel], order_id: int):
    """ """
    print(f"barrels delievered: {barrels_delivered} order_id: {order_id}")
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("SELECT num_green_ml,gold FROM global_inventory")).fetchone()
        total_ml = res.num_green_ml
        total_gold = res.gold
        cost = 0
        for barrel in barrels_delivered:
            total_ml += barrel.ml_per_barrel
            cost = total_gold - barrel.price
        print(f"Now barrel is {barrel}")
        connection.execute(sqlalchemy.text(f"UPDATE global_inventory SET num_green_ml = {total_ml}, gold = {cost}"))
    return "OK"

# Gets called once a day
@router.post("/plan")
def get_wholesale_purchase_plan(wholesale_catalog: list[Barrel]):
    """ """
    print(wholesale_catalog)
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text(f"SELECT num_green_potions,gold FROM global_inventory")).fetchone()
        num_green_potions = res.num_green_potions
        gold = res.gold
    if num_green_potions < 10 and gold >50:    
        return {
         [
            {
                "sku": "SMALL_GREEN_BARREL",
                "quantity": num_green_potions
            }
        ]
        }
    return {}

   
