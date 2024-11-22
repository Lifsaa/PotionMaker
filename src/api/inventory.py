from fastapi import APIRouter, Depends
from pydantic import BaseModel
from src.api import auth
import sqlalchemy
from src import database as db

router = APIRouter(
    prefix="/inventory",
    tags=["inventory"],
    dependencies=[Depends(auth.get_api_key)],
)

@router.get("/audit")
def audit_inventory():
    print("Starting inventory audit.")
    with db.engine.begin() as connection:
        gold_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries
        """))
        total_gold = gold_result.fetchone().gold_total or 0

        ml_result = connection.execute(sqlalchemy.text("""
            SELECT 
                COALESCE(SUM(red_ml_change), 0) as total_red_ml,
                COALESCE(SUM(green_ml_change), 0) as total_green_ml,
                COALESCE(SUM(blue_ml_change), 0) as total_blue_ml,
                COALESCE(SUM(dark_ml_change), 0) as total_dark_ml
            FROM ml_ledger_entries
        """)).fetchone()

        total_red_ml = ml_result.total_red_ml
        total_green_ml = ml_result.total_green_ml
        total_blue_ml = ml_result.total_blue_ml
        total_dark_ml = ml_result.total_dark_ml

        potion_catalog_res = connection.execute(sqlalchemy.text("""
            SELECT 
                id, name, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """)).fetchall()

        potion_inventory = []

        for row in potion_catalog_res:
            ledger_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(change), 0) as total_inventory
                FROM potion_inventory_ledger_entries
                WHERE potion_catalog_id = :catalog_id
            """), {"catalog_id": row.id})
            total_inventory = ledger_result.fetchone().total_inventory or 0

            custom_potion = {
                "name": row.name,
                "red_component": row.red_component,
                "green_component": row.green_component,
                "blue_component": row.blue_component,
                "dark_component": row.dark_component,
                "inventory": total_inventory
            }
            potion_inventory.append(custom_potion)
            print(f"Custom Potion: {custom_potion}")

        audit_data = {
            "gold": total_gold,
            "ml_inventory": {
                "red_ml": total_red_ml,
                "green_ml": total_green_ml,
                "blue_ml": total_blue_ml,
                "dark_ml": total_dark_ml
            },
            "potion_inventory": {
                "custom_potions": potion_inventory
            }
        }

    print(f"Audit Data: {audit_data}")
    return audit_data


class CapacityPurchase(BaseModel):
    potion_capacity: int
    ml_capacity: int

