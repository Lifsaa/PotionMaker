from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from src.api import auth
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


class Customer(BaseModel):
    customer_name: str
    character_class: str
    level: int

# used for global list of carts
# items : list of tuples of (potion_sku, quantity)
class Cart(BaseModel):  
    cart_id: int = None
    items: list[tuple] = []
    customer: Customer = None

# global list of carts
carts_array: list[Cart] = []


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


# class Customer(BaseModel):
#     customer_name: str
#     character_class: str
#     level: int

@router.post("/visits/{visit_id}")
def post_visits(visit_id: int, customers: list[Customer]):
    print("CALLED post_visits()")
    """
    Which customers visited the shop today?
    """
    print(customers)

    return "OK"


@router.post("/")
def create_cart(new_cart: Customer):
    print("CALLED create_cart()")
    """ """

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text(f"""INSERT INTO carts (
                                                        customer_name,
                                                        character_class,
                                                        level
                                                    )  
                                                    VALUES (:name, :class, :level)
                                                    RETURNING id"""),
                                                    [{"name": new_cart.customer_name, 
                                                      "class": new_cart.character_class, 
                                                      "level": new_cart.level}])
        
    return {"cart_id": result.fetchone().id}


class CartItem(BaseModel):
    quantity: int


@router.post("/{cart_id}/items/{item_sku}")
def set_item_quantity(cart_id: int, item_sku: str, cart_item: CartItem):
    print("CALLED set_item_quantity()")
    """ """

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text(f"""SELECT id
                                                    FROM potions_catalog
                                                    WHERE sku = :item_sku"""),
                                                    [{"item_sku": item_sku}])
    potion_id = result.fetchone().id 

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text(f"""INSERT INTO cart_items (
                                                        cart_id,
                                                        potion_id,
                                                        quantity
                                                    )  
                                                    VALUES (:cart_id, :potion_id, :quantity)
                                                    RETURNING id"""),
                                                    [{"cart_id": cart_id, 
                                                      "potion_id": potion_id, 
                                                      "quantity": cart_item.quantity}])

    return "OK"


class CartCheckout(BaseModel):
    payment: str

@router.post("/{cart_id}/checkout")
def checkout(cart_id: int, cart_checkout: CartCheckout):
    print("CALLED checkout()")

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""SELECT sku, id, price
                                                    FROM potions_catalog"""))
    potion_skus = {}
    for row in result:
        potion_skus[row.id] = [row.sku, row.price]

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""SELECT *
                                                    FROM cart_items
                                                    WHERE cart_id = :cart_id"""),
                                                    [{"cart_id": cart_id}])
        
    total_num_potions = total_gains = 0
    for item in result:
        total_num_potions += item.quantity
        total_gains += potion_skus[item.potion_id][1] * item.quantity

        quantity = -1 * item.quantity

        with db.engine.begin() as connection:
            result = connection.execute(sqlalchemy.text("""INSERT INTO potions_inventory (
                                                                order_id,
                                                                sku,
                                                                num_potions
                                                        )
                                                        VALUES (:order_id, 
                                                                :sku, 
                                                                :num_potions)
                                                        """),
                                                        [{"order_id": cart_id,
                                                        "sku": potion_skus[item.potion_id][0],
                                                        "num_potions": quantity}])

    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""INSERT INTO ledgerized_inventory (
                                                        order_id,
                                                        order_type,
                                                        gold,
                                                        num_red_ml,
                                                        num_green_ml,
                                                        num_blue_ml,
                                                        num_dark_ml
                                                    )
                                                    VALUES (:order_id,
                                                            :order_type, 
                                                            :gold, 
                                                            :red_ml, 
                                                            :green_ml, 
                                                            :blue_ml, 
                                                            :dark_ml)
                                                    """),
                                                    [{"order_id": cart_id,
                                                      "order_type": "customer",
                                                      "gold": total_gains,
                                                      "red_ml": 0,
                                                      "green_ml": 0,
                                                      "blue_ml": 0,
                                                      "dark_ml": 0}])


    # for logging
    with db.engine.begin() as connection:
        result = connection.execute(sqlalchemy.text("""SELECT *
                                                    FROM carts
                                                    WHERE id = :cart_id"""),
                                                    [{"cart_id": cart_id}])
    cart = result.fetchone()
    print(f"Cart {cart_id} successfully purchased {total_num_potions} potions and paid {total_gains} gold.\nCustomer Name: {cart.customer_name}, Customer Class: {cart.character_class}, Level: {cart.level}")

    return {"total_potions_bought": total_num_potions, "total_gold_paid": total_gains}
