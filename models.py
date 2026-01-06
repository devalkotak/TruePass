# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import secrets
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    wallet_address = db.Column(db.String(42), unique=True, nullable=False, index=True)
    balance = db.Column(db.Float, default=0.0)
    role = db.Column(db.String(20), nullable=False)
    parent_address = db.Column(db.String(42), nullable=True)
    
    # NEW: Account Status (Active/Inactive)
    is_active = db.Column(db.Boolean, default=True) 

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if not self.wallet_address:
            self.wallet_address = "0x" + secrets.token_hex(20)

# ... (Keep Event, Ticket, CartItem, Transaction classes exactly as they were) ...
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
    type = db.Column(db.String(20))