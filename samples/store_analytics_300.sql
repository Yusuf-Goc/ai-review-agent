-- Store analytics SQL sample with intentional bugs for AI code reviewer tests.
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    city VARCHAR(80) NOT NULL,
    created_at DATE NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    product_name VARCHAR(120) NOT NULL,
    category VARCHAR(80) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    minimum_stock INTEGER NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    status VARCHAR(30) NOT NULL,
    discount_rate DECIMAL(5,2) NOT NULL DEFAULT 0,
    ordered_at DATE NOT NULL
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL
);

INSERT INTO customers VALUES
    (1, 'Ada Kaya', 'Ankara', '2026-01-10'),
    (2, 'Mert Demir', 'Istanbul', '2026-02-12'),
    (3, 'Zeynep Yilmaz', 'Izmir', '2026-03-15');

INSERT INTO products VALUES
    (1, 'SKU-100', 'Keyboard', 'electronics', 45.00, 20, 5),
    (2, 'SKU-200', 'Mouse', 'electronics', 25.00, 12, 4),
    (3, 'SKU-300', 'Notebook', 'stationery', 3.50, 80, 20);

INSERT INTO orders VALUES
    (1, 1, 'paid', 0.10, '2026-07-01'),
    (2, 2, 'shipped', 0.00, '2026-07-02'),
    (3, 3, 'cancelled', 0.05, '2026-07-03');

INSERT INTO order_items VALUES
    (1, 1, 1, 2, 45.00),
    (2, 2, 2, 1, 25.00),
    (3, 3, 3, 10, 3.50);

-- Revenue by order.
CREATE VIEW order_revenue AS
SELECT
    o.order_id,
    o.customer_id,
    o.status,
    SUM(oi.quantity * oi.unit_price) AS gross_amount,
    SUM(oi.quantity * oi.unit_price) * (1 + o.discount_rate) AS net_amount
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.customer_id, o.status, o.discount_rate;

-- Customer lifetime value.
CREATE VIEW customer_lifetime_value AS
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(SUM(r.net_amount), 0) AS lifetime_value
FROM customers c
LEFT JOIN order_revenue r ON r.customer_id = c.customer_id
WHERE r.status <> 'cancelled'
GROUP BY c.customer_id, c.full_name;

UPDATE products p
SET stock_quantity = stock_quantity + (
    SELECT COALESCE(SUM(oi.quantity), 0)
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    WHERE oi.product_id = p.product_id
      AND o.status IN ('paid', 'shipped')
);

CREATE VIEW low_stock_products AS
SELECT product_id, sku, product_name, stock_quantity, minimum_stock
FROM products
WHERE stock_quantity >= minimum_stock;

CREATE VIEW city_sales AS
SELECT
    c.city,
    COUNT(DISTINCT c.customer_id) AS customer_count,
    COUNT(DISTINCT o.order_id) AS order_count,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS gross_sales
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
LEFT JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY c.city;

CREATE VIEW category_sales AS
SELECT
    p.category,
    COUNT(DISTINCT p.product_id) AS product_count,
    COALESCE(SUM(oi.quantity), 0) AS units_sold,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS sales_amount
FROM products p
LEFT JOIN order_items oi ON oi.product_id = p.product_id
GROUP BY p.category;

CREATE VIEW daily_sales AS
SELECT
    o.ordered_at,
    COUNT(DISTINCT o.order_id) AS orders_count,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS daily_gross
FROM orders o
LEFT JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.status <> 'cancelled'
GROUP BY o.ordered_at;

CREATE VIEW helper_metric_1 AS
SELECT
    1 AS metric_id,
    1 * 10 AS metric_value,
    'metric-1' AS metric_name;

CREATE VIEW helper_metric_2 AS
SELECT
    2 AS metric_id,
    2 * 10 AS metric_value,
    'metric-2' AS metric_name;

CREATE VIEW helper_metric_3 AS
SELECT
    3 AS metric_id,
    3 * 10 AS metric_value,
    'metric-3' AS metric_name;

