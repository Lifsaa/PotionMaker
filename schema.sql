CREATE TABLE potion_catalog (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    red_component INT,
    green_component INT,
    blue_component INT,
    dark_component INT,
    price INT NOT NULL,
    quantity INT NOT NULL,
    sku TEXT UNIQUE NOT NULL,
    inventory INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (red_component, green_component, blue_component, dark_component)
);


CREATE TABLE global_inventory (
    id SERIAL PRIMARY KEY,
    num_red_ml INT,
    num_green_ml INT,
    num_blue_ml INT,
    num_dark_ml INT,
    num_red_potions INT NOT NULL,
    num_green_potions INT NOT NULL,
    num_blue_potions INT NOT NULL,
    num_dark_potions INT NOT NULL,
    gold INT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE customer_info (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    customer_name TEXT NOT NULL,
    customer_class TEXT NOT NULL,
    level INT NOT NULL
);

CREATE TABLE carts (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active'
);

CREATE TABLE carts_items (
    cart_id INT NOT NULL,
    catalog_id INT NOT NULL,
    quantity INT NOT NULL,
    sku TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (cart_id, catalog_id),
    FOREIGN KEY (cart_id) REFERENCES carts(id) ON DELETE CASCADE,
    FOREIGN KEY (catalog_id) REFERENCES potion_catalog(id)
);
