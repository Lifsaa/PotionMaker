from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from src.api import auth
import sqlalchemy
from src import database as db
from pulp import LpMaximize, LpProblem, LpVariable, lpSum, LpInteger


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

    total_gold_deducted = 0
    total_green_ml_added = 0
    total_red_ml_added = 0
    total_blue_ml_added = 0
    total_dark_ml_added = 0  

    for barrel in barrels_delivered:
        cost = barrel.price * barrel.quantity
        total_gold_deducted += cost
        ml_added = barrel.ml_per_barrel * barrel.quantity

        if barrel.potion_type == [0, 1, 0, 0]:
            total_green_ml_added += ml_added
        elif barrel.potion_type == [1, 0, 0, 0]:
            total_red_ml_added += ml_added
        elif barrel.potion_type == [0, 0, 1, 0]:
            total_blue_ml_added += ml_added
        elif barrel.potion_type == [0, 0, 0, 1]:
            total_dark_ml_added += ml_added
        else:
            print(f"Invalid potion type for barrel SKU: {barrel.sku}")
            raise ValueError(f"Invalid potion type for barrel SKU: {barrel.sku}")

    with db.engine.begin() as connection:
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

        capacity_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(ml_capacity), 0) AS total_ml_capacity
            FROM capacity_purchases
        """)).fetchone()
        total_ml_capacity_units = 1 + (capacity_result.total_ml_capacity or 0)
        total_ml_capacity = total_ml_capacity_units * 10000

        new_red_ml = ml_inventory["red"] + total_red_ml_added
        new_green_ml = ml_inventory["green"] + total_green_ml_added
        new_blue_ml = ml_inventory["blue"] + total_blue_ml_added
        new_dark_ml = ml_inventory["dark"] + total_dark_ml_added

        if (new_red_ml > total_ml_capacity or
            new_green_ml > total_ml_capacity or
            new_blue_ml > total_ml_capacity or
            new_dark_ml > total_ml_capacity):
            print("Cannot add ML. ML capacity would be exceeded.")
            raise Exception("Cannot exceed ML inventory capacity.")

        gold_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries
        """)).fetchone()
        current_gold = gold_result.gold_total or 0

        updated_gold = current_gold - total_gold_deducted
        print(f"Current Gold: {current_gold}, Gold Deducted: {total_gold_deducted}, Updated Gold: {updated_gold}")

        if updated_gold < 0:
            print("Error: Not enough gold to complete the delivery.")
            raise Exception("Not enough gold")

        transaction_result = connection.execute(sqlalchemy.text("""
            INSERT INTO transactions (description) VALUES (:description) RETURNING id
        """), {"description": f"Barrel delivery order {order_id}"})
        transaction_id = transaction_result.fetchone().id

        connection.execute(sqlalchemy.text("""
            INSERT INTO gold_ledger_entries (transaction_id, change, description)
            VALUES (:transaction_id, :change, :description)
        """), {
            "transaction_id": transaction_id,
            "change": -total_gold_deducted,
            "description": f"Barrel delivery order {order_id}"
        })

        connection.execute(sqlalchemy.text("""
            INSERT INTO ml_ledger_entries (transaction_id, red_ml_change, green_ml_change, blue_ml_change, dark_ml_change, description)
            VALUES (:transaction_id, :red_ml, :green_ml, :blue_ml, :dark_ml, :description)
        """), {
            "transaction_id": transaction_id,
            "red_ml": total_red_ml_added,
            "green_ml": total_green_ml_added,
            "blue_ml": total_blue_ml_added,
            "dark_ml": total_dark_ml_added,
            "description": f"Barrel delivery order {order_id}"
        })

    print("Global inventory updated successfully via ledger entries.")
    return {"message": "Inventory updated via ledger"}


@router.post("/plan")
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]): 
    try:
        print("Generating optimized wholesale purchase plan.")
        with db.engine.begin() as connection:
            gold_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(change), 0) AS gold_total FROM gold_ledger_entries
            """))
            gold = gold_result.fetchone().gold_total or 0
            print(f"Current Gold: {gold}")

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

            capacity_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(ml_capacity), 0) AS total_ml_capacity
                FROM capacity_purchases
            """)).fetchone()
            total_ml_capacity_units = 1 + (capacity_result.total_ml_capacity or 0)
            total_ml_capacity = total_ml_capacity_units * 10000

            current_total_ml = sum(ml_inventory.values())
            remaining_capacity = total_ml_capacity - current_total_ml
            print(f"Remaining ML Capacity: {remaining_capacity} ml")

            ml_threshold = 1000  
            ml_needs = [color for color, amount in ml_inventory.items() if amount < ml_threshold]

            barrel_vars = {}
            for barrel in wholesale_catalog:
                ml_type = ''
                if barrel.potion_type == [1, 0, 0, 0]:
                    ml_type = 'red'
                elif barrel.potion_type == [0, 1, 0, 0]:
                    ml_type = 'green'
                elif barrel.potion_type == [0, 0, 1, 0]:
                    ml_type = 'blue'
                elif barrel.potion_type == [0, 0, 0, 1]:
                    ml_type = 'dark'

                if ml_type in ml_needs:
                    max_quantity = barrel.quantity
                    var = LpVariable(f"b_{barrel.sku.replace(' ', '_')}", lowBound=0, upBound=max_quantity, cat=LpInteger)
                    barrel_vars[barrel.sku] = {
                        "variable": var,
                        "barrel": barrel,
                        "ml_type": ml_type
                    }

            if not barrel_vars:
                print("No barrels needed or affordable.")
                return []

            prob = LpProblem("Wholesale_Purchase_Plan", LpMaximize)

            prob += lpSum([
                var["barrel"].ml_per_barrel * var["variable"]
                for var in barrel_vars.values()
            ]), "Total_ML"

            prob += lpSum([
                var["barrel"].price * var["variable"]
                for var in barrel_vars.values()
            ]) <= gold, "GoldConstraint"

            prob += lpSum([
                var["barrel"].ml_per_barrel * var["variable"]
                for var in barrel_vars.values()
            ]) <= remaining_capacity, "MLCapacityConstraint"

            prob.solve()

            purchase_plan = []
            for sku, var in barrel_vars.items():
                quantity = int(var["variable"].varValue) if var["variable"].varValue else 0
                if quantity > 0:
                    purchase_plan.append({"sku": sku, "quantity": quantity})

            print(f"Final Purchase Plan: {purchase_plan}")
            return purchase_plan
    except Exception as e:
        print(f"Error generating wholesale purchase plan: {e}")
        return {"status": "error", "message": "An error occurred while generating the wholesale purchase plan."}
