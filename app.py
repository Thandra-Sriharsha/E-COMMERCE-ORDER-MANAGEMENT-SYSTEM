from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
DB = BASE / "ecommerce.db"

app = Flask(__name__)
app.secret_key = "college-dbms-demo-key"

STATUS_OPTIONS = ["Pending", "Shipped", "Delivered", "Cancelled"]

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    schema = (BASE/"sql/01_create_tables.sql").read_text(encoding="utf-8")
    seed = (BASE/"sql/02_insert_data.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.executescript(seed)
    conn.commit()
    conn.close()

def rows(query, params=()):
    conn = get_db()
    data = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in data]

def execute(query, params=()):
    conn = get_db()
    cur = conn.execute(query, params)
    conn.commit()
    last = cur.lastrowid
    conn.close()
    return last

@app.route("/")
def dashboard():
    stats = {
        "customers": rows("SELECT COUNT(*) n FROM CUSTOMER")[0]["n"],
        "products": rows("SELECT COUNT(*) n FROM PRODUCT")[0]["n"],
        "orders": rows("SELECT COUNT(*) n FROM ORDERS")[0]["n"],
        "sales": rows("SELECT COALESCE(SUM(Total_Amount),0) n FROM ORDERS")[0]["n"],
    }
    recent = rows("""SELECT O.Order_ID, C.Name, O.Order_Date, O.Total_Amount, O.Status
                     FROM ORDERS O JOIN CUSTOMER C ON C.Customer_ID=O.Customer_ID
                     ORDER BY O.Order_ID DESC LIMIT 6""")
    low = rows("SELECT * FROM PRODUCT WHERE Stock <= 15 ORDER BY Stock")
    return render_template("dashboard.html", stats=stats, recent=recent, low=low)

@app.route("/customers", methods=["GET","POST"])
def customers():
    if request.method == "POST":
        try:
            execute("INSERT INTO CUSTOMER(Name,Email,Phone,Address) VALUES(?,?,?,?)",
                    (request.form["name"],request.form["email"],request.form["phone"],request.form["address"]))
            flash("Customer added successfully.", "success")
        except sqlite3.IntegrityError as e:
            flash("Could not add customer: email/phone may already exist.", "danger")
        return redirect(url_for("customers"))
    data = rows("SELECT * FROM CUSTOMER ORDER BY Customer_ID DESC")
    return render_template("table.html", title="Customers", icon="👥", rows=data,
                           columns=["Customer_ID","Name","Email","Phone","Address"],
                           add_form="customer_form")

@app.route("/customers/delete/<int:id>", methods=["POST"])
def customer_delete(id):
    try:
        execute("DELETE FROM CUSTOMER WHERE Customer_ID=?", (id,))
        flash("Customer deleted.", "success")
    except sqlite3.IntegrityError:
        flash("Customer cannot be deleted while related records exist.", "danger")
    return redirect(url_for("customers"))

@app.route("/products", methods=["GET","POST"])
def products():
    if request.method == "POST":
        try:
            execute("""INSERT INTO PRODUCT(Product_Name,Category_ID,Price,Stock,Brand)
                      VALUES(?,?,?,?,?)""",
                    (request.form["name"],request.form["category"],request.form["price"],
                     request.form["stock"],request.form["brand"]))
            flash("Product added successfully.", "success")
        except sqlite3.IntegrityError:
            flash("Invalid category or product data.", "danger")
        return redirect(url_for("products"))
    data = rows("""SELECT P.*, C.Category_Name FROM PRODUCT P
                   JOIN CATEGORY C ON C.Category_ID=P.Category_ID
                   ORDER BY P.Product_ID DESC""")
    cats = rows("SELECT * FROM CATEGORY ORDER BY Category_Name")
    return render_template("table.html", title="Products", icon="📦", rows=data,
                           columns=["Product_ID","Product_Name","Category_Name","Price","Stock","Brand"],
                           add_form="product_form", categories=cats)

