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


def download_wrap(filename, url):
    try:
        axel(url, output_path=filename, num_connections=10)
        finished.add(filename)
    except:
        failed.add(filename)
        with open("without_pdf_books.txt", "a") as out_file:
            out_file.write(' '.join([filename, '\n']))


finished = set()
failed = set()
def download_all(books):
    if os.path.isfile("without_pdf_books.txt"):
        os.remove("without_pdf_books.txt")
    download_queue = []
    for book in books:
        url = book['urls']['download']['pdf']
        fname = "%s_%s.pdf" % (url.split('/')[-1], book['author'])
        fullname = './gitbooks/%s' % fname
        if not os.path.isfile(fullname) and \
           (book['stars'] > 10 or book['subscriptions'] > 10):
            download_queue.append((fullname, url))
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for download_item in download_queue:
            executor.submit(download_wrap, download_item[0], download_item[1])
        while True:
            sys.stdout.write("Downloading... (%d / %d)" %(len(finished), len(download_queue)) + "\r")
            if len(finished) + len(failed) == len(download_queue):
                print('Download (%d) done                                  ' % len(finished))
                break
            else:
                time.sleep(1)


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
    writer.table_name = "Gitbook \n*%d books sort by %s @ %s (UTC)*\n> List too long so github auto omit last part. You can download READ.md for get full list.\n" % (len(ranking),sort_key, datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    writer.header_list = ["Title", "Author", "Stars", "Subscriptions", "Download"]
    writer.value_matrix = []
    writer.align_list = [Align.LEFT, Align.LEFT, Align.CENTER, Align.CENTER, Align.LEFT]
    for book in ranking:
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
    return ranking


def scan_book(book):
    # sample
    # https://legacy.gitbook.com/book/eyesofkids/javascript-start-from-es6/subscriptions
    # https://legacy.gitbook.com/book/eyesofkids/javascript-start-from-es6/stars
    return


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
already_count = len(bookcase)
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
        sys.stdout.write("Scanning... (%d / %d)" %(len(bookcase) - already_count, len(scanning)) + "\r")
        if scan_itr.has_next():
            author = scan_itr.next()
            if author not in scanning and author not in blacklist:
                scanning.add(author)
                futs.append(executor.submit(scan_author, author))
        else:
            if all(fut.done() for fut in futs):
                if scanning.issubset(bookcase):
                    print('Scanned (%d) done                                  ' % len(scanning))
                    break
                else:
                    unhandle = scanning.difference(bookcase)
                    scan_queue.extend(unhandle)
                    scanning = scanning - unhandle
            else:
                time.sleep(1)

save_dict('bookcase.json', bookcase)
save_dict('authors.json', list(bookcase.keys()))

sorted_list = gen_markdown(bookcase)
download_all(sorted_list)
