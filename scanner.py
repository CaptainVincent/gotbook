from base64 import b64encode, b64decode
from json import JSONEncoder, JSONDecoder, dump, load, dumps, loads
import pickle
import pprint
import os, sys, traceback
from datetime import datetime
import time

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import concurrent.futures
from axel import axel

from pytablewriter import Align, MarkdownTableWriter


# python 3 version
# https://stackoverflow.com/questions/8230315/how-to-json-serialize-sets
class PythonObjectEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (list, dict, str, int, float, bool, type(None))):
            return super().default(obj)
        return {'_python_object': b64encode(pickle.dumps(obj)).decode('utf-8')}

def as_python_object(dct):
    if '_python_object' in dct:
        return pickle.loads(b64decode(dct['_python_object'].encode('utf-8')))
    return dct


def save_dict(file, data):
    temp_file_fname = os.path.join(os.path.dirname(file), '_'.join(['temp', os.path.basename(file)]))
    try:
        with open(temp_file_fname, 'w') as outfile:
            dump(data, outfile, indent=4, sort_keys=True, ensure_ascii=False, cls=PythonObjectEncoder)
            outfile.flush()
            os.fsync(outfile.fileno())
        os.rename(temp_file_fname, file)
        return True
    except Exception:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        exc_msg = ''.join(traceback.format_exception(exc_type, exc_obj, exc_tb)).rstrip()
        print('[Save Fail]', file, '>>>', exc_msg)
    return False

def load_dict(file):
    try:
        with open(file, 'r') as infile:
            infile.flush()
            os.fsync(infile.fileno())
            return load(infile, object_hook=as_python_object)
    except Exception:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        exc_msg = ''.join(traceback.format_exception(exc_type, exc_obj, exc_tb)).rstrip()
        #print('[Load Fail]', file, '>>>', exc_msg)
    return {}


class HasNextIterator:
    def __init__(self, it):
        self._it  = it
        self._idx = -1

    def has_next(self):
        try:
            self._it[self._idx+1]
        except:
            return False
        return True

    def next(self):
        val = self._it[self._idx]
        self._idx = self._idx + 1
        return val


def download_all(bookcase):
    return


header = '''
# Gotbook
According gitbook disable explore(search) feature in his official website. So I write a tool for crawl my stared books before. The steps of my algorithm/idea as below.

1. Collect authors from root stared books.
>  (Default root is my gitbook ID)
2. Scan those authors' books and use their stared books collect more authors.
3. **TBD**. Reflect scan who also stared or subscribed those books collect more authors.
4. Until collect authors and scan their books convergence then generate a sorted books table.

#### If you want me could list more books here
You could pull a request add some good authors I missed in **authors.json**. I will check it and regenerate this index for everyone.

Vincent
'''
def gen_markdown(bookcase, sort_key='stars'):
    ranking = []
    for name, books in bookcase.items():
        ranking.extend(books.values())

    ranking = sorted(ranking, key=lambda k: k[sort_key], reverse=True)
    #print(dumps(ranking[:5], indent=4, sort_keys=True, ensure_ascii=False))

    writer = MarkdownTableWriter()
    writer.table_name = "Gitbook \n*%d books sort by %s @ %s*\n" % (len(ranking),sort_key, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    writer.header_list = ["Title", "Author", "Stars", "Subscriptions", "Download"]
    writer.value_matrix = []
    writer.align_list = [Align.LEFT, Align.LEFT, Align.CENTER, Align.CENTER, Align.LEFT]
    for book in ranking[:]:
        writer.value_matrix.append([
                '[%s](%s)' % (book["title"], book["urls"]['access']),
                '[%s](https://legacy.gitbook.com/@%s)' % (book["author"], book["author"]),
                book["stars"],
                book["subscriptions"],
                '[mobi](%s) | [epub](%s) | [pdf](%s) ' % (
                        book['urls']['download']['mobi'],
                        book['urls']['download']['epub'],
                        book['urls']['download']['pdf']
                    )
            ])

    with open("README.md", "w") as readme:
        readme.write(header)
        writer.stream = readme
        writer.write_table()


postfix = {
    'owner'   : '',
    'starred' : '/starred'
}

fields = {
    'owner'   : 'books',
    'starred' : 'starred'
}
def scan_author(name):
    try:
        for page in ['starred', 'owner']:
            url = "https://legacy.gitbook.com/@%s%s?q=" % (name, postfix[page])
            res = requests.get(url, headers={'x-pjax': 'true', 'accept': '*/*'}, verify=False, timeout=10, allow_redirects=False)
            if res.status_code == 200:
                books = loads(res.text)['props'][fields[page]]
                #print(dumps(loads(res.text), indent=4, sort_keys=True, ensure_ascii=False))
                if page == 'starred':
                    #for book in books:
                    #    print(name, book['author']['username'], book['title'], book['urls']['git'])
                    users = set(book['author']['username'] for book in books)
                    scan_queue.extend(users)

                else:
                    bookcase[name] = {book['title'] : {
                                                        'author'        : book['author']['username'],
                                                        'title'         : book['title'],
                                                        'urls'          : book['urls'],
                                                        'stars'         : book['counts']['stars'],
                                                        'subscriptions' : book['counts']['subscriptions']
                                                      } for book in books}
                '''
                for book in books:
                    bookcase[book['author']['username']] = bookcase.get(book['author']['username'], {})
                    bookcase[book['author']['username']][book['title']] = {
                                                                            'author'        : book['author']['username'],
                                                                            'title'         : book['title'],
                                                                            'urls'          : book['urls'],
                                                                            'stars'         : book['counts']['stars'],
                                                                            'subscriptions' : book['counts']['subscriptions']
                                                                          }
                '''
            else:
                blacklist.add(name)
                exc_msgs = [name, url, str(res.status_code)]
                with open("error.log", "a") as log_file:
                    log_file.write('\n'.join([datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), "\n--\n".join(exc_msgs), '\n']))
    except:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        exc_msgs = [name, url]
        exc_msgs.append(''.join(traceback.format_exception(exc_type, exc_obj, exc_tb)).rstrip())
        with open("error.log", "a") as log_file:
            log_file.write('\n'.join([datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'), "\n--\n".join(exc_msgs), '\n']))



bookcase = load_dict('bookcase.json')
authors = load_dict('authors.json')
blacklist = set()
scan_queue = [author for author in authors if author not in bookcase]
if 'captainvincent' not in bookcase:
    scan_queue.append('captainvincent')

scanning = set()
futs = []
scan_itr = HasNextIterator(scan_queue)
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    while True:
        if scan_itr.has_next():
            author = scan_itr.next()
            if author not in scanning and author not in blacklist:
                scanning.add(author)
                futs.append(executor.submit(scan_author, author))
        else:
            if all(fut.done() for fut in futs):
                if scanning.issubset(bookcase):
                    break
                else:
                    unhandle = scanning.difference(bookcase)
                    scan_queue.extend(unhandle)
                    scanning = scanning - unhandle
            else:
                time.sleep(1)

        sys.stdout.write("Scanning... (%d / %d)" %(len(bookcase), len(scanning)) + "\r")

save_dict('bookcase.json', bookcase)
save_dict('authors.json', list(bookcase.keys()))

gen_markdown(bookcase)

download_all(bookcase)

#file_path = axel('https://legacy.gitbook.com/download/pdf/book/llh911001/mostly-adequate-guide-chinese', num_connections=500)