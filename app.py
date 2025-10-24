from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'petronet-green-rewards-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///petronet_rewards.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==================== DATABASE MODELS ====================

class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    card_id = db.Column(db.String(50), unique=True, nullable=False)
    industry = db.Column(db.String(100))
    location = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    total_points = db.Column(db.Float, default=0)
    total_spent = db.Column(db.Float, default=0)
    total_redeemed = db.Column(db.Float, default=0)
    co2_saved = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    purchases = db.relationship('Purchase', backref='business', lazy=True, cascade='all, delete-orphan')
    redemptions = db.relationship('Redemption', backref='business', lazy=True, cascade='all, delete-orphan')
    statements = db.relationship('Statement', backref='business', lazy=True, cascade='all, delete-orphan')

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    purchase_amount = db.Column(db.Float, nullable=False)
    lng_quantity = db.Column(db.Float, nullable=False)  # in metric tons
    points_earned = db.Column(db.Float, default=0)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='completed')  # pending, completed
    
class Redemption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    points_redeemed = db.Column(db.Float, nullable=False)
    amount_credited = db.Column(db.Float, nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'))
    redemption_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='applied')

class Statement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    period_start = db.Column(db.DateTime)
    period_end = db.Column(db.DateTime)
    points_earned = db.Column(db.Float, default=0)
    points_redeemed = db.Column(db.Float, default=0)
    co2_saved = db.Column(db.Float, default=0)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== AUTHENTICATION ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'business_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'business_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        
        if Business.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already registered'}), 400
        
        # Generate unique card ID
        card_id = f"PGR-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}" # kejwf
        
        business = Business(
            business_name=data['business_name'],
            email=data['email'],
            password=generate_password_hash(data['password']),
            card_id=card_id,
            industry=data.get('industry'),
            location=data.get('location'),
            phone=data.get('phone')
        )
        
        db.session.add(business)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'card_id': card_id
        }), 201
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        business = Business.query.filter_by(email=data['email']).first()
        
        if business and check_password_hash(business.password, data['password']):
            session['business_id'] = business.id
            session['business_name'] = business.business_name
            return jsonify({'success': True}), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================

@app.route('/dashboard')
@login_required
def dashboard():
    business = Business.query.get(session['business_id'])
    
    # Calculate statistics
    recent_purchases = Purchase.query.filter_by(business_id=business.id).order_by(Purchase.purchase_date.desc()).limit(5).all()
    total_purchases = len(Purchase.query.filter_by(business_id=business.id).all())
    
    # Calculate CO2 saved (1 metric ton LNG ≈ 2.75 metric tons CO2 avoided)
    total_lng = sum([p.lng_quantity for p in Purchase.query.filter_by(business_id=business.id).all()])
    co2_saved = total_lng * 2.75
    business.co2_saved = co2_saved
    db.session.commit()
    
    return render_template('dashboard.html', 
                         business=business,
                         recent_purchases=recent_purchases,
                         total_purchases=total_purchases)

# ==================== PURCHASE MANAGEMENT ====================

@app.route('/api/record-purchase', methods=['POST'])
@login_required
def record_purchase():
    data = request.get_json()
    business = Business.query.get(session['business_id'])
    
    purchase_amount = float(data['purchase_amount'])
    lng_quantity = float(data['lng_quantity'])
    
    # Calculate 2% points
    points_earned = purchase_amount * 0.02
    
    purchase = Purchase(
        business_id=business.id,
        purchase_amount=purchase_amount,
        lng_quantity=lng_quantity,
        points_earned=points_earned,
        status='pending'
    )
    
    db.session.add(purchase)
    db.session.commit()
    
    # Simulate 24-48 hour processing
    purchase.status = 'completed'
    business.total_points += points_earned
    business.total_spent += purchase_amount
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Purchase recorded successfully',
        'points_earned': points_earned,
        'purchase_id': purchase.id
    }), 201

@app.route('/api/purchases')
@login_required
def get_purchases():
    business_id = session['business_id']
    purchases = Purchase.query.filter_by(business_id=business_id).order_by(Purchase.purchase_date.desc()).all()
    
    return jsonify([{
        'id': p.id,
        'amount': p.purchase_amount,
        'lng_quantity': p.lng_quantity,
        'points_earned': p.points_earned,
        'date': p.purchase_date.strftime('%Y-%m-%d %H:%M'),
        'status': p.status
    } for p in purchases])

# ==================== POINTS & REDEMPTION ====================

