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




# Gets called once a day
@router.post("/plan")
def get_capacity_plan():
    """
    Get the current capacity plan based on available gold. Each additional capacity 
    for potions (50 potions) and ml (10,000 ml) costs 1000 gold.
    """


class CapacityPurchase(BaseModel):
    potion_capacity: int
    ml_capacity: int

# Gets called once a day
@router.post("/deliver/{order_id}")
def deliver_capacity_plan(capacity_purchase: CapacityPurchase, order_id: int):
    """
    Deduct gold for the purchased capacity. Each additional capacity unit costs 1000 gold.
    """
 

