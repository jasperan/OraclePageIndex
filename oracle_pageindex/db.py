import oracledb
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OracleDB:
    def __init__(self, user, password, dsn, pool_min=1, pool_max=5):
        self.user = user
        self.password = password
        self.dsn = dsn
        self.pool_min = pool_min
        self.pool_max = pool_max
        self._pool = None

    def connect(self):
        self._pool = oracledb.create_pool(
            user=self.user,
            password=self.password,
            dsn=self.dsn,
            min=self.pool_min,
            max=self.pool_max,
            increment=1,
        )
        logger.info(f"Connected to Oracle at {self.dsn}")
        return self._pool

    def get_connection(self):
        if self._pool is None:
            self.connect()
        return self._pool.acquire()

    def close(self):
        if self._pool:
            self._pool.close()
            self._pool = None

    def init_schema(self):
        schema_path = Path(__file__).parent.parent / "setup_schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                sql_content = schema_path.read_text()
                # Split on '/' for PL/SQL blocks and ';' for regular statements
                blocks = sql_content.split("/\n")
                for block in blocks:
                    block = block.strip()
                    if not block or block.startswith("--"):
                        continue
                    # Handle PL/SQL blocks (BEGIN...END;)
                    if block.upper().startswith("BEGIN"):
                        try:
                            cur.execute(block)
                        except oracledb.Error as e:
                            logger.warning(f"PL/SQL block warning: {e}")
                    else:
                        # Split regular SQL statements by semicolon
                        for stmt in block.split(";"):
                            stmt = stmt.strip()
                            if stmt and not stmt.startswith("--"):
                                try:
                                    cur.execute(stmt)
                                except oracledb.Error as e:
                                    logger.warning(f"SQL warning: {e}")
                conn.commit()
        logger.info("Schema initialized successfully")

    def execute(self, sql, params=None):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                conn.commit()
                return cur

    def execute_returning(self, sql, params=None, returning_col="id"):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                out_var = cur.var(oracledb.NUMBER)
                all_params = dict(params or {})
                all_params[f"out_{returning_col}"] = out_var
                cur.execute(sql, all_params)
                conn.commit()
                return int(out_var.getvalue()[0])

    def fetchall(self, sql, params=None):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                columns = [col[0].lower() for col in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    def fetchone(self, sql, params=None):
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params or {})
                row = cur.fetchone()
                if row:
                    columns = [col[0].lower() for col in cur.description]
                    return dict(zip(columns, row))
                return None
