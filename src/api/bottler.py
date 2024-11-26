from fastapi import APIRouter, Depends
from enum import Enum
from pydantic import BaseModel
from src.api import auth
import sqlalchemy
from typing import List
from src import database as db
from pulp import LpMaximize, LpProblem, LpVariable, lpSum, LpInteger


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
        
        potion_inventory_result = connection.execute(sqlalchemy.text("""
            SELECT 
                potion_catalog_id, 
                COALESCE(SUM(change), 0) AS total_inventory
            FROM potion_inventory_ledger_entries
            GROUP BY potion_catalog_id
        """)).fetchall()
        current_potion_inventory = {row.potion_catalog_id: row.total_inventory for row in potion_inventory_result}

        capacity_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(potion_capacity), 0) AS total_potion_capacity
            FROM capacity_purchases
        """)).fetchone()
        total_potion_capacity_units = 1 + (capacity_result.total_potion_capacity or 0)
        total_potion_capacity = total_potion_capacity_units * 50

        total_potions_in_inventory = sum(current_potion_inventory.values())
        total_potions_to_add = sum(potion.quantity for potion in potions_delivered)
        new_total_potions = total_potions_in_inventory + total_potions_to_add

        if new_total_potions > total_potion_capacity:
            print(f"Cannot add potions. Current inventory: {total_potions_in_inventory}, Potions to add: {total_potions_to_add}, Capacity: {total_potion_capacity}")
            return {"error": "Cannot exceed potion inventory capacity."}

        transaction_result = connection.execute(sqlalchemy.text("""
            INSERT INTO transactions (description) VALUES (:description) RETURNING id
        """), {"description": f"Bottler delivery order {order_id}"})
        transaction_id = transaction_result.fetchone().id

        ml_result = connection.execute(sqlalchemy.text("""
            SELECT 
                COALESCE(SUM(red_ml_change), 0) AS red_ml_total,
                COALESCE(SUM(green_ml_change), 0) AS green_ml_total,
                COALESCE(SUM(blue_ml_change), 0) AS blue_ml_total,
                COALESCE(SUM(dark_ml_change), 0) AS dark_ml_total
            FROM ml_ledger_entries 
        """)).fetchone()

        ml_inventory = {
            "red": ml_result.red_ml_total or 0,
            "green": ml_result.green_ml_total or 0,
            "blue": ml_result.blue_ml_total or 0,
            "dark": ml_result.dark_ml_total or 0
        }
        print(f"Initial ML Inventory: {ml_inventory}")

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

            if (
                ml_inventory["red"] < red_ml_required or
                ml_inventory["green"] < green_ml_required or
                ml_inventory["blue"] < blue_ml_required or
                ml_inventory["dark"] < dark_ml_required
            ):
                print("Insufficient ML in inventory for potion production.")
                return {"error": "Insufficient ml in inventory"}

            ml_inventory["red"] -= red_ml_required
            ml_inventory["green"] -= green_ml_required
            ml_inventory["blue"] -= blue_ml_required
            ml_inventory["dark"] -= dark_ml_required

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
    Generate an optimal bottling plan using Integer Linear Programming to maximize profit and variety.
    """
    print("Starting optimized bottling plan generation.")
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

            ml_inventory = {
                "red": ml_result.total_red_ml or 0,
                "green": ml_result.total_green_ml or 0,
                "blue": ml_result.total_blue_ml or 0,
                "dark": ml_result.total_dark_ml or 0
            }

            potion_recipes = connection.execute(sqlalchemy.text("""
                SELECT 
                    id, name, red_component, green_component, blue_component, dark_component, price
                FROM potion_catalog
            """)).fetchall()

            potion_inventory_result = connection.execute(sqlalchemy.text("""
                SELECT 
                    potion_catalog_id, 
                    COALESCE(SUM(change), 0) AS total_inventory
                FROM potion_inventory_ledger_entries
                GROUP BY potion_catalog_id
            """)).fetchall()
            current_potion_inventory = {row.potion_catalog_id: row.total_inventory for row in potion_inventory_result}

            capacity_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(potion_capacity), 0) AS total_potion_capacity
                FROM capacity_purchases
            """)).fetchone()
            total_potion_capacity_units = 1 + (capacity_result.total_potion_capacity or 0)
            total_potion_capacity = total_potion_capacity_units * 50

            total_potions_in_inventory = sum(current_potion_inventory.values())
            available_capacity = total_potion_capacity - total_potions_in_inventory

            if available_capacity <= 0:
                print("No available capacity for new potions.")
                return []

            prob = LpProblem("Potion_Production", LpMaximize)

            potion_vars = {}
            for potion in potion_recipes:
                current_inventory = current_potion_inventory.get(potion.id, 0)
                max_possible = min(50 - current_inventory, available_capacity)
                if max_possible <= 0:
                    continue
                var = LpVariable(f"x_{potion.id}", lowBound=0, upBound=max_possible, cat=LpInteger)
                is_produced = LpVariable(f"y_{potion.id}", cat="Binary")
                potion_vars[potion.id] = {
                    "variable": var,
                    "is_produced": is_produced,
                    "data": potion
                }

            if not potion_vars:
                print("No potions can be produced within capacity constraints.")
                return []

            # Objective function: Maximize profit and variety
            profit_weight = 0.8
            variety_weight = 0.2

            prob += (
                profit_weight * lpSum([potion_vars[potion_id]["data"].price * var["variable"]
                                       for potion_id, var in potion_vars.items()]) +
                variety_weight * lpSum([var["is_produced"] for var in potion_vars.values()])
            ), "ProfitAndVariety"

            # Constraints:
            prob += lpSum([var["variable"] for var in potion_vars.values()]) <= available_capacity, "TotalCapacity"

            # ML constraints
            for ml_type in ['red', 'green', 'blue', 'dark']:
                prob += lpSum([
                    getattr(var["data"], f"{ml_type}_component") * var["variable"]
                    for var in potion_vars.values()
                ]) <= ml_inventory[ml_type], f"{ml_type.capitalize()}MLConstraint"

            # Per-potion type limit
            for potion_id, var in potion_vars.items():
                current_inventory = current_potion_inventory.get(potion_id, 0)
                prob += var["variable"] + current_inventory <= 50, f"PerPotionLimit_{potion_id}"

            for potion_id, var in potion_vars.items():
                max_possible = var["variable"].upBound
                prob += var["variable"] >= var["is_produced"], f"Link_{potion_id}"
                prob += var["variable"] <= var["is_produced"] * max_possible, f"LinkMax_{potion_id}"

            prob.solve()

            production_plan = []
            for potion_id, var in potion_vars.items():
                quantity = int(var["variable"].varValue) if var["variable"].varValue else 0
                if quantity > 0:
                    potion_data = var["data"]
                    production_plan.append({
                        "potion_type": [
                            potion_data.red_component,
                            potion_data.green_component,
                            potion_data.blue_component,
                            potion_data.dark_component
                        ],
                        "quantity": quantity
                    })

            print("Optimized Bottling Plan Complete.")
            print("Production Plan:", production_plan)

            return production_plan

    except Exception as e:
        print(f"Error generating optimized bottling plan: {e}")
        return {"status": "error", "message": "An error occurred while generating the bottling plan."}
