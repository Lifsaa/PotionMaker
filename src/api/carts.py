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
    with db.engine.begin() as connection:
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



@router.post("/{cart_id}/items/{catalog_id}")
def set_item_quantity(cart_id: int, catalog_id: int, cart_item: CartItem):
    """
    Add or update an item in the cart by setting its quantity.
    """
    with db.engine.begin() as connection:
        # Fetch the SKU from potion_catalog
        sku = connection.execute(sqlalchemy.text("""
            SELECT sku FROM potion_catalog WHERE id = :catalog_id
        """), {"catalog_id": catalog_id}).fetchone().sku

        connection.execute(
            sqlalchemy.text("""
                INSERT INTO carts_items (cart_id, catalog_id, quantity, sku)
                VALUES (:cart_id, :catalog_id, :quantity, :sku)
                ON CONFLICT (cart_id, catalog_id)
                DO UPDATE SET quantity = :quantity
            """),
            {"cart_id": cart_id, "catalog_id": catalog_id, "quantity": cart_item.quantity, "sku": sku}
        )

    return {"success": True}




class CartCheckout(BaseModel):
    payment: str


@router.post("/{cart_id}/checkout")
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Process the cart checkout, deduct potion inventory from potion_catalog, and finalize the cart.
    """
    with db.engine.begin() as connection:
        # Fetch cart items and potion details
        cart_items = connection.execute(sqlalchemy.text("""
            SELECT ci.quantity, c.sku, c.price, c.inventory, c.red_component, c.green_component, c.blue_component, c.dark_component
            FROM carts_items ci
            JOIN potion_catalog c ON ci.catalog_id = c.id
            WHERE ci.cart_id = :cart_id
        """), {"cart_id": cart_id}).fetchall()

        # Print cart items for debugging
        print(f"Cart ID: {cart_id}")
        for item in cart_items:
            print(f"Potion SKU: {item.sku}, Quantity: {item.quantity}, Inventory: {item.inventory}, Price: {item.price}")
            print(f"Potion Components - Red: {item.red_component}, Green: {item.green_component}, Blue: {item.blue_component}, Dark: {item.dark_component}")

        # Fetch the current ml inventory and gold
        inventory = connection.execute(sqlalchemy.text("""
            SELECT num_red_ml, num_green_ml, num_blue_ml, num_dark_ml, gold
            FROM global_inventory
        """)).fetchone()

        # Print global inventory for debugging
        print(f"Global Inventory - Red ML: {inventory.num_red_ml}, Green ML: {inventory.num_green_ml}, Blue ML: {inventory.num_blue_ml}, Dark ML: {inventory.num_dark_ml}")
        print(f"Gold: {inventory.gold}")

        total_gold_paid = 0

        # Process each item in the cart
        for item in cart_items:
            quantity = item.quantity
            red_ml_needed = item.red_component * quantity
            green_ml_needed = item.green_component * quantity
            blue_ml_needed = item.blue_component * quantity
            dark_ml_needed = item.dark_component * quantity

            # Check if there is enough ml in the inventory
            if (inventory.num_red_ml < red_ml_needed or
                inventory.num_green_ml < green_ml_needed or
                inventory.num_blue_ml < blue_ml_needed or
                inventory.num_dark_ml < dark_ml_needed):
                print(f"Insufficient ml inventory for potion {item.sku}")
                return {"error": f"Insufficient ml inventory for potion {item.sku}"}

            # Check if there is enough potion inventory for custom potions
            if item.inventory < quantity:
                print(f"Insufficient potion inventory for {item.sku}, Available: {item.inventory}, Needed: {quantity}")
                return {"error": f"Insufficient potion inventory for {item.sku}"}

            # Calculate total cost of the potion
            total_gold_paid += item.price * quantity

        # Ensure the payment matches the total cost
        if int(cart_checkout.payment) != total_gold_paid:
            print(f"Incorrect payment: Received {cart_checkout.payment}, Expected {total_gold_paid}")
            return {"error": "Incorrect payment amount"}

        # Deduct the used ml from global_inventory and add the gold
        connection.execute(sqlalchemy.text("""
            UPDATE global_inventory
            SET num_red_ml = num_red_ml - :red_ml,
                num_green_ml = num_green_ml - :green_ml,
                num_blue_ml = num_blue_ml - :blue_ml,
                num_dark_ml = num_dark_ml - :dark_ml,
                gold = gold + :gold
        """), {
            "red_ml": sum(item.red_component * item.quantity for item in cart_items),
            "green_ml": sum(item.green_component * item.quantity for item in cart_items),
            "blue_ml": sum(item.blue_component * item.quantity for item in cart_items),
            "dark_ml": sum(item.dark_component * item.quantity for item in cart_items),
            "gold": total_gold_paid
        })

        # Deduct the potion inventory from potion_catalog for custom potions
        for item in cart_items:
            connection.execute(sqlalchemy.text("""
                UPDATE potion_catalog
                SET inventory = inventory - :quantity
                WHERE sku = :sku
            """), {"quantity": item.quantity, "sku": item.sku})

        # Clear the cart and mark it as checked out
        connection.execute(sqlalchemy.text("""
            DELETE FROM carts_items WHERE cart_id = :cart_id
        """), {"cart_id": cart_id})

        connection.execute(sqlalchemy.text("""
            UPDATE carts SET status = 'checked_out' WHERE id = :cart_id
        """), {"cart_id": cart_id})

    return {"message": "Checkout successful", "total_gold_paid": total_gold_paid}
