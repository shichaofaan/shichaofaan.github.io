from lineage_hub.extractors import extract_dim_ids, extract_qualified_names


def test_extract_dim_ids():
    text = "dim:trade_gmv and DIM:User_Active_Days plus nonsense dim:"
    assert extract_dim_ids(text) == ["trade_gmv", "user_active_days"]


def test_extract_qualified_names():
    sql = """
    INSERT INTO dws.trade_gmv
    SELECT o.order_id, o.pay_amount
    FROM ods.orders o
    JOIN dim.user u ON o.user_id = u.id
    """
    names = extract_qualified_names(sql)
    assert "dws.trade_gmv" in names
    assert "ods.orders" in names
    assert "dim.user" in names
