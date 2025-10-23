from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os

# -----------------------
# App setup
# -----------------------
app = Flask(__name__)
CORS(app)

base = os.path.dirname(__file__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base, 'grocery.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------
# Models
# -----------------------
class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    category = db.Column(db.String, default='Other')
    max_qty = db.Column(db.Float, default=0.0)
    current_qty = db.Column(db.Float, default=0.0)
    threshold_percent = db.Column(db.Float, default=20.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class ManualList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String, nullable=False)
    qty = db.Column(db.Float, default=1.0)
    regular = db.Column(db.Boolean, default=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, nullable=True)
    change_amount = db.Column(db.Float)
    reason = db.Column(db.String)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# -----------------------
# Helper
# -----------------------
def is_low(item: Item):
    try:
        if item.max_qty <= 0:
            return False
        return (item.current_qty / item.max_qty) <= (item.threshold_percent / 100.0)
    except Exception:
        return False

# -----------------------
# API Routes
# -----------------------
@app.route('/api/items', methods=['GET'])
def get_items():
    items = Item.query.all()
    out = []
    for it in items:
        percent_left = (it.current_qty / it.max_qty * 100) if it.max_qty else 0
        out.append({
            "id": it.id,
            "name": it.name,
            "category": it.category,
            "max_qty": it.max_qty,
            "current_qty": it.current_qty,
            "threshold_percent": it.threshold_percent,
            "percent_left": round(percent_left, 1),
            "low": is_low(it),
            "last_updated": it.last_updated.isoformat()
        })
    return jsonify(out)

@app.route('/api/items', methods=['POST'])
def add_item():
    data = request.json
    it = Item(
        name=data.get('name'),
        category=data.get('category','Other'),
        max_qty=float(data.get('max_qty',0)),
        current_qty=float(data.get('current_qty',0)),
        threshold_percent=float(data.get('threshold_percent',20))
    )
    db.session.add(it)
    db.session.commit()
    return jsonify({"id": it.id}), 201

@app.route('/api/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    data = request.json
    it = Item.query.get_or_404(item_id)
    for k in ('name','category','max_qty','current_qty','threshold_percent'):
        if k in data:
            setattr(it, k, data[k])
    it.last_updated = datetime.utcnow()
    db.session.commit()
    if 'current_qty' in data:
        t = Transaction(item_id=it.id, change_amount=float(data['current_qty']), reason='update')
        db.session.add(t)
        db.session.commit()
    return jsonify({"ok": True})

@app.route('/api/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    it = Item.query.get_or_404(item_id)
    db.session.delete(it)
    db.session.commit()
    return jsonify({"ok": True})

@app.route('/api/shopping-list', methods=['GET'])
def shopping_list():
    items = Item.query.all()
    auto = []
    for it in items:
        if is_low(it):
            auto.append({
                "id": it.id,
                "name": it.name,
                "current_qty": it.current_qty,
                "max_qty": it.max_qty,
                "suggested_qty": max(0, it.max_qty - it.current_qty)
            })
    manual = ManualList.query.filter_by(completed=False).all()
    manual_out = [{"id": m.id, "name": m.item_name, "qty": m.qty, "regular": m.regular} for m in manual]
    return jsonify({"auto": auto, "manual": manual_out})

@app.route('/api/manual-add', methods=['POST'])
def manual_add():
    data = request.json
    m = ManualList(
        item_name=data['name'],
        qty=float(data.get('qty',1)),
        regular=bool(data.get('regular',False))
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({"id": m.id}), 201

@app.route('/api/mark-bought', methods=['POST'])
def mark_bought():
    data = request.json
    if data.get('manual_id'):
        m = ManualList.query.get_or_404(data['manual_id'])
        m.completed = True
        db.session.commit()
        return jsonify({"ok": True})
    if data.get('item_id'):
        it = Item.query.get_or_404(data['item_id'])
        added = float(data.get('add_qty', it.max_qty - it.current_qty))
        it.current_qty += added
        it.last_updated = datetime.utcnow()
        db.session.add(Transaction(item_id=it.id, change_amount=added, reason='bought'))
        db.session.commit()
        return jsonify({"ok": True})
    return jsonify({"error":"no id provided"}), 400

@app.route('/api/items/low', methods=['GET'])
def get_low_items():
    items = Item.query.all()
    low_items = []
    for it in items:
        if is_low(it):
            percent_left = (it.current_qty / it.max_qty * 100) if it.max_qty else 0
            low_items.append({
                "id": it.id,
                "name": it.name,
                "category": it.category,
                "max_qty": it.max_qty,
                "current_qty": it.current_qty,
                "threshold_percent": it.threshold_percent,
                "percent_left": round(percent_left, 1),
                "low": True,
                "last_updated": it.last_updated.isoformat()
            })
    return jsonify(low_items)

# -----------------------
# Frontend Routes
# -----------------------
FRONTEND_DIR = os.path.join(base, '../frontend')

@app.route('/')
def root_redirect():
    # Redirect root to /home
    return redirect('/home')

@app.route('/home')
def home_page():
    return send_from_directory(FRONTEND_DIR, 'home.html')

@app.route('/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(FRONTEND_DIR, filename)

# -----------------------
# Run app
# -----------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
