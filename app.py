import json
import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'change-this-to-a-random-string'  # CHANGE THIS!

# Admin password – change it!
ADMIN_PASSWORD = 'admin123'

# File paths – use absolute paths for cloud
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDERS_FILE = os.path.join(BASE_DIR, "data", "orders.json")
CUSTOMERS_FILE = os.path.join(BASE_DIR, "data", "customers.json")

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_orders(orders):
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)

def load_customers():
    if os.path.exists(CUSTOMERS_FILE):
        with open(CUSTOMERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_customers(customers):
    with open(CUSTOMERS_FILE, "w") as f:
        json.dump(customers, f, indent=2)

def calculate_delivery_fee(quantity):
    if quantity == 1:
        return 10
    elif 2 <= quantity <= 5:
        return 20
    else:  # quantity >= 6
        return 50

def generate_order_id():
    return str(uuid.uuid4())[:8]  # short unique ID

# ---------- Public routes ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/order', methods=['GET', 'POST'])
def order():
    if request.method == 'POST':
        # Get form data
        hostel = request.form.get('hostel', '').strip()
        room = request.form.get('room', '').strip()
        shop_name = request.form.get('shop_name', '').strip()
        item_description = request.form.get('item_description', '').strip()
        try:
            goods_amount = float(request.form.get('goods_amount', 0))
            quantity = int(request.form.get('quantity', 0))
        except ValueError:
            goods_amount = 0
            quantity = 0
        payment_method = request.form.get('payment_method', 'cash')
        mpesa_number = request.form.get('mpesa_number', '').strip()
        receipt_number = request.form.get('receipt_number', '').strip()

        # Validation
        if not room:
            return "Room number is required.", 400
        if not shop_name:
            return "Shop name is required.", 400
        if not item_description:
            return "Please describe what you want.", 400
        if goods_amount < 1:
            return "Goods amount must be at least 1 KES.", 400
        if quantity < 1:
            return "Quantity must be at least 1.", 400
        if payment_method == 'mpesa' and not mpesa_number:
            return "M-Pesa phone number is required.", 400
        if payment_method == 'ussd' and not receipt_number:
            return "M-Pesa receipt number is required for USSD payments.", 400

        # Calculate delivery fee and total
        delivery_fee = calculate_delivery_fee(quantity)
        total_amount = goods_amount + delivery_fee

        # Loyalty program
        customer_id = room.lower()
        customers = load_customers()
        order_count = customers.get(customer_id, 0)

        if order_count == 10:
            final_price = 0
            customers[customer_id] = 0
            free_order = True
        else:
            final_price = total_amount
            customers[customer_id] = order_count + 1
            free_order = False

        save_customers(customers)

        # Create order record
        order_data = {
            "id": generate_order_id(),
            "timestamp": datetime.now().isoformat(),
            "hostel": hostel,
            "room": room,
            "shop_name": shop_name,
            "item": item_description,
            "goods_amount": goods_amount,
            "quantity": quantity,
            "delivery_fee": delivery_fee,
            "total_amount": total_amount,
            "final_price": final_price,
            "free": free_order,
            "payment_method": payment_method,
            "mpesa_number": mpesa_number if payment_method == 'mpesa' else None,
            "receipt_number": receipt_number if payment_method == 'ussd' else None,
            "status": "pending"
        }
        orders = load_orders()
        orders.append(order_data)
        save_orders(orders)

        return redirect(url_for('success', order_id=order_data['id']))

    return render_template('order.html')

@app.route('/success')
def success():
    order_id = request.args.get('order_id', '')
    orders = load_orders()
    order = next((o for o in orders if o['id'] == order_id), None)
    if not order:
        return "Order not found", 404
    return render_template('success.html', order=order)

# ---------- Admin routes ----------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Incorrect password')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@admin_required
def admin_dashboard():
    orders = load_orders()
    customers = load_customers()
    
    total_orders = len(orders)
    pending_orders = len([o for o in orders if o['status'] == 'pending'])
    paid_orders = len([o for o in orders if o['status'] == 'paid'])
    delivered_orders = len([o for o in orders if o['status'] == 'delivered'])
    revenue = sum(o['final_price'] for o in orders if o['status'] == 'paid')
    
    return render_template('admin/dashboard.html',
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           paid_orders=paid_orders,
                           delivered_orders=delivered_orders,
                           revenue=revenue,
                           total_customers=len(customers))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', 'all')
    orders = load_orders()
    orders.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    if status_filter != 'all':
        orders = [o for o in orders if o['status'] == status_filter]
    
    return render_template('admin/orders.html', orders=orders, current_filter=status_filter)

@app.route('/admin/order/<order_id>', methods=['GET', 'POST'])
@admin_required
def admin_order(order_id):
    orders = load_orders()
    order_index = None
    order = None
    for i, o in enumerate(orders):
        if o['id'] == order_id:
            order = o
            order_index = i
            break
    
    if order is None:
        return "Order not found", 404

    if request.method == 'POST':
        new_status = request.form.get('status')
        if new_status in ['pending', 'paid', 'delivered']:
            orders[order_index]['status'] = new_status
            save_orders(orders)
            flash(f'Order status updated to {new_status}')
            return redirect(url_for('admin_order', order_id=order_id))
        else:
            flash('Invalid status')

    return render_template('admin/order.html', order=order)

if __name__ == '__main__':
    app.run()