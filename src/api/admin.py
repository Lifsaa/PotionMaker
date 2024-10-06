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

@router.post("/reset")
def reset():
    with db.engine.begin() as connection:
        connection.execute(sqlalchemy.text("""UPDATE global_inventory
                                           SET num_green_potions = 0,
                                           num_blue_potions = 0,
                                           num_green_ml  = 0,
                                           num_red_potions  = 0,
                                           num_red_ml = 0,
                                           num_blue_ml  = 0,
                                           gold = 100
                                           """  
                                           ))
    return {"message":"Shop has been reset to 0 for inventory and 100 for gold"}

