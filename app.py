from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Order, PaymentMethod, PayoutRequest, Address
from utils import send_email, generate_otp, generate_batch_id
import os
from dotenv import load_dotenv
from datetime import timedelta
import datetime
import subprocess
import random

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

db.init_app(app)

with app.app_context():
    db.create_all()

from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('signup'))

        name = f"{first_name} {last_name}"
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password, method='scrypt')
        

        session['temp_user'] = {
            'name': name, 
            'email': email, 
            'password': hashed_password
        }
        
        otp = generate_otp()
        session['otp'] = otp
        
        email_body = f"""
        <div class='otp-box'>{otp}</div>
        <p>Use the code above to verify your email address.</p>
        """
        
        if send_email(email, "Verify Your Email", email_body, is_html=True):
            return redirect(url_for('verify'))
        else:
            flash('Error sending email. Please try again.', 'error')
            return redirect(url_for('signup'))
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            session.permanent = True  # Keep user logged in
            otp = generate_otp()
            session['otp'] = otp
            session['temp_user_id'] = user.id
            
            email_body = f"""
            <div class='otp-box'>{otp}</div>
            <p>Use the code above to complete your login.</p>
            """
            
            if send_email(user.email, "Login Verification", email_body, is_html=True):
                return redirect(url_for('verify'))
            else:
                flash('Error sending email', 'error')
        else:
            flash('Invalid credentials', 'error')
            
    return render_template('login.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    # Allow if OTP is present and either temp_user (signup) or temp_user_id (login) is present
    if 'otp' not in session or ('temp_user_id' not in session and 'temp_user' not in session):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        user_otp = request.form['otp']
        if user_otp == session.get('otp'):
            
            # Signup Flow
            if 'temp_user' in session:
                user_data = session['temp_user']
                # Check email again just in case
                if User.query.filter_by(email=user_data['email']).first():
                    flash('User already exists', 'error')
                    return redirect(url_for('login'))
                    
                user = User(
                    name=user_data['name'],
                    email=user_data['email'],
                    password=user_data['password'],
                    is_verified=True
                )
                db.session.add(user)
                db.session.commit()
                
                # Cleanup signup session
                session.pop('temp_user', None)

            # Login Flow
            elif 'temp_user_id' in session:
                user = db.session.get(User, session['temp_user_id'])
                if not user:
                     flash('User not found', 'error')
                     return redirect(url_for('login'))
                user.is_verified = True
                db.session.commit()
                
                # Cleanup login session
                session.pop('temp_user_id', None)
            
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['is_admin'] = user.is_admin
            
            session.pop('otp', None)
            
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid OTP', 'error')
            
    return render_template('verify.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('my_orders'))

@app.route('/dashboard/create', methods=['GET', 'POST'])
def create_order():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        waste_types = request.form.getlist('waste_type')
        waste_type = ", ".join(waste_types)
        
        weight = float(request.form['weight'])
        pickup_date = request.form['pickup_date']
        pickup_slot = request.form['pickup_slot'] 
        
        # Handle address - either selected from saved or new
        address_id = request.form.get('address_id')
        if address_id and address_id != 'new':
            address = Address.query.get(int(address_id))
            pickup_address = f"{address.street_address}, {address.landmark}, {address.state}" if address.landmark else f"{address.street_address}, {address.state}"
            pincode = address.pincode
        else:
            # New address
            street_address = request.form['street_address']
            landmark = request.form.get('landmark', '')
            state = request.form['state']
            pincode = request.form['pincode']
            pickup_address = f"{street_address}, {landmark}, {state}" if landmark else f"{street_address}, {state}"
            
            # Save address if checkbox is checked
            if request.form.get('save_address') == 'on':
                is_first = Address.query.filter_by(user_id=session['user_id']).count() == 0
                new_address = Address(
                    user_id=session['user_id'],
                    street_address=street_address,
                    landmark=landmark,
                    state=state,
                    pincode=pincode,
                    is_default=is_first
                )
                db.session.add(new_address)
                db.session.commit()

        session['temp_order'] = {
            'waste_type': waste_type,
            'weight': weight,
            'pickup_date': pickup_date,
            'pickup_slot': pickup_slot,
            'pickup_address': pickup_address,
            'pincode': pincode
        }
        
        otp = generate_otp()
        session['order_otp'] = otp
        user = db.session.get(User, session['user_id'])
        
        if not user:
            flash('User session expired. Please log in again.', 'error')
            return redirect(url_for('login'))
        
        email_body = f"""
        <div class='otp-box'>{otp}</div>
        <p>Use the code above to verify your recycling order.</p>
        <p><strong>Details:</strong><br>
        Type: {waste_type}<br>
        Weight: {weight}kg<br>
        Pickup Date: {pickup_date}<br>
        Time Slot: {pickup_slot}</p>
        """
        
        if send_email(user.email, "Confirm Recycling Order", email_body, is_html=True):
            return redirect(url_for('verify_order'))
        else:
            flash('Error sending OTP', 'error')
            

    today = datetime.date.today()
    next_day = today + timedelta(days=1)
    pickup_date_str = next_day.strftime('%d-%m-%Y')
    slots = ["9:00 AM - 10:00 AM", "6:00 PM - 7:00 PM"]
    assigned_slot = random.choice(slots)
    
    user = db.session.get(User, session['user_id'])
    saved_addresses = Address.query.filter_by(user_id=session['user_id']).order_by(Address.is_default.desc()).all()
    
    return render_template('create_order.html', active_page='create', 
                           pickup_date=pickup_date_str, 
                           assigned_slot=assigned_slot,
                           user=user,
                           saved_addresses=saved_addresses)

@app.route('/dashboard/create/verify', methods=['GET', 'POST'])
def verify_order():
    if 'user_id' not in session or 'temp_order' not in session:
        return redirect(url_for('create_order'))
        
    if request.method == 'POST':
        otp = request.form['otp']
        if otp == session.get('order_otp'):
            order_data = session['temp_order']
            


            batch_num = generate_batch_id()
            
            new_order = Order(
                user_id=session['user_id'],
                waste_type=order_data['waste_type'],
                weight=order_data['weight'],
                pickup_date=order_data['pickup_date'],
                pickup_slot=order_data.get('pickup_slot'), # Save slot
                pickup_address=order_data['pickup_address'],
                pincode=order_data['pincode'],
                status='Pending',
                batch_number=batch_num
            )
            db.session.add(new_order)
            

            user = db.session.get(User, session['user_id'])
            if not user.address:
                user.address = order_data['pickup_address']
                
            db.session.commit()
            

            email_body = f"""
            <p>Your recycling order <strong>#{new_order.id}</strong> has been confirmed.</p>
            <p><strong>Batch Number:</strong> {batch_num}</p>
            <p><strong>Pickup Date:</strong> {new_order.pickup_date}</p>
            <p>Our team will reach out to you shortly.</p>
            """
            send_email(user.email, "Order Confirmed", email_body, is_html=True)
            
            session.pop('temp_order', None)
            session.pop('order_otp', None)
            
            flash(f'Order placed successfully! Batch #{batch_num}', 'success')
            return redirect(url_for('my_orders'))
        else:
            flash('Invalid OTP', 'error')
            
    return render_template('verify_order.html', active_page='create')

@app.route('/dashboard/orders')
def my_orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', active_page='orders', orders=user_orders)

@app.route('/dashboard/payments')
def payments():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    


    # Use user.balance as the source of truth
    available_balance = user.balance
    
    # Calculate stats for display only
    paid_out_orders = Order.query.filter_by(user_id=session['user_id'], status='Money Sent').all()
    # Note: 'Money Sent' orders contribute to lifetime earnings.
    # Payouts are now tracked in PayoutRequest, so 'total_paid' should probably reflect PayoutRequests that are processed?
    # Or keep it as "Value of orders that have been processed". 
    # Let's keep total_earnings as sum of all Money Sent orders.
    total_lifetime_earnings = sum(o.amount_paid for o in paid_out_orders)
    
    # Total Withdrawn (PayoutRequests processed)
    processed_payouts = PayoutRequest.query.filter_by(user_id=session['user_id'], status='Processed').all()
    total_withdrawn = sum(p.amount for p in processed_payouts)
            
    # Check if payout requested today (UTC)
    now_utc = datetime.datetime.utcnow()
    start_of_day_utc = datetime.datetime(now_utc.year, now_utc.month, now_utc.day)
    
    # Check for PENDING payouts (not just today's payouts)
    # User can't request if they have a pending payout
    pending_payout = PayoutRequest.query.filter_by(user_id=user.id, status='Pending').first()
    can_request_payout = pending_payout is None and available_balance > 0
    
    payment_methods = PaymentMethod.query.filter_by(user_id=user.id).all()
    
    # Get all withdrawal requests
    withdrawal_requests = PayoutRequest.query.filter_by(user_id=user.id).order_by(PayoutRequest.requested_at.desc()).all()
            
    return render_template('payments.html', active_page='payments', 
                           user=user, 
                           total_earnings=total_lifetime_earnings,
                           total_paid=total_withdrawn,
                           available_balance=available_balance,
                           orders=paid_out_orders,
                           payment_methods=payment_methods,
                           can_request_payout=can_request_payout,
                           withdrawals=withdrawal_requests,
                           now=now_utc)

@app.route('/dashboard/payments/add', methods=['POST'])
def add_payment_method():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    method_type = request.form['method_type']
    account_holder = request.form['account_holder_name']
    
    if method_type == 'bank':
        bank_name = request.form['bank_name']
        account_number = request.form['account_number']
        ifsc = request.form['ifsc_code']
        
        new_method = PaymentMethod(
            user_id=session['user_id'],
            method_type='bank',
            account_holder_name=account_holder,
            bank_name=bank_name,
            account_number=account_number,
            ifsc_code=ifsc
        )
    elif method_type == 'upi':
        upi_id = request.form['upi_id']
        new_method = PaymentMethod(
            user_id=session['user_id'],
            method_type='upi',
            account_holder_name=account_holder,
            upi_id=upi_id
        )
    else:
        flash('Invalid method type', 'error')
        return redirect(url_for('payments'))
        
    db.session.add(new_method)
    db.session.commit()
    flash('Payment method added successfully', 'success')
    return redirect(url_for('payments'))

@app.route('/dashboard/payments/delete/<int:method_id>', methods=['POST'])
def delete_payment_method(method_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    method = db.session.get(PaymentMethod, method_id)
    if method and method.user_id == session['user_id']:
        db.session.delete(method)
        db.session.commit()
        flash('Payment method removed', 'success')
    else:
        flash('Method not found or access denied', 'error')
        
    return redirect(url_for('payments'))

@app.route('/dashboard/payments/payout', methods=['POST'])
def request_payout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    method_id = request.form['payment_method_id']
    amount = float(request.form.get('amount', 0)) # Or handle total balance
    
    # Simpler: Request full available balance logic or specific amount? 
    # Requirement says "manual payout... send the money". Let's assume full available balance for now or amount logic.
    # Looking at payments route calculation, available_balance is calculated dynamically.
    
    # Recalculate available balance to be safe
    all_paid_orders = Order.query.filter_by(user_id=session['user_id'], status='Money Sent').all()
    current_av_bal = 0
    now = datetime.datetime.utcnow()
    for o in all_paid_orders:
        if not (o.payout_due_date and o.payout_due_date < now): # If NOT already paid out (this logic in payments route was weird actually)
            # Wait, the payments route logic was:
            # if payout_due_date < now: paid_out_amount += amount
            # else: available_balance += amount
            # This implies 'Money Sent' + passed due date = Paid Out. 
            # But we are adding manual payout. 
            # We need to change how available balance is tracked. 
            # For now, let's stick to user.balance which I saw in update_order_status
            pass

    # Actually, update_order_status increments user.balance!
    # "order.user.balance += order.amount_paid"
    # So we can just use user.balance.
    
    if user.balance <= 0:
         flash('Insufficient balance', 'error')
         return redirect(url_for('payments'))

    # Check daily limit (UTC)
    now_utc = datetime.datetime.utcnow()
    start_of_day_utc = datetime.datetime(now_utc.year, now_utc.month, now_utc.day)
    
    if PayoutRequest.query.filter_by(user_id=user.id).filter(PayoutRequest.requested_at >= start_of_day_utc).first():
        flash('You have already requested a payout today. Please wait for 24 hours.', 'error')
        return redirect(url_for('payments'))

    method = db.session.get(PaymentMethod, method_id)
    if not method or method.user_id != user.id:
        flash('Invalid payment method', 'error')
        return redirect(url_for('payments'))
        
    amount_to_withdraw = user.balance
    
    # Snapshot details
    details = f"{method.method_type.upper()}: {method.account_holder_name}"
    if method.method_type == 'bank':
        details += f" | {method.bank_name} - {method.account_number} ({method.ifsc_code})"
    else:
        details += f" | {method.upi_id}"
        
    payout = PayoutRequest(
        user_id=user.id,
        amount=amount_to_withdraw,
        status='Pending',
        payment_method_snapshot=details
    )
    
    user.balance = 0 # Deduct immediately
    db.session.add(payout)
    db.session.commit()
    
    flash(f'Payout request for ₹{amount_to_withdraw} submitted.', 'success')
    return redirect(url_for('payments'))

@app.route('/admin/payouts')
def admin_payouts():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    requests = PayoutRequest.query.order_by(PayoutRequest.requested_at.desc()).all()
    return render_template('admin_payouts.html', requests=requests)

@app.route('/admin/payouts/<int:payout_id>/update', methods=['POST'])
def update_payout_status(payout_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    payout = db.session.get(PayoutRequest, payout_id)
    if not payout:
        abort(404)
        
    action = request.form['action'] # 'process' or 'reject'
    
    if action == 'process':
        payout.status = 'Processed'
        payout.processed_at = datetime.datetime.utcnow()
        send_email(payout.user.email, "Payout Processed", f"Your payout of ₹{payout.amount} has been processed.")
        flash('Payout marked as processed', 'success')
        
    elif action == 'reject':
        payout.status = 'Rejected'
        payout.processed_at = datetime.datetime.utcnow()
        # Refund
        payout.user.balance += payout.amount
        send_email(payout.user.email, "Payout Rejected", f"Your payout of ₹{payout.amount} was rejected. The amount has been refunded to your wallet.")
        flash('Payout rejected and refunded', 'success')
        
    db.session.commit()
    return redirect(url_for('admin_payouts'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    
    if request.method == 'POST':
        user.name = request.form['name']
        db.session.commit()
        session['user_name'] = user.name
        flash('Profile updated successfully', 'success')
        
    return render_template('profile.html', user=user)


@app.route('/settings', methods=['GET'])
def settings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('settings.html')

@app.route('/settings/password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = db.session.get(User, session['user_id'])
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    
    if check_password_hash(user.password, current_password):
        user.password = generate_password_hash(new_password)
        db.session.commit()
        send_email(user.email, "Security Alert", "Your Eco-Recycler password has been changed.")
        flash('Password changed successfully', 'success')
    else:
        flash('Incorrect current password', 'error')
        
    return redirect(url_for('settings'))

@app.route('/settings/email', methods=['POST'])
def change_email():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    new_email = request.form['new_email']
    if User.query.filter_by(email=new_email).first():
        flash('Email already in use', 'error')
        return redirect(url_for('settings'))
        
    otp = generate_otp()
    session['email_change_otp'] = otp
    session['new_email_request'] = new_email
    
    email_body = f"""
    <div class='otp-box'>{otp}</div>
    <p>Use the code above to verify your new email address.</p>
    """
    
    if send_email(new_email, "Verify New Email", email_body, is_html=True):
        flash('OTP sent to new email', 'info')
    else:
        flash('Error sending OTP', 'error')
    return redirect(url_for('verify_email_change'))

@app.route('/settings/email/verify', methods=['GET', 'POST'])
def verify_email_change():
    if 'user_id' not in session or 'new_email_request' not in session:
        return redirect(url_for('settings'))
        
    if request.method == 'POST':
        otp = request.form['otp']
        if otp == session.get('email_change_otp'):
            user = db.session.get(User, session['user_id'])
            old_email = user.email
            new_email = session['new_email_request']
            
            user.email = new_email
            db.session.commit()
            

            send_email(old_email, "Security Alert", f"Your email address has been changed to {new_email}.")
            send_email(new_email, "Email Changed", "Your email address has been successfully updated.")
            
            session.pop('email_change_otp', None)
            session.pop('new_email_request', None)
            
            flash('Email updated successfully', 'success')
            return redirect(url_for('settings'))
        else:
            flash('Invalid OTP', 'error')
            
    return render_template('verify_order.html')

@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin.html', orders=orders)

@app.route('/api/my_orders')
def api_my_orders():
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
    orders = Order.query.filter_by(user_id=session['user_id']).all()
    return {
        'orders': [{
            'id': o.id,
            'status': o.status,
            'amount_paid': o.amount_paid,
            'batch_number': o.batch_number
        } for o in orders]
    }

@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
def update_order_status(order_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))
        
    order = db.session.get(Order, order_id)
    if not order:
        abort(404)
    new_status = request.form['status']
    order.status = new_status
    
    email_body = f"<p>Your order <strong>#{order.id}</strong> status has been updated to: <strong>{new_status}</strong>.</p>"
    
    if new_status == 'Money Sent':
        try:
            total_amount = float(request.form['total_amount'])
            order.amount_calculated = total_amount
            order.amount_paid = total_amount * 0.40
            order.money_sent_date = datetime.datetime.utcnow()
            order.payout_due_date = datetime.datetime.utcnow() + timedelta(days=7)
            order.is_paid_out = False
            

            order.user.balance += order.amount_paid
            
            email_body += f"""
            <p><strong>Amount Credited: ₹{order.amount_paid}</strong>.</p>
            <p>This amount has been added to your available balance.</p>
            <p>Automatic payout to your bank account is scheduled for: <strong>{order.payout_due_date.strftime('%d-%m-%Y')}</strong>.</p>
            """
        except (ValueError, KeyError):
            flash('Invalid Amount', 'error')
            return redirect(url_for('admin_dashboard'))
            
    db.session.commit()
    

    send_email(order.user.email, f"Order Update: {new_status}", email_body, is_html=True)
    flash(f'Order #{order.id} updated to {new_status}', 'success')
    
    return redirect(url_for('admin_dashboard'))

# Address Management Routes
@app.route('/profile/addresses/add', methods=['POST'])
def add_address():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    street_address = request.form.get('street_address')
    landmark = request.form.get('landmark', '')
    state = request.form.get('state')
    pincode = request.form.get('pincode')
    is_default = request.form.get('is_default') == 'on'
    
    if is_default:
        Address.query.filter_by(user_id=session['user_id'], is_default=True).update({'is_default': False})
    
    if Address.query.filter_by(user_id=session['user_id']).count() == 0:
        is_default = True
    
    new_address = Address(
        user_id=session['user_id'],
        street_address=street_address,
        landmark=landmark,
        state=state,
        pincode=pincode,
        is_default=is_default
    )
    
    db.session.add(new_address)
    db.session.commit()
    
    flash('Address added successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/addresses/delete/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    address = Address.query.get(address_id)
    if not address or address.user_id != session['user_id']:
        flash('Address not found', 'error')
        return redirect(url_for('profile'))
    
    was_default = address.is_default
    db.session.delete(address)
    db.session.commit()
    
    if was_default:
        first_address = Address.query.filter_by(user_id=session['user_id']).first()
        if first_address:
            first_address.is_default = True
            db.session.commit()
    
    flash('Address deleted successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/addresses/set-default/<int:address_id>', methods=['POST'])
def set_default_address(address_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    address = Address.query.get(address_id)
    if not address or address.user_id != session['user_id']:
        flash('Address not found', 'error')
        return redirect(url_for('profile'))
    
    Address.query.filter_by(user_id=session['user_id'], is_default=True).update({'is_default': False})
    address.is_default = True
    db.session.commit()
    
    flash('Default address updated!', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/addresses/edit/<int:address_id>', methods=['POST'])
def edit_address(address_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    address = Address.query.get(address_id)
    if not address or address.user_id != session['user_id']:
        flash('Address not found', 'error')
        return redirect(url_for('profile'))
    
    address.street_address = request.form.get('street_address')
    address.landmark = request.form.get('landmark', '')
    address.state = request.form.get('state')
    address.pincode = request.form.get('pincode')
    
    is_default = request.form.get('is_default') == 'on'
    if is_default and not address.is_default:
        Address.query.filter_by(user_id=session['user_id'], is_default=True).update({'is_default': False})
        address.is_default = True
    
    db.session.commit()
    
    flash('Address updated successfully!', 'success')
    return redirect(url_for('profile'))

@app.route('/api/addresses/<int:address_id>')
def get_address(address_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    address = Address.query.get(address_id)
    if not address or address.user_id != session['user_id']:
        return jsonify({'error': 'Address not found'}), 404
    
    return jsonify({
        'id': address.id,
        'street_address': address.street_address,
        'landmark': address.landmark,
        'state': address.state,
        'pincode': address.pincode,
        'is_default': address.is_default
    })

# Real-time API Endpoints
@app.route('/api/admin/orders')
def api_admin_orders():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = db.session.get(User, session['user_id'])
    if not user or not user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return jsonify({
        'orders': [{
            'id': o.id,
            'user_email': o.user.email,
            'waste_type': o.waste_type,
            'weight': o.weight,
            'status': o.status,
            'amount_paid': o.amount_paid,
            'created_at': o.created_at.strftime('%d-%m-%Y %H:%M')
        } for o in orders]
    })

@app.route('/api/admin/payouts')
def api_admin_payouts():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user = db.session.get(User, session['user_id'])
    if not user or not user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    
    payouts = PayoutRequest.query.order_by(PayoutRequest.requested_at.desc()).all()
    return jsonify({
        'payouts': [{
            'id': p.id,
            'user_email': p.user.email,
            'amount': p.amount,
            'status': p.status,
            'requested_at': p.requested_at.strftime('%d-%m-%Y %H:%M')
        } for p in payouts]
    })

@app.route('/api/user/orders')
def api_user_orders():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return jsonify({
        'orders': [{
            'id': o.id,
            'waste_type': o.waste_type,
            'weight': o.weight,
            'status': o.status,
            'amount_paid': o.amount_paid,
            'created_at': o.created_at.strftime('%d-%m-%Y %H:%M')
        } for o in orders]
    })

@app.route('/api/user/payouts')
def api_user_payouts():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    payouts = PayoutRequest.query.filter_by(user_id=session['user_id']).order_by(PayoutRequest.requested_at.desc()).all()
    return jsonify({
        'payouts': [{
            'id': p.id,
            'amount': p.amount,
            'status': p.status,
            'requested_at': p.requested_at.strftime('%d-%m-%Y %H:%M')
        } for p in payouts]
    })

if __name__ == '__main__':
    # Start Cloudflare Tunnel in the main process (not reloader)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        print(" * Starting Cloudflare Tunnel...")
        # Use Popen to run in background
        subprocess.Popen(['cloudflared', 'tunnel', '--config', 'config.yml', 'run'])
        
    app.run(debug=True)