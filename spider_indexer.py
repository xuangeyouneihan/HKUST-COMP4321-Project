import requests
from lxml import html
from collections import deque
from urllib.parse import urljoin  # 用于处理相对链接

def spider(start_url, max_pages):
    """
    A simple web spider that crawls pages using BFS.

    :param start_url: The starting URL for the spider.
    :param max_pages: The maximum number of pages to crawl.
    :return: A set of visited URLs.
    """
    visited = set()  # To keep track of visited URLs
    queue = deque([start_url])  # BFS queue initialized with the start URL

    while queue and len(visited) < max_pages:
        current_url = queue.popleft()
        if current_url in visited:
            continue

        try:
            # Fetch the content of the current URL
            response = requests.get(current_url, timeout=5)
            response.raise_for_status()  # Raise an error for HTTP issues
            visited.add(current_url)

            # Parse the HTML content
            tree = html.fromstring(response.content)
            links = tree.xpath('//a/@href')  # Extract all href attributes

            # Normalize and filter links
            for link in links:
                # 将相对链接转换为绝对链接
                absolute_link = urljoin(current_url, link)
                if absolute_link not in visited:
                    queue.append(absolute_link)

            print(f"Crawled: {current_url}")
        except Exception as e:
            print(f"Failed to crawl {current_url}: {e}")

    return visited

# Example usage
if __name__ == "__main__":
    start_url = "https://comp4321-hkust.github.io/testpages/testpage.htm"  # Replace with your starting URL
    max_pages = 30  # Replace with your desired maximum number of pages
    crawled_urls = spider(start_url, max_pages)
    print(f"Total crawled URLs: {len(crawled_urls)}")