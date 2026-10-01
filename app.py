from flask import Flask, render_template, request, jsonify
import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'rocha_cafe.db'

app = Flask(__name__)


def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = db_connection()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        document TEXT,
        city TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'sacas',
        quantity REAL NOT NULL DEFAULT 0,
        min_stock REAL NOT NULL DEFAULT 0,
        avg_cost REAL NOT NULL DEFAULT 0,
        sale_price REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        movement_type TEXT NOT NULL CHECK(movement_type IN ('entrada','saida')),
        quantity REAL NOT NULL,
        unit_value REAL NOT NULL DEFAULT 0,
        total_value REAL NOT NULL DEFAULT 0,
        paid_amount REAL NOT NULL DEFAULT 0,
        client_id INTEGER,
        movement_date TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE RESTRICT,
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        direction TEXT NOT NULL CHECK(direction IN ('receber','pagar')),
        description TEXT NOT NULL,
        original_amount REAL NOT NULL,
        paid_amount REAL NOT NULL DEFAULT 0,
        due_date TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS debt_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debt_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(debt_id) REFERENCES debts(id) ON DELETE CASCADE
    );
    ''')
    conn.commit()
    conn.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.get('/api/dashboard')
def dashboard():
    conn = db_connection()
    stock = conn.execute('''
        SELECT COALESCE(SUM(quantity),0) qty,
               COALESCE(SUM(quantity * avg_cost),0) value
        FROM products
    ''').fetchone()
    receive = conn.execute('''
        SELECT COALESCE(SUM(original_amount - paid_amount),0) value
        FROM debts WHERE direction='receber' AND original_amount > paid_amount
    ''').fetchone()['value']
    pay = conn.execute('''
        SELECT COALESCE(SUM(original_amount - paid_amount),0) value
        FROM debts WHERE direction='pagar' AND original_amount > paid_amount
    ''').fetchone()['value']
    clients = conn.execute('SELECT COUNT(*) c FROM clients').fetchone()['c']
    low_stock = conn.execute('SELECT COUNT(*) c FROM products WHERE min_stock > 0 AND quantity <= min_stock').fetchone()['c']
    recent = conn.execute('''
        SELECT sm.id, sm.movement_type, sm.quantity, sm.total_value, sm.movement_date,
               p.name product_name, p.unit, c.name client_name
        FROM stock_movements sm
        JOIN products p ON p.id=sm.product_id
        LEFT JOIN clients c ON c.id=sm.client_id
        ORDER BY sm.movement_date DESC, sm.id DESC LIMIT 8
    ''').fetchall()
    conn.close()
    return jsonify({
        'stock_quantity': stock['qty'],
        'stock_value': stock['value'],
        'to_receive': receive,
        'to_pay': pay,
        'clients': clients,
        'low_stock': low_stock,
        'recent': [dict(r) for r in recent]
    })


@app.route('/api/clients', methods=['GET','POST'])
def clients():
    conn = db_connection()
    if request.method == 'GET':
        q = request.args.get('q','').strip()
        if q:
            rows = conn.execute('''SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? OR document LIKE ? ORDER BY name''',
                                (f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()
        else:
            rows = conn.execute('SELECT * FROM clients ORDER BY name').fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    if not name:
        conn.close(); return jsonify({'error':'Nome é obrigatório'}), 400
    cur = conn.execute('INSERT INTO clients(name,phone,document,city,notes) VALUES(?,?,?,?,?)',
                       (name, data.get('phone',''), data.get('document',''), data.get('city',''), data.get('notes','')))
    conn.commit(); cid = cur.lastrowid; conn.close()
    return jsonify({'id':cid}), 201


@app.route('/api/clients/<int:cid>', methods=['PUT','DELETE'])
def client_detail(cid):
    conn = db_connection()
    if request.method == 'DELETE':
        conn.execute('DELETE FROM clients WHERE id=?', (cid,))
        conn.commit(); conn.close(); return jsonify({'ok':True})
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    if not name:
        conn.close(); return jsonify({'error':'Nome é obrigatório'}), 400
    conn.execute('UPDATE clients SET name=?,phone=?,document=?,city=?,notes=? WHERE id=?',
                 (name, data.get('phone',''), data.get('document',''), data.get('city',''), data.get('notes',''), cid))
    conn.commit(); conn.close(); return jsonify({'ok':True})


@app.route('/api/products', methods=['GET','POST'])
def products():
    conn = db_connection()
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM products ORDER BY name').fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    if not name:
        conn.close(); return jsonify({'error':'Produto é obrigatório'}), 400
    cur = conn.execute('''INSERT INTO products(name,unit,quantity,min_stock,avg_cost,sale_price) VALUES(?,?,?,?,?,?)''',
                       (name, data.get('unit','sacas'), float(data.get('quantity') or 0), float(data.get('min_stock') or 0),
                        float(data.get('avg_cost') or 0), float(data.get('sale_price') or 0)))
    conn.commit(); pid = cur.lastrowid; conn.close(); return jsonify({'id':pid}), 201


@app.route('/api/products/<int:pid>', methods=['PUT','DELETE'])
def product_detail(pid):
    conn = db_connection()
    if request.method == 'DELETE':
        used = conn.execute('SELECT COUNT(*) c FROM stock_movements WHERE product_id=?',(pid,)).fetchone()['c']
        if used:
            conn.close(); return jsonify({'error':'Esse item possui movimentações e não pode ser excluído.'}), 409
        conn.execute('DELETE FROM products WHERE id=?',(pid,)); conn.commit(); conn.close(); return jsonify({'ok':True})
    data = request.get_json(force=True)
    conn.execute('''UPDATE products SET name=?,unit=?,min_stock=?,avg_cost=?,sale_price=? WHERE id=?''',
                 ((data.get('name') or '').strip(), data.get('unit','sacas'), float(data.get('min_stock') or 0),
                  float(data.get('avg_cost') or 0), float(data.get('sale_price') or 0), pid))
    conn.commit(); conn.close(); return jsonify({'ok':True})


@app.route('/api/movements', methods=['GET','POST'])
def movements():
    conn = db_connection()
    if request.method == 'GET':
        rows = conn.execute('''
            SELECT sm.*, p.name product_name, p.unit, c.name client_name
            FROM stock_movements sm
            JOIN products p ON p.id=sm.product_id
            LEFT JOIN clients c ON c.id=sm.client_id
            ORDER BY sm.movement_date DESC, sm.id DESC LIMIT 150
        ''').fetchall(); conn.close()
        return jsonify([dict(r) for r in rows])

    data = request.get_json(force=True)
    try:
        product_id = int(data['product_id'])
        movement_type = data['movement_type']
        quantity = float(data['quantity'])
        unit_value = float(data.get('unit_value') or 0)
        paid_amount = float(data.get('paid_amount') or 0)
    except Exception:
        conn.close(); return jsonify({'error':'Dados inválidos'}), 400
    if movement_type not in ('entrada','saida') or quantity <= 0:
        conn.close(); return jsonify({'error':'Movimentação inválida'}), 400

    product = conn.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
    if not product:
        conn.close(); return jsonify({'error':'Produto não encontrado'}), 404
    if movement_type == 'saida' and product['quantity'] < quantity:
        conn.close(); return jsonify({'error':'Estoque insuficiente para esta saída'}), 409

    total = quantity * unit_value
    client_id = data.get('client_id') or None
    movement_date = data.get('movement_date') or datetime.now().strftime('%Y-%m-%d')
    notes = data.get('notes','')

    cur = conn.execute('''INSERT INTO stock_movements(product_id,movement_type,quantity,unit_value,total_value,paid_amount,client_id,movement_date,notes)
                          VALUES(?,?,?,?,?,?,?,?,?)''',
                       (product_id,movement_type,quantity,unit_value,total,paid_amount,client_id,movement_date,notes))

    if movement_type == 'entrada':
        old_q = float(product['quantity'])
        old_cost = float(product['avg_cost'])
        new_q = old_q + quantity
        new_avg = ((old_q * old_cost) + total) / new_q if new_q > 0 and unit_value > 0 else old_cost
        conn.execute('UPDATE products SET quantity=?, avg_cost=? WHERE id=?',(new_q,new_avg,product_id))
    else:
        conn.execute('UPDATE products SET quantity=quantity-? WHERE id=?',(quantity,product_id))

    balance = max(total - paid_amount, 0)
    if balance > 0.005:
        direction = 'pagar' if movement_type == 'entrada' else 'receber'
        who = conn.execute('SELECT name FROM clients WHERE id=?',(client_id,)).fetchone() if client_id else None
        description = f"{'Compra' if movement_type=='entrada' else 'Venda'} de {quantity:g} {product['unit']} de {product['name']}"
        if who:
            description += f" - {who['name']}"
        conn.execute('INSERT INTO debts(client_id,direction,description,original_amount,paid_amount,due_date) VALUES(?,?,?,?,?,?)',
                     (client_id,direction,description,total,paid_amount,data.get('due_date') or None))

    conn.commit(); mid = cur.lastrowid; conn.close(); return jsonify({'id':mid,'total':total}), 201


@app.route('/api/debts', methods=['GET','POST'])
def debts():
    conn = db_connection()
    if request.method == 'GET':
        direction = request.args.get('direction')
        sql = '''SELECT d.*, c.name client_name, (d.original_amount-d.paid_amount) balance
                 FROM debts d LEFT JOIN clients c ON c.id=d.client_id'''
        args=[]
        if direction in ('receber','pagar'):
            sql += ' WHERE d.direction=?'; args.append(direction)
        sql += ' ORDER BY CASE WHEN d.original_amount>d.paid_amount THEN 0 ELSE 1 END, d.due_date IS NULL, d.due_date, d.id DESC'
        rows = conn.execute(sql,args).fetchall(); conn.close(); return jsonify([dict(r) for r in rows])
    data = request.get_json(force=True)
    direction = data.get('direction','receber')
    if direction not in ('receber','pagar'):
        conn.close(); return jsonify({'error':'Tipo inválido'}),400
    amount = float(data.get('original_amount') or 0)
    if amount <= 0:
        conn.close(); return jsonify({'error':'Valor deve ser maior que zero'}),400
    conn.execute('INSERT INTO debts(client_id,direction,description,original_amount,paid_amount,due_date) VALUES(?,?,?,?,?,?)',
                 (data.get('client_id') or None,direction,data.get('description') or 'Saldo manual',amount,float(data.get('paid_amount') or 0),data.get('due_date') or None))
    conn.commit(); conn.close(); return jsonify({'ok':True}),201


@app.post('/api/debts/<int:debt_id>/pay')
def debt_pay(debt_id):
    data = request.get_json(force=True)
    amount = float(data.get('amount') or 0)
    if amount <= 0: return jsonify({'error':'Valor inválido'}),400
    conn = db_connection()
    debt = conn.execute('SELECT * FROM debts WHERE id=?',(debt_id,)).fetchone()
    if not debt:
        conn.close(); return jsonify({'error':'Saldo não encontrado'}),404
    remaining = float(debt['original_amount']) - float(debt['paid_amount'])
    if amount > remaining + 0.005:
        conn.close(); return jsonify({'error':'Valor maior que o saldo pendente'}),409
    pdate = data.get('payment_date') or datetime.now().strftime('%Y-%m-%d')
    conn.execute('INSERT INTO debt_payments(debt_id,amount,payment_date,notes) VALUES(?,?,?,?)',
                 (debt_id,amount,pdate,data.get('notes','')))
    conn.execute('UPDATE debts SET paid_amount=paid_amount+? WHERE id=?',(amount,debt_id))
    conn.commit(); conn.close(); return jsonify({'ok':True})


@app.delete('/api/debts/<int:debt_id>')
def debt_delete(debt_id):
    conn=db_connection(); conn.execute('DELETE FROM debts WHERE id=?',(debt_id,)); conn.commit(); conn.close(); return jsonify({'ok':True})


@app.get('/api/client-summary/<int:cid>')
def client_summary(cid):
    conn=db_connection()
    client=conn.execute('SELECT * FROM clients WHERE id=?',(cid,)).fetchone()
    if not client:
        conn.close(); return jsonify({'error':'Cliente não encontrado'}),404
    debts=conn.execute('''SELECT *, original_amount-paid_amount balance FROM debts WHERE client_id=? ORDER BY id DESC''',(cid,)).fetchall()
    movements=conn.execute('''SELECT sm.*, p.name product_name,p.unit FROM stock_movements sm JOIN products p ON p.id=sm.product_id WHERE sm.client_id=? ORDER BY movement_date DESC,id DESC''',(cid,)).fetchall()
    conn.close(); return jsonify({'client':dict(client),'debts':[dict(r) for r in debts],'movements':[dict(r) for r in movements]})


@app.get('/health')
def health():
    return jsonify({'status':'ok'})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    init_db()
