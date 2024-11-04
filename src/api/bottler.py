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
        transaction_result = connection.execute(sqlalchemy.text("""
            INSERT INTO transactions (description) VALUES (:description) RETURNING id
        """), {"description": f"Bottler delivery order {order_id}"})
        transaction_id = transaction_result.fetchone().id

        ml_result = connection.execute(sqlalchemy.text("""
            SELECT 
                COALESCE(SUM(red_ml_change), 0) as red_ml_total,
                COALESCE(SUM(green_ml_change), 0) as green_ml_total,
                COALESCE(SUM(blue_ml_change), 0) as blue_ml_total,
                COALESCE(SUM(dark_ml_change), 0) as dark_ml_total
            FROM ml_ledger_entries 
        """)).fetchone()

        inventory = {
            "red_ml": ml_result.red_ml_total,
            "green_ml": ml_result.green_ml_total,
            "blue_ml": ml_result.blue_ml_total,
            "dark_ml": ml_result.dark_ml_total
        }
        print(f"Initial ML Inventory: {inventory}")

        for potion in potions_delivered:
            print(f"Processing Potion Type: {potion.potion_type}, Quantity: {potion.quantity}")
            potion_recipe = connection.execute(sqlalchemy.text("""
                SELECT id, red_component, green_component, blue_component, dark_component
                FROM potion_catalog
                WHERE red_component = :red AND green_component = :green AND blue_component = :blue AND dark_component = :dark
            """), {
                "red": potion.potion_type[0],
                "green": potion.potion_type[1],
                "blue": potion.potion_type[2],
                "dark": potion.potion_type[3]
            }).fetchone()

            if not potion_recipe:
                print(f"Invalid potion mix: {potion.potion_type}")
                return {"error": f"Invalid potion mix {potion.potion_type}"}

            red_ml_required = potion_recipe.red_component * potion.quantity
            green_ml_required = potion_recipe.green_component * potion.quantity
            blue_ml_required = potion_recipe.blue_component * potion.quantity
            dark_ml_required = potion_recipe.dark_component * potion.quantity

            if (inventory["red_ml"] < red_ml_required or
                inventory["green_ml"] < green_ml_required or
                inventory["blue_ml"] < blue_ml_required or
                inventory["dark_ml"] < dark_ml_required):
                print("Insufficient ML in inventory after deduction.")
                return {"error": "Insufficient ml in inventory"}

            inventory["red_ml"] -= red_ml_required
            inventory["green_ml"] -= green_ml_required
            inventory["blue_ml"] -= blue_ml_required
            inventory["dark_ml"] -= dark_ml_required

            connection.execute(sqlalchemy.text("""
                INSERT INTO ml_ledger_entries (transaction_id, red_ml_change, green_ml_change, blue_ml_change, dark_ml_change, description)
                VALUES (:transaction_id, :red_ml_change, :green_ml_change, :blue_ml_change, :dark_ml_change, :description)
            """), {
                "transaction_id": transaction_id,
                "red_ml_change": -red_ml_required,
                "green_ml_change": -green_ml_required,
                "blue_ml_change": -blue_ml_required,
                "dark_ml_change": -dark_ml_required,
                "description": f"Used ml for potion {potion_recipe.id} in order {order_id}"
            })

            connection.execute(sqlalchemy.text("""
                INSERT INTO potion_inventory_ledger_entries (potion_catalog_id, transaction_id, change, description)
                VALUES (:catalog_id, :transaction_id, :change, :description)
            """), {
                "catalog_id": potion_recipe.id,
                "transaction_id": transaction_id,
                "change": potion.quantity,
                "description": f"Produced {potion.quantity} units of potion {potion_recipe.id} in order {order_id}"
            })

        print(f"Global inventory updated successfully via ledger entries.")
        return {"message": "Inventory updated successfully via ledger"}

    
