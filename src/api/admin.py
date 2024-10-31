from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from src.api import auth
import sqlalchemy
from src import database as db

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_api_key)],
)

from fastapi import APIRouter, Depends
import sqlalchemy
from src.api import auth
from src import database as db

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_api_key)],
)

@router.post("/reset")
def reset():
    with db.engine.begin() as connection:
        connection.execute(sqlalchemy.text("DELETE FROM gold_ledger_entries"))
        connection.execute(sqlalchemy.text("DELETE FROM ml_ledger_entries"))
        connection.execute(sqlalchemy.text("DELETE FROM potion_inventory_ledger_entries"))
        connection.execute(sqlalchemy.text("DELETE FROM transactions"))
        connection.execute(sqlalchemy.text("DELETE FROM carts_items"))
        connection.execute(sqlalchemy.text("DELETE FROM carts"))
        connection.execute(sqlalchemy.text("""
            UPDATE potion_catalog
            SET inventory = 0
        """))

        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory
            SET num_green_potions = 0,
                num_blue_potions = 0,
                num_red_potions = 0,
                num_dark_potions = 0,
                num_green_ml = 0,
                num_red_ml = 0,
                num_blue_ml = 0,
                num_dark_ml = 0,
                gold = 0  -- Set to 0 since gold is tracked via ledger
        """))

        connection.execute(sqlalchemy.text("""
            INSERT INTO gold_ledger_entries (transaction_id, change, description)
            VALUES (NULL, :change, :description)
        """), {"change": 100, "description": "Initial gold balance after reset"})

    return {"message": "Shop has been reset. Inventory levels set to zero, gold balance set to 100."}



