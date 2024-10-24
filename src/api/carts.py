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
    Log customer visits and save them to the customer_info table if they don't already exist.
    """
    print(f"Visit ID: {visit_id}")
    """
    Which customers visited the shop today?
    """
    print(customers)
    return {"message": "Visit logged successfully"}


class CartItem(BaseModel):
    quantity: int


@router.post("/")
def create_cart():
    """
    Create a new cart and set the status to 'active'.
    """
    with db.engine.begin() as connection:
        result = connection.execute(
            sqlalchemy.text("INSERT INTO carts (status) VALUES ('active') RETURNING id")
        )
        cart_id = result.fetchone().id
    return {"cart_id": cart_id}



@router.post("/{cart_id}/items/{item_sku}")
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    """
    Updates the quantity of a specific item in the cart.
    """
    with db.engine.begin() as connection:
        catalog_item = connection.execute(sqlalchemy.text("""
            SELECT id, inventory FROM potion_catalog WHERE sku = :item_sku
        """), {"item_sku": item_sku}).fetchone()

        if catalog_item is None:
            return {"error": "Item not found in catalog."}

        catalog_id = catalog_item.id

        existing_item = connection.execute(sqlalchemy.text("""
            SELECT quantity FROM carts_items
            WHERE cart_id = :cart_id AND catalog_id = :catalog_id
        """), {"cart_id": cart_id, "catalog_id": catalog_id}).fetchone()

        if existing_item:
            connection.execute(sqlalchemy.text("""
                UPDATE carts_items
                SET quantity = :quantity
                WHERE cart_id = :cart_id AND catalog_id = :catalog_id
            """), {"quantity": cart_item.quantity, "cart_id": cart_id, "catalog_id": catalog_id})
        else:
            connection.execute(sqlalchemy.text("""
                INSERT INTO carts_items (cart_id, catalog_id, quantity, sku)
                VALUES (:cart_id, :catalog_id, :quantity, :item_sku)
            """), {"cart_id": cart_id, "catalog_id": catalog_id, "quantity": cart_item.quantity, "item_sku": item_sku})
    return {"success": True}



class CartCheckout(BaseModel):
    payment: str

@router.post("/{cart_id}/checkout")
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Process the cart checkout, deduct potion inventory from potion_catalog, update gold, and finalize the cart.
    """
    with db.engine.begin() as connection:
        cart_items = connection.execute(sqlalchemy.text("""
            SELECT ci.quantity, c.sku, c.price, c.inventory
            FROM carts_items ci
            JOIN potion_catalog c ON ci.catalog_id = c.id
            WHERE ci.cart_id = :cart_id
        """), {"cart_id": cart_id}).fetchall()

        if not cart_items:
            return {"error": "Cart is empty"}

        print(f"Cart ID: {cart_id}")
        for item in cart_items:
            print(f"Potion SKU: {item.sku}, Quantity: {item.quantity}, Inventory: {item.inventory}, Price: {item.price}")

        total_gold_paid = 0
        for item in cart_items:
            quantity = item.quantity
            if item.inventory < quantity:
                print(f"Insufficient potion inventory for {item.sku}, Available: {item.inventory}, Needed: {quantity}")
                return {"error": f"Insufficient potion inventory for {item.sku}"}
            total_gold_paid += item.price * quantity

        global_inventory = connection.execute(sqlalchemy.text("""
            SELECT gold FROM global_inventory WHERE id = 1
        """)).fetchone()

        current_gold = global_inventory.gold

        for item in cart_items:
            connection.execute(sqlalchemy.text("""
                UPDATE potion_catalog
                SET inventory = inventory - :quantity
                WHERE sku = :sku
            """), {"quantity": item.quantity, "sku": item.sku})
            

        new_gold = current_gold + total_gold_paid
        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory
            SET gold = :new_gold, last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
        """), {"new_gold": new_gold})

        connection.execute(sqlalchemy.text("""
            DELETE FROM carts_items WHERE cart_id = :cart_id
        """), {"cart_id": cart_id})

        connection.execute(sqlalchemy.text("""
            UPDATE carts SET status = 'checked_out' WHERE id = :cart_id
        """), {"cart_id": cart_id})

    return {"message": "Checkout successful", "total_gold_paid": total_gold_paid, "remaining_gold": new_gold}
