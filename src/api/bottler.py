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
    """
    Generate a bottling plan based on available ML inventory and potion recipes.
    Each potion can be produced up to a maximum of 50 units.
    """
    print("Starting bottling plan generation.")
    try:
        with db.engine.begin() as connection:
            ml_result = connection.execute(sqlalchemy.text("""
                SELECT 
                    COALESCE(SUM(red_ml_change), 0) AS total_red_ml,
                    COALESCE(SUM(green_ml_change), 0) AS total_green_ml,
                    COALESCE(SUM(blue_ml_change), 0) AS total_blue_ml,
                    COALESCE(SUM(dark_ml_change), 0) AS total_dark_ml
                FROM ml_ledger_entries
            """)).fetchone()

            inventory = {
                "red_ml": ml_result[0],
                "green_ml": ml_result[1],
                "blue_ml": ml_result[2],
                "dark_ml": ml_result[3]
            }

            potion_recipes = connection.execute(sqlalchemy.text("""
                SELECT id, red_component, green_component, blue_component, dark_component
                FROM potion_catalog
            """)).fetchall()

            potion_quantities = {potion[0]: 0 for potion in potion_recipes}  
            potion_types = {potion[0]: [potion[1], potion[2], potion[3], potion[4]] for potion in potion_recipes} 

            potion_plan = []
            production_possible = True

            while production_possible:
                production_possible = False

                available_potions = [potion for potion in potion_recipes if potion_quantities[potion[0]] < 50]

                if not available_potions:
                    break  

                available_potions.sort(key=lambda potion: potion_quantities[potion[0]])

                for recipe in available_potions:
                    potion_id = recipe[0]
                    red_ml_required, green_ml_required, blue_ml_required, dark_ml_required = recipe[1:]

                    if (
                        (red_ml_required <= inventory["red_ml"] or red_ml_required == 0) and
                        (green_ml_required <= inventory["green_ml"] or green_ml_required == 0) and
                        (blue_ml_required <= inventory["blue_ml"] or blue_ml_required == 0) and
                        (dark_ml_required <= inventory["dark_ml"] or dark_ml_required == 0)
                    ):
                        inventory["red_ml"] -= red_ml_required
                        inventory["green_ml"] -= green_ml_required
                        inventory["blue_ml"] -= blue_ml_required
                        inventory["dark_ml"] -= dark_ml_required

                        potion_quantities[potion_id] += 1
                        potion_type = potion_types[potion_id]

                        potion_in_plan = next((p for p in potion_plan if p["potion_type"] == potion_type), None)
                        if potion_in_plan:
                            potion_in_plan["quantity"] += 1
                        else:
                            potion_plan.append({
                                "potion_type": potion_type,
                                "quantity": 1
                            })

                        production_possible = True
                        break  
                    else:
                        continue 

                if not production_possible:
                    break

        print("Bottling Plan Complete.")
        print("Final Inventory (in ml):", inventory)
        print("Final Potion Quantities:", potion_quantities)

        return potion_plan

    except Exception as e:
        print(f"Error generating bottling plan: {e}")
        return {"status": "error", "message": "An error occurred while generating the bottling plan."}
