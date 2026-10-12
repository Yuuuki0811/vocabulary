import unittest, tempfile, json
from pathlib import Path
from unittest.mock import patch
import accounts
class AccountTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch('accounts.PATH',Path(self.tmp.name)/'accounts.sqlite3');self.patch.start();accounts.SESSIONS.clear()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def test_independent_accounts_and_limit(self):
  a,ta=accounts.register('我','password123');b,tb=accounts.register('男朋友','password456')
  self.assertNotEqual(a['id'],b['id']);self.assertEqual(accounts.user(ta),a)
  with self.assertRaises(ValueError):accounts.register('第三人','password789')
  with self.assertRaises(ValueError):accounts.login('我','wrong')
  self.assertIsNone(accounts.user('invalid'))
 def test_progress_only_and_hash_storage(self):
  a,t=accounts.register('我','password123');accounts.update_progress(a['id'],{'mastered':7,'privateSentence':'不分享'})
  result=accounts.pair_progress()[0]['progress'];self.assertEqual(result['mastered'],7);self.assertNotIn('privateSentence',result)
  with accounts.connect() as c:hashed=c.execute('SELECT hash FROM users').fetchone()[0]
  self.assertNotEqual(hashed,'password123');self.assertEqual(accounts.PATH.stat().st_mode&0o777,0o600)
if __name__=='__main__':unittest.main()
