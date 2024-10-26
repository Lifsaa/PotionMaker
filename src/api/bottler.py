from fastapi import APIRouter, Depends
from enum import Enum
from pydantic import BaseModel
from src.api import auth
import sqlalchemy
from typing import List
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
def post_deliver_bottles(potions_delivered: List[PotionInventory], order_id: int):
    print(f"Delivering potions for Order ID: {order_id}")
    print(f"Potions to deliver: {potions_delivered}")
    
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT num_red_ml, num_green_ml, num_blue_ml, num_dark_ml
            FROM global_inventory
            WHERE id = :inventory_id
            FOR UPDATE
        """), {"inventory_id":1}).fetchone()
        
        if res is None:
            print("Global inventory not found.")
            return {"error": "Global inventory not found."}
        
        inventory = {
            "red_ml": res.num_red_ml,
            "green_ml": res.num_green_ml,
            "blue_ml": res.num_blue_ml,
            "dark_ml": res.num_dark_ml
        }
        print(f"Initial Inventory - Red ML: {inventory['red_ml']}, Green ML: {inventory['green_ml']}, Blue ML: {inventory['blue_ml']}, Dark ML: {inventory['dark_ml']}")
    
        for potion in potions_delivered:
            print(f"Processing Potion Type: {potion.potion_type}, Quantity: {potion.quantity}")
            potion_recipe = connection.execute(sqlalchemy.text("""
                SELECT red_component, green_component, blue_component, dark_component, inventory
                FROM potion_catalog
                WHERE red_component = :red AND green_component = :green AND blue_component = :blue AND dark_component = :dark
                FOR UPDATE
            """), {
                "red": potion.potion_type[0],
                "green": potion.potion_type[1],
                "blue": potion.potion_type[2],
                "dark": potion.potion_type[3]
            }).fetchone()
    
            print(f"Fetched Potion Recipe: {potion_recipe}")
    
            if not potion_recipe:
                print(f"Invalid potion mix: {potion.potion_type}")
                return {"error": f"Invalid potion mix {potion.potion_type}"}
    
            inventory["red_ml"] -= potion_recipe.red_component * potion.quantity
            inventory["green_ml"] -= potion_recipe.green_component * potion.quantity
            inventory["blue_ml"] -= potion_recipe.blue_component * potion.quantity
            inventory["dark_ml"] -= potion_recipe.dark_component * potion.quantity
            print(f"Updated Inventory after Deduction - Red ML: {inventory['red_ml']}, Green ML: {inventory['green_ml']}, Blue ML: {inventory['blue_ml']}, Dark ML: {inventory['dark_ml']}")
    
            if inventory["red_ml"] < 0 or inventory["green_ml"] < 0 or inventory["blue_ml"] < 0 or inventory["dark_ml"] < 0:
                print("Insufficient ML in inventory after deduction.")
                return {"error": "Insufficient ml in inventory"}
    
            new_inventory = potion_recipe.inventory + potion.quantity
            connection.execute(sqlalchemy.text("""
                UPDATE potion_catalog
                SET inventory = :new_inventory
                WHERE red_component = :red AND green_component = :green AND blue_component = :blue AND dark_component = :dark
            """), {
                "new_inventory": new_inventory,
                "red": potion.potion_type[0],
                "green": potion.potion_type[1],
                "blue": potion.potion_type[2],
                "dark": potion.potion_type[3]
            })
            print(f"Updated Potion Catalog for Potion Type {potion.potion_type} to Inventory: {new_inventory}")
    
        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory
            SET num_red_ml = :red_ml, num_green_ml = :green_ml, num_blue_ml = :blue_ml, num_dark_ml = :dark_ml
            WHERE id = :inventory_id
        """), {
            "red_ml": inventory["red_ml"],
            "green_ml": inventory["green_ml"],
            "blue_ml": inventory["blue_ml"],
            "dark_ml": inventory["dark_ml"],
            "inventory_id":1
        })
        print(f"Global inventory updated successfully: {inventory}")
    
    return {"message": "Inventory updated successfully"}    
    
@router.post("/plan")
def get_bottle_plan():
    print("Generating bottling plan.")
    with db.engine.begin() as connection:
        res = connection.execute(sqlalchemy.text("""
            SELECT num_red_ml, num_green_ml, num_blue_ml, num_dark_ml
            FROM global_inventory
            WHERE id = :inventory_id
        """), {"inventory_id":1}).fetchone()
        
        if res is None:
            print("Global inventory not found for bottling plan.")
            return {"error": "Global inventory not found."}
        
        inventory = {
            "red_ml": res.num_red_ml,
            "green_ml": res.num_green_ml,
            "blue_ml": res.num_blue_ml,
            "dark_ml": res.num_dark_ml
        }
        print(f"Current Inventory - Red ML: {inventory['red_ml']}, Green ML: {inventory['green_ml']}, Blue ML: {inventory['blue_ml']}, Dark ML: {inventory['dark_ml']}")
    
        potion_recipes = connection.execute(sqlalchemy.text("""
            SELECT id, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """)).fetchall()
        
        print(f"Fetched Potion Recipes: {potion_recipes}")
    
        potion_plan = []
    
        for recipe in potion_recipes:
            potion_type = [recipe.red_component, recipe.green_component, recipe.blue_component, recipe.dark_component]
            print(f"Evaluating Potion ID: {recipe.id}, Type: {potion_type}")
            red_ml_required = recipe.red_component
            green_ml_required = recipe.green_component
            blue_ml_required = recipe.blue_component
            dark_ml_required = recipe.dark_component
    
            max_potions = min(
                inventory["red_ml"] // red_ml_required if red_ml_required > 0 else float('inf'),
                inventory["green_ml"] // green_ml_required if green_ml_required > 0 else float('inf'),
                inventory["blue_ml"] // blue_ml_required if blue_ml_required > 0 else float('inf'),
                inventory["dark_ml"] // dark_ml_required if dark_ml_required > 0 else float('inf'),
            )
    
            print(f"Max Potions for Potion ID {recipe.id}: {max_potions}")
            if max_potions > 0:
                potion_plan.append({
                    "potion_id": recipe.id,
                    "potion_type": potion_type,
                    "quantity": max_potions
                })
                print(f"Added to Potion Plan: {potion_plan[-1]}")
    
        print(f"Final Bottling Plan: {potion_plan}")
        return potion_plan


if __name__ == "__main__":
    print(get_bottle_plan())