@app.route("/products/delete/<int:id>", methods=["POST"])
def product_delete(id):
    try:
        execute("DELETE FROM PRODUCT WHERE Product_ID=?", (id,))
        flash("Product deleted.", "success")
    except sqlite3.IntegrityError:
        flash("Product is referenced by an order/cart and cannot be deleted.", "danger")
    return redirect(url_for("products"))

@app.route("/categories", methods=["GET","POST"])
def categories():
    if request.method == "POST":
        try:
            execute("INSERT INTO CATEGORY(Category_Name,Description) VALUES(?,?)",
                    (request.form["name"],request.form["description"]))
            flash("Category added.", "success")
        except sqlite3.IntegrityError:
            flash("Category name already exists.", "danger")
        return redirect(url_for("categories"))
    data = rows("SELECT * FROM CATEGORY ORDER BY Category_ID")
    return render_template("table.html", title="Categories", icon="🗂️", rows=data,
                           columns=["Category_ID","Category_Name","Description"],
                           add_form="category_form")

@app.route("/categories/delete/<int:id>", methods=["POST"])
def category_delete(id):
    try:
        execute("DELETE FROM CATEGORY WHERE Category_ID=?", (id,))
        flash("Category deleted.", "success")
    except sqlite3.IntegrityError:
        flash("Category is used by products.", "danger")
    return redirect(url_for("categories"))

@app.route("/orders", methods=["GET","POST"])
def orders():
    if request.method == "POST":
        customer = request.form["customer"]
        total = float(request.form["total"])
        execute("""INSERT INTO ORDERS(Customer_ID,Order_Date,Total_Amount,Status)
                   VALUES(?,?,?,?)""",
                (customer, request.form["order_date"] or str(date.today()), total, request.form["status"]))
        flash("Order created.", "success")
        return redirect(url_for("orders"))
    data = rows("""SELECT O.*, C.Name AS Customer_Name
                   FROM ORDERS O JOIN CUSTOMER C ON C.Customer_ID=O.Customer_ID
                   ORDER BY O.Order_ID DESC""")
    cust = rows("SELECT Customer_ID,Name FROM CUSTOMER ORDER BY Name")
    return render_template("table.html", title="Orders", icon="🧾", rows=data,
                           columns=["Order_ID","Customer_Name","Order_Date","Total_Amount","Status"],
                           add_form="order_form", customers=cust, statuses=STATUS_OPTIONS)

@app.route("/orders/status/<int:id>", methods=["POST"])
def order_status(id):
    status = request.form["status"]
    if status not in STATUS_OPTIONS:
        flash("Invalid status.", "danger")
    else:
        execute("UPDATE ORDERS SET Status=? WHERE Order_ID=?", (status,id))
        flash("Order status updated.", "success")
    return redirect(url_for("orders"))

@app.route("/order-items")
def order_items():
    data = rows("""SELECT OI.Order_Item_ID, OI.Order_ID, P.Product_Name,
                   OI.Quantity, OI.Subtotal
                   FROM ORDER_ITEM OI JOIN PRODUCT P ON P.Product_ID=OI.Product_ID
                   ORDER BY OI.Order_Item_ID DESC""")
    return render_template("simple.html", title="Order Items", icon="🧩",
                           columns=["Order_Item_ID","Order_ID","Product_Name","Quantity","Subtotal"],
                           rows=data)

@app.route("/payments")
def payments():
    data = rows("""SELECT P.Payment_ID,P.Order_ID,C.Name,P.Amount,P.Payment_Date,
                   P.Payment_Method,P.Payment_Status
                   FROM PAYMENT P JOIN ORDERS O ON O.Order_ID=P.Order_ID
                   JOIN CUSTOMER C ON C.Customer_ID=O.Customer_ID
                   ORDER BY P.Payment_ID DESC""")
    return render_template("simple.html", title="Payments", icon="💳",
                           columns=["Payment_ID","Order_ID","Name","Amount","Payment_Date","Payment_Method","Payment_Status"],
                           rows=data)

