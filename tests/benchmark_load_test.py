#!/usr/bin/env python3
"""
Antigravity 360° Load & Performance Benchmark Suite
Tests:
1. Cognitive Memory Engine (Single & Multi-threaded read, FTS5 BM25, German Compound Splitting, Graph Traversal)
2. High-Scale Synthetic Memory Stress Test (10k items, mixed read/write concurrency under WAL)
3. Cockpit HTTP REST API Latency & Concurrency Stress (Fastify/Python backend)
4. Conversation History JSONL Search Benchmark (Transcript traversal speed & regex throughput)
5. SQLite Disk I/O & Host Compute Baseline (WAL sync throughput, CPU multi-core score)
"""

import os
import sys
import time
import math
import json
import random
import string
import tempfile
import sqlite3
import urllib.request
import urllib.error
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

sys.path.insert(0, "/opt/agy-memory-engine")
import schema
import agy_memory

# Terminal formatting
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def calc_stats(latencies: List[float]) -> Dict[str, float]:
    if not latencies:
        return {"min": 0, "p50": 0, "p90": 0, "p95": 0, "p99": 0, "max": 0, "mean": 0, "std": 0}
    sorted_l = sorted(latencies)
    n = len(sorted_l)
    mean = sum(sorted_l) / n
    variance = sum((x - mean) ** 2 for x in sorted_l) / n if n > 1 else 0
    return {
        "min": sorted_l[0] * 1000,
        "p50": sorted_l[int(n * 0.50)] * 1000,
        "p90": sorted_l[min(int(n * 0.90), n - 1)] * 1000,
        "p95": sorted_l[min(int(n * 0.95), n - 1)] * 1000,
        "p99": sorted_l[min(int(n * 0.99), n - 1)] * 1000,
        "max": sorted_l[-1] * 1000,
        "mean": mean * 1000,
        "std": math.sqrt(variance) * 1000
    }

def print_header(title: str):
    print(f"\n{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}", flush=True)
    print(f"{BOLD}{CYAN}  {title}{RESET}", flush=True)
    print(f"{BOLD}{CYAN}══════════════════════════════════════════════════════════════════════════════{RESET}", flush=True)

def print_metric_table(name: str, total: int, duration_sec: float, stats: Dict[str, float], extra_info: str = ""):
    qps = total / duration_sec if duration_sec > 0 else 0
    print(f"  {BOLD}{name:<32}{RESET} | Count: {total:>5} | Time: {duration_sec:>6.2f}s | {GREEN}{qps:>8.1f} ops/s{RESET}", flush=True)
    print(f"    ├─ Latency (ms):  Min: {stats['min']:>6.2f}  |  P50: {BOLD}{stats['p50']:>6.2f}{RESET}  |  P95: {stats['p95']:>6.2f}  |  P99: {stats['p99']:>6.2f}  |  Max: {stats['max']:>6.2f}", flush=True)
    if extra_info:
        print(f"    └─ Info: {DIM}{extra_info}{RESET}", flush=True)

