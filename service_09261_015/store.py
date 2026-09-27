"""SQLite 状态仓储。"""
import sqlite3,json
from .domain import Delivery,Edition,Partner,UnknownDelivery,UnknownEdition,UnknownPartner
class SQLiteStore:
 def __init__(self,path=":memory:"):
  self.db=sqlite3.connect(path); self.db.execute("CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT NOT NULL)"); self.db.commit()
 def save(self,value): self.db.execute("INSERT INTO snapshots(body) VALUES(?)",(json.dumps(value,ensure_ascii=False),)); self.db.commit()
 def latest(self):
  row=self.db.execute("SELECT body FROM snapshots ORDER BY id DESC LIMIT 1").fetchone(); return json.loads(row[0]) if row else []


class DeliveryStore:
    """版本、身份与交付记录的持久化。

    editions 以 (textbook_id, version) 为主键，只插不改，历史版本永远可读；
    deliveries 只追加，留档交付时刻的裁剪结果，供回放与追溯。
    """

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS editions(
                textbook_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                body TEXT NOT NULL,
                PRIMARY KEY(textbook_id, version)
            );
            CREATE TABLE IF NOT EXISTS partners(
                id TEXT PRIMARY KEY,
                body TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                textbook_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                partner_id TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                body TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    @staticmethod
    def _dump(value) -> str:
        return json.dumps(value, ensure_ascii=False)

    # ---- 版本 ----

    def next_version(self, textbook_id) -> int:
        row = self.db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM editions WHERE textbook_id=?",
            (textbook_id,),
        ).fetchone()
        return row[0]

    def save_edition(self, edition: Edition) -> Edition:
        self.db.execute(
            "INSERT INTO editions(textbook_id,version,body) VALUES(?,?,?)",
            (edition.textbook_id, edition.version, self._dump(edition.to_dict())),
        )
        self.db.commit()
        return edition

    def get_edition(self, textbook_id, version) -> Edition:
        row = self.db.execute(
            "SELECT body FROM editions WHERE textbook_id=? AND version=?",
            (textbook_id, version),
        ).fetchone()
        if row is None:
            raise UnknownEdition(f"{textbook_id}@{version}")
        return Edition.from_dict(json.loads(row[0]))

    # ---- 身份 ----

    def save_partner(self, partner: Partner) -> Partner:
        self.db.execute(
            "INSERT OR REPLACE INTO partners(id,body) VALUES(?,?)",
            (partner.id, self._dump(partner.to_dict())),
        )
        self.db.commit()
        return partner

    def get_partner(self, partner_id) -> Partner:
        row = self.db.execute(
            "SELECT body FROM partners WHERE id=?", (partner_id,)
        ).fetchone()
        if row is None:
            raise UnknownPartner(partner_id)
        return Partner.from_dict(json.loads(row[0]))

    # ---- 交付 ----

    def save_delivery(self, delivery: Delivery) -> Delivery:
        cur = self.db.execute(
            "INSERT INTO deliveries(textbook_id,version,partner_id,idempotency_key,body)"
            " VALUES(?,?,?,?,?)",
            (
                delivery.textbook_id,
                delivery.version,
                delivery.partner_id,
                delivery.idempotency_key,
                self._dump(delivery.to_dict()),
            ),
        )
        self.db.commit()
        return Delivery(**{**delivery.to_dict(), "id": cur.lastrowid})

    @staticmethod
    def _to_delivery(row) -> Delivery:
        data = json.loads(row[1])
        data["id"] = row[0]
        return Delivery.from_dict(data)

    def get_delivery(self, delivery_id) -> Delivery:
        row = self.db.execute(
            "SELECT id,body FROM deliveries WHERE id=?", (delivery_id,)
        ).fetchone()
        if row is None:
            raise UnknownDelivery(delivery_id)
        return self._to_delivery(row)

    def find_delivery_by_key(self, key) -> Delivery | None:
        row = self.db.execute(
            "SELECT id,body FROM deliveries WHERE idempotency_key=?", (key,)
        ).fetchone()
        return self._to_delivery(row) if row else None

    def list_deliveries(self, textbook_id=None, partner_id=None):
        sql, cond, args = "SELECT id,body FROM deliveries", [], []
        if textbook_id is not None:
            cond.append("textbook_id=?")
            args.append(textbook_id)
        if partner_id is not None:
            cond.append("partner_id=?")
            args.append(partner_id)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        sql += " ORDER BY id"
        return [self._to_delivery(r) for r in self.db.execute(sql, args)]