@app.route("/deliveries")
def deliveries():
    data = rows("""SELECT D.Delivery_ID,D.Order_ID,C.Name,D.Delivery_Address,
                   D.Delivery_Date,D.Delivery_Status
                   FROM DELIVERY D JOIN ORDERS O ON O.Order_ID=D.Order_ID
                   JOIN CUSTOMER C ON C.Customer_ID=O.Customer_ID
                   ORDER BY D.Delivery_ID DESC""")
    return render_template("simple.html", title="Deliveries", icon="🚚",
                           columns=["Delivery_ID","Order_ID","Name","Delivery_Address","Delivery_Date","Delivery_Status"],
                           rows=data)

@app.route("/cart")
def cart():
    data = rows("""SELECT CI.Cart_Item_ID, CI.Cart_ID, C.Name, P.Product_Name,
                   CI.Quantity, (CI.Quantity*P.Price) AS Amount
                   FROM CART_ITEM CI JOIN CART CA ON CA.Cart_ID=CI.Cart_ID
                   JOIN CUSTOMER C ON C.Customer_ID=CA.Customer_ID
                   JOIN PRODUCT P ON P.Product_ID=CI.Product_ID
                   ORDER BY CI.Cart_Item_ID DESC""")
    return render_template("simple.html", title="Cart Items", icon="🛒",
                           columns=["Cart_Item_ID","Cart_ID","Name","Product_Name","Quantity","Amount"],
                           rows=data)


@app.route("/reviews")
def reviews():
    data = rows("""SELECT R.Review_ID, C.Name, P.Product_Name, R.Rating,
                   R.Review_Text, R.Review_Date
                   FROM REVIEW R
                   JOIN CUSTOMER C ON C.Customer_ID=R.Customer_ID
                   JOIN PRODUCT P ON P.Product_ID=R.Product_ID
                   ORDER BY R.Review_ID DESC""")
    return render_template("simple.html", title="Reviews", icon="⭐",
                           columns=["Review_ID","Name","Product_Name","Rating","Review_Text","Review_Date"],
                           rows=data)

@app.route("/sql-lab")
def sql_lab():
    query_results = {
        "Customer count": rows("SELECT COUNT(*) AS Total_Customers FROM CUSTOMER"),
        "Total sales": rows("SELECT ROUND(SUM(Total_Amount),2) AS Total_Sales FROM ORDERS"),
        "Average product price": rows("SELECT ROUND(AVG(Price),2) AS Average_Price FROM PRODUCT"),
        "Products above average": rows("""SELECT Product_Name, Price FROM PRODUCT
            WHERE Price > (SELECT AVG(Price) FROM PRODUCT) ORDER BY Price DESC"""),
        "Customer order view": rows("SELECT * FROM Customer_Order_View ORDER BY Order_ID DESC"),
        "Order join": rows("""SELECT O.Order_ID,P.Product_Name,OI.Quantity,OI.Subtotal
            FROM ORDERS O JOIN ORDER_ITEM OI ON O.Order_ID=OI.Order_ID
            JOIN PRODUCT P ON OI.Product_ID=P.Product_ID ORDER BY O.Order_ID""")
    }
    return render_template("sql_lab.html", results=query_results)

@app.route("/api/search")
def search():
    q = request.args.get("q","").strip()
    like = f"%{q}%"
    products = rows("""SELECT P.Product_ID,P.Product_Name,P.Price,P.Stock,C.Category_Name
                       FROM PRODUCT P JOIN CATEGORY C ON C.Category_ID=P.Category_ID
                       WHERE P.Product_Name LIKE ? OR P.Brand LIKE ? OR C.Category_Name LIKE ?
                       ORDER BY P.Product_Name LIMIT 20""", (like,like,like))
    return jsonify(products)

@app.route("/db-reset", methods=["POST"])
def db_reset():
    if DB.exists():
        DB.unlink()
    init_db()
    flash("Database reset to the PPT sample data.", "success")
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
