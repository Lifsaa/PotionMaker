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
    print(f"Delivering barrels for Order ID: {order_id}")
    print(f"Barrels to deliver: {barrels_delivered}")
    
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT num_green_ml, num_red_ml, num_blue_ml, gold 
            FROM global_inventory
            WHERE id = :inventory_id
            FOR UPDATE
        """), {"inventory_id": 1}).fetchone()
        
        if res is None:
            print("Global inventory not found.")
            return {"error": "Global inventory not found."}
        
        total_green_ml = res.num_green_ml
        total_red_ml = res.num_red_ml
        total_blue_ml = res.num_blue_ml
        total_gold = res.gold
        print(f"Initial Inventory - Green ML: {total_green_ml}, Red ML: {total_red_ml}, Blue ML: {total_blue_ml}, Gold: {total_gold}")
    
        for barrel in barrels_delivered:
            print(f"Processing Barrel SKU: {barrel.sku}, Quantity: {barrel.quantity}")
            if barrel.potion_type == [0, 1, 0, 0]:  
                total_green_ml += barrel.ml_per_barrel * barrel.quantity
                print(f"Added {barrel.ml_per_barrel * barrel.quantity} ML to Green Potions.")
            if barrel.potion_type == [1, 0, 0, 0]:  
                total_red_ml += barrel.ml_per_barrel * barrel.quantity
                print(f"Added {barrel.ml_per_barrel * barrel.quantity} ML to Red Potions.")
            if barrel.potion_type == [0, 0, 1, 0]:  
                total_blue_ml += barrel.ml_per_barrel * barrel.quantity
                print(f"Added {barrel.ml_per_barrel * barrel.quantity} ML to Blue Potions.")
            total_gold -= barrel.price * barrel.quantity
            print(f"Deducted {barrel.price * barrel.quantity} Gold. Remaining Gold: {total_gold}")
        
        print(f"Updated Totals - Green ML: {total_green_ml}, Red ML: {total_red_ml}, Blue ML: {total_blue_ml}, Gold: {total_gold}")
        
        if total_gold < 0:
            print("Error: Not enough gold to complete the delivery.")
            return {"error": "Not enough gold"}
        
        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory 
            SET num_green_ml = :green_ml, 
                num_red_ml = :red_ml,  
                num_blue_ml = :blue_ml, 
                gold = :gold
            WHERE id = :inventory_id
        """), {
            "green_ml": total_green_ml,
            "red_ml": total_red_ml,
            "blue_ml": total_blue_ml,
            "gold": total_gold,
            "inventory_id":1
        })
        print("Global inventory updated successfully.")
    
    return {"message": "UPDATED inventory"}

# Gets called once a day
@router.post("/plan")
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]): 
    print("Generating wholesale purchase plan.")
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT num_green_potions, num_red_potions, num_blue_potions, gold 
            FROM global_inventory
            WHERE id = :inventory_id
        """), {"inventory_id":1}).fetchone()
        
        if res is None:
            print("Global inventory not found for purchase plan.")
            return {"error": "Global inventory not found."}
   
        num_green_potions = res.num_green_potions
        num_red_potions = res.num_red_potions
        num_blue_potions = res.num_blue_potions
        gold = res.gold
        print(f"Current Gold: {gold}")
        print(f"Potion Counts - Green: {num_green_potions}, Red: {num_red_potions}, Blue: {num_blue_potions}")
       
        purchase_plan = []
        for barrel in wholesale_catalog:
            print(f"Evaluating Barrel SKU: {barrel.sku}, Price: {barrel.price}")
            if gold < barrel.price:  
                print(f"Skipping Barrel SKU: {barrel.sku} due to insufficient gold.")
                continue

            if barrel.sku.upper().startswith("MEDIUM"):
                if barrel.potion_type == [1, 0, 0, 0] and num_red_potions < 30:  
                    purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                    gold -= barrel.price
                    print(f"Added Medium Red Barrel to purchase plan.")
                
                if barrel.potion_type == [0, 1, 0, 0] and num_green_potions < 30:  
                    purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                    gold -= barrel.price
                    print(f"Added Medium Green Barrel to purchase plan.")
                
                if barrel.potion_type == [0, 0, 1, 0] and num_blue_potions < 20:  
                    purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                    gold -= barrel.price
                    print(f"Added Medium Blue Barrel to purchase plan.")

            if barrel.sku.upper() == "SMALL_GREEN_BARREL" and num_green_potions < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
                print(f"Added Small Green Barrel to purchase plan.")

            if barrel.sku.upper() == "SMALL_RED_BARREL" and num_red_potions < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
                print(f"Added Small Red Barrel to purchase plan.")

            if barrel.sku.upper() == "SMALL_BLUE_BARREL" and num_blue_potions < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
                print(f"Added Small Blue Barrel to purchase plan.")

        print(f"Final Purchase Plan: {purchase_plan}")
        return purchase_plan
