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
    print(f"Customers visiting: {customers}")

    with db.engine.begin() as connection:
        for customer in customers:
            existing_customer = connection.execute(sqlalchemy.text("""
                SELECT id FROM customer_info
                WHERE customer_name = :customer_name
            """), {"customer_name": customer.customer_name}).fetchone()

            if existing_customer:
                connection.execute(sqlalchemy.text("""
                    UPDATE customer_info
                    SET character_class = :character_class, level = :level
                    WHERE id = :customer_id
                """), {
                    "character_class": customer.character_class,
                    "level": customer.level,
                    "customer_id": existing_customer.id
                })
                print(f"Updated customer {customer.customer_name} with new information.")
            else:
                result = connection.execute(sqlalchemy.text("""
                    INSERT INTO customer_info (customer_name, customer_class, level)
                    VALUES (:customer_name, :customer_class, :level)
                    RETURNING id
                """), {
                    "customer_name": customer.customer_name,
                    "customer_class": customer.character_class,
                    "level": customer.level
                })
                new_customer_id = result.fetchone().id
                print(f"Added new customer {customer.customer_name} with ID {new_customer_id}.")

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
            cart_id = fetched.id
            print(f"Created cart with ID: {cart_id}")
        return {"cart_id": cart_id}
    except Exception as e:
        print(f"Error creating cart: {e}")
        return {"error": "Failed to create cart."}

@router.post("/{cart_id}/items/{item_sku}")
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    try:
        with db.engine.begin() as connection:
            cart = connection.execute(sqlalchemy.text("""
                SELECT id FROM carts WHERE id = :cart_id FOR UPDATE
            """), {"cart_id": cart_id}).scalar_one()

            catalog_item_id = connection.execute(sqlalchemy.text("""
                SELECT id FROM potion_catalog WHERE sku = :item_sku FOR UPDATE
            """), {"item_sku": item_sku}).scalar_one()

            print(f"Updating cart_id {cart_id} with item_sku {item_sku} (catalog_id {catalog_item_id}) to quantity {cart_item.quantity}")

            connection.execute(sqlalchemy.text("""
                INSERT INTO carts_items (cart_id, catalog_id, quantity, sku)
                VALUES (:cart_id, :catalog_id, :quantity, :item_sku)
                ON CONFLICT (cart_id, catalog_id) DO UPDATE
                SET quantity = EXCLUDED.quantity
            """), {
                "cart_id": cart_id,
                "catalog_id": catalog_item_id,
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
    try:
        with db.engine.begin() as connection:
            cart_items = connection.execute(sqlalchemy.text("""
                SELECT ci.quantity, c.id as catalog_id, c.sku, c.price
                FROM carts_items ci
                JOIN potion_catalog c ON ci.catalog_id = c.id
                WHERE ci.cart_id = :cart_id
                FOR UPDATE
            """), {"cart_id": cart_id}).fetchall()

            if not cart_items:
                print(f"Cart {cart_id} is empty.")
                return {"error": "Cart is empty"}

            total_gold_paid = sum(item.price * item.quantity for item in cart_items)
            total_potions_bought = sum(item.quantity for item in cart_items)

            insufficient_inventory = []
            for item in cart_items:
                current_inventory = connection.execute(sqlalchemy.text("""
                    SELECT COALESCE(SUM(change), 0) as total_inventory
                    FROM potion_inventory_ledger_entries
                    WHERE potion_catalog_id = :catalog_id
                """), {"catalog_id": item.catalog_id}).scalar_one()

                if current_inventory < item.quantity:
                    insufficient_inventory.append(item.sku)

            if insufficient_inventory:
                print(f"Insufficient inventory for SKUs: {insufficient_inventory}")
                return {"error": f"Insufficient inventory for potions: {', '.join(insufficient_inventory)}"}

            transaction_id = connection.execute(sqlalchemy.text("""
                INSERT INTO transactions (description) VALUES (:description) RETURNING id
            """), {"description": f"Cart checkout {cart_id}"}).scalar_one()

            for item in cart_items:
                connection.execute(sqlalchemy.text("""
                    INSERT INTO potion_inventory_ledger_entries (potion_catalog_id, transaction_id, change, description)
                    VALUES (:catalog_id, :transaction_id, :change, :description)
                """), {
                    "catalog_id": item.catalog_id,
                    "transaction_id": transaction_id,
                    "change": -item.quantity,
                    "description": f"Sold {item.quantity} units of SKU {item.sku} from cart {cart_id}"
                })

            connection.execute(sqlalchemy.text("""
                INSERT INTO gold_ledger_entries (transaction_id, change, description)
                VALUES (:transaction_id, :change, :description)
            """), {
                "transaction_id": transaction_id,
                "change": total_gold_paid,
                "description": f"Revenue from cart checkout {cart_id}"
            })

            connection.execute(sqlalchemy.text("""
                UPDATE carts 
                SET status = 'checked_out', updated_at = CURRENT_TIMESTAMP 
                WHERE id = :cart_id
            """), {"cart_id": cart_id})

            #connection.execute(sqlalchemy.text("""
            #    DELETE FROM carts_items WHERE cart_id = :cart_id
           # """), {"cart_id": cart_id})

            new_gold = connection.execute(sqlalchemy.text("""
                SELECT COALESCE(SUM(change), 0) as gold_total FROM gold_ledger_entries
            """)).scalar()

        print("Checkout successful")
        print(f"The total gold paid is: {total_gold_paid}")
        print(f"The remaining gold is: {new_gold}")

        return {
            "total_gold_paid": total_gold_paid,
            "total_potion_bought": total_potions_bought
        }
    except Exception as e:
        print(f"Error during checkout: {e}")
        return {"error": "Checkout failed due to an internal error."}
