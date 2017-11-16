#!/usr/bin/env python

"""
Reddit upvoted image scraper
Date created: 2/6/2017
Author: Nick Yu
Note: only works on windows

Uses Reddit's JSON api to get each post

Each child 'data' object has all the post parameters
{
    "kind": ...
    "data": {
        "children":
            {"data": {} }
            {"data": {} }
            {"data": {} }
            ...
    }
}

"""

import requests
import threading
import queue
import json
import sys
import os

from shutil import copyfileobj
from getpass import getpass
from lxml import html

NUM_WORKERS = 4

HEADERS = {
    'User-Agent': 'RedditApp by /u/<USERNAME>'
}


def print_banner():
    # don't even bother questioning this monstrosity
    banner = '{top}'*50 + '\n{side}{0:^48}{side}' + '\n{side}{1:^48}{side}' + '\n{side}{2:^48}{side}\n' + '{top}'*50
    print(banner.format('Reddit Upvoted Scraper 1.0', '', 'press CTRL-C to exit', side='|', top='='))


def print_status(text, status_code=2, end='\n'):
    """
    print status to stdout
    0 = Err
    1 = OK
    2 = Empty
    """
    ansi = ('\33[91m', '\33[92m', '')  #ANSI escape sequences
    status = ('!', '+', '-')
    postfix = '{}[{:^3}]{}'.format(ansi[status_code], status[status_code], "\33[0m")
    print(postfix, text, end=end)


class DownloadWorker(threading.Thread):
    """
    Threaded object that downloads images in the background
    :param queue: Queue object containing tuples with url and path
    :param status_queue: Queue object which is used to keep track of current downloads
    """ 
    def __init__(self, queue, status_queue):
        threading.Thread.__init__(self)
        self.daemon = True
        self.queue = queue
        self.status_queue = status_queue

    def run(self):
        while not self.queue.empty():
            # each item in the queue is a tuple with url and download_path
            url, download_path, subreddit = self.queue.get()
            try:
                save_image(url, download_path)
            except:
                self.status_queue.put((url, subreddit, 'Failed'))
            else:
                self.status_queue.put((url, subreddit, 'Success'))
            finally:
                self.queue.task_done()


class RedditScraper:
    def __init__(self):
        self.session = requests.Session()
        self.current_page = "https://www.reddit.com/user/{}/upvoted/".format(USERNAME)
        self.login()
        
    def login(self):
        payload = {
            'op': 'login-main',
            'user': USERNAME,
            'passwd': PASSWORD,
            'api_type': 'json'
        }

        res = self.session.post("https://www.reddit.com/api/login/{}".format(USERNAME), data=payload, headers=HEADERS)
        try:
            res.raise_for_status()

            # grab modhash needed for authentication
            modhash = res.json()['json']['data']['modhash']
            HEADERS['X-Modhash'] = modhash

        except Exception as e:
            print_status('Failed to login', status_code=0)
            print(e)
            input('Press enter to continue...')
            self.close()
            sys.exit()
        else:
            print_status('Logged in', status_code=1)

    def get_posts(self):
        """Logs into reddit and returns a list containing each child-post as a dict"""
        parameters = ('title', 'subreddit', 'url', 'domain', 'thumbnail')
        posts = []

        # get json page
        url = self.current_page.split('/')
        url.insert(6, '.json?')

        response = self.session.get('/'.join(url), headers=HEADERS)
        response.raise_for_status()

        data = response.json()
        self.current_page = self.get_next_page(data['data']['after'])
        
        for child in data['data']['children']:
            post = child['data']
            post = {par: value for par, value in post.items() if par in parameters}
            posts.append(post)

        return posts

    def get_next_page(self, last_post_id):
        """
        Create the next page link and return it
        :param last_post_id: 'after' field of the JSON response object

        Each link of reddit's upvoted pages is formatted as:
        reddit.com/user/<USERNAME>/upvoted/?count=<COUNT>&after=<LAST_POST_ID>
        the after field should contain the id of the last post on the current page
        """
        next_page = self.current_page.split('/')[:-1]
        next_page.append('?count=25&after={}'.format(last_post_id))
        next_page = '/'.join(next_page)
        return next_page

    def close(self):
        self.session.close()


