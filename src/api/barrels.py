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
    potion_type: List[int]
    price: int
    quantity: int

@router.post("/deliver/{order_id}")
def post_deliver_barrels(barrels_delivered: List[Barrel], order_id: int):
    """Update the inventory based on delivered barrels"""
    print(f"barrels delivered: {barrels_delivered} order_id: {order_id}")
    
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT num_green_ml, num_red_ml, num_blue_ml, gold 
            FROM global_inventory
        """)).fetchone()
        
        total_green_ml = res.num_green_ml
        total_red_ml = res.num_red_ml
        total_blue_ml = res.num_blue_ml
        total_gold = res.gold
        
        for barrel in barrels_delivered:
            if barrel.sku.upper() == "SMALL_GREEN_BARREL":
                total_green_ml += barrel.ml_per_barrel
            elif barrel.sku.upper() == "SMALL_RED_BARREL":
                total_red_ml += barrel.ml_per_barrel
            elif barrel.sku.upper() == "SMALL_BLUE_BARREL":
                total_blue_ml += barrel.ml_per_barrel
            
            total_gold -= barrel.price
        
        connection.execute(sqlalchemy.text(f"""
            UPDATE global_inventory 
            SET num_green_ml = {total_green_ml}, 
                num_red_ml = {total_red_ml},  
                num_blue_ml = {total_blue_ml}, 
                gold = {total_gold}
        """))
    
    return "UPDATED inventory"

# Gets called once a day
@router.post("/plan")
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]): 
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT num_green_potions, num_red_potions, num_blue_potions, gold 
            FROM global_inventory
        """)).fetchone()
        
        num_green_potions = res.num_green_potions
        num_red_potions = res.num_red_potions
        num_blue_potions = res.num_blue_potions
        gold = res.gold            
        purchase_plan = []
        for barrel in wholesale_catalog:
            if barrel.sku.upper() == "SMALL_GREEN_BARREL" and num_green_potions < 10 and gold >= barrel.price:
                purchase_plan.append({
                    "sku": barrel.sku,
                    "quantity": 1 
                })
                gold -= barrel.price 
          
            if barrel.sku.upper() == "SMALL_RED_BARREL" and num_red_potions < 10 and gold >= barrel.price:
                purchase_plan.append({
                    "sku": barrel.sku,
                    "quantity": 1 
                })
                gold -= barrel.price  
            
            if barrel.sku.upper() == "SMALL_BLUE_BARREL" and num_blue_potions < 10 and gold >= barrel.price:
                purchase_plan.append({
                    "sku": barrel.sku,
                    "quantity": 1 
                })
                gold -= barrel.price  
        return purchase_plan 

    return []
