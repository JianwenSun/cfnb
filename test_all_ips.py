#!/usr/bin/env python3
"""
对根目录下指定 txt 文件（DE.txt JP.txt NL.txt SG.txt uouin.txt ALL.txt）中的 IP 进行综合测试
（TCP延迟 + HTTP可用性 + 带宽测速）
结果输出到 tested_ips.txt
"""

import os
import re
import sys
import socket
import time
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 配置参数 ====================
CONFIG = {
    "TCP_TIMEOUT": 2.0,          # TCP 连接超时(秒)
    "TCP_PROBES": 3,             # 每个 IP 测试次数
    "MIN_SUCCESS_RATE": 0.5,     # 最低成功率(0~1)
    "MAX_TCP_WORKERS": 200,      # TCP 并发数
    "TEST_PORT": 443,            # 默认测试端口

    "TEST_AVAILABILITY": True,   # 是否测试 HTTP 可用性
    "AVAILABILITY_API": "https://api.090227.xyz/check",
    "AVAILABILITY_TIMEOUT": 5,
    "AVAILABILITY_CONNECT_TIMEOUT": 3,
    "AVAILABILITY_WORKERS": 10,

    "TEST_BANDWIDTH": True,      # 是否测试带宽
    "BANDWIDTH_SIZE_MB": 0.5,    # 测速文件大小(MB)
    "BANDWIDTH_TIMEOUT": 5,      # 测速超时(秒)
    "BANDWIDTH_CONNECT_TIMEOUT": 3,
    "BANDWIDTH_WORKERS": 10,
    "BANDWIDTH_CANDIDATES": 0,  # 进入带宽测速的候选数（0=全部）

    "GLOBAL_TOP_N": 0,          # 最终输出 Top N（0=全部）

    "PROGRESS_INTERVAL": 1,      # 进度打印间隔(秒)
}

