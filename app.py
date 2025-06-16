from flask import Flask, render_template, request, redirect, session, url_for, flash
from functools import wraps
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

DATA_FILE = 'data.json'

# ---------------------- Global Data ----------------------

users = {
    "admin_1234": {"password": "admin_1234", "is_admin": True}
}
materials = []
stock_logs = []

# ---------------------- Load / Save ----------------------

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'users': users,
            'materials': materials,
            'stock_logs': stock_logs
        }, f, ensure_ascii=False, indent=2)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            users.update(data.get('users', {}))
            materials.clear()
            materials.extend(data.get('materials', []))
            stock_logs.clear()
            stock_logs.extend(data.get('stock_logs', []))

# ---------------------- Helpers ----------------------

def generate_material_code():
    existing_codes = [m.get('code') for m in materials if m.get('code')]
    index = 1
    while True:
        code = f"MAT{index:03}"
        if code not in existing_codes:
            return code
        index += 1

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash("อนุญาตให้เฉพาะแอดมินเท่านั้น")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ---------------------- Routes ----------------------

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users.get(username)
        if user and user['password'] == password:
            session['username'] = username
            session['is_admin'] = user.get('is_admin', False)
            return redirect(url_for('dashboard'))
        flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', username=session['username'])

@app.route('/materials')
@login_required
def materials_view():
    return render_template('materials.html', materials=materials)

@app.route('/edit-material', methods=['GET', 'POST'])
@app.route('/edit-material/<int:index>', methods=['GET', 'POST'])
@admin_required
def edit_material(index=None):
    material = materials[index] if index is not None and index < len(materials) else None

    if request.method == 'POST':
        name = request.form['name']
        try:
            quantity = int(request.form['quantity'])
        except:
            flash("จำนวนต้องเป็นตัวเลข")
            return redirect(request.url)
        unit = request.form['unit']
        code = request.form.get('code', '').strip() or generate_material_code()

        new_material = {
            'name': name,
            'quantity': quantity,
            'unit': unit,
            'code': code
        }

        if material is None:
            if any(m['name'] == name for m in materials):
                flash("มีวัสดุนี้อยู่แล้วในระบบ", "error")
                return redirect(url_for('edit_material'))
            materials.append(new_material)
        else:
            materials[index] = new_material

        save_data()
        return redirect(url_for('materials_view'))

    return render_template('edit_material.html', material=material)

@app.route('/delete-material/<int:index>')
@admin_required
def delete_material(index):
    if index < len(materials):
        materials.pop(index)
        save_data()
    return redirect(url_for('materials_view'))

@app.route('/admin-delete-material/<material_code>', methods=['POST'])
@admin_required
def admin_delete_material(material_code):
    global materials, stock_logs
    materials = [m for m in materials if m['code'] != material_code]
    stock_logs = [log for log in stock_logs if log.get('code') != material_code]
    flash(f"ลบวัสดุ {material_code} และข้อมูลที่เกี่ยวข้องทั้งหมดเรียบร้อยแล้ว", "success")
    save_data()
    return redirect(url_for('admin_page'))

@app.route('/stock-in', methods=['GET', 'POST'])
@admin_required
def stock_in():
    if request.method == 'POST':
        material_code = request.form.get('material_code')
        quantity_str = request.form.get('quantity')

        if not material_code:
            flash('กรุณาเลือกวัสดุ')
            return redirect(url_for('stock_in'))

        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                flash('จำนวนต้องมากกว่า 0')
                return redirect(url_for('stock_in'))
        except:
            flash('กรุณากรอกจำนวนเป็นตัวเลขที่ถูกต้อง')
            return redirect(url_for('stock_in'))

        material = next((m for m in materials if m['code'] == material_code), None)
        if not material:
            flash('ไม่พบวัสดุที่เลือก')
            return redirect(url_for('stock_in'))

        material['quantity'] += quantity

        stock_logs.append({
            'type': 'in',
            'code': material['code'],
            'name': material['name'],
            'quantity': quantity,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        })

        save_data()
        flash(f'บันทึกการรับเข้า {material["name"]} จำนวน {quantity} {material["unit"]} เรียบร้อยแล้ว')
        return redirect(url_for('stock_in'))

    return render_template('stock_in.html', materials=materials, stock_logs=stock_logs)

@app.route('/stock-out', methods=['GET', 'POST'])
@admin_required
def stock_out():
    if request.method == 'POST':
        material_input = request.form.get('material')
        quantity_str = request.form.get('quantity')
        requester = request.form.get('requester', '').strip()
        project = request.form.get('project', '').strip()

        if not material_input:
            flash('กรุณาเลือกวัสดุ')
            return redirect(url_for('stock_out'))

        try:
            material_code = material_input.split(' - ')[0].strip()
        except Exception:
            material_code = material_input.strip()

        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                flash('จำนวนต้องมากกว่า 0')
                return redirect(url_for('stock_out'))
        except:
            flash('กรุณากรอกจำนวนเป็นตัวเลขที่ถูกต้อง')
            return redirect(url_for('stock_out'))

        material = next((m for m in materials if m['code'] == material_code), None)
        if not material:
            flash('ไม่พบวัสดุที่เลือก')
            return redirect(url_for('stock_out'))

        if material['quantity'] < quantity:
            flash(f"จำนวนในคลังไม่พอ (เหลือ {material['quantity']})")
            return redirect(url_for('stock_out'))

        material['quantity'] -= quantity

        stock_logs.append({
            'type': 'out',
            'code': material['code'],
            'name': material['name'],
            'quantity': quantity,
            'requester': requester,
            'project': project,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M')
        })

        save_data()
        flash(f'บันทึกการเบิกออก {material["name"]} จำนวน {quantity} {material["unit"]} เรียบร้อยแล้ว')
        return redirect(url_for('stock_out'))

    return render_template('stock_out.html', materials=materials, stock_logs=stock_logs)

@app.route('/tracking')
@login_required
def tracking():
    return render_template('tracking.html', materials=materials, logs=stock_logs)

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_page():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = request.form['is_admin'] == 'true'

        if username not in users:
            users[username] = {'password': password, 'is_admin': is_admin}
            flash("เพิ่มผู้ใช้เรียบร้อยแล้ว")
            save_data()
        else:
            flash("ผู้ใช้นี้มีอยู่แล้ว")

        return redirect(url_for('admin_page'))

    return render_template('admin.html', users=users, materials=materials)

@app.route('/delete-user/<username>', methods=['POST'])
@admin_required
def delete_user(username):
    current_user = session.get('username')

    if username not in users:
        flash("ไม่พบผู้ใช้ที่ต้องการลบ", "error")
        return redirect(url_for('admin_page'))

    if users[username].get('is_admin'):
        if current_user != 'admin_1234':
            flash("ไม่อนุญาตให้ลบแอดมิน", "error")
            return redirect(url_for('admin_page'))
        if username == 'admin_1234':
            flash("ไม่อนุญาตให้ลบตัวเอง", "error")
            return redirect(url_for('admin_page'))

    users.pop(username)
    flash(f"ลบผู้ใช้ {username} เรียบร้อยแล้ว")
    save_data()
    return redirect(url_for('admin_page'))

# ---------------------- Main ----------------------
load_data()
if __name__ == '__main__':

    app.run(host='0.0.0.0', port=5000, debug=True)
