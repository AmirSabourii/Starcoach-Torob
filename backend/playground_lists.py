"""Saved lists / virtual basket (no AI). Server-side SQLite (user_lists.sqlite, separate from torob.sqlite), keyed by an
anonymous client id (cid) the page keeps in localStorage. Prices/shops are read from torob.sqlite (via playground_drill)."""
import os, re, sqlite3, threading, time, uuid
import playground_drill as D

HERE = os.path.dirname(os.path.abspath(__file__))
LDB = os.path.join(HERE, 'user_lists.sqlite')
DEFAULT_NAME = 'لیست من'
_lock = threading.Lock()
_c = sqlite3.connect(LDB, check_same_thread=False)
_c.row_factory = sqlite3.Row
_c.executescript('''
CREATE TABLE IF NOT EXISTS lists(list_id TEXT PRIMARY KEY, cid TEXT NOT NULL, name TEXT NOT NULL, created_at REAL, updated_at REAL);
CREATE INDEX IF NOT EXISTS ix_lists_cid ON lists(cid);
CREATE TABLE IF NOT EXISTS items(item_id TEXT PRIMARY KEY, list_id TEXT NOT NULL, product_id TEXT NOT NULL, shop_id TEXT, offer_id TEXT,
  title TEXT, image TEXT, snap_price INTEGER, snap_date TEXT, snap_date_fa TEXT, snap_labels TEXT,
  shop_name TEXT, address TEXT, area TEXT, lat REAL, lon REAL, qty INTEGER DEFAULT 1, added_at REAL, refreshed_at REAL);
CREATE INDEX IF NOT EXISTS ix_items_list ON items(list_id);
''')
_c.commit()

def _cid(cid):
    cid = re.sub(r'[^A-Za-z0-9_-]', '', str(cid or ''))[:64]
    if len(cid) < 8:
        raise ValueError('bad client id')
    return cid

def _x(sql, args=()):
    with _lock:
        cur = _c.execute(sql, args); _c.commit(); return cur

def _q(sql, args=()):
    with _lock:
        return [dict(r) for r in _c.execute(sql, args).fetchall()]

def _own(cid, list_id):
    r = _q('SELECT * FROM lists WHERE list_id=? AND cid=?', (list_id, cid))
    if not r:
        raise KeyError('list not found')
    return r[0]

def ensure_default(cid):
    r = _q('SELECT list_id FROM lists WHERE cid=? ORDER BY created_at LIMIT 1', (cid,))
    if r:
        return r[0]['list_id']
    lid = 'list_' + uuid.uuid4().hex[:16]; t = time.time()
    _x('INSERT INTO lists VALUES(?,?,?,?,?)', (lid, cid, DEFAULT_NAME, t, t))
    return lid

def create(cid, name):
    cid = _cid(cid); name = (str(name or '').strip() or 'لیست جدید')[:40]
    lid = 'list_' + uuid.uuid4().hex[:16]; t = time.time()
    _x('INSERT INTO lists VALUES(?,?,?,?,?)', (lid, cid, name, t, t))
    return lid

def rename(cid, list_id, name):
    cid = _cid(cid); _own(cid, list_id)
    _x('UPDATE lists SET name=?, updated_at=? WHERE list_id=?', ((str(name or '').strip() or DEFAULT_NAME)[:40], time.time(), list_id))

def delete(cid, list_id):
    cid = _cid(cid); _own(cid, list_id)
    _x('DELETE FROM items WHERE list_id=?', (list_id,)); _x('DELETE FROM lists WHERE list_id=?', (list_id,))

def _offer_row(offer_id):
    r = D.q('SELECT offer_id,product_id,shop_id,price_toman,last_price_changed_at FROM offers WHERE offer_id=?', (offer_id,))
    return r[0] if r else None