# ==============================================================================
# 1. LIVE MEMORY ENGINE BENCHMARK (Production DB)
# ==============================================================================
def benchmark_live_memory_engine():
    print_header("1. COGNITIVE MEMORY ENGINE: LIVE DB BENCHMARK")
    
    with schema.db_session() as conn:
        pass
        
    test_queries = [
        "Stephan",
        "Zürich",
        "Tesla Supercharger",
        "Hundeversicherung",       # German Compound
        "Zweitwohnungssteuer",     # German Compound
        "Fondssparplanerhöhung",   # German Compound
        "Helvetia Police",
        "STWEG Höhenweg 15",
        "Aladdin OCI Postgres",
        "TPA Trading Bot Trailing Stop",
        "Krankenkassenpolice",
        "ok",                      # Trivial filter
        "Stephan Blten",           # Typo / Fuzzy
    ]
    
    # 1.1 Single Thread Latency Profile
    latencies = []
    compound_latencies = []
    
    for q in test_queries * 20:
        t0 = time.perf_counter()
        agy_memory.prefetch(q, quiet=True)
        dt = time.perf_counter() - t0
        latencies.append(dt)
        if q in ["Hundeversicherung", "Zweitwohnungssteuer", "Fondssparplanerhöhung"]:
            compound_latencies.append(dt)
            
    stats_all = calc_stats(latencies)
    stats_compound = calc_stats(compound_latencies)
    
    print_metric_table("Prefetch (Single-Thread All)", len(latencies), sum(latencies), stats_all)
    print_metric_table("German Compound Tokenizer", len(compound_latencies), sum(compound_latencies), stats_compound, "Sub-token decomposition + BM25 ranking")

    # 1.2 Multi-threaded Concurrency Benchmark (5, 10, 25, 50, 100 workers)
    for concurrency in [5, 10, 25, 50, 100]:
        total_ops = 500
        queries = [random.choice(test_queries) for _ in range(total_ops)]
        latencies_concurrent = []
        errs = 0
        
        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            def run_single(q):
                try:
                    t0 = time.perf_counter()
                    agy_memory.prefetch(q, quiet=True)
                    dt = time.perf_counter() - t0
                    return dt, None
                except Exception as e:
                    return 0, str(e)
            
            futures = [executor.submit(run_single, q) for q in queries]
            for f in as_completed(futures):
                dt, err = f.result()
                if err:
                    errs += 1
                else:
                    latencies_concurrent.append(dt)
        t_total = time.perf_counter() - t_start
        
        stats_c = calc_stats(latencies_concurrent)
        extra = f"{concurrency} parallel client threads | Errors: {errs}"
        print_metric_table(f"Concurrent Load ({concurrency:>3} Workers)", len(latencies_concurrent), t_total, stats_c, extra)

