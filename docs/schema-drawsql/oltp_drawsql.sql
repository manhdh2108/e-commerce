CREATE TABLE public.ad_spend_logs (
id bigint NOT NULL,
    campaign_id integer,
    channel_code character varying,
    log_date date,
    cost_amount numeric(24,6),
    impressions bigint,
    clicks bigint,
    CONSTRAINT ck_mock_ad_spend_logs_0 CHECK (((cost_amount >= (0)::numeric) AND (clicks >= 0) AND (impressions >= clicks)))
);

CREATE TABLE public.carriers (
id integer NOT NULL,
    carrier_code character varying,
    carrier_name character varying
);

CREATE TABLE public.cart_items (
id bigint NOT NULL,
    session_id bigint,
    customer_id bigint,
    product_id bigint,
    quantity integer,
    cart_status character varying,
    added_at timestamp without time zone,
    closed_at timestamp without time zone
);

CREATE TABLE public.categories (
id integer NOT NULL,
    category_name character varying,
    parent_id integer,
    level integer,
    slug character varying
);

CREATE TABLE public.channels (
id integer NOT NULL,
    channel_name character varying,
    channel_type character varying
);

CREATE TABLE public.checkout_lines (
id bigint NOT NULL,
    checkout_id bigint,
    cart_item_id bigint,
    order_item_id bigint
);

CREATE TABLE public.checkouts (
id bigint NOT NULL,
    checkout_code character varying,
    session_id bigint,
    customer_id bigint,
    created_at timestamp without time zone
);

CREATE TABLE public.customer_addresses (
id bigint NOT NULL,
    customer_id bigint,
    recipient_name character varying,
    phone character varying,
    address_detail character varying,
    ward character varying,
    district character varying,
    province character varying,
    is_default boolean
);

CREATE TABLE public.customers (
id bigint NOT NULL,
    full_name character varying,
    email character varying,
    phone_number character varying,
    gender character varying,
    date_of_birth date,
    province character varying,
    city character varying,
    membership_tier character varying,
    registration_date timestamp without time zone,
    updated_at timestamp without time zone
);

CREATE TABLE public.delivery_attempts (
id bigint NOT NULL,
    shipment_id bigint,
    attempt_number integer,
    result character varying,
    attempted_at timestamp without time zone
);

CREATE TABLE public.inventory_daily_balance (
id bigint NOT NULL,
    balance_date date,
    warehouse_id integer,
    sku character varying,
    quantity_on_hand integer,
    quantity_reserved integer,
    CONSTRAINT ck_mock_inventory_daily_balance_0 CHECK (((quantity_on_hand >= 0) AND (quantity_reserved >= 0) AND (quantity_reserved <= quantity_on_hand)))
);

CREATE TABLE public.inventory_levels (
id bigint NOT NULL,
    warehouse_id integer,
    sku character varying,
    quantity_on_hand integer,
    quantity_reserved integer,
    updated_at timestamp without time zone,
    CONSTRAINT ck_mock_inventory_levels_0 CHECK (((quantity_on_hand >= 0) AND (quantity_reserved >= 0) AND (quantity_reserved <= quantity_on_hand)))
);

CREATE TABLE public.inventory_movements (
id bigint NOT NULL,
    warehouse_id integer,
    sku character varying,
    movement_type character varying,
    quantity_change integer,
    reference_code character varying,
    movement_date timestamp without time zone
);

CREATE TABLE public.marketing_campaigns (
id integer NOT NULL,
    campaign_code character varying,
    campaign_name character varying,
    campaign_type character varying,
    target_channel_code character varying,
    budget_amount numeric(24,6),
    start_date date,
    end_date date
);

CREATE TABLE public.order_item_promotions (
id bigint NOT NULL,
    order_item_id bigint,
    promotion_id bigint,
    applied_discount_amount numeric(24,6),
    funded_by character varying
);

CREATE TABLE public.order_items (
id bigint NOT NULL,
    order_id bigint,
    line_number integer,
    product_id bigint,
    quantity integer,
    list_price numeric(24,6),
    unit_price numeric(24,6),
    discount_amount numeric(24,6),
    net_amount numeric(24,6),
    item_status character varying,
    commission_rate numeric(24,6),
    commission_category_id integer,
    commission_seller_tier character varying,
    CONSTRAINT ck_mock_order_items_0 CHECK (((quantity > 0) AND (unit_price >= (0)::numeric) AND (discount_amount >= (0)::numeric) AND (net_amount >= (0)::numeric)))
);