@router.post("/plan")
def get_bottle_plan():
    print("Generating bottling plan.")
    with db.engine.begin() as connection:
        ml_result = connection.execute(sqlalchemy.text("""
            SELECT 
                COALESCE(SUM(red_ml_change), 0) as total_red_ml,
                COALESCE(SUM(green_ml_change), 0) as total_green_ml,
                COALESCE(SUM(blue_ml_change), 0) as total_blue_ml,
                COALESCE(SUM(dark_ml_change), 0) as total_dark_ml
            FROM ml_ledger_entries
        """)).fetchone()

        if ml_result is None:
            print("No ML ledger entries found.")
            return {"error": "No ML inventory data found."}

        inventory = {
            "red_ml": ml_result.total_red_ml,
            "green_ml": ml_result.total_green_ml,
            "blue_ml": ml_result.total_blue_ml,
            "dark_ml": ml_result.total_dark_ml
        }
        print(f"Current Inventory - Red ML: {inventory['red_ml']}, Green ML: {inventory['green_ml']}, Blue ML: {inventory['blue_ml']}, Dark ML: {inventory['dark_ml']}")

        potion_recipes = connection.execute(sqlalchemy.text("""
            SELECT id, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """)).fetchall()

        print(f"Fetched Potion Recipes: {potion_recipes}")

        max_potions_per_type = []
        for recipe in potion_recipes:
            potion_type = [recipe.red_component, recipe.green_component, recipe.blue_component, recipe.dark_component]
            print(f"Evaluating Potion ID: {recipe.id}, Type: {potion_type}")
            red_ml_required = recipe.red_component
            green_ml_required = recipe.green_component
            blue_ml_required = recipe.blue_component
            dark_ml_required = recipe.dark_component

            if red_ml_required == 0 and green_ml_required == 0 and blue_ml_required == 0 and dark_ml_required == 0:
                print(f"Skipping Potion ID {recipe.id} because it requires no components.")
                continue

            max_potions = min(
                inventory["red_ml"] // red_ml_required if red_ml_required > 0 else float('inf'),
                inventory["green_ml"] // green_ml_required if green_ml_required > 0 else float('inf'),
                inventory["blue_ml"] // blue_ml_required if blue_ml_required > 0 else float('inf'),
                inventory["dark_ml"] // dark_ml_required if dark_ml_required > 0 else float('inf'),
            )

            max_potions_per_type.append({
                "potion_id": recipe.id,
                "potion_type": potion_type,
                "max_quantity": int(max_potions),
                "red_ml_required": red_ml_required,
                "green_ml_required": green_ml_required,
                "blue_ml_required": blue_ml_required,
                "dark_ml_required": dark_ml_required
            })
            print(f"Max Potions for Potion ID {recipe.id}: {int(max_potions)}")

        if not max_potions_per_type:
            print("No potions can be produced with the current inventory.")
            return {"message": "No potions can be produced with the current inventory."}

        min_quantity = min(potion["max_quantity"] for potion in max_potions_per_type if potion["max_quantity"] > 0)
        print(f"Equal quantity to produce for each potion: {min_quantity}")

        potion_plan = []
        for potion in max_potions_per_type:
            if potion["max_quantity"] >= min_quantity and min_quantity > 0:
                potion_plan.append({
                    "potion_id": potion["potion_id"],
                    "potion_type": potion["potion_type"],
                    "quantity": min_quantity
                })
                inventory["red_ml"] -= potion["red_ml_required"] * min_quantity
                inventory["green_ml"] -= potion["green_ml_required"] * min_quantity
                inventory["blue_ml"] -= potion["blue_ml_required"] * min_quantity
                inventory["dark_ml"] -= potion["dark_ml_required"] * min_quantity
                print(f"Added Potion ID {potion['potion_id']} to plan with quantity {min_quantity}.")
                print(f"Updated Inventory: {inventory}")
            else:
                print(f"Potion ID {potion['potion_id']} cannot be produced in equal quantity due to inventory constraints.")

        print(f"Final Bottling Plan: {potion_plan}")
        return potion_plan