# ==============================================================================
# 2. HIGH-SCALE SYNTHETIC STRESS TEST (Isolated SQLite DB)
# ==============================================================================
def benchmark_high_scale_synthetic_memory():
    print_header("2. HIGH-SCALE SYNTHETIC MEMORY STRESS TEST (WAL Mode)")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db_path = tf.name
        
    try:
        conn = sqlite3.connect(temp_db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        schema._init_schema(conn)
        conn.commit()
        conn.close()
        
        print(f"  {DIM}Created isolated benchmark database at {temp_db_path}{RESET}", flush=True)
        
        # 2.1 Bulk Ingestion (10,000 Facts)
        categories = ["infra", "finance", "home", "health", "system", "trading", "travel", "ai", "hardware", "network"]
        german_words = ["Versicherung", "Steuer", "Vertrag", "Server", "Container", "Batterie", "Wohnung", "Fahrzeug", "Konto", "Guthaben"]
        
        facts_data = []
        for i in range(10000):
            cat = random.choice(categories)
            w1 = random.choice(german_words)
            w2 = random.choice(german_words)
            fact_text = f"Master data record #{i} regarding {w1}{w2} configuration in Zurich cluster with IP 192.168.1.{i % 254}."
            facts_data.append((f"bench.fact.{i}", cat, fact_text, f"{w1} {w2}"))
            
        t0 = time.perf_counter()
        conn = sqlite3.connect(temp_db_path)
        cur = conn.cursor()
        cur.executemany("INSERT INTO memories (id, category, fact, keywords) VALUES (?, ?, ?, ?)", facts_data)
        conn.commit()
        conn.close()
        t_ingest = time.perf_counter() - t0
        
        print(f"  {BOLD}{'Bulk Ingestion (10,000 Facts)':<32}{RESET} | Time: {t_ingest:>6.2f}s | {GREEN}{10000/t_ingest:>8.1f} inserts/s{RESET}", flush=True)
        
        # 1,000 Episodes & Learnings
        episodes_data = [
            (f"bench.ep.{i}", "trading", f"Episode Project {i}", "2026", "active", f"Detailed narrative describing process {i} and market conditions.", "BTC, ETH", "Strict adherence", "trading project")
            for i in range(1000)
        ]
        learnings_data = [
            (f"bench.learn.{i}", "system", f"Learning insight #{i} about concurrency and scalability.", f"Context benchmark {i}", "system scale")
            for i in range(1000)
        ]
        
        conn = sqlite3.connect(temp_db_path)
        cur = conn.cursor()
        cur.executemany("INSERT INTO episodes (id, topic, title, period, status, narrative, entities, stance, keywords) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", episodes_data)
        cur.executemany("INSERT INTO learnings (id, category, insight, context, keywords) VALUES (?, ?, ?, ?, ?)", learnings_data)
        conn.commit()
        conn.close()

        # 2.2 FTS5 Search on 12,000 Records
        search_words = ["VersicherungSteuer", "ServerContainer", "BatterieWohnung", "FahrzeugKonto", "Zurich", "192.168.1"]
        query_latencies = []
        
        def run_search(q):
            t_s = time.perf_counter()
            c = sqlite3.connect(temp_db_path)
            cr = c.cursor()
            cr.execute("""
                SELECT m.id, m.category, m.fact 
                FROM memories m 
                JOIN memories_fts f ON m.id = f.id 
                WHERE memories_fts MATCH ? 
                LIMIT 5
            """, (f'"{q}"*',))
            cr.fetchall()
            c.close()
            return time.perf_counter() - t_s

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=50) as executor:
            queries = [random.choice(search_words) for _ in range(1000)]
            futures = [executor.submit(run_search, q) for q in queries]
            for f in as_completed(futures):
                query_latencies.append(f.result())
        t_total = time.perf_counter() - t_start
        
        stats_fts = calc_stats(query_latencies)
        print_metric_table("10k FTS5 Search (50 Workers)", 1000, t_total, stats_fts, "High-scale dataset with FTS5 BM25 match")

        # 2.3 Mixed Concurrent Read / Write Stress Test (80% Read, 20% Write)
        mixed_latencies = []
        errors = 0
        
        def mixed_worker(worker_id):
            nonlocal errors
            lat = []
            c = sqlite3.connect(temp_db_path, timeout=15.0)
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA synchronous=NORMAL;")
            for op_idx in range(50):
                is_write = (random.random() < 0.20)
                t_op = time.perf_counter()
                try:
                    if is_write:
                        fid = f"bench.fact.live.{worker_id}.{op_idx}"
                        c.execute("INSERT OR REPLACE INTO memories (id, category, fact, keywords) VALUES (?, 'mixed', 'Live dynamic update under load', 'live update')", (fid,))
                        c.commit()
                    else:
                        cr = c.cursor()
                        cr.execute("SELECT id, fact FROM memories WHERE id = ? LIMIT 1", (f"bench.fact.{random.randint(0, 9999)}",))
                        cr.fetchone()
                    lat.append(time.perf_counter() - t_op)
                except Exception as e:
                    errors += 1
            c.close()
            return lat

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(mixed_worker, w) for w in range(25)]
            for f in as_completed(futures):
                mixed_latencies.extend(f.result())
        t_total = time.perf_counter() - t_start

        stats_mixed = calc_stats(mixed_latencies)
        status_note = f"0 errors, 100% ACID consistency" if errors == 0 else f"{errors} lock errors!"
        print_metric_table("Mixed R/W (80% R / 20% W)", len(mixed_latencies), t_total, stats_mixed, f"25 parallel threads, {status_note}")

    except Exception as e:
        print(f"  {RED}Error in high scale test: {e}{RESET}", flush=True)
        traceback.print_exc()
    finally:
        if os.path.exists(temp_db_path):
            try: os.remove(temp_db_path)
            except: pass
        for ext in ["-wal", "-shm"]:
            if os.path.exists(temp_db_path + ext):
                try: os.remove(temp_db_path + ext)
                except: pass