CREATE TABLE public.orders (
id bigint NOT NULL,
    order_code character varying,
    customer_id bigint,
    seller_id bigint,
    channel_id integer,
    session_id bigint,
    campaign_id integer,
    order_status character varying,
    total_gross_amount numeric(24,6),
    total_discount_amount numeric(24,6),
    shipping_fee numeric(24,6),
    shipping_discount_amount numeric(24,6),
    shipping_promotion_id bigint,
    final_amount numeric(24,6),
    shipping_address_id bigint,
    created_at timestamp without time zone,
    completed_at timestamp without time zone,
    cancelled_at timestamp without time zone,
    updated_at timestamp without time zone,
    checkout_id bigint,
    cancellation_reason text,
    CONSTRAINT ck_mock_orders_0 CHECK (((total_gross_amount >= (0)::numeric) AND (total_discount_amount >= (0)::numeric) AND (shipping_fee >= (0)::numeric) AND (shipping_discount_amount >= (0)::numeric) AND (final_amount >= (0)::numeric)))
);

CREATE TABLE public.page_events (
id bigint NOT NULL,
    session_id bigint,
    event_type character varying,
    product_id bigint,
    order_id bigint,
    event_time timestamp without time zone,
    search_keyword text
);

CREATE TABLE public.payment_methods (
id integer NOT NULL,
    method_name character varying,
    method_group character varying
);

CREATE TABLE public.payments (
id bigint NOT NULL,
    order_id bigint,
    payment_method_id integer,
    payment_status character varying,
    paid_amount numeric(24,6),
    transaction_time timestamp without time zone,
    CONSTRAINT ck_mock_payments_0 CHECK ((paid_amount >= (0)::numeric))
);

CREATE TABLE public.product_reviews (
id bigint NOT NULL,
    order_item_id bigint,
    product_id bigint,
    customer_id bigint,
    rating integer,
    comment text,
    created_at timestamp without time zone,
    CONSTRAINT ck_mock_product_reviews_0 CHECK (((rating >= 1) AND (rating <= 5)))
);

CREATE TABLE public.products (
id bigint NOT NULL,
    sku character varying,
    name character varying,
    url_key character varying,
    price numeric(24,6),
    original_price numeric(24,6),
    discount numeric(24,6),
    discount_rate numeric(24,6),
    brand_name character varying,
    rating_average numeric(24,6),
    review_count integer,
    thumbnail_url character varying,
    category_id integer,
    category_name character varying,
    quantity_sold integer,
    crawl_date date,
    is_active boolean,
    seller_id bigint,
    seller_product_id character varying,
    url_path character varying,
    inventory_status character varying,
    stock_item text,
    short_description text,
    type character varying,
    cost_price numeric(24,6),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);

CREATE TABLE public.promotion_usages (
id bigint NOT NULL,
    promotion_id bigint,
    order_id bigint,
    customer_id bigint,
    discount_amount numeric(24,6),
    usage_status character varying,
    created_at timestamp without time zone,
    released_at timestamp without time zone
);

CREATE TABLE public.promotions (
id bigint NOT NULL,
    promo_code character varying,
    promo_name character varying,
    promo_type character varying,
    seller_id bigint,
    apply_level character varying,
    product_id bigint,
    eligibility character varying,
    discount_type character varying,
    discount_value numeric(24,6),
    min_order_value numeric(24,6),
    max_discount_amount numeric(24,6),
    usage_limit integer,
    per_customer_limit integer,
    start_date timestamp without time zone,
    end_date timestamp without time zone
);

CREATE TABLE public.refunds (
id bigint NOT NULL,
    order_id bigint,
    return_id bigint,
    amount numeric(24,6),
    reason character varying,
    refund_status character varying,
    requested_at timestamp without time zone,
    completed_at timestamp without time zone,
    CONSTRAINT ck_mock_refunds_0 CHECK ((amount > (0)::numeric))
);

CREATE TABLE public.returns (
id bigint NOT NULL,
    order_item_id bigint,
    quantity integer,
    return_reason character varying,
    refund_amount numeric(24,6),
    status character varying,
    requested_at timestamp without time zone,
    refunded_at timestamp without time zone,
    received_at timestamp without time zone,
    warehouse_id integer,
    approved_at timestamp without time zone,
    decision_reason text,
    CONSTRAINT ck_mock_returns_0 CHECK (((quantity > 0) AND (refund_amount >= (0)::numeric)))
);

CREATE TABLE public.seller_commission_rates (
id integer NOT NULL,
    category_id integer,
    seller_tier character varying,
    commission_rate numeric(24,6),
    effective_from date,
    effective_to date,
    CONSTRAINT ck_mock_seller_commission_rates_0 CHECK (((commission_rate >= (0)::numeric) AND (commission_rate <= (1)::numeric)))
);