def _choose_offer(product_id, shop_id=None, offer_id=None):
    """offer to snapshot: the given offer; else the cheapest priced offer of that product at that shop; else the product's best (fresh) price"""
    if offer_id:
        r = _offer_row(offer_id)
        if r and r[1] == product_id:
            return r
    if shop_id:
        r = D.q('''SELECT offer_id,product_id,shop_id,price_toman,last_price_changed_at FROM offers WHERE product_id=? AND shop_id=?
                   ORDER BY price_toman IS NULL, price_toman LIMIT 1''', (product_id, shop_id))
        if r:
            return r[0]
    best, _, _ = D.price_summary(product_id)
    return _offer_row(best['offer_id']) if best else None

def _snapshot(product_id, shop_id=None, offer_id=None):
    head = D.product_head(product_id)
    if not head:
        raise KeyError('product not found')
    o = _choose_offer(product_id, shop_id, offer_id)
    snap = {'title': head['title'], 'image': head['image'], 'offer_id': None, 'snap_price': None, 'snap_date': None, 'snap_date_fa': None,
            'snap_labels': '', 'shop_id': shop_id, 'shop_name': None, 'address': None, 'area': None, 'lat': None, 'lon': None}
    if o:
        med, _ = D._median_of(product_id)
        _, _, _, labels = D._label_offer(o[3], o[4], med)
        snap.update(offer_id=o[0], snap_price=int(o[3]) if o[3] else None, snap_date=(o[4] or '')[:10] or None,
                    snap_date_fa=D.jalali(o[4]) if o[4] else None, snap_labels=','.join(labels))
        if shop_id or offer_id:          # a seller row was saved -> keep its shop
            snap['shop_id'] = o[2]
    if snap['shop_id']:
        s = D.q('SELECT name,address,location_label,lat,lon FROM shops WHERE shop_id=?', (snap['shop_id'],))
        if s:
            snap.update(shop_name=s[0][0], address=s[0][1], area=s[0][2], lat=s[0][3], lon=s[0][4])
    return snap

def add_item(cid, product_id, shop_id=None, offer_id=None, list_id=None):
    cid = _cid(cid)
    list_id = list_id or ensure_default(cid)
    _own(cid, list_id)
    snap = _snapshot(str(product_id)[:64], (str(shop_id)[:64] if shop_id else None), (str(offer_id)[:64] if offer_id else None))
    dup = _q('SELECT item_id FROM items WHERE list_id=? AND product_id=? AND IFNULL(shop_id,"")=IFNULL(?,"")', (list_id, product_id, snap['shop_id']))
    if dup:
        return dup[0]['item_id'], list_id, True
    iid = 'item_' + uuid.uuid4().hex[:16]; t = time.time()
    _x('''INSERT INTO items(item_id,list_id,product_id,shop_id,offer_id,title,image,snap_price,snap_date,snap_date_fa,snap_labels,shop_name,address,area,lat,lon,qty,added_at,refreshed_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)''',
       (iid, list_id, product_id, snap['shop_id'], snap['offer_id'], snap['title'], snap['image'], snap['snap_price'], snap['snap_date'], snap['snap_date_fa'],
        snap['snap_labels'], snap['shop_name'], snap['address'], snap['area'], snap['lat'], snap['lon'], t, t))
    _x('UPDATE lists SET updated_at=? WHERE list_id=?', (t, list_id))
    return iid, list_id, False

def _own_item(cid, item_id):
    r = _q('SELECT i.* FROM items i JOIN lists l USING(list_id) WHERE i.item_id=? AND l.cid=?', (item_id, cid))
    if not r:
        raise KeyError('item not found')
    return r[0]

def remove_item(cid, item_id):
    cid = _cid(cid); _own_item(cid, item_id); _x('DELETE FROM items WHERE item_id=?', (item_id,))

def move_item(cid, item_id, to_list_id):
    cid = _cid(cid); _own_item(cid, item_id); _own(cid, to_list_id)
    _x('UPDATE items SET list_id=? WHERE item_id=?', (to_list_id, item_id))

