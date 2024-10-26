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
        res = connection.execute(sqlalchemy.text("""
            SELECT 
                num_red_ml, num_green_ml, num_blue_ml, num_dark_ml,
                gold, last_updated
            FROM global_inventory
            WHERE id = :inventory_id
        """), {"inventory_id":1}).fetchone()
        
        if res is None:
            print("Global inventory not found during audit.")
            return {"error": "Global inventory not found."}
        
        total_red_ml = res.num_red_ml
        total_green_ml = res.num_green_ml
        total_blue_ml = res.num_blue_ml
        total_dark_ml = res.num_dark_ml
        total_gold = res.gold
        last_updated = res.last_updated
        print(f"Fetched Global Inventory - Red ML: {total_red_ml}, Green ML: {total_green_ml}, Blue ML: {total_blue_ml}, Dark ML: {total_dark_ml}, Gold: {total_gold}, Last Updated: {last_updated}")
    
        potion_catalog_res = connection.execute(sqlalchemy.text("""
            SELECT 
                name, red_component, green_component, blue_component, dark_component, inventory
            FROM potion_catalog
        """)).fetchall()
        
        print(f"Fetched Potion Catalog: {potion_catalog_res}")
    
        audit_data = {
            "gold": total_gold,
            "last_updated": last_updated,
            "ml_inventory": {
                "red_ml": total_red_ml,
                "green_ml": total_green_ml,
                "blue_ml": total_blue_ml,
                "dark_ml": total_dark_ml
            },
            "potion_inventory": {
                "custom_potions": []
            }
        }
    
        for row in potion_catalog_res:
            custom_potion = {
                "name": row.name,
                "red_component": row.red_component,
                "green_component": row.green_component,
                "blue_component": row.blue_component,
                "dark_component": row.dark_component,
                "inventory": row.inventory
            }
            audit_data["potion_inventory"]["custom_potions"].append(custom_potion)
            print(f"Custom Potion: {custom_potion}")
    
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
 

