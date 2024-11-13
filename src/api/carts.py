from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from src.api import auth
from typing import List
from enum import Enum
import sqlalchemy
from src import database as db
from sqlalchemy import select, and_, or_, func, desc, asc,String
import json
import base64
from datetime import datetime
from src.database import engine, customer_info, potion_catalog, carts, carts_items


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
    MAX_RESULTS = 5 

    try:
        page = int(search_page) if search_page else 1
        if page < 1:
            page = 1
    except (ValueError, TypeError):
        page = 1

    offset = (page - 1) * MAX_RESULTS

    line_item_id_expr = (carts_items.c.cart_id * 100000 + carts_items.c.catalog_id).label('line_item_id')

    item_sku_expr = func.concat(
        carts_items.c.quantity.cast(String),
        ' x ',
        potion_catalog.c.name
    ).label('item_sku')

    line_item_total_expr = (carts_items.c.quantity * potion_catalog.c.price).label('line_item_total')

    query = select(
        line_item_id_expr,
        item_sku_expr,
        customer_info.c.customer_name,
        line_item_total_expr,
        carts.c.created_at.label('timestamp')
    ).select_from(
        carts_items
        .join(carts, carts_items.c.cart_id == carts.c.id)
        .join(potion_catalog, carts_items.c.catalog_id == potion_catalog.c.id)
        .join(customer_info, carts.c.customer_id == customer_info.c.id)
    )

    if customer_name:
        query = query.where(customer_info.c.customer_name.ilike(f"%{customer_name}%"))
    if potion_sku:
        query = query.where(potion_catalog.c.sku.ilike(f"%{potion_sku}%"))

    sort_col_mapping = {
        "customer_name": customer_info.c.customer_name,
        "item_sku": item_sku_expr,
        "line_item_total": line_item_total_expr,
        "timestamp": carts.c.created_at
    }
    sort_column = sort_col_mapping.get(sort_col.value, carts.c.created_at)

    if sort_order == search_sort_order.asc:
        query = query.order_by(asc(sort_column), asc(line_item_id_expr))
    else:
        query = query.order_by(desc(sort_column), desc(line_item_id_expr))

    query = query.limit(MAX_RESULTS + 1).offset(offset)

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    has_next = len(rows) > MAX_RESULTS
    if has_next:
        rows = rows[:MAX_RESULTS]

    results = []
    for row in rows:
        timestamp_str = row.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')  
        result_item = {
            "line_item_id": row.line_item_id,
            "item_sku": row.item_sku,
            "customer_name": row.customer_name,
            "line_item_total": int(row.line_item_total),
            "timestamp": timestamp_str
        }
        results.append(result_item)

    base_path = "/carts/search/"

    query_params = f"customer_name={customer_name}&potion_sku={potion_sku}&sort_col={sort_col.value}&sort_order={sort_order.value}"

    next_link = ""
    if has_next:
        next_page = page + 1
        next_link = f"{base_path}?{query_params}&search_page={next_page}"

    previous_link = ""
    if page > 1:
        prev_page = page - 1
        previous_link = f"{base_path}?{query_params}&search_page={prev_page}"

    return {
        "previous": previous_link,
        "next": next_link,
        "results": results
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
                    SET customer_class = :customer_class, level = :level
                    WHERE id = :customer_id
                """), {
                    "customer_class": customer.character_class,
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
    Create a new cart and set the status to 'active', associating it with an existing customer_id.
    """
    try:
        with db.engine.begin() as connection:
            customer = connection.execute(
                sqlalchemy.text("SELECT id FROM customer_info LIMIT 1")
            ).fetchone()

            if not customer:
                print("No customers found. Please add a customer first.")
                return {"error": "No customers available. Please add a customer first."}

            customer_id = customer.id

            result = connection.execute(
                sqlalchemy.text("""
                    INSERT INTO carts (status, customer_id) 
                    VALUES ('active', :customer_id) 
                    RETURNING id
                """),
                {"customer_id": customer_id}
            )
            fetched = result.fetchone()
            cart_id = fetched.id
            print(f"Created cart with ID: {cart_id} for customer_id {customer_id}")
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
            "total_potions_bought": total_potions_bought
        }
    except Exception as e:
        print(f"Error during checkout: {e}")
        return {"error": "Checkout failed due to an internal error."}