@router.post("/plan")
def get_capacity_plan():
    """
    Get the current capacity plan based on available gold. Each additional capacity 
    for potions (50 potions) and ml (10,000 ml) costs 1000 gold.
    """
    print("Calculating capacity plan.")
    with db.engine.begin() as connection:
        capacity_result = connection.execute(sqlalchemy.text("""
            SELECT 
                COALESCE(SUM(potion_capacity), 0) as total_potion_capacity,
                COALESCE(SUM(ml_capacity), 0) as total_ml_capacity
            FROM capacity_purchases
        """)).fetchone()
        total_potion_capacity_units = 1 + capacity_result.total_potion_capacity
        total_ml_capacity_units = 1 + capacity_result.total_ml_capacity

        total_potion_capacity = total_potion_capacity_units * 50
        total_ml_capacity = total_ml_capacity_units * 10000

        print(f"Total potion capacity units: {total_potion_capacity_units}, Total ml capacity units: {total_ml_capacity_units}")
        print(f"Total potion capacity: {total_potion_capacity}, Total ml capacity: {total_ml_capacity}")

        potion_inventory_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(change), 0) as total_potions
            FROM potion_inventory_ledger_entries
        """)).fetchone()
        total_potions = potion_inventory_result.total_potions or 0

        ml_result = connection.execute(sqlalchemy.text("""
            SELECT 
                COALESCE(SUM(red_ml_change), 0) as total_red_ml,
                COALESCE(SUM(green_ml_change), 0) as total_green_ml,
                COALESCE(SUM(blue_ml_change), 0) as total_blue_ml,
                COALESCE(SUM(dark_ml_change), 0) as total_dark_ml
            FROM ml_ledger_entries
        """)).fetchone()
        total_ml_inventory = (
            ml_result.total_red_ml +
            ml_result.total_green_ml +
            ml_result.total_blue_ml +
            ml_result.total_dark_ml
        )

        print(f"Total potions in inventory: {total_potions}")
        print(f"Total ml in inventory: {total_ml_inventory}")

        potion_capacity_usage = total_potions / total_potion_capacity
        ml_capacity_usage = total_ml_inventory / total_ml_capacity

        print(f"Potion capacity usage: {potion_capacity_usage * 100:.2f}%")
        print(f"ML capacity usage: {ml_capacity_usage * 100:.2f}%")

        potion_capacity_to_buy = 0
        ml_capacity_to_buy = 0

        threshold = 0.8 
        UNIT_COST = 1000

        gold_result = connection.execute(sqlalchemy.text("""
            SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries
        """))
        total_gold = gold_result.fetchone().gold_total or 0
        print(f"Total gold available: {total_gold}")

        if potion_capacity_usage > threshold and total_gold >= UNIT_COST:
            potion_capacity_to_buy = 1
            print("Potion capacity exceeds 80%, planning to buy 1 more capacity unit.")

        if ml_capacity_usage > threshold and total_gold >= UNIT_COST:
            ml_capacity_to_buy = 1
            print("ML capacity exceeds 80%, planning to buy 1 more capacity unit.")

        response = {
            "potion_capacity": potion_capacity_to_buy,
            "ml_capacity": ml_capacity_to_buy
        }

    print(f"Capacity plan response: {response}")
    return response


@router.post("/deliver")
def deliver_capacity_plan(capacity_purchase: CapacityPurchase):
    """
    Deduct gold for the purchased capacity. Each additional capacity unit costs 1000 gold.
    """
    potion_capacity = capacity_purchase.potion_capacity
    ml_capacity = capacity_purchase.ml_capacity

    if potion_capacity == 0 and ml_capacity == 0:
        raise ValueError("No capacity units requested for purchase.")

    if potion_capacity < 0 or ml_capacity < 0:
        raise ValueError("Capacity units cannot be negative.")

    total_units = potion_capacity + ml_capacity
    total_cost = total_units * 1000

    print(f"Delivering capacity plan.")
    print(f"Potion capacity to add: {potion_capacity}, ML capacity to add: {ml_capacity}")
    print(f"Total capacity units: {total_units}, Total cost: {total_cost}")

    try:
        with db.engine.begin() as connection:
            gold_result = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries
                FOR UPDATE
            """)).fetchone()
            total_gold = gold_result.gold_total or 0

            print(f"Total gold before deduction: {total_gold}")

            if total_gold < total_cost:
                print("Not enough gold to purchase capacity.")
                raise Exception("Insufficient gold to complete the purchase.")

            transaction_result = connection.execute(sqlalchemy.text("""
                INSERT INTO transactions (description) VALUES (:description) RETURNING id
            """), {"description": "Capacity purchase"})
            transaction_id = transaction_result.fetchone().id

            connection.execute(sqlalchemy.text("""
                INSERT INTO gold_ledger_entries (transaction_id, change, description)
                VALUES (:transaction_id, :change, :description)
            """), {
                "transaction_id": transaction_id,
                "change": -total_cost,
                "description": "Capacity purchase"
            })

            print(f"Deducted {total_cost} gold for capacity purchase.")

            connection.execute(sqlalchemy.text("""
                INSERT INTO capacity_purchases (transaction_id, potion_capacity, ml_capacity)
                VALUES (:transaction_id, :potion_capacity, :ml_capacity)
            """), {
                "transaction_id": transaction_id,
                "potion_capacity": potion_capacity,
                "ml_capacity": ml_capacity
            })

            print(f"Recorded capacity purchase: Potion capacity {potion_capacity}, ML capacity {ml_capacity}")

        return {"status": "success", "message": "Capacity purchase delivered successfully."}

    except Exception as e:
        print(f"Error during capacity purchase delivery: {e}")
        raise Exception("An error occurred while processing the capacity purchase.")