# ==================== 正则 ====================
IPV4_RE = re.compile(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')
NODE_PATTERN = re.compile(r'^(\d+\.\d+\.\d+\.\d+):(\d+)#(.+)$')

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 要测试的文件列表（根目录下）
TARGET_FILES = ["JP.txt", "US.txt", "DE.txt", "SG.txt", "uouin.txt", "ALL.txt", "NL.txt"]


def extract_ips_from_file(filepath):
    """从文件中提取所有 IP:端口#标签 格式的节点和纯 IP"""
    all_nodes = {}  # key: "ip:port", value: (ip, port, labels_set)

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # 尝试匹配 IP:端口#标签 格式
                m = NODE_PATTERN.match(line)
                if m:
                    ip, port, label = m.groups()
                    key = f"{ip}:{port}"
                    if key not in all_nodes:
                        all_nodes[key] = (ip, int(port), set())
                    if label:
                        all_nodes[key][2].add(label)
                    continue

                # 尝试匹配 IP#标签 格式 (如 uouin.txt)
                if '#' in line:
                    parts = line.split('#', 1)
                    ip_part = parts[0].strip()
                    label = parts[1].strip()
                    m_ip = IPV4_RE.match(ip_part)
                    if m_ip:
                        ip = m_ip.group(1)
                        if ':' in ip_part:
                            try:
                                port = int(ip_part.split(':')[1])
                            except ValueError:
                                port = CONFIG["TEST_PORT"]
                        else:
                            port = CONFIG["TEST_PORT"]
                        key = f"{ip}:{port}"
                        if key not in all_nodes:
                            all_nodes[key] = (ip, port, set())
                        if label:
                            all_nodes[key][2].add(label)
                        continue

                # 纯 IP 提取
                for m in IPV4_RE.finditer(line):
                    ip = m.group(1)
                    key = f"{ip}:{CONFIG['TEST_PORT']}"
                    if key not in all_nodes:
                        all_nodes[key] = (ip, CONFIG["TEST_PORT"], set())
    except Exception as e:
        print(f"  读取 {filepath} 失败: {e}")

    return all_nodes


def scan_target_files():
    """扫描指定的 txt 文件，提取 IP"""
    all_nodes = {}  # key: "ip:port", value: (ip, port, labels_set)
    found_files = []

    for fname in TARGET_FILES:
        filepath = os.path.join(BASE_DIR, fname)
        if not os.path.isfile(filepath):
            print(f"  {fname}: 文件不存在，跳过")
            continue
        found_files.append(fname)
        nodes = extract_ips_from_file(filepath)
        print(f"  {fname}: 提取到 {len(nodes)} 个节点")
        for key, (ip, port, labels) in nodes.items():
            if key not in all_nodes:
                all_nodes[key] = (ip, port, set())
            all_nodes[key][2].update(labels)

    return found_files, all_nodes


def test_tcp_latency(ip, port):
    """测试 TCP 延迟，返回 (最小延迟ms, 成功次数)"""
    min_lat = float('inf')
    success = 0
    for _ in range(CONFIG["TCP_PROBES"]):
        try:
            start = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(CONFIG["TCP_TIMEOUT"])
                s.connect((ip, port))
            lat_ms = (time.time() - start) * 1000
            if lat_ms < min_lat:
                min_lat = lat_ms
            success += 1
        except Exception:
            continue
    return min_lat, success


def check_availability(ip, port):
    """检测 IP 可用性（通过代理检测 API）"""
    proxyip = f"{ip}:{port}"
    try:
        import requests
        resp = requests.get(
            CONFIG["AVAILABILITY_API"],
            params={"proxyip": proxyip},
            timeout=(CONFIG["AVAILABILITY_CONNECT_TIMEOUT"], CONFIG["AVAILABILITY_TIMEOUT"])
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") is True:
                stack = data.get("inferred_stack", "unknown")
                probe = data.get("probe_results", {}).get("ipv4") or data.get("probe_results", {}).get("ipv6") or {}
                exit_info = probe.get("exit", {})
                country = exit_info.get("country", "")
                return True, stack, country
    except Exception:
        pass
    return False, "unknown", ""


def measure_bandwidth(ip, port):
    """使用 curl 测量带宽"""
    size_bytes = int(CONFIG["BANDWIDTH_SIZE_MB"] * 1024 * 1024)
    url = f"https://speed.cloudflare.com/__down?bytes={size_bytes}"

    null_dev = "NUL" if sys.platform == "win32" else "/dev/null"
    cmd = [
        "curl", "-s", "-o", null_dev,
        "-w", "%{size_download} %{time_total}",
        "--resolve", f"speed.cloudflare.com:{port}:{ip}",
        "--connect-timeout", str(CONFIG["BANDWIDTH_CONNECT_TIMEOUT"]),
        "--max-time", str(CONFIG["BANDWIDTH_TIMEOUT"]),
        "--insecure",
        url
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=CONFIG["BANDWIDTH_TIMEOUT"] + 2
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                dl_bytes = float(parts[0])
                time_total = float(parts[1])
                if time_total > 0 and dl_bytes > 0:
                    speed_mbps = (dl_bytes * 8) / (time_total * 1000 * 1000)
                    return speed_mbps
    except Exception:
        pass
    return 0


def main():
    print("=" * 60)
    print("  Cloudflare IP 综合测试工具")
    print(f"  目标文件: {', '.join(TARGET_FILES)}")
    print("=" * 60)

    # 1. 扫描指定 txt 文件，提取 IP
    print("\n[1/4] 扫描指定文件，提取 IP...")
    found_files, all_nodes = scan_target_files()
    total = len(all_nodes)
    print(f"\n去重后共 {total} 个 IP:端口 节点")

    if total == 0:
        print("未找到任何 IP，退出。")
        sys.exit(0)

    # 2. TCP 延迟测试
    print(f"\n[2/4] TCP 延迟测试（超时 {CONFIG['TCP_TIMEOUT']}s，每节点 {CONFIG['TCP_PROBES']} 次，并发 {CONFIG['MAX_TCP_WORKERS']}）...")

    tcp_results = []  # (ip, port, label, min_lat_ms, success_count)
    completed = 0
    last_print = time.time()

    def tcp_worker(key):
        ip, port, labels = all_nodes[key]
        min_lat, success = test_tcp_latency(ip, port)
        label_str = ",".join(sorted(labels)) if labels else ""
        return (ip, port, label_str, min_lat, success)

    with ThreadPoolExecutor(max_workers=CONFIG["MAX_TCP_WORKERS"]) as executor:
        futures = {executor.submit(tcp_worker, key): key for key in all_nodes}
        for future in as_completed(futures):
            completed += 1
            ip, port, label, min_lat, success = future.result()
            rate = success / CONFIG["TCP_PROBES"]
            if rate >= CONFIG["MIN_SUCCESS_RATE"] and success > 0:
                tcp_results.append((ip, port, label, min_lat, success))
            now = time.time()
            if now - last_print >= CONFIG["PROGRESS_INTERVAL"] or completed == total:
                passed = len(tcp_results)
                print(f"\r  进度：{completed}/{total} ({completed/total*100:.1f}%) 通过：{passed}", end="", flush=True)
                last_print = now

    print(f"\n  TCP 测试完成，{len(tcp_results)} 个节点通过（成功率 >= {CONFIG['MIN_SUCCESS_RATE']*100:.0f}%）")

    if not tcp_results:
        print("没有节点通过 TCP 测试，退出。")
        sys.exit(0)

    # 按延迟排序
    tcp_results.sort(key=lambda x: x[3])

    # 3. 可用性检测
    avail_results = []  # (ip, port, label, min_lat_ms, stack, country)
    if CONFIG["TEST_AVAILABILITY"]:
        # 取延迟最低的候选
        candidates = tcp_results[:CONFIG["BANDWIDTH_CANDIDATES"]] if CONFIG["BANDWIDTH_CANDIDATES"] > 0 else tcp_results
        print(f"\n[3/4] 可用性检测（对前 {len(candidates)} 个节点，并发 {CONFIG['AVAILABILITY_WORKERS']}）...")

        completed = 0
        total_c = len(candidates)
        last_print = time.time()

        def avail_worker(item):
            ip, port, label, min_lat, success = item
            ok, stack, country = check_availability(ip, port)
            return (ip, port, label, min_lat, ok, stack, country)

        with ThreadPoolExecutor(max_workers=CONFIG["AVAILABILITY_WORKERS"]) as executor:
            futures = {executor.submit(avail_worker, item): item for item in candidates}
            for future in as_completed(futures):
                completed += 1
                ip, port, label, min_lat, ok, stack, country = future.result()
                if ok:
                    avail_results.append((ip, port, label, min_lat, stack, country))
                now = time.time()
                if now - last_print >= CONFIG["PROGRESS_INTERVAL"] or completed == total_c:
                    print(f"\r  进度：{completed}/{total_c} ({completed/total_c*100:.1f}%) 通过：{len(avail_results)}", end="", flush=True)
                    last_print = now

        print(f"\n  可用性检测完成，{len(avail_results)} 个节点可用")

        if not avail_results:
            print("⚠️ 没有节点通过可用性检测，使用 TCP 结果继续。")
            avail_results = [(ip, port, label, min_lat, "unknown", "") for ip, port, label, min_lat, _ in (tcp_results[:CONFIG["BANDWIDTH_CANDIDATES"]] if CONFIG["BANDWIDTH_CANDIDATES"] > 0 else tcp_results)]
    else:
        print("\n[3/4] 可用性检测已跳过")
        avail_results = [(ip, port, label, min_lat, "unknown", "") for ip, port, label, min_lat, _ in (tcp_results[:CONFIG["BANDWIDTH_CANDIDATES"]] if CONFIG["BANDWIDTH_CANDIDATES"] > 0 else tcp_results)]

    # 4. 带宽测速
    bw_results = []  # (ip, port, label, min_lat_ms, stack, country, speed_mbps)
    if CONFIG["TEST_BANDWIDTH"]:
        if not shutil.which("curl"):
            print("\n⚠️ 未检测到 curl，跳过带宽测速")
        else:
            print(f"\n[4/4] 带宽测速（{len(avail_results)} 个节点，并发 {CONFIG['BANDWIDTH_WORKERS']}，文件 {CONFIG['BANDWIDTH_SIZE_MB']}MB）...")

            completed = 0
            total_b = len(avail_results)
            last_print = time.time()

            def bw_worker(item):
                ip, port, label, min_lat, stack, country = item
                speed = measure_bandwidth(ip, port)
                return (ip, port, label, min_lat, stack, country, speed)

            with ThreadPoolExecutor(max_workers=CONFIG["BANDWIDTH_WORKERS"]) as executor:
                futures = {executor.submit(bw_worker, item): item for item in avail_results}
                for future in as_completed(futures):
                    completed += 1
                    ip, port, label, min_lat, stack, country, speed = future.result()
                    bw_results.append((ip, port, label, min_lat, stack, country, speed))
                    now = time.time()
                    if now - last_print >= CONFIG["PROGRESS_INTERVAL"] or completed == total_b:
                        print(f"\r  进度：{completed}/{total_b} ({completed/total_b*100:.1f}%)", end="", flush=True)
                        last_print = now

            print(f"\n  带宽测速完成")

            # 按速度排序
            bw_results.sort(key=lambda x: x[6], reverse=True)
    else:
        print("\n[4/4] 带宽测速已跳过")
        bw_results = [(ip, port, label, min_lat, stack, country, 0) for ip, port, label, min_lat, stack, country in avail_results]

    # 5. 输出结果
    top_n = CONFIG["GLOBAL_TOP_N"]
    final = bw_results[:top_n] if top_n > 0 else bw_results

    output_file = os.path.join(BASE_DIR, "tested_ips.txt")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Cloudflare IP 综合测试结果 - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 测试文件: {', '.join(found_files)}\n")
        f.write(f"# 格式: IP:端口#国家 延迟(ms) 速度(Mbps) 栈类型\n")
        f.write(f"# 共 {len(final)} 个节点\n\n")
        for ip, port, label, min_lat, stack, country, speed in final:
            country_str = country if country else (label.split(',')[0] if label else "??")
            line = f"{ip}:{port}#{country_str}  延迟:{min_lat:.0f}ms  速度:{speed:.2f}Mbps  栈:{stack}"
            f.write(line + "\n")

    print(f"\n{'=' * 60}")
    print(f"  测试完成！结果已保存到 {output_file}")
    print(f"  Top {len(final)} 节点：")
    print(f"{'=' * 60}")
    print(f"{'排名':<5}{'节点':<30}{'延迟':>8}{'速度':>12}{'栈':>10}")
    print("-" * 65)
    for i, (ip, port, label, min_lat, stack, country, speed) in enumerate(final, 1):
        country_str = country if country else (label.split(',')[0] if label else "??")
        print(f"{i:<5}{ip}:{port}#{country_str:<8}{min_lat:>7.0f}ms{speed:>10.2f}Mbps{stack:>10}")

    # 同时输出标准格式（兼容 main.py 的 ip.txt 格式）
    compat_file = os.path.join(BASE_DIR, "tested_ips_compat.txt")
    with open(compat_file, 'w', encoding='utf-8') as f:
        for ip, port, label, min_lat, stack, country, speed in final:
            country_str = country if country else (label.split(',')[0] if label else "??")
            f.write(f"{ip}:{port}#{country_str}\n")
    print(f"\n  兼容格式（IP:端口#国家）已保存到 {compat_file}")


if __name__ == "__main__":
    main()