def set_qty(cid, item_id, qty):
    cid = _cid(cid); _own_item(cid, item_id)
    _x('UPDATE items SET qty=? WHERE item_id=?', (max(1, min(int(qty or 1), 999)), item_id))

def refresh(cid, list_id):
    """«بروزرسانی قیمت‌ها»: re-read every item's price from torob.sqlite (same offer if it still exists, else same shop, else best price)"""
    cid = _cid(cid); _own(cid, list_id)
    changes = []
    for it in _q('SELECT * FROM items WHERE list_id=?', (list_id,)):
        try:
            snap = _snapshot(it['product_id'], it['shop_id'], it['offer_id'])
        except KeyError:
            changes.append({'item_id': it['item_id'], 'status': 'product_missing'}); continue
        if snap['snap_price'] != it['snap_price'] or snap['offer_id'] != it['offer_id']:
            changes.append({'item_id': it['item_id'], 'title': it['title'], 'old_price': it['snap_price'], 'new_price': snap['snap_price']})
        _x('''UPDATE items SET offer_id=?,snap_price=?,snap_date=?,snap_date_fa=?,snap_labels=?,shop_name=COALESCE(?,shop_name),address=COALESCE(?,address),
              area=COALESCE(?,area),lat=COALESCE(?,lat),lon=COALESCE(?,lon),refreshed_at=? WHERE item_id=?''',
           (snap['offer_id'], snap['snap_price'], snap['snap_date'], snap['snap_date_fa'], snap['snap_labels'], snap['shop_name'], snap['address'],
            snap['area'], snap['lat'], snap['lon'], time.time(), it['item_id']))
    return changes

def _item_out(it):
    lab = [x for x in (it.get('snap_labels') or '').split(',') if x]
    return {'item_id': it['item_id'], 'product_id': it['product_id'], 'shop_id': it['shop_id'], 'offer_id': it['offer_id'], 'title': it['title'],
            'image': it['image'], 'qty': it['qty'], 'price_toman': it['snap_price'], 'price_date_fa': it['snap_date_fa'] or D.UNKNOWN, 'labels': lab,
            'shop': ({'shop_id': it['shop_id'], 'name': it['shop_name'] or D.UNKNOWN, 'address': it['address'] or D.UNKNOWN, 'area': it['area'] or D.UNKNOWN,
                      'lat': it['lat'], 'lon': it['lon'],
                      'map_url': f"https://www.openstreetmap.org/?mlat={it['lat']}&mlon={it['lon']}#map=17/{it['lat']}/{it['lon']}" if it['lat'] is not None else None}
                     if it['shop_id'] else None),
            'price_basis': 'offer_of_chosen_shop' if it['shop_id'] else 'best_price_any_shop',
            'added_at': it['added_at'], 'refreshed_at': it['refreshed_at']}

def get_all(cid):
    cid = _cid(cid); ensure_default(cid)
    out = []
    for l in _q('SELECT * FROM lists WHERE cid=? ORDER BY created_at', (cid,)):
        items = [_item_out(i) for i in _q('SELECT * FROM items WHERE list_id=? ORDER BY added_at', (l['list_id'],))]
        known = [i['price_toman'] * i['qty'] for i in items if i['price_toman']]
        shops = {}
        for i in items:
            if i['shop'] and i['shop']['lat'] is not None:
                shops.setdefault(i['shop_id'], dict(i['shop'], n_items=0))['n_items'] += 1
        out.append({'list_id': l['list_id'], 'name': l['name'], 'n_items': len(items), 'items': items,
                    'total_toman': sum(known) if items else 0, 'n_unknown_price': sum(1 for i in items if not i['price_toman']),
                    'total_is_partial': any(not i['price_toman'] for i in items), 'shops': list(shops.values()),
                    'created_at': l['created_at'], 'updated_at': l['updated_at']})
    return {'client_id': cid, 'lists': out, 'note': D.OFFER_NOTE}