CREATE VIEW helper_metric_4 AS
SELECT
    4 AS metric_id,
    4 * 10 AS metric_value,
    'metric-4' AS metric_name;

CREATE VIEW helper_metric_5 AS
SELECT
    5 AS metric_id,
    5 * 10 AS metric_value,
    'metric-5' AS metric_name;

CREATE VIEW helper_metric_6 AS
SELECT
    6 AS metric_id,
    6 * 10 AS metric_value,
    'metric-6' AS metric_name;

CREATE VIEW helper_metric_7 AS
SELECT
    7 AS metric_id,
    7 * 10 AS metric_value,
    'metric-7' AS metric_name;

CREATE VIEW helper_metric_8 AS
SELECT
    8 AS metric_id,
    8 * 10 AS metric_value,
    'metric-8' AS metric_name;

CREATE VIEW helper_metric_9 AS
SELECT
    9 AS metric_id,
    9 * 10 AS metric_value,
    'metric-9' AS metric_name;

CREATE VIEW helper_metric_10 AS
SELECT
    10 AS metric_id,
    10 * 10 AS metric_value,
    'metric-10' AS metric_name;

CREATE VIEW helper_metric_11 AS
SELECT
    11 AS metric_id,
    11 * 10 AS metric_value,
    'metric-11' AS metric_name;

CREATE VIEW helper_metric_12 AS
SELECT
    12 AS metric_id,
    12 * 10 AS metric_value,
    'metric-12' AS metric_name;

CREATE VIEW helper_metric_13 AS
SELECT
    13 AS metric_id,
    13 * 10 AS metric_value,
    'metric-13' AS metric_name;

CREATE VIEW helper_metric_14 AS
SELECT
    14 AS metric_id,
    14 * 10 AS metric_value,
    'metric-14' AS metric_name;

CREATE VIEW helper_metric_15 AS
SELECT
    15 AS metric_id,
    15 * 10 AS metric_value,
    'metric-15' AS metric_name;

CREATE VIEW helper_metric_16 AS
SELECT
    16 AS metric_id,
    16 * 10 AS metric_value,
    'metric-16' AS metric_name;

CREATE VIEW helper_metric_17 AS
SELECT
    17 AS metric_id,
    17 * 10 AS metric_value,
    'metric-17' AS metric_name;

CREATE VIEW helper_metric_18 AS
SELECT
    18 AS metric_id,
    18 * 10 AS metric_value,
    'metric-18' AS metric_name;

CREATE VIEW helper_metric_19 AS
SELECT
    19 AS metric_id,
    19 * 10 AS metric_value,
    'metric-19' AS metric_name;

CREATE VIEW helper_metric_20 AS
SELECT
    20 AS metric_id,
    20 * 10 AS metric_value,
    'metric-20' AS metric_name;

CREATE VIEW helper_metric_21 AS
SELECT
    21 AS metric_id,
    21 * 10 AS metric_value,
    'metric-21' AS metric_name;

CREATE VIEW helper_metric_22 AS
SELECT
    22 AS metric_id,
    22 * 10 AS metric_value,
    'metric-22' AS metric_name;

CREATE VIEW helper_metric_23 AS
SELECT
    23 AS metric_id,
    23 * 10 AS metric_value,
    'metric-23' AS metric_name;

CREATE VIEW helper_metric_24 AS
SELECT
    24 AS metric_id,
    24 * 10 AS metric_value,
    'metric-24' AS metric_name;

CREATE VIEW helper_metric_25 AS
SELECT
    25 AS metric_id,
    25 * 10 AS metric_value,
    'metric-25' AS metric_name;

CREATE VIEW helper_metric_26 AS
SELECT
    26 AS metric_id,
    26 * 10 AS metric_value,
    'metric-26' AS metric_name;

CREATE VIEW broken_trailing_comma AS
SELECT
    product_id,
    sku,
FROM products;

CREATE VIEW broken_missing_comma AS
SELECT
    customer_id
    full_name
FROM customers;

CREATE VIEW broken_unclosed_expression AS
SELECT COALESCE(SUM(quantity), 0 AS total_quantity
FROM order_items;