CREATE TABLE public.seller_payout_items (
id bigint NOT NULL,
    seller_payout_id bigint,
    order_item_id bigint,
    gross_amount numeric(24,6),
    refund_amount numeric(24,6),
    commission_amount numeric(24,6),
    net_amount numeric(24,6),
    created_at timestamp without time zone
);

CREATE TABLE public.seller_payouts (
id bigint NOT NULL,
    seller_id bigint,
    period_start date,
    period_end date,
    gross_sales numeric(24,6),
    refund_amount numeric(24,6),
    commission_amount numeric(24,6),
    payout_amount numeric(24,6),
    payout_status character varying,
    paid_at timestamp without time zone
);

CREATE TABLE public.sellers (
id bigint NOT NULL,
    seller_name character varying,
    shop_name character varying,
    tier character varying,
    province character varying,
    city character varying,
    email character varying,
    phone character varying,
    status character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);

CREATE TABLE public.sessions (
id bigint NOT NULL,
    customer_id bigint,
    channel_id integer,
    campaign_id integer,
    traffic_source character varying,
    device_type character varying,
    started_at timestamp without time zone,
    ended_at timestamp without time zone
);

CREATE TABLE public.shipments (
id bigint NOT NULL,
    order_code character varying,
    warehouse_id integer,
    carrier_id integer,
    tracking_code character varying,
    shipment_status character varying,
    shipping_cost numeric(24,6),
    created_at timestamp without time zone,
    picked_at timestamp without time zone,
    delivered_at timestamp without time zone,
    failed_at timestamp without time zone,
    in_transit_at timestamp without time zone,
    returned_at timestamp without time zone
);

CREATE TABLE public.warehouses (
id integer NOT NULL,
    warehouse_code character varying,
    warehouse_name character varying,
    province character varying,
    city character varying,
    address text
);

ALTER TABLE ONLY public.ad_spend_logs
    ADD CONSTRAINT ad_spend_logs_campaign_id_channel_code_log_date_key UNIQUE (campaign_id, channel_code, log_date);

ALTER TABLE ONLY public.ad_spend_logs
    ADD CONSTRAINT ad_spend_logs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.carriers
    ADD CONSTRAINT carriers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.checkout_lines
    ADD CONSTRAINT checkout_lines_cart_item_id_key UNIQUE (cart_item_id);

ALTER TABLE ONLY public.checkout_lines
    ADD CONSTRAINT checkout_lines_order_item_id_key UNIQUE (order_item_id);

ALTER TABLE ONLY public.checkout_lines
    ADD CONSTRAINT checkout_lines_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.checkouts
    ADD CONSTRAINT checkouts_checkout_code_key UNIQUE (checkout_code);

ALTER TABLE ONLY public.checkouts
    ADD CONSTRAINT checkouts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.customer_addresses
    ADD CONSTRAINT customer_addresses_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.delivery_attempts
    ADD CONSTRAINT delivery_attempts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.delivery_attempts
    ADD CONSTRAINT delivery_attempts_shipment_id_attempt_number_key UNIQUE (shipment_id, attempt_number);

ALTER TABLE ONLY public.inventory_daily_balance
    ADD CONSTRAINT inventory_daily_balance_balance_date_warehouse_id_sku_key UNIQUE (balance_date, warehouse_id, sku);

ALTER TABLE ONLY public.inventory_daily_balance
    ADD CONSTRAINT inventory_daily_balance_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.inventory_levels
    ADD CONSTRAINT inventory_levels_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.inventory_levels
    ADD CONSTRAINT inventory_levels_warehouse_id_sku_key UNIQUE (warehouse_id, sku);

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.marketing_campaigns
    ADD CONSTRAINT marketing_campaigns_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.order_item_promotions
    ADD CONSTRAINT order_item_promotions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_line_number_key UNIQUE (order_id, line_number);

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_order_code_key UNIQUE (order_code);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.page_events
    ADD CONSTRAINT page_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT payment_methods_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.product_reviews
    ADD CONSTRAINT product_reviews_order_item_id_key UNIQUE (order_item_id);

ALTER TABLE ONLY public.product_reviews
    ADD CONSTRAINT product_reviews_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_sku_key UNIQUE (sku);

ALTER TABLE ONLY public.promotion_usages
    ADD CONSTRAINT promotion_usages_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT returns_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.seller_commission_rates
    ADD CONSTRAINT seller_commission_rates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.seller_payout_items
    ADD CONSTRAINT seller_payout_items_order_item_id_key UNIQUE (order_item_id);

ALTER TABLE ONLY public.seller_payout_items
    ADD CONSTRAINT seller_payout_items_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.seller_payouts
    ADD CONSTRAINT seller_payouts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.seller_payouts
    ADD CONSTRAINT seller_payouts_seller_id_period_start_period_end_key UNIQUE (seller_id, period_start, period_end);

