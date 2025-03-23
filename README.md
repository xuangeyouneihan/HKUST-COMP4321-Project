# HKUST-COMP4321-Project

```
       　  　▃▆█▇▄▖
　 　 　 ▟◤▖　　　◥█▎
   　 ◢◤　 ▐　　　 　▐▉
　 ▗◤　　　▂　▗▖　　▕█▎
　◤　▗▅▖◥▄　▀◣　　█▊
▐　▕▎◥▖◣◤　　　　◢██
█◣　◥▅█▀　　　　▐██◤
▐█▙▂　　     　◢██◤
◥██◣　　　　◢▄◤
 　　▀██▅▇▀
```

This is a work-in-progress web search engine.

## Phase 1

### Overview

- A spider crawling a site using BFS and generating a foward index given a start page.
- An indexer generating two inverted indexes according to the body keywords and the title keywords from the spider's result.
- Both the spider and the indexer will store their results to databases. See [Database Schema](schema.md)

### Test

If your system is Windows, make sure you have installed Python 3.13 on your system, then run following command in the directory:

```sh
pip install -r requirements.txt
python spider_test.py
```

If your system is Arch Linux, run following command in the directory:

```sh
sudo pacman -S python python-requests python-lxml nltk-data python-nltk
python spider_test.py
```

The test program will first try to read `webpages.db`. If the database can be read, it will use the data in the database to generate `spider_result.txt`. Otherwise, it will crawl the webpages and generate `spider_result.txt`. Then, it will run the indexer to generate or update `body_inverted_index.db` and `title_inverted_index.db`.

### Last Modified Date Handling

The default value of the last modified date is 1970-01-01 00:00:00 UTC. When a webpage is being visited, the spider will first check the Last-Modified key in the header. If the Last-Modified key exists, it will insert it into the date property of the webpage. Otherwise, it will treat the current time as the last modified date.

### Cyclic Path Handling

Here's a breakdown of how cyclic paths are handled:

- **Parent Links**: Each page tracks its `parent_links` (URLs linking to it). When a page is revisited, its parent links are updated to include the current page, but it is **not requeued**.

  ```python
  existing_child_page.parent_links.add(current_page.url)
  ```

  This avoids reprocessing the same page again via the queue.
- **Child Links**: When processing child links, the code checks if the child is already in `visited `and has not been updated. If so, it updates the child's parent links but does not requeue it. Otherwise, add the link to the queue. After that, if the current page is updated this time, the spider will recheck its child links. If there exists a page which was a child link of the current page previously but not a child link of the current page now, the spider will go through `visited` and the queue to search for the page. If the page is found, then the current page will be removed from its parent links. If it has no parent link after removing and it is not the start page, it will be removed from `visited` and the queue.

## Schema

[Database Schema](schema.md)

## Author

* Yu Yingxuan (xuangeyouneihan)
* Du Maosen (ThisIsNotCodingJellyfish)
* The two other persons in our group did not participate in the project. Wu Lixin has applied to late-drop for this course, so it is unfair to let him contribute something to our project. Even so, he emailed to us and demonstrated his case, and he provided some ideas to our program. By contrast, Lin Xuanyu is much more irresponsible. He has not replied any words to we three since our group was found, whether via Email or via Canvas.
