"""AI店长 v1.1 - SQLite 数据层

提供 6 张核心表：
- products: 抓取的商品快照
- price_history: 价格历史（10天曲线用）
- opportunities: 价差机会（含计算结果）
- user_blacklist: 拉黑清单
- system_config: 系统配置
- workflow_runs: 跑批日志
- push_log: 推送日志（防重复推送）
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,           -- '1688' / 'pdd' / 'xianyu'
    product_id TEXT NOT NULL,        -- 平台商品ID
    title TEXT NOT NULL,
    price REAL NOT NULL,
    sales_count INTEGER DEFAULT 0,   -- 已售数
    seller_name TEXT,
    seller_credit TEXT,
    product_url TEXT,
    store_url TEXT,                  -- 店铺主页链接
    image_url TEXT,
    region TEXT,                     -- 发货地
    raw_data TEXT,                   -- 完整原始数据 (JSON)
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, product_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_products_platform ON products(platform);
CREATE INDEX IF NOT EXISTS idx_products_title ON products(title);
CREATE INDEX IF NOT EXISTS idx_products_fetched ON products(fetched_at);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    product_id TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    sales_count INTEGER DEFAULT 0,
    snapshot_date TEXT NOT NULL,     -- YYYY-MM-DD
    UNIQUE(platform, product_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_price_platform_id ON price_history(platform, product_id);
CREATE INDEX IF NOT EXISTS idx_price_date ON price_history(snapshot_date);

CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_platform TEXT NOT NULL,   -- 进货平台
    source_title TEXT NOT NULL,
    source_price REAL NOT NULL,
    source_url TEXT,
    target_platform TEXT NOT NULL,   -- 销售平台
    target_title TEXT NOT NULL,
    target_price REAL NOT NULL,
    target_url TEXT,
    gross_profit REAL NOT NULL,
    net_profit REAL NOT NULL,
    roi REAL NOT NULL,               -- 投资回报率
    confidence REAL NOT NULL,        -- 置信度 0-1
    sales_signal INTEGER DEFAULT 0,  -- 销量信号
    status TEXT DEFAULT 'PENDING',   -- PENDING / APPROVED / REJECTED / ANALYZING / DECIDED
    notes TEXT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP,
    decided_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_opp_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opp_roi ON opportunities(roi);
CREATE INDEX IF NOT EXISTS idx_opp_discovered ON opportunities(discovered_at);

CREATE TABLE IF NOT EXISTS user_blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,                   -- 品类
    brand TEXT,                      -- 品牌
    seller_name TEXT,                -- 商家
    product_keyword TEXT,            -- 商品关键词
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_blacklist_keyword ON user_blacklist(product_keyword);
CREATE INDEX IF NOT EXISTS idx_blacklist_brand ON user_blacklist(brand);
CREATE INDEX IF NOT EXISTS idx_blacklist_seller ON user_blacklist(seller_name);

CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,          -- 'auto_scan' / 'manual' / 'push'
    platforms TEXT,                  -- 涉及平台
    signals_found INTEGER DEFAULT 0,
    opportunities_found INTEGER DEFAULT 0,
    opportunities_pushed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',   -- running / success / failed
    error_message TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_runs_started ON workflow_runs(started_at);

CREATE TABLE IF NOT EXISTS push_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER,
    push_type TEXT NOT NULL,         -- 'realtime' / 'daily_report' / 'test'
    channel TEXT NOT NULL,           -- 'serverchan' / 'email'
    status TEXT,                     -- 'success' / 'failed' / 'skipped'
    message TEXT,
    pushed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_push_opp ON push_log(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_push_pushed ON push_log(pushed_at);

CREATE TABLE IF NOT EXISTS keyword_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    source TEXT DEFAULT 'seed',        -- 'seed' / 'suggest' / 'manual'
    seed_category TEXT,                -- 来源种子品类
    last_scanned_at TIMESTAMP,         -- 上次扫描时间
    scan_count INTEGER DEFAULT 0,      -- 累计扫描次数
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_kw_pool_last_scanned ON keyword_pool(last_scanned_at);
CREATE INDEX IF NOT EXISTS idx_kw_pool_keyword ON keyword_pool(keyword);

CREATE TABLE IF NOT EXISTS search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    normalized_keyword TEXT NOT NULL,
    result_json TEXT NOT NULL,
    item_count INTEGER DEFAULT 0,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, normalized_keyword)
);
CREATE INDEX IF NOT EXISTS idx_search_cache_lookup ON search_cache(platform, normalized_keyword);

CREATE TABLE IF NOT EXISTS shipping_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id TEXT,
    product_family_id TEXT,
    xianyu_order_no TEXT,
    buyer_name TEXT,
    buyer_phone TEXT,
    buyer_address TEXT,
    pdd_goods_url TEXT,
    pdd_sku TEXT,
    pdd_order_no TEXT,
    cost_price REAL DEFAULT 0,
    sale_price REAL DEFAULT 0,
    profit REAL DEFAULT 0,
    shipping_status TEXT DEFAULT '待填地址',
    tracking_no TEXT,
    tracking_company TEXT,
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_shipping_status ON shipping_orders(shipping_status);
CREATE INDEX IF NOT EXISTS idx_shipping_draft ON shipping_orders(draft_id);

CREATE TABLE IF NOT EXISTS traffic_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER,
    product_family_id TEXT,
    xianyu_item_id TEXT,
    date TEXT NOT NULL,
    title TEXT,
    exposure_count INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    want_count INTEGER DEFAULT 0,
    chat_count INTEGER DEFAULT 0,
    order_count INTEGER DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(xianyu_item_id, date)
);
CREATE INDEX IF NOT EXISTS idx_traffic_date ON traffic_data(date);
CREATE INDEX IF NOT EXISTS idx_traffic_item ON traffic_data(xianyu_item_id);

CREATE TABLE IF NOT EXISTS image_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_family_id TEXT,
    title TEXT,
    source TEXT,
    image_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    pack_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def _connect(db_path: str):
    """SQLite 连接的上下文管理器"""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_db(conn) -> None:
    """数据库迁移：为已有表添加新字段"""
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()]
        if "store_url" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN store_url TEXT")
            logger.info("Migration: added store_url to products")
    except Exception as e:
        logger.debug("Migration check: %s", e)

    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(opportunities)").fetchall()]
        if "actual_sell_price" not in cols:
            conn.execute("ALTER TABLE opportunities ADD COLUMN actual_sell_price REAL DEFAULT 0")
        if "sold_at" not in cols:
            conn.execute("ALTER TABLE opportunities ADD COLUMN sold_at TIMESTAMP")
        if "sold_profit" not in cols:
            conn.execute("ALTER TABLE opportunities ADD COLUMN sold_profit REAL DEFAULT 0")
        logger.info("Migration: added sold tracking columns to opportunities")
    except Exception as e:
        logger.debug("Migration check: %s", e)

    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()]
        if "watched" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN watched INTEGER DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_products_watched ON products(watched)")
            logger.info("Migration: added watched column to products")
    except Exception as e:
        logger.debug("Migration check: %s", e)


def init_db(db_path: str) -> None:
    """初始化数据库（创建所有表 + 迁移）"""
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_db(conn)
    logger.info("Database initialized: %s", db_path)


# ========== 商品快照 ==========

def save_products(db_path: str, products: Iterable[Dict[str, Any]]) -> int:
    """批量保存商品快照"""
    rows = []
    for p in products:
        rows.append((
            p.get("platform"),
            p.get("product_id"),
            p.get("title"),
            float(p.get("price", 0)),
            int(p.get("sales_count", 0)),
            p.get("seller_name", ""),
            p.get("seller_credit", ""),
            p.get("product_url", ""),
            p.get("store_url", ""),
            p.get("image_url", ""),
            p.get("region", ""),
            json.dumps(p.get("raw_data", {}), ensure_ascii=False),
        ))
    with _connect(db_path) as conn:
        cursor = conn.executemany(
            """INSERT OR IGNORE INTO products
               (platform, product_id, title, price, sales_count,
                seller_name, seller_credit, product_url, store_url, image_url, region, raw_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return cursor.rowcount


def get_recent_products(db_path: str, platform: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """获取最近抓取的商品"""
    with _connect(db_path) as conn:
        if platform:
            rows = conn.execute(
                "SELECT * FROM products WHERE platform=? ORDER BY fetched_at DESC LIMIT ?",
                (platform, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY fetched_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


# ========== 价格历史 ==========

def save_price_snapshot(db_path: str, products: Iterable[Dict[str, Any]]) -> int:
    """保存每日价格快照（去重：同 platform+product_id+date 只保留一条）"""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for p in products:
        rows.append((
            p.get("platform"),
            p.get("product_id"),
            p.get("title"),
            float(p.get("price", 0)),
            int(p.get("sales_count", 0)),
            today,
        ))
    with _connect(db_path) as conn:
        cursor = conn.executemany(
            """INSERT OR REPLACE INTO price_history
               (platform, product_id, title, price, sales_count, snapshot_date)
               VALUES (?,?,?,?,?,?)""",
            rows,
        )
    return cursor.rowcount


def get_price_curve(db_path: str, platform: str, product_id: str, days: int = 10) -> List[Dict[str, Any]]:
    """获取单商品 N 天价格曲线"""
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT snapshot_date, price, sales_count FROM price_history
               WHERE platform=? AND product_id=?
               ORDER BY snapshot_date DESC LIMIT ?""",
            (platform, product_id, days),
        ).fetchall()
    return [dict(r) for r in rows][::-1]


# ========== 价差机会 ==========

def save_opportunity(db_path: str, opp: Dict[str, Any]) -> int:
    """保存一个套利机会"""
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO opportunities
               (source_platform, source_title, source_price, source_url,
                target_platform, target_title, target_price, target_url,
                gross_profit, net_profit, roi, confidence, sales_signal, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                opp["source_platform"],
                opp["source_title"],
                opp["source_price"],
                opp.get("source_url", ""),
                opp["target_platform"],
                opp["target_title"],
                opp["target_price"],
                opp.get("target_url", ""),
                opp["gross_profit"],
                opp["net_profit"],
                opp["roi"],
                opp["confidence"],
                opp.get("sales_signal", 0),
                opp.get("status", "PENDING"),
            ),
        )
    return cursor.lastrowid


def list_opportunities(
    db_path: str,
    status: Optional[str] = None,
    min_roi: Optional[float] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """列出机会，可按状态/最小 ROI 过滤"""
    sql = "SELECT * FROM opportunities WHERE 1=1"
    params: List[Any] = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if min_roi is not None:
        sql += " AND roi>=?"
        params.append(min_roi)
    sql += " ORDER BY discovered_at DESC LIMIT ?"
    params.append(limit)

    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def update_opportunity_status(
    db_path: str,
    opp_id: int,
    status: str,
    notes: str = "",
    decided_by: str = "user",
) -> None:
    """更新机会状态"""
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE opportunities
               SET status=?, notes=?, decided_by=?, decided_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (status, notes, decided_by, opp_id),
        )


# ========== 拉黑清单 ==========

def add_to_blacklist(db_path: str, item: Dict[str, Any]) -> int:
    """加入拉黑清单"""
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO user_blacklist
               (category, brand, seller_name, product_keyword, reason)
               VALUES (?,?,?,?,?)""",
            (
                item.get("category", ""),
                item.get("brand", ""),
                item.get("seller_name", ""),
                item.get("product_keyword", ""),
                item.get("reason", ""),
            ),
        )
    return cursor.lastrowid


def is_blacklisted(
    db_path: str,
    title: str = "",
    brand: str = "",
    seller_name: str = "",
) -> bool:
    """检查商品/品牌/商家是否在黑名单"""
    with _connect(db_path) as conn:
        # 商家黑名单
        if seller_name:
            row = conn.execute(
                "SELECT 1 FROM user_blacklist WHERE seller_name=? AND seller_name!='' LIMIT 1",
                (seller_name,),
            ).fetchone()
            if row:
                return True
        # 品牌黑名单
        if brand:
            row = conn.execute(
                "SELECT 1 FROM user_blacklist WHERE brand=? AND brand!='' LIMIT 1",
                (brand,),
            ).fetchone()
            if row:
                return True
        # 关键词黑名单
        if title:
            rows = conn.execute(
                "SELECT product_keyword FROM user_blacklist WHERE product_keyword!=''",
            ).fetchall()
            for r in rows:
                kw = r["product_keyword"].lower()
                if kw and kw in title.lower():
                    return True
    return False


def list_blacklist(db_path: str) -> List[Dict[str, Any]]:
    """列出拉黑清单"""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM user_blacklist ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def remove_from_blacklist(db_path: str, item_id: int) -> None:
    """从拉黑清单移除"""
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM user_blacklist WHERE id=?", (item_id,))


# ========== 跑批日志 ==========

def start_workflow_run(db_path: str, run_type: str, platforms: List[str]) -> int:
    """开始一次跑批，返回 run_id"""
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO workflow_runs (run_type, platforms, status)
               VALUES (?, ?, 'running')""",
            (run_type, ",".join(platforms)),
        )
    return cursor.lastrowid


def finish_workflow_run(
    db_path: str,
    run_id: int,
    status: str,
    signals: int = 0,
    opportunities: int = 0,
    pushed: int = 0,
    error: str = "",
) -> None:
    """结束一次跑批"""
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE workflow_runs
               SET status=?, signals_found=?, opportunities_found=?,
                   opportunities_pushed=?, error_message=?, finished_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (status, signals, opportunities, pushed, error, run_id),
        )


# ========== 推送日志（防重复） ==========

def was_pushed_recently(db_path: str, opportunity_id: int, hours: int = 24) -> bool:
    """检查机会在 N 小时内是否已推送"""
    with _connect(db_path) as conn:
        row = conn.execute(
            """SELECT 1 FROM push_log
               WHERE opportunity_id=? AND status='success'
               AND pushed_at > datetime('now', ?)
               LIMIT 1""",
            (opportunity_id, f"-{hours} hours"),
        ).fetchone()
    return row is not None


def log_push(
    db_path: str,
    opportunity_id: int,
    push_type: str,
    channel: str,
    status: str,
    message: str = "",
) -> None:
    """记录一次推送"""
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO push_log
               (opportunity_id, push_type, channel, status, message)
               VALUES (?,?,?,?,?)""",
            (opportunity_id, push_type, channel, status, message),
        )


# ========== 清理过期数据 ==========

def cleanup_old_data(db_path: str, retention_days: int) -> int:
    """清理 N 天前的旧数据"""
    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    with _connect(db_path) as conn:
        cur1 = conn.execute(
            "DELETE FROM products WHERE DATE(fetched_at) < ?", (cutoff,)
        )
        cur2 = conn.execute(
            "DELETE FROM price_history WHERE snapshot_date < ?", (cutoff,)
        )
        cur3 = conn.execute(
            "DELETE FROM push_log WHERE DATE(pushed_at) < ?", (cutoff,)
        )
    deleted = cur1.rowcount + cur2.rowcount + cur3.rowcount
    logger.info("Cleanup: removed %d old records (before %s)", deleted, cutoff)
    return deleted


# ========== 系统配置键值存储 ==========

def set_system_config(db_path: str, key: str, value: str) -> None:
    """保存系统配置键值"""
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value),
        )