ALTER TABLE ONLY public.sellers
    ADD CONSTRAINT sellers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_order_code_key UNIQUE (order_code);

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_tracking_code_key UNIQUE (tracking_code);

ALTER TABLE ONLY public.warehouses
    ADD CONSTRAINT warehouses_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.ad_spend_logs
    ADD CONSTRAINT ad_spend_logs_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.marketing_campaigns(id);

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);

ALTER TABLE ONLY public.cart_items
    ADD CONSTRAINT cart_items_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id);

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.categories(id);

ALTER TABLE ONLY public.checkout_lines
    ADD CONSTRAINT checkout_lines_cart_item_id_fkey FOREIGN KEY (cart_item_id) REFERENCES public.cart_items(id);

ALTER TABLE ONLY public.checkout_lines
    ADD CONSTRAINT checkout_lines_checkout_id_fkey FOREIGN KEY (checkout_id) REFERENCES public.checkouts(id);

ALTER TABLE ONLY public.checkout_lines
    ADD CONSTRAINT checkout_lines_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES public.order_items(id);

ALTER TABLE ONLY public.checkouts
    ADD CONSTRAINT checkouts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.checkouts
    ADD CONSTRAINT checkouts_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id);

ALTER TABLE ONLY public.customer_addresses
    ADD CONSTRAINT customer_addresses_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.delivery_attempts
    ADD CONSTRAINT delivery_attempts_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES public.shipments(id);

ALTER TABLE ONLY public.inventory_daily_balance
    ADD CONSTRAINT inventory_daily_balance_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

ALTER TABLE ONLY public.inventory_levels
    ADD CONSTRAINT inventory_levels_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

ALTER TABLE ONLY public.order_item_promotions
    ADD CONSTRAINT order_item_promotions_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES public.order_items(id);

ALTER TABLE ONLY public.order_item_promotions
    ADD CONSTRAINT order_item_promotions_promotion_id_fkey FOREIGN KEY (promotion_id) REFERENCES public.promotions(id);

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_commission_category_id_fkey FOREIGN KEY (commission_category_id) REFERENCES public.categories(id);

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.marketing_campaigns(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channels(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_checkout_id_fkey FOREIGN KEY (checkout_id) REFERENCES public.checkouts(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.sellers(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_shipping_address_id_fkey FOREIGN KEY (shipping_address_id) REFERENCES public.customer_addresses(id);

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_shipping_promotion_id_fkey FOREIGN KEY (shipping_promotion_id) REFERENCES public.promotions(id);

ALTER TABLE ONLY public.page_events
    ADD CONSTRAINT page_events_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

ALTER TABLE ONLY public.page_events
    ADD CONSTRAINT page_events_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);

ALTER TABLE ONLY public.page_events
    ADD CONSTRAINT page_events_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.sessions(id);

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_payment_method_id_fkey FOREIGN KEY (payment_method_id) REFERENCES public.payment_methods(id);

ALTER TABLE ONLY public.product_reviews
    ADD CONSTRAINT product_reviews_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.product_reviews
    ADD CONSTRAINT product_reviews_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES public.order_items(id);

ALTER TABLE ONLY public.product_reviews
    ADD CONSTRAINT product_reviews_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id);

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.sellers(id);

ALTER TABLE ONLY public.promotion_usages
    ADD CONSTRAINT promotion_usages_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.promotion_usages
    ADD CONSTRAINT promotion_usages_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

ALTER TABLE ONLY public.promotion_usages
    ADD CONSTRAINT promotion_usages_promotion_id_fkey FOREIGN KEY (promotion_id) REFERENCES public.promotions(id);

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.sellers(id);

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_return_id_fkey FOREIGN KEY (return_id) REFERENCES public.returns(id);

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT returns_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES public.order_items(id);

ALTER TABLE ONLY public.returns
    ADD CONSTRAINT returns_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

ALTER TABLE ONLY public.seller_commission_rates
    ADD CONSTRAINT seller_commission_rates_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id);

ALTER TABLE ONLY public.seller_payout_items
    ADD CONSTRAINT seller_payout_items_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES public.order_items(id);

ALTER TABLE ONLY public.seller_payout_items
    ADD CONSTRAINT seller_payout_items_seller_payout_id_fkey FOREIGN KEY (seller_payout_id) REFERENCES public.seller_payouts(id);

ALTER TABLE ONLY public.seller_payouts
    ADD CONSTRAINT seller_payouts_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.sellers(id);

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.marketing_campaigns(id);

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES public.channels(id);

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES public.carriers(id);

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);