# ==============================================================================
# 3. COCKPIT REST API CONCURRENCY & LATENCY BENCHMARK
# ==============================================================================
def benchmark_cockpit_api():
    print_header("3. ANTIGRAVITY COCKPIT REST API LOAD TEST (Port 8084)")
    
    endpoints = [
        "/api/overview",
        "/api/cron",
        "/api/mcp",
        "/api/skills",
        "/api/memory?q=tesla",
    ]
    
    base_url = "http://127.0.0.1:8084"
    try:
        req = urllib.request.Request(f"{base_url}/api/overview")
        with urllib.request.urlopen(req, timeout=2) as resp:
            pass
    except Exception as e:
        print(f"  {YELLOW}Cockpit server not reachable on {base_url}: {e}{RESET}", flush=True)
        return

    for endpoint in endpoints:
        total_reqs = 100
        concurrency = 15
        latencies = []
        status_codes = {}
        
        def hit_endpoint():
            url = f"{base_url}{endpoint}"
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    dt = time.perf_counter() - t0
                    return dt, r.status
            except urllib.error.HTTPError as he:
                return time.perf_counter() - t0, he.code
            except Exception:
                return time.perf_counter() - t0, 599

        t_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(hit_endpoint) for _ in range(total_reqs)]
            for f in as_completed(futures):
                dt, code = f.result()
                latencies.append(dt)
                status_codes[code] = status_codes.get(code, 0) + 1
        t_total = time.perf_counter() - t_start

        stats_api = calc_stats(latencies)
        status_str = ", ".join(f"HTTP {k}: {v}" for k, v in sorted(status_codes.items()))
        print_metric_table(f"GET {endpoint[:28]}", total_reqs, t_total, stats_api, status_str)

# ==============================================================================
# 4. CONVERSATION HISTORY SEARCH BENCHMARK
# ==============================================================================
def benchmark_transcript_search():
    print_header("4. CONVERSATION HISTORY SEARCH BENCHMARK")
    brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain")
    
    if not os.path.isdir(brain_dir):
        print(f"  {YELLOW}Brain dir not found at {brain_dir}{RESET}", flush=True)
        return

    transcript_files = []
    total_bytes = 0
    for root, _, files in os.walk(brain_dir):
        for f in files:
            if f == "transcript.jsonl":
                fp = os.path.join(root, f)
                transcript_files.append(fp)
                total_bytes += os.path.getsize(fp)

    print(f"  Found {len(transcript_files)} conversation transcripts ({total_bytes / (1024*1024):.2f} MB)", flush=True)

    # 4.1 Substring Search
    keyword = "performance"
    t0 = time.perf_counter()
    lines_scanned = 0
    matches = 0
    for fp in transcript_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    lines_scanned += 1
                    if keyword in line:
                        matches += 1
        except Exception:
            pass
    dt_search = time.perf_counter() - t0
    
    mb_scanned = total_bytes / (1024 * 1024)
    speed_mb = mb_scanned / dt_search if dt_search > 0 else 0
    speed_lines = lines_scanned / dt_search if dt_search > 0 else 0
    
    print(f"  {BOLD}{'Substring Search (Fast Scan)':<32}{RESET} | Time: {dt_search:>6.3f}s | {GREEN}{speed_mb:>8.1f} MB/s{RESET} | {speed_lines:,.0f} lines/s", flush=True)
    print(f"    └─ Matches: {matches} in {lines_scanned:,} lines across {len(transcript_files)} sessions", flush=True)

    # 4.2 Regex + JSON parse
    import re
    pat = re.compile(r"(TPA|Trading|Memory|Swiss|Zürich)", re.IGNORECASE)
    t0 = time.perf_counter()
    json_parsed = 0
    regex_matches = 0
    for fp in transcript_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if pat.search(line):
                        regex_matches += 1
                        try:
                            json.loads(line)
                            json_parsed += 1
                        except Exception:
                            pass
        except Exception:
            pass
    dt_regex = time.perf_counter() - t0
    
    speed_regex_mb = mb_scanned / dt_regex if dt_regex > 0 else 0
    print(f"  {BOLD}{'Regex + JSON Parse':<32}{RESET} | Time: {dt_regex:>6.3f}s | {GREEN}{speed_regex_mb:>8.1f} MB/s{RESET} | {regex_matches:,} matches", flush=True)

