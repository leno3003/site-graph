from bs4 import BeautifulSoup
import urllib
import os 
import requests
from pyvis.network import Network
import networkx as nx
import argparse
import pickle
import scipy
import numpy as np

from collections import deque

def handle_error(error, error_obj, r, url, visited, error_codes):
    error = str(error_obj) if error else r.status_code
    visited.add(url)
    error_codes[url] = error
    print(f'{error} ERROR while visiting {url}')


def crawl(url, visit_external):
    visited = set()
    edges = set()
    resource_pages = set()
    error_codes = dict()
    redirect_target_url = dict()

    head = requests.head(url, timeout=10)
    site_url = head.url
    redirect_target_url[url] = site_url

    to_visit = deque()
    to_visit.append((site_url, None))

    while to_visit:
        url, from_url = to_visit.pop()

        print('Visiting', url, 'from', from_url)

        error = False
        error_obj = None
        try:
            page = requests.get(url, timeout=10)
        except requests.exceptions.RequestException as e:
            error = True
            error_obj = e

        if error or not page:
            handle_error(error, error_obj, page, url, visited, error_codes)
            continue
        
        soup = BeautifulSoup(page.text, 'html.parser')
        internal_links = set()
        external_links = set()

        # Handle <base> tags
        base_url = soup.find('base')
        base_url = '' if base_url is None else base_url.get('href', '')

        for link in soup.find_all('a', href=True):
            link_url = link['href']
        
            if link_url.startswith('mailto:'):
                continue
            
            # Resolve relative paths
            if not link_url.startswith('http'):
                link_url = urllib.parse.urljoin(url, urllib.parse.urljoin(base_url, link_url))

            # Remove queries/fragments from internal links
            if link_url.startswith(site_url):
                link_url = urllib.parse.urljoin(link_url, urllib.parse.urlparse(link_url).path)

            # Load where we know that link_url will be redirected
            if link_url in redirect_target_url:
                link_url = redirect_target_url[link_url]

            if link_url not in visited and (visit_external or link_url.startswith(site_url)):
                is_html = False
                error = False
                error_obj = None

                try:
                    head = requests.head(link_url, timeout=10)
                    if head and 'html' in head.headers.get('content-type', ''):
                        is_html = True
                except requests.exceptions.RequestException as e:
                    error = True
                    error_obj = e

                if error or not head:
                    handle_error(error, error_obj, head, link_url, visited, error_codes)
                    edges.add((url, link_url))
                    continue

                redirect_target_url[link_url] = head.url
                link_url = head.url
                visited.add(link_url)

                if link_url.startswith(site_url):
                    if is_html:
                        to_visit.append((head.url, url))
                    else:
                        resource_pages.add(link_url)
            
            edges.add((url, link_url))

    return edges, error_codes, resource_pages


def get_node_info(nodes, error_codes, resource_pages, args):
    node_info = []
    for node in nodes:
        if node in error_codes:
            node_info.append(f'Error: {error_codes[node]}')
        elif node in resource_pages:
            node_info.append('resource')
        elif node.startswith(args.site_url):
            node_info.append('internal')
        else:
            node_info.append('external')
    return node_info



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Visualize the link graph of a website.')
    parser.add_argument('site_url', type=str, help='the base URL of the website', nargs='?', default='')
    default = 'site.html'
    parser.add_argument('--vis-file', type=str, help='filename in which to save HTML graph visualization (default: ' + default + ')', default=default)
    default = 'crawl.pickle'
    parser.add_argument('--data-file', type=str, help='filename in which to save crawled graph data (default: ' + default + ')', default=default)
    default = 1000
    parser.add_argument('--width', type=int, help='width of graph visualization in pixels (default: ' + str(default) + ')', default=default)
    default = 800
    parser.add_argument('--height', type=int, help='height of graph visualization in pixels (default: ' + str(default) + ')', default=default)
    parser.add_argument('--visit-external', action='store_true', help='detect broken external links (slower)')
    parser.add_argument('--show-buttons', action='store_true', help='show visualization settings UI')
    parser.add_argument('--options', type=str, help='file with drawing options (use --show-buttons to configure, then generate options)')
    parser.add_argument('--from-data-file', type=str, help='create visualization from given data file', default=None)
    parser.add_argument('--force', action='store_true', help='override warnings about base URL')
    parser.add_argument('--save-txt', type=str, nargs='?', help='filename in which to save adjacency matrix (if no argument, uses adj_matrix.txt). Also saves node labels to [filename]_nodes.txt', const='adj_matrix.txt', default=None)
    parser.add_argument('--save-npz', type=str, nargs='?', help='filename in which to save sparse adjacency matrix (if no argument, uses adj_matrix.npz). Also saves node labels to [filename]_nodes.txt',  const='adj_matrix.npz', default=None)

    args = parser.parse_args()

    print("l'url è: " + args.site_url)
    new_dir = "scanned_sites/" +  args.site_url.split("/")[2]
    try:
        os.makedirs(new_dir)
    except:
        pass


    if args.from_data_file is None:
        if not args.site_url.endswith('/'):
            if not args.force:
                print('Warning: no trailing slash on site_url (may get duplicate homepage node). If you really don\'t want the trailing slash, run with --force')
                exit(1)

        if not args.site_url.startswith('https'):
            if not args.force:
                print('Warning: not using https. If you really want to use http, run with --force')
                exit(1)

        edges, error_codes, resource_pages = crawl(args.site_url, args.visit_external)
        print('Crawl complete.')

        with open(str(new_dir + '/pages.txt'), 'w') as f:
            for i in edges:
                if 'Javascript:' not in i[1]:
                    f.write(str(i[1]) + '\n')
        print(f'Saved crawl data to {args.data_file}')
    else:
        with open(args.from_data_file, 'rb') as f:
            edges, error_codes, resource_pages, site_url = pickle.load(f)
            args.site_url = site_url

