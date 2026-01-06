from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, text, inspect
import secrets
from datetime import datetime

# --- CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'final_year_project_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ledger.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- DATABASE MODELS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    wallet_address = db.Column(db.String(42), unique=True, nullable=False, index=True)
    balance = db.Column(db.Float, default=0.0)
    role = db.Column(db.String(20), nullable=False) # admin, organizer, reseller, customer
    parent_address = db.Column(db.String(42), nullable=True) # Hierarchy tracking
    is_active = db.Column(db.Boolean, default=True) # Account status

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if not self.wallet_address:
            self.wallet_address = "0x" + secrets.token_hex(20)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    creator_address = db.Column(db.String(42), db.ForeignKey('user.wallet_address'))
    name = db.Column(db.String(150), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    date = db.Column(db.String(50))
    wholesale_price = db.Column(db.Float)
    max_resale_price = db.Column(db.Float)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    owner_address = db.Column(db.String(42), db.ForeignKey('user.wallet_address'))
    is_listed = db.Column(db.Boolean, default=False)
    listing_price = db.Column(db.Float, nullable=True)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    reseller_address = db.Column(db.String(42))
    quantity = db.Column(db.Integer, default=1)
    price_per_item = db.Column(db.Float)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tx_hash = db.Column(db.String(66))
    ticket_id = db.Column(db.Integer, nullable=True)
    event_name = db.Column(db.String(150), nullable=True)
    from_address = db.Column(db.String(42))
    to_address = db.Column(db.String(42))
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    type = db.Column(db.String(20)) # 'MINT', 'TOPUP', 'PURCHASE', 'SALE', 'WITHDRAW'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HELPER FUNCTION: Ledger Logging ---
def log_ledger(tx_hash, t_id, evt_name, f_addr, t_addr, amt, t_type):
    new_tx = Transaction(
        tx_hash=tx_hash, ticket_id=t_id, event_name=evt_name,
        from_address=f_addr, to_address=t_addr, amount=amt, type=t_type
    )
    db.session.add(new_tx)

# --- PUBLIC ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            # Security Check: Is Account Active?
            if not user.is_active:
                flash("This account has been deactivated. Contact Admin.")
                return render_template('login.html')
                
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid Credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Public registration is strictly for Customers
    if request.method == 'POST':
        user = User(
            username=request.form['username'],
            password_hash=generate_password_hash(request.form['password']),
            role='customer',
            balance=0.0
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/ledger')
def public_ledger():
    txs = Transaction.query.order_by(Transaction.timestamp.desc()).limit(50).all()
    return render_template('ledger.html', transactions=txs)

# --- SECURE USER MANAGEMENT (Admin/Org) ---

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    new_pass = request.form['new_password']
    if len(new_pass) < 4:
        flash("Password too short.")
        return redirect(url_for('dashboard'))
    
    current_user.password_hash = generate_password_hash(new_pass)
    db.session.commit()
    flash("Password Updated Successfully.")
    return redirect(url_for('dashboard'))

@app.route('/manage_user/<int:user_id>/<action>')
@login_required
def manage_user(user_id, action):
    target_user = User.query.get_or_404(user_id)
    
    # Permission Logic
    allowed = False
    if current_user.role == 'admin' and target_user.role == 'organizer': allowed = True
    if current_user.role == 'organizer' and target_user.role == 'reseller' and target_user.parent_address == current_user.wallet_address: allowed = True
    
    if not allowed: return "Unauthorized", 403

    if action == 'toggle':
        target_user.is_active = not target_user.is_active
        status = "Activated" if target_user.is_active else "Deactivated"
        flash(f"User {target_user.username} {status}.")
        
    elif action == 'delete':
        try:
            db.session.delete(target_user)
            flash(f"User {target_user.username} Deleted.")
        except:
            db.session.rollback()
            flash("Cannot delete: User has active history.")
            
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/create_staff', methods=['POST'])
@login_required
def create_staff():
    target_role = request.form['role']
    # Permission Logic
    allowed = False
    if current_user.role == 'admin' and target_role == 'organizer': allowed = True
    if current_user.role == 'organizer' and target_role == 'reseller': allowed = True
    
    if not allowed: return "Permission Denied", 403

    new_user = User(
        username=request.form['username'],
        password_hash=generate_password_hash(request.form['password']),
        role=target_role,
        balance=0.0,
        parent_address=current_user.wallet_address
    )
    db.session.add(new_user)
    db.session.commit()
    flash(f"Created {target_role}: {new_user.username}")
    return redirect(url_for('dashboard'))

# --- CORE DASHBOARD & EVENTS ---

@app.route('/dashboard')
@login_required
def dashboard():
    # 1. Admin View
    if current_user.role == 'admin':
        orgs = User.query.filter_by(role='organizer', parent_address=current_user.wallet_address).all()
        return render_template('dashboard.html', staff_list=orgs)
    
    # 2. Organizer View
    if current_user.role == 'organizer':
        events = Event.query.filter_by(creator_address=current_user.wallet_address).all()
        # Calculate stats for each event
        my_events_data = []
        for e in events:
            total = Ticket.query.filter_by(event_id=e.id).count()
            unsold = Ticket.query.filter_by(event_id=e.id, owner_address=current_user.wallet_address).count()
            my_events_data.append({'event': e, 'total': total, 'sold': total-unsold, 'unsold': unsold})
        
        resellers = User.query.filter_by(role='reseller', parent_address=current_user.wallet_address).all()
        return render_template('dashboard.html', organizer_data=my_events_data, staff_list=resellers)

    # 3. Reseller/Customer View
    market_events = []
    if current_user.role == 'reseller':
        # Can only see parent's events
        market_events = Event.query.filter_by(creator_address=current_user.parent_address).all()
        
    # Asset Inventory (For Resellers/Customers)
    my_assets = []
    asset_stats = db.session.query(
        Ticket.event_id, func.count(Ticket.id)
    ).filter_by(owner_address=current_user.wallet_address).group_by(Ticket.event_id).all()

    for eid, count in asset_stats:
        evt = Event.query.get(eid)
        listed = Ticket.query.filter_by(owner_address=current_user.wallet_address, event_id=eid, is_listed=True).count()
        my_assets.append({'event': evt, 'owned_count': count, 'listed_count': listed, 'unlisted_count': count-listed})
        
    return render_template('dashboard.html', my_assets=my_assets, market_events=market_events)

@app.route('/create_event', methods=['POST'])
@login_required
def create_event():
    if current_user.role != 'organizer': return "Unauthorized", 403
    
    new_event = Event(
        creator_address=current_user.wallet_address,
        name=request.form['name'],
        symbol=request.form['symbol'].upper(),
        date=request.form['date'],
        wholesale_price=float(request.form['wholesale']),
        max_resale_price=float(request.form['cap'])
    )
    db.session.add(new_event)
    db.session.flush()
    
    supply = int(request.form['supply'])
    tx_hash = "0x" + secrets.token_hex(20)
    
    for i in range(supply):
        t = Ticket(
            event_id=new_event.id, 
            owner_address=current_user.wallet_address, 
            is_listed=True, 
            listing_price=new_event.wholesale_price
        )
        db.session.add(t)
        # Log first ticket only to keep ledger clean but showing mint occured
        if i == 0:
            log_ledger(tx_hash, None, f"MINT {supply}x {new_event.symbol}", "SYSTEM", current_user.wallet_address, 0, "MINT")
            
    db.session.commit()
    flash(f"Event Deployed & {supply} Tickets Minted!")
    return redirect(url_for('dashboard'))

# --- WALLET & CART SYSTEM ---

@app.route('/wallet', methods=['GET', 'POST'])
@login_required
def wallet():
    if request.method == 'POST':
        amt = float(request.form['amount'])
        current_user.balance += amt
        log_ledger(secrets.token_hex(16), None, "Wallet Top-Up", "BANK", current_user.wallet_address, amt, "TOPUP")
        db.session.commit()
        return redirect(url_for('wallet'))
        
    txs = Transaction.query.filter(
        (Transaction.from_address == current_user.wallet_address) | 
        (Transaction.to_address == current_user.wallet_address)
    ).order_by(Transaction.timestamp.desc()).all()
    return render_template('wallet.html', transactions=txs)

@app.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    if current_user.role != 'organizer': return "Unauthorized", 403
    amt = float(request.form['amount'])
    
    if amt <= current_user.balance:
        current_user.balance -= amt
        log_ledger(secrets.token_hex(16), None, "Withdrawal", current_user.wallet_address, "BANK", amt, "WITHDRAW")
        db.session.commit()
        flash("Withdrawal Successful")
    else:
        flash("Insufficient Funds")
    return redirect(url_for('wallet'))

@app.route('/cart')
@login_required
def view_cart():
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(i.quantity * i.price_per_item for i in items)
    cart_data = []
    for item in items:
        evt = Event.query.get(item.event_id)
        cart_data.append({'item': item, 'event': evt, 'subtotal': item.quantity * item.price_per_item})
    return render_template('cart.html', cart=cart_data, total=total)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    e_id = int(request.form['event_id'])
    reseller = request.form['reseller_wallet']
    price = float(request.form['price'])
    qty = int(request.form['quantity'])
    
    # Check if exists, update quantity
    exist = CartItem.query.filter_by(user_id=current_user.id, event_id=e_id, price_per_item=price).first()
    if exist:
        exist.quantity += qty
    else:
        db.session.add(CartItem(
            user_id=current_user.id, event_id=e_id, reseller_address=reseller, quantity=qty, price_per_item=price
        ))
    
    db.session.commit()
    flash("Added to Cart")
    return redirect(url_for('view_market', wallet_address=reseller))

@app.route('/remove_cart/<int:item_id>')
@login_required
def remove_cart(item_id):
    CartItem.query.filter_by(id=item_id, user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart: return redirect(url_for('dashboard'))
    
    total = sum(i.quantity * i.price_per_item for i in cart)
    if current_user.balance < total:
        flash("Insufficient Balance")
        return redirect(url_for('wallet'))
    
    order_hash = "0x" + secrets.token_hex(20)
    
    try:
        current_user.balance -= total
        
        for item in cart:
            # Atomic Stock Check
            tickets = Ticket.query.filter_by(
                owner_address=item.reseller_address, 
                event_id=item.event_id, 
                is_listed=True, 
                listing_price=item.price_per_item
            ).limit(item.quantity).all()
            
            if len(tickets) < item.quantity:
                raise Exception("Stock changed during checkout.")
            
            # Pay Seller
            seller = User.query.filter_by(wallet_address=item.reseller_address).first()
            seller.balance += (item.quantity * item.price_per_item)
            
            event_name = Event.query.get(item.event_id).name
            
            # Transfer Assets
            for t in tickets:
                t.owner_address = current_user.wallet_address
                t.is_listed = False
                t.listing_price = None
                log_ledger(order_hash, t.id, event_name, item.reseller_address, current_user.wallet_address, item.price_per_item, "PURCHASE")
        
        # Clear Cart
        CartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return redirect(url_for('orders'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Transaction Failed: {str(e)}")
        return redirect(url_for('view_cart'))

@app.route('/orders')
@login_required
def orders():
    purchases = db.session.query(
        Transaction.tx_hash, Transaction.timestamp, Transaction.event_name,
        func.count(Transaction.id).label('count'), func.sum(Transaction.amount).label('total')
    ).filter_by(to_address=current_user.wallet_address, type='PURCHASE')\
    .group_by(Transaction.tx_hash).order_by(Transaction.timestamp.desc()).all()
    return render_template('orders.html', orders=purchases)

# --- MARKETPLACE & LISTING ---

@app.route('/bulk_acquire', methods=['POST'])
@login_required
def bulk_acquire():
    if current_user.role != 'reseller': return "Unauthorized", 403
    
    evt_id = int(request.form['event_id'])
    qty = int(request.form['quantity'])
    event = Event.query.get(evt_id)
    
    # Security: Hierarchy Check
    if event.creator_address != current_user.parent_address:
        flash("Security Alert: Unauthorized Source")
        return redirect(url_for('dashboard'))
        
    cost = event.wholesale_price * qty
    if current_user.balance < cost:
        flash("Insufficient Funds")
        return redirect(url_for('dashboard'))
        
    tickets = Ticket.query.filter_by(event_id=evt_id, owner_address=event.creator_address, is_listed=True).limit(qty).all()
    
    if len(tickets) < qty:
        flash("Not enough stock")
        return redirect(url_for('dashboard'))
        
    organizer = User.query.filter_by(wallet_address=event.creator_address).first()
    current_user.balance -= cost
    organizer.balance += cost
    
    tx_hash = "0x" + secrets.token_hex(20)
    for t in tickets:
        t.owner_address = current_user.wallet_address
        t.is_listed = False
        t.listing_price = None
        log_ledger(tx_hash, t.id, event.name, event.creator_address, current_user.wallet_address, event.wholesale_price, "WHOLESALE")
        
    db.session.commit()
    flash("Stock Acquired Successfully")
    return redirect(url_for('dashboard'))

@app.route('/bulk_list', methods=['POST'])
@login_required
def bulk_list():
    evt_id = int(request.form['event_id'])
    qty = int(request.form['quantity'])
    price = float(request.form['price'])
    
    if price > Event.query.get(evt_id).max_resale_price:
        flash("Price Cap Exceeded")
        return redirect(url_for('dashboard'))
        
    tickets = Ticket.query.filter_by(event_id=evt_id, owner_address=current_user.wallet_address, is_listed=False).limit(qty).all()
    
    for t in tickets:
        t.is_listed = True
        t.listing_price = price
        
    db.session.commit()
    flash(f"{qty} Tickets Listed")
    return redirect(url_for('dashboard'))

@app.route('/market/<wallet_address>')
def view_market(wallet_address):
    reseller = User.query.filter_by(wallet_address=wallet_address).first_or_404()
    
    inventory = db.session.query(
        Ticket.event_id, Ticket.listing_price, func.count(Ticket.id)
    ).filter_by(owner_address=wallet_address, is_listed=True).group_by(Ticket.event_id, Ticket.listing_price).all()
    
    grouped = []
    for e_id, price, count in inventory:
        grouped.append({'event': Event.query.get(e_id), 'price': price, 'available': count})
        
    return render_template('market_view.html', reseller=reseller, inventory=grouped)

# --- AUTO-MIGRATION LOGIC (Robust) ---
def check_and_update_schema():
    with app.app_context():
        inspector = inspect(db.engine)
        db.create_all()
        
        with db.engine.connect() as conn:
            # 1. Check User Table
            user_cols = [col['name'] for col in inspector.get_columns('user')]
            if 'balance' not in user_cols: conn.execute(text("ALTER TABLE user ADD COLUMN balance FLOAT DEFAULT 0.0"))
            if 'parent_address' not in user_cols: conn.execute(text("ALTER TABLE user ADD COLUMN parent_address VARCHAR(42)"))
            if 'role' not in user_cols: conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'customer'"))
            if 'is_active' not in user_cols: 
                print("Migrating: Adding 'is_active'...")
                conn.execute(text("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1"))

            # 2. Check Transaction Table
            if inspector.has_table('transaction'):
                tx_cols = [col['name'] for col in inspector.get_columns('transaction')]
                if 'event_name' not in tx_cols: 
                    print("Migrating: Adding 'event_name'...")
                    conn.execute(text("ALTER TABLE `transaction` ADD COLUMN event_name VARCHAR(150)"))
                if 'type' not in tx_cols:
                    print("Migrating: Adding 'type'...")
                    conn.execute(text("ALTER TABLE `transaction` ADD COLUMN type VARCHAR(20)"))

            conn.commit()
            print("Database Schema Verified.")

# Run migration check on startup
check_and_update_schema()

if __name__ == '__main__':
    app.run(debug=True)