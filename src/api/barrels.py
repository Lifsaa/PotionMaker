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
            if barrel.potion_type == [0, 1, 0, 0]:  
                total_green_ml += barrel.ml_per_barrel
            elif barrel.potion_type == [1, 0, 0, 0]:  
                total_red_ml += barrel.ml_per_barrel
            elif barrel.potion_type == [0, 0, 1, 0]:  
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
    """Generate a wholesale purchase plan based on available stock and gold."""
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT  gold 
            FROM global_inventory
        """)).fetchone()

        purchase_plan = []
        gold = res.gold
        
        for barrel in wholesale_catalog:
            potion = connection.execute(sqlalchemy.text("""
                SELECT red_component, green_component, blue_component, dark_component 
                FROM potion_catalog 
                WHERE sku = :sku
            """), {"sku": barrel.sku}).fetchone()
            
            if not potion:
                continue  # Skip if potion type is invalid

            # Check if we can afford the barrel with the current gold
            if gold >= barrel.price:
                purchase_plan.append({"sku": barrel.sku, "quantity": barrel.quantity})
                gold -= barrel.price

        return purchase_plan