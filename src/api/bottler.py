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
def post_deliver_bottles(potions_delivered: list[PotionInventory], order_id: int):
    """
    Update potion inventory based on delivered potions dynamically.
    Handles both pure and custom potions.
    """
    with db.engine.begin() as connection:
        # Fetch ml from global_inventory
        global_inventory = connection.execute(sqlalchemy.text("""
            SELECT num_red_ml, num_green_ml, num_blue_ml, num_dark_ml
            FROM global_inventory
        """)).fetchone()

        inventory = {
            "red_ml": global_inventory.num_red_ml,
            "green_ml": global_inventory.num_green_ml,
            "blue_ml": global_inventory.num_blue_ml,
            "dark_ml": global_inventory.num_dark_ml
        }

        for potion in potions_delivered:
            # Dynamically fetch the potion recipe from potion_catalog
            potion_recipe = connection.execute(sqlalchemy.text("""
                SELECT red_component, green_component, blue_component, dark_component, inventory
                FROM potion_catalog
                WHERE red_component = :red AND green_component = :green AND blue_component = :blue AND dark_component = :dark
            """), {
                "red": potion.potion_type[0],
                "green": potion.potion_type[1],
                "blue": potion.potion_type[2],
                "dark": potion.potion_type[3]
            }).fetchone()

            if not potion_recipe:
                return {"error": f"Invalid potion mix {potion.potion_type}"}

            # Deduct ml from global inventory
            inventory["red_ml"] -= potion_recipe.red_component * potion.quantity
            inventory["green_ml"] -= potion_recipe.green_component * potion.quantity
            inventory["blue_ml"] -= potion_recipe.blue_component * potion.quantity
            inventory["dark_ml"] -= potion_recipe.dark_component * potion.quantity

            # Update the potion inventory in potion_catalog (for custom potions like Lumiere)
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

        # Update global inventory ml counts
        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory
            SET num_red_ml = :red_ml, num_green_ml = :green_ml, num_blue_ml = :blue_ml, num_dark_ml = :dark_ml
        """), inventory)

    return {"message": "Inventory updated successfully"}


@router.post("/plan")
def get_bottle_plan():
    """
    Get the bottling plan based on available ml in the inventory.
    Supports custom potion types dynamically.
    """
    with db.engine.begin() as connection:
        # Fetch available ml from global_inventory
        global_inventory = connection.execute(sqlalchemy.text("""
            SELECT num_red_ml, num_green_ml, num_blue_ml, num_dark_ml
            FROM global_inventory
        """)).fetchone()

        inventory = {
            "red_ml": global_inventory.num_red_ml,
            "green_ml": global_inventory.num_green_ml,
            "blue_ml": global_inventory.num_blue_ml,
            "dark_ml": global_inventory.num_dark_ml
        }

        # Fetch all potion recipes
        potion_recipes = connection.execute(sqlalchemy.text("""
            SELECT id, red_component, green_component, blue_component, dark_component
            FROM potion_catalog
        """)).fetchall()

        potion_plan = []

        # Plan how many potions can be made for each recipe based on available ml
        for recipe in potion_recipes:
            red_ml_required = recipe.red_component
            green_ml_required = recipe.green_component
            blue_ml_required = recipe.blue_component
            dark_ml_required = recipe.dark_component

            # Calculate how many potions can be made based on available ml
            max_potions = min(
                inventory["red_ml"] // red_ml_required if red_ml_required > 0 else float('inf'),
                inventory["green_ml"] // green_ml_required if green_ml_required > 0 else float('inf'),
                inventory["blue_ml"] // blue_ml_required if blue_ml_required > 0 else float('inf'),
                inventory["dark_ml"] // dark_ml_required if dark_ml_required > 0 else float('inf'),
            )

            if max_potions > 0:
                potion_plan.append({
                    "potion_id": recipe.id,
                    "potion_type": [recipe.red_component, recipe.green_component, recipe.blue_component, recipe.dark_component],
                    "quantity": max_potions
                })

    return potion_plan if potion_plan else []

if __name__ == "__main__":
    print(get_bottle_plan())
