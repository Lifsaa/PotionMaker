from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from src.api import auth
from typing import List
from enum import Enum
import sqlalchemy
from src import database as db

router = APIRouter(
    prefix="/carts",
    tags=["cart"],
    dependencies=[Depends(auth.get_api_key)],
)

class search_sort_options(str, Enum):
    customer_name = "customer_name"
    item_sku = "item_sku"
    line_item_total = "line_item_total"
    timestamp = "timestamp"

class search_sort_order(str, Enum):
    asc = "asc"
    desc = "desc"   

@router.get("/search/", tags=["search"])
def search_orders(
    customer_name: str = "",
    potion_sku: str = "",
    search_page: str = "",
    sort_col: search_sort_options = search_sort_options.timestamp,
    sort_order: search_sort_order = search_sort_order.desc,
):
    """
    Search for cart line items by customer name and/or potion sku.

    Customer name and potion sku filter to orders that contain the 
    string (case insensitive). If the filters aren't provided, no
    filtering occurs on the respective search term.

    Search page is a cursor for pagination. The response to this
    search endpoint will return previous or next if there is a
    previous or next page of results available. The token passed
    in that search response can be passed in the next search request
    as search page to get that page of results.

    Sort col is which column to sort by and sort order is the direction
    of the search. They default to searching by timestamp of the order
    in descending order.

    The response itself contains a previous and next page token (if
    such pages exist) and the results as an array of line items. Each
    line item contains the line item id (must be unique), item sku, 
    customer name, line item total (in gold), and timestamp of the order.
    Your results must be paginated, the max results you can return at any
    time is 5 total line items.
    """

    return {
        "previous": "",
        "next": "",
        "results": [
            {
                "line_item_id": 1,
                "item_sku": "1 oblivion potion",
                "customer_name": "Scaramouche",
                "line_item_total": 50,
                "timestamp": "2021-01-01T00:00:00Z",
            }
        ],
    }


class Customer(BaseModel):
    customer_name: str
    character_class: str
    level: int

@router.post("/visits/{visit_id}")
def post_visits(visit_id: int, customers: list[Customer]):
    """
    Which customers visited the shop today?
    """
    print(customers)

    return "OK"


@router.post("/")
def create_cart(new_cart: Customer):
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("SELECT num_green_potions, gold FROM global_inventory WHERE id = 1")).fetchone()
        
        # Check if result is None before accessing its attributes
        if result is not None:
            num_green_potions = result.num_green_potions
            gold = result.gold
        else:
            num_green_potions = 0
            gold = 0  # Set a default value or handle as per your logic
        
        if num_green_potions <= 0:
            return {"error": "Insufficient potions available in inventory to create a cart"}
        if gold < 10:
            return {"error": "Insufficient gold to proceed"}

        return {"cart_id": 1}



class CartItem(BaseModel):
    quantity: int


@router.post("/{cart_id}/items/{item_sku}")
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("SELECT num_green_potions FROM global_inventory WHERE id = 1")).fetchone()
        
        # Correct the condition to check if result is not None
        num_green_potions = result.num_green_potions if result is not None else 0
        
        if cart_item.quantity > num_green_potions:
            return {"error": f"Requested quantity exceeds available inventory. Only {num_green_potions} potions are available."}
    return {"status": "Item quantity updated successfully"}


class CartCheckout(BaseModel):
    payment: str

@router.post("/{cart_id}/checkout")
def checkout(cart_id: int, cart_checkout: CartCheckout):
     with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("SELECT num_green_potions FROM global_inventory WHERE id = 1")).fetchone()
        num_green_potions = result.num_green_potions if result is not None else 0

        if num_green_potions > 0:
            connection.execute(sqlalchemy.text(
                "UPDATE global_inventory SET num_green_potions = num_green_potions - 1 WHERE id = 1"
            ))
            total_potions_bought = 1
            total_gold_paid = 10
        else:
            total_potions_bought = 0
            total_gold_paid = 0
        
        if total_potions_bought > 0:
            return {"total_potions_bought": total_potions_bought, "total_gold_paid": total_gold_paid}
        else: return {"error":"No potions were bought"}
