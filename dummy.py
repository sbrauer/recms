from cms.resources import Article
import datetime
from cms import command
from cms.dateutil import utcnow

# These functions could be called from a pshell session...

def delete_all(root, request):
    names = root.get_child_names()
    for name in names:
        root.delete_child(name)

#def reindex_all(root, request):
#    for child in root.get_children():
#        child.es_index()

def populate(folder, request):
    # Read a file containing 100 paragraphs of lorem ipsum text.
    f = open('lorem.txt')
    raw = f.read()
    f.close()
    lorem = [x for x in raw.split('\n') if x]

    for n in range(50):
        num = n+1
        p1 = lorem[n*2]
        p2 = lorem[(n*2)+1]
        title = "Article %s" % num
        body = "<p>%s</p>\n<p>%s</p>" % (p1, p2)
        name = "article-%s" %num
        dateline = utcnow(zero_seconds=True)
        #obj = Article(request, title=title, body=body, dateline=dateline, description='meh', attachments=[], list_attachments=False)
        #folder.add_child(name, obj)
        command.create(request, folder, Article, name, dict(title=title, body=body, dateline=dateline, description='meh', attachments=[], list_attachments=False))
