import unittest
from unittest.mock import patch
from server import Handler
class Fake(Handler):
    def __init__(self, path, headers, body=b''):
        import io
        self.path=path; self.headers=headers; self.rfile=io.BytesIO(body)
        self.server=type('Server',(),{'server_port':8770})()
    def send(self, status, value, *args): self.result=(status,value)
class Tests(unittest.TestCase):
    def test_no_cookie(self):
        h=Fake('/api/status',{'Host':'127.0.0.1:8770'});h.do_GET();self.assertEqual(h.result[0],401)
    def test_host_protection(self):
        h=Fake('/',{'Host':'evil.test'});h.do_GET();self.assertEqual(h.result[0],403)
    def test_no_service(self):
        import server
        h=Fake('/api/generate',{'Host':'127.0.0.1:8770','Origin':'http://127.0.0.1:8770','Cookie':'business_session='+server.SESSION})
        with patch('server.KEY',''):h.do_POST()
        self.assertEqual(h.result[0],503)
    def test_cross_origin(self):
        h=Fake('/api/generate',{'Host':'127.0.0.1:8770','Origin':'https://evil.test'});h.do_POST();self.assertEqual(h.result[0],403)
    def test_generate(self):
        import server,json
        body=json.dumps({'prompt':'test'}).encode()
        h=Fake('/api/generate',{'Host':'127.0.0.1:8770','Origin':'http://127.0.0.1:8770','Cookie':'business_session='+server.SESSION,'Content-Length':str(len(body)),'Content-Type':'application/json'},body)
        with patch('server.KEY','mock'),patch('server.MODEL','mock'),patch('server.LAST',-100),patch('server.generate',return_value={'words':[{'word':'invoice','meanings':['发票']}]}) :h.do_POST()
        self.assertEqual(h.result[0],200);self.assertEqual(h.result[1]['words'][0]['word'],'invoice')
if __name__=='__main__':unittest.main()
