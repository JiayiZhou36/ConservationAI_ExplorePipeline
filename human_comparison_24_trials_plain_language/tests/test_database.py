import ast
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import Database, SQLSession


class DatabaseTests(unittest.TestCase):
    def test_actual_schema_persistence_uniqueness_and_fractional_timing(self):
        source=Path(__file__).resolve().parents[1]/'app.py'
        tree=ast.parse(source.read_text())
        schema=next(node.value for node in ast.walk(tree) if isinstance(node,ast.Constant)
                    and isinstance(node.value,str) and 'CREATE TABLE IF NOT EXISTS participants' in node.value)
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'responses.sqlite3')
            with db.connect() as connection:
                connection.executescript(schema)
                connection.execute('INSERT INTO participants VALUES (?, ?, ?)',('person','[]','today'))
                connection.execute('INSERT INTO exposures VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING',('person',0,'today',1780000000.12345))
                statement='INSERT INTO responses VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING'
                values=('person',0,'left','tie','today',.123456,'comment')
                connection.execute(statement,values)
                connection.execute(statement,values)
            # A new connection and Database instance see committed responses.
            with Database(Path(directory)/'responses.sqlite3').connect() as connection:
                records=connection.execute('SELECT * FROM responses').fetchall()
                self.assertEqual(len(records),1)
                self.assertAlmostEqual(records[0]['elapsed_seconds'],.123456)
                joined=connection.execute('SELECT r.*, e.shown_at FROM responses r JOIN exposures e USING(participant_id, trial_index)').fetchone()
                self.assertEqual(joined['shown_at'],'today')

    def test_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            db=Database(Path(directory)/'data.sqlite3')
            with db.connect() as connection:
                connection.execute('CREATE TABLE sample (value TEXT)')
            with self.assertRaises(RuntimeError):
                with db.connect() as connection:
                    connection.execute('INSERT INTO sample VALUES (?)',('unsaved',))
                    raise RuntimeError('simulated failure')
            with db.connect() as connection:
                self.assertEqual(len(connection.execute('SELECT * FROM sample').fetchall()),0)

    def test_postgres_parameter_translation(self):
        class Recorder:
            def execute(self,sql,parameters):
                return sql,parameters
        sql,parameters=SQLSession(Recorder(),True).execute('SELECT * FROM responses WHERE participant_id=? AND trial_index=?',('person',2))
        self.assertEqual(sql,'SELECT * FROM responses WHERE participant_id=%s AND trial_index=%s')
        self.assertEqual(parameters,('person',2))


if __name__=='__main__':
    unittest.main()
