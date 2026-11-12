import sqlite3
import tempfile
import unittest
from pathlib import Path
from meridian_dispatch.main import article_key,render,select_new,relevance

class DigestTests(unittest.TestCase):
    def test_relevance(self):
        self.assertGreater(relevance({'title':'New maritime boundary map','description':''}),0)
    def test_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            db=sqlite3.connect(':memory:')
            db.execute('CREATE TABLE seen (article_key TEXT PRIMARY KEY, first_seen TEXT NOT NULL)')
            item={'title':'Border map updated','url':'https://example.org','description':''}
            self.assertEqual(len(select_new(db,[item],10)),1)
            db.execute('INSERT INTO seen VALUES (?,?)',(article_key(item),'now'))
            self.assertEqual(len(select_new(db,[item],10)),0)
    def test_render(self):
        md,body=render([], '2026-11-11')
        self.assertIn('No new matching',md)
        self.assertIn('<html>',body)
if __name__=='__main__': unittest.main()
