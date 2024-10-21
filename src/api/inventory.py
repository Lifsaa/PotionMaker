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
def get_inventory():
    """
    Audit the current inventory, including total number of potions, ml in barrels, and available gold.
    """
    with db.engine.begin() as connection:
        inventory = connection.execute(sqlalchemy.text("""
            SELECT num_red_potions, num_green_potions, num_blue_potions, num_dark_potions,
                   num_red_ml, num_green_ml, num_blue_ml, num_dark_ml, gold
            FROM global_inventory
        """)).fetchone()

        custom_potions = connection.execute(sqlalchemy.text("""
            SELECT SUM(inventory) AS total_custom_potions,
                   SUM(red_component * inventory) AS red_ml,
                   SUM(green_component * inventory) AS green_ml,
                   SUM(blue_component * inventory) AS blue_ml,
                   SUM(dark_component * inventory) AS dark_ml
            FROM potion_catalog
        """)).fetchone()

        total_potions = (
            inventory.num_red_potions + inventory.num_green_potions +
            inventory.num_blue_potions + inventory.num_dark_potions +
            custom_potions.total_custom_potions
        )

        total_ml = (
            inventory.num_red_ml + inventory.num_green_ml +
            inventory.num_blue_ml + inventory.num_dark_ml +
            custom_potions.red_ml + custom_potions.green_ml +
            custom_potions.blue_ml + custom_potions.dark_ml
        )

        return {
            "number_of_potions": total_potions,
            "ml_in_barrels": total_ml,
            "gold": inventory.gold
        }


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
 