def get_system_config(db_path: str, key: str, default: str = "") -> str:
    """读取系统配置键值"""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM system_config WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def save_scheduler_state(db_path: str, state: dict) -> None:
    """保存调度器状态（JSON）"""
    import json
    set_system_config(db_path, "scheduler_state", json.dumps(state, ensure_ascii=False))


def load_scheduler_state(db_path: str) -> dict:
    """恢复调度器状态"""
    import json
    raw = get_system_config(db_path, "scheduler_state", "{}")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


# ========== 关键词池 ==========

def add_keywords(
    db_path: str,
    keywords: List[str],
    source: str = "seed",
    seed_category: str = "",
) -> int:
    """批量添加关键词到池中（IGNORE 重复）"""
    rows = [(kw, source, seed_category) for kw in keywords]
    with _connect(db_path) as conn:
        cursor = conn.executemany(
            """INSERT OR IGNORE INTO keyword_pool
               (keyword, source, seed_category)
               VALUES (?,?,?)""",
            rows,
        )
    return cursor.rowcount


def get_next_keywords(db_path: str, limit: int = 20) -> List[str]:
    """获取下一批待扫描的关键词

    优先级：未扫描 > 历史有产出 > 历史无产出
    历史有产出：该关键词之前扫出过套利机会（ROI>=10%），值得多扫
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT k.keyword
               FROM keyword_pool k
               LEFT JOIN (
                   SELECT source_title as title, 1 as has_opps
                   FROM opportunities 
                   WHERE roi >= 10 AND discovered_at > datetime('now', '-7 days')
                   GROUP BY source_title
               ) o ON k.keyword = o.title OR o.title LIKE '%' || k.keyword || '%'
               ORDER BY
                 CASE WHEN k.last_scanned_at IS NULL THEN 0 ELSE 1 END,
                 CASE WHEN o.has_opps = 1 THEN 0 ELSE 1 END,
                 k.last_scanned_at ASC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [r["keyword"] for r in rows]


def mark_keyword_scanned(db_path: str, keyword: str) -> None:
    """标记关键词已扫描"""
    with _connect(db_path) as conn:
        conn.execute(
            """UPDATE keyword_pool
               SET last_scanned_at=CURRENT_TIMESTAMP, scan_count=scan_count+1
               WHERE keyword=?""",
            (keyword,),
        )


def get_keyword_pool_stats(db_path: str) -> Dict[str, Any]:
    """获取关键词池统计"""
    with _connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM keyword_pool").fetchone()["c"]
        scanned = conn.execute(
            "SELECT COUNT(*) as c FROM keyword_pool WHERE last_scanned_at IS NOT NULL"
        ).fetchone()["c"]
        return {
            "total": total,
            "scanned": scanned,
            "pending": total - scanned,
        }


# ========== 统计 ==========

def get_stats(db_path: str) -> Dict[str, Any]:
    """获取数据库统计信息"""
    with _connect(db_path) as conn:
        stats = {}
        stats["total_products"] = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
        stats["total_opportunities"] = conn.execute("SELECT COUNT(*) as c FROM opportunities").fetchone()["c"]
        stats["pending_opportunities"] = conn.execute(
            "SELECT COUNT(*) as c FROM opportunities WHERE status='PENDING'"
        ).fetchone()["c"]
        stats["approved_opportunities"] = conn.execute(
            "SELECT COUNT(*) as c FROM opportunities WHERE status='APPROVED'"
        ).fetchone()["c"]
        stats["blacklist_count"] = conn.execute(
            "SELECT COUNT(*) as c FROM user_blacklist"
        ).fetchone()["c"]
        stats["runs_count"] = conn.execute(
            "SELECT COUNT(*) as c FROM workflow_runs"
        ).fetchone()["c"]
    return stats


# ========== Database 类包装器 ==========
# 适配 UI 层的对象式调用接口，处理键映射和状态大小写规范

_STATUS_MAP = {
    "pending": "PENDING",
    "approved": "APPROVED",
    "rejected": "REJECTED",
    "analyzing": "ANALYZING",
    "decided": "DECIDED",
    "PENDING": "PENDING",
    "APPROVED": "APPROVED",
    "REJECTED": "REJECTED",
}


class Database:
    """SQLite 数据层 OO 封装

    UI 层调用示例:
        db = Database("data/ai_storekeeper.db")
        db.save_products(items, platform="1688")
        db.save_opportunity(opp.to_dict())
        db.list_opportunities(limit=50, status="pending")
        db.get_stats()
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        init_db(db_path)

    def save_products(self, products, platform: str = "") -> int:
        """保存商品快照。若 products 项缺少 platform 字段，用 platform 参数补齐"""
        fixed = []
        for p in products:
            p = dict(p)
            if platform and not p.get("platform"):
                p["platform"] = platform
            fixed.append(p)
        return save_products(self.db_path, fixed)

    def save_price_snapshot(self, products) -> int:
        return save_price_snapshot(self.db_path, products)

    def get_recent_products(self, platform=None, limit=500):
        return get_recent_products(self.db_path, platform, limit)

    def get_price_curve(self, platform, product_id, days=10):
        return get_price_curve(self.db_path, platform, product_id, days)

    def save_opportunity(self, opp: Dict[str, Any]) -> int:
        """保存机会，自动适配键名 + 去重（同PDD+同闲鱼不重复）"""
        import sqlite3
        mapped = self._map_opportunity_keys(opp)
        # 去重：检查 24h 内是否已有相同买+卖的组合
        with _connect(self.db_path) as conn:
            buy_title = mapped.get("source_title", "")[:60]
            sell_title = mapped.get("target_title", "")[:60]
            existing = conn.execute(
                """SELECT id FROM opportunities 
                   WHERE source_title=? AND target_title=? 
                   AND discovered_at > datetime('now', '-24 hours')
                   LIMIT 1""",
                (buy_title, sell_title)
            ).fetchone()
            if existing:
                return -existing[0]  # 返回负ID表示已存在
        return save_opportunity(self.db_path, mapped)

    def _map_opportunity_keys(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        """将 arbitrage 模块的 buy_*/sell_* 键映射为 DB 的 source_*/target_*"""
        m = dict(opp)
        # 平台
        if "buy_platform" in m and "source_platform" not in m:
            m["source_platform"] = m["buy_platform"]
        if "sell_platform" in m and "target_platform" not in m:
            m["target_platform"] = m["sell_platform"]
        # 标题
        if "buy_title" in m and "source_title" not in m:
            m["source_title"] = m["buy_title"]
        if "sell_title" in m and "target_title" not in m:
            m["target_title"] = m["sell_title"]
        # 价格
        if "buy_price" in m and "source_price" not in m:
            m["source_price"] = m["buy_price"]
        if "sell_price" in m and "target_price" not in m:
            m["target_price"] = m["sell_price"]
        # URL
        if "buy_url" in m and "source_url" not in m:
            m["source_url"] = m["buy_url"]
        if "sell_url" in m and "target_url" not in m:
            m["target_url"] = m["sell_url"]
        # 净利润/毛利润
        if "profit" in m and "net_profit" not in m:
            m["net_profit"] = m["profit"]
        if "profit" in m and "gross_profit" not in m:
            m["gross_profit"] = m["profit"]
        # 销量信号
        if "sell_sales" in m and "sales_signal" not in m:
            m["sales_signal"] = m.get("sell_sales", 0)
        # 状态规范化
        if "status" in m:
            m["status"] = _STATUS_MAP.get(str(m["status"]).upper(), "PENDING")
        return m

    def list_opportunities(self, limit=50, status=None, min_roi=None) -> List[Dict[str, Any]]:
        """列出机会，status 大小写不敏感"""
        norm_status = _STATUS_MAP.get(str(status).lower()) if status else None
        rows = list_opportunities(self.db_path, norm_status, min_roi, limit)
        # 增强：补充 buy_*/sell_* 别名 + title 别名，方便 UI 统一使用
        out = []
        for r in rows:
            d = dict(r)
            d["buy_platform"] = d.get("source_platform", "")
            d["sell_platform"] = d.get("target_platform", "")
            d["buy_title"] = d.get("source_title", "")
            d["sell_title"] = d.get("target_title", "")
            d["buy_price"] = d.get("source_price", 0)
            d["sell_price"] = d.get("target_price", 0)
            d["buy_url"] = d.get("source_url", "")
            d["sell_url"] = d.get("target_url", "")
            d["profit"] = d.get("net_profit", 0)
            d["title"] = d.get("source_title", "")
            d["status"] = str(d.get("status", "")).lower()
            out.append(d)
        return out

    def update_opportunity_status(self, opp_id: int, status: str, notes: str = "") -> None:
        norm = _STATUS_MAP.get(str(status).lower(), status.upper())
        update_opportunity_status(self.db_path, opp_id, norm, notes)

    def add_blacklist(self, bl_type: str, value: str, reason: str = "") -> int:
        """添加黑名单。bl_type: seller/brand/category/keyword"""
        item = {"reason": reason}
        key_map = {"seller": "seller_name", "brand": "brand",
                   "category": "category", "keyword": "product_keyword"}
        key_map.get(bl_type, "product_keyword")
        item[key_map.get(bl_type, "product_keyword")] = value
        return add_to_blacklist(self.db_path, item)

    def is_blacklisted(self, title="", brand="", seller_name="") -> bool:
        return is_blacklisted(self.db_path, title, brand, seller_name)

    def list_blacklist(self) -> List[Dict[str, Any]]:
        rows = list_blacklist(self.db_path)
        out = []
        for r in rows:
            d = dict(r)
            # 暴露统一的 type/value 字段给 UI
            if d.get("seller_name"):
                d["type"] = "seller"; d["value"] = d["seller_name"]
            elif d.get("brand"):
                d["type"] = "brand"; d["value"] = d["brand"]
            elif d.get("category"):
                d["type"] = "category"; d["value"] = d["category"]
            elif d.get("product_keyword"):
                d["type"] = "keyword"; d["value"] = d["product_keyword"]
            else:
                d["type"] = ""; d["value"] = ""
            out.append(d)
        return out

    def remove_blacklist(self, item_id: int) -> None:
        remove_from_blacklist(self.db_path, item_id)

    def start_workflow_run(self, run_type: str, platforms: List[str]) -> int:
        return start_workflow_run(self.db_path, run_type, platforms)

    def finish_workflow_run(self, run_id, status, signals=0, opportunities=0, pushed=0, error=""):
        finish_workflow_run(self.db_path, run_id, status, signals, opportunities, pushed, error)

    def was_pushed_recently(self, opportunity_id: int, hours: int = 24) -> bool:
        return was_pushed_recently(self.db_path, opportunity_id, hours)

    def log_push(self, opportunity_id, push_type, channel, status, message=""):
        log_push(self.db_path, opportunity_id, push_type, channel, status, message)

    def cleanup_old_data(self, retention_days: int = 30) -> int:
        return cleanup_old_data(self.db_path, retention_days)

    def delete_opportunities_by_platform(self, platform: str) -> int:
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM opportunities WHERE source_platform = ? OR target_platform = ?",
                (platform, platform)
            )
            return cur.rowcount

    def mark_opportunity_sold(self, opp_id: int, actual_price: float, actual_profit: float) -> None:
        """将机会标记为已卖出"""
        with _connect(self.db_path) as conn:
            conn.execute(
                "UPDATE opportunities SET status='SOLD', sold_at=CURRENT_TIMESTAMP, "
                "actual_sell_price=?, sold_profit=? WHERE id=?",
                (actual_price, actual_profit, opp_id)
            )

    def get_sold_stats(self) -> Dict[str, Any]:
        """获取已卖出统计"""
        with _connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*), COALESCE(SUM(sold_profit),0) FROM opportunities WHERE status='SOLD'").fetchone()
            month = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(sold_profit),0) FROM opportunities "
                "WHERE status='SOLD' AND sold_at >= date('now','-30 days')"
            ).fetchone()
            return {
                "total_sold": total[0],
                "total_real_profit": round(total[1], 2),
                "month_sold": month[0],
                "month_real_profit": round(month[1], 2),
            }

    def toggle_watch_product(self, product_id: str, platform: str, watched: bool = True) -> None:
        """标记/取消标记关注商品"""
        with _connect(self.db_path) as conn:
            conn.execute(
                "UPDATE products SET watched=? WHERE product_id=? AND platform=?",
                (1 if watched else 0, product_id, platform)
            )

    def save_search_cache(self, platform: str, keyword: str, items: list) -> None:
        """保存搜索缓存"""
        import json as _json
        with _connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache (platform, normalized_keyword, result_json, item_count, cached_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                (platform, keyword, _json.dumps(items, ensure_ascii=False), len(items))
            )

    def get_search_cache(self, platform: str, keyword: str) -> list:
        """读取搜索缓存（1小时内有效）"""
        import json as _json
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT result_json FROM search_cache WHERE platform=? AND normalized_keyword=? AND cached_at > datetime('now','-1 hour')",
                (platform, keyword)
            ).fetchone()
            if row:
                return _json.loads(row["result_json"])
            return []

    def get_watched_products(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取关注的商品列表"""
        with _connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM products WHERE watched=1 ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def backup(self) -> str:
        """备份数据库到 data/backups/，返回备份路径"""
        import shutil
        from datetime import datetime
        backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(backup_dir, f"ai_storekeeper_{ts}.db")
        shutil.copy2(self.db_path, dest)
        # 保留最近 10 个备份
        all_backups = sorted(
            [f for f in os.listdir(backup_dir) if f.endswith(".db")],
            reverse=True
        )
        for old in all_backups[10:]:
            os.remove(os.path.join(backup_dir, old))
        logger.info("DB backup: %s (%d KB)", dest, os.path.getsize(dest) // 1024)
        return dest

    def set_config(self, key: str, value: str) -> None:
        set_system_config(self.db_path, key, value)

    def get_config(self, key: str, default: str = "") -> str:
        return get_system_config(self.db_path, key, default)

    def save_scheduler_state(self, state: dict) -> None:
        save_scheduler_state(self.db_path, state)

    def load_scheduler_state(self) -> dict:
        return load_scheduler_state(self.db_path)

    def get_stats(self) -> Dict[str, Any]:
        """增强版统计，补充 UI 所需字段"""
        base = get_stats(self.db_path)
        with _connect(self.db_path) as conn:
            # 今日机会
            base["today_opportunities"] = conn.execute(
                "SELECT COUNT(*) as c FROM opportunities WHERE DATE(discovered_at)=DATE('now')"
            ).fetchone()["c"]
            # 今日推送
            base["pushed_count"] = conn.execute(
                "SELECT COUNT(*) as c FROM push_log WHERE DATE(pushed_at)=DATE('now')"
            ).fetchone()["c"]
            # 待审核（小写别名）
            base["pending_count"] = base.get("pending_opportunities", 0)
            # 平均/最高 ROI（今日）
            row = conn.execute(
                "SELECT AVG(roi) as avg_roi, MAX(roi) as max_roi FROM opportunities WHERE DATE(discovered_at)=DATE('now')"
            ).fetchone()
            base["avg_roi"] = row["avg_roi"] or 0.0
            base["max_roi"] = row["max_roi"] or 0.0
            # 高 ROI 数
            base["high_roi_count"] = conn.execute(
                "SELECT COUNT(*) as c FROM opportunities WHERE roi>=60"
            ).fetchone()["c"]
            # ROI 分布
            base["roi_distribution"] = {
                "60%+": conn.execute("SELECT COUNT(*) as c FROM opportunities WHERE roi>=60").fetchone()["c"],
                "30-60%": conn.execute("SELECT COUNT(*) as c FROM opportunities WHERE roi>=30 AND roi<60").fetchone()["c"],
                "20-30%": conn.execute("SELECT COUNT(*) as c FROM opportunities WHERE roi>=20 AND roi<30").fetchone()["c"],
                "<20%": conn.execute("SELECT COUNT(*) as c FROM opportunities WHERE roi<20").fetchone()["c"],
            }
            # 累计潜在利润
            base["cumulative_profit"] = conn.execute(
                "SELECT COALESCE(SUM(net_profit), 0) FROM opportunities WHERE status='approved'"
            ).fetchone()[0] or 0.0
            # 总利润（含待审核）
            base["total_potential_profit"] = conn.execute(
                "SELECT COALESCE(SUM(net_profit), 0) FROM opportunities"
            ).fetchone()[0] or 0.0
        return base

    def clear_all(self) -> None:
        with _connect(self.db_path) as conn:
            for t in ["products", "price_history", "opportunities",
                       "user_blacklist", "workflow_runs", "push_log",
                       "keyword_pool", "search_cache", "shipping_orders",
                       "traffic_data", "image_packs"]:
                conn.execute(f"DELETE FROM {t}")

    # ---------- 关键词池 ----------
    def add_keywords(self, keywords: List[str], source: str = "seed",
                     seed_category: str = "") -> int:
        return add_keywords(self.db_path, keywords, source, seed_category)

    def get_next_keywords(self, limit: int = 20) -> List[str]:
        return get_next_keywords(self.db_path, limit)

    def mark_keyword_scanned(self, keyword: str) -> None:
        mark_keyword_scanned(self.db_path, keyword)

    def get_keyword_pool_stats(self) -> Dict[str, Any]:
        return get_keyword_pool_stats(self.db_path)

    def reset_keyword_pool(self) -> int:
        """重置所有关键词为未扫描状态"""
        import sqlite3
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE keyword_pool SET last_scanned_at=NULL WHERE last_scanned_at IS NOT NULL"
            )
            logger.info("Reset %d keywords to pending", cur.rowcount)
            return cur.rowcount


    # ---------- 发货 SOP ----------
    def create_shipping_order(self, order: dict) -> int:
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO shipping_orders
                   (draft_id, product_family_id, xianyu_order_no, buyer_name, buyer_phone, buyer_address,
                    pdd_goods_url, pdd_sku, pdd_order_no, cost_price, sale_price, profit,
                    shipping_status, tracking_no, tracking_company, remark)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order.get("draft_id",""), order.get("product_family_id",""), order.get("xianyu_order_no",""),
                 order.get("buyer_name",""), order.get("buyer_phone",""), order.get("buyer_address",""),
                 order.get("pdd_goods_url",""), order.get("pdd_sku",""), order.get("pdd_order_no",""),
                 float(order.get("cost_price",0)), float(order.get("sale_price",0)), float(order.get("profit",0)),
                 order.get("shipping_status","待填地址"),
                 order.get("tracking_no",""), order.get("tracking_company",""), order.get("remark","")),
            )
            return cur.lastrowid

    def update_shipping_order(self, order_id: int, fields: dict) -> None:
        set_parts = []
        vals = []
        for k, v in fields.items():
            set_parts.append(f"{k}=?")
            vals.append(v)
        vals.append(order_id)
        with _connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE shipping_orders SET {', '.join(set_parts)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                vals
            )

    def get_shipping_orders(self, status: str = None, limit: int = 50) -> list:
        with _connect(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM shipping_orders WHERE shipping_status=? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM shipping_orders ORDER BY updated_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_shipping_order(self, order_id: int) -> dict:
        with _connect(self.db_path) as conn:
            r = conn.execute("SELECT * FROM shipping_orders WHERE id=?", (order_id,)).fetchone()
            return dict(r) if r else {}

    def get_shipping_stats(self) -> dict:
        with _connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM shipping_orders").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM shipping_orders WHERE shipping_status NOT IN ('COMPLETED','CANCELLED')").fetchone()[0]
            return {"total": total, "pending": pending}

    # ---------- 流量分析 ----------
    def save_traffic_record(self, rec: dict) -> int:
        with _connect(self.db_path) as conn:
            try:
                cur = conn.execute(
                    """INSERT OR REPLACE INTO traffic_data
                       (draft_id, product_family_id, xianyu_item_id, date, title,
                        exposure_count, view_count, want_count, chat_count, order_count, conversion_rate)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (rec.get("draft_id"), rec.get("product_family_id"), rec.get("xianyu_item_id",""),
                     rec.get("date",""), rec.get("title",""),
                     int(rec.get("exposure_count",0)), int(rec.get("view_count",0)),
                     int(rec.get("want_count",0)), int(rec.get("chat_count",0)),
                     int(rec.get("order_count",0)), float(rec.get("conversion_rate",0)))
                )
                return cur.lastrowid
            except Exception as e:
                logger.error("save_traffic_record: %s", e)
                return 0

    def get_traffic_records(self, xianyu_item_id: str = None, date_from: str = None, date_to: str = None, limit: int = 200) -> list:
        with _connect(self.db_path) as conn:
            sql = "SELECT * FROM traffic_data WHERE 1=1"
            params = []
            if xianyu_item_id:
                sql += " AND xianyu_item_id=?"
                params.append(xianyu_item_id)
            if date_from:
                sql += " AND date>=?"
                params.append(date_from)
            if date_to:
                sql += " AND date<=?"
                params.append(date_to)
            sql += " ORDER BY date DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_traffic_items(self) -> list:
        with _connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT xianyu_item_id, title FROM traffic_data ORDER BY xianyu_item_id"
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_traffic_record(self, record_id: int) -> None:
        with _connect(self.db_path) as conn:
            conn.execute("DELETE FROM traffic_data WHERE id=?", (record_id,))

    # ---------- 图片打包 ----------
    def save_image_pack(self, pack: dict) -> int:
        with _connect(self.db_path) as conn:
            cur = conn.execute(
                """INSERT INTO image_packs
                   (product_family_id, title, source, image_count, failed_count, pack_path)
                   VALUES (?,?,?,?,?,?)""",
                (pack.get("product_family_id",""), pack.get("title",""), pack.get("source",""),
                 int(pack.get("image_count",0)), int(pack.get("failed_count",0)), pack.get("pack_path",""))
            )
            return cur.lastrowid

    def get_image_packs(self, product_family_id: str = None, limit: int = 50) -> list:
        with _connect(self.db_path) as conn:
            if product_family_id:
                rows = conn.execute(
                    "SELECT * FROM image_packs WHERE product_family_id=? ORDER BY created_at DESC LIMIT ?",
                    (product_family_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM image_packs ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    # ---------- 仪表盘统计 ----------
    def get_dashboard_stats(self, days: int = 30) -> dict:
        with _connect(self.db_path) as conn:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
            month_ago = (now - timedelta(days=days)).strftime("%Y-%m-%d")
            stats = {}

            # 已铺货 = approved opportunities
            stats["listed_count"] = conn.execute(
                "SELECT COUNT(*) FROM opportunities WHERE status='APPROVED'"
            ).fetchone()[0]

            # 待发货
            stats["pending_shipping"] = conn.execute(
                "SELECT COUNT(*) FROM shipping_orders WHERE shipping_status NOT IN ('COMPLETED','CANCELLED')"
            ).fetchone()[0]

            def _order_stats(since: str) -> dict:
                row = conn.execute(
                    """SELECT COUNT(*), COALESCE(SUM(sale_price),0), COALESCE(SUM(profit),0)
                       FROM shipping_orders WHERE DATE(updated_at)>=?""",
                    (since,)
                ).fetchone()
                return {"orders": row[0], "revenue": round(row[1], 2), "profit": round(row[2], 2)}

            stats["today"] = _order_stats(today)
            stats["week"] = _order_stats(week_ago)
            stats["month"] = _order_stats(month_ago)

            # 平均ROI
            stats["avg_roi"] = conn.execute(
                "SELECT COALESCE(AVG(roi),0) FROM opportunities WHERE status IN ('APPROVED','PENDING')"
            ).fetchone()[0]

            # 已售罄
            stats["sold_out"] = conn.execute(
                "SELECT COUNT(*) FROM opportunities WHERE status='SOLD'"
            ).fetchone()[0]

            # 按类目利润
            stats["category_profit"] = []
            rows = conn.execute(
                "SELECT source_title, COALESCE(SUM(net_profit),0) as total FROM opportunities WHERE status='APPROVED' GROUP BY source_title ORDER BY total DESC LIMIT 10"
            ).fetchall()
            for r in rows:
                cat = (r["source_title"] or "未知")[:20]
                stats["category_profit"].append({"category": cat, "profit": round(r["total"], 2)})

            # 近N天每日销售额/利润/订单
            stats["daily_trend"] = []
            trend_rows = conn.execute(
                """SELECT DATE(updated_at) as dt,
                          COUNT(*) as orders,
                          COALESCE(SUM(sale_price),0) as revenue,
                          COALESCE(SUM(profit),0) as profit
                   FROM shipping_orders
                   WHERE DATE(updated_at)>=?
                   GROUP BY DATE(updated_at)
                   ORDER BY dt""",
                (month_ago,)
            ).fetchall()
            for r in trend_rows:
                stats["daily_trend"].append({
                    "date": r["dt"], "orders": r["orders"],
                    "revenue": round(r["revenue"], 2), "profit": round(r["profit"], 2)
                })

            return stats


__all__ = [
    "init_db",
    "Database",
    "save_products",
    "get_recent_products",
    "save_price_snapshot",
    "get_price_curve",
    "save_opportunity",
    "list_opportunities",
    "update_opportunity_status",
    "add_to_blacklist",
    "is_blacklisted",
    "list_blacklist",
    "remove_from_blacklist",
    "start_workflow_run",
    "finish_workflow_run",
    "was_pushed_recently",
    "log_push",
    "cleanup_old_data",
    "get_stats",
    "add_keywords",
    "get_next_keywords",
    "mark_keyword_scanned",
    "get_keyword_pool_stats",
]
