import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import os
import common_function
import re
from playwright.sync_api import sync_playwright
import time
import subprocess
import sys
 
def ensure_playwright_installed():
    try:
        if getattr(sys, 'frozen', False):
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                          check=True, capture_output=True)
        else:
            subprocess.run(["playwright", "install", "chromium"], 
                          check=True, capture_output=True)
    except Exception as e:
        print(f"Failed to install Playwright: {e}")
        return False
    return True

if not ensure_playwright_installed():
    sys.exit(1)

duplicate_list = []
error_list     = []
completed_list = []
 
try:
    with open('urlDetails.txt', 'r', encoding='utf-8') as file:
        url_list = [l for l in file.read().splitlines() if l.strip()]
 
    try:
        with open('completed.txt', 'r', encoding='utf-8') as read_file:
            read_content = read_file.read().splitlines()
    except FileNotFoundError:
        open('completed.txt', 'w', encoding='utf-8').close()
        read_content = []
 
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()
 
        for entry in url_list:
            try:
                url, url_id = entry.split(',')
                print(f"Processing URL: {url}")
                
                now = datetime.now()
                current_date = now.strftime("%Y-%m-%d")
                current_time = now.strftime("%H:%M:%S")
 
                ini_path = os.path.join(os.getcwd(), "Ref_4322.ini")
                Download_Path, Email_Sent, Duplicate_Check, User_id = common_function.read_ini_file(ini_path)
 
                current_out    = common_function.return_current_outfolder(Download_Path, User_id, url_id)
                out_excel_file = common_function.output_excel_name(current_out)
                Ref_value      = "Ref_4322"
 
                duplicate_list.clear()
                error_list.clear()
                completed_list.clear()
                final_data_list = []
                pdf_count       = 1
 
                page.goto(url, wait_until='networkidle', timeout=60000)
                time.sleep(2)
                soup = BeautifulSoup(page.content(), 'html.parser')
                
                print(f"Page loaded successfully")
 
                current_issue = soup.find('a', string=re.compile(r'Current issue', re.I))
                if current_issue:
                    issue_href = current_issue['href']
                    issue_url  = requests.compat.urljoin(url, issue_href)
                    page.goto(issue_url, wait_until='networkidle')
                    time.sleep(2)
                    soup = BeautifulSoup(page.content(), 'html.parser')
                else:
                    print("No 'Current issue' link found. Looking for issue/volume links...")
                    
                    nav_links = soup.find_all('a', href=True)
                    for link in nav_links:
                        text = link.get_text(strip=True).lower()
                        if any(word in text for word in ['current issue', 'browse', 'issue', 'volume']):
                            if link.get('href') and not link['href'].startswith('javascript'):
                                nav_url = requests.compat.urljoin(url, link['href'])
                                print(f"Trying navigation link: {text} -> {nav_url}")
                                page.goto(nav_url, wait_until='networkidle')
                                time.sleep(2)
                                soup = BeautifulSoup(page.content(), 'html.parser')
                                break
 
                volume = issue = year = month = ''
                j_list = soup.find('div', class_='j_list')
                if j_list:
                    j_title = j_list.find('p', class_='j_title')
                    if j_title:
                        title_text = j_title.get_text()
                        print(f"Issue info: {title_text}")
                        
                        vol_match = re.search(r'Vol\.\s*(\d+)', title_text)
                        issue_match = re.search(r'No\.\s*(\d+)', title_text)
                        year_match = re.search(r'(\d{4})', title_text)
                        month_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)', title_text)
                        
                        volume = vol_match.group(1) if vol_match else ''
                        issue = issue_match.group(1) if issue_match else ''
                        year = year_match.group(1) if year_match else ''
                        month = month_match.group(1) if month_match else ''
                        
                        print(f"Extracted - Volume: {volume}, Issue: {issue}, Year: {year}, Month: {month}")
 
                articles = soup.select('div.con_box')
                article_boxes = []
                for box in articles:
                    link = box.find('a', href=lambda x: x and 'journal_detail.html' in x)
                    if link:
                        article_boxes.append(box)
                
                articles = article_boxes
                print(f"Found {len(articles)} articles on current page")
 
                for art in articles:
                    try:
                        title_elem = art.find('h2')
                        if title_elem:
                            title_link = title_elem.find('a')
                            title = title_link.get('title', '') or title_link.get_text(strip=True)
                        else:
                            title = ''
                        
                        detail_link = art.find('a', href=lambda x: x and 'journal_detail.html' in x)
                        if not detail_link:
                            print(f"No detail link found for article: {title}")
                            continue
                            
                        detail_href = detail_link['href']
                        detail_url = requests.compat.urljoin(url, detail_href)
                        
                        print(f"Processing article: {title}")
                        
                        author_elem = art.find('p', class_='author')
                        author = author_elem.get_text(strip=True) if author_elem else ''
                        page_range = ''  

                        try:
                            print(f"Navigating to detail page...")
                            page.goto(detail_url, wait_until='networkidle', timeout=30000)
                            time.sleep(2)
                            det_soup = BeautifulSoup(page.content(), 'html.parser')
                            print(f"Detail page loaded successfully")
                            
                        except Exception as nav_err:
                            print(f"Failed to load detail page: {nav_err}")
                            error_list.append(f"{title}: Failed to load detail page - {nav_err}")
                            continue

                        doi_text = det_soup.get_text()
                        doi_match = re.search(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', doi_text, re.I)
                        doi = doi_match.group(0) if doi_match else ''
                        print(f"Found DOI: {doi}")

                        print("Searching for PDF link...")
                        pdf_download_url = '' 
                        fname = ''
                        
                        code_match = re.search(r'code=(\d+)', detail_url)
                        if code_match:
                            article_code = code_match.group(1)
                            print(f"Article code: {article_code}")
                            
                            pdf_patterns = [
                                f"http://journal.korfin.org/upload/pdf/{article_code}.pdf",
                                f"http://journal.korfin.org/data/pdf/{article_code}.pdf",
                                f"http://journal.korfin.org/pdf/{article_code}.pdf",
                                f"http://journal.korfin.org/files/pdf/{article_code}.pdf",
                                f"http://journal.korfin.org/journal/pdf/{article_code}.pdf"
                            ]
                            
                            for pdf_url in pdf_patterns:
                                try:
                                    print(f"Trying direct PDF: {pdf_url}")
                                    pdf_res = requests.get(pdf_url, timeout=30)
                                    
                                    if (pdf_res.status_code == 200 and 
                                        len(pdf_res.content) > 1000 and  
                                        (pdf_res.headers.get('content-type', '').startswith('application/pdf') or
                                         pdf_res.content.startswith(b'%PDF'))):
                                        
                                        fname = f"A{pdf_count}.pdf"
                                        pdf_path = os.path.join(current_out, fname)
                                        with open(pdf_path, 'wb') as pf:
                                            pf.write(pdf_res.content)
                                        
                                        print(f"✅ PDF downloaded: {fname} ({len(pdf_res.content)} bytes)")
                                        pdf_download_url = pdf_url 
                                        break
                                    else:
                                        print(f"  Not a PDF: {pdf_res.status_code}, {len(pdf_res.content)} bytes")
                                        
                                except Exception as e:
                                    print(f"  Failed: {e}")
                                    continue
                            
                            if not pdf_download_url:
                                print("Looking for download buttons on detail page...")
                                
                                download_patterns = [
                                    r'pdf.*다운로드',
                                    r'다운로드.*pdf',
                                    r'원문.*다운로드',
                                    r'download.*pdf',
                                    r'pdf.*download',
                                    r'full.*text.*pdf',
                                    r'view.*pdf'
                                ]
                                
                                for pattern in download_patterns:
                                    download_elem = det_soup.find('a', string=re.compile(pattern, re.I))
                                    if download_elem and download_elem.get('href'):
                                        download_url = requests.compat.urljoin(detail_url, download_elem['href'])
                                        
                                        try:
                                            print(f"Trying download button: {download_url}")
                                            pdf_res = requests.get(download_url, timeout=30)
                                            
                                            if (pdf_res.status_code == 200 and 
                                                len(pdf_res.content) > 1000 and
                                                (pdf_res.headers.get('content-type', '').startswith('application/pdf') or
                                                 pdf_res.content.startswith(b'%PDF'))):
                                                
                                                fname = f"A{pdf_count}.pdf"
                                                pdf_path = os.path.join(current_out, fname)
                                                with open(pdf_path, 'wb') as pf:
                                                    pf.write(pdf_res.content)
                                                
                                                print(f"✅ PDF downloaded via button: {fname} ({len(pdf_res.content)} bytes)")
                                                pdf_download_url = download_url  # Store the actual PDF URL
                                                break
                                                
                                        except Exception as e:
                                            print(f"  Download button failed: {e}")
                                            continue
                        
                        if not pdf_download_url:
                            print("Trying Playwright download...")
                            try:
                                download_selectors = [
                                    'a:has-text("PDF")',
                                    'a:has-text("다운로드")',
                                    'a:has-text("Download")',
                                    'button:has-text("PDF")',
                                    'button:has-text("다운로드")',
                                    '[onclick*="pdf"]',
                                    '[onclick*="download"]'
                                ]
                                
                                for selector in download_selectors:
                                    try:
                                        download_element = page.locator(selector).first
                                        if download_element.is_visible():
                                            print(f"Found download element: {selector}")
                                            
                                            element_href = download_element.get_attribute('href')
                                            if element_href and not element_href.startswith('javascript'):
                                                test_url = requests.compat.urljoin(detail_url, element_href)
                                                try:
                                                    test_res = requests.head(test_url, timeout=10)
                                                    if test_res.headers.get('content-type', '').startswith('application/pdf'):
                                                        pdf_download_url = test_url
                                                        print(f"✅ Found PDF link via Playwright: {pdf_download_url}")
                                                        
                                                        pdf_res = requests.get(pdf_download_url, timeout=30)
                                                        fname = f"A{pdf_count}.pdf"
                                                        pdf_path = os.path.join(current_out, fname)
                                                        with open(pdf_path, 'wb') as pf:
                                                            pf.write(pdf_res.content)
                                                        break
                                                except:
                                                    pass
                                            
                                            if not pdf_download_url:
                                                with page.expect_download() as download_info:
                                                    download_element.click()
                                                    download = download_info.value
                                                
                                                fname = f"A{pdf_count}.pdf"
                                                pdf_path = os.path.join(current_out, fname)
                                                download.save_as(pdf_path)
                                                
                                                pdf_download_url = f"http://journal.korfin.org/download/{article_code}.pdf"
                                                print(f"✅ PDF downloaded via Playwright click: {fname}")
                                                break
                                            
                                    except Exception as click_err:
                                        print(f"  Click failed for {selector}: {click_err}")
                                        continue
                                
                            except Exception as pw_err:
                                print(f"Playwright download failed: {pw_err}")
                        
                        if not pdf_download_url:
                            print("❌ No working PDF download method found")
                            error_list.append(f"{title}: No PDF download available")
                            continue

                        if not fname:
                            fname = f"A{pdf_count}.pdf"

                        print("✅ PDF downloaded successfully, checking for duplicates...")
                        
                        if title in completed_list:
                            duplicate_list.append(title)
                            print(f"Duplicate found: {title}")
                            continue

                        dup, tpa = common_function.check_duplicate(doi, title, url_id, volume, issue)
                        if str(Duplicate_Check).lower() == 'true' and dup:
                            duplicate_list.append(f"{pdf_download_url} - duplicate TPAID:{tpa}")
                            print(f"Duplicate found: {title}")
                            continue

                        final_data_list.append({
                            'Title': title,
                            'DOI': doi,
                            'Publisher Item Type': '',
                            'ItemID': '',
                            'Identifier': '',
                            'Volume': volume,
                            'Issue': issue,
                            'Supplement': '',
                            'Part': '',
                            'Special Issue': '',
                            'Page Range': page_range,
                            'Month': month,
                            'Day': "",
                            'Year': year,
                            'Article Type': '',
                            'Abstract': '',
                            'Funding': '',
                            'Acknowledgement': '',
                            'URL': pdf_download_url, 
                            'SOURCE File Name': fname,
                            'user_id': User_id,
                            'TOC File Name': ''
                        })

                        pd.DataFrame(final_data_list).to_excel(out_excel_file, index=False)
                        completed_list.append(title)
                        if title not in read_content:
                            with open('completed.txt','a', encoding='utf-8') as cf:
                                cf.write(title + '\n')

                        pdf_count += 1
                        print(f"Article processed successfully: {title}\n")

                    except Exception as art_err:
                        print(f"Error processing article '{title}': {art_err}")
                        error_list.append(f"{title}: {art_err}")
                        with open(os.path.join(current_out,'log.txt'),'a') as lg:
                            lg.write(f"{title} - {art_err}\n")
                        continue

            except Exception as url_err:
                print(f"Error processing URL {url}: {url_err}")
                with open(os.path.join(current_out,'log.txt'),'a') as lg:
                    lg.write(f"URL Error: {url} - {url_err}\n")

        browser.close()

except Exception as e:
    print(f"Fatal error: {e}")

try:
    response = requests.post('https://your-endpoint.com/api/download-count', 
                           json={'count': len(completed_list)})
    print("The download count POST request was sent successfully.")
except:
    print("Failed to send download count POST request.")