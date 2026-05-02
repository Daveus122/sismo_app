import traceback 
import sys 
sys.stdout.reconfigure(encoding='utf-8') 
try: 
    import app 
except Exception as e: 
    traceback.print_exc() 
