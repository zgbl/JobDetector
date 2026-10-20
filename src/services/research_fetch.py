"""Bounded HTTPS evidence retrieval. Every redirect resolves to public, pinned IPs."""
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

MAX_BYTES = 3_000_000


def checked_target(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Only public HTTPS pages are supported.')
    host = parsed.hostname.encode('idna').decode('ascii')
    if host == 'localhost' or not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise ValueError('Invalid public hostname.')
    addresses = {row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or not all(ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('Private or reserved network destinations are not supported.')
    return host, sorted(addresses)[0], parsed.path or '/', parsed.query


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        super().__init__(host, timeout=5, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        raw = socket.create_connection((self.ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def fetch_evidence(url, deadline=None):
    deadline = min(deadline or float("inf"), time.monotonic()+8)
    for _ in range(4):
        if time.monotonic() >= deadline:
            raise ValueError("Page retrieval timed out.")
        host, ip, path, query = checked_target(url)
        connection = PinnedHTTPS(host, ip)
        connection.timeout = max(.1, min(5, deadline-time.monotonic()))
        try:
            connection.request('GET', path + ('?' + query if query else ''), headers={
                'Host': host, 'User-Agent': 'JobDetector-Research-Lab/1.0', 'Accept': 'text/html,application/json', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Redirect has no destination.')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f'Page returned HTTP {response.status}.')
            content_type = response.getheader('Content-Type', '')
            if not any(kind in content_type for kind in ('text/html', 'application/json', 'text/plain')):
                raise ValueError('Page is not readable text.')
            chunks, length = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise ValueError('Page retrieval timed out.')
                chunk = response.read(min(32768,MAX_BYTES+1-length))
                if not chunk:break
                chunks.append(chunk);length += len(chunk)
                if length > MAX_BYTES:
                    raise ValueError('Page exceeds the experiment size limit.')
            raw = b''.join(chunks)
        finally:
            connection.close()
        html = raw.decode('utf-8', errors='replace')
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else host
        links = [{'url': urljoin(url, a.get('href', '')), 'label': a.get_text(' ', strip=True)} for a in soup.find_all('a', href=True)]
        for tag in soup(['script', 'style', 'nav', 'noscript', 'svg', 'header']):
            tag.decompose()
        text = soup.get_text(' ', strip=True)
        return {'url': url, 'title': title[:200], 'text': text[:22000], 'links': links[:180]}
    raise ValueError('Too many redirects.')
