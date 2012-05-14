import unittest
from pyramid import testing

def _getBlogPostClass():
    from cms.resources import BlogPost
    return BlogPost

def _makeOneBlogPost(request, title="A Title", body="Some body."):
    return _getBlogPostClass()(request, title=title, body=body)

def _getRootClass():
    from cms.resources import Root
    return Root

def _makeOneRoot(request):
    return _getRootClass()(request)

class ViewTests(unittest.TestCase):

    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def test_root_view(self):
        from cms.views import root_view
        request = testing.DummyRequest()
        info = root_view(root, request)
        self.assertEqual(len(info['items']), 0)

class BlogPostTests(unittest.TestCase):

    def test_constructor(self):
        request = testing.DummyRequest()
        instance = _makeOneBlogPost(request)
        self.assertEqual(instance.title, "A Title")
        self.assertEqual(instance.body, "Some body.")

    def test_validate(self):
        import dateutil
        before = dateutil.utcnow()
        request = testing.DummyRequest()
        request.GET['title'] = "Hello"
        request.GET['body'] = "World"
        result = _getBlogPostClass().validate(request)
        self.assertEqual(result['title'], "Hello")
        self.assertEqual(result['body'], "World")
        # Make sure dateline defaulted to the current time (when validation occurred).
        self.assertTrue(result['dateline'] > before)
        after = dateutil.utcnow()
        self.assertTrue(result['dateline'] < after)

class RootTests(unittest.TestCase):

    def test_constructor(self):
        request = testing.DummyRequest()
        instance = _makeOneRoot(request)
        self.assertEqual(instance.__name__, "")
        self.assertEqual(instance.__parent__, None)

class FunctionalTests(unittest.TestCase):

    def setUp(self):
        #self.config = testing.setUp()
        settings = dict(
            db_uri = "mongodb://localhost/",
            db_name = "cms_unittests",
            es_uri = "127.0.0.1:9500",
            es_name = "cms_unittests",
        )
        import cms
        self.app = cms.main({}, **settings)
        self.db_conn = self.app.registry.settings['db_conn']
        self.settings = settings
        self.request = testing.DummyRequest()
        self.request.registry = self.app.registry
        #from webtest import TestApp
        #self.testapp = TestApp(self.app)

    def tearDown(self):
        #self.db_conn.drop_database(self.settings['db_name'])
        db = self.db_conn[self.settings['db_name']]
        names = db.collection_names()
        for name in names:
            if name == 'system.indexes': continue
            db.drop_collection(name)
        self.db_conn.disconnect()
        #testing.tearDown()

    def test_savepost(self):
        instance = _makeOneBlogPost(self.request)
        instance.__name__ = "dummy"
        self.assertEqual(instance._id, None)
        instance.save()
        self.assertNotEqual(instance._id, None)

    def test_crud(self):
        root = _makeOneRoot(self.request)
        names = root.get_child_names()
        self.assertEqual(names, [])
        name = "dummy"
        self.assertFalse(root.has_child(name))

        post = _makeOneBlogPost(self.request)
        root.add_child(name, post)
        self.assertTrue(root.has_child(name))
        other = root[name]
        self.assertEqual(post.title, other.title)
        self.assertEqual(post.body, other.body)

        post.title = "New Title"
        post.body = "New Body"
        post.save()
        self.assertNotEqual(post.title, other.title)
        self.assertNotEqual(post.body, other.body)
        other = root[name]
        self.assertEqual(post.title, other.title)
        self.assertEqual(post.body, other.body)

        root.delete_child(name)
        self.assertFalse(root.has_child(name))

    def test_child_names(self):
        root = _makeOneRoot(self.request)
        names = root.get_child_names()
        self.assertEqual(names, [])
        for x in range(1, 21):
            post = _makeOneBlogPost(self.request, title="Title %s"%x, body="Body %s"%x)
            root.add_child("post%02d"%x, post)
        self.assertEqual(len(root.get_child_names()), 20)
        self.assertEqual(len(root.get_child_names(limit=10)), 10)
        from cms.resources import ASCENDING, DESCENDING
        self.assertEqual(root.get_child_names(sort=[("__name__", ASCENDING)], limit=5), ["post01", "post02", "post03", "post04", "post05"])
        self.assertEqual(root.get_child_names(sort=[("__name__", DESCENDING)], limit=5), ["post20", "post19", "post18", "post17", "post16"])
        

    # FIXME: add more functional tests.... see http://docs.pylonsproject.org/projects/pyramid/en/1.2-branch/tutorials/wiki/tests.html
