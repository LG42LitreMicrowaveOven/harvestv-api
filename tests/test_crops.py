"""Run from harvestv-api/:  python -m unittest discover tests -v
Database tests need only the standard library. API tests need fastapi + httpx and are skipped otherwise."""
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest

_tmp = tempfile.TemporaryDirectory()
os.environ["HARVESTV_DB_PATH"] = os.path.join(_tmp.name, "test.db")  # never touch the real database file

from database import database as db  # noqa: E402
from database.seed_crops import load_seed  # noqa: E402


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        if db.DB_PATH.exists():
            db.DB_PATH.unlink()

    def test_seed_creates_all_crops(self):
        self.assertEqual(db.init_db(), len(load_seed()))
        self.assertEqual(len(db.list_crops()), len(load_seed()))

    def test_init_twice_has_no_duplicates(self):
        db.init_db(); db.init_db(); db.init_db()
        ids = [c["id"] for c in db.list_crops()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), len(load_seed()))

    def test_order_matches_seed_order(self):
        db.init_db()
        self.assertEqual([c["id"] for c in db.list_crops()], [c["id"] for c in load_seed()])

    def test_get_crop_returns_full_record(self):
        db.init_db()
        c = db.get_crop("mung")
        self.assertEqual(c["name"], "Mung Bean")
        self.assertIs(c["is_legume"], True)
        self.assertIsInstance(c["preceding_crops"], list)

    def test_unknown_and_malicious_ids_return_none(self):
        db.init_db()
        for bad in ("nope", "", "rice' OR '1'='1", "rice; DROP TABLE crops;--"):
            self.assertIsNone(db.get_crop(bad))
        self.assertEqual(len(db.list_crops()), len(load_seed()))  # table intact

    def test_missing_database_file_is_rebuilt_on_demand(self):
        db.init_db()
        db.DB_PATH.unlink()
        self.assertEqual(len(db.list_crops()), len(load_seed()))

    def test_missing_table_is_rebuilt_on_demand(self):
        db.init_db()
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            with conn:
                conn.execute("DROP TABLE crops")
        self.assertIsNotNone(db.get_crop("rice"))

    def test_edited_row_is_restored_by_reseed(self):
        db.init_db()
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            with conn:
                conn.execute("UPDATE crops SET season='Autumn' WHERE id='rice'")
                conn.execute(
                    "INSERT INTO crops (id, name, season) "
                    "VALUES ('ghost', 'Ghost', 'Summer')"
                )
        db.init_db()
        self.assertEqual(db.get_crop("rice")["season"], "Summer")
        self.assertIsNone(db.get_crop("ghost"))


try:
    from fastapi.testclient import TestClient
    import main
    HAVE_API = True
except Exception:  # fastapi / httpx not installed
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "fastapi/httpx not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.client.__enter__()  # runs startup (seeds the database)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_list(self):
        r = self.client.get("/api/crops")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], len(load_seed()))

    def test_detail_and_404(self):
        self.assertEqual(self.client.get("/api/crops/wheat").json()["name"], "Wheat")
        r = self.client.get("/api/crops/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertIn("not found", r.json()["detail"])

    def test_environment_route_still_registered(self):
        self.assertEqual(self.client.get("/api/environment?latitude=999&longitude=0").status_code, 422)
        self.assertEqual(self.client.get("/").json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
