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

    total_gold_deducted = 0
    total_green_ml_added = 0
    total_red_ml_added = 0
    total_blue_ml_added = 0

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

    with db.engine.begin() as connection:
        transaction_result = connection.execute(sqlalchemy.text("""
            INSERT INTO transactions (description) VALUES (:description) RETURNING id
        """), {"description": f"Barrel delivery order {order_id}"})
        transaction_id = transaction_result.fetchone().id

        gold_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries 
        """))
        current_gold = gold_result.fetchone().gold_total or 0

        updated_gold = current_gold - total_gold_deducted
        print(f"Current Gold: {current_gold}, Gold Deducted: {total_gold_deducted}, Updated Gold: {updated_gold}")

        if updated_gold < 0:
            print("Error: Not enough gold to complete the delivery.")
            raise ValueError("Not enough gold")

        connection.execute(sqlalchemy.text("""
            INSERT INTO gold_ledger_entries (transaction_id, change, description)
            VALUES (:transaction_id, :change, :description)
        """), {
            "transaction_id": transaction_id,
            "change": -total_gold_deducted,
            "description": f"Barrel delivery order {order_id}"
        })

        connection.execute(sqlalchemy.text("""
            INSERT INTO ml_ledger_entries (transaction_id, red_ml_change, green_ml_change, blue_ml_change, description)
            VALUES (:transaction_id, :red_ml, :green_ml, :blue_ml, :description)
        """), {
            "transaction_id": transaction_id,
            "red_ml": total_red_ml_added,
            "green_ml": total_green_ml_added,
            "blue_ml": total_blue_ml_added,
            "description": f"Barrel delivery order {order_id}"
        })

    print("Global inventory updated successfully via ledger entries.")
    return {"message": "Inventory updated via ledger"}


# Gets called once a day
@router.post("/plan")
def get_wholesale_purchase_plan(wholesale_catalog: List[Barrel]): 
    print("Generating wholesale purchase plan.")
    with db.engine.begin() as connection:
        gold_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries
        """))
        gold = gold_result.fetchone().gold_total or 0
        print(f"Current Gold: {gold}")

        potion_counts = {
            "num_green_potions": 0,
            "num_red_potions": 0,
            "num_blue_potions": 0
        }
        potion_catalog_ids = {}
        catalog_res = connection.execute(sqlalchemy.text("""
            SELECT id, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """)).fetchall()
        for row in catalog_res:
            potion_type = [row.red_component, row.green_component, row.blue_component, row.dark_component]
            potion_catalog_ids[tuple(potion_type)] = row.id

        for potion_type, catalog_id in potion_catalog_ids.items():
            ledger_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(change), 0) as total_inventory
                FROM potion_inventory_ledger_entries
                WHERE potion_catalog_id = :catalog_id
            """), {"catalog_id": catalog_id})
            total_inventory = ledger_result.fetchone().total_inventory or 0
            if potion_type == (1, 0, 0, 0):
                potion_counts["num_red_potions"] = total_inventory
            elif potion_type == (0, 1, 0, 0):
                potion_counts["num_green_potions"] = total_inventory
            elif potion_type == (0, 0, 1, 0):
                potion_counts["num_blue_potions"] = total_inventory

        print(f"Potion Counts - Green: {potion_counts['num_green_potions']}, Red: {potion_counts['num_red_potions']}, Blue: {potion_counts['num_blue_potions']}")
       
        purchase_plan = []
        for barrel in wholesale_catalog:
            print(f"Evaluating Barrel SKU: {barrel.sku}, Price: {barrel.price}")
            if gold < barrel.price:  
                print(f"Skipping Barrel SKU: {barrel.sku} due to insufficient gold.")
                continue
            
            if barrel.sku.upper() == "SMALL_GREEN_BARREL" and potion_counts["num_green_potions"] < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
                print(f"Added Small Green Barrel to purchase plan.")

            if barrel.sku.upper() == "SMALL_RED_BARREL" and potion_counts["num_red_potions"] < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
                print(f"Added Small Red Barrel to purchase plan.")

            if barrel.sku.upper() == "SMALL_BLUE_BARREL" and potion_counts["num_blue_potions"] < 10:
                purchase_plan.append({"sku": barrel.sku, "quantity": 1})
                gold -= barrel.price
                print(f"Added Small Blue Barrel to purchase plan.")

        print(f"Final Purchase Plan: {purchase_plan}")
        return purchase_plan
