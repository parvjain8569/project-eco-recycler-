from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255))
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Float, default=0.0)
    orders = db.relationship('Order', backref='user', lazy=True)
    payment_methods = db.relationship('PaymentMethod', backref='user', lazy=True)
    payout_requests = db.relationship('PayoutRequest', backref='user', lazy=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    waste_type = db.Column(db.String(50), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    pickup_date = db.Column(db.String(20), nullable=False)
    pickup_slot = db.Column(db.String(50)) # Added for smart pickup
    pickup_address = db.Column(db.String(255), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='Pending')
    batch_number = db.Column(db.String(50))
    amount_calculated = db.Column(db.Float, default=0.0)
    amount_paid = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    money_sent_date = db.Column(db.DateTime)
    payout_due_date = db.Column(db.DateTime)
    is_paid_out = db.Column(db.Boolean, default=False)

class PaymentMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    method_type = db.Column(db.String(20), nullable=False) # 'bank' or 'upi'
    
    # Common/Bank fields
    account_holder_name = db.Column(db.String(100), nullable=False)
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(50))
    ifsc_code = db.Column(db.String(20))
    
    # UPI fields
    upi_id = db.Column(db.String(100))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PayoutRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Processed, Rejected
    
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    
    # Snapshot of payment details to ensure history doesn't change if user updates profile
    payment_method_snapshot = db.Column(db.Text, nullable=False) 
    
    def __repr__(self):
        return f'<PayoutRequest {self.id} - {self.user_id} - {self.status}>'

class Address(db.Model):
    __tablename__ = 'addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    street_address = db.Column(db.String(500), nullable=False)
    landmark = db.Column(db.String(200))
    state = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(6), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('addresses', lazy=True))
    
    def __repr__(self):
        return f'<Address {self.id} - {self.street_address[:20]}>'

