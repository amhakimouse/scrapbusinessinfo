#!/usr/bin/env python3
"""Comprehensive end-to-end test script for all services in amazon-affiliate-leads.

Tests:
1. Pytest Unit & Integration Suite
2. CLI Scraper Execution (URL mode, Seeds mode, Niche Keyword mode)
3. FastAPI Server Endpoints (GET /api/health, GET /api/leads, GET /api/stats, POST /api/discover)
4. Frontend Build Validation
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import httpx

APP_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable

def log_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def run_pytest():
    log_section("1. RUNNING PYTEST UNIT & INTEGRATION SUITE")
    cmd = [PYTHON, "-m", "pytest", "tests", "-v"]
    res = subprocess.run(cmd, cwd=APP_DIR)
    if res.returncode != 0:
        print("\n[FAIL] Pytest suite failed!")
        return False
    print("\n[PASS] All Pytest tests passed!")
    return True

def run_cli_tests():
    log_section("2. TESTING CLI SCRAPER EXECUTION")
    
    # 2a. Test Single URL Scrape
    test_url = "https://thesommerhome.com/16-of-the-best-kitchen-gadgets-from-amazon/"
    print(f"Testing single URL scrape: {test_url}")
    cmd = [PYTHON, "main.py", "--url", test_url, "--mode", "fast"]
    res = subprocess.run(cmd, cwd=APP_DIR, capture_output=True, text=True)
    if "SUCCESS" not in res.stdout:
        print(f"[FAIL] Single URL scrape failed:\n{res.stdout}\n{res.stderr}")
        return False
    print("  ✓ Single URL scrape: OK")

    # 2b. Test Niche Keyword Discovery CLI
    print("Testing niche keyword CLI: --keyword \"kitchen\"")
    cmd = [PYTHON, "main.py", "--keyword", "kitchen", "--mode", "fast"]
    res = subprocess.run(cmd, cwd=APP_DIR, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[FAIL] Keyword discovery CLI failed:\n{res.stdout}\n{res.stderr}")
        return False
    print("  ✓ Keyword discovery CLI: OK")

    # 2c. Test Empty Seeds Error Reporting
    tmp_seeds = APP_DIR / "data" / "empty_test_seeds.txt"
    tmp_seeds.write_text("# only comment\n")
    env = dict(os.environ, SEEDS_FILE=str(tmp_seeds))
    res = subprocess.run([PYTHON, "main.py"], cwd=APP_DIR, capture_output=True, text=True, env=env)
    tmp_seeds.unlink(missing_ok=True)
    if "[ERROR] No seed URLs found to scrape" not in res.stdout:
        print(f"[FAIL] Loud empty seeds error not displayed:\n{res.stdout}")
        return False
    print("  ✓ Loud empty seeds error reporting: OK")

    print("\n[PASS] CLI Scraper tests passed!")
    return True

def run_api_tests():
    log_section("3. TESTING FASTAPI LIVE SERVER & ENDPOINTS")
    test_port = 8009
    server_process = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "api:app", "--port", str(test_port)],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{test_port}"
    max_wait = 10
    started = False

    try:
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                r = httpx.get(f"{base_url}/api/health", timeout=1.0)
                if r.status_code == 200:
                    started = True
                    break
            except Exception:
                time.sleep(0.3)

        if not started:
            print("[FAIL] FastAPI server failed to start within 10s.")
            return False

        print(f"FastAPI server running on port {test_port}.")

        # Test GET /api/health
        r_health = httpx.get(f"{base_url}/api/health")
        health = r_health.json()
        print(f"  ✓ GET /api/health: {health}")
        assert health["status"] == "ok"
        assert "leads_file_path" in health
        assert "seeds_file_path" in health

        # Test GET /api/stats
        r_stats = httpx.get(f"{base_url}/api/stats")
        stats = r_stats.json()
        print(f"  ✓ GET /api/stats: {stats}")
        assert "total" in stats
        assert "with_email" in stats

        # Test GET /api/leads
        r_leads = httpx.get(f"{base_url}/api/leads")
        leads = r_leads.json()
        print(f"  ✓ GET /api/leads: {len(leads)} lead(s) retrieved")
        assert isinstance(leads, list)

        # Test GET /api/leads?has_email=true
        r_leads_email = httpx.get(f"{base_url}/api/leads?has_email=true")
        leads_email = r_leads_email.json()
        print(f"  ✓ GET /api/leads?has_email=true: {len(leads_email)} lead(s) with email retrieved")
        assert all(len(l.get("emails", [])) > 0 for l in leads_email)

        # Test POST /api/discover
        r_disco = httpx.post(f"{base_url}/api/discover", json={"keyword": "espresso gear", "limit": 2}, timeout=60.0)
        disco = r_disco.json()
        print(f"  ✓ POST /api/discover: discovered {disco.get('discovered_urls_count')} URLs, scraped {disco.get('scraped_count')} leads")
        assert r_disco.status_code == 200

        # Test POST /api/discover/bulk
        r_bulk = httpx.post(f"{base_url}/api/discover/bulk", json={"keywords": ["espresso gear", "coffee roaster"], "limit": 1, "max_workers": 8}, timeout=60.0)
        bulk_data = r_bulk.json()
        print(f"  ✓ POST /api/discover/bulk: processed {bulk_data.get('total_niches')} niches across 8 workers, total scraped: {bulk_data.get('total_scraped')}")
        assert r_bulk.status_code == 200
        assert bulk_data.get("total_niches") == 2

        print("\n[PASS] All FastAPI live endpoints passed!")
        return True

    finally:
        server_process.terminate()
        server_process.wait()

def run_frontend_tests():
    log_section("4. TESTING FRONTEND BUILD")
    frontend_dir = APP_DIR / "frontend"
    if not (frontend_dir / "package.json").exists():
        print("[FAIL] frontend/package.json not found!")
        return False

    cmd = ["npm", "run", "build"]
    res = subprocess.run(cmd, cwd=frontend_dir, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[FAIL] Frontend build failed:\n{res.stdout}\n{res.stderr}")
        return False
    print("  ✓ Vite production build succeeded without errors.")
    print("\n[PASS] Frontend test passed!")
    return True

def main():
    print("\nStarting comprehensive test suite for Amazon Affiliate Leads...")
    results = {}
    
    results["Pytest Suite"] = run_pytest()
    results["CLI Scraper"] = run_cli_tests()
    results["FastAPI Server & Endpoints"] = run_api_tests()
    results["Frontend Build"] = run_frontend_tests()

    log_section("SUMMARY OF TEST RESULTS")
    all_passed = True
    for name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"  • {name:30s} : {status}")
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("\n🎉 ALL SERVICES ARE FULLY FUNCTIONAL AND VERIFIED!\n")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED. Please inspect the output above.\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