@app.route('/api/redeem-points', methods=['POST'])
@login_required
def redeem_points():
    data = request.get_json()
    business = Business.query.get(session['business_id'])
    
    points_to_redeem = float(data['points'])
    
    if points_to_redeem > business.total_points:
        return jsonify({'error': 'Insufficient points'}), 400
    
    # 1 point = 1 rupee value (can be adjusted)
    amount_credited = points_to_redeem
    
    redemption = Redemption(
        business_id=business.id,
        points_redeemed=points_to_redeem,
        amount_credited=amount_credited,
        status='applied'
    )
    
    business.total_points -= points_to_redeem
    business.total_redeemed += amount_credited
    
    db.session.add(redemption)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Points redeemed successfully',
        'amount_credited': amount_credited,
        'remaining_points': business.total_points
    }), 200

@app.route('/api/points-summary')
@login_required
def points_summary():
    business = Business.query.get(session['business_id'])
    
    return jsonify({
        'total_points': business.total_points,
        'total_spent': business.total_spent,
        'total_redeemed': business.total_redeemed,
        'co2_saved': business.co2_saved,
        'card_id': business.card_id
    })

# ==================== STATEMENTS ====================

@app.route('/api/generate-statement', methods=['POST'])
@login_required
def generate_statement():
    business = Business.query.get(session['business_id'])
    
    # Get last 30 days data
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    purchases = Purchase.query.filter(
        Purchase.business_id == business.id,
        Purchase.purchase_date >= thirty_days_ago
    ).all()
    
    redemptions = Redemption.query.filter(
        Redemption.business_id == business.id,
        Redemption.redemption_date >= thirty_days_ago
    ).all()
    
    points_earned = sum([p.points_earned for p in purchases])
    points_redeemed = sum([r.points_redeemed for r in redemptions])
    lng_quantity = sum([p.lng_quantity for p in purchases])
    co2_saved = lng_quantity * 2.75
    
    statement = Statement(
        business_id=business.id,
        period_start=thirty_days_ago,
        period_end=datetime.utcnow(),
        points_earned=points_earned,
        points_redeemed=points_redeemed,
        co2_saved=co2_saved
    )
    
    db.session.add(statement)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'statement': {
            'id': statement.id,
            'period': f"{thirty_days_ago.strftime('%Y-%m-%d')} to {datetime.utcnow().strftime('%Y-%m-%d')}",
            'points_earned': points_earned,
            'points_redeemed': points_redeemed,
            'co2_saved': round(co2_saved, 2),
            'generated_date': statement.generated_date.strftime('%Y-%m-%d %H:%M')
        }
    }), 201

@app.route('/api/statements')
@login_required
def get_statements():
    business_id = session['business_id']
    statements = Statement.query.filter_by(business_id=business_id).order_by(Statement.generated_date.desc()).all()
    
    return jsonify([{
        'id': s.id,
        'period_start': s.period_start.strftime('%Y-%m-%d'),
        'period_end': s.period_end.strftime('%Y-%m-%d'),
        'points_earned': s.points_earned,
        'points_redeemed': s.points_redeemed,
        'co2_saved': round(s.co2_saved, 2),
        'generated_date': s.generated_date.strftime('%Y-%m-%d %H:%M')
    } for s in statements])

# ==================== LEARNING RESOURCES ====================

@app.route('/resources')
@login_required
def resources():
    resources_data = [
        {
            'title': 'Understanding LNG Benefits',
            'description': 'Learn about the environmental and economic benefits of LNG',
            'link': 'https://molgasenergy.com/lng-benefits-discover-its-benefits-and-applications/'
        },
        {
            'title': 'Green Points Guide',
            'description': 'How to maximize your Green Points and redemption value',
            'link': 'https://greenpts.org/'
        },
        {
            'title': 'Carbon Footprint Reduction',
            'description': 'Track your contribution to reducing carbon emissions',
            'link': 'https://www.siemens.com/global/en/products/energy/topics/electrification-x.html?acz=1&gad_source=1&gad_campaignid=21198017406&gbraid=0AAAAADEuPPMdLcA7VPGShp0uU9GEw6pkS&gclid=CjwKCAjwx-zHBhBhEiwA7Kjq67P71VxPc6A6yfj9Kr3kkuTMCzfjXv-tvDbF4KL7WtnVEi8aLfd6jBoCuDMQAvD_BwE'
        },
        {
            'title': 'Sustainability Best Practices',
            'description': 'Industry best practices for sustainable energy consumption',
            'link': 'Sustainability Best Practices'
        }
    ]
    return render_template('resources.html', resources=resources_data)

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
