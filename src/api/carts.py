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
    try:
        with db.engine.begin() as connection:
            result = connection.execute(
                sqlalchemy.text("INSERT INTO carts (status) VALUES ('active') RETURNING id")
            )
            fetched = result.fetchone()
            if fetched is None:
                raise ValueError("Failed to create cart: No ID returned.")
            cart_id = fetched.id
            print(f"Created cart with ID: {cart_id}")
        return {"cart_id": cart_id}
    except Exception as e:
        print(f"Error creating cart: {e}")
        return {"error": "Failed to create cart."}




@router.post("/{cart_id}/items/{item_sku}")
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    """
    Updates the quantity of a specific item in the cart.
    """
    try:
        with db.engine.begin() as connection:
            cart = connection.execute(sqlalchemy.text("""
                SELECT id FROM carts WHERE id = :cart_id FOR UPDATE
            """), {"cart_id": cart_id}).fetchone()

            if cart is None:
                print(f"Cart with ID {cart_id} not found.")
                return {"error": "Cart not found."}

            catalog_item = connection.execute(sqlalchemy.text("""
                SELECT id, inventory FROM potion_catalog WHERE sku = :item_sku FOR UPDATE
            """), {"item_sku": item_sku}).fetchone()

            if catalog_item is None:
                print(f"Item with SKU {item_sku} not found in catalog.")
                return {"error": "Item not found in catalog."}

            catalog_id = catalog_item.id
            print(f"Updating cart_id {cart_id} with item_sku {item_sku} (catalog_id {catalog_id}) to quantity {cart_item.quantity}")

            connection.execute(sqlalchemy.text("""
                INSERT INTO carts_items (cart_id, catalog_id, quantity, sku)
                VALUES (:cart_id, :catalog_id, :quantity, :item_sku)
                ON CONFLICT (cart_id, catalog_id) DO UPDATE
                SET quantity = EXCLUDED.quantity
            """), {
                "cart_id": cart_id,
                "catalog_id": catalog_id,
                "quantity": cart_item.quantity,
                "item_sku": item_sku
            })

            print(f"Set quantity for SKU {item_sku} in cart {cart_id} to {cart_item.quantity}")

        return {"success": True}
    except Exception as e:
        print(f"Error setting item quantity: {e}")
        return {"error": "Failed to set item quantity."}





class CartCheckout(BaseModel):
    payment: str

@router.post("/{cart_id}/checkout")
def checkout(cart_id: int, cart_checkout: CartCheckout):
    """
    Process the cart checkout, deduct potion inventory from potion_catalog, update gold, and finalize the cart.
    """
    try:
        with db.engine.begin() as connection:
            cart_items = connection.execute(sqlalchemy.text("""
                SELECT ci.quantity, c.id as catalog_id, c.sku, c.price, c.inventory
                FROM carts_items ci
                JOIN potion_catalog c ON ci.catalog_id = c.id
                WHERE ci.cart_id = :cart_id
                FOR UPDATE
            """), {"cart_id": cart_id}).fetchall()

            if not cart_items:
                print(f"Cart {cart_id} is empty.")
                return {"error": "Cart is empty"}

            print(f"Cart {cart_id} items: {cart_items}")

            total_gold_paid = sum(item.price * item.quantity for item in cart_items)
            print(f"Total gold to be paid: {total_gold_paid}")

            insufficient_inventory = [item for item in cart_items if item.inventory < item.quantity]
            if insufficient_inventory:
                insufficient_skus = [item.sku for item in insufficient_inventory]
                print(f"Insufficient inventory for SKUs: {insufficient_skus}")
                return {"error": f"Insufficient inventory for potions: {', '.join(insufficient_skus)}"}

            for item in cart_items:
                print(f"Deducting {item.quantity} from inventory of SKU {item.sku} (ID {item.catalog_id})")
                connection.execute(sqlalchemy.text("""
                    UPDATE potion_catalog
                    SET inventory = inventory - :quantity
                    WHERE id = :catalog_id
                """), {"quantity": item.quantity, "catalog_id": item.catalog_id})

            result = connection.execute(sqlalchemy.text("""
                UPDATE global_inventory
                SET gold = gold + :total_gold_paid, last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
                RETURNING gold
            """), {"total_gold_paid": total_gold_paid}).fetchone()

            if result is None:
                print("Failed to update gold in global_inventory.")
                raise ValueError("Global inventory not found.")

            new_gold = result.gold
            print(f"Updated gold in global_inventory: {new_gold}")

            connection.execute(sqlalchemy.text("""
                UPDATE carts 
                SET status = 'checked_out', updated_at = CURRENT_TIMESTAMP 
                WHERE id = :cart_id
            """), {"cart_id": cart_id})
            print(f"Cart {cart_id} status updated to 'checked_out'.")

            connection.execute(sqlalchemy.text("""
                DELETE FROM carts_items WHERE cart_id = :cart_id
            """), {"cart_id": cart_id})
            print(f"Cart {cart_id} items cleared.")

        return {
            "message": "Checkout successful",
            "total_gold_paid": total_gold_paid,
            "remaining_gold": new_gold
        }
    except Exception as e:
        print(f"Error during checkout: {e}")
        return {"error": "Checkout failed due to an internal error."}
