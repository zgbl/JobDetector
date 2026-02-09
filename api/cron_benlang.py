from http.server import BaseHTTPRequestHandler
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.parse_benlang import BenLangParser
from scripts.import_benlang import BenLangImporter
# We also need to run the scraper after import!
from scripts.scrape_benlang import scrape_benlang_companies
import asyncio

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Identify if this is a cron request (optional security check)
        # auth_header = self.headers.get('Authorization')
        
        try:
            # 1. Parse File
            file_path = Path(__file__).parent.parent / 'data' / 'ImportList' / 'BenLang.txt'
            if not file_path.exists():
                self._send_response(404, {"error": "BenLang.txt not found"})
                return

            parser = BenLangParser()
            companies = parser.parse_file(str(file_path))
            
            # 2. Import Companies & Update Collection
            importer = BenLangImporter(dry_run=False)
            results = await importer.import_all_async(companies)
            
            # 3. Trigger Scraping (Async)
            # Since this is a serverless function, we should ideally await the scraping
            # But Vercel has timeouts (10s-60s). Scrape might take longer.
            # Only option is to try to scrape a few or rely on a separate worker.
            # For now, let's try to run it. BenLang scraper uses a semaphore of 5.
            # 348 companies... might timeout.
            # Optimization: Only scrape NEWLY imported companies?
            # Or reliance on the fact that 'scrape_benlang_companies' checks ALL.
            
            # For the cron job, maybe we just trigger the scrape for *active* ones?
            # Let's try to run it. If it times out, we might need a better architecture (queue).
            # But for this user request, "like other background imports", usually implies straight execution.

            # Loop init for async
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(scrape_benlang_companies())
            
            response_data = {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "import_results": {
                    "total": results['total'],
                    "imported": results['imported'],
                    "exists": results['exists'],
                    "failed": results['failed']
                },
                "message": "Import and scrape completed"
            }
            self._send_response(200, response_data)
            
        except Exception as e:
            self._send_response(500, {"status": "error", "error": str(e)})

    def _send_response(self, code, data):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
