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
def post_visits(visit_id: int, customers: List[Customer]):
    """
    Which customers visited the shop today?
    """
    print(f"Visit ID: {visit_id}")
    print("Customers:")
    for customer in customers:
        print(f"- {customer.customer_name}, Class: {customer.character_class}, Level: {customer.level}")
    return "OK"


carts = {}
next_cart_id = 1

@router.post("/")
def create_cart():
    global next_cart_id
    cart_id = next_cart_id
    next_cart_id += 1
    carts[cart_id] = {}
    print(f"Created cart with ID: {cart_id}")
    return {"cart_id": cart_id}


class CartItem(BaseModel):
    quantity: int

@router.post("/{cart_id}/items/{item_sku}")
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    if cart_id not in carts:
        return {"error": "Cart not found"}
    quantity = cart_item.quantity
    carts[cart_id][item_sku] = quantity
    if quantity:
        print(f"Great! now the potion quantity is {quantity}") 
    else:
        print("No change was made")
    return {"success": True}


class CartCheckout(BaseModel):
    payment: str

@router.post("/{cart_id}/checkout")
def checkout(cart_id: int, cart_checkout: CartCheckout):
    print(f"Payment is = {cart_checkout.payment} gold")
    if cart_id not in carts:
        return {"error": "Cart not found"}
    cart_items = carts[cart_id]
    if not cart_items:
        return {}
    total_potions_bought = 0
    total_gold_paid = 0
    potion_prices = {
        "GREEN_POTION": 60,
        "RED_POTION": 55,
        "BLUE_POTION": 35
    }
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text(
                "SELECT num_green_potions, num_red_potions, num_blue_potions, gold FROM global_inventory"
            )
        )
        inventory = result.fetchone()

        new_inventory = {
            "GREEN_POTION": inventory.num_green_potions,
            "RED_POTION": inventory.num_red_potions,
            "BLUE_POTION": inventory.num_blue_potions
        }
        new_gold = inventory.gold

        for item_sku, quantity in cart_items.items():
            if item_sku in new_inventory:
                new_inventory[item_sku] -= quantity
                total_gold_paid += potion_prices[item_sku] * quantity
                total_potions_bought += quantity

        new_gold += total_gold_paid
        connection.execute(
            sqlalchemy.text(
                """
                UPDATE global_inventory 
                SET num_green_potions = :green_potions, 
                    num_red_potions = :red_potions, 
                    num_blue_potions = :blue_potions,
                    gold = :gold
                """
            ),
            {
                "green_potions": new_inventory['GREEN_POTION'],
                "red_potions": new_inventory['RED_POTION'],
                "blue_potions": new_inventory['BLUE_POTION'],
                "gold": new_gold
            }
        )
    del carts[cart_id]
    return {"total_potions_bought": total_potions_bought, "total_gold_paid": total_gold_paid}

