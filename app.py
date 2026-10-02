from flask import Flask, render_template, request, jsonify
import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('ROCHA_DATA_DIR', '/data'))
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    test_file = DATA_DIR / '.write-test'
    test_file.write_text('ok')
    test_file.unlink(missing_ok=True)
except Exception:
    DATA_DIR = BASE_DIR
DB_PATH = DATA_DIR / 'rocha_cafe.db'
LEGACY_DB_PATH = BASE_DIR / 'rocha_cafe.db'

# Migração simples para instalações locais/antigas em que o arquivo legado ainda exista.
# Em produção, /data deve ser um volume persistente no Coolify.
if DB_PATH != LEGACY_DB_PATH and not DB_PATH.exists() and LEGACY_DB_PATH.exists():
    try:
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)
    except Exception:
        pass

app = Flask(__name__)


def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 5000')
    return conn



def _table_columns(conn, table):
    return {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _movement_description(product_name, unit, movement_type, quantity, client_name=None):
    text = f"{'Compra' if movement_type == 'entrada' else 'Venda'} de {quantity:g} {unit} de {product_name}"
    if client_name:
        text += f" - {client_name}"
    return text


def _money_br(value):
    formatted = f"{float(value or 0):,.2f}"
    return 'R$ ' + formatted.replace(',', '#').replace('.', ',').replace('#', '.')


def _date_br(value):
    if not value:
        return '—'
    try:
        return datetime.strptime(value, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return str(value)


def _initial_cost_for_target(conn, product_id, initial_qty, target_avg):
    """Infer an opening cost that reproduces the current average for migrated databases."""
    qty = float(initial_qty or 0)
    a, b = 1.0, 0.0
    rows = conn.execute("SELECT movement_type, quantity, unit_value FROM stock_movements WHERE product_id=? ORDER BY id", (product_id,)).fetchall()
    for row in rows:
        q = float(row['quantity'] or 0)
        if row['movement_type'] == 'entrada':
            new_qty = qty + q
            unit = float(row['unit_value'] or 0)
            if new_qty > 0 and unit > 0:
                factor = qty / new_qty
                a = factor * a
                b = factor * b + (q * unit) / new_qty
            qty = new_qty
        else:
            qty -= q
    if abs(a) > 1e-9:
        return (float(target_avg or 0) - b) / a
    return float(target_avg or 0)


def _recalculate_product(conn, product_id):
    product = conn.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
    if not product:
        raise ValueError('Produto não encontrado')
    qty = float(product['initial_quantity'] or 0)
    avg = float(product['initial_cost'] or 0)
    rows = conn.execute("SELECT movement_type, quantity, unit_value FROM stock_movements WHERE product_id=? ORDER BY id", (product_id,)).fetchall()
    for row in rows:
        q = float(row['quantity'] or 0)
        unit = float(row['unit_value'] or 0)
        if row['movement_type'] == 'entrada':
            new_qty = qty + q
            if new_qty > 0 and unit > 0:
                avg = ((qty * avg) + (q * unit)) / new_qty
            qty = new_qty
        else:
            qty -= q
            if qty < -0.005:
                raise ValueError('Essa alteração deixaria o estoque negativo. Confira a quantidade da saída.')
    if abs(qty) < 0.005:
        qty = 0.0
    conn.execute('UPDATE products SET quantity=?, avg_cost=? WHERE id=?', (qty, avg, product_id))
    return qty, avg


def _find_or_link_movement_debt(conn, movement, product):
    debt = conn.execute('SELECT * FROM debts WHERE movement_id=? ORDER BY id LIMIT 1', (movement['id'],)).fetchone()
    if debt:
        return debt
    client_name = None
    if movement['client_id']:
        who = conn.execute('SELECT name FROM clients WHERE id=?', (movement['client_id'],)).fetchone()
        client_name = who['name'] if who else None
    description = _movement_description(product['name'], product['unit'], movement['movement_type'], float(movement['quantity']), client_name)
    direction = 'pagar' if movement['movement_type'] == 'entrada' else 'receber'
    if movement['client_id']:
        candidates = conn.execute(
            'SELECT * FROM debts WHERE movement_id IS NULL AND direction=? AND client_id=? AND ABS(original_amount-?) < 0.01 AND description=? ORDER BY id',
            (direction, movement['client_id'], float(movement['total_value']), description)
        ).fetchall()
    else:
        candidates = conn.execute(
            'SELECT * FROM debts WHERE movement_id IS NULL AND direction=? AND client_id IS NULL AND ABS(original_amount-?) < 0.01 AND description=? ORDER BY id',
            (direction, float(movement['total_value']), description)
        ).fetchall()
    if len(candidates) == 1:
        conn.execute('UPDATE debts SET movement_id=? WHERE id=?', (movement['id'], candidates[0]['id']))
        return conn.execute('SELECT * FROM debts WHERE id=?', (candidates[0]['id'],)).fetchone()
    return None

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

    # Lightweight migrations for databases created by earlier app versions.
    product_cols = _table_columns(conn, 'products')
    if 'initial_quantity' not in product_cols:
        conn.execute('ALTER TABLE products ADD COLUMN initial_quantity REAL')
    if 'initial_cost' not in product_cols:
        conn.execute('ALTER TABLE products ADD COLUMN initial_cost REAL')

    debt_cols = _table_columns(conn, 'debts')
    if 'movement_id' not in debt_cols:
        conn.execute('ALTER TABLE debts ADD COLUMN movement_id INTEGER')
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_debts_movement_id ON debts(movement_id) WHERE movement_id IS NOT NULL')

    movement_cols = _table_columns(conn, 'stock_movements')
    if 'payment_condition' not in movement_cols:
        conn.execute("ALTER TABLE stock_movements ADD COLUMN payment_condition TEXT DEFAULT 'aprazo'")
        conn.execute("UPDATE stock_movements SET payment_condition = CASE WHEN COALESCE(paid_amount,0) >= COALESCE(total_value,0) - 0.005 THEN 'avista' ELSE 'aprazo' END")
    else:
        conn.execute("UPDATE stock_movements SET payment_condition = CASE WHEN COALESCE(paid_amount,0) >= COALESCE(total_value,0) - 0.005 THEN 'avista' ELSE 'aprazo' END WHERE payment_condition IS NULL OR payment_condition NOT IN ('avista','aprazo')")

    # Infer an opening balance for existing products without changing their visible current balance/cost.
    products_to_migrate = conn.execute('SELECT * FROM products WHERE initial_quantity IS NULL OR initial_cost IS NULL').fetchall()
    for product in products_to_migrate:
        flow = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN movement_type='entrada' THEN quantity ELSE -quantity END),0) net FROM stock_movements WHERE product_id=?",
            (product['id'],)
        ).fetchone()['net']
        opening_qty = float(product['quantity'] or 0) - float(flow or 0)
        if abs(opening_qty) < 0.005:
            opening_qty = 0.0
        opening_cost = _initial_cost_for_target(conn, product['id'], opening_qty, float(product['avg_cost'] or 0))
        conn.execute('UPDATE products SET initial_quantity=?, initial_cost=? WHERE id=?',
                     (opening_qty, opening_cost, product['id']))

    # Link automatic debts created by previous versions whenever the match is unambiguous.
    old_movements = conn.execute('SELECT * FROM stock_movements ORDER BY id').fetchall()
    for movement in old_movements:
        product = conn.execute('SELECT * FROM products WHERE id=?', (movement['product_id'],)).fetchone()
        if product:
            _find_or_link_movement_debt(conn, movement, product)

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
    products = conn.execute('SELECT COUNT(*) c FROM products').fetchone()['c']
    low_stock = conn.execute('SELECT COUNT(*) c FROM products WHERE min_stock > 0 AND quantity <= min_stock').fetchone()['c']
    month_key = datetime.now().strftime('%Y-%m')
    month_values = conn.execute('''
        SELECT
            COALESCE(SUM(CASE WHEN movement_type='entrada' THEN total_value ELSE 0 END),0) month_in,
            COALESCE(SUM(CASE WHEN movement_type='saida' THEN total_value ELSE 0 END),0) month_out
        FROM stock_movements
        WHERE substr(movement_date,1,7)=?
    ''', (month_key,)).fetchone()
    recent = conn.execute('''
        SELECT sm.id, sm.movement_type, sm.quantity, sm.total_value, sm.movement_date,
               p.name product_name, p.unit, c.name client_name
        FROM stock_movements sm
        JOIN products p ON p.id=sm.product_id
        LEFT JOIN clients c ON c.id=sm.client_id
        ORDER BY sm.movement_date DESC, sm.id DESC LIMIT 8
    ''').fetchall()

    month_counts = conn.execute('''
        SELECT
          SUM(CASE WHEN movement_type='entrada' THEN 1 ELSE 0 END) entries,
          SUM(CASE WHEN movement_type='saida' THEN 1 ELSE 0 END) sales,
          COALESCE(AVG(CASE WHEN movement_type='saida' THEN total_value END),0) avg_ticket
        FROM stock_movements WHERE substr(movement_date,1,7)=?
    ''', (month_key,)).fetchone()

    top_product = conn.execute('''
        SELECT p.name, p.unit, COALESCE(SUM(sm.quantity),0) qty, COALESCE(SUM(sm.total_value),0) total
        FROM stock_movements sm JOIN products p ON p.id=sm.product_id
        WHERE sm.movement_type='saida' AND substr(sm.movement_date,1,7)=?
        GROUP BY p.id ORDER BY total DESC LIMIT 1
    ''', (month_key,)).fetchone()
    top_client = conn.execute('''
        SELECT c.name, COALESCE(SUM(sm.total_value),0) total
        FROM stock_movements sm JOIN clients c ON c.id=sm.client_id
        WHERE sm.movement_type='saida' AND substr(sm.movement_date,1,7)=?
        GROUP BY c.id ORDER BY total DESC LIMIT 1
    ''', (month_key,)).fetchone()

    # Série dos últimos 6 meses para o gráfico executivo.
    series = []
    cursor = datetime.now().replace(day=1)
    for i in range(5, -1, -1):
        year = cursor.year
        month = cursor.month - i
        while month <= 0:
            month += 12
            year -= 1
        key = f'{year:04d}-{month:02d}'
        values = conn.execute('''
            SELECT
              COALESCE(SUM(CASE WHEN movement_type='entrada' THEN total_value ELSE 0 END),0) purchases,
              COALESCE(SUM(CASE WHEN movement_type='saida' THEN total_value ELSE 0 END),0) sales
            FROM stock_movements WHERE substr(movement_date,1,7)=?
        ''', (key,)).fetchone()
        series.append({'month': key, 'purchases': values['purchases'], 'sales': values['sales']})

    conn.close()
    return jsonify({
        'stock_quantity': stock['qty'],
        'stock_value': stock['value'],
        'to_receive': receive,
        'to_pay': pay,
        'clients': clients,
        'products': products,
        'low_stock': low_stock,
        'month_in': month_values['month_in'],
        'month_out': month_values['month_out'],
        'month_balance': float(month_values['month_out'] or 0) - float(month_values['month_in'] or 0),
        'month_entries': month_counts['entries'] or 0,
        'month_sales': month_counts['sales'] or 0,
        'avg_ticket': month_counts['avg_ticket'] or 0,
        'top_product': dict(top_product) if top_product else None,
        'top_client': dict(top_client) if top_client else None,
        'series': series,
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
    initial_quantity = float(data.get('quantity') or 0)
    initial_cost = float(data.get('avg_cost') or 0)
    cur = conn.execute('''INSERT INTO products(name,unit,quantity,min_stock,avg_cost,sale_price,initial_quantity,initial_cost) VALUES(?,?,?,?,?,?,?,?)''',
                       (name, data.get('unit','sacas'), initial_quantity, float(data.get('min_stock') or 0),
                        initial_cost, float(data.get('sale_price') or 0), initial_quantity, initial_cost))
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
            SELECT sm.*, p.name product_name, p.unit, c.name client_name, d.due_date,
                   COALESCE(d.paid_amount, sm.paid_amount) settled_amount,
                   CASE WHEN d.id IS NOT NULL THEN MAX(d.original_amount-d.paid_amount,0)
                        ELSE MAX(sm.total_value-sm.paid_amount,0) END balance
            FROM stock_movements sm
            JOIN products p ON p.id=sm.product_id
            LEFT JOIN clients c ON c.id=sm.client_id
            LEFT JOIN debts d ON d.movement_id=sm.id
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
        payment_condition = data.get('payment_condition') or 'aprazo'
    except Exception:
        conn.close(); return jsonify({'error':'Dados inválidos'}), 400
    if movement_type not in ('entrada','saida') or quantity <= 0 or payment_condition not in ('avista','aprazo'):
        conn.close(); return jsonify({'error':'Movimentação inválida'}), 400

    product = conn.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
    if not product:
        conn.close(); return jsonify({'error':'Produto não encontrado'}), 404
    if movement_type == 'saida' and product['quantity'] < quantity:
        conn.close(); return jsonify({'error':'Estoque insuficiente para esta saída'}), 409

    total = quantity * unit_value
    if payment_condition == 'avista':
        paid_amount = total
    if paid_amount < 0 or paid_amount > total + 0.005:
        conn.close(); return jsonify({'error':'O valor pago/recebido não pode ser maior que o total.'}), 400
    client_id = data.get('client_id') or None
    movement_date = data.get('movement_date') or datetime.now().strftime('%Y-%m-%d')
    notes = data.get('notes','')

    cur = conn.execute('''INSERT INTO stock_movements(product_id,movement_type,quantity,unit_value,total_value,paid_amount,client_id,movement_date,notes,payment_condition)
                          VALUES(?,?,?,?,?,?,?,?,?,?)''',
                       (product_id,movement_type,quantity,unit_value,total,paid_amount,client_id,movement_date,notes,payment_condition))

    mid = cur.lastrowid
    try:
        _recalculate_product(conn, product_id)
    except ValueError as exc:
        conn.rollback(); conn.close(); return jsonify({'error':str(exc)}), 409

    balance = max(total - paid_amount, 0)
    if balance > 0.005:
        direction = 'pagar' if movement_type == 'entrada' else 'receber'
        who = conn.execute('SELECT name FROM clients WHERE id=?',(client_id,)).fetchone() if client_id else None
        description = _movement_description(product['name'], product['unit'], movement_type, quantity, who['name'] if who else None)
        conn.execute('''INSERT INTO debts(client_id,direction,description,original_amount,paid_amount,due_date,movement_id)
                        VALUES(?,?,?,?,?,?,?)''',
                     (client_id,direction,description,total,paid_amount,data.get('due_date') or None,mid))

    conn.commit(); conn.close(); return jsonify({'id':mid,'total':total}), 201


@app.put('/api/movements/<int:mid>')
def movement_update(mid):
    data = request.get_json(force=True)
    conn = db_connection()
    old = conn.execute('SELECT * FROM stock_movements WHERE id=?', (mid,)).fetchone()
    if not old:
        conn.close(); return jsonify({'error':'Movimentação não encontrada'}), 404
    try:
        product_id = int(data['product_id'])
        movement_type = data['movement_type']
        quantity = float(data['quantity'])
        unit_value = float(data.get('unit_value') or 0)
        paid_amount = float(data.get('paid_amount') or 0)
        payment_condition = data.get('payment_condition') or old['payment_condition'] or 'aprazo'
    except Exception:
        conn.close(); return jsonify({'error':'Dados inválidos'}), 400
    if movement_type not in ('entrada','saida') or quantity <= 0 or unit_value < 0 or payment_condition not in ('avista','aprazo'):
        conn.close(); return jsonify({'error':'Movimentação inválida'}), 400
    total = quantity * unit_value
    if paid_amount < 0 or paid_amount > total + 0.005:
        conn.close(); return jsonify({'error':'O valor pago/recebido não pode ser maior que o total.'}), 400

    product = conn.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
    if not product:
        conn.close(); return jsonify({'error':'Produto não encontrado'}), 404
    old_product = conn.execute('SELECT * FROM products WHERE id=?', (old['product_id'],)).fetchone()
    client_id = data.get('client_id') or None
    movement_date = data.get('movement_date') or old['movement_date']
    notes = data.get('notes', '')
    due_date = data.get('due_date') or None

    linked = _find_or_link_movement_debt(conn, old, old_product)
    extra_payments = 0.0
    if linked:
        extra_payments = float(conn.execute('SELECT COALESCE(SUM(amount),0) s FROM debt_payments WHERE debt_id=?',
                                            (linked['id'],)).fetchone()['s'] or 0)
    if payment_condition == 'avista':
        if extra_payments > total + 0.005:
            conn.rollback(); conn.close()
            return jsonify({'error':'O novo total ficou menor que o valor que já foi baixado nessa movimentação.'}), 409
        paid_amount = max(total - extra_payments, 0)
    if paid_amount + extra_payments > total + 0.005:
        conn.rollback(); conn.close()
        return jsonify({'error':'O novo total ficou menor que o valor que já foi pago/baixado nessa movimentação.'}), 409

    conn.execute('''UPDATE stock_movements
                    SET product_id=?, movement_type=?, quantity=?, unit_value=?, total_value=?, paid_amount=?,
                        client_id=?, movement_date=?, notes=?, payment_condition=?
                    WHERE id=?''',
                 (product_id, movement_type, quantity, unit_value, total, paid_amount,
                  client_id, movement_date, notes, payment_condition, mid))

    affected = {int(old['product_id']), int(product_id)}
    try:
        for pid in affected:
            _recalculate_product(conn, pid)
    except ValueError as exc:
        conn.rollback(); conn.close(); return jsonify({'error':str(exc)}), 409

    who = conn.execute('SELECT name FROM clients WHERE id=?', (client_id,)).fetchone() if client_id else None
    description = _movement_description(product['name'], product['unit'], movement_type, quantity, who['name'] if who else None)
    direction = 'pagar' if movement_type == 'entrada' else 'receber'
    debt_paid = paid_amount + extra_payments
    outstanding = total - debt_paid

    if linked:
        conn.execute('''UPDATE debts
                        SET client_id=?, direction=?, description=?, original_amount=?, paid_amount=?, due_date=?, movement_id=?
                        WHERE id=?''',
                     (client_id, direction, description, total, debt_paid, due_date, mid, linked['id']))
    elif outstanding > 0.005:
        conn.execute('''INSERT INTO debts(client_id,direction,description,original_amount,paid_amount,due_date,movement_id)
                        VALUES(?,?,?,?,?,?,?)''',
                     (client_id, direction, description, total, paid_amount, due_date, mid))

    conn.commit(); conn.close()
    return jsonify({'ok':True,'total':total})


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


@app.get('/venda/<int:mid>/imprimir')
def print_sale(mid):
    conn = db_connection()
    row = conn.execute('''
        SELECT sm.*, p.name product_name, p.unit,
               c.name client_name, c.phone client_phone, c.document client_document, c.city client_city,
               d.due_date,
               COALESCE(d.paid_amount, sm.paid_amount) settled_amount,
               CASE WHEN d.id IS NOT NULL THEN MAX(d.original_amount-d.paid_amount,0)
                    ELSE MAX(sm.total_value-sm.paid_amount,0) END balance
        FROM stock_movements sm
        JOIN products p ON p.id=sm.product_id
        LEFT JOIN clients c ON c.id=sm.client_id
        LEFT JOIN debts d ON d.movement_id=sm.id
        WHERE sm.id=?
    ''', (mid,)).fetchone()
    conn.close()
    if not row or row['movement_type'] != 'saida':
        return 'Venda não encontrada.', 404
    return render_template('sale_receipt.html', sale=dict(row), generated_at=datetime.now(), money_br=_money_br, date_br=_date_br)


@app.get('/relatorio/mensal')
def monthly_report():
    month = request.args.get('month') or datetime.now().strftime('%Y-%m')
    try:
        month_date = datetime.strptime(month, '%Y-%m')
    except ValueError:
        return 'Mês inválido.', 400
    conn = db_connection()
    movements = conn.execute('''
        SELECT sm.*, p.name product_name, p.unit, c.name client_name
        FROM stock_movements sm
        JOIN products p ON p.id=sm.product_id
        LEFT JOIN clients c ON c.id=sm.client_id
        WHERE substr(sm.movement_date,1,7)=?
        ORDER BY sm.movement_date, sm.id
    ''', (month,)).fetchall()
    totals = conn.execute('''
        SELECT
          COALESCE(SUM(CASE WHEN movement_type='entrada' THEN total_value ELSE 0 END),0) purchases,
          COALESCE(SUM(CASE WHEN movement_type='saida' THEN total_value ELSE 0 END),0) sales,
          COALESCE(SUM(CASE WHEN movement_type='entrada' THEN paid_amount ELSE 0 END),0) purchases_settled,
          COALESCE(SUM(CASE WHEN movement_type='saida' THEN paid_amount ELSE 0 END),0) sales_settled
        FROM stock_movements WHERE substr(movement_date,1,7)=?
    ''', (month,)).fetchone()
    open_receive = conn.execute("SELECT COALESCE(SUM(original_amount-paid_amount),0) v FROM debts WHERE direction='receber' AND original_amount>paid_amount").fetchone()['v']
    open_pay = conn.execute("SELECT COALESCE(SUM(original_amount-paid_amount),0) v FROM debts WHERE direction='pagar' AND original_amount>paid_amount").fetchone()['v']
    stock = conn.execute('SELECT COALESCE(SUM(quantity),0) qty, COALESCE(SUM(quantity*avg_cost),0) value FROM products').fetchone()
    conn.close()
    return render_template('monthly_report.html',
        month_label=month_date.strftime('%m/%Y'), month=month,
        movements=[dict(r) for r in movements], totals=dict(totals),
        open_receive=open_receive, open_pay=open_pay, stock=dict(stock),
        generated_at=datetime.now(), money_br=_money_br, date_br=_date_br)


@app.get('/health')
def health():
    return jsonify({'status':'ok'})


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    init_db()