def save_image(url, download_path):
    filename = url.split('/')[-1]

    # add '_copy' to the filename if it already exists in the folder
    while os.path.isfile(download_path + '\\' + filename):
        filename += '_copy'

    response = requests.get(url, stream=True, timeout=15)

    with open(download_path + '\\' + filename, 'wb') as f:
        copyfileobj(response.raw, f)


def image_exists(url, download_path):
    """Checks if the image in the specified folder already exists and returns True or False"""
    filename = url.split('/')[-1]
    download_path = download_path + '\\' + filename
    return os.path.isfile(download_path)


def get_subreddits():
    """
    Parses json file located in the program directory where each key is 
    a folder path, and each value is a list of the subreddits to put in 
    Returns a dict with each key being a subreddit with the corresponding download path
    """
    with open('subreddits.json', 'r') as f:
        file = json.loads(f.read())

    subreddits = {}
    for path, subs in file.items():
        subreddits.update({s: path for s in subs})

    return subreddits


def parse_posts(posts, subreddits):
    """
    Remove all unwanted posts
    Returns a list with posts in the format {<PARAMETERS>:..., download_path:...}
    """
    allowed_posts = []

    for post in posts:
        # Remove when not from wished subreddits or if there is no thumbnail
        subreddit = post['subreddit']

        if subreddit in subreddits and post['thumbnail'] != 'self':
            post['download_path'] = subreddits[subreddit]
            allowed_posts.append(post)

    return allowed_posts


class App:
    def __init__(self):
        self.subreddits = get_subreddits()
        self.scraper = RedditScraper()
        self.queue = queue.Queue()
        self.status_queue = queue.Queue()
        self.threads = []

    def grab_links(self):
        """Get image links and put inside queue"""
        found_existing = False
        page = 0

        while not found_existing:
            print_status('Getting page {}'.format(page))

            posts = self.scraper.get_posts()
            posts = parse_posts(posts, self.subreddits)

            for post in posts:
                if image_exists(post['url'], post['download_path']):
                    found_existing = True
                    break

                # call get_imgur_links if the post url refers to an imgur album
                if 'imgur' in post['domain'] and not ('.jpeg' in post['url'] or '.png' in post['url']):
                    self.get_imgur_links(post)

                self.queue.put((post['url'], post['download_path'], post['subreddit']))

            page += 1

    # TODO: doesn't always work, imgur pages structure differ
    def get_imgur_links(self, post):
        """Get all images inside an imgur album"""
        response = requests.get(post['url'], headers=HEADERS)
        tree = html.fromstring(response.content)

        links = tree.xpath("//a[@class='zoom']/@href")

        for link in links: 
            # all links are formatted as //i.imgur.com/<IMAGE NAME>
            # so the shema is added before the image is downloaded
            link = 'http:' + link
            self.queue.put((link, post['download_path'], post['subreddit']))

    def start_workers(self):
        for i in range(NUM_WORKERS):
            self.threads.append(DownloadWorker(self.queue, self.status_queue))

        for thread in self.threads:
            thread.start()

    def workers_alive(self):
        return any([t.isAlive() for t in self.threads])

    def run(self):
        self.grab_links()
        self.start_workers()
        
        print_status('Starting Downloads')

        while self.workers_alive():
            download_status = self.status_queue.get()
            filename = download_status[0].split('/')[-1]
            subreddit = download_status[1]
            status = download_status[2]

            if status == 'Success':
                print_status(status, status_code=1, end=' ')
            else:
                print_status(status, status_code=0, end=' ')

            print('-', filename, '({})'.format(subreddit))

        print_status('Done', status_code=1)


if __name__ == '__main__':
    print_banner()
    USERNAME = input('Username: ')
    PASSWORD = getpass('Password: ')

    App().run()
    sys.exit()