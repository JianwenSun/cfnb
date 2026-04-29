#!/usr/bin/env python3
"""
爬取 api.uouin.com/cloudflare.html 页面的 CloudFlare 优选IP 表格数据
支持从URL或本地HTML文件读取
"""

import requests
from bs4 import BeautifulSoup
import urllib3
import time
import sys
import os
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def scrape_from_url():
    url = 'https://api.uouin.com/cloudflare.html'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    session = requests.Session()
    session.verify = False
    session.headers.update(headers)
    
    for attempt in range(3):
        try:
            print(f"尝试连接URL... (第 {attempt + 1} 次)")
            response = session.get(url, timeout=30)
            response.encoding = 'utf-8'
            return response.text
        except Exception as e:
            print(f"错误: {e}")
            if attempt < 2:
                time.sleep(2)
                continue
    return None

def scrape_from_file(filepath):
    try:
        print(f"从文件读取: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"读取文件错误: {e}")
        return None

def clean_text(text):
    """清理文本，移除多余内容"""
    text = re.sub(r'已复制!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    tables = soup.find_all('table')
    
    for table in tables:
        headers_row = table.find('thead')
        if headers_row:
            th_list = headers_row.find_all(['th', 'td'])
            headers = [th.get_text(strip=True) for th in th_list]
            
            if '优选IP' in headers or '线路' in headers:
                print(f"找到目标表格，表头: {headers}")
                tbody = table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    for row in rows:
                        th_cols = row.find_all('th')
                        td_cols = row.find_all('td')
                        
                        if td_cols:
                            row_data = [clean_text(col.get_text(strip=True)) for col in td_cols]
                            if row_data and len(row_data) >= 2:
                                line_type = row_data[0]
                                ip = row_data[1]
                                results.append([line_type, ip])
    
    if not results:
        print("未在thead中找到数据，尝试查找所有表格...")
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) > 1:
                first_row = rows[0]
                header_cells = first_row.find_all(['th', 'td'])
                headers = [cell.get_text(strip=True) for cell in header_cells]
                
                header_text = ''.join(headers)
                if any(keyword in header_text for keyword in ['优选IP', '线路', '丢包', '延迟']):
                    print(f"找到目标表格，表头: {headers}")
                    for row in rows[1:]:
                        th_cols = row.find_all('th')
                        td_cols = row.find_all('td')
                        
                        if td_cols:
                            row_data = [clean_text(col.get_text(strip=True)) for col in td_cols]
                            if row_data and len(row_data) >= 2:
                                line_type = row_data[0]
                                ip = row_data[1]
                                results.append([line_type, ip])
    
    return results

def save_to_file(data, filename='uouin.txt'):
    if not data:
        print("没有数据可保存")
        return False
    
    line_mapping = {
        '电信': 'CT',
        '联通': 'CU',
        '移动': 'CM',
        '多线': 'Multi',
        'IPV6': 'IPv6',
        'IPv6': 'IPv6'
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        for row in data:
            if len(row) >= 2:
                line_type = row[0]
                ip = row[1]
                tag = line_mapping.get(line_type, line_type)
                
                if ':' in ip and not ip.startswith('['):
                    output = f"[{ip}]:443#{tag}"
                else:
                    output = f"{ip}:443#{tag}"
                
                f.write(output + '\n')
    
    print(f"成功保存 {len(data)} 条数据到 {filename}")
    return True

def main():
    print("=" * 60)
    print("CloudFlare 优选IP 数据爬取脚本 (uouin.com)")
    print("=" * 60)
    
    html_content = None
    
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        html_content = scrape_from_file(filepath)
    else:
        html_content = scrape_from_url()
    
    if not html_content:
        print()
        print("无法获取页面内容")
        print()
        print("使用方法:")
        print("  1. 直接运行: python3 scrape_uouin.py")
        print("  2. 从文件读取: python3 scrape_uouin.py <html文件路径>")
        return
    
    print("解析HTML内容...")
    data = parse_html(html_content)
    
    if data:
        print()
        print(f"获取到 {len(data)} 条数据")
        save_to_file(data)
        
        print()
        print("数据预览 (前5条):")
        line_mapping = {
            '电信': 'CT',
            '联通': 'CU',
            '移动': 'CM',
            '多线': 'Multi',
            'IPV6': 'IPv6',
            'IPv6': 'IPv6'
        }
        for i, row in enumerate(data[:5], 1):
            if len(row) >= 2:
                line_type = row[0]
                ip = row[1]
                tag = line_mapping.get(line_type, line_type)
                
                if ':' in ip and not ip.startswith('['):
                    print(f"{i}. [{ip}]:443#{tag}")
                else:
                    print(f"{i}. {ip}:443#{tag}")
    else:
        print()
        print("未能从HTML中提取表格数据")
        print("可能页面结构已变化，请检查HTML文件")

if __name__ == '__main__':
    main()
