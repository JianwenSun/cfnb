#!/usr/bin/env python3
"""
将cfst结果文件转换为指定格式
输入格式: IP  4  4  0.00  11.19  0.00  N/A
输出格式: IP:443#TAG
"""

import sys
import os

def convert_file(input_file, output_file=None, tag='CF'):
    if not os.path.exists(input_file):
        print(f"错误: 文件不存在 {input_file}")
        return False
    
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}_formatted.txt"
    
    count = 0
    na_count = 0
    
    with open(input_file, 'r', encoding='utf-8') as f_in:
        with open(output_file, 'w', encoding='utf-8') as f_out:
            for line_num, line in enumerate(f_in, 1):
                line = line.strip()
                if not line:
                    continue
                
                if ',' in line:
                    parts = [p.strip() for p in line.split(',')]
                else:
                    parts = line.split()
                
                if not parts:
                    continue
                
                if line_num == 1 and parts[0] in ['IP', 'IP地址', 'IP Address']:
                    continue
                
                ip = parts[0]
                
                region_tag = tag
                if ',' in line and len(parts) >= 7:
                    region = parts[6]
                    if region and region != 'N/A':
                        region_tag = region
                    else:
                        na_count += 1
                
                if is_valid_ip(ip):
                    output_line = f"{ip}:443#{region_tag}"
                    f_out.write(output_line + '\n')
                    count += 1
    
    print(f"成功转换 {count} 条数据")
    if na_count > 0:
        print(f"其中 {na_count} 条使用默认标签 '{tag}'")
    print(f"输出文件: {output_file}")
    return True

def is_valid_ip(ip):
    if ':' in ip:
        parts = ip.split(':')
        if len(parts) >= 8:
            return True
        return False
    
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    
    try:
        for part in parts:
            num = int(part)
            if num < 0 or num > 255:
                return False
        return True
    except:
        return False

def main():
    print("=" * 60)
    print("CFST结果文件格式转换工具")
    print("=" * 60)
    
    if len(sys.argv) < 2:
        print("\n使用方法:")
        print("  python3 convert_cfst.py <输入文件> [输出文件] [标签]")
        print("\n示例:")
        print("  python3 convert_cfst.py result.csv")
        print("  python3 convert_cfst.py result.csv output.txt CF")
        print("  python3 convert_cfst.py result.csv output.txt HK")
        print("\n默认:")
        print("  - 输出文件: <输入文件名>_formatted.txt")
        print("  - 标签: CF")
        return
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    tag = sys.argv[3] if len(sys.argv) > 3 else 'CF'
    
    print(f"\n输入文件: {input_file}")
    print(f"标签: {tag}")
    print()
    
    convert_file(input_file, output_file, tag)

if __name__ == '__main__':
    main()
