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

CREATE TABLE gold_ledger_entries (
    id SERIAL PRIMARY KEY,
    transaction_id INT,
    change INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

CREATE TABLE ml_ledger_entries (
    id SERIAL PRIMARY KEY,
    transaction_id INT,
    red_ml_change INT DEFAULT 0,
    green_ml_change INT DEFAULT 0,
    blue_ml_change INT DEFAULT 0,
    dark_ml_change INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

CREATE TABLE potion_inventory_ledger_entries (
    id SERIAL PRIMARY KEY,
    potion_catalog_id INT NOT NULL REFERENCES potion_catalog(id),
    transaction_id INT,
    change INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);
CREATE TABLE capacity_purchases (
    id SERIAL PRIMARY KEY,
    transaction_id INT REFERENCES transactions(id),
    potion_capacity INT DEFAULT 0,
    ml_capacity INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