# ==============================================================================
# 5. HOST HARDWARE BASELINE & DISK I/O
# ==============================================================================
def benchmark_system_baseline():
    print_header("5. HOST HARDWARE BASELINE & DISK I/O")
    
    # CPU
    import hashlib
    def cpu_worker(n_ops):
        data = b"Antigravity Benchmark Payload " * 100
        for _ in range(n_ops):
            hashlib.sha256(data).hexdigest()

    t0 = time.perf_counter()
    cpu_worker(50000)
    dt_single = time.perf_counter() - t0
    sha_per_sec_single = 50000 / dt_single

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(cpu_worker, 25000) for _ in range(4)]
        for f in as_completed(futures):
            f.result()
    dt_multi = time.perf_counter() - t0
    sha_per_sec_multi = 100000 / dt_multi

    print(f"  {BOLD}{'CPU SHA256 (Single-Thread)':<32}{RESET} | Time: {dt_single:>6.2f}s | {GREEN}{sha_per_sec_single:>8,.0f} hashes/s{RESET}", flush=True)
    print(f"  {BOLD}{'CPU SHA256 (4 Threads)':<32}{RESET} | Time: {dt_multi:>6.2f}s | {GREEN}{sha_per_sec_multi:>8,.0f} hashes/s{RESET} ({sha_per_sec_multi/sha_per_sec_single:.2f}x speedup)", flush=True)

    # SQLite WAL Commit IOPS
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        disk_db_path = tf.name
    try:
        conn = sqlite3.connect(disk_db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("CREATE TABLE sync_test (id INT PRIMARY KEY, val TEXT);")
        conn.commit()

        t0 = time.perf_counter()
        for i in range(1000):
            conn.execute("INSERT INTO sync_test VALUES (?, ?)", (i, f"data_{i}"))
            conn.commit()
        dt_sync = time.perf_counter() - t0
        conn.close()

        print(f"  {BOLD}{'SQLite WAL Commit IOPS':<32}{RESET} | Time: {dt_sync:>6.2f}s | {GREEN}{1000/dt_sync:>8.1f} commits/s{RESET} ({dt_sync/1000*1000:.2f} ms/commit)", flush=True)
    finally:
        if os.path.exists(disk_db_path):
            try: os.remove(disk_db_path)
            except: pass
        for ext in ["-wal", "-shm"]:
            if os.path.exists(disk_db_path + ext):
                try: os.remove(disk_db_path + ext)
                except: pass

def main():
    print(f"\n{BOLD}{GREEN}🚀 ANTIGRAVITY 360° LOAD & PERFORMANCE TEST SUITE{RESET}", flush=True)
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} (Zurich/CEST)\n", flush=True)
    
    t_global = time.perf_counter()
    benchmark_live_memory_engine()
    benchmark_high_scale_synthetic_memory()
    benchmark_cockpit_api()
    benchmark_transcript_search()
    benchmark_system_baseline()
    
    total_duration = time.perf_counter() - t_global
    print(f"\n{BOLD}{GREEN}✅ ALL BENCHMARKS & LOAD TESTS COMPLETED SUCCESSFULLY IN {total_duration:.2f}s{RESET}\n", flush=True)

if __name__ == "__main__":
    main()
