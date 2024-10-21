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
    """Update the inventory based on delivered barrels dynamically without hardcoding potion types"""
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
            potion_details = connection.execute(sqlalchemy.text("""
                SELECT red_component, green_component, blue_component, dark_component
                FROM potion_catalog
                WHERE sku = :sku
            """), {"sku": barrel.sku}).fetchone()

            if potion_details is None:
                return {"error": f"Potion with SKU '{barrel.sku}' not found in catalog."}

            total_red_ml += potion_details.red_component * barrel.ml_per_barrel // 100
            total_green_ml += potion_details.green_component * barrel.ml_per_barrel // 100
            total_blue_ml += potion_details.blue_component * barrel.ml_per_barrel // 100
            total_gold -= barrel.price

        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory 
            SET num_green_ml = :green_ml, 
                num_red_ml = :red_ml,  
                num_blue_ml = :blue_ml, 
                gold = :gold
        """), {
            "green_ml": total_green_ml,
            "red_ml": total_red_ml,
            "blue_ml": total_blue_ml,
            "gold": total_gold
        })
    
    return {"message": "Inventory updated successfully"}


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
            if not barrel.sku.upper().startswith("SMALL"):
                continue

            potion_details = connection.execute(sqlalchemy.text("""
                SELECT red_component, green_component, blue_component, dark_component
                FROM potion_catalog
            """)).fetchone()
            if potion_details is None:
                continue
            red_component = potion_details.red_component
            green_component = potion_details.green_component
            blue_component = potion_details.blue_component

            if gold < barrel.price:
                continue
            if red_component > 0 and num_red_potions < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
            elif green_component > 0 and num_green_potions < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
            elif blue_component > 0 and num_blue_potions < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
        
        print(f"Barrel plan: ${purchase_plan}")
        print(f"Gold after: {gold}")
        return purchase_plan
